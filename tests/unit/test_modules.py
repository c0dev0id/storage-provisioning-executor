# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for kernel-module loading: top-level, per-node, aggregation, emit."""

from __future__ import annotations

import pytest

from storage.base import (
    Context,
    NodeValidationError,
    collect_modprobe_commands,
    normalize_modules,
)
from storage.hardware import HardwareNode
from storage.scriptgen import ScriptGenerator
from storage.spec import load_spec


# ---------------------------------------------------------------- normalize --

def test_normalize_modules_accepts_none() -> None:
    assert normalize_modules(None, where="x") == []


def test_normalize_modules_accepts_string_scalar() -> None:
    assert normalize_modules("dm_crypt", where="x") == ["dm_crypt"]


def test_normalize_modules_accepts_list() -> None:
    assert normalize_modules(["dm_mod", "raid1"], where="x") == ["dm_mod", "raid1"]


def test_normalize_modules_rejects_non_string_entry() -> None:
    with pytest.raises(NodeValidationError, match="must be strings"):
        normalize_modules(["dm_mod", 42], where="x")


def test_normalize_modules_rejects_wrong_type() -> None:
    with pytest.raises(NodeValidationError, match="must be string or list"):
        normalize_modules({"a": "b"}, where="x")


def test_normalize_modules_rejects_empty_string() -> None:
    with pytest.raises(NodeValidationError, match="empty"):
        normalize_modules(["dm_mod", "   "], where="x")


# ---------------------------------------------------------------- spec load --

def test_control_modules_lifted_into_context() -> None:
    text = """
storage:
  - {type: control, path: /t, modules: [dm_mod, raid1]}
  - {type: hardware, id: hw, path: /dev/sda}
"""
    ctx, _nodes = load_spec(text)
    assert ctx.modules == ["dm_mod", "raid1"]


def test_control_modules_default_empty() -> None:
    text = """
storage:
  - {type: control, path: /t}
  - {type: hardware, id: hw, path: /dev/sda}
"""
    ctx, _nodes = load_spec(text)
    assert ctx.modules == []


def test_per_node_modules_parsed() -> None:
    text = """
storage:
  - {type: control, path: /t}
  - {type: hardware, id: hw, path: /dev/sda, modules: dm_crypt}
"""
    _ctx, nodes = load_spec(text)
    assert nodes[0].modules == ["dm_crypt"]


# ---------------------------------------------------------------- aggregate --

def test_collect_dedupes_preserving_first_appearance() -> None:
    ctx = Context(modules=["dm_mod", "raid1"])
    hw1 = HardwareNode({"id": "hw1", "path": "/dev/sda", "modules": ["raid1", "xfs"]}, ctx)
    hw2 = HardwareNode({"id": "hw2", "path": "/dev/sdb", "modules": ["dm_mod", "ext4"]}, ctx)
    cmds = collect_modprobe_commands(ctx, [hw1, hw2])
    assert [c.argv for c in cmds] == [
        ["modprobe", "dm_mod"],
        ["modprobe", "raid1"],
        ["modprobe", "xfs"],
        ["modprobe", "ext4"],
    ]


def test_collect_returns_empty_when_no_modules() -> None:
    ctx = Context()
    hw = HardwareNode({"id": "hw", "path": "/dev/sda"}, ctx)
    assert collect_modprobe_commands(ctx, [hw]) == []


def test_collect_uses_ctx_only_when_nodes_have_none() -> None:
    ctx = Context(modules=["dm_mod"])
    hw = HardwareNode({"id": "hw", "path": "/dev/sda"}, ctx)
    cmds = collect_modprobe_commands(ctx, [hw])
    assert [c.argv for c in cmds] == [["modprobe", "dm_mod"]]


# ---------------------------------------------------------------- scriptgen --

def test_scriptgen_emits_modules_section_at_top() -> None:
    ctx = Context(modules=["dm_mod"])
    hw = HardwareNode(
        {
            "id": "hw", "path": "/dev/sda",
            "overwrite": "yes", "label": "gpt",
            "modules": ["raid1"],
        },
        ctx,
    )
    out = ScriptGenerator([hw]).emit()
    assert "# === modules ===" in out
    modules_idx = out.index("# === modules ===")
    node_idx = out.index("# === hw (hardware) ===")
    assert modules_idx < node_idx
    assert "modprobe dm_mod" in out
    assert "modprobe raid1" in out
    assert out.index("modprobe dm_mod") < out.index("modprobe raid1")


def test_scriptgen_omits_modules_section_when_none_declared() -> None:
    ctx = Context()
    hw = HardwareNode({"id": "hw", "path": "/dev/sda"}, ctx)
    out = ScriptGenerator([hw]).emit()
    assert "# === modules ===" not in out


def test_scriptgen_empty_nodes_emits_no_modules_section() -> None:
    out = ScriptGenerator([]).emit()
    assert "# === modules ===" not in out


# ---------------------------------------------------------------- executor --

def test_executor_runs_modprobe_before_first_node() -> None:
    from storage.executor import Executor
    from storage.system import SystemCommand

    calls: list[list[str]] = []

    class _RecordingSys(SystemCommand):
        def run(self, argv, **_kwargs):  # type: ignore[no-untyped-def]
            calls.append(list(argv))
            from storage.system import CommandResult
            return CommandResult(cmd=list(argv), rc=0)

    ctx = Context(modules=["dm_mod", "raid1"], sys=_RecordingSys())
    hw = HardwareNode(
        {
            "id": "hw", "path": "/dev/sda",
            "overwrite": "yes", "label": "gpt",
            "modules": ["xfs"],
        },
        ctx,
    )
    Executor([hw]).run()
    modprobe_calls = [c for c in calls if c[0] == "modprobe"]
    assert modprobe_calls == [
        ["modprobe", "dm_mod"],
        ["modprobe", "raid1"],
        ["modprobe", "xfs"],
    ]
    first_non_modprobe = next(i for i, c in enumerate(calls) if c[0] != "modprobe")
    last_modprobe = max(i for i, c in enumerate(calls) if c[0] == "modprobe")
    assert last_modprobe < first_non_modprobe
