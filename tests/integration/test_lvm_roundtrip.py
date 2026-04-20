# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration test: PV → VG → LV → ext4 on a single loop device."""

from __future__ import annotations

import subprocess

import pytest

from storage.executor import Executor
from storage.spec import load_spec


pytestmark = pytest.mark.integration


def test_lvm_stack(loop_device: str, tmp_path) -> None:
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
    size: "{{max}}"
  - type: lvm-pv
    id: pv
    parents: p1
  - type: lvm-vg
    id: vg
    name: vgtest
    parents: [pv]
  - type: lvm-lv
    id: lv
    name: lvtest
    parents: vg
    size: 64MiB
  - type: filesystem
    id: fs
    parents: lv
    fstype: ext4
    mountpoint: /
"""
    _ctx, nodes = load_spec(spec)
    try:
        Executor(nodes).run()
        mount_info = subprocess.check_output(["mount"], text=True)
        assert target in mount_info
        assert "/dev/mapper/vgtest-lvtest" in mount_info \
            or "/dev/dm-" in mount_info
    finally:
        subprocess.run(["umount", "-R", target], check=False)
        subprocess.run(["vgchange", "-an", "vgtest"], check=False)
        subprocess.run(["vgremove", "-f", "vgtest"], check=False)
        subprocess.run(["pvremove", "-ff", "-y", f"{loop_device}p1"], check=False)
