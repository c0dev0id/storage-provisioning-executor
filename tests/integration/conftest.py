# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration-test fixtures: loop devices backed by sparse files."""

from __future__ import annotations

import pathlib
import subprocess
from typing import Iterator

import pytest


pytestmark = pytest.mark.integration


def _attach(sparse: pathlib.Path) -> str:
    return subprocess.check_output(
        ["losetup", "--find", "--show", "-P", str(sparse)],
        text=True,
    ).strip()


def _detach(dev: str) -> None:
    subprocess.run(["losetup", "-d", dev], check=False)


@pytest.fixture
def loop_device(tmp_path: pathlib.Path) -> Iterator[str]:
    sparse = tmp_path / "disk.img"
    subprocess.run(["truncate", "-s", "256M", str(sparse)], check=True)
    dev = _attach(sparse)
    try:
        yield dev
    finally:
        subprocess.run(["umount", "-R", dev], check=False)
        _detach(dev)


@pytest.fixture
def two_loop_devices(tmp_path: pathlib.Path) -> Iterator[tuple[str, str]]:
    paths = [tmp_path / "a.img", tmp_path / "b.img"]
    devs: list[str] = []
    try:
        for p in paths:
            subprocess.run(["truncate", "-s", "128M", str(p)], check=True)
            devs.append(_attach(p))
        yield (devs[0], devs[1])
    finally:
        for dev in devs:
            _detach(dev)


@pytest.fixture
def three_loop_devices(tmp_path: pathlib.Path) -> Iterator[tuple[str, str, str]]:
    paths = [tmp_path / f"{name}.img" for name in ("main", "r1", "r2")]
    devs: list[str] = []
    try:
        for p in paths:
            subprocess.run(["truncate", "-s", "256M", str(p)], check=True)
            devs.append(_attach(p))
        yield (devs[0], devs[1], devs[2])
    finally:
        for dev in devs:
            subprocess.run(["umount", "-R", dev], check=False)
            _detach(dev)
