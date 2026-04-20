# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for partition_device() suffix rules and HardwareNode command lines."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.hardware import HardwareNode
from storage.partition import PartitionNode, partition_device


@pytest.mark.parametrize(
    "parent,index,expected",
    [
        ("/dev/sda", 1, "/dev/sda1"),
        ("/dev/sda", 2, "/dev/sda2"),
        ("/dev/vda", 3, "/dev/vda3"),
        ("/dev/hdb", 4, "/dev/hdb4"),
        ("/dev/xvda", 1, "/dev/xvda1"),
        ("/dev/nvme0n1", 1, "/dev/nvme0n1p1"),
        ("/dev/nvme1n2", 3, "/dev/nvme1n2p3"),
        ("/dev/mmcblk0", 1, "/dev/mmcblk0p1"),
        ("/dev/loop0", 1, "/dev/loop0p1"),
        ("/dev/md128", 1, "/dev/md128p1"),
        ("/dev/disk/by-id/nvme_Vendor_device_Serial1", 2,
         "/dev/disk/by-id/nvme_Vendor_device_Serial1p2"),
    ],
)
def test_partition_device_suffix_rules(parent: str, index: int, expected: str) -> None:
    assert partition_device(parent, index) == expected


def test_partition_device_zero_index_rejected() -> None:
    with pytest.raises(ValueError):
        partition_device("/dev/sda", 0)


def test_partition_device_negative_index_rejected() -> None:
    with pytest.raises(ValueError):
        partition_device("/dev/sda", -1)


# -----------------------------------------------------------
# HardwareNode
# -----------------------------------------------------------


def test_hardware_requires_path() -> None:
    with pytest.raises(NodeValidationError, match="missing 'path'"):
        HardwareNode({"id": "hw"}, Context())


def test_hardware_rejects_parents() -> None:
    with pytest.raises(NodeValidationError, match="must not have parents"):
        HardwareNode({"id": "hw", "path": "/dev/sda", "parents": "other"}, Context())


def test_hardware_overwrite_yes_requires_label() -> None:
    node = HardwareNode(
        {"id": "hw", "path": "/dev/sda", "overwrite": "yes"}, Context()
    )
    with pytest.raises(NodeValidationError, match="requires a label"):
        node.validate()


def test_hardware_bad_overwrite_rejected() -> None:
    node = HardwareNode(
        {"id": "hw", "path": "/dev/sda", "overwrite": "maybe", "label": "gpt"},
        Context(),
    )
    with pytest.raises(NodeValidationError, match="overwrite must be yes/no"):
        node.validate()


def test_hardware_bad_label_rejected() -> None:
    node = HardwareNode(
        {"id": "hw", "path": "/dev/sda", "overwrite": "yes", "label": "bsd"},
        Context(),
    )
    with pytest.raises(NodeValidationError, match="label must be one of"):
        node.validate()


def test_hardware_erase_all_plus_mklabel() -> None:
    node = HardwareNode(
        {
            "id": "hw",
            "path": "/dev/sda",
            "overwrite": "yes",
            "erase": "all",
            "label": "gpt",
        },
        Context(),
    )
    node.validate()
    lines = node.command_lines()
    assert any("dd if=/dev/zero" in part for argv in lines for part in argv)
    assert ["parted", "-s", "/dev/sda", "mklabel", "gpt"] in lines


def test_hardware_erase_1g_emits_dd_count() -> None:
    node = HardwareNode(
        {
            "id": "hw",
            "path": "/dev/sda",
            "erase": "1G",
            "overwrite": "no",
        },
        Context(),
    )
    node.validate()
    lines = node.command_lines()
    dd = lines[0]
    assert dd[0] == "dd"
    assert "count=1024" in dd


def test_hardware_overwrite_no_label_not_required() -> None:
    node = HardwareNode(
        {"id": "hw", "path": "/dev/sda", "overwrite": "no"},
        Context(),
    )
    node.validate()
    assert node.command_lines() == []


def test_hardware_device_path() -> None:
    node = HardwareNode({"id": "hw", "path": "/dev/sda"}, Context())
    assert node.device_path() == "/dev/sda"


# -----------------------------------------------------------
# PartitionNode: construction-level checks (index is Executor-assigned,
# so full command-line generation is covered in executor tests).
# -----------------------------------------------------------


def test_partition_requires_size() -> None:
    with pytest.raises(NodeValidationError, match="missing 'size'"):
        PartitionNode({"id": "p", "parents": "hw"}, Context())


def test_partition_validate_requires_one_parent() -> None:
    node = PartitionNode({"id": "p", "parents": [], "size": "1G"}, Context())
    with pytest.raises(NodeValidationError, match="exactly one parent"):
        node.validate()


def test_partition_validate_accepts_good_input() -> None:
    node = PartitionNode(
        {"id": "p", "parents": "hw", "size": "1G", "flags": ["boot", "esp"]},
        Context(),
    )
    node.validate()


def test_partition_validate_rejects_bad_size() -> None:
    node = PartitionNode({"id": "p", "parents": "hw", "size": "1Q"}, Context())
    with pytest.raises(ValueError):
        node.validate()


def test_partition_device_before_index_assigned() -> None:
    hw = HardwareNode({"id": "hw", "path": "/dev/sda"}, Context())
    part = PartitionNode(
        {"id": "p", "parents": "hw", "size": "1G"},
        Context(),
    )
    part._resolved_parents = [hw]
    with pytest.raises(NodeValidationError, match="index not assigned"):
        part.device_path()


def test_partition_device_after_index_assigned() -> None:
    hw = HardwareNode({"id": "hw", "path": "/dev/nvme0n1"}, Context())
    part = PartitionNode(
        {"id": "p", "parents": "hw", "size": "1G"},
        Context(),
    )
    part._resolved_parents = [hw]
    part._index = 2
    assert part.device_path() == "/dev/nvme0n1p2"
