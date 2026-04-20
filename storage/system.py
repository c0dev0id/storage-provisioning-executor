# SPDX-License-Identifier: GPL-2.0-or-later
"""System-level helpers: subprocess wrapper with dry-run and verbosity."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field


VERBOSITY_SILENT = 0
VERBOSITY_NORMAL = 1
VERBOSITY_VERBOSE = 2
VERBOSITY_DEBUG = 3


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
