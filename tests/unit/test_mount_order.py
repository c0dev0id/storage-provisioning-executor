# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for FilesystemNode mount-order reshuffling."""

from __future__ import annotations

from storage.base import Context
from storage.executor import Executor
from storage.filesystem import FilesystemNode
from storage.hardware import HardwareNode


def _hw(node_id: str, path: str) -> HardwareNode:
    return HardwareNode({"id": node_id, "path": path}, Context())


def _fs(node_id: str, parent: str, mountpoint: str) -> FilesystemNode:
    return FilesystemNode(
        {
            "id": node_id,
            "parents": parent,
            "fstype": "ext4",
            "mountpoint": mountpoint,
        },
        Context(),
    )


def test_root_before_boot_before_efi() -> None:
    hw1 = _hw("hw1", "/dev/sda1")
    hw2 = _hw("hw2", "/dev/sdb1")
    hw3 = _hw("hw3", "/dev/sdc1")
    fs_efi = _fs("fs_efi", "hw1", "/boot/efi")
    fs_root = _fs("fs_root", "hw2", "/")
    fs_boot = _fs("fs_boot", "hw3", "/boot")
    ex = Executor([hw1, hw2, hw3, fs_efi, fs_root, fs_boot])
    ordered = ex.prepare()
    fs_ids = [n.id for n in ordered if isinstance(n, FilesystemNode)]
    assert fs_ids == ["fs_root", "fs_boot", "fs_efi"]


def test_mounts_come_after_storage_ops() -> None:
    hw = _hw("hw", "/dev/sda1")
    fs = _fs("fs", "hw", "/")
    ex = Executor([fs, hw])
    ordered = ex.prepare()
    assert [n.id for n in ordered] == ["hw", "fs"]


def test_same_depth_keeps_source_order() -> None:
    hw1 = _hw("hw1", "/dev/sda1")
    hw2 = _hw("hw2", "/dev/sdb1")
    fs_var = _fs("fs_var", "hw1", "/var")
    fs_srv = _fs("fs_srv", "hw2", "/srv")
    ex = Executor([hw1, hw2, fs_var, fs_srv])
    ordered = ex.prepare()
    fs_ids = [n.id for n in ordered if isinstance(n, FilesystemNode)]
    assert fs_ids == ["fs_var", "fs_srv"]


def test_deep_nesting_four_levels() -> None:
    hw1 = _hw("hw1", "/dev/sda1")
    hw2 = _hw("hw2", "/dev/sdb1")
    hw3 = _hw("hw3", "/dev/sdc1")
    hw4 = _hw("hw4", "/dev/sdd1")
    fs_deep = _fs("fs_deep", "hw1", "/a/b/c/d")
    fs_root = _fs("fs_root", "hw2", "/")
    fs_ab = _fs("fs_ab", "hw3", "/a/b")
    fs_a = _fs("fs_a", "hw4", "/a")
    ex = Executor([hw1, hw2, hw3, hw4, fs_deep, fs_root, fs_ab, fs_a])
    ordered = ex.prepare()
    fs_ids = [n.id for n in ordered if isinstance(n, FilesystemNode)]
    assert fs_ids == ["fs_root", "fs_a", "fs_ab", "fs_deep"]
