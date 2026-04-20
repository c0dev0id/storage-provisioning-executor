# SPDX-License-Identifier: GPL-2.0-or-later
"""CryptLuksNode — dm-crypt / LUKS2 container."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand


_MAPPER_SANITIZE = re.compile(r"[^A-Za-z0-9_.-]")


class CryptLuksNode(Node):
    TYPE: ClassVar[str] = "dm-crypt-luks"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        key = raw.get("key") or {}
        if not isinstance(key, dict):
            raise NodeValidationError(
                f"dm-crypt-luks id={self.id}: key must be a mapping"
            )
        if "passphrase" not in key:
            raise NodeValidationError(
                f"dm-crypt-luks id={self.id}: key.passphrase is required"
            )
        self.passphrase: str = str(key["passphrase"])
        self.slot: int = int(key.get("slot", 0))

    def validate(self) -> None:
        if len(self.parents) != 1:
            raise NodeValidationError(
                f"dm-crypt-luks id={self.id}: must have exactly one parent"
            )
        if not 0 <= self.slot <= 7:
            raise NodeValidationError(
                f"dm-crypt-luks id={self.id}: slot must be 0..7, got {self.slot}"
            )
        if not self.passphrase:
            raise NodeValidationError(
                f"dm-crypt-luks id={self.id}: empty passphrase"
            )

    def execute(self) -> None:
        for cmd in self.command_lines():
            self.ctx.sys.run(cmd.argv, stdin=cmd.stdin, check=cmd.check)
        self.register_cleanup(lambda: self._close())

    def device_path(self) -> str:
        return f"/dev/mapper/{self.mapper_name}"

    @property
    def mapper_name(self) -> str:
        return _MAPPER_SANITIZE.sub("_", self.id)

    def command_lines(self) -> list[ShellCommand]:
        parent_dev = self._require_one_parent().device_path()
        if parent_dev is None:
            raise NodeValidationError(
                f"dm-crypt-luks id={self.id}: parent has no device path"
            )
        passphrase = self.passphrase.encode("utf-8")
        lines: list[ShellCommand] = [
            ShellCommand(
                argv=[
                    "cryptsetup",
                    "-q",
                    "--type", "luks2",
                    "luksFormat",
                    "--key-file=-",
                    parent_dev,
                ],
                stdin=passphrase,
                comment=f"LUKS2 format {parent_dev}",
            ),
            ShellCommand(
                argv=[
                    "cryptsetup",
                    "-q",
                    "open",
                    "--type", "luks2",
                    "--key-file=-",
                    parent_dev,
                    self.mapper_name,
                ],
                stdin=passphrase,
                comment=f"open {parent_dev} as {self.mapper_name}",
            ),
        ]
        if self.slot != 0:
            lines.append(
                ShellCommand(
                    argv=[
                        "cryptsetup",
                        "-q",
                        "luksAddKey",
                        f"--key-slot={self.slot}",
                        "--key-file=-",
                        parent_dev,
                    ],
                    stdin=passphrase + b"\n" + passphrase,
                    comment=f"add passphrase to slot {self.slot}",
                )
            )
            lines.append(
                ShellCommand(
                    argv=[
                        "cryptsetup",
                        "-q",
                        "luksKillSlot",
                        "--key-file=-",
                        parent_dev,
                        "0",
                    ],
                    stdin=passphrase,
                    comment="remove default slot 0",
                )
            )
        return lines

    def _close(self) -> None:
        self.ctx.sys.run(
            ["cryptsetup", "-q", "close", self.mapper_name], check=False
        )
