# Testing Guide

VolFoundry uses pytest with markers to separate test categories.  The test suite
is organised under `tests/`.

## Test categories

| Directory | Marker | Description |
|-----------|--------|-------------|
| `tests/unit/` | `unit` | Fast, deterministic. Default CI suite. |
| `tests/property/` | `property` | Hypothesis property-based tests for mathematical invariants. |
| `tests/integration/` | `integration` | Multi-module pipeline tests (calibration, surface, persistence). |
| `tests/regression/` | `regression` | Golden fixtures — deterministic inputs with known outputs. |
| `tests/live/` | `live` | Live Deribit integration (scheduled, not per-PR). |

Additional markers:

| Marker | Purpose |
|--------|---------|
| `slow` | Tests taking >5 seconds |
| `benchmark` | QuantLib/py_vollib comparison benchmarks |

Each directory has a `conftest.py` that auto-marks files within it, so tests
inherited from the file tree get the correct marker automatically.

## Running tests

```bash
# Fast deterministic suite (default for CI)
pytest -m "not live and not benchmark"

# Everything
pytest

# Live tests only
pytest -m live

# Benchmark comparisons
pytest -m benchmark

# Specific category
pytest -m unit
pytest -m integration
pytest -m regression
pytest -m property

# With coverage
pytest -m "not live and not benchmark" --cov=volfoundry --cov-report=term
```

## Writing tests

### Unit tests

```python
# tests/unit/test_example.py
import pytest
from volfoundry.pricers import black76_price, OptionType

def test_black76_atm():
    price = black76_price(F=100, K=100, T=1.0, sigma=0.2, option_type=OptionType.CALL)
    assert price == pytest.approx(7.9655, rel=1e-4)
```

### Property-based tests

```python
from hypothesis import given, strategies as st

@given(
    sigma=st.floats(min_value=0.01, max_value=2.0),
    T=st.floats(min_value=0.01, max_value=5.0),
)
def test_put_call_parity(sigma, T):
    call = black76_price(F=100, K=100, T=T, sigma=sigma, option_type=OptionType.CALL)
    put = black76_price(F=100, K=100, T=T, sigma=sigma, option_type=OptionType.PUT)
    assert call == pytest.approx(put, abs=1e-12)
```

### Regression tests

```python
def test_golden_calibration(golden_calibration_fixture):
    """Calibrate on a known dataset and verify outputs."""
    df, expected_params = golden_calibration_fixture
    result = SurfaceBuilder().fit_dataframe(df)
    assert result.global_diagnostics["r2"] == pytest.approx(expected_params["r2"], rel=1e-3)
```

### Live tests

```python
@pytest.mark.live
def test_fetch_btc_snapshot():
    """Verify we can fetch a public BTC snapshot and it has the expected schema."""
    snapshot = DeribitClient(read_timeout=15).fetch("BTC")
    assert snapshot.currency == "BTC"
    assert len(snapshot.raw_quotes) > 0
```

## Adding a new test

1. Determine the category (unit, integration, property, regression, live).
2. Place the file in the corresponding `tests/<category>/` directory.
3. Automatic marker registration via `conftest.py`.
4. Use `pytest` decorators for additional markers (`@pytest.mark.slow`,
   `@pytest.mark.benchmark`).
5. Ensure it passes in isolation and as part of the suite.

## Coverage

Coverage is measured with `pytest-cov`.  The current baseline is approximately
92% line coverage on the core library.  The coverage configuration is in
`pyproject.toml` under `[tool.coverage]`.

```bash
pytest -m "not live and not benchmark" --cov=volfoundry --cov-report=html
```

## CI expectations

- PRs must pass `pytest -m "not live and not benchmark"`.
- Live tests run on a schedule (daily) via `.github/workflows/live-integration.yml`.
- Benchmark tests are not run in CI by default — they require optional dependencies.
- The wheel installation smoke test verifies the built artifact installs and imports.

## Fixtures

- Live Deribit fixtures are stored in `data/snapshots/` but not committed in
  large numbers.  Test fixtures are generated from synthetic data.
- The regression suite uses a small committed golden fixture dataset.
- Monte Carlo tests use fixed seeds for reproducibility.