# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for storage.system.parse_size."""

from __future__ import annotations

import pytest

from storage.system import SIZE_MAX, parse_size


@pytest.mark.parametrize(
    "expr,expected",
    [
        (0, 0),
        (1024, 1024),
        ("0", 0),
        ("1024", 1024),
        ("1024b", 1024),
        ("1K", 1024),
        ("1k", 1024),
        ("1KiB", 1024),
        ("1kib", 1024),
        ("4M", 4 * 1024**2),
        ("4MiB", 4 * 1024**2),
        ("4G", 4 * 1024**3),
        ("4GiB", 4 * 1024**3),
        ("1T", 1024**4),
        ("1TiB", 1024**4),
        ("1KB", 1000),
        ("1MB", 1000**2),
        ("1GB", 1000**3),
        ("1TB", 1000**4),
        ("2048s", 2048 * 512),
        ("4s", 2048),
        ("  4G  ", 4 * 1024**3),
    ],
)
def test_parse_size_valid(expr: str | int, expected: int) -> None:
    assert parse_size(expr) == expected


@pytest.mark.parametrize("expr", ["{max}", "max", "MAX", "{MAX}", "  {max}  "])
def test_parse_size_max_sentinel(expr: str) -> None:
    assert parse_size(expr) == SIZE_MAX


@pytest.mark.parametrize(
    "expr",
    ["", "foo", "4GX", "-5", "4 Gi B", "G4", "4..0G", "4.5G", "True"],
)
def test_parse_size_invalid(expr: str) -> None:
    with pytest.raises(ValueError):
        parse_size(expr)


def test_parse_size_bool_rejected() -> None:
    with pytest.raises(ValueError):
        parse_size(True)  # type: ignore[arg-type]


def test_parse_size_negative_int_rejected() -> None:
    with pytest.raises(ValueError):
        parse_size(-1)


def test_parse_size_custom_sector_size() -> None:
    assert parse_size("100s", sector_size=4096) == 100 * 4096


def test_parse_size_sentinel_identity() -> None:
    # SIZE_MAX is the exact literal "MAX" — callers may compare with ==.
    assert SIZE_MAX == "MAX"
    assert parse_size("{max}") == SIZE_MAX
