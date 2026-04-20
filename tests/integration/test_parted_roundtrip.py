# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration test: partition a loop device end-to-end."""

from __future__ import annotations

import subprocess

import pytest

from storage.executor import Executor
from storage.spec import load_spec


pytestmark = pytest.mark.integration


def test_partition_and_mkfs_ext4_roundtrip(loop_device: str, tmp_path) -> None:
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
    size: 64MiB
  - type: filesystem
    id: fs
    parents: p1
    fstype: ext4
    mountpoint: /
"""
    _ctx, nodes = load_spec(spec)
    Executor(nodes).run()
    mount_info = subprocess.check_output(["mount"], text=True)
    assert target in mount_info
    subprocess.run(["umount", "-R", target], check=False)
