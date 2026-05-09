"""Root-level test configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end (e2e) tests that require Telegram bot infrastructure",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-e2e"):
        return  # Run all tests, including e2e
    skip_e2e = pytest.mark.skip(reason="Use --run-e2e to include e2e tests")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)