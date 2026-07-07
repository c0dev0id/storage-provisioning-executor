# SPDX-License-Identifier: GPL-2.0-or-later
"""PartitionNode — a single partition on a parent hardware device."""

from __future__ import annotations

from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand
from storage.system import SIZE_MAX, parse_size


def partition_device(parent_path: str, index: int) -> str:
    """Compute the kernel device path of partition <index> on <parent_path>.

    nvme, mmcblk, loop, and paths ending in a digit insert a 'p' before the
    index; everything else concatenates directly.
    """
    if index < 1:
        raise ValueError(f"partition index must be >= 1, got {index}")
    tail = parent_path.rsplit("/", 1)[-1]
    needs_p = (
        tail and tail[-1].isdigit()
    ) or any(token in tail for token in ("nvme", "mmcblk", "loop", "md"))
    sep = "p" if needs_p else ""
    return f"{parent_path}{sep}{index}"


class PartitionNode(Node):
    TYPE: ClassVar[str] = "partition"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        self.label: str | None = (
            None if raw.get("label") is None else str(raw["label"])
        )
        self.begin: str | None = (
            None if raw.get("begin") is None else str(raw["begin"])
        )
        if "size" not in raw:
            raise NodeValidationError(
                f"partition id={self.id}: missing 'size'"
            )
        self.size: str = str(raw["size"])
        self.uuid: str | None = (
            None if raw.get("uuid") is None else str(raw["uuid"])
        )
        self.flags: list[str] = list(raw.get("flags") or [])
        # Set by Executor during reference resolution.
        self._index: int | None = None
        self._begin_expr: str | None = None
        self._end_expr: str | None = None

    def validate(self) -> None:
        if len(self.parents) != 1:
            raise NodeValidationError(
                f"partition id={self.id}: must have exactly one parent"
            )
        parse_size(self.size)
        if not all(isinstance(f, str) for f in self.flags):
            raise NodeValidationError(
                f"partition id={self.id}: flags must be a list of strings"
            )

    def device_path(self) -> str:
        parent_path = self._require_one_parent().device_path()
        if parent_path is None:
            raise NodeValidationError(
                f"partition id={self.id}: parent has no device path"
            )
        if self._index is None:
            raise NodeValidationError(
                f"partition id={self.id}: index not assigned (Executor not run)"
            )
        return partition_device(parent_path, self._index)

    def command_lines(self) -> list[ShellCommand]:
        parent_path = self._require_one_parent().device_path()
        if parent_path is None or self._index is None:
            raise NodeValidationError(
                f"partition id={self.id}: parent path or index unresolved"
            )
        begin = self._begin_expr or (self.begin or "1MiB")
        end = self._end_expr or _compute_end_expr(begin, self.size)
        name = self.label or self.id
        lines: list[ShellCommand] = [
            ShellCommand(
                argv=[
                    "parted", "-s", "-a", "optimal", parent_path, "--",
                    "mkpart", name, begin, end,
                ],
                comment=f"create partition {self._index} ({name}) on {parent_path}",
            ),
        ]
        for flag in self.flags:
            lines.append(
                ShellCommand(
                    argv=[
                        "parted", "-s", parent_path,
                        "set", str(self._index), flag, "on",
                    ],
                )
            )
        if self.uuid:
            lines.append(
                ShellCommand(
                    argv=[
                        "sgdisk",
                        f"--partition-guid={self._index}:{self.uuid}",
                        parent_path,
                    ],
                )
            )
        part_dev = partition_device(parent_path, self._index)
        lines.append(
            ShellCommand(
                argv=[
                    "partx", "-a", "-n",
                    f"{self._index}:{self._index}",
                    parent_path,
                ],
                comment=f"register partition {self._index} with the kernel",
                check=False,
            )
        )
        lines.append(
            ShellCommand(
                argv=["udevadm", "settle"],
                comment=f"wait for udev to create {part_dev}",
            )
        )
        return lines


def _compute_end_expr(begin: str, size: str) -> str:
    parsed = parse_size(size)
    if parsed == SIZE_MAX:
        return "100%"
    return f"{begin} + {parsed}B"
