# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for SwapNode."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.hardware import HardwareNode
from storage.swap import SwapNode


def _hw(path: str = "/dev/sda2") -> HardwareNode:
    return HardwareNode({"id": "hw", "path": path}, Context())


def test_requires_one_parent_zero() -> None:
    sw = SwapNode({"id": "sw", "parents": []}, Context())
    sw._resolved_parents = []
    with pytest.raises(NodeValidationError, match="must have exactly one parent"):
        sw.validate()


def test_requires_one_parent_two() -> None:
    hw1 = _hw("/dev/sda2")
    hw2 = _hw("/dev/sdb2")
    sw = SwapNode({"id": "sw", "parents": ["hw1", "hw2"]}, Context())
    sw._resolved_parents = [hw1, hw2]
    with pytest.raises(NodeValidationError, match="must have exactly one parent"):
        sw.validate()


def test_validate_parent_no_device_path() -> None:
    from storage.filesystem import FilesystemNode

    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "ext4", "mountpoint": "/"},
        Context(),
    )
    fs._resolved_parents = [_hw()]
    sw = SwapNode({"id": "sw", "parents": "fs"}, Context())
    sw._resolved_parents = [fs]
    with pytest.raises(NodeValidationError, match="parent has no device path"):
        sw.validate()


def test_device_path_is_none() -> None:
    sw = SwapNode({"id": "sw", "parents": "hw"}, Context())
    assert sw.device_path() is None


def test_command_lines_no_label() -> None:
    sw = SwapNode({"id": "sw", "parents": "hw"}, Context())
    sw._resolved_parents = [_hw("/dev/sda2")]
    cmds = sw.command_lines()
    assert len(cmds) == 2
    assert cmds[0].argv == ["mkswap", "/dev/sda2"]
    assert cmds[1].argv == ["swapon", "/dev/sda2"]


def test_command_lines_with_label() -> None:
    sw = SwapNode({"id": "sw", "parents": "hw", "label": "myswap"}, Context())
    sw._resolved_parents = [_hw("/dev/sda2")]
    cmds = sw.command_lines()
    assert cmds[0].argv == ["mkswap", "-L", "myswap", "/dev/sda2"]
    assert cmds[1].argv == ["swapon", "/dev/sda2"]


def test_mkswap_options_appended() -> None:
    sw = SwapNode(
        {
            "id": "sw",
            "parents": "hw",
            "label": "swap",
            "mkswap_options": ["-p", "2048"],
        },
        Context(),
    )
    sw._resolved_parents = [_hw("/dev/sda2")]
    cmds = sw.command_lines()
    assert cmds[0].argv == ["mkswap", "-L", "swap", "-p", "2048", "/dev/sda2"]


def test_mkswap_options_no_label() -> None:
    sw = SwapNode(
        {"id": "sw", "parents": "hw", "mkswap_options": ["-v1"]},
        Context(),
    )
    sw._resolved_parents = [_hw("/dev/sda2")]
    cmds = sw.command_lines()
    assert cmds[0].argv == ["mkswap", "-v1", "/dev/sda2"]
