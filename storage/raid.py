# SPDX-License-Identifier: GPL-2.0-or-later
"""Raid1Node — Linux software RAID-1 via mdadm."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand


_MD_NAME_RE = re.compile(r"^md[0-9]+$")


class Raid1Node(Node):
    TYPE: ClassVar[str] = "raid1"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        if "name" not in raw:
            raise NodeValidationError(f"raid1 id={self.id}: missing 'name'")
        self.name: str = str(raw["name"])

    def validate(self) -> None:
        if len(self.parents) < 2:
            raise NodeValidationError(
                f"raid1 id={self.id}: needs at least two parents, got {len(self.parents)}"
            )
        if not _MD_NAME_RE.match(self.name):
            raise NodeValidationError(
                f"raid1 id={self.id}: name must match ^md[0-9]+$, got {self.name!r}"
            )

    def _post_execute(self) -> None:
        self.register_cleanup(self._stop)

    def device_path(self) -> str:
        return f"/dev/{self.name}"

    def command_lines(self) -> list[ShellCommand]:
        members = self._members()
        lines: list[ShellCommand] = []
        for dev in members:
            lines.append(
                ShellCommand(
                    argv=["mdadm", "--zero-superblock", "--force", dev],
                    check=False,
                    comment=f"zero mdraid superblock on {dev}",
                )
            )
        lines.append(
            ShellCommand(
                argv=[
                    "mdadm",
                    "--create",
                    "--verbose",
                    "--run",
                    "--force",
                    "--assume-clean",
                    "--metadata=1.2",
                    "--level=1",
                    f"--raid-devices={len(members)}",
                    self.device_path(),
                    *members,
                ],
                comment=f"create {self.name} from {' '.join(members)}",
            )
        )
        return lines

    def _members(self) -> list[str]:
        devs: list[str] = []
        for parent in self._resolved_parents:
            d = parent.device_path()
            if d is None:
                raise NodeValidationError(
                    f"raid1 id={self.id}: parent {parent.id!r} has no device path"
                )
            devs.append(d)
        return devs

    def _stop(self) -> None:
        self.ctx.sys.run(["mdadm", "--stop", self.device_path()], check=False)
