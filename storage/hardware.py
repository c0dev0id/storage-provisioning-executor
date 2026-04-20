# SPDX-License-Identifier: GPL-2.0-or-later
"""HardwareNode — raw block device wiping and partition-table creation."""

from __future__ import annotations

from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand
from storage.system import SIZE_MAX, parse_size


VALID_LABELS = frozenset({"gpt", "msdos"})
VALID_OVERWRITE = frozenset({"yes", "no"})


class HardwareNode(Node):
    TYPE: ClassVar[str] = "hardware"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        if self.parents:
            raise NodeValidationError(
                f"hardware id={self.id}: must not have parents"
            )
        if "path" not in raw:
            raise NodeValidationError(f"hardware id={self.id}: missing 'path'")
        self.path: str = str(raw["path"])
        self.overwrite: str = str(raw.get("overwrite", "no")).lower()
        self.erase: str | None = None if raw.get("erase") is None else str(raw["erase"])
        self.align: int = int(raw.get("align", 1))
        self.label: str | None = (
            None if raw.get("label") is None else str(raw["label"]).lower()
        )

    def validate(self) -> None:
        if self.overwrite not in VALID_OVERWRITE:
            raise NodeValidationError(
                f"hardware id={self.id}: overwrite must be yes/no, got {self.overwrite!r}"
            )
        if self.label is not None and self.label not in VALID_LABELS:
            raise NodeValidationError(
                f"hardware id={self.id}: label must be one of {sorted(VALID_LABELS)}, "
                f"got {self.label!r}"
            )
        if self.overwrite == "yes" and self.label is None:
            raise NodeValidationError(
                f"hardware id={self.id}: overwrite=yes requires a label"
            )
        if self.erase is not None and self.erase.lower() != "all":
            parse_size(self.erase)
        if self.align < 1:
            raise NodeValidationError(
                f"hardware id={self.id}: align must be >= 1, got {self.align}"
            )

    def execute(self) -> None:
        for cmd in self.command_lines():
            self.ctx.sys.run(cmd.argv, stdin=cmd.stdin, check=cmd.check)

    def device_path(self) -> str:
        return self.path

    def command_lines(self) -> list[ShellCommand]:
        lines: list[ShellCommand] = []
        if self.erase is not None:
            if self.erase.lower() == "all":
                lines.append(_dd_zero_all(self.path))
            else:
                byte_count = parse_size(self.erase)
                if byte_count == SIZE_MAX:
                    lines.append(_dd_zero_all(self.path))
                else:
                    lines.append(_dd_zero_prefix(self.path, int(byte_count)))
        if self.overwrite == "yes":
            lines.append(
                ShellCommand(
                    argv=["parted", "-s", self.path, "mklabel", str(self.label)],
                    comment=f"create {self.label} partition table on {self.path}",
                )
            )
        return lines


def _dd_zero_all(path: str) -> ShellCommand:
    return ShellCommand(
        argv=[
            "sh",
            "-c",
            f"dd if=/dev/zero of={_shq(path)} bs=1M status=none conv=fdatasync 2>/dev/null || true",
        ],
        check=False,
        comment=f"zero entire device {path}",
    )


def _dd_zero_prefix(path: str, byte_count: int) -> ShellCommand:
    mib = max(1, byte_count // (1024 * 1024))
    return ShellCommand(
        argv=[
            "dd",
            "if=/dev/zero",
            f"of={path}",
            "bs=1M",
            f"count={mib}",
            "conv=fdatasync",
            "status=none",
        ],
        comment=f"zero first {mib} MiB of {path}",
    )


def _shq(s: str) -> str:
    """Shell-single-quote for embedding in a sh -c string."""
    return "'" + s.replace("'", "'\\''") + "'"
