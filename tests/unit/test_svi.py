"""Tests for volfoundry.svi — SVI parameterization and calibration."""

from __future__ import annotations

import numpy as np
import pytest

from volfoundry.svi.parameterization import (
    SviParams,
    clip_params_to_valid,
    svi_first_derivative,
    svi_implied_vol,
    svi_min_total_variance,
    svi_second_derivative,
    svi_total_variance,
)
from volfoundry.svi.calibration import (
    build_inverse_spread_weights,
    build_vega_weights,
    calibrate_svi_slice,
    _inner_lls,
    _outer_objective,
)


def make_valid_params(**overrides) -> SviParams:
    defaults = dict(a=0.04, b=0.4, rho=-0.2, m=0.05, sigma=0.15)
    defaults.update(overrides)
    return SviParams(**defaults)


# ===================================================================
# SviParams
# ===================================================================


class TestSviParams:
    def test_valid_construction(self):
        p = SviParams(a=0.04, b=0.4, rho=-0.2, m=0.0, sigma=0.1)
        assert p.a == 0.04

    def test_negative_a_raises(self):
        with pytest.raises(ValueError, match="a must be positive"):
            SviParams(a=-0.01, b=0.1, rho=0.0, m=0.0, sigma=0.1)

    def test_zero_a_raises(self):
        with pytest.raises(ValueError, match="a must be positive"):
            SviParams(a=0.0, b=0.1, rho=0.0, m=0.0, sigma=0.1)

    def test_negative_b_raises(self):
        with pytest.raises(ValueError, match="b must be non-negative"):
            SviParams(a=0.04, b=-0.1, rho=0.0, m=0.0, sigma=0.1)

    def test_rho_out_of_bounds_raises(self):
        with pytest.raises(ValueError, match="rho must be in"):
            SviParams(a=0.04, b=0.1, rho=1.5, m=0.0, sigma=0.1)
        with pytest.raises(ValueError, match="rho must be in"):
            SviParams(a=0.04, b=0.1, rho=-1.0, m=0.0, sigma=0.1)

    def test_zero_sigma_raises(self):
        with pytest.raises(ValueError, match="sigma must be positive"):
            SviParams(a=0.04, b=0.1, rho=0.0, m=0.0, sigma=0.0)

    def test_right_slope(self):
        p = SviParams(a=0.04, b=0.5, rho=0.3, m=0.0, sigma=0.1)
        assert abs(p.right_slope - 0.65) < 1e-12

    def test_left_slope(self):
        p = SviParams(a=0.04, b=0.5, rho=0.3, m=0.0, sigma=0.1)
        assert abs(p.left_slope - (-0.35)) < 1e-12

    def test_satisfies_lee(self):
        p = SviParams(a=0.04, b=1.0, rho=0.5, m=0.0, sigma=0.1)
        assert p.satisfies_lee_moment_formula()
        p2 = SviParams(a=0.04, b=1.5, rho=0.5, m=0.0, sigma=0.1)
        assert not p2.satisfies_lee_moment_formula()
        p3 = SviParams(a=0.04, b=1.0, rho=-0.5, m=0.0, sigma=0.1)
        assert p3.satisfies_lee_moment_formula()


# ===================================================================
# svi_total_variance
# ===================================================================


class TestSviTotalVariance:
    def test_at_k_equals_m(self):
        p = make_valid_params(m=0.1)
        w = svi_total_variance(0.1, p)
        expected = p.a + p.b * p.sigma
        assert abs(w - expected) < 1e-12

    def test_scalar_input(self):
        p = make_valid_params()
        w = svi_total_variance(0.0, p)
        assert isinstance(w, (float, np.floating))

    def test_array_input(self):
        p = make_valid_params()
        ks = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
        w = svi_total_variance(ks, p)
        assert w.shape == (5,)
        assert np.all(np.isfinite(w))
        assert np.all(w > 0)

    def test_non_negative(self):
        p = make_valid_params(a=0.01, b=0.8, sigma=0.1, rho=-0.9)
        ks = np.linspace(-5.0, 5.0, 200)
        w = svi_total_variance(ks, p)
        assert np.all(w >= -1e-12)

    def test_known_values(self):
        p = SviParams(a=0.1, b=0.2, rho=0.0, m=0.0, sigma=0.3)
        w = svi_total_variance(0.0, p)
        assert abs(w - 0.16) < 1e-12
        w2 = svi_total_variance(0.4, p)
        assert abs(w2 - 0.2) < 1e-12


# ===================================================================
# svi_implied_vol
# ===================================================================


class TestSviImpliedVol:
    def test_at_T_one(self):
        p = make_valid_params()
        ks = np.linspace(-1.0, 1.0, 11)
        iv = svi_implied_vol(ks, p, T=1.0)
        w = svi_total_variance(ks, p)
        np.testing.assert_allclose(iv**2, w)

    def test_T_dependence(self):
        p = make_valid_params()
        iv_short = svi_implied_vol(0.0, p, T=0.25)
        iv_long = svi_implied_vol(0.0, p, T=1.0)
        assert iv_short > iv_long

    def test_nonpositive_T_raises(self):
        with pytest.raises(ValueError):
            svi_implied_vol(0.0, make_valid_params(), T=0.0)


# ===================================================================
# Derivatives
# ===================================================================


class TestSviDerivatives:
    def test_first_derivative_at_m(self):
        p = make_valid_params(m=0.1, rho=-0.3, b=0.5)
        wp = svi_first_derivative(0.1, p)
        assert abs(wp - p.b * p.rho) < 1e-12

    def test_first_derivative_scalar_and_array(self):
        p = make_valid_params()
        wp_scalar = svi_first_derivative(0.0, p)
        assert isinstance(wp_scalar, (float, np.floating))
        ks = np.array([-1.0, 0.0, 1.0])
        wp_arr = svi_first_derivative(ks, p)
        assert wp_arr.shape == (3,)

    def test_second_derivative_positive(self):
        p = make_valid_params()
        ks = np.linspace(-3.0, 3.0, 100)
        wpp = svi_second_derivative(ks, p)
        assert np.all(wpp >= 0)

    def test_second_derivative_decays(self):
        p = make_valid_params()
        wpp_near = svi_second_derivative(0.0, p)
        wpp_far = svi_second_derivative(10.0, p)
        assert wpp_far < wpp_near
        # Should be very small at large |k|
        assert wpp_far < 1e-4

    def test_wpp_max_at_k_equals_m(self):
        """w''(k) has its maximum at k = m, with value b / sigma."""
        p = make_valid_params(b=0.4, sigma=0.2, m=0.1)
        # Sample closely around m so we capture the true peak
        ks = np.linspace(p.m - 0.02, p.m + 0.02, 200)
        wpp = svi_second_derivative(ks, p)
        expected_max = p.b / p.sigma
        assert abs(np.max(wpp) - expected_max) < 1e-6


# ===================================================================
# svi_min_total_variance
# ===================================================================


class TestSviMinTotalVariance:
    def test_known_formula(self):
        p = SviParams(a=0.05, b=0.3, rho=0.0, m=0.0, sigma=0.2)
        w_min = svi_min_total_variance(p)
        expected = 0.05 + 0.3 * 0.2 * 1.0
        assert abs(w_min - expected) < 1e-12

    def test_rho_dependence(self):
        p1 = SviParams(a=0.05, b=0.3, rho=0.0, m=0.0, sigma=0.2)
        p2 = SviParams(a=0.05, b=0.3, rho=0.8, m=0.0, sigma=0.2)
        assert svi_min_total_variance(p2) < svi_min_total_variance(p1)


# ===================================================================
# clip_params_to_valid
# ===================================================================


class TestClipParamsToValid:
    def test_valid_params_unchanged(self):
        p = make_valid_params()
        clipped = clip_params_to_valid(p)
        assert clipped.a == p.a
        assert clipped.b == p.b
        assert clipped.rho == p.rho
        assert clipped.sigma == p.sigma

    def test_clips_negative(self):
        # We cannot construct SviParams with negative values, so patch attributes
        p = make_valid_params()
        # Manually set invalid values on the dataclass (bypass validation)
        object.__setattr__(p, 'a', -1.0)
        object.__setattr__(p, 'b', -1.0)
        object.__setattr__(p, 'rho', -10.0)
        object.__setattr__(p, 'sigma', 0.0)
        clipped = clip_params_to_valid(p)
        assert clipped.a >= 1e-12
        assert clipped.b >= 0.0
        assert clipped.rho == -0.999
        assert clipped.sigma >= 1e-12

    def test_clips_rho_upper(self):
        p = make_valid_params()
        object.__setattr__(p, 'rho', 5.0)
        clipped = clip_params_to_valid(p)
        assert clipped.rho == 0.999


# ===================================================================
# Inner linear least squares
# ===================================================================


class TestInnerLLS:
    def test_exact_recovery(self):
        true = make_valid_params(m=0.1, sigma=0.2)
        ks = np.linspace(-1.5, 1.5, 30)
        w_true = svi_total_variance(ks, true)
        params, obj = _inner_lls(ks, w_true, np.ones_like(ks), m=0.1, sigma=0.2)
        assert params is not None
        assert abs(params.a - true.a) < 1e-10
        assert abs(params.b - true.b) < 1e-10
        assert abs(params.rho - true.rho) < 1e-10
        assert obj < 1e-20

    def test_handles_noise(self):
        true = make_valid_params()
        ks = np.linspace(-2.0, 2.0, 50)
        w_true = svi_total_variance(ks, true)
        rng = np.random.RandomState(123)
        noise = rng.normal(0, 0.001, len(ks))
        w_obs = w_true + noise
        params, obj = _inner_lls(ks, w_obs, np.ones_like(ks), m=true.m, sigma=true.sigma)
        assert params is not None
        assert params.a > 0
        assert params.b > 0
        assert abs(params.rho) < 1.0
        assert obj > 0

    def test_rho_constraint_enforced(self):
        ks = np.array([-0.5, 0.0, 0.5, 1.0])
        w_obs = np.array([0.05, 0.03, 0.02, 0.01])
        params, _ = _inner_lls(ks, w_obs, np.ones(4), m=0.0, sigma=0.1)
        assert params is not None
        assert abs(params.rho) < 1.0


# ===================================================================
# Outer objective
# ===================================================================


class TestOuterObjective:
    def test_returns_finite_float(self):
        p = make_valid_params()
        ks = np.linspace(-1.5, 1.5, 30)
        w = svi_total_variance(ks, p)
        obj = _outer_objective(np.array([p.m, p.sigma]), ks, w, np.ones_like(ks))
        assert isinstance(obj, float)
        assert np.isfinite(obj)

    def test_objective_zero_at_true_params(self):
        p = make_valid_params()
        ks = np.linspace(-1.5, 1.5, 30)
        w = svi_total_variance(ks, p)
        obj = _outer_objective(np.array([p.m, p.sigma]), ks, w, np.ones_like(ks))
        assert obj < 1e-20


# ===================================================================
# Full calibration
# ===================================================================


class TestCalibrateSviSlice:
    def test_exact_data_no_noise(self):
        true = make_valid_params(a=0.04, b=0.4, rho=-0.2, m=0.05, sigma=0.15)
        ks = np.linspace(-1.5, 1.5, 50)
        w_true = svi_total_variance(ks, true)
        result = calibrate_svi_slice(ks, w_true, T=0.25)
        assert result.outer_success
        assert result.r2 > 0.999
        assert result.rmse < 0.01
        assert abs(result.params.a - true.a) < 0.02
        assert abs(result.params.b - true.b) < 0.05
        assert abs(result.params.rho - true.rho) < 0.05
        assert abs(result.params.m - true.m) < 0.05

    def test_noisy_data(self):
        true = make_valid_params()
        ks = np.linspace(-2.0, 2.0, 60)
        w_true = svi_total_variance(ks, true)
        rng = np.random.RandomState(42)
        noise = rng.normal(0, 0.005, len(ks))
        w_obs = w_true + noise
        result = calibrate_svi_slice(ks, w_obs, T=0.25)
        assert result.outer_success
        assert result.r2 > 0.9
        assert result.rmse < 0.05
        assert result.params.a > 0
        assert result.params.b > 0
        assert abs(result.params.rho) < 1.0

    def test_flat_smile(self):
        ks = np.linspace(-1.0, 1.0, 30)
        w_flat = np.full_like(ks, 0.04)
        result = calibrate_svi_slice(ks, w_flat, T=0.25)
        # Flat data is degenerate (no variance to explain); R² may be low.
        # The calibration should still return an outer_success and valid params.
        assert result.outer_success
        assert result.params.a > 0

    def test_skewed_smile(self):
        true = make_valid_params(a=0.05, b=0.5, rho=-0.7, m=0.05, sigma=0.2)
        ks = np.linspace(-2.0, 2.0, 60)
        w_true = svi_total_variance(ks, true)
        rng = np.random.RandomState(7)
        noise = rng.normal(0, 0.0005, len(ks))
        w_obs = w_true + noise
        result = calibrate_svi_slice(ks, w_obs, T=0.25)
        assert result.outer_success
        assert result.params.rho < -0.3

    def test_with_vega_weights(self):
        true = make_valid_params()
        ks = np.linspace(-1.5, 1.5, 40)
        w_true = svi_total_variance(ks, true)
        rng = np.random.RandomState(99)
        noise = rng.normal(0, 0.002, len(ks))
        w_obs = w_true + noise
        vega_w = build_vega_weights(ks, T=0.25, F=50000.0, r=0.05, sigma_guess=0.5)
        result = calibrate_svi_slice(ks, w_obs, T=0.25, weights=vega_w)
        assert result.outer_success
        assert result.params.a > 0