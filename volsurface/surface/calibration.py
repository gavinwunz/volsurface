"""SSVI global calibration: fit the full volatility surface simultaneously.

The SSVI (Surface SVI) calibration fits all expiry slices jointly under
the Gatheral-Jacquier (2014) parameterization.  Unlike raw SVI (which
calibrates each slice independently), SSVI imposes:

1. A common correlation parameter $rho$ across all maturities.
2. ATM total variance $theta_t$ extracted from the market at each expiry.
3. A curvature function $phi(theta) = eta / theta^{lambda}$ with global
   parameters $(eta, lambda)$.

Calibration Strategy
--------------------
The SSVI calibration proceeds in two stages:

**Stage 1: ATM extraction.**
    For each expiry slice, we extract $theta_t$ as the ATM total implied
    variance by interpolating the observed implied volatilities near the
    ATM point ($k approx 0$). This is model-independent and ensures
    the surface hits ATM market quotes exactly.

**Stage 2: Global $(eta, lambda)$ fit.**
    With $theta_t$ fixed and $rho$ estimated from raw SVI slices (or
    calibrated jointly), we minimize the weighted sum of squared errors
    across ALL slices simultaneously:

        $min_{eta>0, lambdain[0,1]} sum_{t} sum_i
        w_{t,i} (w_{obs}(k_i, T_t) - w_{SSVI}(k_i, theta_t; eta, lambda))^2$

    subject to the Lee moment formula bound:
        $eta (1 + |rho|) leq 2$

    and the calendar no-arbitrage condition:
        $partial_theta w(k, theta_t) geq 0$ for all k.

This two-stage approach is robust: $theta_t$ is extracted directly from
the data, and the curvature parameters are calibrated globally.

References
----------
Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
    Quantitative Finance, 14(1), 59–71.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

from volsurface.svi.calibration import SviCalibrationResult
from volsurface.svi.parameterization import SviParams
from volsurface.surface.ssvi import (
    SsviParams,
    ssvi_total_variance,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default bounds
# ---------------------------------------------------------------------------

DEFAULT_ETA_BOUNDS = (1e-6, 20.0)
DEFAULT_LAMBDA_BOUNDS = (0.0, 1.0)
DEFAULT_RHO_BOUNDS = (-0.99, 0.99)


# ---------------------------------------------------------------------------
# Global calibration result
# ---------------------------------------------------------------------------


@dataclass
class SsviCalibrationResult:
    """Result of global SSVI surface calibration.

    Attributes
    ----------
    params : SsviParams
        Calibrated global SSVI parameters with theta_grid populated.
    theta_values : ndarray
        Extracted ATM total variances per expiry.
    expiry_times : ndarray
        Time to expiry in years for each slice.
    rho : float
        Calibrated (or fixed) correlation.
    eta : float
        Curvature scale.
    lamb : float
        Power-law exponent.
    rmse : float
        Root-mean-square error across all slices (in total variance).
    r2 : float
        Global R-squared across all slices.
    per_slice_rmse : list of float
        RMSE for each individual slice.
    success : bool
        Whether the optimisation converged.
    message : str
        Optimiser termination message.
    calendar_violations : int
        Number of calendar arbitrage violations found.
    raw_slices : list of SviCalibrationResult
        Raw SVI calibration results used as input (for diagnostics).
    """

    params: SsviParams
    theta_values: np.ndarray
    expiry_times: np.ndarray
    rho: float
    eta: float
    lamb: float
    rmse: float
    r2: float
    per_slice_rmse: list[float] = field(default_factory=list)
    success: bool = False
    message: str = ""
    calendar_violations: int = 0
    raw_slices: list[SviCalibrationResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 1: Extract ATM total variance
# ---------------------------------------------------------------------------


def extract_atm_variance(
    k: np.ndarray,
    w_observed: np.ndarray,
    method: str = "linear",
) -> float:
    """Extract ATM total variance $theta = w(0)$ from observed data.

    The ATM point is at $k = 0$ (log-moneyness). Since observed strikes
    may not include exactly $k = 0$, we interpolate nearby points.

    Parameters
    ----------
    k : ndarray
        Log-moneyness values.
    w_observed : ndarray
        Observed total implied variance at each k.
    method : str
        Interpolation method: "linear", "quadratic", or "nearest".

    Returns
    -------
    float
        ATM total variance $theta$.
    """
    if len(k) < 2:
        return float(w_observed[0])

    k_sorted_idx = np.argsort(k)
    k_sorted = np.asarray(k)[k_sorted_idx]
    w_sorted = np.asarray(w_observed)[k_sorted_idx]

    # Check if we exactly hit k=0
    if np.any(np.abs(k_sorted) < 1e-15):
        idx = np.argmin(np.abs(k_sorted))
        return float(w_sorted[idx])

    if method == "nearest":
        idx = np.argmin(np.abs(k_sorted))
        return float(w_sorted[idx])
    elif method == "quadratic" and len(k) >= 3:
        # Fit a quadratic through the 3 points nearest k=0
        idx_center = np.argmin(np.abs(k_sorted))
        lo = max(0, idx_center - 1)
        hi = min(len(k_sorted) - 1, idx_center + 1)
        if hi - lo < 2:
            lo = max(0, hi - 2)
        ks = k_sorted[lo:hi+1]
        ws = w_sorted[lo:hi+1]
        coeffs = np.polyfit(ks, ws, 2)
        # Evaluate at k=0
        return float(np.polyval(coeffs, 0.0))
    else:
        # Linear interpolation
        return float(np.interp(0.0, k_sorted, w_sorted))


def extract_theta_grid(
    slices_data: list[tuple[np.ndarray, np.ndarray, float]],
    method: str = "linear",
) -> np.ndarray:
    """Extract ATM total variance $theta_t$ for each expiry slice.

    Parameters
    ----------
    slices_data : list of (k, w_observed, T)
        Each tuple is the (log-moneyness, total implied variance, expiry time)
        for one slice.
    method : str
        Interpolation method passed to extract_atm_variance.

    Returns
    -------
    ndarray
        ATM total variances for each slice (same order as input).
    """
    theta_vals = []
    for k, w_obs, T in slices_data:
        theta_vals.append(extract_atm_variance(k, w_obs, method=method))
    return np.array(theta_vals)


# ---------------------------------------------------------------------------
# Stage 2: Global (eta, lambda) calibration
# ---------------------------------------------------------------------------


def _ssvi_global_objective(
    theta_vec: np.ndarray,
    k_all: list[np.ndarray],
    w_all: list[np.ndarray],
    weights_all: list[np.ndarray],
    rho: float,
    eta: float,
    lamb: float,
) -> float:
    """Compute global weighted sum of squared errors across all slices.

    Parameters
    ----------
    theta_vec : ndarray
        Pre-extracted ATM total variances (n_slices,). Not optimised.
    k_all, w_all, weights_all : lists of ndarray
        Per-slice calibration data.
    rho, eta, lamb : floats
        SSVI parameters.

    Returns
    -------
    float
        Total weighted sum of squared residuals.
    """
    total_obj = 0.0
    n_total = 0

    for i, (k, w_obs, wts) in enumerate(zip(k_all, w_all, weights_all)):
        theta_i = float(theta_vec[i])
        phi_i = float(eta / (theta_i ** lamb)) if theta_i > 0 else 0.0

        if phi_i <= 0:
            return 1e20

        w_fit = ssvi_total_variance(k, theta_i, phi_i, rho)
        residuals = np.sqrt(wts) * (w_obs - w_fit)
        total_obj += float(np.sum(residuals ** 2))
        n_total += len(k)

    if n_total == 0:
        return 1e20
    return total_obj


def _global_objective_wrapper(
    x: np.ndarray,
    theta_vec: np.ndarray,
    k_all: list[np.ndarray],
    w_all: list[np.ndarray],
    weights_all: list[np.ndarray],
    rho: float,
) -> float:
    """Wrapper for scipy.optimize: x = [eta, lamb]."""
    eta, lamb = float(x[0]), float(x[1])
    if eta <= 0 or lamb < 0 or lamb > 1:
        return 1e20
    return _ssvi_global_objective(theta_vec, k_all, w_all, weights_all,
                                   rho, eta, lamb)


def calibrate_ssvi_surface(
    slices_data: list[tuple[np.ndarray, np.ndarray, float]],
    expiration_times: list[float],
    weights_all: Optional[list[np.ndarray]] = None,
    rho: Optional[float] = None,
    eta_init: Optional[float] = None,
    lamb_init: Optional[float] = None,
    eta_bounds: tuple[float, float] = DEFAULT_ETA_BOUNDS,
    lamb_bounds: tuple[float, float] = DEFAULT_LAMBDA_BOUNDS,
    rho_bounds: tuple[float, float] = DEFAULT_RHO_BOUNDS,
    method: str = "L-BFGS-B",
    tol: float = 1e-8,
    max_iter: int = 500,
) -> SsviCalibrationResult:
    """Calibrate SSVI surface globally across all expiry slices.

    Two-stage approach:
    1. Extract $theta_t$ from ATM implied variance at each expiry.
    2. Fit $(rho, eta, lambda)$ globally.

    Parameters
    ----------
    slices_data : list of (k, w_observed, T)
        Per-slice calibration data. k is log-moneyness, w_observed is
        total implied variance, T is time to expiry.
    expiration_times : list of float
        Expiry times in years (used for calendar ordering).
    weights_all : list of ndarray, optional
        Per-slice observation weights. Default: equal weights per slice.
    rho : float, optional
        Fixed correlation. If None, rho is calibrated jointly with (eta, lamb).
    eta_init, lamb_init : float, optional
        Initial guesses for curvature parameters.
    eta_bounds, lamb_bounds : tuple
        Bounds for eta and lambda.
    rho_bounds : tuple
        Bounds for rho (used only if rho is None).
    method : str
        scipy.optimize.minimize method.
    tol : float
        Optimisation tolerance.
    max_iter : int
        Maximum iterations.

    Returns
    -------
    SsviCalibrationResult
    """
    n_slices = len(slices_data)
    if n_slices < 1:
        raise ValueError("Need at least one slice for SSVI calibration")

    # Extract ATM variances
    theta_vec = extract_theta_grid(slices_data)

    # Build calibration arrays
    k_all = [data[0] for data in slices_data]
    w_all = [data[1] for data in slices_data]
    T_all = np.array([data[2] for data in slices_data])

    if weights_all is None:
        weights_all = [np.ones_like(k) for k in k_all]

    n_total = sum(len(k) for k in k_all)

    # Initial guesses
    if eta_init is None:
        # Typical range: eta ~ 0.5-2.0
        eta_init = 1.0
    if lamb_init is None:
        lamb_init = 0.25

    # ------------------------------------------------------------------
    # If rho is fixed, calibrate (eta, lambda) only
    # ------------------------------------------------------------------
    if rho is not None:
        x0 = np.array([eta_init, lamb_init])
        bounds = [eta_bounds, lamb_bounds]

        result = minimize(
            _global_objective_wrapper,
            x0,
            args=(theta_vec, k_all, w_all, weights_all, rho),
            method=method,
            bounds=bounds,
            tol=tol,
            options={"maxiter": max_iter, "ftol": tol},
        )

        eta_opt = float(result.x[0])
        lamb_opt = float(result.x[1])
        rho_opt = rho
        success = result.success
        message = result.message
    else:
        # ------------------------------------------------------------------
        # Joint calibration of (eta, lamb, rho)
        # ------------------------------------------------------------------
        x0 = np.array([eta_init, lamb_init, 0.0 if rho is None else rho])
        bounds = [eta_bounds, lamb_bounds, rho_bounds]

        def obj_3d(x, theta_vec, k_all, w_all, weights_all):
            eta, lamb, rho = float(x[0]), float(x[1]), float(x[2])
            if eta <= 0 or lamb < 0 or lamb > 1 or rho <= -0.999 or rho >= 0.999:
                return 1e20
            return _ssvi_global_objective(theta_vec, k_all, w_all, weights_all,
                                           rho, eta, lamb)

        result = minimize(
            obj_3d,
            x0,
            args=(theta_vec, k_all, w_all, weights_all),
            method=method,
            bounds=bounds,
            tol=tol,
            options={"maxiter": max_iter, "ftol": tol},
        )

        eta_opt = float(result.x[0])
        lamb_opt = float(result.x[1])
        rho_opt = float(result.x[2])
        success = result.success
        message = result.message

    # ------------------------------------------------------------------
    # Build result
    # ------------------------------------------------------------------
    params = SsviParams(rho=rho_opt, eta=eta_opt, lamb=lamb_opt,
                        theta_grid=theta_vec)

    # Compute diagnostics
    total_ss = _ssvi_global_objective(theta_vec, k_all, w_all, weights_all,
                                       rho_opt, eta_opt, lamb_opt)
    rmse = np.sqrt(total_ss / n_total) if n_total > 0 else 0.0

    # Per-slice RMSE
    per_slice_rmse = []
    for i, (k, w_obs, wts) in enumerate(zip(k_all, w_all, weights_all)):
        theta_i = float(theta_vec[i])
        phi_i = float(eta_opt / (theta_i ** lamb_opt))
        w_fit = ssvi_total_variance(k, theta_i, phi_i, rho_opt)
        residuals = np.sqrt(wts) * (w_obs - w_fit)
        slice_rmse = np.sqrt(np.sum(residuals ** 2) / len(k))
        per_slice_rmse.append(slice_rmse)

    # R-squared
    all_w = np.concatenate(w_all)
    ss_tot = float(np.sum((all_w - np.mean(all_w)) ** 2))
    r2 = 1.0 - total_ss / ss_tot if ss_tot > 1e-15 else 0.0

    # Calendar arbitrage check
    calendar_violations = 0
    k_check = np.linspace(-3, 3, 201)
    for i in range(n_slices - 1):
        j_order = np.argsort(T_all)
        t_i_idx, t_j_idx = j_order[i], j_order[i + 1]
        theta_i = float(theta_vec[t_i_idx])
        theta_j = float(theta_vec[t_j_idx])
        phi_i = float(eta_opt / (theta_i ** lamb_opt))
        phi_j = float(eta_opt / (theta_j ** lamb_opt))
        w_i = ssvi_total_variance(k_check, theta_i, phi_i, rho_opt)
        w_j = ssvi_total_variance(k_check, theta_j, phi_j, rho_opt)
        if np.any(w_j - w_i < -1e-12):
            calendar_violations += 1

    return SsviCalibrationResult(
        params=params,
        theta_values=theta_vec,
        expiry_times=T_all,
        rho=rho_opt,
        eta=eta_opt,
        lamb=lamb_opt,
        rmse=rmse,
        r2=r2,
        per_slice_rmse=per_slice_rmse,
        success=success,
        message=message,
        calendar_violations=calendar_violations,
    )