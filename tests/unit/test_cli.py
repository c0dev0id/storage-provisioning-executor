# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for the CLI argparse surface and exit-code contract."""

from __future__ import annotations

import io
import pathlib

import pytest

from storage.main import (
    EXIT_EXECUTION,
    EXIT_SUCCESS,
    EXIT_USAGE,
    EXIT_VALIDATION,
    _resolve_verbosity,
    main,
)
from storage.system import (
    VERBOSITY_DEBUG,
    VERBOSITY_NORMAL,
    VERBOSITY_SILENT,
    VERBOSITY_VERBOSE,
)


DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"


def _run(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    rc = main(argv, stdout=out, stderr=err)
    return rc, out.getvalue(), err.getvalue()


# --- verbosity math -------------------------------------------------


def test_resolve_verbosity_default() -> None:
    assert _resolve_verbosity(0, 0) == VERBOSITY_NORMAL


def test_resolve_verbosity_minus_v() -> None:
    assert _resolve_verbosity(1, 0) == VERBOSITY_VERBOSE
    assert _resolve_verbosity(2, 0) == VERBOSITY_DEBUG
    # Clamped at VERBOSITY_DEBUG.
    assert _resolve_verbosity(10, 0) == VERBOSITY_DEBUG


def test_resolve_verbosity_minus_q() -> None:
    assert _resolve_verbosity(0, 1) == VERBOSITY_SILENT
    # Clamped at VERBOSITY_SILENT.
    assert _resolve_verbosity(0, 5) == VERBOSITY_SILENT


def test_resolve_verbosity_minus_v_and_q_cancel() -> None:
    assert _resolve_verbosity(1, 1) == VERBOSITY_NORMAL


# --- CLI surface ----------------------------------------------------


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as info:
        _run(["--help"])
    assert info.value.code == 0


def test_version_exits_zero() -> None:
    with pytest.raises(SystemExit) as info:
        _run(["--version"])
    assert info.value.code == 0


def test_missing_spec_argument_exits_usage() -> None:
    with pytest.raises(SystemExit) as info:
        _run([])
    # argparse raises SystemExit with code 2 on usage errors.
    assert info.value.code == 2


def test_unreadable_spec_returns_usage_exit_code(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "nope.yaml"
    rc, _out, err = _run([str(missing)])
    assert rc == EXIT_USAGE
    assert "cannot read spec" in err


def test_validation_error_returns_validation_code(tmp_path: pathlib.Path) -> None:
    spec = tmp_path / "bad.yaml"
    spec.write_text("storage:\n  - {type: control, path: /t}\n  - {type: bogus, id: x}\n")
    rc, _out, err = _run([str(spec)])
    assert rc == EXIT_VALIDATION
    assert "unknown node type" in err


def test_script_mode_emits_to_stdout() -> None:
    rc, out, _err = _run(["--script", str(DATA_DIR / "example.yaml")])
    assert rc == EXIT_SUCCESS
    assert out.startswith("#!/bin/sh\n")
    assert "set -eu" in out
    assert "# === hw-sda (hardware) ===" in out


def test_script_mode_matches_golden() -> None:
    rc, out, _err = _run(["--script", str(DATA_DIR / "example.yaml")])
    assert rc == EXIT_SUCCESS
    expected = (DATA_DIR / "example.sh.golden").read_text()
    assert out == expected


def test_dry_run_executes_without_forking(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    spec = tmp_path / "min.yaml"
    spec.write_text(
        "storage:\n"
        "  - {type: control, path: /t}\n"
        "  - {type: hardware, id: hw, path: /dev/sda, overwrite: yes, label: gpt}\n"
    )
    caplog.set_level(logging.DEBUG, logger="sprov")
    rc, _out, _err = _run(["--dry-run", "-v", str(spec)])
    assert rc == EXIT_SUCCESS
    # Verbose dry-run echoes each command with the dry-run marker.
    assert any("[dry-run] exec:" in rec.message for rec in caplog.records)


def test_execution_error_returns_execution_code(tmp_path: pathlib.Path) -> None:
    # Use a spec that will fail during execute() because /dev paths don't exist
    # in dry-run=False, but we'd actually fork subprocess. The cleanest way to
    # exercise EXIT_EXECUTION without forking is to inject a broken node via
    # an unknown fstype that slips past the type registry but fails mkfs --
    # harder. Instead: a valid spec that the Executor.run() can't survive.
    #
    # We rely on subprocess failing because e.g. /dev/does-not-exist isn't
    # writable and parted bails; but this would fork. To keep the test
    # hermetic, skip here — covered by integration tests in CI.
    pytest.skip("EXIT_EXECUTION path exercised under CI integration tests")
