# SPDX-License-Identifier: GPL-2.0-or-later
"""System-level helpers: subprocess wrapper, size parser, templating."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal


VERBOSITY_SILENT = 0
VERBOSITY_NORMAL = 1
VERBOSITY_VERBOSE = 2
VERBOSITY_DEBUG = 3

SECTOR_SIZE = 512
SIZE_MAX: Literal["MAX"] = "MAX"

_SIZE_SUFFIXES: dict[str, int] = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kib": 1024,
    "kb": 1000,
    "m": 1024**2,
    "mib": 1024**2,
    "mb": 1000**2,
    "g": 1024**3,
    "gib": 1024**3,
    "gb": 1000**3,
    "t": 1024**4,
    "tib": 1024**4,
    "tb": 1000**4,
}

_SIZE_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z]*)\s*$")


def parse_size(expr: str | int, *, sector_size: int = SECTOR_SIZE) -> int | Literal["MAX"]:
    """Parse a size expression into bytes.

    Accepts:
      - int              -> returned as-is (bytes)
      - "1024"           -> bytes
      - "4G", "4GiB"     -> binary multiplier
      - "4GB"            -> decimal multiplier
      - "2048s"          -> sectors * sector_size
      - "{max}" or "max" -> sentinel SIZE_MAX

    Raises ValueError on unparseable input.
    """
    if isinstance(expr, bool):
        raise ValueError(f"unparseable size: {expr!r}")
    if isinstance(expr, int):
        if expr < 0:
            raise ValueError(f"size must be non-negative: {expr}")
        return expr
    if not isinstance(expr, str):
        raise ValueError(f"unparseable size: {expr!r}")
    s = expr.strip()
    if s.lower() in ("{max}", "max"):
        return SIZE_MAX
    if s.lower().endswith("s") and s[:-1].isdigit():
        return int(s[:-1]) * sector_size
    match = _SIZE_RE.match(s)
    if match is None:
        raise ValueError(f"unparseable size: {expr!r}")
    number = int(match.group(1))
    suffix = match.group(2).lower()
    if suffix not in _SIZE_SUFFIXES:
        raise ValueError(f"unknown size suffix {suffix!r} in {expr!r}")
    return number * _SIZE_SUFFIXES[suffix]


@dataclass
class CommandResult:
    """Outcome of a subprocess invocation."""

    cmd: list[str]
    rc: int
    stdout: str = ""
    stderr: str = ""


class SystemCommandError(RuntimeError):
    """Raised when a checked command exits non-zero."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        super().__init__(
            f"command {result.cmd!r} failed with rc={result.rc}: {result.stderr.strip()}"
        )


@dataclass
class SystemCommand:
    """Thin wrapper around subprocess.run with dry-run and verbosity support."""

    dry_run: bool = False
    verbosity: int = VERBOSITY_NORMAL
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("sprov"))

    def run(
        self,
        argv: list[str],
        *,
        stdin: bytes | None = None,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        self._log_invocation(argv, stdin)
        if self.dry_run:
            return CommandResult(cmd=list(argv), rc=0)
        proc = subprocess.run(  # noqa: S603  # argv list, no shell
            argv,
            input=stdin,
            capture_output=True,
            env=env,
            check=False,
        )
        result = CommandResult(
            cmd=list(argv),
            rc=proc.returncode,
            stdout=_decode(proc.stdout),
            stderr=_decode(proc.stderr),
        )
        self._log_result(result)
        if check and result.rc != 0:
            raise SystemCommandError(result)
        return result

    def _log_invocation(self, argv: list[str], stdin: bytes | None) -> None:
        if self.verbosity <= VERBOSITY_SILENT:
            return
        prefix = "[dry-run] " if self.dry_run else ""
        stdin_note = f" [stdin: {len(stdin)} bytes]" if stdin else ""
        msg = f"{prefix}exec: {_fmt_argv(argv)}{stdin_note}"
        if self.verbosity >= VERBOSITY_VERBOSE:
            self.logger.info(msg)
        else:
            self.logger.debug(msg)

    def _log_result(self, result: CommandResult) -> None:
        if self.verbosity < VERBOSITY_DEBUG:
            return
        self.logger.debug("    rc=%d", result.rc)
        if result.stdout:
            self.logger.debug("    stdout: %s", result.stdout.rstrip())
        if result.stderr:
            self.logger.debug("    stderr: %s", result.stderr.rstrip())


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _fmt_argv(argv: list[str]) -> str:
    return " ".join(argv)


_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def expand_vars(value: str, variables: dict[str, str]) -> str:
    """Replace {{var}} occurrences in value using variables; KeyError on miss."""

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise KeyError(f"undefined template variable: {key}")
        return str(variables[key])

    return _TEMPLATE_RE.sub(_repl, value)


def expand_vars_in_tree(data: Any, variables: dict[str, str]) -> Any:
    """Recursively walk dict/list/tuple structures, expanding every leaf string."""
    if isinstance(data, str):
        return expand_vars(data, variables)
    if isinstance(data, dict):
        return {k: expand_vars_in_tree(v, variables) for k, v in data.items()}
    if isinstance(data, list):
        return [expand_vars_in_tree(item, variables) for item in data]
    if isinstance(data, tuple):
        return tuple(expand_vars_in_tree(item, variables) for item in data)
    return data
