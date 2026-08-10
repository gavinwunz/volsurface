"""Monte Carlo pricer with antithetic variates and Black-Scholes control variate.

The MC engine simulates the forward price F under the risk-neutral measure:

    dF = sigma * F * dW

which, via Ito's lemma, integrates to:

    F_T = F_0 * exp(-0.5 * sigma^2 * T + sigma * sqrt(T) * Z)

where Z ~ N(0, 1).  Option payoffs are then discounted:

    C = exp(-rT) * E[max(F_T - K, 0)]
    P = exp(-rT) * E[max(K - F_T, 0)]

Variance reduction
------------------
1. **Antithetic variates**: For each draw Z, also use -Z.  The pair (F_T(Z),
   F_T(-Z)) is perfectly negatively correlated in the Gaussian case,
   reducing the variance of the sample mean by roughly a factor of 2.

2. **Black-Scholes delta-hedged control variate**: For each path we form
   the discounted delta-hedged portfolio P&L:

       CV_i = df * [ payoff_i - delta_BS * (F_T_i - F) ]

   where delta_BS is the analytical Black-76 delta.  Since E[F_T] = F
   under the forward measure, E[CV_i] = E[discounted_payoff_i] = C_true,
   and Var(CV_i) << Var(discounted_payoff_i) because the linear term
   absorbs first-order randomness.

   A second-level control variate (F_T itself) is applied on the hedged
   residuals to eliminate any remaining linear dependence, giving near
   machine-precision convergence with moderate N.

Standard errors are reported alongside the price estimate.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional, Tuple

import numpy as np

from volsurface.iv.black_scholes import OptionType, black76_price, norm_cdf


def _generate_paths(
    F: float,
    sigma: float,
    T: float,
    n_paths: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate terminal forward prices F_T for n_paths independent draws.

    Uses antithetic pairs internally: draws n_paths/2 independent Z, then
    appends -Z for the other half.  Returns an array of length n_paths.
    """
    half = n_paths // 2
    Z = rng.standard_normal(half)
    # Antithetic: use -Z for the second half
    Z_all = np.concatenate([Z, -Z])

    # If odd, add one extra independent draw
    if n_paths % 2 == 1:
        extra = rng.standard_normal(1)
        Z_all = np.concatenate([Z_all, extra])

    F_T = F * np.exp(-0.5 * sigma * sigma * T + sigma * math.sqrt(T) * Z_all)
    return F_T


def mc_price(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
    n_paths: int = 100_000,
    seed: Optional[int] = None,
    use_control_variate: bool = True,
) -> dict[str, float]:
    """Price a European option via Monte Carlo with variance reduction.

    Parameters
    ----------
    F : float
        Forward price.
    K : float
        Strike.
    sigma : float
        Volatility (decimal).
    T : float
        Time to expiry in years.
    r : float
        Risk-free / discount rate (continuous).
    option_type : OptionType
        CALL or PUT.
    n_paths : int
        Number of Monte Carlo paths (default 100,000). Rounded up to an even
        number for antithetic pairing.
    seed : int, optional
        RNG seed for reproducibility.
    use_control_variate : bool
        If True (default), apply the Black-Scholes control variate.

    Returns
    -------
    dict
        Keys: price, std_error, price_raw, bs_control_price.
        - price: the variance-reduced estimate (or raw MC if use_control_variate=False).
        - std_error: standard error of the estimate.
        - price_raw: raw MC average before control variate adjustment.
        - bs_control_price: analytical BS price used as control.
    """
    if sigma <= 0 or T <= 0 or F <= 0 or K <= 0:
        df = math.exp(-r * T)
        if option_type == OptionType.CALL:
            p = float(df * max(F - K, 0.0))
        else:
            p = float(df * max(K - F, 0.0))
        return {"price": p, "std_error": 0.0, "price_raw": p, "bs_control_price": p}

    # Ensure even number of paths for clean antithetic pairing
    n_paths = max(n_paths, 2)
    if n_paths % 2 != 0:
        n_paths += 1

    rng = np.random.default_rng(seed)
    df = math.exp(-r * T)

    # ------------------------------------------------------------------
    # Generate paths and payoffs
    # ------------------------------------------------------------------
    F_T = _generate_paths(F, sigma, T, n_paths, rng)

    if option_type == OptionType.CALL:
        payoffs = np.maximum(F_T - K, 0.0)
    else:
        payoffs = np.maximum(K - F_T, 0.0)

    discounted = df * payoffs
    price_raw = float(np.mean(discounted))

    # Raw standard error
    std_raw = float(np.std(discounted, ddof=1) / math.sqrt(n_paths))

    if not use_control_variate:
        return {
            "price": price_raw,
            "std_error": std_raw,
            "price_raw": price_raw,
            "bs_control_price": black76_price(F, K, sigma, T, r, option_type),
        }

    # ------------------------------------------------------------------
    # Black-Scholes delta-hedged control variate
    # ------------------------------------------------------------------
    # For each path i we form the delta-hedged portfolio P&L:
    #
    #   CV_i = df * [ payoff_i - delta_BS * (F_T_i - F) ]
    #
    # where delta_BS = df * N(d1) for calls, df * (N(d1) - 1) for puts
    # (the *discounted* Black-76 delta, consistent with black76_delta()).
    #
    # Because E[F_T] = F (martingale in the forward measure), we have:
    #
    #   E[payoff_i] = E[CV_i]
    #
    # and Var(CV_i) << Var(payoff_i) since the linear term delta_BS*(F_T-F)
    # absorbs most of the first-order randomness in the payoff.
    #
    # We also apply the optimal beta scaling (F_T as a second control
    # variate, orthogonalised) for any residual variance.
    #
    # References
    # ----------
    # Glasserman, P. (2003). Monte Carlo Methods in Financial Engineering.
    #   Springer.  Section 4.1 (control variates), Section 4.2 (delta-hedged
    #   control variates for option pricing).

    # Compute the discounted Black-76 delta for the control variate
    d1 = math.log(F / K) / (sigma * math.sqrt(T)) + 0.5 * sigma * math.sqrt(T)
    if option_type == OptionType.CALL:
        delta_bs = df * norm_cdf(d1)
    else:
        delta_bs = df * (norm_cdf(d1) - 1.0)

    # Delta-hedged portfolio values
    hedged = discounted - delta_bs * (F_T - F)

    # Optional: further reduce variance by regressing hedged values
    # against F_T (second-level control variate for any remaining linear
    # dependence).  This is cheap and improves convergence slightly.
    hedged_centered = hedged - np.mean(hedged)
    f_centered = F_T - F
    cov_hf = np.mean(hedged_centered * f_centered)
    var_f = np.mean(f_centered * f_centered)

    if var_f > 1e-20:
        beta2 = cov_hf / var_f
        adjusted = hedged - beta2 * f_centered
    else:
        adjusted = hedged

    price_cv = float(np.mean(adjusted))
    std_cv = float(np.std(adjusted, ddof=1) / math.sqrt(n_paths))

    return {
        "price": price_cv,
        "std_error": std_cv,
        "price_raw": price_raw,
        "bs_control_price": black76_price(F, K, sigma, T, r, option_type),
    }


def mc_price_with_confidence(
    F: float,
    K: float,
    sigma: float,
    T: float,
    r: float,
    option_type: OptionType = OptionType.CALL,
    n_paths: int = 1_000_000,
    seed: Optional[int] = None,
) -> dict[str, float]:
    """Higher-precision MC with 95% confidence interval.

    Returns a dict with price, std_error, ci_lower, ci_upper.
    """
    result = mc_price(F, K, sigma, T, r, option_type, n_paths, seed)
    ci_half = 1.96 * result["std_error"]
    return {
        "price": result["price"],
        "std_error": result["std_error"],
        "ci_lower": result["price"] - ci_half,
        "ci_upper": result["price"] + ci_half,
    }