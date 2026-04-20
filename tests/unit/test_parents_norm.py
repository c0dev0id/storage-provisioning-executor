# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for storage.base.normalize_parents and the Node base class."""

from __future__ import annotations

from typing import Any

import pytest

from storage.base import (
    Context,
    Node,
    NodeValidationError,
    normalize_parents,
)


def test_none_returns_empty_list() -> None:
    assert normalize_parents(None) == []


def test_missing_key_treated_as_none() -> None:
    assert normalize_parents(None) == []


def test_scalar_wraps_to_single_list() -> None:
    assert normalize_parents("hw-sda") == ["hw-sda"]


def test_list_of_strings_preserved() -> None:
    assert normalize_parents(["a", "b"]) == ["a", "b"]


def test_list_is_copied_not_aliased() -> None:
    src = ["a", "b"]
    out = normalize_parents(src)
    out.append("c")
    assert src == ["a", "b"]


def test_list_of_non_strings_rejected() -> None:
    with pytest.raises(NodeValidationError):
        normalize_parents(["a", 42])


@pytest.mark.parametrize("bad", [42, 1.5, True, {"x": "y"}, object()])
def test_non_string_non_list_rejected(bad: Any) -> None:
    with pytest.raises(NodeValidationError):
        normalize_parents(bad)


class _StubNode(Node):
    TYPE = "stub"

    def execute(self) -> None:
        pass


def test_node_requires_id() -> None:
    with pytest.raises(NodeValidationError, match="missing required field 'id'"):
        _StubNode({}, Context())


def test_node_normalizes_parents_on_init() -> None:
    n = _StubNode({"id": "x", "parents": "p1"}, Context())
    assert n.parents == ["p1"]


def test_node_parents_default_empty() -> None:
    n = _StubNode({"id": "x"}, Context())
    assert n.parents == []


def test_node_register_cleanup_appends() -> None:
    n = _StubNode({"id": "x"}, Context())
    calls: list[str] = []
    n.register_cleanup(lambda: calls.append("first"))
    n.register_cleanup(lambda: calls.append("second"))
    for fn in n._cleanup_actions:
        fn()
    assert calls == ["first", "second"]


def test_require_one_parent_raises_when_zero() -> None:
    n = _StubNode({"id": "x"}, Context())
    with pytest.raises(NodeValidationError, match="expected exactly one parent"):
        n._require_one_parent()


def test_require_one_parent_raises_when_multiple() -> None:
    n = _StubNode({"id": "x"}, Context())
    p1 = _StubNode({"id": "p1"}, Context())
    p2 = _StubNode({"id": "p2"}, Context())
    n._resolved_parents = [p1, p2]
    with pytest.raises(NodeValidationError, match="expected exactly one parent"):
        n._require_one_parent()


def test_require_one_parent_returns_the_parent() -> None:
    n = _StubNode({"id": "x"}, Context())
    p = _StubNode({"id": "p"}, Context())
    n._resolved_parents = [p]
    assert n._require_one_parent() is p


def test_default_device_path_is_none() -> None:
    n = _StubNode({"id": "x"}, Context())
    assert n.device_path() is None


def test_default_command_lines_empty() -> None:
    n = _StubNode({"id": "x"}, Context())
    assert n.command_lines() == []


def test_context_defaults() -> None:
    ctx = Context()
    assert ctx.variables == {}
    assert ctx.control_path == "/target"
    assert ctx.dry_run is False
    assert ctx.verbosity == 1
