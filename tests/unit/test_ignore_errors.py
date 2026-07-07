# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for per-node ignore_errors handling (base + scriptgen)."""

from __future__ import annotations

from typing import Any

import pytest

from storage.base import Context, Node, NodeValidationError, ShellCommand
from storage.scriptgen import ScriptGenerator


class _CmdNode(Node):
    TYPE = "stub"

    def command_lines(self) -> list[ShellCommand]:
        return [
            ShellCommand(argv=["true"], comment="ok"),
            ShellCommand(argv=["false"], comment="fails"),
        ]


def test_ignore_errors_default_false() -> None:
    n = _CmdNode({"id": "x"}, Context())
    assert n.ignore_errors is False


def test_ignore_errors_native_bool_true() -> None:
    n = _CmdNode({"id": "x", "ignore_errors": True}, Context())
    assert n.ignore_errors is True


def test_ignore_errors_native_bool_false() -> None:
    n = _CmdNode({"id": "x", "ignore_errors": False}, Context())
    assert n.ignore_errors is False


@pytest.mark.parametrize("value", ["yes", "true", "on", "1", "YES", "True"])
def test_ignore_errors_quoted_truthy_strings(value: str) -> None:
    n = _CmdNode({"id": "x", "ignore_errors": value}, Context())
    assert n.ignore_errors is True


@pytest.mark.parametrize("value", ["no", "false", "off", "0", "No", "FALSE"])
def test_ignore_errors_quoted_falsy_strings(value: str) -> None:
    n = _CmdNode({"id": "x", "ignore_errors": value}, Context())
    assert n.ignore_errors is False


@pytest.mark.parametrize("bad", [42, 1.5, "maybe", {"a": 1}, [1, 2]])
def test_ignore_errors_rejects_junk(bad: Any) -> None:
    with pytest.raises(NodeValidationError, match="ignore_errors"):
        _CmdNode({"id": "x", "ignore_errors": bad}, Context())


def test_effective_command_lines_passthrough_when_false() -> None:
    n = _CmdNode({"id": "x"}, Context())
    cmds = n.effective_command_lines()
    assert all(c.check is True for c in cmds)


def test_effective_command_lines_forces_check_false() -> None:
    n = _CmdNode({"id": "x", "ignore_errors": True}, Context())
    cmds = n.effective_command_lines()
    assert cmds and all(c.check is False for c in cmds)
    assert [c.argv for c in cmds] == [["true"], ["false"]]
    assert [c.comment for c in cmds] == ["ok", "fails"]


def test_effective_command_lines_does_not_mutate_command_lines() -> None:
    n = _CmdNode({"id": "x", "ignore_errors": True}, Context())
    n.effective_command_lines()
    original = n.command_lines()
    assert all(c.check is True for c in original)


def test_scriptgen_emits_or_true_when_ignore_errors_set() -> None:
    n = _CmdNode({"id": "x", "ignore_errors": True}, Context())
    out = ScriptGenerator([n]).emit()
    assert "true || true" in out
    assert "false || true" in out


def test_scriptgen_no_or_true_by_default() -> None:
    n = _CmdNode({"id": "x"}, Context())
    out = ScriptGenerator([n]).emit()
    assert "|| true" not in out
