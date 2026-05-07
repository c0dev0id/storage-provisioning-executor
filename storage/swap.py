# SPDX-License-Identifier: GPL-2.0-or-later
"""SwapNode — mkswap + swapon a block device."""

from __future__ import annotations

from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand


class SwapNode(Node):
    TYPE: ClassVar[str] = "swap"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        self.label: str | None = (
            None if raw.get("label") is None else str(raw["label"])
        )
        self.mkswap_options: list[str] = [
            str(x) for x in (raw.get("mkswap_options") or [])
        ]

    def validate(self) -> None:
        if len(self.parents) != 1:
            raise NodeValidationError(
                f"swap id={self.id}: must have exactly one parent"
            )
        dev = self._require_one_parent().device_path()
        if dev is None:
            raise NodeValidationError(
                f"swap id={self.id}: parent has no device path"
            )

    def device_path(self) -> None:
        return None

    def _post_execute(self) -> None:
        dev = self._require_one_parent().device_path()
        self.register_cleanup(lambda: self.ctx.sys.run(["swapoff", dev], check=False))

    def command_lines(self) -> list[ShellCommand]:
        dev = self._require_one_parent().device_path()
        if dev is None:
            raise NodeValidationError(
                f"swap id={self.id}: parent has no device path"
            )
        mkswap_argv: list[str] = ["mkswap"]
        if self.label is not None:
            mkswap_argv.extend(["-L", self.label])
        mkswap_argv.extend(self.mkswap_options)
        mkswap_argv.append(dev)
        return [
            ShellCommand(argv=mkswap_argv, comment=f"create swap on {dev}"),
            ShellCommand(argv=["swapon", dev], comment=f"enable swap on {dev}"),
        ]
