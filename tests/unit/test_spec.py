# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for YAML spec loader: variable expansion, control extraction, typing."""

from __future__ import annotations

import pytest

from storage.base import NodeValidationError
from storage.filesystem import FilesystemNode
from storage.hardware import HardwareNode
from storage.spec import TYPE_REGISTRY, load_spec


def test_loads_minimal_spec() -> None:
    text = """
vars:
  h: foo
storage:
  - {type: control, path: /t}
  - {type: hardware, id: hw, path: /dev/sda}
"""
    ctx, nodes = load_spec(text)
    assert ctx.control_path == "/t"
    assert len(nodes) == 1
    assert isinstance(nodes[0], HardwareNode)


def test_expands_template_vars_in_labels() -> None:
    text = """
vars:
  hostname: foo
storage:
  - {type: control, path: /t}
  - {type: hardware, id: hw, path: /dev/sda}
  - type: filesystem
    id: fs
    parents: hw
    fstype: ext4
    mountpoint: /
    label: "{{hostname}}-root"
"""
    _ctx, nodes = load_spec(text)
    fs = [n for n in nodes if isinstance(n, FilesystemNode)][0]
    assert fs.label == "foo-root"


def test_missing_control_rejected() -> None:
    text = """
storage:
  - {type: hardware, id: hw, path: /dev/sda}
"""
    with pytest.raises(NodeValidationError, match="exactly one control"):
        load_spec(text)


def test_multiple_controls_rejected() -> None:
    text = """
storage:
  - {type: control, path: /a}
  - {type: control, path: /b}
  - {type: hardware, id: hw, path: /dev/sda}
"""
    with pytest.raises(NodeValidationError, match="exactly one control"):
        load_spec(text)


def test_unknown_type_rejected() -> None:
    text = """
storage:
  - {type: control, path: /t}
  - {type: bogus, id: x}
"""
    with pytest.raises(NodeValidationError, match="unknown node type"):
        load_spec(text)


def test_missing_type_rejected() -> None:
    text = """
storage:
  - {type: control, path: /t}
  - {id: x}
"""
    with pytest.raises(NodeValidationError, match="missing 'type'"):
        load_spec(text)


def test_storage_must_be_list() -> None:
    text = "storage: not-a-list"
    with pytest.raises(NodeValidationError, match="'storage' must be a list"):
        load_spec(text)


def test_root_must_be_mapping() -> None:
    with pytest.raises(NodeValidationError, match="root must be a mapping"):
        load_spec("- just a list")


def test_type_registry_contains_all_node_types() -> None:
    expected = {
        "hardware", "partition", "raid1", "dm-crypt-luks",
        "lvm-pv", "lvm-vg", "lvm-lv", "filesystem", "swap",
    }
    assert set(TYPE_REGISTRY) == expected


def test_ctx_overrides_applied() -> None:
    text = """
storage:
  - {type: control, path: /t}
  - {type: hardware, id: hw, path: /dev/sda}
"""
    ctx, _nodes = load_spec(text, ctx_overrides={"dry_run": True, "verbosity": 3})
    assert ctx.dry_run is True
    assert ctx.verbosity == 3
