# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for Executor execution loop and reverse-order cleanup."""

from __future__ import annotations

from typing import Any, Callable, ClassVar

import pytest

from storage.base import Context, Node, NodeExecutionError


class _Recorder(Node):
    """Node that records its execute/cleanup calls on a shared list."""

    TYPE: ClassVar[str] = "recorder"

    def __init__(
        self,
        raw: dict[str, Any],
        ctx: Context,
        *,
        log: list[str],
        cleanups: list[str] | None = None,
        raise_on_execute: bool = False,
    ) -> None:
        super().__init__(raw, ctx)
        self._log = log
        self._cleanups = cleanups or []
        self._raise = raise_on_execute

    def execute(self) -> None:
        self._log.append(f"exec:{self.id}")
        for tag in self._cleanups:
            self.register_cleanup(self._make_cleanup(tag))
        if self._raise:
            raise RuntimeError(f"boom in {self.id}")

    def _make_cleanup(self, tag: str) -> Callable[[], None]:
        def _fn() -> None:
            self._log.append(f"cleanup:{self.id}:{tag}")
        return _fn


def _rec(
    node_id: str,
    log: list[str],
    parents: Any = None,
    cleanups: list[str] | None = None,
    raise_on_execute: bool = False,
) -> _Recorder:
    raw: dict[str, Any] = {"id": node_id}
    if parents is not None:
        raw["parents"] = parents
    return _Recorder(
        raw,
        Context(),
        log=log,
        cleanups=cleanups,
        raise_on_execute=raise_on_execute,
    )


def test_run_executes_in_topo_order() -> None:
    from storage.executor import Executor

    log: list[str] = []
    a = _rec("a", log)
    b = _rec("b", log, parents="a")
    c = _rec("c", log, parents="b")
    Executor([c, a, b]).run()
    assert log == ["exec:a", "exec:b", "exec:c"]


def test_mid_run_failure_triggers_reverse_cleanup() -> None:
    from storage.executor import Executor

    log: list[str] = []
    a = _rec("a", log, cleanups=["a1", "a2"])
    b = _rec("b", log, parents="a", cleanups=["b1"])
    c = _rec("c", log, parents="b", raise_on_execute=True)
    with pytest.raises(NodeExecutionError, match="'c'"):
        Executor([a, b, c]).run()
    # c raised before registering any cleanup; a and b clean up in reverse.
    assert log == [
        "exec:a",
        "exec:b",
        "exec:c",
        "cleanup:b:b1",
        "cleanup:a:a2",
        "cleanup:a:a1",
    ]


def test_cleanup_failures_are_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from storage.executor import Executor

    log: list[str] = []

    class _BadCleanup(_Recorder):
        def execute(self) -> None:
            log.append(f"exec:{self.id}")
            self.register_cleanup(self._raise_fn)
            if self._raise:
                raise RuntimeError("trigger")

        def _raise_fn(self) -> None:
            raise RuntimeError("cleanup fail")

    a = _BadCleanup({"id": "a"}, Context(), log=log)
    b = _BadCleanup({"id": "b", "parents": "a"}, Context(), log=log, raise_on_execute=True)
    caplog.set_level(logging.WARNING, logger="sprov")
    with pytest.raises(NodeExecutionError):
        Executor([a, b]).run()
    assert "cleanup fail" in caplog.text


def test_run_no_failure_no_cleanup_invoked() -> None:
    from storage.executor import Executor

    log: list[str] = []
    a = _rec("a", log, cleanups=["a1"])
    b = _rec("b", log, parents="a", cleanups=["b1"])
    Executor([a, b]).run()
    assert log == ["exec:a", "exec:b"]


def test_succeeded_list_tracks_completed_nodes() -> None:
    from storage.executor import Executor

    log: list[str] = []
    a = _rec("a", log)
    b = _rec("b", log, parents="a", raise_on_execute=True)
    c = _rec("c", log, parents="b")
    ex = Executor([a, b, c])
    with pytest.raises(NodeExecutionError):
        ex.run()
    assert [n.id for n in ex._succeeded] == ["a"]
