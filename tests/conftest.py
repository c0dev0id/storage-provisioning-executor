# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared pytest configuration and fixtures.

Integration tests are skipped by default. Enable them with:
    pytest --run-integration
or by setting environment variable INTEGRATION=1.
"""

import os
import sys

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests (require Linux + privileged + loop devices)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: marks tests requiring real Linux block-device subsystems",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_integration = config.getoption("--run-integration") or os.environ.get(
        "INTEGRATION"
    ) == "1"
    if run_integration and sys.platform != "linux":
        skip = pytest.mark.skip(reason="integration tests require Linux")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
        return
    if not run_integration:
        skip = pytest.mark.skip(reason="need --run-integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
