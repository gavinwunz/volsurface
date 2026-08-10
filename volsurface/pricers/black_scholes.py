"""Black-Scholes / Black-76 pricer with full Greeks.

Implements European call and put pricing under the Black-76 (futures/forwards)
formulation, which is the natural setting for the volsurface pipeline since
forwards are extracted from put-call parity.

Formulas
--------
Let df = exp(-rT), d1 = (ln(F/K) + sigma^2*T/2) / (sigma*sqrt(T)), d2 = d1 - sigma*sqrt(T).
Let N'(x) = exp(-x^2/2) / sqrt(2*pi).

    Call  = df * [F*N(d1) - K*N(d2)]
    Put   = df * [K*N(-d2) - F*N(-d1)]

Greeks (all reported as derivatives of the *undiscounted* option value divided
by df, i.e. per unit of discount factor; multiply by df to get the usual
discounted Greeks):

    Delta_call  = N(d1)                     Delta_put  = N(d1) - 1
    Gamma       = N'(d1) / (F * sigma * sqrt(T))   (same for call and put)
    Vega        = F * sqrt(T) * N'(d1)      (same; sensitivity to sigma)
    Theta_call  = -(F*sigma*N'(d1)) / (2*sqrt(T))  (undiscounted)
    Theta_put   = Theta_call
                  Note: Theta here is partial derivative w.r.t. T,
                  not the time-decay with discounting included.
    Rho_call    = K * T * df * N(d2)        Rho_put  = -K * T * df * N(-d2)

All functions accept scalar inputs and return scalars.  Vectorised variants
are provided for batch pricing and Greeks computations.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional, Union

import numpy as np

from volsurface.iv.black_scholes import (  # shared primitives
    OptionType,
    SQRT2PI,
    black76_price,
    black76_vega,
    norm_cdf,
    norm_pdf,
)

# ---------------------------------------------------------------------------
# Public re-exports for convenience
# ---------------------------------------------------------------------------

__all__ = [
    "OptionType",
    "black76_price",
    "black76_vega",
    "norm_cdf",
    "norm_pdf",
    "black76_delta",
    "black76_gamma",
    "black76_theta",
    "black76_rho",
    "black76_all_greeks",
    "price_and_greeks_vectorized",
    "parity_check_call",
    "parity_check_put",
]


# ---------------------------------------------------------------------------
# Individual Greeks
# ---------------------------------------------------------------------------


def black76_delta(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
) -> float:
    """Black-76 Delta — sensitivity of undiscounted option value to F.

    Delta_call  = N(d1)
    Delta_put   = N(d1) - 1
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        if option_type == OptionType.CALL:
            return 1.0 if F > K else 0.0
        else:
            return -1.0 if K > F else 0.0

    sigma_sqrt_T = sigma * math.sqrt(T)
    d1 = math.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T

    if option_type == OptionType.CALL:
        return float(norm_cdf(d1))
    else:
        return float(norm_cdf(d1) - 1.0)


def black76_gamma(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
) -> float:
    """Black-76 Gamma — second derivative w.r.t. F (same for call/put).

    Gamma = N'(d1) / (F * sigma * sqrt(T))
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        return 0.0

    sigma_sqrt_T = sigma * math.sqrt(T)
    d1 = math.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T
    return float(norm_pdf(d1) / (F * sigma_sqrt_T))


def black76_theta(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
) -> float:
    """Black-76 Theta — partial derivative of the undiscounted price w.r.t. T.

    Theta = -(F * sigma * N'(d1)) / (2 * sqrt(T))

    This is the *undiscounted* theta.  To get the usual time-decay including
    the discounting effect, compute:

        theta_discounted = df * theta_undiscounted - r * df * price_undiscounted

    where df = exp(-rT) and price_undiscounted = price / df.
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        return 0.0

    sigma_sqrt_T = sigma * math.sqrt(T)
    d1 = math.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T
    return float(-F * sigma * norm_pdf(d1) / (2.0 * math.sqrt(T)))


def black76_rho(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
) -> float:
    """Black-76 Rho — sensitivity of the *discounted* price to r.

    Rho_call  = -T * price
    Rho_put   = -T * price

    In the Black-76 formulation, r only appears via the discount factor df = exp(-rT).
    Therefore dPrice/dr = -T * Price for both calls and puts.
    """
    price = black76_price(F, K, sigma, T, r, option_type)
    return float(-T * price)


# ---------------------------------------------------------------------------
# All Greeks in one call
# ---------------------------------------------------------------------------


def black76_all_greeks(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
) -> dict[str, float]:
    """Compute price and all Greeks for a single Black-76 option.

    Returns a dictionary with keys:
        price, delta, gamma, vega, theta, rho

    All Greeks are the standard *discounted* sensitivities consistent with
    the existing black76_vega / black76_price in volsurface.iv.
    Delta and gamma are per unit of F (not per unit of df).
    Theta is the time-decay including discounting.
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        # Degenerate case
        df = math.exp(-r * T)
        if option_type == OptionType.CALL:
            intrinsic = max(F - K, 0.0)
        else:
            intrinsic = max(K - F, 0.0)
        return {
            "price": float(df * intrinsic),
            "delta": float(df if option_type == OptionType.CALL and F > K else
                           (-df if option_type == OptionType.PUT and K > F else 0.0)),
            "gamma": 0.0,
            "vega": 0.0,
            "theta": 0.0,
            "rho": float(-T * df * intrinsic),
        }

    sigma_sqrt_T = sigma * math.sqrt(T)
    d1 = math.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T
    d2 = d1 - sigma_sqrt_T
    df = math.exp(-r * T)

    sqrt_t = math.sqrt(T)
    npdf_d1 = norm_pdf(d1)

    if option_type == OptionType.CALL:
        nd1 = norm_cdf(d1)
        nd2 = norm_cdf(d2)
        price = float(df * (F * nd1 - K * nd2))
        delta = float(df * nd1)
        theta = float(-F * sigma * npdf_d1 / (2.0 * sqrt_t) * df
                      + r * F * nd1 * df
                      - r * K * nd2 * df)
    else:
        nd1 = norm_cdf(d1)
        nd2 = norm_cdf(d2)
        n_nd1 = norm_cdf(-d1)
        n_nd2 = norm_cdf(-d2)
        price = float(df * (K * n_nd2 - F * n_nd1))
        delta = float(df * (nd1 - 1.0))
        theta = float(-F * sigma * npdf_d1 / (2.0 * sqrt_t) * df
                      - r * F * n_nd1 * df
                      + r * K * n_nd2 * df)

    gamma = float(df * npdf_d1 / (F * sigma_sqrt_T))
    vega = float(df * F * sqrt_t * npdf_d1)
    rho = -T * price

    return {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
        "rho": rho,
    }


# ---------------------------------------------------------------------------
# Vectorised pricing and Greeks
# ---------------------------------------------------------------------------


def price_and_greeks_vectorized(
    F: np.ndarray,
    K: np.ndarray,
    sigma: np.ndarray,
    T: np.ndarray,
    r: np.ndarray,
    option_type: OptionType = OptionType.CALL,
) -> dict[str, np.ndarray]:
    """Vectorised Black-76 price and Greeks for arrays of option parameters.

    All input arrays must be the same shape.

    Returns a dictionary with keys price, delta, gamma, vega, theta, rho,
    each an ndarray of the same shape as the inputs.
    """
    F = np.asarray(F, dtype=np.float64)
    K = np.asarray(K, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)

    sigma_sqrt_T = sigma * np.sqrt(T)
    d1 = np.log(F / K) / sigma_sqrt_T + 0.5 * sigma_sqrt_T
    d2 = d1 - sigma_sqrt_T

    df = np.exp(-r * T)
    npdf_d1 = norm_pdf(d1)

    if option_type == OptionType.CALL:
        nd1 = norm_cdf(d1)
        nd2 = norm_cdf(d2)
        price = df * (F * nd1 - K * nd2)
        delta = nd1
    else:
        nd1 = norm_cdf(d1)
        nd2 = norm_cdf(d2)
        price = df * (K * (1.0 - nd2) - F * (1.0 - nd1))
        delta = nd1 - 1.0

    gamma = npdf_d1 / (F * sigma_sqrt_T)
    vega = F * np.sqrt(T) * npdf_d1
    theta = -F * sigma * npdf_d1 / (2.0 * np.sqrt(T))
    rho_g = -T * price

    return {
        "price": price,
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
        "rho": rho_g,
    }


# ---------------------------------------------------------------------------
# Put-call parity verification helpers
# ---------------------------------------------------------------------------


def parity_check_call(
    put_price: float,
    F: float,
    K: float,
    T: float,
    r: float,
) -> float:
    """Compute call price from put via put-call parity: C = P + df*(F - K)."""
    df = math.exp(-r * T)
    return put_price + df * (F - K)


def parity_check_put(
    call_price: float,
    F: float,
    K: float,
    T: float,
    r: float,
) -> float:
    """Compute put price from call via put-call parity: P = C - df*(F - K)."""
    df = math.exp(-r * T)
    return call_price - df * (F - K)