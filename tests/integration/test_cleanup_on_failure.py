# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration test: reverse cleanup fires when a step fails mid-run.

Strategy: open a LUKS container (which registers a close-cleanup), then force
mkfs to fail via a bogus option. After the executor raises NodeExecutionError,
the LUKS mapper must be gone (cryptsetup status exits nonzero).
"""

from __future__ import annotations

import subprocess

import pytest

from storage.base import NodeExecutionError
from storage.executor import Executor
from storage.spec import load_spec


pytestmark = pytest.mark.integration


def test_luks_is_closed_after_failure(loop_device: str, tmp_path) -> None:
    target = str(tmp_path / "target")
    spec = f"""
storage:
  - {{type: control, path: {target}}}
  - type: hardware
    id: hw
    path: {loop_device}
    overwrite: "yes"
    label: gpt
  - type: partition
    id: p1
    parents: hw
    size: 128MiB
  - type: dm-crypt-luks
    id: crfail
    parents: p1
    key:
      passphrase: "testpassword"
  - type: filesystem
    id: fs
    parents: crfail
    fstype: ext4
    mountpoint: /
    mkfs_options: ["--this-flag-does-not-exist"]
"""
    _ctx, nodes = load_spec(spec)
    with pytest.raises(NodeExecutionError):
        Executor(nodes).run()

    # The LUKS mapper must have been closed by reverse cleanup.
    rc = subprocess.run(
        ["cryptsetup", "status", "crfail"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode
    assert rc != 0, "cryptsetup mapper still active; cleanup did not close it"
