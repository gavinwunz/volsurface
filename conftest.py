"""Pytest configuration — shared fixtures and marker registration for VolFoundry."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so ``pytest --markers`` lists them."""
    config.addinivalue_line(
        "markers",
        "unit: Fast deterministic unit tests (default CI suite)",
    )
    config.addinivalue_line(
        "markers",
        "integration: Tests that combine multiple modules",
    )
    config.addinivalue_line(
        "markers",
        "live: Tests requiring live Deribit network access — excluded from default suite",
    )
    config.addinivalue_line(
        "markers",
        "slow: Tests that take significantly longer than the typical unit",
    )
    config.addinivalue_line(
        "markers",
        "benchmark: Performance benchmarks — may require optional dependencies",
    )