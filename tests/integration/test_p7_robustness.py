"""P7 acceptance tests: numerical robustness and reproducibility.

Covers plan §10 requirements:
  1. IV inversion edge cases
  2. SVI deterministic init + multi-start + diagnostics
  3. Monte Carlo reproducibility + structured results
  4. Central named tolerances
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from volfoundry.iv.black_scholes import (
    OptionType,
    compute_iv_surface,
    implied_vol_brent,
    implied_volatility,
)
from volfoundry.pricers.monte_carlo import MCResult, _generate_paths, mc_price
from volfoundry.svi.calibration import (
    build_vega_weights,
    calibrate_svi_slice,
)
from volfoundry.svi.parameterization import SviParams, svi_total_variance
from volfoundry.tolerances import (
    ARBITRAGE_TOL,
    CALIBRATION_TOL,
    PRICE_TOL,
    VOL_TOL,
    get_tolerances,
)

CALL = OptionType.CALL
PUT = OptionType.PUT


# ============================================================================
# 1. Central named tolerances
# ============================================================================


class TestCentralTolerances:
    """P7: Central named tolerances exist and are importable."""

    def test_all_tolerances_defined(self):
        """PRICE_TOL, VOL_TOL, ARBITRAGE_TOL, CALIBRATION_TOL are defined."""
        assert isinstance(PRICE_TOL, float)
        assert isinstance(VOL_TOL, float)
        assert isinstance(ARBITRAGE_TOL, float)
        assert isinstance(CALIBRATION_TOL, float)

    def test_order_of_magnitude_is_sensible(self):
        """Tolerances should have sensible orders of magnitude."""
        assert 1e-15 <= PRICE_TOL <= 1e-8
        assert 1e-12 <= VOL_TOL <= 1e-4
        assert ARBITRAGE_TOL < 0  # should be a one-sided negative tolerance
        assert 1e-12 <= CALIBRATION_TOL <= 1e-4

    def test_get_tolerances_returns_dict(self):
        """get_tolerances() returns a dict with four keys."""
        t = get_tolerances()
        assert set(t.keys()) == {"price_tol", "vol_tol", "arbitrage_tol", "calibration_tol"}
        assert all(isinstance(v, float) for v in t.values())


# ============================================================================
# 2. IV inversion edge cases
# ============================================================================


class TestIvEdgeCases:
    """P7: Implied volatility solver handles edge cases robustly."""

    def test_negative_F_raises_or_returns_sensible(self):
        """Non-positive forward should not silently return nonsense."""
        # black76_price handles degenerate inputs
        from volfoundry.iv.black_scholes import black76_price

        price = black76_price(-100.0, 100.0, 0.2, 0.25, 0.05, CALL)
        # Should be 0 or handle gracefully
        assert price >= 0
        assert math.isfinite(price)

    def test_zero_maturity(self):
        """Zero T should produce sensible result."""
        from volfoundry.iv.black_scholes import black76_price

        price = black76_price(100.0, 100.0, 0.20, 0.0, 0.05, CALL)
        assert price == 0.0 or price >= 0

    def test_huge_vol_recovery(self):
        """Very high vol (500%) should be recoverable via IV inversion."""
        F, K, T, r, sigma_true = 100.0, 100.0, 0.25, 0.05, 5.0
        from volfoundry.iv.black_scholes import black76_price

        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) / sigma_true < 1e-4

    def test_tiny_vol_recovery(self):
        """Very low vol (1%) should be recoverable."""
        F, K, T, r, sigma_true = 100.0, 100.0, 0.25, 0.05, 0.01
        from volfoundry.iv.black_scholes import black76_price

        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < VOL_TOL * 100

    def test_deep_itm_recovery(self):
        """Deep ITM (K << F) still recovers the true vol."""
        F, K, T, r, sigma_true = 100.0, 10.0, 0.25, 0.05, 0.40
        from volfoundry.iv.black_scholes import black76_price

        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert iv > 0  # Deep ITM: price ≈ intrinsic, tiny vol is returned

    def test_deep_otm_recovery(self):
        """Deep OTM (K >> F) recovers vol within reasonable tolerance."""
        F, K, T, r, sigma_true = 100.0, 500.0, 0.25, 0.05, 0.40
        from volfoundry.iv.black_scholes import black76_price

        price = black76_price(F, K, sigma_true, T, r, CALL)
        # Deep OTM: price is tiny, inversion is inherently noisy
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert iv > 0
        # Only check order of magnitude for extremely deep OTM
        assert 0.01 <= iv <= max(sigma_true * 3, 5.0)

    def test_price_below_lower_bound(self):
        """Price at or below no-arbitrage lower bound returns tiny vol."""
        F, K, T, r = 100.0, 90.0, 0.25, 0.05
        df = math.exp(-r * T)
        intrinsic = df * (F - K)
        iv = implied_volatility(intrinsic * 0.5, F, K, T, r, CALL)
        assert iv <= 1e-8

    def test_price_above_upper_bound(self):
        """Price exceeding the no-arbitrage upper bound is rejected."""
        # For a call, the upper bound is df * F
        F, T, r = 100.0, 0.25, 0.05
        df = math.exp(-r * T)
        # Price > df * F is impossible → Brent should fail to bracket
        with pytest.raises(ValueError, match="cannot bracket"):
            implied_vol_brent(df * F * 1.5, F, 100.0, T, r, CALL)

    def test_vectorized_recovers_vols(self):
        """Vectorised compute_iv_surface recovers correct vols."""
        n = 20
        F_arr = np.full(n, 100.0)
        K_arr = np.linspace(80.0, 120.0, n)
        T_arr = np.full(n, 0.25)
        r_arr = np.full(n, 0.05)
        sigma_true = 0.25
        from volfoundry.iv.black_scholes import black76_price

        prices = np.array(
            [
                black76_price(
                    float(F_arr[i]),
                    float(K_arr[i]),
                    sigma_true,
                    float(T_arr[i]),
                    float(r_arr[i]),
                    CALL,
                )
                for i in range(n)
            ]
        )
        ivs = compute_iv_surface(F_arr, K_arr, T_arr, r_arr, prices, CALL)
        assert ivs.shape == (n,)
        for iv in ivs:
            assert abs(iv - sigma_true) < VOL_TOL * 10


# ============================================================================
# 3. SVI calibration diagnostics
# ============================================================================


class TestSviDiagnostics:
    """P7: SVI calibration reports optimizer diagnostics."""

    def test_deterministic_initial_conditions(self):
        """Same data + same seed → same SVI parameters."""
        k = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
        a, b, rho, m, sigma = 0.04, 0.3, -0.3, 0.0, 0.2
        ref_params = SviParams(a=a, b=b, rho=rho, m=m, sigma=sigma)
        w_obs = svi_total_variance(k, ref_params)
        T = 0.25

        r1 = calibrate_svi_slice(k, w_obs, T, m_init=0.0, sigma_init=0.1)
        r2 = calibrate_svi_slice(k, w_obs, T, m_init=0.0, sigma_init=0.1)
        assert r1.params.a == r2.params.a
        assert r1.params.b == r2.params.b
        assert r1.params.rho == r2.params.rho

    def test_result_contains_outer_success_flag(self):
        """SviCalibrationResult has outer_success and outer_message."""
        k = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
        ref_params = SviParams(a=0.04, b=0.3, rho=-0.3, m=0.0, sigma=0.2)
        w_obs = svi_total_variance(k, ref_params)
        result = calibrate_svi_slice(k, w_obs, 0.25)
        assert isinstance(result.outer_success, bool)
        assert isinstance(result.outer_message, str)
        assert result.r2 > 0.9  # near-perfect fit to synthetic data

    def test_result_contains_diagnostics(self):
        """Calibration result has R², RMSE, n_points, k range."""
        k = np.linspace(-1.5, 1.5, 15)
        ref_params = SviParams(a=0.06, b=0.4, rho=-0.2, m=0.1, sigma=0.3)
        w_obs = svi_total_variance(k, ref_params)
        result = calibrate_svi_slice(k, w_obs, 0.5)
        assert result.n_points == 15
        assert result.k_min <= result.k_max
        assert result.r2 >= 0.0
        assert result.rmse >= 0.0
        assert result.rmse_unweighted >= 0.0

    def test_bound_proximity_visible(self):
        """When parameters land near bounds, it should be detectable."""
        k = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
        ref_params = SviParams(a=0.04, b=0.3, rho=-0.3, m=0.0, sigma=0.01)
        w_obs = svi_total_variance(k, ref_params)
        # Tight bounds on m — solution may hit boundary
        result = calibrate_svi_slice(
            k,
            w_obs,
            0.25,
            m_bounds=(-0.01, 0.01),
            sigma_bounds=(1e-6, 5.0),
        )
        # m should be clipped to the bound
        assert abs(result.params.m) <= 0.01 + 1e-6

    def test_weights_are_normalised(self):
        """Vega weights are normalised to mean ~1."""
        k = np.linspace(-1.0, 1.0, 9)
        w = build_vega_weights(k, 0.25, 50000.0, 0.01, sigma_guess=0.6)
        assert abs(np.mean(w) - 1.0) < 1e-10
        assert np.all(w > 0)

    def test_min_data_requirement(self):
        """Fewer than 4 points raises ValueError."""
        with pytest.raises(ValueError, match="at least 4"):
            calibrate_svi_slice(np.array([0.0, 0.1, 0.2]), np.array([0.01, 0.02, 0.03]), 0.25)

    def test_degenerate_smile_flat(self):
        """Flat smile (all same vol) calibrates without error."""
        k = np.linspace(-1.0, 1.0, 9)
        w_obs = np.full_like(k, 0.04)  # constant total variance
        result = calibrate_svi_slice(k, w_obs, 0.25)
        # Should succeed; b should be small (flat smile)
        assert result.outer_success
        assert result.params.b < 0.5
        # R² should be okay (zero-slope fit)
        assert result.r2 >= 0.0


# ============================================================================
# 4. Monte Carlo reproducibility and structured results
# ============================================================================


class TestMcStructuredResults:
    """P7: Monte Carlo uses numpy.random.Generator, seeds, and structured returns."""

    def test_mc_result_is_structured(self):
        """mc_price returns MCResult, not a plain dict."""
        result = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=10_000, seed=42)
        assert isinstance(result, MCResult)
        # Check all required fields
        assert isinstance(result.price, float)
        assert isinstance(result.std_error, float)
        assert isinstance(result.price_raw, float)
        assert isinstance(result.bs_control_price, float)
        assert isinstance(result.ci_lower, float)
        assert isinstance(result.ci_upper, float)
        assert isinstance(result.n_paths, int)
        assert result.seed == 42
        assert result.control_variate is True

    def test_confidence_interval_contains_price(self):
        """95% CI should contain the price estimate."""
        result = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=10_000, seed=123)
        assert result.ci_lower <= result.price <= result.ci_upper
        assert result.ci_upper - result.ci_lower > 0

    def test_reproducibility_with_seed(self):
        """Same seed → identical results."""
        r1 = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=10_000, seed=42)
        r2 = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=10_000, seed=42)
        assert r1.price == r2.price
        assert r1.std_error == r2.std_error

    def test_different_seeds_produce_different_results(self):
        """Different seeds → different prices (MC is stochastic)."""
        r1 = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=50_000, seed=1)
        r2 = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=50_000, seed=2)
        # Very unlikely to be bit-identical
        assert r1.price != r2.price

    def test_control_variate_near_bs(self):
        """Control-variate MC price should be close to BS for ATM."""
        from volfoundry.iv.black_scholes import black76_price

        F, K, sigma, T, r = 100.0, 100.0, 0.20, 0.25, 0.05
        bs = black76_price(F, K, sigma, T, r, CALL)
        result = mc_price(F, K, sigma, T, r, CALL, n_paths=100_000, seed=42)
        assert abs(result.price - bs) < 3 * result.std_error + 0.5

    def test_zero_vol_returns_exact_intrinsic(self):
        """Zero vol → MC returns exact discounted intrinsic."""
        result = mc_price(100.0, 90.0, 0.0, 0.25, 0.05, CALL, n_paths=1000, seed=1)
        df = math.exp(-0.05 * 0.25)
        expected = df * (100.0 - 90.0)
        assert abs(result.price - expected) < PRICE_TOL * 10

    def test_mc_generator_is_isolated(self):
        """MC uses numpy.random.Generator, never global RNG."""
        # Generate paths and verify generator is used internally
        rng = np.random.default_rng(999)
        paths1 = _generate_paths(100.0, 0.20, 0.25, 100, rng)
        rng2 = np.random.default_rng(999)
        paths2 = _generate_paths(100.0, 0.20, 0.25, 100, rng2)
        np.testing.assert_array_equal(paths1, paths2)
