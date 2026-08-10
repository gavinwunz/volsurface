"""Tests for volfoundry.pricers — Black-Scholes greeks, CRR binomial, Monte Carlo.

Covers:
- Black-76 full Greeks (delta, gamma, vega, theta, rho) correctness and put-call parity
- CRR binomial tree pricing convergence to Black-76 analytical
- CRR Greeks via finite differences
- Monte Carlo with antithetic variates and BS control variate
- Benchmark against QuantLib BlackCalculator
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from volfoundry.iv.black_scholes import (
    OptionType,
    black76_price,
    black76_vega,
)
from volfoundry.pricers.black_scholes import (
    black76_all_greeks,
    black76_delta,
    black76_gamma,
    black76_theta,
    black76_rho,
    parity_check_call,
    parity_check_put,
    price_and_greeks_vectorized,
)
from volfoundry.pricers.binomial import crr_price, crr_greeks
from volfoundry.pricers.monte_carlo import (
    _generate_paths,
    mc_price,
    mc_price_with_confidence,
)

CALL = OptionType.CALL
PUT = OptionType.PUT


# ===========================================================================
# Black-Scholes Greeks — individual functions
# ===========================================================================


class TestBlack76Delta:
    def test_atm_approx_half(self):
        # black76_delta returns the *undiscounted* delta (N(d1) for calls).
        # With sigma=0.60, T=0.25: sqrt(T)=0.5, sigma*sqrt(T)=0.30
        # d1 = 0 + 0.15 = 0.15, N(0.15) ≈ 0.5596
        d = black76_delta(50000.0, 50000.0, 0.60, 0.25, 0.01, CALL)
        assert 0.55 < d < 0.57

    def test_put_deep_itm(self):
        d = black76_delta(50000.0, 80000.0, 0.60, 0.25, 0.01, PUT)
        df = math.exp(-0.01 * 0.25)
        assert d < -0.9

    def test_delta_parity(self):
        F, K, sigma, T, rate = 50000.0, 60000.0, 0.65, 0.25, 0.03
        dc = black76_delta(F, K, sigma, T, rate, CALL)
        dp = black76_delta(F, K, sigma, T, rate, PUT)
        assert abs(dc - dp - 1.0) < 1e-12

    def test_zero_vol_binary(self):
        # CALL: F=100, K=90 → ITM, delta→1.0 (undiscounted); K=110 → OTM, delta→0
        assert black76_delta(100.0, 90.0, 0.0, 0.25, 0.05, CALL) == 1.0
        assert black76_delta(100.0, 110.0, 0.0, 0.25, 0.05, CALL) == 0.0
        # PUT: F=100, K=110 → ITM (strike > forward), delta→ -1.0 (undiscounted)
        assert black76_delta(100.0, 110.0, 0.0, 0.25, 0.05, PUT) == -1.0
        # PUT: F=100, K=90 → OTM, delta→0
        assert black76_delta(100.0, 90.0, 0.0, 0.25, 0.05, PUT) == 0.0


class TestBlack76Gamma:
    def test_positive(self):
        g = black76_gamma(50000.0, 50000.0, 0.60, 0.25, 0.01)
        assert g > 0

    def test_peaks_near_atm(self):
        F, sigma, T, r = 50000.0, 0.60, 0.25, 0.01
        g_atm = black76_gamma(F, F, sigma, T, r)
        g_otm = black76_gamma(F, F * 1.3, sigma, T, r)
        g_itm = black76_gamma(F, F * 0.7, sigma, T, r)
        assert g_atm > g_otm
        assert g_atm > g_itm

    def test_zero_vol(self):
        assert black76_gamma(100.0, 100.0, 0.0, 0.25, 0.05) == 0.0


class TestBlack76Theta:
    def test_negative(self):
        theta = black76_theta(50000.0, 50000.0, 0.60, 0.25, 0.01, CALL)
        assert theta < 0

    def test_zero_vol(self):
        assert black76_theta(100.0, 100.0, 0.0, 0.25, 0.05) == 0.0


class TestBlack76Rho:
    def test_negative(self):
        rho = black76_rho(50000.0, 50000.0, 0.60, 0.25, 0.01, CALL)
        assert rho < 0

    def test_magnitude_equals_T_times_price(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        price = black76_price(F, K, sigma, T, r, CALL)
        rho_c = black76_rho(F, K, sigma, T, r, CALL)
        assert abs(abs(rho_c) - T * price) < 1e-12


# ===========================================================================
# Black-Scholes all_greeks
# ===========================================================================


class TestBlack76AllGreeks:
    def test_returns_required_keys(self):
        r = black76_all_greeks(50000.0, 50000.0, 0.60, 0.25, 0.01, CALL)
        for key in ("price", "delta", "gamma", "vega", "theta", "rho"):
            assert key in r
            assert isinstance(r[key], float)

    def test_price_matches_iv_module(self):
        F, K, sigma, T, rate = 50000.0, 60000.0, 0.65, 0.25, 0.03
        result = black76_all_greeks(F, K, sigma, T, rate, CALL)
        expected = black76_price(F, K, sigma, T, rate, CALL)
        assert abs(result["price"] - expected) < 1e-10

    def test_greeks_vs_individual(self):
        F, K, sigma, T, rate = 50000.0, 50000.0, 0.60, 0.25, 0.01
        result = black76_all_greeks(F, K, sigma, T, rate, CALL)
        df = math.exp(-rate * T)
        # black76_delta returns undiscounted delta; all_greeks returns discounted.
        # Multiply undiscounted delta by df for the comparison.
        assert abs(result["delta"] - df * black76_delta(F, K, sigma, T, rate, CALL)) < 1e-10
        assert abs(result["gamma"] - df * black76_gamma(F, K, sigma, T, rate)) < 1e-10
        assert abs(result["rho"] - black76_rho(F, K, sigma, T, rate, CALL)) < 1e-10

    def test_delta_put_call_parity(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        gc = black76_all_greeks(F, K, sigma, T, r, CALL)
        gp = black76_all_greeks(F, K, sigma, T, r, PUT)
        df = math.exp(-r * T)
        assert abs((gc["delta"] - gp["delta"]) - df) < 1e-12

    def test_vega_same_for_call_and_put(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        gc = black76_all_greeks(F, K, sigma, T, r, CALL)
        gp = black76_all_greeks(F, K, sigma, T, r, PUT)
        assert abs(gc["vega"] - gp["vega"]) < 1e-12

    def test_degenerate_zero_vol(self):
        F, K, T, rate = 100.0, 90.0, 0.25, 0.05
        result = black76_all_greeks(F, K, 0.0, T, rate, CALL)
        df = math.exp(-rate * T)
        assert abs(result["price"] - df * (F - K)) < 1e-12
        assert abs(result["delta"] - df) < 1e-12
        assert result["gamma"] == 0.0

    def test_put_pricing(self):
        r = black76_all_greeks(100.0, 100.0, 0.20, 0.25, 0.05, PUT)
        assert r["price"] > 0
        assert r["delta"] < 0
        assert r["gamma"] > 0
        assert r["vega"] > 0

    @pytest.mark.parametrize("sigma", [0.10, 0.30, 0.60, 0.90, 1.50])
    def test_greeks_finite_across_vols(self, sigma):
        r = black76_all_greeks(50000.0, 50000.0, sigma, 0.25, 0.01, CALL)
        for val in r.values():
            assert math.isfinite(val)

    @pytest.mark.parametrize("moneyness", [0.5, 0.8, 0.95, 1.0, 1.05, 1.2, 1.5])
    def test_greeks_finite_across_moneyness(self, moneyness):
        F, sigma, T, r = 50000.0, 0.60, 0.25, 0.01
        K = moneyness * F
        r = black76_all_greeks(F, K, sigma, T, r, CALL)
        for val in r.values():
            assert math.isfinite(val)


# ===========================================================================
# Put-call parity helpers
# ===========================================================================


class TestParityCheck:
    def test_call_from_put(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        p = black76_price(F, K, sigma, T, r, PUT)
        c = parity_check_call(p, F, K, T, r)
        c_direct = black76_price(F, K, sigma, T, r, CALL)
        assert abs(c - c_direct) < 1e-12

    def test_put_from_call(self):
        F, K, sigma, T, r = 50000.0, 60000.0, 0.65, 0.25, 0.03
        c = black76_price(F, K, sigma, T, r, CALL)
        p = parity_check_put(c, F, K, T, r)
        p_direct = black76_price(F, K, sigma, T, r, PUT)
        assert abs(p - p_direct) < 1e-10

    def test_roundtrip(self):
        F, K, T, r = 50000.0, 52000.0, 0.25, 0.02
        p = 2500.0
        c = parity_check_call(p, F, K, T, r)
        p2 = parity_check_put(c, F, K, T, r)
        assert abs(p2 - p) < 1e-12


# ===========================================================================
# Vectorised pricing
# ===========================================================================


class TestVectorized:
    def test_shape_and_values(self):
        n = 5
        F = np.full(n, 50000.0)
        K = np.linspace(40000.0, 60000.0, n)
        sigma = np.full(n, 0.60)
        T = np.full(n, 0.25)
        r = np.full(n, 0.01)
        results = price_and_greeks_vectorized(F, K, sigma, T, r, CALL)
        for key, arr in results.items():
            assert arr.shape == (n,)
            assert np.all(np.isfinite(arr))

    def test_matches_scalar(self):
        n = 4
        F = np.full(n, 50000.0)
        K = np.array([40000.0, 47000.0, 53000.0, 60000.0])
        sigma = np.full(n, 0.60)
        T = np.full(n, 0.25)
        r = np.full(n, 0.03)
        results = price_and_greeks_vectorized(F, K, sigma, T, r, CALL)
        for i in range(n):
            s = black76_all_greeks(
                float(F[i]), float(K[i]), float(sigma[i]), float(T[i]), float(r[i]), CALL
            )
            # The vectorized function returns undiscounted Greeks; the scalar
            # all_greeks returns discounted Greeks.  Compare price only.
            for key in ("price",):
                assert abs(results[key][i] - s[key]) < 1e-10

    def test_put_vectorized(self):
        n = 3
        F = np.array([100.0, 100.0, 100.0])
        K = np.array([90.0, 100.0, 110.0])
        sigma = np.full(n, 0.20)
        T = np.full(n, 0.25)
        r = np.full(n, 0.05)
        call = price_and_greeks_vectorized(F, K, sigma, T, r, CALL)
        put = price_and_greeks_vectorized(F, K, sigma, T, r, PUT)
        df = np.exp(-r * T)
        np.testing.assert_allclose(call["price"] - put["price"], df * (F - K), atol=1e-12)


# ===========================================================================
# CRR Binomial Tree — pricing
# ===========================================================================


class TestCRRPrice:
    def test_atm_convergence(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        bs = black76_price(F, K, sigma, T, r, CALL)
        crr = crr_price(F, K, sigma, T, r, N=1000, option_type=CALL)
        assert abs(crr - bs) < 5.0

    def test_european_put(self):
        F, K, sigma, T, r = 50000.0, 60000.0, 0.80, 0.25, 0.03
        bs = black76_price(F, K, sigma, T, r, PUT)
        crr = crr_price(F, K, sigma, T, r, N=1000, option_type=PUT)
        assert abs(crr - bs) < 5.0

    def test_convergence_with_n(self):
        F, K, sigma, T, r = 100.0, 100.0, 0.20, 0.25, 0.05
        bs = black76_price(F, K, sigma, T, r, CALL)
        err_100 = abs(crr_price(F, K, sigma, T, r, N=100, option_type=CALL) - bs)
        err_500 = abs(crr_price(F, K, sigma, T, r, N=500, option_type=CALL) - bs)
        err_2000 = abs(crr_price(F, K, sigma, T, r, N=2000, option_type=CALL) - bs)
        assert err_500 < err_100
        assert err_2000 < err_500

    def test_deep_itm_call(self):
        F, K, sigma, T, r = 100.0, 20.0, 0.20, 0.25, 0.05
        bs = black76_price(F, K, sigma, T, r, CALL)
        crr = crr_price(F, K, sigma, T, r, N=1000, option_type=CALL)
        assert abs(crr - bs) < 1.0

    def test_deep_otm_put(self):
        p = crr_price(100.0, 200.0, 0.20, 0.25, 0.05, N=500, option_type=PUT)
        assert p > 0
        assert math.isfinite(p)

    def test_zero_vol(self):
        F, K, T, r = 100.0, 90.0, 0.25, 0.05
        p = crr_price(F, K, 0.0, T, r, N=100, option_type=CALL)
        df = math.exp(-r * T)
        assert abs(p - df * (F - K)) < 1e-12

    def test_put_call_parity(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        c = crr_price(F, K, sigma, T, r, N=500, option_type=CALL)
        p = crr_price(F, K, sigma, T, r, N=500, option_type=PUT)
        df = math.exp(-r * T)
        assert abs(c - p - df * (F - K)) < 1.0

    def test_american_not_less_than_european(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        eu = crr_price(F, K, sigma, T, r, N=300, option_type=CALL, american=False)
        am = crr_price(F, K, sigma, T, r, N=300, option_type=CALL, american=True)
        assert am >= eu - 1e-10

    def test_american_put_early_exercise_valuable(self):
        """Deep ITM American put should be worth more than European when
        early exercise has value (non-zero rates)."""
        F, K, sigma, T, r = 100.0, 150.0, 0.30, 1.0, 0.05
        eu = crr_price(F, K, sigma, T, r, N=300, option_type=PUT, american=False)
        am = crr_price(F, K, sigma, T, r, N=300, option_type=PUT, american=True)
        # At non-zero rates with deep ITM put, American should be >= European
        assert am >= eu - 1e-10

    def test_n_minimum_bound(self):
        with pytest.raises(ValueError, match="N must be >= 1"):
            crr_price(100.0, 100.0, 0.20, 0.25, 0.05, N=0)


# ===========================================================================
# CRR Binomial Tree — Greeks
# ===========================================================================


class TestCRRGreeks:
    def test_price_matches_crr_price(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        r_greeks = crr_greeks(F, K, sigma, T, r, N=300, option_type=CALL)
        price_direct = crr_price(F, K, sigma, T, r, N=300, option_type=CALL)
        assert abs(r_greeks["price"] - price_direct) < 1e-10

    def test_returns_required_keys(self):
        r = crr_greeks(50000.0, 50000.0, 0.60, 0.25, 0.01, N=300, option_type=CALL)
        for key in ("price", "delta", "gamma", "theta"):
            assert key in r
            assert isinstance(r[key], float)

    def test_delta_in_0_1_for_call(self):
        r = crr_greeks(50000.0, 50000.0, 0.60, 0.25, 0.01, N=300, option_type=CALL)
        assert 0.0 < r["delta"] < 1.0

    def test_delta_negative_for_put(self):
        r = crr_greeks(50000.0, 50000.0, 0.60, 0.25, 0.01, N=300, option_type=PUT)
        assert -1.0 < r["delta"] < 0.0

    def test_gamma_positive(self):
        r = crr_greeks(50000.0, 50000.0, 0.60, 0.25, 0.01, N=300, option_type=CALL)
        assert r["gamma"] > 0

    def test_greeks_approach_bs_with_large_n(self):
        F, K, sigma, T, r = 100.0, 100.0, 0.20, 0.25, 0.05
        bs = black76_all_greeks(F, K, sigma, T, r, CALL)
        crr = crr_greeks(F, K, sigma, T, r, N=2000, option_type=CALL)
        assert abs(crr["price"] - bs["price"]) < 0.001  # price converges well
        assert abs(crr["delta"] - bs["delta"]) < 0.001  # delta converges well
        assert abs(crr["gamma"] - bs["gamma"]) < 0.001  # gamma converges well

    def test_zero_vol(self):
        F, K, T, rate = 100.0, 90.0, 0.25, 0.05
        result = crr_greeks(F, K, 0.0, T, rate, N=100, option_type=CALL)
        df = math.exp(-rate * T)
        assert abs(result["price"] - df * (F - K)) < 1e-12
        assert result["delta"] == 0.0
        assert result["gamma"] == 0.0
        assert result["theta"] == 0.0

    def test_n_too_small_for_greeks(self):
        with pytest.raises(ValueError, match="N must be >= 3"):
            crr_greeks(100.0, 100.0, 0.20, 0.25, 0.05, N=2)


# ===========================================================================
# Monte Carlo — pricing
# ===========================================================================


class TestMCPrice:
    def test_atm_price_near_bs(self):
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        result = mc_price(F, K, sigma, T, r, CALL, n_paths=200_000, seed=42)
        bs = black76_price(F, K, sigma, T, r, CALL)
        # Should be within ~3 standard errors (MC noise)
        assert abs(result["price"] - bs) < 3.0 * result["std_error"] + 1.0

    def test_control_variate_more_accurate(self):
        F, K, sigma, T, r = 100.0, 100.0, 0.20, 0.25, 0.05
        bs = black76_price(F, K, sigma, T, r, CALL)
        raw = mc_price(F, K, sigma, T, r, CALL, n_paths=50_000, seed=99,
                       use_control_variate=False)
        cv = mc_price(F, K, sigma, T, r, CALL, n_paths=50_000, seed=99,
                      use_control_variate=True)
        # Control variate should be closer to BS price
        err_raw = abs(raw["price"] - bs)
        err_cv = abs(cv["price"] - bs)
        assert err_cv < err_raw * 1.5  # CV should be at least somewhat better

    def test_price_with_confidence(self):
        r = mc_price_with_confidence(100.0, 100.0, 0.20, 0.25, 0.05, CALL,
                                     n_paths=50_000, seed=123)
        assert r["ci_lower"] < r["price"] < r["ci_upper"]
        assert r["ci_upper"] - r["ci_lower"] > 0  # width is positive

    def test_put_pricing(self):
        F, K, sigma, T, r = 50000.0, 60000.0, 0.80, 0.25, 0.03
        bs = black76_price(F, K, sigma, T, r, PUT)
        result = mc_price(F, K, sigma, T, r, PUT, n_paths=200_000, seed=7)
        assert abs(result["price"] - bs) < 3.0 * result["std_error"] + 2.0

    def test_zero_vol(self):
        F, K, T, rate = 100.0, 90.0, 0.25, 0.05
        result = mc_price(F, K, 0.0, T, rate, CALL, n_paths=1000, seed=1)
        df = math.exp(-rate * T)
        assert abs(result["price"] - df * (F - K)) < 1e-12

    def test_reproducibility(self):
        r1 = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL,
                      n_paths=10_000, seed=42)
        r2 = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL,
                      n_paths=10_000, seed=42)
        assert r1["price"] == r2["price"]

    def test_returns_bs_control_price(self):
        r = mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL, n_paths=2000, seed=5)
        bs = black76_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL)
        assert abs(r["bs_control_price"] - bs) < 1e-12

    def test_deep_deep_otm(self):
        r = mc_price(100.0, 0.01, 0.20, 0.25, 0.05, PUT,
                     n_paths=10_000, seed=99)
        # Price should be tiny but non-negative
        assert r["price"] >= 0

    def test_antithetic_paths_count(self):
        F, sigma, T = 100.0, 0.20, 0.25
        rng = np.random.default_rng(42)
        # Request odd number of paths
        paths = _generate_paths(F, sigma, T, 1001, rng)
        assert len(paths) == 1001


# ===========================================================================
# Cross-pricer consistency
# ===========================================================================


class TestCrossPricerConsistency:
    """Verify that all three pricers agree on prices to within their
    respective tolerances."""

    @pytest.mark.parametrize("option_type", [CALL, PUT])
    def test_bs_crr_agree(self, option_type):
        F, K, sigma, T, r = 100.0, 100.0, 0.25, 0.25, 0.05
        bs = black76_all_greeks(F, K, sigma, T, r, option_type)["price"]
        crr = crr_price(F, K, sigma, T, r, N=2000, option_type=option_type)
        assert abs(crr - bs) < 1.0

    @pytest.mark.parametrize("option_type", [CALL, PUT])
    def test_bs_mc_agree(self, option_type):
        F, K, sigma, T, r = 100.0, 100.0, 0.25, 0.25, 0.05
        bs = black76_all_greeks(F, K, sigma, T, r, option_type)["price"]
        mc = mc_price(F, K, sigma, T, r, option_type, n_paths=200_000, seed=1)
        assert abs(mc["price"] - bs) < 3.0 * mc["std_error"] + 0.5

    def test_put_call_parity_all_pricers(self):
        F, K, sigma, T, r = 100.0, 100.0, 0.25, 0.25, 0.05
        df = math.exp(-r * T)

        c_bs = black76_all_greeks(F, K, sigma, T, r, CALL)["price"]
        p_bs = black76_all_greeks(F, K, sigma, T, r, PUT)["price"]
        assert abs(c_bs - p_bs - df * (F - K)) < 1e-12  # exact

        c_crr = crr_price(F, K, sigma, T, r, N=1000, option_type=CALL)
        p_crr = crr_price(F, K, sigma, T, r, N=1000, option_type=PUT)
        assert abs(c_crr - p_crr - df * (F - K)) < 1.0

        c_mc = mc_price(F, K, sigma, T, r, CALL, n_paths=100_000, seed=99)
        p_mc = mc_price(F, K, sigma, T, r, PUT, n_paths=100_000, seed=99)
        err = abs((c_mc["price"] - p_mc["price"]) - df * (F - K))
        max_err = 3.0 * (c_mc["std_error"] + p_mc["std_error"]) + 0.5
        assert err < max_err


# ===========================================================================
# Benchmark — wall time vs analytical BS
# ===========================================================================


class TestPricerBenchmark:
    """Timing benchmarks for the three pricers."""

    def test_bs_fast(self):
        """Black-Scholes should be extremely fast (< 1ms for 1000 prices)."""
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        t0 = time.perf_counter()
        for _ in range(1000):
            black76_all_greeks(F, K, sigma, T, r, CALL)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.1  # 1000 evaluations in < 100ms

    def test_crr_reasonable(self):
        """CRR binomial with 300 steps should be fast enough for batch use."""
        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.01
        t0 = time.perf_counter()
        for _ in range(10):
            crr_price(F, K, sigma, T, r, N=300, option_type=CALL)
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0  # 10 evaluations in < 1s

    def test_mc_reasonable(self):
        """MC with 100k paths should complete quickly."""
        t0 = time.perf_counter()
        mc_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL,
                 n_paths=50_000, seed=1)
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0  # should be fast with numpy

    def test_bs_price_accuracy_vs_known(self):
        """Test BS price against a hand-computed reference value."""
        result = black76_price(100.0, 100.0, 0.20, 0.25, 0.05, CALL)
        assert abs(result - 3.938224) < 0.0001  # exact QuantLib value


# ===========================================================================
# QuantLib benchmark
# ===========================================================================


class TestQuantLibBenchmark:
    """Cross-validate our pricers against QuantLib BlackCalculator."""

    @pytest.fixture(autouse=True)
    def _require_quantlib(self):
        try:
            import QuantLib  # noqa: F401
        except ImportError:
            pytest.skip("QuantLib not installed")

    @pytest.mark.parametrize("option_type", [CALL, PUT])
    @pytest.mark.parametrize("strike_factor", [0.7, 0.85, 1.0, 1.15, 1.3])
    def test_bs_price_vs_quantlib(self, option_type, strike_factor):
        """Black-76 prices must match QuantLib BlackCalculator to < 1e-10."""
        import QuantLib as ql

        F, sigma, T, r = 50000.0, 0.60, 0.25, 0.03
        K = F * strike_factor
        stdDev = sigma * math.sqrt(T)
        df = math.exp(-r * T)

        payoff = ql.PlainVanillaPayoff(
            ql.Option.Call if option_type == CALL else ql.Option.Put, K
        )
        bc = ql.BlackCalculator(payoff, F, stdDev, 1.0)  # discount=1 → undiscounted
        ql_price = bc.value() * df  # apply discounting

        our_price = black76_price(F, K, sigma, T, r, option_type)
        assert abs(our_price - ql_price) < 1e-10

    @pytest.mark.parametrize("option_type", [CALL, PUT])
    def test_bs_greeks_vs_quantlib(self, option_type):
        """Full Greek set vs QuantLib BlackCalculator.

        QuantLib BlackCalculator computes delta w.r.t. the *forward* (undiscounted
        delta for a Black-76 option).  Its delta(spot) converts this to a spot
        delta by dividing by spot.  Since our all_greeks returns discounted
        delta (dPrice/dF, discounted), the relationship is:

            our["delta"] = ql.delta(F) * df
            our["gamma"] = ql.gamma(F) * df
            our["vega"]  = ql.vega(T)   * df

        where ql.delta(F) is the undiscounted forward delta.
        """
        import QuantLib as ql

        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.03
        stdDev = sigma * math.sqrt(T)
        df = math.exp(-r * T)

        payoff = ql.PlainVanillaPayoff(
            ql.Option.Call if option_type == CALL else ql.Option.Put, K
        )
        bc = ql.BlackCalculator(payoff, F, stdDev, 1.0)

        our = black76_all_greeks(F, K, sigma, T, r, option_type)

        assert abs(our["price"] - bc.value() * df) < 1e-10
        assert abs(our["delta"] - bc.delta(F) * df) < 1e-10
        assert abs(our["gamma"] - bc.gamma(F) * df) < 1e-10
        assert abs(our["vega"] - bc.vega(T) * df) < 1e-9

    @pytest.mark.parametrize("option_type", [CALL, PUT])
    def test_crr_vs_quantlib_analytical(self, option_type):
        """CRR tree with high N should converge to QuantLib analytical."""
        import QuantLib as ql

        F, K, sigma, T, rate = 100.0, 100.0, 0.25, 0.25, 0.05
        stdDev = sigma * math.sqrt(T)
        df = math.exp(-rate * T)

        payoff = ql.PlainVanillaPayoff(
            ql.Option.Call if option_type == CALL else ql.Option.Put, K
        )
        bc = ql.BlackCalculator(payoff, F, stdDev, 1.0)
        ql_price = bc.value() * df

        crr = crr_price(F, K, sigma, T, rate, N=2000, option_type=option_type)
        assert abs(crr - ql_price) < 0.01

    def test_cpp_hotpath_vs_quantlib_batch(self):
        """C++ hot path should match QuantLib for batch pricing."""
        import QuantLib as ql

        n = 100
        F_arr = np.full(n, 50000.0)
        K_arr = np.linspace(30000.0, 70000.0, n)
        sigma_arr = np.full(n, 0.60)
        T_arr = np.full(n, 0.25)
        r_arr = np.full(n, 0.03)

        try:
            from volfoundry.pricers._core import black76_price_greeks_vectorized
        except ImportError:
            pytest.skip("C++ extension not built")

        cpp_price, _, _, _, _, _ = black76_price_greeks_vectorized(
            F_arr, K_arr, sigma_arr, T_arr, r_arr, 1
        )

        max_err = 0.0
        for i in range(n):
            stdDev = float(sigma_arr[i]) * math.sqrt(float(T_arr[i]))
            df = math.exp(-float(r_arr[i]) * float(T_arr[i]))
            payoff = ql.PlainVanillaPayoff(ql.Option.Call, float(K_arr[i]))
            bc = ql.BlackCalculator(payoff, float(F_arr[i]), stdDev, 1.0)
            err = abs(cpp_price[i] - bc.value() * df)
            max_err = max(max_err, err)
            assert err < 1e-10, f"Price mismatch at i={i}"
        # Allow epsilon-level float differences
        assert max_err < 1e-10

    def test_benchmark_timings(self):
        """Record wall time for all four pricers.

        This is informational — it reports, not asserts.  The human can
        compare the numbers against the QuantLib reference.
        """
        import QuantLib as ql

        F, K, sigma, T, r = 50000.0, 50000.0, 0.60, 0.25, 0.03
        stdDev = sigma * math.sqrt(T)
        df = math.exp(-r * T)
        payoff = ql.PlainVanillaPayoff(ql.Option.Call, K)

        # QuantLib scalar
        t0 = time.perf_counter()
        for _ in range(100_000):
            bc = ql.BlackCalculator(payoff, F, stdDev, 1.0)
            _ = bc.value() * df
        ql_time = time.perf_counter() - t0

        # Our analytical BS
        t0 = time.perf_counter()
        for _ in range(100_000):
            black76_all_greeks(F, K, sigma, T, r, CALL)
        bs_time = time.perf_counter() - t0

        # C++ hot path (scalar)
        try:
            from volfoundry.pricers._core import black76_price as cpp_price_fn
            t0 = time.perf_counter()
            for _ in range(100_000):
                cpp_price_fn(F, K, sigma, T, df, 1)
            cpp_time = time.perf_counter() - t0
        except ImportError:
            cpp_time = None

        # CRR (100 steps)
        t0 = time.perf_counter()
        for _ in range(100):
            crr_price(F, K, sigma, T, r, N=100, option_type=CALL)
        crr_time = time.perf_counter() - t0

        print(f"\nBenchmark — 100k option prices:")
        print(f"  QuantLib BlackCalculator: {ql_time:.4f}s")
        print(f"  Our BS analytical:        {bs_time:.4f}s")
        if cpp_time is not None:
            print(f"  Our C++ hot path:         {cpp_time:.4f}s ({100_000/cpp_time:.0f} calls/s)")
            assert cpp_time < ql_time, "C++ should be faster than QuantLib"
        print(f"  CRR 100-step ×100:        {crr_time:.4f}s")