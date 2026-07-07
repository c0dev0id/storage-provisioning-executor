# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for ScriptGenerator, including the example-spec golden-file diff."""

from __future__ import annotations

import pathlib

import pytest

from storage.base import ShellCommand
from storage.executor import Executor
from storage.scriptgen import ScriptGenerator, _render_command
from storage.spec import load_spec


DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"


def test_emit_header_and_shebang() -> None:
    sg = ScriptGenerator([])
    out = sg.emit()
    assert out.startswith("#!/bin/sh\n")
    assert "set -eux" in out


def test_render_command_basic_argv() -> None:
    out = _render_command(ShellCommand(argv=["mkfs.ext4", "-F", "/dev/sda1"]))
    assert out == "mkfs.ext4 -F /dev/sda1"


def test_render_command_quotes_special_chars() -> None:
    out = _render_command(ShellCommand(argv=["echo", "hello world", "a&b"]))
    assert out == "echo 'hello world' 'a&b'"


def test_render_command_with_comment() -> None:
    out = _render_command(
        ShellCommand(argv=["true"], comment="this does nothing")
    )
    assert out == "# this does nothing\ntrue"


def test_render_command_check_false_appends_or_true() -> None:
    out = _render_command(ShellCommand(argv=["false"], check=False))
    assert out == "false || true"


def test_render_command_stdin_uses_heredoc() -> None:
    out = _render_command(
        ShellCommand(argv=["cat"], stdin=b"hello\n")
    )
    expected = "cat <<'SPROV_STDIN_EOF'\nhello\nSPROV_STDIN_EOF"
    assert out == expected


def test_render_command_stdin_missing_trailing_newline_is_added() -> None:
    out = _render_command(ShellCommand(argv=["cat"], stdin=b"hello"))
    assert out == "cat <<'SPROV_STDIN_EOF'\nhello\nSPROV_STDIN_EOF"


def test_render_command_stdin_rejects_marker_collision() -> None:
    bad = b"some\nSPROV_STDIN_EOF\ndata\n"
    with pytest.raises(ValueError, match="heredoc marker"):
        _render_command(ShellCommand(argv=["cat"], stdin=bad))


def test_render_command_stdin_rejects_non_utf8() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        _render_command(ShellCommand(argv=["cat"], stdin=b"\xff\xfe"))


def test_render_command_stdin_with_check_false() -> None:
    out = _render_command(
        ShellCommand(argv=["cat"], stdin=b"x\n", check=False)
    )
    assert "cat <<'SPROV_STDIN_EOF' || true" in out


def test_emit_omits_verify_section_when_no_nodes_verify() -> None:
    out = ScriptGenerator([]).emit()
    assert "# === verify ===" not in out


def test_emit_appends_verify_section_from_filesystem_nodes() -> None:
    from storage.base import Context
    from storage.filesystem import FilesystemNode
    from storage.hardware import HardwareNode

    ctx = Context(control_path="/target")
    hw = HardwareNode({"id": "hw", "path": "/dev/sda1"}, ctx)
    fs = FilesystemNode(
        {"id": "fs", "parents": "hw", "fstype": "ext4", "mountpoint": "/boot"},
        ctx,
    )
    fs._resolved_parents = [hw]
    out = ScriptGenerator([hw, fs]).emit()
    assert "# === verify ===" in out
    assert "mountpoint -q /target/boot" in out
    # Verify section must come after the fs node's own commands.
    assert out.index("mount /dev/sda1") < out.index("mountpoint -q")


def test_emit_golden_matches_checked_in_file() -> None:
    yaml_path = DATA_DIR / "example.yaml"
    golden_path = DATA_DIR / "example.sh.golden"
    _ctx, nodes = load_spec(yaml_path.read_text())
    ordered = Executor(nodes).prepare()
    actual = ScriptGenerator(ordered).emit()
    expected = golden_path.read_text()
    if actual != expected:
        # When this fires, run `python3 -m tests.regen_golden` (or just
        # rerun sprov --script) to update the expected output after a
        # deliberate node-behavior change.
        diff = _mini_diff(expected, actual)
        pytest.fail(f"generated script diverged from golden:\n{diff}")


def test_emit_golden_is_posix_sh_parseable(tmp_path: pathlib.Path) -> None:
    import subprocess
    script = DATA_DIR / "example.sh.golden"
    result = subprocess.run(
        ["sh", "-n", str(script)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


def _mini_diff(expected: str, actual: str) -> str:
    import difflib
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual",
            n=3,
        )
    )
