# SPDX-License-Identifier: GPL-2.0-or-later
"""Node base class, Context, exceptions, and parents normalization."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar

from storage.system import SystemCommand


@dataclass
class ShellCommand:
    """Canonical representation of a single shell operation.

    Both the live executor and the script generator consume this type, so
    generated shell scripts match what the Python path runs. `stdin` bytes
    are fed on stdin (never passed on the command line) to keep secrets
    out of /proc/<pid>/cmdline. `comment` is an optional note the script
    generator emits as a leading comment line.
    """

    argv: list[str]
    stdin: bytes | None = None
    comment: str | None = None
    check: bool = True


class NodeValidationError(ValueError):
    """Raised when a node's YAML fields are invalid."""


class NodeExecutionError(RuntimeError):
    """Raised when a node fails to execute."""


_TRUE_STRINGS = frozenset({"yes", "true", "on", "1"})
_FALSE_STRINGS = frozenset({"no", "false", "off", "0"})


def _as_bool(value: Any, *, field_name: str) -> bool:
    """Accept YAML native bool or the quoted string variants.

    YAML 1.1's `yes`/`no`/`on`/`off` parse as bool when unquoted; the string
    forms only appear when the user quoted them. Anything else is an error.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in _TRUE_STRINGS:
            return True
        if s in _FALSE_STRINGS:
            return False
    raise NodeValidationError(
        f"{field_name} must be a boolean, got {value!r}"
    )


@dataclass
class Context:
    """Runtime context shared across all nodes in a provisioning run."""

    variables: dict[str, str] = field(default_factory=dict)
    control_path: str = "/target"
    dry_run: bool = False
    verbosity: int = 1
    sys: SystemCommand = field(default_factory=SystemCommand)


def normalize_parents(raw: Any) -> list[str]:
    """Normalize a `parents:` field to a list of id strings.

    Accepts None (→ []), str (→ [str]), or list[str] (→ copy).
    Anything else raises NodeValidationError.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str):
                raise NodeValidationError(
                    f"parents entries must be strings, got {type(item).__name__}: {item!r}"
                )
        return list(raw)
    raise NodeValidationError(
        f"parents must be string or list, got {type(raw).__name__}: {raw!r}"
    )


class Node:
    """Abstract base for every storage graph node."""

    TYPE: ClassVar[str] = ""

    def __init__(self, raw: dict[str, Any], ctx: Context) -> None:
        if "id" not in raw:
            raise NodeValidationError(f"{self.TYPE}: missing required field 'id'")
        self.id: str = str(raw["id"])
        self.raw: dict[str, Any] = raw
        self.ctx: Context = ctx
        self.parents: list[str] = normalize_parents(raw.get("parents"))
        self.ignore_errors: bool = _as_bool(
            raw.get("ignore_errors", False),
            field_name=f"{self.TYPE} id={self.id}: ignore_errors",
        )
        self._resolved_parents: list[Node] = []
        self._cleanup_actions: list[Callable[[], None]] = []

    # ------------------------------------------------------------
    # Contract implemented by subclasses.
    # ------------------------------------------------------------

    def validate(self) -> None:
        """Validate fields; raise NodeValidationError on bad input."""

    def execute(self) -> None:
        """Run effective_command_lines() then call _post_execute() for cleanup registration."""
        for cmd in self.effective_command_lines():
            self.ctx.sys.run(cmd.argv, stdin=cmd.stdin, check=cmd.check)
        self._post_execute()

    def _post_execute(self) -> None:
        """Override to register cleanup actions after commands complete."""

    def device_path(self) -> str | None:
        """Return the block device path this node produces, or None."""
        return None

    def command_lines(self) -> list[ShellCommand]:
        """Return ShellCommand records that produce this node's effect.

        Shared between Executor and ScriptGenerator. Subclasses that need
        runtime-derived state may override execute() directly and return [].
        """
        return []

    def effective_command_lines(self) -> list[ShellCommand]:
        """Return command_lines() with ignore_errors applied to `check`.

        Both Executor and ScriptGenerator consume this. When ignore_errors
        is set, every ShellCommand is rewritten with check=False so that
        SystemCommand.run() will not raise and the emitted script appends
        `|| true` to each command.
        """
        cmds = self.command_lines()
        if not self.ignore_errors:
            return cmds
        return [dataclasses.replace(c, check=False) for c in cmds]

    # ------------------------------------------------------------
    # Helpers.
    # ------------------------------------------------------------

    def register_cleanup(self, fn: Callable[[], None]) -> None:
        self._cleanup_actions.append(fn)

    def _require_one_parent(self) -> Node:
        if len(self._resolved_parents) != 1:
            raise NodeValidationError(
                f"{self.TYPE} id={self.id}: expected exactly one parent, "
                f"got {len(self._resolved_parents)}"
            )
        return self._resolved_parents[0]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r}>"
