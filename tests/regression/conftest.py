"""Auto-mark all tests in tests/regression/ as @pytest.mark.regression."""
from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.parent and item.parent.path and "tests/regression" in str(item.parent.path):
            item.add_marker(pytest.mark.regression)