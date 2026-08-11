"""Pytest configuration — shared fixtures and marker registration for VolFoundry."""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so ``pytest --markers`` lists them."""
    markers = [
        ("unit", "Fast deterministic unit tests (default CI suite)"),
        ("integration", "Tests that combine multiple modules"),
        ("property", "Hypothesis property-based tests for mathematical invariants"),
        ("regression", "Golden-fixture tests with expected outputs and tolerances"),
        ("live", "Tests requiring live Deribit network access — excluded from default suite"),
        ("slow", "Tests that take significantly longer than the typical unit"),
        ("benchmark", "Performance benchmarks — may require optional dependencies"),
    ]
    for name, desc in markers:
        config.addinivalue_line("markers", f"{name}: {desc}")