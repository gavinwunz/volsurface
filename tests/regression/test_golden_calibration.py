"""Golden-fixture regression tests for VolFoundry calibration pipeline.

These tests use a deterministic synthetic dataset (flat 30% implied volatility)
and compare calibration outputs against committed golden values to detect
accidental numerical behaviour changes during refactoring.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest

from volfoundry.surface.builder import SurfaceBuilder

_HERE = pathlib.Path(__file__).parent
_FIXTURE_DIR = _HERE / "test_data"
_FIXTURE_FILE = _FIXTURE_DIR / "golden_calibration_fixture.parquet"
_EXPECTED_FILE = _FIXTURE_DIR / "golden_expected.json"


@pytest.fixture(scope="module")
def expected():
    with open(_EXPECTED_FILE) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def quote_df():
    df = pd.read_parquet(_FIXTURE_FILE)
    df["expiry"] = pd.to_datetime(df["expiry"], utc=True)
    return df


class TestGoldenCalibration:
    """SSVI calibration on a known dataset matches committed golden outputs."""

    def test_fixture_loads(self, expected, quote_df):
        assert len(quote_df) == expected["n_quotes"]
        assert quote_df["expiry"].nunique() == expected["n_expiries"]

    def test_eta_matches_golden(self, expected, quote_df):
        result = SurfaceBuilder().fit(quote_df.copy(), validation="report")
        fitted = result.global_diagnostics["eta"]
        target = expected["golden_eta"]
        rel = abs(fitted - target) / max(abs(target), 1e-15)
        assert rel < 2e-4, f"eta {fitted:.6f} != golden {target:.6f} (rel={rel:.2e})"

    def test_lam_matches_golden(self, expected, quote_df):
        result = SurfaceBuilder().fit(quote_df.copy(), validation="report")
        fitted = result.global_diagnostics["lambda"]
        target = expected["golden_lam"]
        assert abs(fitted - target) < 1e-4, f"lam {fitted:.6f} != golden {target:.6f}"

    def test_rho_matches_golden(self, expected, quote_df):
        result = SurfaceBuilder().fit(quote_df.copy(), validation="report")
        fitted = result.global_diagnostics["rho"]
        target = expected["golden_rho"]
        assert abs(fitted - target) < 3e-4, f"rho {fitted:.6f} != golden {target:.6f}"

    def test_calibration_result_is_valid(self, quote_df):
        result = SurfaceBuilder().fit(quote_df.copy(), validation="report")
        assert result.validation.is_valid, (
            f"Expected valid, got: {result.validation.rejection_reasons}"
        )

    def test_reproducible_output(self, quote_df):
        """Repeated calibration with fixed seed is stable to O(~1e-5)."""
        np.random.seed(42)
        r1 = SurfaceBuilder().fit(quote_df.copy(), validation="report")
        np.random.seed(42)
        r2 = SurfaceBuilder().fit(quote_df.copy(), validation="report")
        for k, tol in [("eta", 2e-5), ("lambda", 2e-5), ("rho", 2e-5)]:
            v1 = r1.global_diagnostics[k]
            v2 = r2.global_diagnostics[k]
            assert v1 == pytest.approx(v2, rel=tol), f"{k} not reproducible: {v1} vs {v2}"


def test_regression_fixtures_exist():
    assert _FIXTURE_FILE.exists(), f"Missing fixture: {_FIXTURE_FILE}"
    assert _EXPECTED_FILE.exists(), f"Missing expected file: {_EXPECTED_FILE}"


class TestWheelSmokeInstall:
    """Verify that the built wheel can be installed and core functionality works.

    Uses the current venv (which has volfoundry installed editable) rather than
    rebuilding a wheel, since this test validates the install path.  A separate
    fresh-venv wheel smoke is part of the CI/release workflow.
    """

    def test_package_imports(self):
        import volfoundry

        assert volfoundry.__version__ == "0.1.0"

    def test_core_api_available(self):
        from volfoundry import (
            DeribitClient,
            SurfaceBuilder,
            SurfaceFitResult,
            ValidationReport,
            VolatilitySurface,
        )

        assert DeribitClient is not None
        assert SurfaceBuilder is not None
        assert VolatilitySurface is not None
        assert ValidationReport is not None
        assert SurfaceFitResult is not None

    def test_minimal_pricing(self):
        from volfoundry.iv.black_scholes import (
            OptionType,
            black76_price,
            implied_vol_nr,
        )

        F, K, sigma_d, T, r = 100.0, 100.0, 0.30, 0.50, 0.0
        price = black76_price(F, K, sigma_d, T, r, OptionType.CALL)
        # implied_vol_nr is the direct NR solver (decimal sigma)
        sigma = implied_vol_nr(price, F, K, T, r, OptionType.CALL)
        assert sigma == pytest.approx(0.30, rel=1e-6)
        # Round-trip pricing
        rt_price = black76_price(F, K, sigma, T, r, OptionType.CALL)
        assert rt_price == pytest.approx(price, rel=1e-12)
