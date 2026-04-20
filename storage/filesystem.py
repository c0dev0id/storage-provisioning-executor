# SPDX-License-Identifier: GPL-2.0-or-later
"""FilesystemNode — mkfs + mount under control.path."""

from __future__ import annotations

import logging
import posixpath
from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand


_logger = logging.getLogger("sprov")


def _mkfs_ext4(dev: str, label: str | None, options: list[str]) -> list[str]:
    argv: list[str] = ["mkfs.ext4", "-F"]
    if label is not None:
        argv.extend(["-L", label])
    argv.extend(options)
    argv.append(dev)
    return argv


def _mkfs_ext2(dev: str, label: str | None, options: list[str]) -> list[str]:
    argv: list[str] = ["mkfs.ext2", "-F"]
    if label is not None:
        argv.extend(["-L", label])
    argv.extend(options)
    argv.append(dev)
    return argv


def _mkfs_ext3(dev: str, label: str | None, options: list[str]) -> list[str]:
    argv: list[str] = ["mkfs.ext3", "-F"]
    if label is not None:
        argv.extend(["-L", label])
    argv.extend(options)
    argv.append(dev)
    return argv


def _mkfs_xfs(dev: str, label: str | None, options: list[str]) -> list[str]:
    argv: list[str] = ["mkfs.xfs", "-f"]
    if label is not None:
        argv.extend(["-L", label])
    argv.extend(options)
    argv.append(dev)
    return argv


def _mkfs_btrfs(dev: str, label: str | None, options: list[str]) -> list[str]:
    argv: list[str] = ["mkfs.btrfs", "-f"]
    if label is not None:
        argv.extend(["-L", label])
    argv.extend(options)
    argv.append(dev)
    return argv


def _mkfs_fat32(dev: str, label: str | None, options: list[str]) -> list[str]:
    argv: list[str] = ["mkfs.vfat", "-F", "32"]
    if label is not None:
        sanitized = _sanitize_fat_label(label)
        if sanitized != label:
            _logger.warning(
                "fat32 label %r sanitized to %r (max 11 chars, uppercase)",
                label,
                sanitized,
            )
        argv.extend(["-n", sanitized])
    argv.extend(options)
    argv.append(dev)
    return argv


def _sanitize_fat_label(label: str) -> str:
    return label.upper()[:11]


MKFS_DISPATCH = {
    "ext2": _mkfs_ext2,
    "ext3": _mkfs_ext3,
    "ext4": _mkfs_ext4,
    "xfs": _mkfs_xfs,
    "btrfs": _mkfs_btrfs,
    "fat32": _mkfs_fat32,
    "vfat": _mkfs_fat32,
}


class FilesystemNode(Node):
    TYPE: ClassVar[str] = "filesystem"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        if "fstype" not in raw:
            raise NodeValidationError(
                f"filesystem id={self.id}: missing 'fstype'"
            )
        self.fstype: str = str(raw["fstype"]).lower()
        if "mountpoint" not in raw:
            raise NodeValidationError(
                f"filesystem id={self.id}: missing 'mountpoint'"
            )
        self.mountpoint: str = str(raw["mountpoint"])
        self.label: str | None = (
            None if raw.get("label") is None else str(raw["label"])
        )
        self.mkfs_options: list[str] = [
            str(x) for x in (raw.get("mkfs_options") or [])
        ]

    def validate(self) -> None:
        if len(self.parents) != 1:
            raise NodeValidationError(
                f"filesystem id={self.id}: must have exactly one parent"
            )
        if self.fstype not in MKFS_DISPATCH:
            raise NodeValidationError(
                f"filesystem id={self.id}: unknown fstype {self.fstype!r}"
            )
        if not self.mountpoint.startswith("/"):
            raise NodeValidationError(
                f"filesystem id={self.id}: mountpoint must be absolute, "
                f"got {self.mountpoint!r}"
            )

    def execute(self) -> None:
        for cmd in self.command_lines():
            self.ctx.sys.run(cmd.argv, stdin=cmd.stdin, check=cmd.check)
        target = self.target_path()
        self.register_cleanup(lambda: self._umount(target))

    def device_path(self) -> None:
        return None

    def target_path(self) -> str:
        return posixpath.normpath(self.ctx.control_path + self.mountpoint)

    def command_lines(self) -> list[ShellCommand]:
        dev = self._require_one_parent().device_path()
        if dev is None:
            raise NodeValidationError(
                f"filesystem id={self.id}: parent has no device path"
            )
        target = self.target_path()
        mkfs_argv = MKFS_DISPATCH[self.fstype](dev, self.label, self.mkfs_options)
        return [
            ShellCommand(
                argv=mkfs_argv,
                comment=f"create {self.fstype} on {dev}",
            ),
            ShellCommand(
                argv=["mkdir", "-p", target],
                comment=f"ensure mountpoint {target}",
            ),
            ShellCommand(
                argv=["mount", dev, target],
                comment=f"mount {dev} at {target}",
            ),
        ]

    def _umount(self, target: str) -> None:
        self.ctx.sys.run(["umount", target], check=False)
