"""Tests for the VolFoundry public high-level API (P3 milestone).

Covers:
- VolatilitySurface construction, evaluation, interpolation
- SurfaceBuilder.fit_dataframe() with synthetic data (report + strict)
- Result types and ValidationReport
- Exception hierarchy
- DeribitClient existence (live tests are in test_fetcher.py with @pytest.mark.live)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Imports from new public API
# ---------------------------------------------------------------------------
from volfoundry import (
    OptionChain,
    SurfaceBuilder,
    SurfaceFitResult,
    ValidationReport,
    VolatilitySurface,
)
from volfoundry.exceptions import (
    ArbitrageViolationError,
    CalibrationConvergenceError,
    CalibrationError,
    ConfigurationError,
    DataError,
    ImpliedVolError,
    InvalidSurfaceError,
    MarketDataError,
    PersistenceError,
    PricingError,
    QuoteValidationError,
    VolFoundryError,
)
from volfoundry.surface.ssvi import SsviParams

# ===========================================================================
# VolatilitySurface
# ===========================================================================


class TestVolatilitySurface:
    """Unit tests for the VolatilitySurface callable object."""

    def _make_surface(self) -> VolatilitySurface:
        """Build a simple 3-slice surface with known parameters."""
        theta = np.array([0.04, 0.09, 0.16])  # ATM total variance
        T = np.array([0.1, 0.3, 0.5])  # years
        params = SsviParams(rho=-0.3, eta=1.0, lamb=0.25, theta_grid=theta)
        return VolatilitySurface(params, T, currency="BTC", r=0.0)

    def test_construction(self):
        s = self._make_surface()
        assert s.n_slices == 3
        assert s.currency == "BTC"
        assert s.r == 0.0
        assert s.min_expiry == pytest.approx(0.1)
        assert s.max_expiry == pytest.approx(0.5)

    def test_construction_mismatched_lengths_raises(self):
        params = SsviParams(rho=0.0, eta=1.0, lamb=0.5, theta_grid=np.array([0.04, 0.09]))
        with pytest.raises(ValueError, match="must match"):
            VolatilitySurface(params, np.array([0.1]), currency="X")

    def test_construction_null_theta_grid_raises(self):
        params = SsviParams(rho=0.0, eta=1.0, lamb=0.5, theta_grid=None)
        with pytest.raises(ValueError, match="theta_grid"):
            VolatilitySurface(params, np.array([0.1]))

    def test_iv_atm_no_forward(self):
        """Without a forward, iv() returns ATM sqrt(theta/T)."""
        s = self._make_surface()
        iv = s.iv(strike=100, maturity=0.3)
        # ATM: theta=0.09 at T=0.3 → sigma = sqrt(0.09/0.3) = sqrt(0.3) ≈ 0.5477
        expected = math.sqrt(0.09 / 0.3)
        assert iv == pytest.approx(expected, rel=1e-6)

    def test_iv_with_forward(self):
        """With forward, iv() accounts for moneyness skew."""
        s = self._make_surface()
        iv_atm = s.iv(strike=65000, maturity=0.3, F=65000)
        iv_itm = s.iv(strike=50000, maturity=0.3, F=65000)
        iv_otm = s.iv(strike=80000, maturity=0.3, F=65000)
        # With rho=-0.3, OTM puts (low strikes) should have higher IV than ATM
        assert iv_atm > 0
        assert iv_itm > 0
        assert iv_otm > 0
        # Skew direction: rho < 0 → downward skew → lower strikes higher IV
        assert iv_itm > iv_otm

    def test_iv_positive_strike_required(self):
        s = self._make_surface()
        with pytest.raises(ValueError, match="strike"):
            s.iv(strike=0, maturity=0.3)
        with pytest.raises(ValueError, match="strike"):
            s.iv(strike=-1, maturity=0.3)

    def test_iv_positive_maturity_required(self):
        s = self._make_surface()
        with pytest.raises(ValueError, match="maturity"):
            s.iv(strike=100, maturity=0)
        with pytest.raises(ValueError, match="maturity"):
            s.iv(strike=100, maturity=-0.1)

    def test_total_variance(self):
        s = self._make_surface()
        w = s.total_variance(0.0, 0.3)
        # At k=0, w = theta at ~T=0.3 ≈ interpolated theta
        assert w > 0
        assert np.isfinite(w)

    def test_total_variance_positive_T_required(self):
        s = self._make_surface()
        with pytest.raises(ValueError, match="positive"):
            s.total_variance(0.0, 0.0)

    def test_iv_grid(self):
        s = self._make_surface()
        strikes = np.array([60000, 65000, 70000])
        maturities = np.array([0.1, 0.3])
        ivg = s.iv_grid(strikes, maturities, F=65000)
        assert ivg.shape == (3, 2)
        assert np.all(np.isfinite(ivg))
        assert np.all(ivg > 0)

    def test_interpolation_within_bounds(self):
        s = self._make_surface()
        # T=0.2 is between 0.1 and 0.3 → log-linear interpolation
        iv = s.iv(strike=65000, maturity=0.2, F=65000)
        assert iv > 0
        assert np.isfinite(iv)

    def test_interpolation_below_min_uses_first_theta(self):
        """Below min expiry, theta is held at the first grid value (flat extrapolation)."""
        s = self._make_surface()
        # At T=0.05 (below min=0.1), theta = theta[0] = 0.04
        # So IV = sqrt(0.04 / 0.05) and total_variance = 0.04
        w_below = s.total_variance(0.0, 0.05)
        w_at_min = s.total_variance(0.0, 0.1)
        assert w_below == pytest.approx(w_at_min, rel=1e-6)
        # But IV differs because maturity differs
        iv_below = s.iv(strike=65000, maturity=0.05, F=65000)
        iv_at_min = s.iv(strike=65000, maturity=0.1, F=65000)
        assert iv_below > iv_at_min  # shorter maturity with same theta → higher IV

    def test_interpolation_above_max_uses_last_theta(self):
        """Above max expiry, theta is held at the last grid value (flat extrapolation)."""
        s = self._make_surface()
        w_above = s.total_variance(0.0, 0.8)
        w_at_max = s.total_variance(0.0, 0.5)
        assert w_above == pytest.approx(w_at_max, rel=1e-6)
        # But IV differs because maturity differs
        iv_above = s.iv(strike=65000, maturity=0.8, F=65000)
        iv_at_max = s.iv(strike=65000, maturity=0.5, F=65000)
        assert iv_above < iv_at_max  # longer maturity with same theta → lower IV

    def test_repr(self):
        s = self._make_surface()
        r = repr(s)
        assert "VolatilitySurface" in r
        assert "BTC" in r
        assert "3 slices" in r

    def test_properties_readonly(self):
        s = self._make_surface()
        params = s.params
        assert isinstance(params, SsviParams)
        T = s.expiry_times
        assert len(T) == 3
        # Copies, not views
        T[0] = 999
        assert s.expiry_times[0] == pytest.approx(0.1)


# ===========================================================================
# SurfaceBuilder with synthetic data (offline path)
# ===========================================================================


def _make_synthetic_option_chain(
    F: float = 65000.0,
    n_expiries: int = 4,
    strikes_per_expiry: int = 8,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a realistic synthetic option chain for testing.

    Produces put and call quotes around the forward with a mild skew.
    Uses future expiry dates since today is Aug 2026.
    """
    rng = np.random.default_rng(seed)
    # Use future dates: Sep 2026, Oct 2026, Dec 2026, Mar 2027
    days_from_now = [30, 60, 120, 240]
    pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=30)
    rows = []
    for d_offset in days_from_now[:n_expiries]:
        T = d_offset / 365.25
        expiry_dt = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=d_offset + 1)
        # ATM vol with mild decay over time
        atm_vol = 0.55 - 0.05 * math.log(1 + T)
        # Strikes from 0.7F to 1.3F
        for i in range(strikes_per_expiry):
            strike = F * (0.7 + 0.6 * i / (strikes_per_expiry - 1))
            k = math.log(strike / F)
            # Skew: vol = atm_vol - 0.15 * k (negative skew)
            iv = atm_vol - 0.15 * k + rng.normal(0, 0.005)
            iv = max(iv, 0.01)

            # Approximate Black-76 mid price (r=0 for simplicity)
            import math as _m

            sigma_sqrt_T = iv * _m.sqrt(T)
            d1 = _m.log(F / strike) / sigma_sqrt_T + 0.5 * sigma_sqrt_T

            # norm_cdf via math.erf
            def _cdf(x):
                return 0.5 * (1.0 + _m.erf(x / _m.sqrt(2)))

            # Call price
            call_mid = F * _cdf(d1) - strike * _cdf(d1 - sigma_sqrt_T)
            call_mid = max(call_mid, 0.001)
            # bid-ask spread as a small percentage of mid (0.1%–1%)
            spread_pct = rng.uniform(0.001, 0.01)
            call_bid = call_mid * (1.0 - spread_pct * 0.5)
            call_ask = call_mid * (1.0 + spread_pct * 0.5)

            rows.append(
                {
                    "strike": strike,
                    "expiry": expiry_dt,
                    "option_type": "C",
                    "mid": call_mid,
                    "bid": call_bid,
                    "ask": call_ask,
                    "underlying_price": F + rng.normal(0, 50),
                }
            )

            # Put via put-call parity: P = C + K - F (r=0)
            put_mid = max(call_mid + strike - F, 0.001)  # approximate with r=0
            put_bid = put_mid * 0.995
            put_ask = put_mid * 1.005

            rows.append(
                {
                    "strike": strike,
                    "expiry": expiry_dt,
                    "option_type": "P",
                    "mid": put_mid,
                    "bid": put_bid,
                    "ask": put_ask,
                    "underlying_price": F + rng.normal(0, 50),
                }
            )

    return pd.DataFrame(rows)


class TestSurfaceBuilder:
    """Tests for SurfaceBuilder.fit_dataframe() with synthetic data."""

    @pytest.fixture(autouse=True)
    def _builder(self):
        self.builder = SurfaceBuilder(
            min_quotes_per_slice=4,
            min_expiry_days=2.0,
            k_range=(-3.0, 3.0),
            n_k=201,
        )

    def _make_df(self, **kwargs) -> pd.DataFrame:
        return _make_synthetic_option_chain(**kwargs)

    def test_fit_dataframe_report_mode(self):
        """Fit a surface in report mode with synthetic data."""
        df = self._make_df(n_expiries=3)
        result = self.builder.fit_dataframe(df, validation="report")
        assert isinstance(result, SurfaceFitResult)
        assert result.surface is not None
        assert isinstance(result.surface, VolatilitySurface)
        assert isinstance(result.validation, ValidationReport)
        assert result.calibration_status in ("converged", "converged_invalid")
        assert result.surface.n_slices > 0

    def test_fit_dataframe_strict_mode(self):
        """Fit in strict mode — should raise if invalid, return if valid."""
        df = self._make_df(n_expiries=3, strikes_per_expiry=10)
        result = self.builder.fit_dataframe(df, validation="strict")
        assert result.calibration_status in ("converged", "converged_invalid")
        # The surface should exist regardless
        assert result.surface is not None

    def test_fit_dataframe_validation_report_structure(self):
        df = self._make_df(n_expiries=3)
        result = self.builder.fit_dataframe(df, validation="report")
        vr = result.validation
        assert isinstance(vr.is_valid, bool)
        assert "k_min" in vr.evaluation_domain or len(vr.evaluation_domain) >= 1
        assert vr.per_slice is not None

    def test_fit_dataframe_returns_cleaning_stats(self):
        df = self._make_df()
        result = self.builder.fit_dataframe(df, validation="report")
        stats = result.quote_cleaning_stats
        assert "raw" in stats
        assert "retained" in stats
        assert stats["retained"] <= stats["raw"]

    def test_fit_dataframe_returns_per_expiry_diagnostics(self):
        df = self._make_df(n_expiries=3)
        result = self.builder.fit_dataframe(df, validation="report")
        diag = result.per_expiry_diagnostics
        assert len(diag) > 0
        for d in diag:
            assert "slice_id" in d
            assert "T" in d
            assert "svi_rmse" in d
            assert "n_points" in d

    def test_fit_dataframe_returns_global_diagnostics(self):
        df = self._make_df(n_expiries=3)
        result = self.builder.fit_dataframe(df, validation="report")
        gd = result.global_diagnostics
        assert "rho" in gd
        assert "eta" in gd
        assert "lambda" in gd
        assert "rmse" in gd
        assert "r2" in gd

    def test_fit_dataframe_theta_arrays(self):
        df = self._make_df(n_expiries=3)
        result = self.builder.fit_dataframe(df, validation="report")
        assert result.theta_raw is not None
        assert result.theta_adjusted is not None
        assert len(result.theta_raw) >= 1
        assert np.all(result.theta_raw > 0)

    def test_fit_dataframe_empty_raises(self):
        builder = SurfaceBuilder()
        with pytest.raises(ValueError, match="empty|No quotes"):
            builder.fit_dataframe(pd.DataFrame())

    def test_fit_dataframe_too_few_quotes_raises(self):
        builder = SurfaceBuilder(min_quotes_per_slice=1000)
        df = self._make_df(n_expiries=1)
        with pytest.raises(ValueError, match="valid expiry"):
            builder.fit_dataframe(df, validation="report")

    def test_fit_with_option_chain(self):
        df = self._make_df(n_expiries=3)
        chain = OptionChain(
            currency="BTC",
            timestamp=pd.Timestamp.now(tz="UTC"),
            source="test",
            quotes=df,
        )
        result = self.builder.fit(chain, validation="report")
        assert isinstance(result, SurfaceFitResult)
        assert result.surface is not None

    def test_fit_with_unknown_type_raises(self):
        with pytest.raises(TypeError, match="Snapshot, OptionChain, or DataFrame"):
            self.builder.fit([1, 2, 3])

    def test_surface_iv_after_fit(self):
        df = self._make_df(n_expiries=3, strikes_per_expiry=10)
        result = self.builder.fit_dataframe(df, validation="report")
        iv = result.surface.iv(strike=65000, maturity=0.2, F=65000)
        assert iv > 0
        assert np.isfinite(iv)

    def test_workflow_under_15_lines(self):
        """Verify the main workflow is achievable in < 15 lines."""
        df = _make_synthetic_option_chain(n_expiries=3)
        builder = SurfaceBuilder()
        result = builder.fit_dataframe(df, validation="report")

        assert result.calibration_status in (
            "converged",
            "converged_invalid",
            "did_not_converge",
        )
        iv = result.surface.iv(strike=65000, maturity=30 / 365.25)
        assert iv > 0
        is_valid = result.validation.is_valid
        assert isinstance(is_valid, bool)


# ===========================================================================
# Exception hierarchy
# ===========================================================================


class TestExceptionHierarchy:
    """Verify exception class relationships."""

    def test_all_exceptions_inherit_from_volfoundry_error(self):
        for cls in [
            DataError,
            MarketDataError,
            QuoteValidationError,
            PersistenceError,
            PricingError,
            ImpliedVolError,
            CalibrationError,
            CalibrationConvergenceError,
            InvalidSurfaceError,
            ArbitrageViolationError,
            ConfigurationError,
        ]:
            assert issubclass(cls, VolFoundryError), f"{cls} must inherit from VolFoundryError"

    def test_arbitrage_violation_is_invalid_surface(self):
        assert issubclass(ArbitrageViolationError, InvalidSurfaceError)

    def test_data_exceptions_inherit_correctly(self):
        assert issubclass(MarketDataError, DataError)
        assert issubclass(PersistenceError, DataError)
        assert issubclass(QuoteValidationError, DataError)

    def test_calibration_exceptions_inherit_correctly(self):
        assert issubclass(CalibrationConvergenceError, CalibrationError)
        assert issubclass(InvalidSurfaceError, CalibrationError)

    def test_pricing_exceptions_inherit_correctly(self):
        assert issubclass(ImpliedVolError, PricingError)

    def test_arbitrage_violation_error_message(self):
        err = ArbitrageViolationError("Surface failed: butterfly negative")
        assert "butterfly" in str(err)

    def test_exception_cause_chaining(self):
        try:
            try:
                raise ValueError("inner")
            except ValueError as e:
                raise MarketDataError("outer") from e
        except MarketDataError as outer:
            assert isinstance(outer.__cause__, ValueError)
            assert "inner" in str(outer.__cause__)


# ===========================================================================
# OptionChain and result types
# ===========================================================================


class TestOptionChain:
    def test_default_construction(self):
        ts = pd.Timestamp.now(tz="UTC")
        chain = OptionChain(currency="BTC", timestamp=ts, source="test")
        assert chain.currency == "BTC"
        assert chain.source == "test"
        assert chain.schema_version == 1
        assert chain.quotes.empty

    def test_with_dataframe(self):
        df = pd.DataFrame({"strike": [50000], "expiry": [pd.Timestamp("2026-03-01", tz="UTC")]})
        ts = pd.Timestamp.now(tz="UTC")
        chain = OptionChain(currency="ETH", timestamp=ts, source="parquet", quotes=df)
        assert len(chain.quotes) == 1


class TestValidationReport:
    def test_defaults(self):
        vr = ValidationReport()
        assert vr.is_valid is False
        assert vr.butterfly_passed is None
        assert vr.calendar_passed is None
        assert vr.density_passed is None

    def test_valid_report(self):
        vr = ValidationReport(
            is_valid=True,
            butterfly_passed=True,
            calendar_passed=True,
            density_passed=True,
            evaluation_domain={"k_min": -3.0, "k_max": 3.0, "n_k": 501},
            tolerances={"butterfly_tol": -1e-12},
            per_slice=[{"slice_id": "2026-01-01", "T": 0.25, "butterfly_passed": True}],
        )
        assert vr.is_valid
        assert vr.evaluation_domain["k_min"] == -3.0
        assert len(vr.per_slice) == 1

    def test_invalid_report_with_rejected_slices(self):
        vr = ValidationReport(
            is_valid=False,
            rejected_slices=["slice_A"],
            rejection_reasons={"slice_A": ["butterfly (min g=-5.1234e-03)"]},
            warnings=["optimizer did not converge"],
        )
        assert not vr.is_valid
        assert "slice_A" in vr.rejected_slices
        assert len(vr.warnings) == 1


class TestSurfaceFitResult:
    def test_minimal_construction(self):
        sfr = SurfaceFitResult()
        assert sfr.calibration_status == "failed"
        assert sfr.surface is None

    def test_successful_result(self):
        sfr = SurfaceFitResult(
            calibration_status="converged",
            quote_cleaning_stats={"raw": 100, "retained": 80},
            optimizer_diagnostics={"success": True, "message": "converged"},
            global_diagnostics={"rho": -0.3, "eta": 1.0, "rmse": 0.001},
            theta_raw=np.array([0.04, 0.09]),
            theta_adjusted=np.array([0.04, 0.09]),
        )
        assert sfr.calibration_status == "converged"
        assert sfr.quote_cleaning_stats["retained"] == 80
        assert sfr.theta_raw is not None
        assert len(sfr.theta_raw) == 2


# ===========================================================================
# SurfaceBuilder edge cases
# ===========================================================================


class TestSurfaceBuilderEdgeCases:
    """Edge cases and error paths for SurfaceBuilder."""

    def test_single_slice_dataframe(self):
        """Single expiry slice should still produce a surface."""
        df = _make_synthetic_option_chain(n_expiries=1, strikes_per_expiry=8)
        builder = SurfaceBuilder(min_quotes_per_slice=4)
        result = builder.fit_dataframe(df, validation="report")
        assert isinstance(result, SurfaceFitResult)
        assert result.surface is not None

    def test_fixed_rho(self):
        """Passing a fixed rho should be respected."""
        df = _make_synthetic_option_chain(n_expiries=3, strikes_per_expiry=10)
        builder = SurfaceBuilder()
        result = builder.fit_dataframe(df, validation="report", rho=-0.5)
        assert result.global_diagnostics["rho"] == pytest.approx(-0.5)

    def test_warnings_propagated(self):
        df = _make_synthetic_option_chain(n_expiries=2, strikes_per_expiry=5)
        builder = SurfaceBuilder()
        result = builder.fit_dataframe(df, validation="report")
        # Warnings may be empty if everything is fine
        assert isinstance(result.warnings, list)

    def test_source_metadata_in_result(self):
        df = _make_synthetic_option_chain(n_expiries=2)
        builder = SurfaceBuilder()
        result = builder.fit_dataframe(df, validation="report")
        assert "source" in result.source_snapshot
        assert result.source_snapshot["source"] == "dataframe"
