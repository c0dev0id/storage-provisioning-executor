# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for CryptLuksNode."""

from __future__ import annotations

import pytest

from storage.base import Context, NodeValidationError
from storage.crypt import CryptLuksNode
from storage.hardware import HardwareNode


def _hw(path: str = "/dev/sda1") -> HardwareNode:
    return HardwareNode({"id": "hw", "path": path}, Context())


def test_requires_passphrase() -> None:
    with pytest.raises(NodeValidationError, match="passphrase is required"):
        CryptLuksNode({"id": "c", "parents": "p", "key": {}}, Context())


def test_key_must_be_mapping() -> None:
    with pytest.raises(NodeValidationError, match="must be a mapping"):
        CryptLuksNode({"id": "c", "parents": "p", "key": "hunter2"}, Context())


def test_default_slot_is_zero() -> None:
    n = CryptLuksNode(
        {"id": "c", "parents": "p", "key": {"passphrase": "x"}}, Context()
    )
    assert n.slot == 0


def test_validate_needs_one_parent() -> None:
    n = CryptLuksNode(
        {"id": "c", "parents": ["a", "b"], "key": {"passphrase": "x"}},
        Context(),
    )
    with pytest.raises(NodeValidationError, match="exactly one parent"):
        n.validate()


def test_validate_rejects_empty_passphrase() -> None:
    n = CryptLuksNode(
        {"id": "c", "parents": "p", "key": {"passphrase": ""}}, Context()
    )
    with pytest.raises(NodeValidationError, match="empty passphrase"):
        n.validate()


def test_validate_rejects_slot_out_of_range() -> None:
    n = CryptLuksNode(
        {"id": "c", "parents": "p", "key": {"passphrase": "x", "slot": 8}},
        Context(),
    )
    with pytest.raises(NodeValidationError, match="slot must be 0..7"):
        n.validate()


def test_mapper_name_sanitized() -> None:
    n = CryptLuksNode(
        {"id": "crypt/root!", "parents": "p", "key": {"passphrase": "x"}},
        Context(),
    )
    assert n.mapper_name == "crypt_root_"


def test_device_path() -> None:
    n = CryptLuksNode(
        {"id": "crypt-root", "parents": "p", "key": {"passphrase": "x"}},
        Context(),
    )
    assert n.device_path() == "/dev/mapper/crypt-root"


def test_command_lines_slot0_format_and_open() -> None:
    n = CryptLuksNode(
        {"id": "crypt-root", "parents": "p", "key": {"passphrase": "hunter2"}},
        Context(),
    )
    n._resolved_parents = [_hw("/dev/sda1")]
    cmds = n.command_lines()
    assert len(cmds) == 2
    assert cmds[0].argv[:5] == [
        "cryptsetup", "-q", "--type", "luks2", "luksFormat",
    ]
    assert cmds[0].argv[-1] == "/dev/sda1"
    assert cmds[0].stdin == b"hunter2"
    assert cmds[1].argv[0:4] == ["cryptsetup", "-q", "open", "--type"]
    assert cmds[1].argv[-1] == "crypt-root"
    assert cmds[1].stdin == b"hunter2"


def test_command_lines_nonzero_slot_adds_and_kills() -> None:
    n = CryptLuksNode(
        {
            "id": "crypt-root",
            "parents": "p",
            "key": {"passphrase": "pw", "slot": 3},
        },
        Context(),
    )
    n._resolved_parents = [_hw("/dev/sda1")]
    cmds = n.command_lines()
    assert len(cmds) == 4
    add_key = cmds[2]
    kill_slot = cmds[3]
    assert "--key-slot=3" in add_key.argv
    assert "luksAddKey" in add_key.argv
    assert add_key.stdin is not None
    assert b"pw" in add_key.stdin
    assert "luksKillSlot" in kill_slot.argv
    assert kill_slot.argv[-1] == "0"
    assert kill_slot.stdin == b"pw"


def test_passphrase_never_in_argv() -> None:
    n = CryptLuksNode(
        {
            "id": "c",
            "parents": "p",
            "key": {"passphrase": "topsecret123"},
        },
        Context(),
    )
    n._resolved_parents = [_hw("/dev/sda1")]
    for cmd in n.command_lines():
        assert all("topsecret123" not in arg for arg in cmd.argv)
