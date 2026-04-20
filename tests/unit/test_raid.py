# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for Raid1Node."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.hardware import HardwareNode
from storage.raid import Raid1Node


def _hw(path: str) -> HardwareNode:
    return HardwareNode({"id": path, "path": path}, Context())


def test_raid_requires_name() -> None:
    with pytest.raises(NodeValidationError, match="missing 'name'"):
        Raid1Node({"id": "r", "parents": ["a", "b"]}, Context())


def test_raid_validate_needs_two_parents() -> None:
    n = Raid1Node({"id": "r", "parents": "only", "name": "md0"}, Context())
    with pytest.raises(NodeValidationError, match="at least two parents"):
        n.validate()


def test_raid_name_pattern() -> None:
    n = Raid1Node({"id": "r", "parents": ["a", "b"], "name": "raid0"}, Context())
    with pytest.raises(NodeValidationError, match="must match"):
        n.validate()


def test_raid_device_path() -> None:
    n = Raid1Node({"id": "r", "parents": ["a", "b"], "name": "md128"}, Context())
    assert n.device_path() == "/dev/md128"


def test_raid_command_lines() -> None:
    n = Raid1Node(
        {"id": "r", "parents": ["pA", "pB"], "name": "md128"}, Context()
    )
    n._resolved_parents = [_hw("/dev/sda1"), _hw("/dev/sdb1")]
    lines = n.command_lines()
    assert lines[0] == ["mdadm", "--zero-superblock", "--force", "/dev/sda1"]
    assert lines[1] == ["mdadm", "--zero-superblock", "--force", "/dev/sdb1"]
    create = lines[2]
    assert create[:4] == ["mdadm", "--create", "--verbose", "--run"]
    assert "--level=1" in create
    assert "--raid-devices=2" in create
    assert "--metadata=1.2" in create
    assert "--assume-clean" in create
    assert create[-3] == "/dev/md128"
    assert create[-2:] == ["/dev/sda1", "/dev/sdb1"]


def test_raid_command_lines_three_members() -> None:
    n = Raid1Node(
        {"id": "r", "parents": ["a", "b", "c"], "name": "md0"}, Context()
    )
    n._resolved_parents = [_hw("/dev/sda1"), _hw("/dev/sdb1"), _hw("/dev/sdc1")]
    lines = n.command_lines()
    zero_lines = [l for l in lines if l[1] == "--zero-superblock"]
    assert len(zero_lines) == 3
    create = lines[-1]
    assert "--raid-devices=3" in create
