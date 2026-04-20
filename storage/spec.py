# SPDX-License-Identifier: GPL-2.0-or-later
"""YAML specification loader: parse, expand {{vars}}, build Node objects."""

from __future__ import annotations

from typing import Any, Type

import yaml

from storage.base import Context, Node, NodeValidationError
from storage.crypt import CryptLuksNode
from storage.filesystem import FilesystemNode
from storage.hardware import HardwareNode
from storage.lvm import LvmLvNode, LvmPvNode, LvmVgNode
from storage.partition import PartitionNode
from storage.raid import Raid1Node
from storage.system import expand_vars_in_tree


TYPE_REGISTRY: dict[str, Type[Node]] = {
    "hardware": HardwareNode,
    "partition": PartitionNode,
    "raid1": Raid1Node,
    "dm-crypt-luks": CryptLuksNode,
    "lvm-pv": LvmPvNode,
    "lvm-vg": LvmVgNode,
    "lvm-lv": LvmLvNode,
    "filesystem": FilesystemNode,
}


def load_spec(yaml_text: str, *, ctx_overrides: dict[str, Any] | None = None) -> tuple[Context, list[Node]]:
    """Parse YAML spec, expand variables, extract control, instantiate nodes.

    Returns (context, nodes). The caller passes `nodes` to `Executor`.
    `ctx_overrides` lets the CLI override dry_run / verbosity / sys without
    re-parsing.
    """
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise NodeValidationError(
            f"spec root must be a mapping, got {type(data).__name__}"
        )
    variables_raw = data.get("vars") or {}
    if not isinstance(variables_raw, dict):
        raise NodeValidationError("spec: 'vars' must be a mapping")
    variables = {str(k): str(v) for k, v in variables_raw.items()}

    storage = data.get("storage")
    if not isinstance(storage, list):
        raise NodeValidationError("spec: 'storage' must be a list")

    expanded = expand_vars_in_tree(storage, variables)

    control_entries = [
        e for e in expanded if isinstance(e, dict) and e.get("type") == "control"
    ]
    other = [
        e for e in expanded
        if not (isinstance(e, dict) and e.get("type") == "control")
    ]
    if len(control_entries) != 1:
        raise NodeValidationError(
            f"spec: expected exactly one control entry, got {len(control_entries)}"
        )
    control = control_entries[0]

    ctx = Context(
        variables=variables,
        control_path=str(control.get("path", "/target")),
    )
    if ctx_overrides:
        for key, value in ctx_overrides.items():
            setattr(ctx, key, value)

    nodes: list[Node] = []
    for entry in other:
        if not isinstance(entry, dict):
            raise NodeValidationError(
                f"spec: storage entries must be mappings, got {entry!r}"
            )
        type_name = entry.get("type")
        if type_name is None:
            raise NodeValidationError(f"spec: missing 'type' in entry {entry!r}")
        if type_name not in TYPE_REGISTRY:
            raise NodeValidationError(f"spec: unknown node type {type_name!r}")
        cls = TYPE_REGISTRY[type_name]
        nodes.append(cls(entry, ctx))
    return ctx, nodes
