"""No-arbitrage enforcement for SVI volatility surfaces.

This module implements the three key no-arbitrage conditions for implied
volatility surfaces:

1. **Butterfly arbitrage** (absence of calendar spread butterfly): the
   g(k) function derived from Breeden-Litzenberger must be non-negative.

2. **Calendar arbitrage** (absence of calendar spread arbitrage): total
   implied variance must be non-decreasing in time to expiry at each
   fixed log-moneyness k.

3. **Breeden-Litzenberger density** non-negativity: the risk-neutral
   density extracted from call prices via d²C/dK² must be >= 0.

When a calibrated slice violates any of these, it is REJECTED and logged
to reports/. No silent acceptance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from volfoundry.tolerances import ARBITRAGE_TOL, EPSILON
from volfoundry.svi.parameterization import (
    SviParams,
    svi_first_derivative,
    svi_second_derivative,
    svi_total_variance,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Butterfly (g(k)) check
# ---------------------------------------------------------------------------


def butterfly_g(
    k: np.ndarray, params: SviParams, T: float
) -> np.ndarray:
    """Compute the butterfly no-arbitrage function g(k).

    g(k) = (1 - k * w' / (2w))^2 - (w'^2 / 4) * (1/w + 1/4) + w'' / 2

    A necessary condition for no butterfly arbitrage is g(k) >= 0 for all k.

    Parameters
    ----------
    k : ndarray
        Log-moneyness values k = log(K/F).
    params : SviParams
        SVI parameters for the slice.
    T : float
        Time to expiry in years.

    Returns
    -------
    ndarray
        g(k) values at each k. Must be >= 0 for no arbitrage.
    """
    w = svi_total_variance(k, params)
    wp = svi_first_derivative(k, params)
    wpp = svi_second_derivative(k, params)

    # Avoid division by zero
    w = np.maximum(w, EPSILON)

    term1 = (1.0 - k * wp / (2.0 * w)) ** 2
    term2 = (wp**2 / 4.0) * (1.0 / w + 0.25)
    term3 = wpp / 2.0

    return term1 - term2 + term3


def butterfly_is_arbitrage_free(
    k: np.ndarray, params: SviParams, T: float, tol: float = ARBITRAGE_TOL
) -> bool:
    """Check if the butterfly condition holds over the given k-range.

    Parameters
    ----------
    k : ndarray
        Log-moneyness values.
    params : SviParams
        SVI parameters.
    T : float
        Time to expiry.
    tol : float
        Numerical tolerance (negative values below tol are violations).

    Returns
    -------
    bool
        True if g(k) >= tol for all k.
    """
    g = butterfly_g(k, params, T)
    return bool(np.all(g >= tol))


def find_butterfly_violations(
    k: np.ndarray, params: SviParams, T: float, tol: float = ARBITRAGE_TOL
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Find k-regions where the butterfly condition is violated.

    Parameters
    ----------
    k : ndarray
        Log-moneyness values.
    params : SviParams
        SVI parameters.
    T : float
        Time to expiry.
    tol : float
        Tolerance threshold.

    Returns
    -------
    (k_viol, g_viol) or None
        Arrays of violating log-moneyness and g(k) values, or None if none.
    """
    g = butterfly_g(k, params, T)
    mask = g < tol
    if not np.any(mask):
        return None
    return k[mask], g[mask]


# ---------------------------------------------------------------------------
# Calendar spread check
# ---------------------------------------------------------------------------


def calendar_monotonicity(
    k: np.ndarray,
    params_slices: List[Tuple[SviParams, float]],
    tol: float = ARBITRAGE_TOL,
) -> bool:
    """Check calendar monotonicity across expiry slices.

    For no calendar arbitrage, total implied variance w(k, T) must be
    non-decreasing in T at each fixed k:

        w(k, T_i) <= w(k, T_j)  for all T_i < T_j, for all k.

    Parameters
    ----------
    k : ndarray
        Log-moneyness values at which to check.
    params_slices : list of (SviParams, T)
        Slices ordered by increasing T.
    tol : float
        Negative tolerance for numerical fuzz.

    Returns
    -------
    bool
        True if calendar monotonicity holds.
    """
    if len(params_slices) < 2:
        return True

    # Sort by T to ensure correct ordering
    sorted_slices = sorted(params_slices, key=lambda x: x[1])

    for i in range(len(sorted_slices) - 1):
        params_i, T_i = sorted_slices[i]
        params_j, T_j = sorted_slices[i + 1]

        w_i = svi_total_variance(k, params_i)
        w_j = svi_total_variance(k, params_j)

        if np.any(w_j - w_i < tol):
            return False

    return True


def find_calendar_violations(
    k: np.ndarray,
    params_slices: List[Tuple[SviParams, float]],
    tol: float = ARBITRAGE_TOL,
) -> List[Tuple[float, float, np.ndarray]]:
    """Find calendar arbitrage violations.

    Parameters
    ----------
    k : ndarray
        Log-moneyness values.
    params_slices : list of (SviParams, T)
        Slices ordered by increasing T.
    tol : float
        Tolerance.

    Returns
    -------
    list of (T_i, T_j, k_viol) tuples for each violating pair of slices.
    """
    violations = []
    sorted_slices = sorted(params_slices, key=lambda x: x[1])

    for i in range(len(sorted_slices) - 1):
        params_i, T_i = sorted_slices[i]
        params_j, T_j = sorted_slices[i + 1]

        w_i = svi_total_variance(k, params_i)
        w_j = svi_total_variance(k, params_j)

        viol_mask = (w_j - w_i) < tol
        if np.any(viol_mask):
            violations.append((T_i, T_j, k[viol_mask]))

    return violations


# ---------------------------------------------------------------------------
# Breeden-Litzenberger density check
# ---------------------------------------------------------------------------


def breeden_litzenberger_density(
    K: np.ndarray, F: float, T: float, r: float, sigma: np.ndarray
) -> np.ndarray:
    """Approximate the Breeden-Litzenberger risk-neutral density.

    The risk-neutral density is proportional to the second derivative of
    the call price with respect to strike:

        q(K) = e^{rT} * d²C/dK²

    We approximate d²C/dK² via finite differences on implied volatilities,
    converting from BS prices.

    This is a cross-check: for no-arbitrage, q(K) >= 0 for all K.

    Parameters
    ----------
    K : ndarray
        Strike prices (must be sorted).
    F : float
        Forward price.
    T : float
        Time to expiry.
    r : float
        Risk-free rate.
    sigma : ndarray
        Implied volatilities at each strike.

    Returns
    -------
    ndarray
        Approximate risk-neutral density at each strike (interior points
        only — endpoints are NaN).
    """
    from volfoundry.iv.black_scholes import black76_price, OptionType

    n = len(K)
    if n < 3:
        raise ValueError("Need at least 3 strikes for density estimation")

    # Compute call prices from implied vols
    calls = np.array([black76_price(F, float(Ki), float(si), T, r, OptionType.CALL)
                      for Ki, si in zip(K, sigma)])

    # Non-uniform three-point second derivative formula.
    # For a quadratic through (K[i-1], C[i-1]), (K[i], C[i]), (K[i+1], C[i+1]):
    #   d^2C/dK^2 = 2 * [C[i+1]*h0 - C[i]*(h0+h1) + C[i-1]*h1]
    #               / [(h0+h1) * h1 * h0]
    # where h0 = K[i] - K[i-1], h1 = K[i+1] - K[i].
    q = np.empty(n)
    q[0] = np.nan
    q[-1] = np.nan

    for i in range(1, n - 1):
        h0 = K[i] - K[i - 1]
        h1 = K[i + 1] - K[i]
        h_sum = h0 + h1

        d2C_dK2 = (
            2.0
            * (
                calls[i + 1] * h0
                - calls[i] * h_sum
                + calls[i - 1] * h1
            )
            / (h_sum * h1 * h0)
        )
        q[i] = np.exp(r * T) * d2C_dK2

    return q


def breeden_litzenberger_is_nonnegative(
    K: np.ndarray, F: float, T: float, r: float, sigma: np.ndarray,
    tol: float = ARBITRAGE_TOL,
) -> bool:
    """Check that the Breeden-Litzenberger density is non-negative.

    Parameters
    ----------
    K, F, T, r, sigma : see breeden_litzenberger_density.
    tol : float
        Negative tolerance.

    Returns
    -------
    bool
        True if all interior-point density values >= tol.
    """
    q = breeden_litzenberger_density(K, F, T, r, sigma)
    interior = q[1:-1]  # skip NaN endpoints
    return bool(np.all(np.isfinite(interior)) and np.all(interior >= tol))


# ---------------------------------------------------------------------------
# Full slice arbitrage check
# ---------------------------------------------------------------------------


@dataclass
class ArbitrageCheckResult:
    """Result of a full no-arbitrage check on a single SVI slice.

    Attributes
    ----------
    slice_id : str
        Identifier for the slice (e.g., "BTC-27DEC24").
    T : float
        Time to expiry.
    butterfly_passed : bool
        True if g(k) >= 0 for all k in the evaluation range.
    butterfly_min_g : float
        Minimum g(k) value observed.
    bl_passed : bool or None
        True if Breeden-Litzenberger density is non-negative.
        None if not computed (no spot/rate data provided).
    params : SviParams
        The SVI parameters that were checked.
    k_range : tuple
        (k_min, k_max) used for evaluation.
    """
    slice_id: str
    T: float
    butterfly_passed: bool
    butterfly_min_g: float
    bl_passed: Optional[bool]
    params: SviParams
    k_range: Tuple[float, float]


def check_slice_arbitrage(
    slice_id: str,
    params: SviParams,
    T: float,
    k: Optional[np.ndarray] = None,
    K: Optional[np.ndarray] = None,
    F: Optional[float] = None,
    r: Optional[float] = None,
    n_k: int = 500,
    k_min: float = -5.0,
    k_max: float = 5.0,
) -> ArbitrageCheckResult:
    """Run all no-arbitrage checks on a single SVI slice.

    Parameters
    ----------
    slice_id : str
        Identifier for the slice.
    params : SviParams
        Calibrated SVI parameters.
    T : float
        Time to expiry.
    k : ndarray, optional
        Pre-computed log-moneyness grid.  If None, generates linspace.
    K : ndarray, optional
        Strike prices for BL check. If None and F is provided, computed from k.
    F : float, optional
        Forward price (required for BL density check).
    r : float, optional
        Risk-free rate (required for BL density check).
    n_k : int
        Number of k points if generating grid.
    k_min, k_max : float
        Range for k grid.

    Returns
    -------
    ArbitrageCheckResult
    """
    if k is None:
        k = np.linspace(k_min, k_max, n_k)

    g = butterfly_g(k, params, T)
    butterfly_ok = bool(np.all(g >= ARBITRAGE_TOL))
    min_g = float(np.min(g))

    # Breeden-Litzenberger
    bl_passed: Optional[bool] = None
    if F is not None and r is not None:
        sigma_iv = np.sqrt(np.maximum(svi_total_variance(k, params), 0.0) / T)
        K_arr = F * np.exp(k) if K is None else K
        bl_passed = breeden_litzenberger_is_nonnegative(
            K_arr, F, T, r, sigma_iv
        )

    return ArbitrageCheckResult(
        slice_id=slice_id,
        T=T,
        butterfly_passed=butterfly_ok,
        butterfly_min_g=min_g,
        bl_passed=bl_passed,
        params=params,
        k_range=(float(np.min(k)), float(np.max(k))),
    )


# ---------------------------------------------------------------------------
# Rejection and reporting
# ---------------------------------------------------------------------------


@dataclass
class SliceValidationReport:
    """Report for multi-slice no-arbitrage validation.

    Attributes
    ----------
    slice_results : list
        Per-slice ArbitrageCheckResult objects.
    calendar_passed : bool or None
        None if only one slice; True/False otherwise.
    calendar_violations : list
        Calendar violation details.
    all_passed : bool
        True if all checks in all slices pass.
    rejected_slices : list
        IDs of slices that failed any check.
    """
    slice_results: List[ArbitrageCheckResult] = field(default_factory=list)
    calendar_passed: Optional[bool] = None
    calendar_violations: List = field(default_factory=list)
    all_passed: bool = True
    rejected_slices: List[str] = field(default_factory=list)


def validate_surface(
    slices: List[Tuple[str, SviParams, float]],
    K: Optional[np.ndarray] = None,
    F: Optional[float] = None,
    r: Optional[float] = None,
    k_grid: Optional[np.ndarray] = None,
    n_k: int = 500,
) -> SliceValidationReport:
    """Validate an entire surface of SVI slices for no-arbitrage.

    Parameters
    ----------
    slices : list of (slice_id, SviParams, T)
        Calibrated slices. Must be ordered by increasing T for calendar check.
    K, F, r : optional
        Required for Breeden-Litzenberger cross-check.
    k_grid : ndarray, optional
        Shared log-moneyness grid.
    n_k : int
        Grid size if generating.

    Returns
    -------
    SliceValidationReport
    """
    report = SliceValidationReport()

    # Sort by T
    slices_sorted = sorted(slices, key=lambda x: x[2])

    all_butterfly_ok = True
    all_bl_ok = True

    # Per-slice checks
    for slice_id, params, T in slices_sorted:
        result = check_slice_arbitrage(
            slice_id=slice_id,
            params=params,
            T=T,
            k=k_grid,
            K=K,
            F=F,
            r=r,
            n_k=n_k,
        )
        report.slice_results.append(result)

        if not result.butterfly_passed:
            all_butterfly_ok = False
            report.rejected_slices.append(slice_id)
            logger.warning(
                f"Slice {slice_id} (T={T:.4f}) REJECTED: butterfly g_min={result.butterfly_min_g:.6e}"
            )

        if result.bl_passed is not None and not result.bl_passed:
            all_bl_ok = False
            if slice_id not in report.rejected_slices:
                report.rejected_slices.append(slice_id)
            logger.warning(
                f"Slice {slice_id} (T={T:.4f}) REJECTED: BL density negative"
            )

    # Calendar check
    if len(slices_sorted) >= 2:
        params_T_pairs = [(params, T) for _, params, T in slices_sorted]
        calendar_ok = calendar_monotonicity(
            k_grid if k_grid is not None else np.linspace(-5, 5, n_k),
            params_T_pairs,
        )
        report.calendar_passed = calendar_ok

        if not calendar_ok:
            report.calendar_violations = find_calendar_violations(
                k_grid if k_grid is not None else np.linspace(-5, 5, n_k),
                params_T_pairs,
            )
            logger.warning(
                f"Calendar arbitrage detected: {len(report.calendar_violations)} violating pair(s)"
            )
    else:
        report.calendar_passed = None  # not applicable

    report.all_passed = all_butterfly_ok and (all_bl_ok) and (
        report.calendar_passed is None or report.calendar_passed
    )

    return report