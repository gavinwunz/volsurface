"""Black-Scholes pricing and implied volatility inversion.

Uses the Black-76 (Black model for futures/forwards) formulation since the
data layer recovers the forward price F via put-call parity.  This makes
dividend/carry treatment consistent: all rates and yields are embedded in
the discount factor exp(-rT) and the forward F.

Formulas:

    d1 = (ln(F/K) + sigma^2 * T / 2) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)

    Call  = exp(-rT) * [F * N(d1) - K * N(d2)]
    Put   = exp(-rT) * [K * N(-d2) - F * N(-d1)]
    Vega  = exp(-rT) * F * sqrt(T) * N'(d1)

where N'(x) = exp(-x^2/2) / sqrt(2*pi) is the standard normal density.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SQRT2PI = math.sqrt(2 * math.pi)
IV_CONVERGENCE_TOL = 1e-10  # vol tolerance for Newton-Raphson iteration
MAX_NR_ITERATIONS = 100
VEGA_FLOOR = 1e-12  # below this, switch to Brent bracketing


class OptionType(Enum):
    CALL = "C"
    PUT = "P"


# ---------------------------------------------------------------------------
# Black-76 pricing
# ---------------------------------------------------------------------------


def norm_cdf(x: np.ndarray | float) -> np.ndarray | float:
    """Standard normal CDF via erf.  Vectorised."""
    if isinstance(x, (int, float)):
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2)))
    # Use scipy.special.erf for vectorized
    from scipy.special import erf as scipy_erf
    return 0.5 * (1.0 + scipy_erf(x / math.sqrt(2)))


def norm_pdf(x: np.ndarray | float) -> np.ndarray | float:
    """Standard normal PDF."""
    if isinstance(x, (int, float)):
        return math.exp(-0.5 * float(x) * float(x)) / SQRT2PI
    return np.exp(-0.5 * x * x) / SQRT2PI


def black76_price(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
) -> float:
    """Black-76 price for a European option on a forward/future.

    Parameters
    ----------
    F : float
        Forward price of the underlying.
    K : float
        Strike price.
    sigma : float
        Implied volatility (decimal, e.g. 0.50 for 50%).
    T : float
        Time to expiry in years.
    r : float
        Risk-free / discount rate (continuous).
    option_type : OptionType
        CALL or PUT.

    Returns
    -------
    float
        Option price.
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        # Degenerate case: handle at boundaries
        df = math.exp(-r * T)
        if option_type == OptionType.CALL:
            return float(df * max(F - K, 0.0))
        else:
            return float(df * max(K - F, 0.0))

    sigma_sqrt_T = sigma * math.sqrt(T)
    d1 = math.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T
    d2 = d1 - sigma_sqrt_T
    df = math.exp(-r * T)

    if option_type == OptionType.CALL:
        return float(df * (F * norm_cdf(d1) - K * norm_cdf(d2)))
    else:
        return float(df * (K * norm_cdf(-d2) - F * norm_cdf(-d1)))


def black76_vega(F: float, K: float, sigma: float, T: float, r: float) -> float:
    """Vega of a Black-76 option (sensitivity to sigma).

    Parameters
    ----------
    F, K, sigma, T, r : float
        Same as black76_price.

    Returns
    -------
    float
        Vega = df * F * sqrt(T) * N'(d1).
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        return 0.0

    sigma_sqrt_T = sigma * math.sqrt(T)
    d1 = math.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T
    df = math.exp(-r * T)
    return float(df * F * math.sqrt(T) * norm_pdf(d1))


# ---------------------------------------------------------------------------
# Brenner-Subrahmanyam initial guess
# ---------------------------------------------------------------------------


def brenner_subrahmanyam_guess(
    price: float,
    F: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
) -> float:
    """Brenner-Subrahmanyam (1988) approximation for ATM or near-ATM IV.

    For an at-the-money-forward option:
        sigma ≈ price * sqrt(2*pi/T) / (F * df)

    This gives a very good starting point for Newton-Raphson.

    Parameters
    ----------
    price : float
        Observed market price (mid).
    F, K, T, r : same as black76_price.
    option_type : OptionType

    Returns
    -------
    float
        Approximate implied volatility (clamped to [1e-8, 10.0]).
    """
    df = math.exp(-r * T)
    if F <= 0 or T <= 0 or df <= 0 or price <= 0:
        return 0.2  # fallback: 20% vol

    # ATM-forward approximation: sigma ≈ price * sqrt(2π/T) / (F * df)
    sigma_guess = abs(price) * math.sqrt(2 * math.pi / max(T, 1e-10)) / (F * df)

    # Clamp to sensible range
    sigma_guess = max(1e-8, min(sigma_guess, 10.0))
    return sigma_guess


# ---------------------------------------------------------------------------
# Newton-Raphson implied volatility solver
# ---------------------------------------------------------------------------


def implied_vol_nr(
    price: float,
    F: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
    tol: float = IV_CONVERGENCE_TOL,
    max_iter: int = MAX_NR_ITERATIONS,
) -> float:
    """Newton-Raphson iterative IV solver.

    Parameters
    ----------
    price : float
        Market option price to invert.
    F, K, T, r : float
        See black76_price.
    option_type : OptionType
    tol : float
        Convergence tolerance on sigma (default 1e-10).
    max_iter : int
        Maximum iterations (default 100).

    Returns
    -------
    float
        Implied volatility.

    Raises
    ------
    ValueError
        If the solver does not converge within max_iter iterations.
    """
    # Price bounds check
    df = math.exp(-r * T)
    intrinsic = df * max(0.0, F - K) if option_type == OptionType.CALL else df * max(0.0, K - F)

    if price <= intrinsic:
        # Price below intrinsic — return tiny vol
        return 1e-12

    sigma = brenner_subrahmanyam_guess(price, F, K, T, r, option_type)

    for i in range(max_iter):
        model_price = black76_price(F, K, sigma, T, r, option_type)
        diff = model_price - price

        vega = black76_vega(F, K, sigma, T, r)

        if abs(vega) < VEGA_FLOOR:
            # Fall through to Brent bracketing
            raise ValueError(
                "Vega too small for NR; use Brent bracketing fallback."
            )

        # Newton step: sigma_new = sigma - (C_mkt - C_model) / vega
        delta_sigma = -diff / vega

        # Clamp to prevent runaway steps from tiny vega in deep ITM/OTM
        max_step = sigma * 0.5  # limit to 50% step
        if abs(delta_sigma) > max_step:
            delta_sigma = max_step if delta_sigma > 0 else -max_step

        # Line-search adjustment: halve step if new sigma would be near zero
        step_scale = 1.0
        while sigma + step_scale * delta_sigma <= 1e-10 and step_scale > 1e-6:
            step_scale *= 0.5

        sigma_new = sigma + step_scale * delta_sigma
        sigma_new = max(sigma_new, 1e-10)

        # Check sigma convergence FIRST (target: 1e-8 vol accuracy)
        if abs(sigma_new - sigma) < tol:
            return sigma_new

        # Also check price convergence
        if abs(diff) < tol * max(price, 1e-8):
            if abs(sigma_new - sigma) < tol:
                return sigma_new

        sigma = sigma_new

    raise ValueError(
        f"Newton-Raphson did not converge within {max_iter} iterations "
        f"(price={price}, F={F}, K={K}, T={T:.4f}, r={r:.4f})."
    )


# ---------------------------------------------------------------------------
# Brent bracketing fallback
# ---------------------------------------------------------------------------


def implied_vol_brent(
    price: float,
    F: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
    tol: float = IV_CONVERGENCE_TOL,
    sigma_lo: float = 1e-10,
    sigma_hi: float = 10.0,
) -> float:
    """Brent's method for implied volatility — robust fallback.

    Parameters
    ----------
    price, F, K, T, r, option_type : same as black76_price.
    tol : float
        Convergence tolerance.
    sigma_lo, sigma_hi : float
        Bracketing bounds on sigma.

    Returns
    -------
    float
        Implied volatility.

    Raises
    ------
    ValueError
        If price cannot be bracketed in [sigma_lo, sigma_hi].
    """
    df = math.exp(-r * T)

    def f(sigma: float) -> float:
        return black76_price(F, K, sigma, T, r, option_type) - price

    f_lo = f(sigma_lo)
    f_hi = f(sigma_hi)

    if f_lo * f_hi > 0:
        # Try to widen the bracket
        found_bracket = False
        for _ in range(20):
            sigma_hi *= 2.0
            if sigma_hi > 100.0:
                break
            f_hi = f(sigma_hi)
            if f_lo * f_hi <= 0:
                found_bracket = True
                break
        if not found_bracket:
            raise ValueError(
                f"Brent: cannot bracket IV. f({sigma_lo})={f_lo:.6e}, "
                f"f({sigma_hi})={f_hi:.6e}, price={price}."
            )

    # Simple Brent-style implementation
    a, b = sigma_lo, sigma_hi
    fa, fb = f_lo, f_hi

    if abs(fa) < abs(fb):
        a, b = b, a
        fa, fb = fb, fa

    c, fc = a, fa
    d = b - a
    e = d
    mflag = True

    for _ in range(200):
        if abs(b - a) < tol:
            return (a + b) / 2.0

        if abs(fb) < tol * abs(price):
            return b

        if fa != fc and fb != fc:
            # Inverse quadratic interpolation
            s = a * fb * fc / ((fa - fb) * (fa - fc)) + \
                b * fa * fc / ((fb - fa) * (fb - fc)) + \
                c * fa * fb / ((fc - fa) * (fc - fb))
        else:
            # Secant
            s = b - fb * (b - a) / (fb - fa)

        cond1 = not ((3 * a + b) / 4.0 < s < b or b < s < (3 * a + b) / 4.0)
        cond2 = mflag and abs(s - b) >= abs(b - c) / 2.0
        cond3 = not mflag and abs(s - b) >= abs(c - d) / 2.0
        cond4 = mflag and abs(b - c) < tol
        cond5 = not mflag and abs(c - d) < tol

        if cond1 or cond2 or cond3 or cond4 or cond5:
            s = (a + b) / 2.0
            mflag = True
        else:
            mflag = False

        fs = f(s)
        d, c = c, b
        fc = fb

        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs

        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa

    raise ValueError(f"Brent exceeded max iterations; price={price}, F={F}, K={K}.")


# ---------------------------------------------------------------------------
# Unified solver
# ---------------------------------------------------------------------------


def implied_volatility(
    price: float,
    F: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
    tol: float = IV_CONVERGENCE_TOL,
) -> float:
    """Compute implied volatility, trying Newton-Raphson first, then Brent.

    This is the recommended entry point for IV inversion.

    Parameters
    ----------
    price, F, K, T, r, option_type, tol : see individual solvers.

    Returns
    -------
    float
        Implied volatility (decimal).
    """
    # Quick sanity: price <= intrinsic → zero vol
    df = math.exp(-r * T)
    if option_type == OptionType.CALL:
        intrinsic = df * max(0.0, F - K)
    else:
        intrinsic = df * max(0.0, K - F)

    if price <= intrinsic + 1e-15:
        return 1e-12

    try:
        return implied_vol_nr(price, F, K, T, r, option_type, tol)
    except ValueError:
        return implied_vol_brent(price, F, K, T, r, option_type, tol)


# ---------------------------------------------------------------------------
# Batch solver
# ---------------------------------------------------------------------------


def compute_iv_surface(
    F_array: np.ndarray,
    K_array: np.ndarray,
    T_array: np.ndarray,
    r_array: np.ndarray,
    price_array: np.ndarray,
    option_type: OptionType,
    tol: float = IV_CONVERGENCE_TOL,
) -> np.ndarray:
    """Vectorised convenience wrapper — computes IV for an array of quotes.

    Parameters
    ----------
    F_array, K_array, T_array, r_array, price_array : ndarray
        Arrays of the same length.
    option_type : OptionType
    tol : float

    Returns
    -------
    ndarray
        Implied volatilities, same length as inputs.
    """
    results = np.empty(len(F_array))
    for i in range(len(F_array)):
        results[i] = implied_volatility(
            float(price_array[i]),
            float(F_array[i]),
            float(K_array[i]),
            float(T_array[i]),
            float(r_array[i]),
            option_type,
            tol,
        )
    return results