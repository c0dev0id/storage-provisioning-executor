# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for CommandNode and DebugNode."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.command import CommandNode, DebugNode
from storage.executor import Executor
from storage.hardware import HardwareNode
from storage.scriptgen import ScriptGenerator


# ------------------------------------------------------------- CommandNode --

def test_command_node_argv_produces_shell_command() -> None:
    node = CommandNode(
        {"id": "settle", "argv": ["udevadm", "settle"]},
        Context(),
    )
    cmds = node.command_lines()
    assert len(cmds) == 1
    assert cmds[0].argv == ["udevadm", "settle"]


def test_command_node_argv_missing_rejected() -> None:
    with pytest.raises(NodeValidationError, match="non-empty list"):
        CommandNode({"id": "x"}, Context())


def test_command_node_argv_empty_rejected() -> None:
    with pytest.raises(NodeValidationError, match="non-empty list"):
        CommandNode({"id": "x", "argv": []}, Context())


def test_command_node_argv_wrong_type_rejected() -> None:
    with pytest.raises(NodeValidationError, match="non-empty list"):
        CommandNode({"id": "x", "argv": "udevadm settle"}, Context())


def test_command_node_argv_non_string_entry_rejected() -> None:
    with pytest.raises(NodeValidationError, match=r"argv\[1\]"):
        CommandNode({"id": "x", "argv": ["udevadm", 42]}, Context())


def test_command_node_optional_comment() -> None:
    node = CommandNode(
        {"id": "x", "argv": ["true"], "comment": "sanity check"},
        Context(),
    )
    assert node.command_lines()[0].comment == "sanity check"


def test_command_node_no_device_path() -> None:
    node = CommandNode({"id": "x", "argv": ["true"]}, Context())
    assert node.device_path() is None


def test_command_node_respects_ignore_errors() -> None:
    node = CommandNode(
        {"id": "x", "argv": ["false"], "ignore_errors": True},
        Context(),
    )
    assert node.effective_command_lines()[0].check is False


# --------------------------------------------------------------- DebugNode --

def test_debug_node_emits_echo() -> None:
    node = DebugNode({"id": "msg", "message": "hello"}, Context())
    cmds = node.command_lines()
    assert cmds[0].argv == ["echo", "hello"]


def test_debug_node_message_required() -> None:
    with pytest.raises(NodeValidationError, match="non-empty string"):
        DebugNode({"id": "x"}, Context())


def test_debug_node_message_empty_rejected() -> None:
    with pytest.raises(NodeValidationError, match="non-empty string"):
        DebugNode({"id": "x", "message": ""}, Context())


def test_debug_node_message_wrong_type_rejected() -> None:
    with pytest.raises(NodeValidationError, match="non-empty string"):
        DebugNode({"id": "x", "message": ["a", "b"]}, Context())


def test_debug_node_comment_labels_id() -> None:
    node = DebugNode({"id": "greeting", "message": "hi"}, Context())
    assert node.command_lines()[0].comment == "debug: greeting"


# --------------------------------------------------------------- ordering --

def test_command_node_as_fence_between_nodes_via_parents() -> None:
    ctx = Context()
    hw = HardwareNode(
        {"id": "hw", "path": "/dev/sda", "overwrite": "yes", "label": "gpt"},
        ctx,
    )
    fence = CommandNode(
        {"id": "fence", "parents": "hw", "argv": ["udevadm", "settle"]},
        ctx,
    )
    ordered = Executor([fence, hw]).prepare()
    assert [n.id for n in ordered] == ["hw", "fence"]


def test_scriptgen_emits_command_section() -> None:
    ctx = Context()
    node = CommandNode(
        {"id": "settle", "argv": ["udevadm", "settle"]}, ctx,
    )
    out = ScriptGenerator([node]).emit()
    assert "# === settle (command) ===" in out
    assert "udevadm settle" in out


def test_scriptgen_emits_debug_section_with_echo() -> None:
    ctx = Context()
    node = DebugNode({"id": "greet", "message": "hello world"}, ctx)
    out = ScriptGenerator([node]).emit()
    assert "# === greet (debug) ===" in out
    assert "echo 'hello world'" in out


def test_debug_node_respects_ignore_errors_in_scriptgen() -> None:
    ctx = Context()
    node = DebugNode(
        {"id": "x", "message": "y", "ignore_errors": True}, ctx,
    )
    out = ScriptGenerator([node]).emit()
    assert "echo y || true" in out
