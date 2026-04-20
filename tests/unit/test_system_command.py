# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for storage.system.SystemCommand."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from storage.system import (
    CommandResult,
    SystemCommand,
    SystemCommandError,
    VERBOSITY_DEBUG,
    VERBOSITY_NORMAL,
    VERBOSITY_SILENT,
    VERBOSITY_VERBOSE,
)


def test_dry_run_does_not_fork() -> None:
    sc = SystemCommand(dry_run=True)
    with patch("storage.system.subprocess.run") as mock_run:
        result = sc.run(["ls", "/"])
    mock_run.assert_not_called()
    assert result.rc == 0
    assert result.cmd == ["ls", "/"]
    assert result.stdout == ""
    assert result.stderr == ""


def test_normal_run_captures_output() -> None:
    sc = SystemCommand(dry_run=False)
    fake_proc = MagicMock(returncode=0, stdout=b"hello\n", stderr=b"")
    with patch("storage.system.subprocess.run", return_value=fake_proc) as mock_run:
        result = sc.run(["echo", "hello"])
    mock_run.assert_called_once()
    assert result.rc == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""


def test_nonzero_rc_with_check_raises() -> None:
    sc = SystemCommand(dry_run=False)
    fake_proc = MagicMock(returncode=2, stdout=b"", stderr=b"boom\n")
    with patch("storage.system.subprocess.run", return_value=fake_proc):
        with pytest.raises(SystemCommandError) as excinfo:
            sc.run(["false"])
    assert excinfo.value.result.rc == 2
    assert "boom" in str(excinfo.value)


def test_nonzero_rc_with_check_false_returns() -> None:
    sc = SystemCommand(dry_run=False)
    fake_proc = MagicMock(returncode=1, stdout=b"", stderr=b"nope")
    with patch("storage.system.subprocess.run", return_value=fake_proc):
        result = sc.run(["false"], check=False)
    assert result.rc == 1
    assert result.stderr == "nope"


def test_stdin_bytes_never_logged_verbatim(caplog: pytest.LogCaptureFixture) -> None:
    sc = SystemCommand(dry_run=True, verbosity=VERBOSITY_DEBUG)
    caplog.set_level(logging.DEBUG, logger="sprov")
    secret = b"hunter2"
    sc.run(["cryptsetup", "luksFormat", "/dev/loop0"], stdin=secret)
    captured = caplog.text
    assert "hunter2" not in captured
    assert "[stdin: 7 bytes]" in captured


def test_silent_verbosity_suppresses_info(caplog: pytest.LogCaptureFixture) -> None:
    sc = SystemCommand(dry_run=True, verbosity=VERBOSITY_SILENT)
    caplog.set_level(logging.DEBUG, logger="sprov")
    sc.run(["ls", "/"])
    assert "exec:" not in caplog.text


def test_verbose_verbosity_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    sc = SystemCommand(dry_run=True, verbosity=VERBOSITY_VERBOSE)
    caplog.set_level(logging.INFO, logger="sprov")
    sc.run(["ls", "/"])
    assert "exec: ls /" in caplog.text


def test_debug_verbosity_logs_rc_stdout_stderr(caplog: pytest.LogCaptureFixture) -> None:
    sc = SystemCommand(dry_run=False, verbosity=VERBOSITY_DEBUG)
    fake_proc = MagicMock(returncode=0, stdout=b"out-data\n", stderr=b"err-data\n")
    caplog.set_level(logging.DEBUG, logger="sprov")
    with patch("storage.system.subprocess.run", return_value=fake_proc):
        sc.run(["echo", "x"])
    assert "rc=0" in caplog.text
    assert "out-data" in caplog.text
    assert "err-data" in caplog.text


def test_normal_verbosity_does_not_log_result_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sc = SystemCommand(dry_run=False, verbosity=VERBOSITY_NORMAL)
    fake_proc = MagicMock(returncode=0, stdout=b"detail", stderr=b"")
    caplog.set_level(logging.DEBUG, logger="sprov")
    with patch("storage.system.subprocess.run", return_value=fake_proc):
        sc.run(["true"])
    assert "rc=" not in caplog.text
    assert "detail" not in caplog.text


def test_command_result_defaults() -> None:
    r = CommandResult(cmd=["a"], rc=0)
    assert r.stdout == ""
    assert r.stderr == ""


def test_env_passed_through() -> None:
    sc = SystemCommand(dry_run=False)
    fake_proc = MagicMock(returncode=0, stdout=b"", stderr=b"")
    env = {"PATH": "/usr/bin"}
    with patch("storage.system.subprocess.run", return_value=fake_proc) as mock_run:
        sc.run(["env"], env=env)
    assert mock_run.call_args.kwargs["env"] == env


def test_stdin_bytes_forwarded() -> None:
    sc = SystemCommand(dry_run=False)
    fake_proc = MagicMock(returncode=0, stdout=b"", stderr=b"")
    with patch("storage.system.subprocess.run", return_value=fake_proc) as mock_run:
        sc.run(["cat"], stdin=b"payload")
    assert mock_run.call_args.kwargs["input"] == b"payload"
