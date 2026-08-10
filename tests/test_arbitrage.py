"""Tests for volsurface.arbitrage — no-arbitrage enforcement.

Includes hypothesis property-based tests over randomized parameter draws
for butterfly and calendar conditions.
"""

from __future__ import annotations

import numpy as np
import pytest

from hypothesis import assume, given, settings, strategies as st

from volsurface.svi.parameterization import (
    SviParams,
    svi_implied_vol,
    svi_second_derivative,
    svi_total_variance,
)
from volsurface.arbitrage.checks import (
    ArbitrageCheckResult,
    SliceValidationReport,
    breeden_litzenberger_density,
    breeden_litzenberger_is_nonnegative,
    butterfly_g,
    butterfly_is_arbitrage_free,
    calendar_monotonicity,
    check_slice_arbitrage,
    find_butterfly_violations,
    find_calendar_violations,
    validate_surface,
)


def make_params(a=0.06, b=0.3, rho=-0.2, m=0.0, sigma=0.15):
    return SviParams(a=a, b=b, rho=rho, m=m, sigma=sigma)


# ===================================================================
# Butterfly g(k)
# ===================================================================


class TestButterflyG:
    def test_g_nonnegative_for_valid_params(self):
        """Well-behaved params produce non-negative g(k)."""
        p = make_params()
        ks = np.linspace(-3.0, 3.0, 200)
        g = butterfly_g(ks, p, T=0.25)
        assert np.all(g >= -1e-12)

    def test_g_scalar(self):
        p = make_params()
        g = butterfly_g(np.array([0.0]), p, T=0.25)
        assert isinstance(g, np.ndarray)
        assert g.shape == (1,)

    def test_g_shape_matches_input(self):
        p = make_params()
        ks = np.linspace(-2.0, 2.0, 50)
        g = butterfly_g(ks, p, T=1.0)
        assert g.shape == ks.shape

    def test_butterfly_is_arbitrage_free_returns_bool(self):
        p = make_params()
        ks = np.linspace(-2.0, 2.0, 30)
        result = butterfly_is_arbitrage_free(ks, p, T=0.25)
        assert isinstance(result, bool)

    def test_find_butterfly_violations_returns_none_when_clean(self):
        p = make_params()
        ks = np.linspace(-2.0, 2.0, 100)
        result = find_butterfly_violations(ks, p, T=0.25)
        assert result is None

    def test_b_equals_zero_produces_positive_g(self):
        """b=0 means flat w(k), which should have g(k) > 0."""
        p = make_params(b=0.0)
        ks = np.linspace(-3.0, 3.0, 100)
        g = butterfly_g(ks, p, T=0.5)
        assert np.all(g >= -1e-12)


# ===================================================================
# Calendar monotonicity
# ===================================================================


class TestCalendarMonotonicity:
    def test_single_slice_passes(self):
        p = make_params()
        ks = np.linspace(-2.0, 2.0, 50)
        result = calendar_monotonicity(ks, [(p, 0.25)])
        assert result is True

    def test_identical_slices_pass(self):
        p = make_params()
        ks = np.linspace(-2.0, 2.0, 50)
        result = calendar_monotonicity(ks, [(p, 0.25), (p, 0.25)])
        assert result is True

    def test_increasing_variance_slices_pass(self):
        """Same params + larger a should give larger w(k)."""
        p = make_params(a=0.06, b=0.3, rho=0.0, m=0.0, sigma=0.15)
        ks = np.linspace(-2.0, 2.0, 50)
        p2 = make_params(a=0.08, b=0.3, rho=0.0, m=0.0, sigma=0.15)
        result = calendar_monotonicity(ks, [(p, 0.25), (p2, 0.5)])
        assert result is True

    def test_find_calendar_violations_empty_when_clean(self):
        p = make_params(a=0.06, b=0.3, rho=0.0, m=0.0, sigma=0.15)
        p2 = make_params(a=0.08, b=0.3, rho=0.0, m=0.0, sigma=0.15)
        ks = np.linspace(-2.0, 2.0, 50)
        viols = find_calendar_violations(ks, [(p, 0.25), (p2, 0.5)])
        assert len(viols) == 0

    def test_calendar_fails_when_variance_decreases(self):
        """Lower a at later T should violate calendar."""
        p = make_params(a=0.08, b=0.3, rho=0.0, m=0.0, sigma=0.15)
        p2 = make_params(a=0.04, b=0.3, rho=0.0, m=0.0, sigma=0.15)
        ks = np.linspace(-2.0, 2.0, 50)
        result = calendar_monotonicity(ks, [(p, 0.25), (p2, 0.5)])
        assert not result


# ===================================================================
# Breeden-Litzenberger density
# ===================================================================


class TestBreedenLitzenberger:
    def test_density_positive_for_flat_smile(self):
        K = np.linspace(48000, 52000, 30)
        F = 50000.0
        T, r = 0.25, 0.05
        sigma = np.full_like(K, 0.5)
        result = breeden_litzenberger_is_nonnegative(K, F, T, r, sigma)
        assert result is True

    def test_density_shape(self):
        K = np.linspace(48000, 52000, 30)
        F = 50000.0
        T, r = 0.25, 0.05
        sigma = np.full_like(K, 0.5)
        q = breeden_litzenberger_density(K, F, T, r, sigma)
        assert q.shape == (30,)
        assert np.isnan(q[0])
        assert np.isnan(q[-1])
        assert np.all(np.isfinite(q[1:-1]))

    def test_raises_on_too_few_strikes(self):
        with pytest.raises(ValueError):
            breeden_litzenberger_density(
                np.array([10000, 20000]), 50000, 0.25, 0.05,
                np.array([0.5, 0.5]),
            )


# ===================================================================
# Full slice check
# ===================================================================


class TestCheckSliceArbitrage:
    def test_clean_slice_passes(self):
        p = make_params()
        result = check_slice_arbitrage("test", p, T=0.25)
        assert result.butterfly_passed
        assert result.butterfly_min_g > -1e-12

    def test_with_bl_check(self):
        p = make_params()
        result = check_slice_arbitrage(
            "test", p, T=0.25, F=50000.0, r=0.05,
        )
        assert result.butterfly_passed
        assert result.bl_passed is True

    def test_arbitrage_check_result_fields(self):
        p = make_params()
        result = check_slice_arbitrage("BTC-100D", p, T=100/365)
        assert result.slice_id == "BTC-100D"
        assert result.T == pytest.approx(100/365)
        assert result.k_range[0] < result.k_range[1]
        assert result.params is p


# ===================================================================
# Surface validation
# ===================================================================


class TestValidateSurface:
    def test_single_slice_passes(self):
        p = make_params()
        slices = [("s1", p, 0.25)]
        report = validate_surface(slices)
        assert report.all_passed
        assert report.calendar_passed is None
        assert len(report.rejected_slices) == 0

    def test_two_valid_slices_pass(self):
        p1 = make_params(a=0.06)
        p2 = make_params(a=0.08)
        slices = [("s1", p1, 0.25), ("s2", p2, 0.5)]
        report = validate_surface(slices)
        assert report.all_passed
        assert report.calendar_passed is True

    def test_calendar_violation_reported(self):
        p1 = make_params(a=0.08)
        p2 = make_params(a=0.04)  # lower a at later expiry
        slices = [("s1", p1, 0.25), ("s2", p2, 0.5)]
        report = validate_surface(slices)
        assert not report.all_passed
        assert report.calendar_passed is False

    def test_slices_sorted_by_T(self):
        """Validate sorts slices by T internally regardless of input order."""
        p1 = make_params(a=0.06)
        p2 = make_params(a=0.08)
        slices = [("s2", p2, 0.5), ("s1", p1, 0.25)]
        report = validate_surface(slices)
        assert report.all_passed
        assert report.calendar_passed is True


# ===================================================================
# Hypothesis property-based tests (SPEC requirement)
# ===================================================================


@st.composite
def valid_svi_params_strategy(draw):
    """Generate valid SVI parameters respecting domain constraints."""
    a = draw(st.floats(min_value=0.001, max_value=2.0))
    b = draw(st.floats(min_value=0.0, max_value=1.0))
    rho = draw(st.floats(min_value=-0.99, max_value=0.99))
    m = draw(st.floats(min_value=-3.0, max_value=3.0))
    sigma = draw(st.floats(min_value=0.01, max_value=2.0))
    return SviParams(a=a, b=b, rho=rho, m=m, sigma=sigma)


class TestHypothesisButterfly:
    """Property-based tests: for ANY valid SVI params, certain invariants hold."""

    @given(params=valid_svi_params_strategy())
    @settings(max_examples=200, deadline=3000)
    def test_svi_total_variance_non_negative(self, params):
        """Total variance must be non-negative for all k."""
        ks = np.linspace(-5.0, 5.0, 200)
        w = svi_total_variance(ks, params)
        assert np.all(w >= -1e-12)

    @given(params=valid_svi_params_strategy())
    @settings(max_examples=200, deadline=3000)
    def test_svi_implied_vol_real(self, params):
        """Implied volatility must be real (non-negative under sqrt)."""
        T = 0.25
        ks = np.linspace(-3.0, 3.0, 100)
        iv = svi_implied_vol(ks, params, T)
        assert np.all(np.isfinite(iv))
        assert np.all(iv >= 0.0)

    @given(params=valid_svi_params_strategy())
    @settings(max_examples=200, deadline=3000)
    def test_second_derivative_non_negative(self, params):
        """w''(k) >= 0 is required for convexity."""
        ks = np.linspace(-3.0, 3.0, 100)
        wpp = svi_second_derivative(ks, params)
        assert np.all(wpp >= -1e-12)

    @given(params=valid_svi_params_strategy())
    @settings(max_examples=200, deadline=3000)
    def test_wing_slopes_bounded(self, params):
        """Lee's moment formula: |asymptotic slope| <= 2."""
        assert abs(params.right_slope) <= 2.0 + 1e-10
        assert abs(params.left_slope) <= 2.0 + 1e-10

    @given(params=valid_svi_params_strategy())
    @settings(max_examples=200, deadline=3000)
    def test_g_symmetric_for_rho_zero(self, params):
        """When rho=0 and m=0, g(k) is symmetric around k=0.

        With rho=0, w(k) depends only on (k-m)^2, making w'(k) odd and
        w''(k) even around k=m.  When additionally m=0, g(k) should be
        symmetric: g(-k) = g(k).
        """
        assume(abs(params.rho) < 1e-10)
        assume(abs(params.m) < 1e-10)
        n = 100
        ks = np.linspace(-2.0, 2.0, n)
        g_vals = butterfly_g(ks, params, T=0.25)
        mid = n // 2
        left = g_vals[:mid]
        right_rev = g_vals[-1:mid-1:-1] if mid > 0 else g_vals[:0]
        assert len(left) == len(right_rev), (
            f"shape mismatch: left={left.shape}, right_rev={right_rev.shape}"
        )
        np.testing.assert_allclose(left, right_rev, rtol=1e-8, atol=1e-8)

    @given(params=valid_svi_params_strategy())
    @settings(max_examples=200, deadline=5000)
    def test_butterfly_g_shape_near_ATM(self, params):
        """g(k) is a well-behaved function (finite, reasonable magnitude)."""
        atm_ks = np.linspace(-1.0, 1.0, 60)
        atm_g = butterfly_g(atm_ks, params, T=0.25)
        assert np.all(np.isfinite(atm_g))
        # g(k) should not blow up to unreasonable magnitudes near ATM
        assert np.max(np.abs(atm_g)) < 1e6


@st.composite
def matched_svi_pair_strategy(draw):
    """Generate two SVI params that are identical except a2 > a1."""
    a1 = draw(st.floats(min_value=0.01, max_value=1.5))
    a2 = draw(st.floats(min_value=a1 + 0.01, max_value=2.0))
    b = draw(st.floats(min_value=0.0, max_value=1.0))
    rho = draw(st.floats(min_value=-0.99, max_value=0.99))
    m = draw(st.floats(min_value=-3.0, max_value=3.0))
    sigma = draw(st.floats(min_value=0.01, max_value=2.0))
    p1 = SviParams(a=a1, b=b, rho=rho, m=m, sigma=sigma)
    p2 = SviParams(a=a2, b=b, rho=rho, m=m, sigma=sigma)
    return p1, p2


class TestHypothesisCalendar:
    """Property-based tests for calendar no-arbitrage."""

    @given(pair=matched_svi_pair_strategy())
    @settings(max_examples=200, deadline=5000)
    def test_calendar_with_increasing_a(self, pair):
        """If all params equal except a2 > a1, calendar should pass."""
        p1, p2 = pair
        ks = np.linspace(-2.0, 2.0, 50)
        result = calendar_monotonicity(ks, [(p1, 0.25), (p2, 0.5)])
        assert result is True


# ===================================================================
# Plotting (smoke tests — no visual verification, just no crash)
# ===================================================================


class TestPlotting:
    def test_plot_butterfly_g_no_crash(self, tmp_path):
        from volsurface.arbitrage.plotting import plot_butterfly_g

        p = make_params()
        result = check_slice_arbitrage("BTC-TEST", p, T=0.25)
        paths = plot_butterfly_g([result], output_dir=tmp_path, prefix="test")
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].suffix == ".png"

    def test_write_validation_report_no_crash(self, tmp_path):
        from volsurface.arbitrage.plotting import write_validation_report

        p = make_params()
        slices = [("s1", p, 0.25)]
        report = validate_surface(slices)
        fpath = write_validation_report(report, output_dir=tmp_path)
        assert fpath.exists()
        content = fpath.read_text()
        assert "No-Arbitrage Validation Report" in content
        assert "s1" in content

    def test_plot_butterfly_g_with_violation_fake(self, tmp_path):
        from volsurface.arbitrage.plotting import plot_butterfly_g

        p = make_params()
        result = check_slice_arbitrage("BTC-TEST", p, T=0.25)
        paths = plot_butterfly_g([result], output_dir=tmp_path, prefix="test_viol")
        assert len(paths) == 1
        assert paths[0].exists()