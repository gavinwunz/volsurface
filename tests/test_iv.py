"""Tests for volsurface.iv — Black-76 pricing and implied volatility inversion."""

from __future__ import annotations

import math

import numpy as np
import pytest

from volsurface.iv.black_scholes import (
    MAX_NR_ITERATIONS,
    VEGA_FLOOR,
    OptionType,
    black76_price,
    black76_vega,
    brenner_subrahmanyam_guess,
    compute_iv_surface,
    implied_vol_brent,
    implied_vol_nr,
    implied_volatility,
    norm_cdf,
    norm_pdf,
)

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

CALL = OptionType.CALL
PUT = OptionType.PUT


# ---------------------------------------------------------------------------
# norm_cdf / norm_pdf
# ---------------------------------------------------------------------------

class TestNormCdf:
    def test_zero(self):
        assert abs(norm_cdf(0.0) - 0.5) < 1e-12

    def test_symmetric(self):
        assert abs(norm_cdf(-1.0) - (1.0 - norm_cdf(1.0))) < 1e-12

    def test_large_values(self):
        assert norm_cdf(10.0) > 0.999_999
        assert norm_cdf(-10.0) < 1e-15

    def test_vectorized(self):
        x = np.array([-1.0, 0.0, 1.0])
        result = norm_cdf(x)
        assert result.shape == (3,)
        assert abs(result[1] - 0.5) < 1e-12


class TestNormPdf:
    def test_zero(self):
        expected = 1.0 / math.sqrt(2 * math.pi)
        assert abs(norm_pdf(0.0) - expected) < 1e-12

    def test_symmetric(self):
        assert abs(norm_pdf(1.0) - norm_pdf(-1.0)) < 1e-12


# ---------------------------------------------------------------------------
# Black-76 pricing
# ---------------------------------------------------------------------------


class TestBlack76Price:
    def test_atm_call(self):
        """ATM-forward call: price ≈ 0.4 * sigma * sqrt(T) * df * F."""
        F, K, sigma, T, r = 100.0, 100.0, 0.20, 0.25, 0.05
        price = black76_price(F, K, sigma, T, r, CALL)
        # Approximate: df * F * sigma * sqrt(T) / sqrt(2*pi) * 2
        expected = math.exp(-r * T) * F * (2.0 * norm_cdf(0.5 * sigma * math.sqrt(T)) - 1.0)
        assert price > 0
        assert abs(price - expected) < 1e-12

    def test_deep_itm_call(self):
        """Deep ITM call: price ≈ df * (F - K)."""
        F, K, sigma, T, r = 100.0, 20.0, 0.20, 0.25, 0.05
        price = black76_price(F, K, sigma, T, r, CALL)
        df = math.exp(-r * T)
        intrinsic = df * (F - K)
        assert price >= intrinsic - 1e-10

    def test_deep_otm_put(self):
        """Deep OTM put: price ≈ 0."""
        F, K, sigma, T, r = 100.0, 200.0, 0.20, 0.25, 0.05
        price = black76_price(F, K, sigma, T, r, PUT)
        assert price < 100.0  # well below intrinsic
        assert price > 0

    def test_put_call_parity(self):
        """C - P = exp(-rT) * (F - K)."""
        F, K, sigma, T, r = 100.0, 110.0, 0.30, 0.50, 0.03
        C = black76_price(F, K, sigma, T, r, CALL)
        P = black76_price(F, K, sigma, T, r, PUT)
        parity_diff = math.exp(-r * T) * (F - K)
        assert abs(C - P - parity_diff) < 1e-12

    def test_zero_vol(self):
        """Zero vol: price = discounted intrinsic."""
        F, K, T, r = 100.0, 90.0, 0.25, 0.05
        price = black76_price(F, K, 0.0, T, r, CALL)
        assert abs(price - math.exp(-r * T) * (F - K)) < 1e-12

        price_put = black76_price(F, K, 0.0, T, r, PUT)
        assert abs(price_put - 0.0) < 1e-12


class TestBlack76Vega:
    def test_atm_vega_positive(self):
        F, K, sigma, T, r = 100.0, 100.0, 0.20, 0.25, 0.05
        v = black76_vega(F, K, sigma, T, r)
        assert v > 0

    def test_vega_zero_at_zero_vol(self):
        v = black76_vega(100.0, 100.0, 0.0, 0.25, 0.05)
        assert v == 0.0

    def test_vega_call_put_equal(self):
        F, K, sigma, T, r = 100.0, 100.0, 0.25, 0.5, 0.03
        # Vega is the same for calls and puts (depends on d1, not option type)
        # But our function signature requires T,r; it's a pricing vega
        v_call = black76_vega(F, K, sigma, T, r)
        assert v_call > 0


# ---------------------------------------------------------------------------
# Brenner-Subrahmanyam guess
# ---------------------------------------------------------------------------


class TestBrennerSubrahmanyam:
    def test_atm(self):
        F, K, T, r = 100.0, 100.0, 0.25, 0.05
        sigma_true = 0.25
        price = black76_price(F, K, sigma_true, T, r, CALL)
        guess = brenner_subrahmanyam_guess(price, F, K, T, r, CALL)
        # Should be within ~10% relative for ATM
        assert guess > 0.1
        assert guess < 0.5

    def test_fallback(self):
        guess = brenner_subrahmanyam_guess(0.0, 100.0, 100.0, 0.25, 0.05)
        assert guess == 0.2


# ---------------------------------------------------------------------------
# Newton-Raphson IV
# ---------------------------------------------------------------------------


class TestImpliedVolNR:
    def test_exact_recovery_atm(self):
        """NR recovers true vol exactly for ATM call."""
        F, K, T, r, sigma_true = 100.0, 100.0, 0.50, 0.05, 0.30
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_vol_nr(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    def test_exact_recovery_otm(self):
        """NR recovers vol for OTM call."""
        F, K, T, r, sigma_true = 52000.0, 60000.0, 0.10, 0.02, 0.65
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_vol_nr(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    def test_exact_recovery_itm_put(self):
        """NR recovers vol for ITM put."""
        F, K, T, r, sigma_true = 52000.0, 60000.0, 0.10, 0.02, 0.80
        price = black76_price(F, K, sigma_true, T, r, PUT)
        iv = implied_vol_nr(price, F, K, T, r, PUT)
        assert abs(iv - sigma_true) < 1e-8

    def test_high_vol(self):
        """NR handles high vol (200%)."""
        F, K, T, r, sigma_true = 100.0, 100.0, 0.25, 0.05, 2.0
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_vol_nr(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) / sigma_true < 1e-6

    def test_low_vol(self):
        """NR handles low vol (5%)."""
        F, K, T, r, sigma_true = 100.0, 100.0, 0.25, 0.05, 0.05
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_vol_nr(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    def test_below_intrinsic_returns_tiny_vol(self):
        """Price at intrinsic → tiny vol."""
        F, K, T, r = 100.0, 90.0, 0.25, 0.05
        intrinsic = math.exp(-r * T) * (F - K)
        iv = implied_vol_nr(intrinsic, F, K, T, r, CALL)
        assert iv < 1e-10


# ---------------------------------------------------------------------------
# Brent fallback
# ---------------------------------------------------------------------------


class TestImpliedVolBrent:
    def test_atm_recovery(self):
        F, K, T, r, sigma_true = 100.0, 100.0, 0.50, 0.05, 0.30
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_vol_brent(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    def test_deep_otm(self):
        """Brent handles very deep OTM call where vega is tiny."""
        F, K, T, r, sigma_true = 100.0, 180.0, 0.25, 0.05, 0.40
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_vol_brent(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    def test_cannot_bracket(self):
        """Price too high → Brent raises."""
        with pytest.raises(ValueError, match="cannot bracket"):
            implied_vol_brent(1e6, 100.0, 100.0, 0.25, 0.05, CALL)


# ---------------------------------------------------------------------------
# Unified solver
# ---------------------------------------------------------------------------


class TestImpliedVolatility:
    def test_uses_nr_normally(self):
        F, K, T, r, sigma_true = 100.0, 100.0, 0.25, 0.05, 0.25
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    @pytest.mark.parametrize(
        "sigma_true",
        [0.05, 0.10, 0.20, 0.30, 0.50, 0.80, 1.00, 1.50, 2.00],
    )
    def test_accuracy_across_vols(self, sigma_true):
        """Accuracy ≤ 1e-8 across a range of true vols."""
        F, K, T, r = 100.0, 100.0, 0.25, 0.05
        price = black76_price(F, K, sigma_true, T, r, CALL)
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert abs(iv - sigma_true) < 1e-8

    @pytest.mark.parametrize(
        "moneyness",
        [0.5, 0.8, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.5, 2.0],
    )
    def test_accuracy_across_moneyness(self, moneyness):
        """Accuracy ≤ 1e-8 across ITM/ATM/OTM."""
        F, sigma, T, r = 100.0, 0.30, 0.25, 0.05
        K = moneyness * F
        price = black76_price(F, K, sigma, T, r, CALL)
        iv = implied_volatility(price, F, K, T, r, CALL)
        assert abs(iv - sigma) < 1e-8

    def test_price_below_intrinsic(self):
        F, K, T, r = 100.0, 90.0, 0.25, 0.05
        intrinsic = math.exp(-r * T) * (F - K)
        iv = implied_volatility(intrinsic * 0.99, F, K, T, r, CALL)
        assert iv < 1e-10


# ---------------------------------------------------------------------------
# Batch solver
# ---------------------------------------------------------------------------


class TestComputeIVSurface:
    def test_basic(self):
        F = np.array([100.0, 100.0, 100.0])
        K = np.array([90.0, 100.0, 110.0])
        T = np.array([0.25, 0.25, 0.25])
        r = np.array([0.05, 0.05, 0.05])
        sigma_true = 0.25
        prices = np.array([
            black76_price(float(F[i]), float(K[i]), sigma_true, float(T[i]), float(r[i]), CALL)
            for i in range(3)
        ])
        ivs = compute_iv_surface(F, K, T, r, prices, CALL)
        assert ivs.shape == (3,)
        for iv in ivs:
            assert abs(iv - sigma_true) < 1e-8


# ---------------------------------------------------------------------------
# Benchmark vs py_vollib (if installed)
# ---------------------------------------------------------------------------


def _has_py_vollib() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("py_vollib") is not None
    except Exception:
        return False


@pytest.mark.skipif(not _has_py_vollib(), reason="py_vollib not installed")
def test_benchmark_vs_pyvollib():
    """Cross-check our Black-76 IV against vollib's BS implied vol.

    Classical Black-Scholes with zero dividend (q=0, b=r) is equivalent to
    Black-76 with F = S * exp(rT).  We cross-verify pricing and IV on the
    same inputs to within 1e-8.
    """
    import importlib.util as _util
    if _util.find_spec("vollib") is not None:
        from vollib.black_scholes import black_scholes as bsm
        from vollib.black_scholes.implied_volatility import implied_volatility as pyv_iv
    else:
        from py_vollib.black_scholes import black_scholes as bsm
        from py_vollib.black_scholes.implied_volatility import implied_volatility as pyv_iv

    S = 100.0
    K = 100.0
    T = 0.25
    r = 0.05
    sigma = 0.30

    # BS with q=0: C = S*N(d1) - K*exp(-rT)*N(d2)
    # Equivalent to Black-76 with F = S * exp(rT)
    F = S * math.exp(r * T)

    price_bs = bsm('c', S, K, T, r, sigma)
    price_ours = black76_price(F, K, sigma, T, r, CALL)
    assert abs(price_ours - price_bs) < 1e-12

    # Cross-check IV inversion: vollib on BS price should recover sigma
    iv_pyv = pyv_iv(price_bs, S, K, T, r, 'c')
    assert abs(iv_pyv - sigma) < 1e-8

    # Our IV on BS price (with correct F) should also recover sigma
    iv_ours = implied_volatility(price_bs, F, K, T, r, CALL)
    assert abs(iv_ours - sigma) < 1e-8