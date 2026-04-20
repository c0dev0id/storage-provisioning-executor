# SPDX-License-Identifier: GPL-2.0-or-later
"""CLI entry point — parse args, load spec, run Executor or ScriptGenerator."""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from typing import IO

from storage import __version__
from storage.base import NodeExecutionError, NodeValidationError
from storage.executor import Executor
from storage.scriptgen import ScriptGenerator
from storage.spec import load_spec
from storage.system import (
    VERBOSITY_DEBUG,
    VERBOSITY_NORMAL,
    VERBOSITY_SILENT,
    VERBOSITY_VERBOSE,
    SystemCommand,
)


EXIT_SUCCESS = 0
EXIT_VALIDATION = 1
EXIT_EXECUTION = 2
EXIT_CLEANUP = 3
EXIT_USAGE = 64


_logger = logging.getLogger("sprov")


def main(
    argv: list[str] | None = None,
    *,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    """Run the CLI. Returns a process exit code."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    parser = _build_parser()
    args = parser.parse_args(argv)

    verbosity = _resolve_verbosity(args.verbose, args.quiet)
    _setup_logging(verbosity)

    try:
        yaml_text = pathlib.Path(args.spec).read_text()
    except OSError as exc:
        print(f"sprov: cannot read spec: {exc}", file=err)
        return EXIT_USAGE

    try:
        _ctx, nodes = load_spec(
            yaml_text,
            ctx_overrides={
                "dry_run": args.dry_run,
                "verbosity": verbosity,
                "sys": SystemCommand(dry_run=args.dry_run, verbosity=verbosity),
            },
        )
        executor = Executor(nodes)
        ordered = executor.prepare()
    except NodeValidationError as exc:
        print(f"sprov: validation error: {exc}", file=err)
        return EXIT_VALIDATION

    if args.script:
        out.write(ScriptGenerator(ordered).emit())
        return EXIT_SUCCESS

    if not args.no_cleanup_first and not args.dry_run:
        _preflight_cleanup(_ctx.control_path)

    try:
        executor.run()
    except NodeExecutionError as exc:
        print(f"sprov: execution failed: {exc}", file=err)
        return EXIT_EXECUTION
    return EXIT_SUCCESS


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sprov",
        description="Storage provisioning executor (YAML-driven)",
    )
    p.add_argument(
        "--version", action="version", version=f"sprov {__version__}"
    )
    p.add_argument(
        "-n", "--dry-run", action="store_true",
        help="Log every command without running it",
    )
    p.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase verbosity (repeatable: -v, -vv, -vvv)",
    )
    p.add_argument(
        "-q", "--quiet", action="count", default=0,
        help="Decrease verbosity (repeatable)",
    )
    p.add_argument(
        "--script", action="store_true",
        help="Emit a busybox-compatible POSIX shell script to stdout and exit",
    )
    p.add_argument(
        "--no-cleanup-first", action="store_true",
        help="Skip the implicit pre-flight cleanup of control.path",
    )
    p.add_argument(
        "spec", help="Path to the YAML spec file",
    )
    return p


def _resolve_verbosity(verbose: int, quiet: int) -> int:
    level = VERBOSITY_NORMAL + verbose - quiet
    return max(VERBOSITY_SILENT, min(VERBOSITY_DEBUG, level))


def _setup_logging(level: int) -> None:
    mapping = {
        VERBOSITY_SILENT: logging.WARNING,
        VERBOSITY_NORMAL: logging.INFO,
        VERBOSITY_VERBOSE: logging.INFO,
        VERBOSITY_DEBUG: logging.DEBUG,
    }
    py_level = mapping.get(level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(py_level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)


def _preflight_cleanup(control_path: str) -> None:
    """Best-effort tear-down of a previous failed run's state."""
    sysc = SystemCommand()
    try:
        sysc.run(["umount", "-R", control_path], check=False)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("pre-flight umount ignored: %s", exc)


if __name__ == "__main__":
    sys.exit(main())
