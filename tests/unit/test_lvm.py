# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for LvmPvNode, LvmVgNode, LvmLvNode."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.hardware import HardwareNode
from storage.lvm import LvmLvNode, LvmPvNode, LvmVgNode


def _hw(path: str = "/dev/sda") -> HardwareNode:
    return HardwareNode({"id": "hw", "path": path}, Context())


def test_pv_validate_requires_one_parent() -> None:
    pv = LvmPvNode({"id": "pv"}, Context())
    with pytest.raises(NodeValidationError, match="exactly one parent"):
        pv.validate()


def test_pv_command_lines_calls_pvcreate() -> None:
    pv = LvmPvNode({"id": "pv", "parents": "hw"}, Context())
    pv._resolved_parents = [_hw("/dev/sda3")]
    assert pv.command_lines() == [["pvcreate", "-ff", "-y", "/dev/sda3"]]


def test_pv_device_path_is_parent_device() -> None:
    pv = LvmPvNode({"id": "pv", "parents": "hw"}, Context())
    pv._resolved_parents = [_hw("/dev/sda3")]
    assert pv.device_path() == "/dev/sda3"


def test_vg_validate_requires_parents() -> None:
    vg = LvmVgNode({"id": "vg"}, Context())
    with pytest.raises(NodeValidationError, match="at least one PV parent"):
        vg.validate()


def test_vg_command_lines_single_pv() -> None:
    vg = LvmVgNode({"id": "vg", "parents": "pv1"}, Context())
    pv = LvmPvNode({"id": "pv1", "parents": "hw"}, Context())
    pv._resolved_parents = [_hw("/dev/sda3")]
    vg._resolved_parents = [pv]
    assert vg.command_lines() == [
        ["vgcreate", "-f", "-y", "vg", "/dev/sda3"],
    ]


def test_vg_command_lines_multiple_pvs() -> None:
    vg = LvmVgNode({"id": "vg", "parents": ["pv1", "pv2"]}, Context())
    pv1 = LvmPvNode({"id": "pv1", "parents": "hwA"}, Context())
    pv1._resolved_parents = [_hw("/dev/sda3")]
    pv2 = LvmPvNode({"id": "pv2", "parents": "hwB"}, Context())
    pv2._resolved_parents = [_hw("/dev/sdb3")]
    vg._resolved_parents = [pv1, pv2]
    assert vg.command_lines() == [
        ["vgcreate", "-f", "-y", "vg", "/dev/sda3", "/dev/sdb3"],
    ]


def test_vg_device_path_is_none() -> None:
    vg = LvmVgNode({"id": "vg", "parents": "pv"}, Context())
    assert vg.device_path() is None


def test_vg_name_defaults_to_id() -> None:
    vg = LvmVgNode({"id": "vg-host", "parents": "pv"}, Context())
    assert vg.name == "vg-host"


def test_vg_name_override() -> None:
    vg = LvmVgNode({"id": "node1", "name": "actual-vg", "parents": "pv"}, Context())
    assert vg.name == "actual-vg"


def test_lv_requires_name() -> None:
    with pytest.raises(NodeValidationError, match="missing 'name'"):
        LvmLvNode({"id": "lv", "parents": "vg", "size": "1G"}, Context())


def test_lv_requires_size() -> None:
    with pytest.raises(NodeValidationError, match="missing 'size'"):
        LvmLvNode({"id": "lv", "parents": "vg", "name": "c_root"}, Context())


def test_lv_validate_rejects_non_vg_parent() -> None:
    lv = LvmLvNode(
        {"id": "lv", "parents": "hw", "name": "c_root", "size": "8G"}, Context()
    )
    lv._resolved_parents = [_hw("/dev/sda")]
    with pytest.raises(NodeValidationError, match="parent must be lvm-vg"):
        lv.validate()


def test_lv_command_lines_fixed_size() -> None:
    lv = LvmLvNode(
        {"id": "lv", "parents": "vg", "name": "c_root", "size": "8G"}, Context()
    )
    vg = LvmVgNode({"id": "vg-host", "parents": "pv"}, Context())
    lv._resolved_parents = [vg]
    lines = lv.command_lines()
    assert lines == [
        ["lvcreate", "-y", "-W", "y", "-L", f"{8 * 1024**3}B", "-n", "c_root", "vg-host"],
    ]


def test_lv_command_lines_max_size() -> None:
    lv = LvmLvNode(
        {"id": "lv", "parents": "vg", "name": "full", "size": "{max}"}, Context()
    )
    vg = LvmVgNode({"id": "vg-host", "parents": "pv"}, Context())
    lv._resolved_parents = [vg]
    lines = lv.command_lines()
    assert lines == [
        ["lvcreate", "-y", "-W", "y", "-l", "100%FREE", "-n", "full", "vg-host"],
    ]


def test_lv_device_path() -> None:
    lv = LvmLvNode(
        {"id": "lv", "parents": "vg", "name": "c_root", "size": "8G"}, Context()
    )
    vg = LvmVgNode({"id": "vg-host", "parents": "pv"}, Context())
    lv._resolved_parents = [vg]
    assert lv.device_path() == "/dev/vg-host/c_root"
