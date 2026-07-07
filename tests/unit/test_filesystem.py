# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for FilesystemNode."""

from __future__ import annotations

import logging

import pytest

from storage.base import Context, NodeValidationError
from storage.filesystem import FilesystemNode, _sanitize_fat_label
from storage.hardware import HardwareNode


def _hw(path: str = "/dev/sda1") -> HardwareNode:
    return HardwareNode({"id": "hw", "path": path}, Context())


def test_requires_fstype() -> None:
    with pytest.raises(NodeValidationError, match="missing 'fstype'"):
        FilesystemNode(
            {"id": "fs", "parents": "hw", "mountpoint": "/"}, Context()
        )


def test_requires_mountpoint() -> None:
    with pytest.raises(NodeValidationError, match="missing 'mountpoint'"):
        FilesystemNode(
            {"id": "fs", "parents": "hw", "fstype": "ext4"}, Context()
        )


def test_validate_rejects_unknown_fstype() -> None:
    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "reiserfs", "mountpoint": "/"},
        Context(),
    )
    with pytest.raises(NodeValidationError, match="unknown fstype"):
        fs.validate()


def test_validate_requires_absolute_mountpoint() -> None:
    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "ext4", "mountpoint": "boot"},
        Context(),
    )
    with pytest.raises(NodeValidationError, match="mountpoint must be absolute"):
        fs.validate()


def test_target_path_prepends_control_path() -> None:
    ctx = Context(control_path="/target")
    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "ext4", "mountpoint": "/boot"},
        ctx,
    )
    assert fs.target_path() == "/target/boot"


def test_target_path_root_mountpoint() -> None:
    ctx = Context(control_path="/target")
    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "ext4", "mountpoint": "/"},
        ctx,
    )
    assert fs.target_path() == "/target"


def test_target_path_nested() -> None:
    ctx = Context(control_path="/target")
    fs = FilesystemNode(
        {
            "id": "fs",
            "parents": "hw",
            "fstype": "ext4",
            "mountpoint": "/boot/efi",
        },
        ctx,
    )
    assert fs.target_path() == "/target/boot/efi"


def test_command_lines_ext4_with_label() -> None:
    fs = FilesystemNode(
        {
            "id": "fs",
            "parents": "hw",
            "fstype": "ext4",
            "mountpoint": "/",
            "label": "foo-root",
        },
        Context(control_path="/target"),
    )
    fs._resolved_parents = [_hw("/dev/sda1")]
    cmds = fs.command_lines()
    assert cmds[0].argv == ["mkfs.ext4", "-F", "-q", "-L", "foo-root", "/dev/sda1"]
    assert cmds[1].argv == ["mkdir", "-p", "/target"]
    assert cmds[2].argv == ["mount", "/dev/sda1", "/target"]


def test_command_lines_xfs() -> None:
    fs = FilesystemNode(
        {
            "id": "fs",
            "parents": "hw",
            "fstype": "xfs",
            "mountpoint": "/srv",
            "label": "ssdraid",
        },
        Context(control_path="/target"),
    )
    fs._resolved_parents = [_hw("/dev/md128")]
    cmds = fs.command_lines()
    assert cmds[0].argv == ["mkfs.xfs", "-f", "-q", "-L", "ssdraid", "/dev/md128"]


def test_command_lines_fat32_label_uppercased(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fs = FilesystemNode(
        {
            "id": "fs",
            "parents": "hw",
            "fstype": "fat32",
            "mountpoint": "/boot/efi",
            "label": "foo-EFI",
        },
        Context(),
    )
    fs._resolved_parents = [_hw("/dev/sda1")]
    caplog.set_level(logging.WARNING, logger="sprov")
    cmds = fs.command_lines()
    assert cmds[0].argv == ["mkfs.vfat", "-F", "32", "-n", "FOO-EFI", "/dev/sda1"]
    assert "sanitized" in caplog.text


def test_command_lines_fat32_long_label_truncated() -> None:
    fs = FilesystemNode(
        {
            "id": "fs",
            "parents": "hw",
            "fstype": "fat32",
            "mountpoint": "/boot/efi",
            "label": "this-label-is-too-long",
        },
        Context(),
    )
    fs._resolved_parents = [_hw("/dev/sda1")]
    cmds = fs.command_lines()
    label = cmds[0].argv[4]  # mkfs.vfat has no -q, so label is still at index 4
    assert len(label) == 11
    assert label == "THIS-LABEL-"


def test_sanitize_fat_label_exact_edge() -> None:
    assert _sanitize_fat_label("abc") == "ABC"
    assert _sanitize_fat_label("12345678901") == "12345678901"
    assert _sanitize_fat_label("123456789012") == "12345678901"


def test_mkfs_options_appended() -> None:
    fs = FilesystemNode(
        {
            "id": "fs",
            "parents": "hw",
            "fstype": "ext4",
            "mountpoint": "/",
            "label": "root",
            "mkfs_options": ["-E", "lazy_itable_init=0"],
        },
        Context(),
    )
    fs._resolved_parents = [_hw("/dev/sda1")]
    cmds = fs.command_lines()
    assert cmds[0].argv == [
        "mkfs.ext4", "-F", "-q", "-L", "root", "-E", "lazy_itable_init=0", "/dev/sda1",
    ]


def test_device_path_is_none() -> None:
    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "ext4", "mountpoint": "/"},
        Context(),
    )
    assert fs.device_path() is None


def test_all_fstypes_have_mkfs() -> None:
    for fstype in ("ext2", "ext3", "ext4", "xfs", "btrfs", "fat32", "vfat"):
        fs = FilesystemNode(
            {
                "id": "fs",
                "parents": "hw",
                "fstype": fstype,
                "mountpoint": "/",
            },
            Context(),
        )
        fs._resolved_parents = [_hw("/dev/sda1")]
        cmds = fs.command_lines()
        assert cmds[0].argv[0].startswith("mkfs.")
