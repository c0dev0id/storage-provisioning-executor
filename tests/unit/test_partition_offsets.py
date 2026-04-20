# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for Executor partition index + MiB-offset assignment."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.executor import Executor
from storage.hardware import HardwareNode
from storage.partition import PartitionNode


def _hw(node_id: str = "sda", path: str = "/dev/sda") -> HardwareNode:
    return HardwareNode({"id": node_id, "path": path}, Context())


def _part(node_id: str, size: str, begin: str | None = None) -> PartitionNode:
    raw = {"id": node_id, "parents": "sda", "size": size}
    if begin is not None:
        raw["begin"] = begin
    return PartitionNode(raw, Context())


def test_indices_assigned_in_source_order() -> None:
    hw = _hw()
    p1 = _part("p1", "512MiB")
    p2 = _part("p2", "1GiB")
    p3 = _part("p3", "{max}")
    Executor([hw, p1, p2, p3]).prepare()
    assert (p1._index, p2._index, p3._index) == (1, 2, 3)


def test_first_partition_begin_defaults_to_1MiB() -> None:
    hw = _hw()
    p = _part("p", "512MiB")
    Executor([hw, p]).prepare()
    assert p._begin_expr == "1MiB"


def test_chained_begin_end_mib() -> None:
    hw = _hw()
    p1 = _part("p1", "512MiB")
    p2 = _part("p2", "1GiB")
    Executor([hw, p1, p2]).prepare()
    assert p1._begin_expr == "1MiB"
    assert p1._end_expr == "513MiB"
    assert p2._begin_expr == "513MiB"
    assert p2._end_expr == "1537MiB"


def test_max_size_yields_100_percent() -> None:
    hw = _hw()
    p = _part("p", "{max}")
    Executor([hw, p]).prepare()
    assert p._end_expr == "100%"


def test_max_cannot_be_followed_by_implicit_begin() -> None:
    hw = _hw()
    p1 = _part("p1", "{max}")
    p2 = _part("p2", "1MiB")
    with pytest.raises(NodeValidationError, match="implicit begin requires"):
        Executor([hw, p1, p2]).prepare()


def test_explicit_begin_overrides_cursor() -> None:
    hw = _hw()
    p1 = _part("p1", "512MiB")
    p2 = _part("p2", "1GiB", begin="2000MiB")
    Executor([hw, p1, p2]).prepare()
    assert p2._begin_expr == "2000MiB"
    assert p2._end_expr == "3024MiB"


def test_explicit_non_mib_begin_breaks_chain() -> None:
    hw = _hw()
    p1 = _part("p1", "512MiB", begin="999B")
    p2 = _part("p2", "1GiB")
    with pytest.raises(NodeValidationError, match="implicit begin requires"):
        Executor([hw, p1, p2]).prepare()


def test_sector_begin_chains_when_mib_aligned() -> None:
    # 2048 sectors = 1 MiB exactly, so the cursor is preserved.
    hw = _hw()
    p1 = _part("p1", "4GiB", begin="2048s")
    p2 = _part("p2", "4GiB")
    Executor([hw, p1, p2]).prepare()
    assert p1._begin_expr == "2048s"
    assert p1._end_expr == "4097MiB"
    assert p2._begin_expr == "4097MiB"


def test_per_parent_numbering_is_independent() -> None:
    hwa = HardwareNode({"id": "sda", "path": "/dev/sda"}, Context())
    hwb = HardwareNode({"id": "sdb", "path": "/dev/sdb"}, Context())
    a1 = PartitionNode({"id": "a1", "parents": "sda", "size": "1GiB"}, Context())
    a2 = PartitionNode({"id": "a2", "parents": "sda", "size": "1GiB"}, Context())
    b1 = PartitionNode({"id": "b1", "parents": "sdb", "size": "1GiB"}, Context())
    Executor([hwa, hwb, a1, a2, b1]).prepare()
    assert (a1._index, a2._index, b1._index) == (1, 2, 1)


def test_command_lines_use_computed_mib_offsets() -> None:
    hw = _hw()
    p1 = _part("p1", "512MiB")
    p2 = _part("p2", "1GiB")
    Executor([hw, p1, p2]).prepare()
    lines1 = p1.command_lines()
    lines2 = p2.command_lines()
    assert lines1[0].argv[-2:] == ["1MiB", "513MiB"]
    assert lines2[0].argv[-2:] == ["513MiB", "1537MiB"]


def test_size_rounds_up_to_next_mib() -> None:
    hw = _hw()
    p = _part("p", "1536B")  # less than 1 MiB, rounds to 1
    Executor([hw, p]).prepare()
    assert p._end_expr == "2MiB"
