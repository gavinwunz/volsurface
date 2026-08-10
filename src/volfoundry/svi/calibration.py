"""Zeliade quasi-explicit SVI calibration.

The calibration follows the Zeliade (2011) quasi-explicit method:

    1. OUTER: 2-parameter non-linear optimisation over (m, sigma).
    2. INNER:  For fixed (m, sigma), the SVI formula is linear in (a, b*rho, b):

         w(k) = a + b*rho * (k-m) + b * sqrt((k-m)^2 + sigma^2)

       Let  beta0 = a,  beta1 = b * rho,  beta2 = b.

       Then  w(k) = beta0 + beta1 * z1 + beta2 * z2

       where  z1 = k - m,  z2 = sqrt((k-m)^2 + sigma^2).

       This is a constrained linear least-squares problem:
         - b >= 0  (beta2 >= 0)
         - rho in (-1, 1)  => |beta1| < beta2
         - a >= 0  (beta0 >= 0, or at least a >= -b*sigma*sqrt(1-rho^2))

    3. Residuals are weighted by vega or inverse bid-ask spread (not unweighted mids).

The outer objective is:

    min_{m, sigma}  ||W * (w_observed - w_fitted(m, sigma))||^2

where the inner coefficients beta are the LLS solution at each (m, sigma) guess.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import numpy as np
from numpy.linalg import LinAlgError
from scipy.optimize import minimize

from volfoundry.svi.parameterization import (
    SviParams,
    clip_params_to_valid,
    svi_total_variance,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default bounds and tolerances
# ---------------------------------------------------------------------------

# m: typical range is a few std-devs of log-moneyness
# sigma: curvature, typically 0.01 - 2.0
DEFAULT_M_BOUNDS = (-5.0, 5.0)
DEFAULT_SIGMA_BOUNDS = (1e-6, 5.0)

# Regularisation: small penalty for deviation from prior
REG_LAMBDA = 1e-6


# ---------------------------------------------------------------------------
# Calibration result
# ---------------------------------------------------------------------------


@dataclass
class SviCalibrationResult:
    """Result of SVI calibration for a single expiry slice.

    Attributes
    ----------
    params : SviParams
        Calibrated SVI parameters.
    outer_success : bool
        Whether the outer optimisation converged.
    outer_message : str
        Optimizer termination message.
    r2 : float
        R-squared of the fitted total variance vs observed.
    rmse : float
        Root-mean-square error (weighted).
    rmse_unweighted : float
        Unweighted RMSE (for diagnostics).
    n_points : int
        Number of data points used for fitting.
    k_min, k_max : float
        Range of log-moneyness used.
    """

    params: SviParams
    outer_success: bool
    outer_message: str
    r2: float
    rmse: float
    rmse_unweighted: float
    n_points: int
    k_min: float
    k_max: float


# ---------------------------------------------------------------------------
# Inner: constrained linear least squares for (a, b*rho, b)
# ---------------------------------------------------------------------------


def _inner_lls(
    k: np.ndarray,
    w_observed: np.ndarray,
    weights: np.ndarray,
    m: float,
    sigma: float,
) -> Tuple[Optional[SviParams], float]:
    """Solve the inner linear least-squares problem for fixed (m, sigma).

    Parameters
    ----------
    k : ndarray, shape (n,)
        Log-moneyness values.
    w_observed : ndarray, shape (n,)
        Observed total implied variance: sigma_IV^2 * T.
    weights : ndarray, shape (n,)
        Observation weights (e.g. vega or inverse spread).
    m : float
        Current outer guess for horizontal shift.
    sigma : float
        Current outer guess for curvature.

    Returns
    -------
    params : SviParams or None
        Solved SVI parameters, or None if the problem is singular.
    objective : float
        Weighted sum of squared residuals.
    """
    z1 = k - m
    z2 = np.sqrt(z1**2 + sigma**2)

    # Design matrix: w = beta0 + beta1*z1 + beta2*z2
    # beta0 = a, beta1 = b*rho, beta2 = b
    W_diag = np.sqrt(weights)
    X = np.column_stack([np.ones_like(k), z1, z2])
    Xw = W_diag[:, None] * X
    yw = W_diag * w_observed

    try:
        beta, residuals, rank, singular = np.linalg.lstsq(Xw, yw, rcond=None)
    except LinAlgError:
        return None, np.inf

    beta0, beta1, beta2 = float(beta[0]), float(beta[1]), float(beta[2])

    # Recover a, b, rho with constraints.
    # Floor ``a`` at a tiny positive epsilon rather than 0.0: SviParams requires
    # a > 0, and on real (OTM-only) smiles the unconstrained intercept beta0 can
    # land at or below zero, which would otherwise raise inside the optimizer.
    a = max(beta0, 1e-8)
    b = max(beta2, 0.0)

    # Enforce |beta1| < beta2 for valid rho in (-1, 1)
    if b < 1e-15:
        rho = 0.0
        b = max(b, abs(beta1) + 0.001)  # ensure b >= |beta1|
    else:
        if abs(beta1) >= b:
            rho = np.sign(beta1) * 0.999
        else:
            rho = beta1 / b

    params = SviParams(a=a, b=b, rho=rho, m=m, sigma=sigma)

    # Compute weighted residual
    w_fitted = svi_total_variance(k, params)
    weighted_residuals = np.sqrt(weights) * (w_observed - w_fitted)
    objective = float(np.sum(weighted_residuals**2))

    return params, objective


# ---------------------------------------------------------------------------
# Outer objective for scipy.optimize
# ---------------------------------------------------------------------------


def _outer_objective(
    theta: np.ndarray,
    k: np.ndarray,
    w_observed: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Outer objective: sum of squared weighted residuals at optimal inner beta.

    Parameters
    ----------
    theta : ndarray, shape (2,)
        [m, sigma] — the two outer parameters.
    k, w_observed, weights : ndarray
        Calibration data.

    Returns
    -------
    float
        Weighted sum of squared residuals.
    """
    m, sigma_val = float(theta[0]), float(theta[1])
    sigma_val = max(sigma_val, 1e-12)
    _, obj = _inner_lls(k, w_observed, weights, m, sigma=sigma_val)
    if not np.isfinite(obj):
        # Penalise infeasible region heavily
        return 1e12 + (abs(m) + abs(sigma_val)) * 1e6
    return obj


# ---------------------------------------------------------------------------
# Main calibration entry point
# ---------------------------------------------------------------------------


def calibrate_svi_slice(
    k: np.ndarray,
    w_observed: np.ndarray,
    T: float,
    weights: Optional[np.ndarray] = None,
    m_init: Optional[float] = None,
    sigma_init: Optional[float] = None,
    m_bounds: Tuple[float, float] = DEFAULT_M_BOUNDS,
    sigma_bounds: Tuple[float, float] = DEFAULT_SIGMA_BOUNDS,
    method: str = "L-BFGS-B",
    outer_tol: float = 1e-8,
    max_iter: int = 500,
) -> SviCalibrationResult:
    """Calibrate raw SVI parameters for a single expiry slice.

    Uses the Zeliade quasi-explicit method:
    - OUTER: 2-parameter optimisation over (m, sigma)
    - INNER: Constrained linear least squares for (a, b, rho)

    Parameters
    ----------
    k : ndarray, shape (n,)
        Log-moneyness values, k = log(K/F).
    w_observed : ndarray, shape (n,)
        Observed total implied variance: sigma_IV^2 * T.
    T : float
        Time to expiry in years.
    weights : ndarray, optional
        Observation weights, same shape as k.  Default: equal weights.
        Should be vega or inverse bid-ask spread (NOT 1.0).
    m_init : float, optional
        Initial guess for m (default: weighted-mean of k).
    sigma_init : float, optional
        Initial guess for sigma (default: 0.1).
    m_bounds : tuple
        Bounds for m.
    sigma_bounds : tuple
        Bounds for sigma.
    method : str
        scipy.optimize.minimize method.
    outer_tol : float
        Tolerance for outer optimisation convergence.
    max_iter : int
        Maximum outer optimisation iterations.

    Returns
    -------
    SviCalibrationResult
    """
    n = len(k)
    if n < 4:
        raise ValueError(f"Need at least 4 data points for SVI calibration, got {n}")

    if weights is None:
        weights = np.ones(n)
    else:
        weights = np.asarray(weights, dtype=float)
        # Normalise weights so objective scale is interpretable
        weights = weights / np.mean(weights)

    # Initial guesses
    if m_init is None:
        m_init = float(np.average(k, weights=weights))
    if sigma_init is None:
        sigma_init = 0.1

    # Outer optimisation
    theta0 = np.array([m_init, sigma_init])
    bounds = [m_bounds, sigma_bounds]

    result = minimize(
        _outer_objective,
        theta0,
        args=(k, w_observed, weights),
        method=method,
        bounds=bounds,
        tol=outer_tol,
        options={"maxiter": max_iter, "ftol": outer_tol},
    )

    m_opt, sigma_opt = float(result.x[0]), max(float(result.x[1]), 1e-12)

    # Recover final parameters from inner solve
    final_params, final_obj = _inner_lls(k, w_observed, weights, m_opt, sigma=sigma_opt)

    if final_params is None:
        # Fallback: build params from bounds
        final_params = SviParams(
            a=float(np.mean(w_observed)),
            b=0.1,
            rho=0.0,
            m=m_opt,
            sigma=sigma_opt,
        )

    # Compute diagnostics
    w_fitted = svi_total_variance(k, final_params)

    # Weighted RMSE
    weighted_ss = float(np.sum(weights * (w_observed - w_fitted) ** 2))
    rmse = np.sqrt(weighted_ss / n)

    # Unweighted RMSE
    unweighted_ss = float(np.sum((w_observed - w_fitted) ** 2))
    rmse_unweighted = np.sqrt(unweighted_ss / n)

    # R-squared
    ss_tot = float(np.sum(weights * (w_observed - np.mean(w_observed)) ** 2))
    r2 = 1.0 - weighted_ss / ss_tot if ss_tot > 1e-15 else 0.0

    k_min, k_max = float(np.min(k)), float(np.max(k))

    return SviCalibrationResult(
        params=final_params,
        outer_success=result.success,
        outer_message=result.message,
        r2=float(r2),
        rmse=float(rmse),
        rmse_unweighted=float(rmse_unweighted),
        n_points=n,
        k_min=k_min,
        k_max=k_max,
    )


# ---------------------------------------------------------------------------
# Utility: build weights
# ---------------------------------------------------------------------------


def build_vega_weights(
    k: np.ndarray,
    T: float,
    F: float,
    r: float,
    sigma_guess: float = 0.5,
    option_type_strs: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Build observation weights proportional to Black-76 vega.

    Vega weights ensure the SVI fit prioritises strikes where the option
    price is most sensitive to volatility (ATM region).

    Parameters
    ----------
    k : ndarray
        Log-moneyness k = log(K/F).
    T : float
        Time to expiry.
    F : float
        Forward price.
    r : float
        Risk-free rate.
    sigma_guess : float
        Approximate ATM volatility for vega computation.
    option_type_strs : ndarray, optional
        Array of "C" or "P" strings for each observation.  Default: all Calls.

    Returns
    -------
    ndarray
        Normalised vega weights (sum to n).
    """
    from volfoundry.iv.black_scholes import black76_vega, OptionType

    n = len(k)
    weights = np.empty(n)
    K_array = F * np.exp(k)

    for i in range(n):
        ot = OptionType.CALL
        if option_type_strs is not None:
            ot = OptionType.CALL if option_type_strs[i] == "C" else OptionType.PUT
        v = black76_vega(F, float(K_array[i]), sigma_guess, T, r)
        weights[i] = max(v, 1e-15)

    # Normalise
    weights = weights / np.mean(weights)
    return weights


def build_inverse_spread_weights(
    bid: np.ndarray,
    ask: np.ndarray,
    floor: float = 1e-8,
) -> np.ndarray:
    """Build observation weights proportional to inverse bid-ask spread.

    Strikes with tight spreads get higher weight.

    Parameters
    ----------
    bid : ndarray
        Bid prices.
    ask : ndarray
        Ask prices.
    floor : float
        Minimum spread to avoid division by zero.

    Returns
    -------
    ndarray
        Normalised inverse-spread weights (sum to n).
    """
    spread = np.maximum(ask - bid, floor)
    weights = 1.0 / spread
    weights = weights / np.mean(weights)
    return weights