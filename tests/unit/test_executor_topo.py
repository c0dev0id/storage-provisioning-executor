# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for Executor topological sort and reference resolution."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from storage.base import Context, Node, NodeValidationError
from storage.executor import Executor


class _Stub(Node):
    """Minimal concrete Node used to exercise Executor graph logic."""

    TYPE: ClassVar[str] = "stub"

    def execute(self) -> None:  # pragma: no cover - not called here
        pass


def _stub(node_id: str, parents: Any = None) -> _Stub:
    raw: dict[str, Any] = {"id": node_id}
    if parents is not None:
        raw["parents"] = parents
    return _Stub(raw, Context())


def test_topo_sort_single_node() -> None:
    a = _stub("a")
    ex = Executor([a])
    assert [n.id for n in ex.prepare()] == ["a"]


def test_topo_sort_linear_chain() -> None:
    a = _stub("a")
    b = _stub("b", parents="a")
    c = _stub("c", parents="b")
    ex = Executor([c, a, b])
    assert [n.id for n in ex.prepare()] == ["a", "b", "c"]


def test_topo_sort_stable_tie_break_by_source_order() -> None:
    a = _stub("a")
    b = _stub("b")
    c = _stub("c")
    ex = Executor([c, a, b])
    assert [n.id for n in ex.prepare()] == ["c", "a", "b"]


def test_topo_sort_diamond() -> None:
    a = _stub("a")
    b = _stub("b", parents="a")
    c = _stub("c", parents="a")
    d = _stub("d", parents=["b", "c"])
    ex = Executor([a, b, c, d])
    assert [n.id for n in ex.prepare()] == ["a", "b", "c", "d"]


def test_topo_sort_cycle_rejected() -> None:
    a = _stub("a", parents="b")
    b = _stub("b", parents="a")
    ex = Executor([a, b])
    with pytest.raises(NodeValidationError, match="cycle detected"):
        ex.prepare()


def test_topo_sort_self_cycle_rejected() -> None:
    a = _stub("a", parents="a")
    ex = Executor([a])
    with pytest.raises(NodeValidationError, match="cycle detected"):
        ex.prepare()


def test_unknown_parent_rejected() -> None:
    a = _stub("a", parents="missing")
    ex = Executor([a])
    with pytest.raises(NodeValidationError, match="unknown parent id"):
        ex.prepare()


def test_duplicate_ids_rejected() -> None:
    a = _stub("dup")
    b = _stub("dup")
    with pytest.raises(NodeValidationError, match="duplicate node id"):
        Executor([a, b])


def test_resolved_parents_set() -> None:
    a = _stub("a")
    b = _stub("b", parents="a")
    ex = Executor([a, b])
    ex.prepare()
    assert b._resolved_parents == [a]


def test_disconnected_components() -> None:
    a = _stub("a")
    b = _stub("b")
    c = _stub("c", parents="b")
    ex = Executor([a, b, c])
    assert [n.id for n in ex.prepare()] == ["a", "b", "c"]
