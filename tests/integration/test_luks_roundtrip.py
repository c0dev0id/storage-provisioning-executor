# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration test: LUKS2 container on a loop device."""

from __future__ import annotations

import subprocess

import pytest

from storage.executor import Executor
from storage.spec import load_spec


pytestmark = pytest.mark.integration


def test_luks_format_open_and_mkfs(loop_device: str, tmp_path) -> None:
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
    id: crypt
    parents: p1
    key:
      passphrase: "testpassword"
  - type: filesystem
    id: fs
    parents: crypt
    fstype: ext4
    mountpoint: /
"""
    _ctx, nodes = load_spec(spec)
    try:
        Executor(nodes).run()
        header = subprocess.check_output(
            ["cryptsetup", "isLuks", "--type", "luks2", f"{loop_device}p1"],
            stderr=subprocess.STDOUT,
        )
        assert header is not None  # exits 0 only if header is LUKS2
        mount_info = subprocess.check_output(["mount"], text=True)
        assert target in mount_info
    finally:
        subprocess.run(["umount", "-R", target], check=False)
        subprocess.run(["cryptsetup", "close", "crypt"], check=False)
