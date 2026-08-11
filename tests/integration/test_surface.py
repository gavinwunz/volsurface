"""Tests for volfoundry.surface — SSVI parameterization and global calibration."""

from __future__ import annotations

import numpy as np
import pytest

from volfoundry.surface.calibration import (
    SsviCalibrationResult,
    _global_objective_wrapper,
    _ssvi_global_objective,
    calibrate_ssvi_surface,
    extract_atm_variance,
    extract_theta_grid,
)
from volfoundry.surface.ssvi import (
    SsviParams,
    ssvi_implied_vol,
    ssvi_to_raw_svi,
    ssvi_to_raw_svi_surface,
    ssvi_total_variance,
    ssvi_total_variance_surface,
)

# ===================================================================
# Helper: generate synthetic SSVI data
# ===================================================================


def _make_ssvi_params(**overrides) -> SsviParams:
    """Create valid SsviParams with defaults suitable for BTC-like surface."""
    defaults = {"rho": -0.3, "eta": 1.2, "lamb": 0.25}
    defaults.update(overrides)
    return SsviParams(**defaults)


def _generate_synthetic_slices(
    params: SsviParams,
    theta_values: np.ndarray,
    T_values: np.ndarray,
    n_k: int = 40,
    k_min: float = -1.5,
    k_max: float = 1.5,
    noise: float = 0.0,
    rng_seed: int = 42,
) -> list:
    """Generate synthetic slice data from SSVI parameters.

    Returns list of (k, w_observed, T) tuples suitable for
    calibrate_ssvi_surface.
    """
    rng = np.random.RandomState(rng_seed)
    k_grid = np.linspace(k_min, k_max, n_k)
    slices = []
    for theta, T in zip(theta_values, T_values, strict=False):
        phi_val = params.phi(float(theta))
        w_true = ssvi_total_variance(k_grid, float(theta), float(phi_val), params.rho)
        w_obs = w_true + noise * rng.normal(0, 1, n_k)
        slices.append((k_grid.copy(), w_obs, float(T)))
    return slices


# ===================================================================
# SsviParams
# ===================================================================


class TestSsviParams:
    def test_valid_construction(self):
        p = SsviParams(rho=-0.3, eta=1.2, lamb=0.25)
        assert p.rho == -0.3
        assert p.eta == 1.2
        assert p.lamb == 0.25
        assert p.theta_grid is None

    def test_rho_bounds(self):
        # Valid at edge
        SsviParams(rho=0.99, eta=0.1, lamb=0.0)
        SsviParams(rho=-0.99, eta=0.1, lamb=0.0)
        # Invalid
        with pytest.raises(ValueError, match="rho must be in"):
            SsviParams(rho=1.0, eta=0.1, lamb=0.0)
        with pytest.raises(ValueError, match="rho must be in"):
            SsviParams(rho=-1.0, eta=0.1, lamb=0.0)
        with pytest.raises(ValueError, match="rho must be in"):
            SsviParams(rho=1.5, eta=0.1, lamb=0.0)

    def test_eta_must_be_positive(self):
        with pytest.raises(ValueError, match="eta must be positive"):
            SsviParams(rho=0.0, eta=0.0, lamb=0.5)
        with pytest.raises(ValueError, match="eta must be positive"):
            SsviParams(rho=0.0, eta=-0.1, lamb=0.5)

    def test_lambda_bounds(self):
        # Valid at boundaries
        SsviParams(rho=0.0, eta=1.0, lamb=0.0)
        SsviParams(rho=0.0, eta=1.0, lamb=1.0)
        # Invalid
        with pytest.raises(ValueError, match="lambda must be in"):
            SsviParams(rho=0.0, eta=1.0, lamb=-0.01)
        with pytest.raises(ValueError, match="lambda must be in"):
            SsviParams(rho=0.0, eta=1.0, lamb=1.01)

    def test_theta_grid_optional(self):
        p = SsviParams(rho=-0.5, eta=2.0, lamb=0.5)
        assert p.theta_grid is None

    def test_theta_grid_populated(self):
        p = SsviParams(rho=-0.5, eta=2.0, lamb=0.5, theta_grid=np.array([0.01, 0.04, 0.09]))
        assert len(p.theta_grid) == 3

    def test_phi_power_law(self):
        p = SsviParams(rho=0.0, eta=1.5, lamb=0.5)
        assert abs(p.phi(0.04) - 1.5 / np.sqrt(0.04)) < 1e-12
        assert abs(p.phi(1.0) - 1.5) < 1e-12

    def test_phi_array_input(self):
        p = SsviParams(rho=0.0, eta=2.0, lamb=0.0)
        thetas = np.array([0.01, 0.04, 0.09])
        phi_vals = p.phi(thetas)
        assert np.all(phi_vals == 2.0)
        assert phi_vals.shape == (3,)

    def test_phi_nonpositive_raises(self):
        p = SsviParams(rho=0.0, eta=1.0, lamb=0.5)
        with pytest.raises(ValueError, match="theta must be positive"):
            p.phi(0.0)

    def test_satisfies_lee_bound(self):
        # eta*(1+|rho|) <= 2
        assert SsviParams(rho=0.0, eta=1.9, lamb=0.0).satisfies_lee_bound()
        assert SsviParams(rho=0.5, eta=1.2, lamb=0.0).satisfies_lee_bound()
        # 1.5 * (1+0.5) = 2.25 > 2
        assert not SsviParams(rho=0.5, eta=1.5, lamb=0.0).satisfies_lee_bound()
        # -0.5 same abs
        assert not SsviParams(rho=-0.5, eta=1.5, lamb=0.0).satisfies_lee_bound()
        # 1.0*(1+0.9) = 1.9 < 2
        assert SsviParams(rho=0.9, eta=1.0, lamb=0.0).satisfies_lee_bound()

    def test_lambda_does_not_affect_lee_bound_check(self):
        # The Lee bound uses only eta and rho; lambda doesn't matter
        p = SsviParams(rho=0.0, eta=1.9, lamb=1.0)
        assert p.satisfies_lee_bound()


# ===================================================================
# ssvi_total_variance
# ===================================================================


class TestSsviTotalVariance:
    def test_scalar_k(self):
        p = _make_ssvi_params(rho=-0.3, eta=1.2, lamb=0.25)
        theta = 0.04
        phi_val = p.phi(theta)
        w = ssvi_total_variance(0.0, theta, phi_val, p.rho)
        # At k=0, w(0) = theta/2 * (1 + sqrt(rho^2 + 1 - rho^2))
        #                 = theta/2 * (1 + 1) = theta
        assert abs(w - theta) < 1e-12

    def test_array_k(self):
        p = _make_ssvi_params()
        theta = 0.04
        phi_val = p.phi(theta)
        ks = np.linspace(-1.0, 1.0, 11)
        w = ssvi_total_variance(ks, theta, phi_val, p.rho)
        assert w.shape == (11,)
        assert np.all(np.isfinite(w))
        assert np.all(w > 0)

    def test_non_negative(self):
        p = _make_ssvi_params(rho=-0.7, eta=1.5, lamb=0.3)
        theta = 0.02
        phi_val = p.phi(theta)
        ks = np.linspace(-5.0, 5.0, 500)
        w = ssvi_total_variance(ks, theta, phi_val, p.rho)
        assert np.all(w >= -1e-12)

    def test_at_k_zero_is_theta(self):
        """At k=0, w(0) = theta regardless of rho, phi."""
        for rho in [-0.9, -0.3, 0.0, 0.3, 0.9]:
            for theta in [0.01, 0.04, 0.25]:
                p = _make_ssvi_params(rho=rho)
                phi_val = p.phi(theta)
                w = ssvi_total_variance(0.0, theta, phi_val, p.rho)
                assert abs(w - theta) < 1e-12, f"rho={rho}, theta={theta}"

    def test_negative_k_symmetry_with_positive_rho(self):
        """With rho > 0 (positive skew), the right wing is steeper."""
        theta = 0.04
        phi_val = 1.0
        # rho > 0: put wing (k < 0) should be lower than call wing (k > 0)
        w_neg = ssvi_total_variance(-1.0, theta, phi_val, 0.5)
        w_pos = ssvi_total_variance(1.0, theta, phi_val, 0.5)
        # For positive rho, put side has LESS variance (lower vol)
        assert w_neg < w_pos

    def test_negative_rho_skew(self):
        """With rho < 0 (negative skew, typical equity-like), put wing is higher."""
        theta = 0.04
        phi_val = 1.0
        w_neg = ssvi_total_variance(-1.0, theta, phi_val, -0.5)
        w_pos = ssvi_total_variance(1.0, theta, phi_val, -0.5)
        # Put wing (k < 0) has MORE variance
        assert w_neg > w_pos

    def test_invalid_theta_raises(self):
        with pytest.raises(ValueError, match="theta must be positive"):
            ssvi_total_variance(0.0, 0.0, 1.0, 0.0)

    def test_invalid_phi_raises(self):
        with pytest.raises(ValueError, match="phi must be positive"):
            ssvi_total_variance(0.0, 0.04, 0.0, 0.0)

    def test_float_input_returns_float(self):
        w = ssvi_total_variance(0.0, 0.04, 1.0, 0.0)
        assert isinstance(w, float)

    def test_w_monotonic_in_k_wings(self):
        """w(k) should be monotonic for large |k| (linear wings)."""
        theta = 0.04
        phi_val = 1.0
        rho = -0.5
        ks_left = np.array([-5.0, -4.5, -4.0])
        ks_right = np.array([4.0, 4.5, 5.0])
        w_left = [ssvi_total_variance(k, theta, phi_val, rho) for k in ks_left]
        w_right = [ssvi_total_variance(k, theta, phi_val, rho) for k in ks_right]
        # Left wing: monotonically decreasing (rho < 0 gives steeper left)
        assert w_left[0] > w_left[1] > w_left[2]
        # Right wing: monotonically increasing
        assert w_right[0] < w_right[1] < w_right[2]


# ===================================================================
# ssvi_implied_vol
# ===================================================================


class TestSsviImpliedVol:
    def test_at_k_zero_returns_atm_vol(self):
        p = _make_ssvi_params(rho=-0.3)
        theta = 0.08
        T = 0.25
        phi_val = p.phi(theta)
        iv = ssvi_implied_vol(0.0, theta, phi_val, p.rho, T)
        expected = np.sqrt(theta / T)
        assert abs(iv - expected) < 1e-12

    def test_nonpositive_T_raises(self):
        with pytest.raises(ValueError):
            ssvi_implied_vol(0.0, 0.04, 1.0, 0.0, T=0.0)

    def test_array_k_shape(self):
        ks = np.linspace(-2.0, 2.0, 20)
        iv = ssvi_implied_vol(ks, 0.04, 1.2, -0.3, T=1.0)
        assert iv.shape == (20,)
        assert np.all(np.isfinite(iv))


# ===================================================================
# ssvi_total_variance_surface
# ===================================================================


class TestSsviTotalVarianceSurface:
    def test_output_shape(self):
        p = _make_ssvi_params()
        thetas = np.array([0.01, 0.04, 0.09, 0.16])
        p.theta_grid = thetas
        k_grid = np.linspace(-2.0, 2.0, 50)
        surface = ssvi_total_variance_surface(k_grid, p)
        assert surface.shape == (50, 4)

    def test_surface_non_negative(self):
        p = _make_ssvi_params(rho=-0.6, eta=1.5, lamb=0.3)
        thetas = np.array([0.02, 0.06, 0.15])
        p.theta_grid = thetas
        k_grid = np.linspace(-3.0, 3.0, 100)
        surface = ssvi_total_variance_surface(k_grid, p)
        assert np.all(surface >= -1e-12)

    def test_monotonic_in_theta(self):
        """For fixed k, w(k, theta) should be increasing in theta."""
        p = _make_ssvi_params(rho=-0.3, eta=1.0, lamb=0.25)
        thetas = np.array([0.01, 0.04, 0.09, 0.16])
        p.theta_grid = thetas
        k_grid = np.linspace(-2.0, 2.0, 50)
        surface = ssvi_total_variance_surface(k_grid, p)
        for j in range(len(thetas) - 1):
            # Check that each slice is <= the next (calendar monotonicity)
            assert np.all(surface[:, j] <= surface[:, j + 1] - 1e-12), (
                f"Calendar violation at theta index {j}"
            )

    def test_no_theta_grid_raises(self):
        p = _make_ssvi_params()
        with pytest.raises(ValueError, match="theta_grid must be populated"):
            ssvi_total_variance_surface(np.linspace(-1, 1, 10), p)


# ===================================================================
# ssvi_to_raw_svi
# ===================================================================


class TestSsviToRawSvi:
    def test_roundtrip_at_k_zero(self):
        """At k=0, SSVI -> raw SVI conversion should preserve w(0) = theta."""
        p = _make_ssvi_params(rho=-0.3, eta=1.2, lamb=0.25)
        theta = 0.04
        phi_val = p.phi(theta)
        raw = ssvi_to_raw_svi(theta, phi_val, p.rho)

        from volfoundry.svi.parameterization import svi_total_variance

        w_ssvi = ssvi_total_variance(0.0, theta, phi_val, p.rho)
        w_raw = svi_total_variance(0.0, raw)
        assert abs(w_ssvi - w_raw) < 1e-12

    def test_conversion_preserves_rho(self):
        raw = ssvi_to_raw_svi(0.04, 1.0, -0.5)
        assert raw.rho == -0.5

    def test_conversion_formula_known(self):
        """Test the algebraic mapping with known values."""
        theta = 0.04
        phi_val = 0.8
        rho = -0.3
        raw = ssvi_to_raw_svi(theta, phi_val, rho)

        half_theta = 0.5 * theta
        one_minus_rho2 = 1 - rho**2

        expected_a = half_theta * one_minus_rho2
        expected_b = half_theta * phi_val
        expected_m = -rho / phi_val
        expected_sigma = np.sqrt(one_minus_rho2) / phi_val

        assert abs(raw.a - expected_a) < 1e-12
        assert abs(raw.b - expected_b) < 1e-12
        assert abs(raw.m - expected_m) < 1e-12
        assert abs(raw.sigma - expected_sigma) < 1e-12

    def test_full_curvature_mapping(self):
        """SSVI -> raw SVI should be equivalent for entire k range."""
        theta = 0.04
        phi_val = 0.6
        rho = 0.5
        raw = ssvi_to_raw_svi(theta, phi_val, rho)

        from volfoundry.svi.parameterization import svi_total_variance

        ks = np.linspace(-3.0, 3.0, 100)
        w_ssvi = ssvi_total_variance(ks, theta, phi_val, rho)
        w_raw = svi_total_variance(ks, raw)
        np.testing.assert_allclose(w_ssvi, w_raw, rtol=1e-12)

    def test_rho_zero_symmetric_mapping(self):
        """With rho=0 and phi=1, m=0, and both variances symmetric."""
        raw = ssvi_to_raw_svi(0.04, 1.0, 0.0)
        assert raw.m == 0.0
        assert raw.rho == 0.0


class TestSsviToRawSviSurface:
    def test_output_length(self):
        thetas = np.array([0.01, 0.04, 0.09])
        p = _make_ssvi_params(theta_grid=thetas)
        slices = ssvi_to_raw_svi_surface(p)
        assert len(slices) == 3
        for theta, raw in slices:
            assert theta > 0
            assert raw.a > 0
            assert raw.b >= 0
            assert abs(raw.rho) < 1.0
            assert raw.sigma > 0

    def test_no_theta_grid_raises(self):
        p = _make_ssvi_params()
        with pytest.raises(ValueError, match="theta_grid must be populated"):
            ssvi_to_raw_svi_surface(p)

    def test_theta_order_preserved(self):
        thetas = np.array([0.05, 0.02, 0.10])
        p = _make_ssvi_params(theta_grid=thetas)
        slices = ssvi_to_raw_svi_surface(p)
        result_thetas = [t for t, _ in slices]
        np.testing.assert_allclose(result_thetas, thetas)


# ===================================================================
# extract_atm_variance
# ===================================================================


class TestExtractAtmVariance:
    def test_exact_atm_point(self):
        """When k=0 is in the data, return w(0) directly."""
        ks = np.array([-0.5, -0.2, 0.0, 0.2, 0.5])
        ws = np.array([0.06, 0.05, 0.04, 0.05, 0.06])
        theta = extract_atm_variance(ks, ws)
        assert abs(theta - 0.04) < 1e-12

    def test_linear_interpolation(self):
        """Without exact ATM, linear interpolation between bracketing points."""
        ks = np.array([-0.2, -0.1, 0.1, 0.2])
        ws = np.array([0.05, 0.045, 0.045, 0.05])
        # Linear interpolation: between (-0.1, 0.045) and (0.1, 0.045) => 0.045
        theta = extract_atm_variance(ks, ws, method="linear")
        assert abs(theta - 0.045) < 1e-12

    def test_quadratic_interpolation(self):
        """Quadratic through 3 nearest points should interpolate smoothly."""
        # Parabola: w = 0.04 + 0.1 * k^2, so w(0) = 0.04
        ks = np.array([-0.3, -0.1, 0.2])
        ws = 0.04 + 0.1 * ks**2
        theta = extract_atm_variance(ks, ws, method="quadratic")
        assert abs(theta - 0.04) < 1e-10

    def test_nearest_method(self):
        ks = np.array([-0.5, -0.02, 0.5])
        ws = np.array([0.07, 0.04, 0.06])
        theta = extract_atm_variance(ks, ws, method="nearest")
        assert abs(theta - 0.04) < 1e-12

    def test_single_point(self):
        theta = extract_atm_variance(np.array([0.1]), np.array([0.04]))
        assert abs(theta - 0.04) < 1e-12

    def test_unsorted_input(self):
        """Unordered k values should be handled correctly."""
        ks = np.array([0.3, -0.2, -0.5, 0.0, 0.2])
        ws = np.array([0.06, 0.05, 0.07, 0.04, 0.05])
        theta = extract_atm_variance(ks, ws)
        assert abs(theta - 0.04) < 1e-12


class TestExtractThetaGrid:
    def test_multiple_slices(self):
        slices = [
            (np.array([-0.5, -0.1, 0.0, 0.2, 0.5]), np.array([0.06, 0.05, 0.04, 0.05, 0.06]), 0.25),
            (np.array([-0.5, 0.0, 0.5]), np.array([0.12, 0.09, 0.12]), 0.5),
        ]
        theta_vec = extract_theta_grid(slices)
        assert len(theta_vec) == 2
        assert abs(theta_vec[0] - 0.04) < 1e-12
        assert abs(theta_vec[1] - 0.09) < 1e-12


# ===================================================================
# SSVI global objective
# ===================================================================


class TestSsviGlobalObjective:
    def test_zero_at_true_params(self):
        p = _make_ssvi_params(rho=-0.3, eta=1.2, lamb=0.25)
        thetas = np.array([0.02, 0.05, 0.10])
        Ts = np.array([0.1, 0.25, 0.5])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=30)
        k_all = [s[0] for s in slices]
        w_all = [s[1] for s in slices]
        weights_all = [np.ones_like(k) for k in k_all]
        obj = _ssvi_global_objective(thetas, k_all, w_all, weights_all, p.rho, p.eta, p.lamb)
        assert obj < 1e-20

    def test_positive_at_wrong_params(self):
        p = _make_ssvi_params(rho=-0.3, eta=1.2, lamb=0.25)
        thetas = np.array([0.02, 0.05, 0.10])
        Ts = np.array([0.1, 0.25, 0.5])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=30)
        k_all = [s[0] for s in slices]
        w_all = [s[1] for s in slices]
        weights_all = [np.ones_like(k) for k in k_all]
        # Wrong eta
        obj = _ssvi_global_objective(thetas, k_all, w_all, weights_all, p.rho, 0.5, p.lamb)
        assert obj > 0

    def test_invalid_eta_penalized(self):
        p = _make_ssvi_params()
        thetas = np.array([0.04])
        k_all = [np.linspace(-1, 1, 10)]
        w_all = [np.array([0.05] * 10)]
        weights_all = [np.ones(10)]
        obj = _ssvi_global_objective(thetas, k_all, w_all, weights_all, p.rho, 0.0, 0.5)
        # With eta=0, phi(theta) = eta/theta^lambda = 0, which is non-positive.
        # The function now returns NON_POSITIVE_PHI_PENALTY (1e20).
        assert obj >= 1e20

    def test_wrapper_interface(self):
        p = _make_ssvi_params(rho=-0.3, eta=1.0, lamb=0.3)
        thetas = np.array([0.04, 0.09])
        Ts = np.array([0.25, 0.5])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=20)
        k_all = [s[0] for s in slices]
        w_all = [s[1] for s in slices]
        weights_all = [np.ones_like(k) for k in k_all]
        obj = _global_objective_wrapper(
            np.array([1.0, 0.3]), thetas, k_all, w_all, weights_all, p.rho, Ts
        )
        assert obj < 1


# ===================================================================
# calibrate_ssvi_surface
# ===================================================================


class TestCalibrateSsviSurface:
    def test_exact_recovery_no_noise(self):
        """With exact SSVI data and fixed rho, recover eta and lambda."""
        p = _make_ssvi_params(rho=-0.3, eta=1.2, lamb=0.25)
        thetas = np.array([0.02, 0.05, 0.10, 0.20])
        Ts = np.array([0.1, 0.25, 0.5, 1.0])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=40)

        result = calibrate_ssvi_surface(
            slices,
            expiration_times=list(Ts),
            rho=-0.3,  # fix rho to true value
        )
        assert result.success
        assert result.r2 > 0.999
        assert result.rmse < 0.01
        assert abs(result.eta - p.eta) < 0.02
        assert abs(result.lamb - p.lamb) < 0.02

    def test_noisy_data_converges(self):
        p = _make_ssvi_params(rho=-0.4, eta=1.0, lamb=0.3)
        thetas = np.array([0.02, 0.06, 0.15])
        Ts = np.array([0.1, 0.3, 0.75])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=50, noise=0.003)

        result = calibrate_ssvi_surface(slices, expiration_times=list(Ts), rho=-0.4)
        assert result.success
        assert result.r2 > 0.8
        assert result.eta > 0
        assert 0 <= result.lamb <= 1
        assert result.calendar_violations == 0

    def test_joint_rho_calibration(self):
        """When rho is not fixed, calibrate all three parameters."""
        p = _make_ssvi_params(rho=-0.3, eta=1.0, lamb=0.3)
        thetas = np.array([0.02, 0.05, 0.10, 0.20])
        Ts = np.array([0.1, 0.25, 0.5, 1.0])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=40, noise=0.001)

        result = calibrate_ssvi_surface(slices, expiration_times=list(Ts))
        assert result.success
        assert abs(result.rho) < 1.0
        assert result.eta > 0
        assert 0 <= result.lamb <= 1
        # With low noise, rho should be close to true
        assert abs(result.rho - p.rho) < 0.15

    def test_single_slice(self):
        p = _make_ssvi_params(rho=-0.3, eta=0.8, lamb=0.0)
        thetas = np.array([0.04])
        Ts = np.array([0.25])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=40)

        result = calibrate_ssvi_surface(slices, expiration_times=list(Ts), rho=-0.3)
        assert result.success
        assert result.calendar_violations == 0

    def test_result_dataclass_fields(self):
        p = _make_ssvi_params()
        thetas = np.array([0.04, 0.09])
        Ts = np.array([0.25, 0.5])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=30)

        result = calibrate_ssvi_surface(slices, expiration_times=list(Ts), rho=-0.3)
        assert isinstance(result, SsviCalibrationResult)
        assert len(result.theta_values) == 2
        assert len(result.expiry_times) == 2
        assert len(result.per_slice_rmse) == 2
        assert result.params is not None
        assert result.params.theta_grid is not None
        assert len(result.params.theta_grid) == 2

    def test_per_slice_rmse_non_negative(self):
        p = _make_ssvi_params()
        thetas = np.array([0.04, 0.09, 0.16])
        Ts = np.array([0.2, 0.5, 0.8])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=40, noise=0.001)

        result = calibrate_ssvi_surface(slices, expiration_times=list(Ts), rho=-0.3)
        for rmse in result.per_slice_rmse:
            assert rmse >= 0

    def test_no_slices_raises(self):
        with pytest.raises(ValueError, match="Need at least one slice"):
            calibrate_ssvi_surface([], expiration_times=[], rho=-0.3)

    def test_weights_used(self):
        p = _make_ssvi_params()
        thetas = np.array([0.04, 0.09])
        Ts = np.array([0.25, 0.5])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=30, noise=0.005)
        weights_all = [np.ones(len(s[0])) * 2.0 for s in slices]

        result = calibrate_ssvi_surface(
            slices, expiration_times=list(Ts), rho=-0.3, weights_all=weights_all
        )
        assert result.success

    def test_lambda_zero_special_case(self):
        """lambda=0 means constant curvature: phi(theta) = eta."""
        p = _make_ssvi_params(rho=-0.2, eta=1.5, lamb=0.0)
        thetas = np.array([0.02, 0.06, 0.12])
        Ts = np.array([0.1, 0.3, 0.6])
        slices = _generate_synthetic_slices(p, thetas, Ts, n_k=40)

        result = calibrate_ssvi_surface(slices, expiration_times=list(Ts), rho=-0.2)
        assert result.success
        assert abs(result.lamb - 0.0) < 0.1 or result.r2 > 0.95
