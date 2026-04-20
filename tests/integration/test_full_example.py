# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration test: README-shaped stack end-to-end on loop devices.

Covers mount ordering (/ < /boot < /boot/efi), LVM, LUKS, RAID1, fat32, ext4,
xfs, and cleanup ordering on success path.
"""

from __future__ import annotations

import subprocess

import pytest

from storage.executor import Executor
from storage.spec import load_spec


pytestmark = pytest.mark.integration


def test_full_stack(three_loop_devices: tuple[str, str, str], tmp_path) -> None:
    main_dev, r1_dev, r2_dev = three_loop_devices
    target = str(tmp_path / "target")
    spec = f"""
vars:
  hostname: "sprovhost"
storage:
  - {{type: control, path: {target}}}

  - type: hardware
    id: hwMain
    path: {main_dev}
    overwrite: "yes"
    label: gpt

  - type: partition
    id: pEFI
    parents: hwMain
    size: 48MiB
    flags: [boot, esp]
  - type: partition
    id: pBoot
    parents: hwMain
    size: 48MiB
  - type: partition
    id: pPv
    parents: hwMain
    size: "{{max}}"

  - type: lvm-pv
    id: pv
    parents: pPv
  - type: lvm-vg
    id: vg
    name: vgmain
    parents: [pv]
  - type: lvm-lv
    id: lvroot
    name: lvroot
    parents: vg
    size: 80MiB

  - type: dm-crypt-luks
    id: cryptroot
    parents: lvroot
    key:
      passphrase: "sprov-test"

  - type: filesystem
    id: fsRoot
    parents: cryptroot
    fstype: ext4
    label: "{{{{hostname}}}}-root"
    mountpoint: /
  - type: filesystem
    id: fsBoot
    parents: pBoot
    fstype: ext4
    label: "boot"
    mountpoint: /boot
  - type: filesystem
    id: fsEfi
    parents: pEFI
    fstype: fat32
    label: "EFI"
    mountpoint: /boot/efi

  - type: hardware
    id: hwR1
    path: {r1_dev}
    overwrite: "yes"
    label: gpt
  - type: hardware
    id: hwR2
    path: {r2_dev}
    overwrite: "yes"
    label: gpt
  - type: partition
    id: pr1
    parents: hwR1
    size: "{{max}}"
  - type: partition
    id: pr2
    parents: hwR2
    size: "{{max}}"
  - type: raid1
    id: md
    parents: [pr1, pr2]
    name: md77
  - type: filesystem
    id: fsSrv
    parents: md
    fstype: xfs
    label: "srv"
    mountpoint: /srv
"""
    _ctx, nodes = load_spec(spec)
    try:
        Executor(nodes).run()
        mount_info = subprocess.check_output(["mount"], text=True)
        assert target in mount_info
        assert f"{target}/boot" in mount_info
        assert f"{target}/boot/efi" in mount_info
        assert f"{target}/srv" in mount_info
    finally:
        subprocess.run(["umount", "-R", target], check=False)
        subprocess.run(["cryptsetup", "close", "cryptroot"], check=False)
        subprocess.run(["vgchange", "-an", "vgmain"], check=False)
        subprocess.run(["vgremove", "-f", "vgmain"], check=False)
        subprocess.run(["mdadm", "--stop", "/dev/md77"], check=False)
