# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration test: RAID1 on two loop devices, then mkfs + mount."""

from __future__ import annotations

import subprocess

import pytest

from storage.executor import Executor
from storage.spec import load_spec


pytestmark = pytest.mark.integration


def test_raid1_xfs(two_loop_devices: tuple[str, str], tmp_path) -> None:
    dev_a, dev_b = two_loop_devices
    target = str(tmp_path / "target")
    spec = f"""
storage:
  - {{type: control, path: {target}}}
  - type: hardware
    id: hwA
    path: {dev_a}
    overwrite: "yes"
    label: gpt
  - type: hardware
    id: hwB
    path: {dev_b}
    overwrite: "yes"
    label: gpt
  - type: partition
    id: pA
    parents: hwA
    size: 64MiB
  - type: partition
    id: pB
    parents: hwB
    size: 64MiB
  - type: raid1
    id: rd
    parents: [pA, pB]
    name: md42
  - type: filesystem
    id: fs
    parents: rd
    fstype: xfs
    mountpoint: /
"""
    _ctx, nodes = load_spec(spec)
    try:
        Executor(nodes).run()
        mount_info = subprocess.check_output(["mount"], text=True)
        assert target in mount_info
        assert "xfs" in mount_info or "xfs" in subprocess.check_output(
            ["findmnt", "-n", "-o", "FSTYPE", target], text=True
        )
    finally:
        subprocess.run(["umount", "-R", target], check=False)
        subprocess.run(["mdadm", "--stop", "/dev/md42"], check=False)
