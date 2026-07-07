# SPDX-License-Identifier: GPL-2.0-or-later
# pylint: disable=protected-access
"""Executor — DAG build, topological sort, execute, reverse cleanup."""

from __future__ import annotations

import heapq
import logging
import posixpath
from typing import Iterable

from storage.base import Node, NodeExecutionError, NodeValidationError
from storage.filesystem import FilesystemNode
from storage.partition import PartitionNode
from storage.system import SIZE_MAX, parse_size


_logger = logging.getLogger("sprov")


class Executor:
    """Build the DAG, resolve refs, topo-sort, execute with reverse cleanup."""

    def __init__(self, nodes: Iterable[Node]) -> None:
        self.nodes: list[Node] = list(nodes)
        self._by_id: dict[str, Node] = {}
        for node in self.nodes:
            if node.id in self._by_id:
                raise NodeValidationError(f"duplicate node id: {node.id!r}")
            self._by_id[node.id] = node
        self._succeeded: list[Node] = []

    # ------------------------------------------------------------
    # Preparation (pure logic — no side effects).
    # ------------------------------------------------------------

    def prepare(self) -> list[Node]:
        """Return nodes in execution order; resolves refs and validates."""
        self._resolve_parents()
        self._assign_partition_indices()
        ordered = self._topo_sort()
        ordered = self._reorder_mounts(ordered)
        for node in ordered:
            node.validate()
        return ordered

    def _resolve_parents(self) -> None:
        for node in self.nodes:
            resolved: list[Node] = []
            for pid in node.parents:
                if pid not in self._by_id:
                    raise NodeValidationError(
                        f"node id={node.id!r}: unknown parent id {pid!r}"
                    )
                resolved.append(self._by_id[pid])
            node._resolved_parents = resolved

    def _assign_partition_indices(self) -> None:
        """Number partitions per parent (YAML source order) and compute offsets.

        Computes absolute MiB offsets for chained partitions when sizes are
        concrete. An explicit `begin` overrides the running cursor; `size: {max}`
        consumes the remainder and terminates the chain.
        """
        per_parent: dict[str, list[PartitionNode]] = {}
        for node in self.nodes:
            if isinstance(node, PartitionNode) and len(node.parents) == 1:
                per_parent.setdefault(node.parents[0], []).append(node)
        for parts in per_parent.values():
            cursor_mib: int | None = 1
            for i, part in enumerate(parts, start=1):
                part._index = i
                if part.begin is not None:
                    begin_expr = part.begin
                    cursor_mib = _try_parse_mib(part.begin)
                elif cursor_mib is None:
                    raise NodeValidationError(
                        f"partition id={part.id}: implicit begin requires the "
                        "previous partition to end on a MiB boundary"
                    )
                else:
                    begin_expr = f"{cursor_mib}MiB"
                part._begin_expr = begin_expr

                parsed = parse_size(part.size)
                if parsed == SIZE_MAX:
                    part._end_expr = "100%"
                    cursor_mib = None
                elif cursor_mib is not None:
                    size_mib = _bytes_to_mib_ceil(int(parsed))
                    cursor_mib += size_mib
                    part._end_expr = f"{cursor_mib}MiB"
                else:
                    part._end_expr = f"{begin_expr} + {int(parsed)}B"

    def _topo_sort(self) -> list[Node]:
        """Kahn's algorithm with a min-heap keyed by source-order index."""
        indeg: dict[str, int] = {n.id: len(n.parents) for n in self.nodes}
        order: dict[str, int] = {n.id: i for i, n in enumerate(self.nodes)}
        children: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for node in self.nodes:
            for pid in node.parents:
                if pid not in children:
                    continue
                children[pid].append(node.id)

        heap: list[tuple[int, str]] = []
        for nid, deg in indeg.items():
            if deg == 0:
                heapq.heappush(heap, (order[nid], nid))

        result: list[Node] = []
        while heap:
            _, current_id = heapq.heappop(heap)
            result.append(self._by_id[current_id])
            for cid in children[current_id]:
                indeg[cid] -= 1
                if indeg[cid] == 0:
                    heapq.heappush(heap, (order[cid], cid))

        if len(result) != len(self.nodes):
            seen = {n.id for n in result}
            remaining = [n.id for n in self.nodes if n.id not in seen]
            raise NodeValidationError(f"cycle detected among nodes: {remaining}")
        return result

    def _reorder_mounts(self, ordered: list[Node]) -> list[Node]:
        """Stable-sort FilesystemNodes so shorter mountpoints mount first.

        Mount ops produce no device path, so pulling them to the tail of the
        execution order preserves every data dependency.
        """
        non_mounts = [n for n in ordered if not isinstance(n, FilesystemNode)]
        mounts = [n for n in ordered if isinstance(n, FilesystemNode)]
        mounts.sort(key=lambda fs: _mount_depth(fs.mountpoint))
        return non_mounts + mounts

    # ------------------------------------------------------------
    # Execution.
    # ------------------------------------------------------------

    def run(self) -> None:
        """Execute nodes in order; on failure, reverse-cleanup succeeded nodes."""
        ordered = self.prepare()
        self._succeeded = []
        current: Node | None = None
        try:
            for node in ordered:
                current = node
                node.execute()
                self._succeeded.append(node)
        except Exception as exc:
            cid = current.id if current is not None else "?"
            _logger.error("execution failed at node %r: %s", cid, exc)
            self._cleanup()
            raise NodeExecutionError(f"node {cid!r}: {exc}") from exc

        try:
            for node in ordered:
                current = node
                node.verify()
        except Exception as exc:
            cid = current.id if current is not None else "?"
            _logger.error("post-run verification failed at node %r: %s", cid, exc)
            self._cleanup()
            raise NodeExecutionError(
                f"verification failed for node {cid!r}: {exc}"
            ) from exc

    def _cleanup(self) -> None:
        """Invoke cleanup closures of succeeded nodes in reverse order."""
        for node in reversed(self._succeeded):
            for fn in reversed(node._cleanup_actions):
                try:
                    fn()
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    _logger.warning(
                        "cleanup action for node %r raised: %s", node.id, exc
                    )


# ----------------------------------------------------------------
# Helpers.
# ----------------------------------------------------------------


def _mount_depth(mountpoint: str) -> int:
    normalized = posixpath.normpath(mountpoint)
    if normalized == "/":
        return 0
    return normalized.count("/")


def _try_parse_mib(expr: str) -> int | None:
    """Return MiB count for expr if it parses to a whole number of MiB."""
    try:
        parsed = parse_size(expr)
    except ValueError:
        return None
    if parsed == SIZE_MAX:
        return None
    mib = 1024 * 1024
    byte_val = int(parsed)
    if byte_val % mib == 0:
        return byte_val // mib
    return None


def _bytes_to_mib_ceil(byte_count: int) -> int:
    mib = 1024 * 1024
    return (byte_count + mib - 1) // mib
