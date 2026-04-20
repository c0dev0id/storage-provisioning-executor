# SPDX-License-Identifier: GPL-2.0-or-later
"""LVM nodes: physical volume, volume group, logical volume."""

from __future__ import annotations

from typing import Any, ClassVar

from storage.base import Context, Node, NodeValidationError, ShellCommand
from storage.system import SIZE_MAX, parse_size


class LvmPvNode(Node):
    TYPE: ClassVar[str] = "lvm-pv"

    def validate(self) -> None:
        if len(self.parents) != 1:
            raise NodeValidationError(
                f"lvm-pv id={self.id}: must have exactly one parent"
            )

    def device_path(self) -> str | None:
        parent = self._require_one_parent()
        return parent.device_path()

    def command_lines(self) -> list[ShellCommand]:
        dev = self._require_one_parent().device_path()
        if dev is None:
            raise NodeValidationError(
                f"lvm-pv id={self.id}: parent has no device path"
            )
        return [
            ShellCommand(
                argv=["pvcreate", "-ff", "-y", dev],
                comment=f"create PV on {dev}",
            )
        ]


class LvmVgNode(Node):
    TYPE: ClassVar[str] = "lvm-vg"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        # VG name defaults to the node id; allow explicit override.
        self.name: str = str(raw.get("name", self.id))

    def validate(self) -> None:
        if len(self.parents) < 1:
            raise NodeValidationError(
                f"lvm-vg id={self.id}: needs at least one PV parent"
            )

    def _post_execute(self) -> None:
        self.register_cleanup(self._deactivate)

    def device_path(self) -> None:
        return None

    def command_lines(self) -> list[ShellCommand]:
        pvs = [p.device_path() for p in self._resolved_parents]
        for dev in pvs:
            if dev is None:
                raise NodeValidationError(
                    f"lvm-vg id={self.id}: parent has no device path"
                )
        return [
            ShellCommand(
                argv=[
                    "vgcreate", "-f", "-y", self.name,
                    *[str(d) for d in pvs],
                ],
                comment=f"create VG {self.name}",
            )
        ]

    def _deactivate(self) -> None:
        self.ctx.sys.run(["vgchange", "-an", self.name], check=False)


class LvmLvNode(Node):
    TYPE: ClassVar[str] = "lvm-lv"

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        super().__init__(raw, ctx)
        if "name" not in raw:
            raise NodeValidationError(f"lvm-lv id={self.id}: missing 'name'")
        self.name: str = str(raw["name"])
        if "size" not in raw:
            raise NodeValidationError(f"lvm-lv id={self.id}: missing 'size'")
        self.size: str = str(raw["size"])

    def validate(self) -> None:
        if len(self.parents) != 1:
            raise NodeValidationError(
                f"lvm-lv id={self.id}: must have exactly one VG parent"
            )
        parent = self._require_one_parent()
        if parent.TYPE != "lvm-vg":
            raise NodeValidationError(
                f"lvm-lv id={self.id}: parent must be lvm-vg, got {parent.TYPE}"
            )
        parse_size(self.size)

    def device_path(self) -> str:
        vg = self._require_one_parent()
        vgname = getattr(vg, "name", vg.id)
        return f"/dev/{vgname}/{self.name}"

    def command_lines(self) -> list[ShellCommand]:
        vg = self._require_one_parent()
        vgname = getattr(vg, "name", vg.id)
        parsed = parse_size(self.size)
        if parsed == SIZE_MAX:
            size_args = ["-l", "100%FREE"]
        else:
            size_args = ["-L", f"{int(parsed)}B"]
        return [
            ShellCommand(
                argv=[
                    "lvcreate", "-y", "-W", "n",
                    *size_args, "-n", self.name, vgname,
                ],
                comment=f"create LV {vgname}/{self.name}",
            ),
            ShellCommand(
                argv=["vgmknodes", vgname],
                comment=f"create device nodes for {vgname}",
            ),
        ]
