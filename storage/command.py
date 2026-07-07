# SPDX-License-Identifier: GPL-2.0-or-later
"""CommandNode and DebugNode — arbitrary commands and human-readable notes."""

from __future__ import annotations

from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand


class CommandNode(Node):
    """Run an arbitrary argv at a chosen fence point in the DAG.

    Produces no device path. Ordering is expressed the same way as every
    other node: via `parents`. A `command` node with no parents runs first;
    one downstream of the last filesystem mount runs last.
    """

    TYPE: ClassVar[str] = "command"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        raw_argv = raw.get("argv")
        if not isinstance(raw_argv, list) or not raw_argv:
            raise NodeValidationError(
                f"command id={self.id}: 'argv' must be a non-empty list"
            )
        argv: list[str] = []
        for i, item in enumerate(raw_argv):
            if not isinstance(item, str):
                raise NodeValidationError(
                    f"command id={self.id}: argv[{i}] must be a string, "
                    f"got {type(item).__name__}: {item!r}"
                )
            argv.append(item)
        self.argv: list[str] = argv
        self.comment: str | None = (
            None if raw.get("comment") is None else str(raw["comment"])
        )

    def command_lines(self) -> list[ShellCommand]:
        return [ShellCommand(argv=list(self.argv), comment=self.comment)]


class DebugNode(Node):
    """Emit a human-readable message at a chosen fence point.

    Sugar over a `command` node running `echo <message>`. Kept as a distinct
    type because "print a message" reads clearer in the spec than spelling
    out `argv: [echo, ...]` at every debug point.
    """

    TYPE: ClassVar[str] = "debug"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        msg = raw.get("message")
        if not isinstance(msg, str) or not msg:
            raise NodeValidationError(
                f"debug id={self.id}: 'message' must be a non-empty string"
            )
        self.message: str = msg

    def command_lines(self) -> list[ShellCommand]:
        return [ShellCommand(
            argv=["echo", self.message],
            comment=f"debug: {self.id}",
        )]
