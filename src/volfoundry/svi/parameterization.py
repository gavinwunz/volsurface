"""Raw SVI parameterization for implied volatility surfaces.

The raw SVI (Stochastic Volatility Inspired) parameterization by Gatheral (2004)
expresses total implied variance w(k) = sigma_IV^2 * T as a function of
log-moneyness k = log(K/F):

    w(k) = a + b * [rho * (k - m) + sqrt((k - m)^2 + sigma^2)]

Parameters:
    a   — overall variance level (a > 0)
    b   — slope of the wings (b >= 0)
    rho — asymmetry parameter (-1 < rho < 1)
    m   — horizontal shift (translates the curve left/right)
    sigma — curvature / smoothness parameter (sigma > 0)

Properties:
- For |k| -> infinity, w(k) ~ a + b * (rho * (k - m) + |k - m|)
  The asymptotic slopes are b * (rho + 1) for the right wing (k -> +inf)
  and b * (rho - 1) for the left wing (k -> -inf).
- Lee's moment formula bounds: |w'(k)| <= 2 / sqrt(T) as k -> +/-inf,
  which for total variance implies |asymptotic_slope| <= 2.
  Hence b * (1 + |rho|) <= 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class SviParams:
    """Raw SVI parameters for a single expiry slice.

    Attributes
    ----------
    a : float
        Overall variance level (must be > 0).
    b : float
        Wing slope (must be >= 0).
    rho : float
        Asymmetry (-1 < rho < 1).
    m : float
        Horizontal shift.
    sigma : float
        Curvature parameter (must be > 0).
    """

    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def __post_init__(self) -> None:
        if self.a <= 0:
            raise ValueError(f"a must be positive, got {self.a}")
        if self.b < 0:
            raise ValueError(f"b must be non-negative, got {self.b}")
        if not (-1.0 < self.rho < 1.0):
            raise ValueError(f"rho must be in (-1, 1), got {self.rho}")
        if self.sigma <= 0:
            raise ValueError(f"sigma must be positive, got {self.sigma}")

    @property
    def right_slope(self) -> float:
        """Asymptotic slope of w(k) for k -> +inf."""
        return self.b * (self.rho + 1.0)

    @property
    def left_slope(self) -> float:
        """Asymptotic slope of w(k) for k -> -inf."""
        return self.b * (self.rho - 1.0)

    def satisfies_lee_moment_formula(self) -> bool:
        """Check that wing slopes satisfy Lee's moment formula (|slope| <= 2)."""
        return abs(self.right_slope) <= 2.0 and abs(self.left_slope) <= 2.0


# ---------------------------------------------------------------------------
# SVI functional forms
# ---------------------------------------------------------------------------


def svi_total_variance(k: np.ndarray | float, params: SviParams) -> np.ndarray | float:
    """Evaluate raw SVI total variance w(k).

    Parameters
    ----------
    k : array-like or float
        Log-moneyness k = log(K/F).  Can be a float, 1-d, or 2-d array.
    params : SviParams
        SVI parameters (a, b, rho, m, sigma).

    Returns
    -------
    array-like or float
        Total implied variance w(k) = sigma_IV(k)^2 * T.
    """
    k_shifted = k - params.m
    disc = np.sqrt(k_shifted**2 + params.sigma**2)
    return params.a + params.b * (params.rho * k_shifted + disc)


def svi_implied_vol(
    k: np.ndarray | float, params: SviParams, T: float
) -> np.ndarray | float:
    """Evaluate raw SVI implied volatility sigma_IV(k).

    Parameters
    ----------
    k : array-like or float
        Log-moneyness k = log(K/F).
    params : SviParams
        SVI parameters.
    T : float
        Time to expiry in years.

    Returns
    -------
    array-like or float
        Implied volatility sigma_IV(k) = sqrt(w(k) / T).
    """
    w = svi_total_variance(k, params)
    if T <= 0:
        raise ValueError(f"T must be positive, got {T}")
    return np.sqrt(np.maximum(w, 0.0) / T)


def svi_first_derivative(k: np.ndarray | float, params: SviParams) -> np.ndarray | float:
    """First derivative of total variance w'(k).

    Parameters
    ----------
    k : array-like or float
        Log-moneyness.
    params : SviParams

    Returns
    -------
    array-like or float
        w'(k) = b * [rho + (k - m) / sqrt((k - m)^2 + sigma^2)]
    """
    k_shifted = k - params.m
    disc = np.sqrt(k_shifted**2 + params.sigma**2)
    return params.b * (params.rho + k_shifted / disc)


def svi_second_derivative(k: np.ndarray | float, params: SviParams) -> np.ndarray | float:
    """Second derivative of total variance w''(k).

    Parameters
    ----------
    k : array-like or float
        Log-moneyness.
    params : SviParams

    Returns
    -------
    array-like or float
        w''(k) = b * sigma^2 / ((k - m)^2 + sigma^2)^(3/2)
    """
    k_shifted = k - params.m
    disc3 = (k_shifted**2 + params.sigma**2) ** 1.5
    return params.b * params.sigma**2 / disc3


# ---------------------------------------------------------------------------
# Constraint helpers
# ---------------------------------------------------------------------------


def svi_min_total_variance(params: SviParams) -> float:
    """Minimum total variance across all k (occurs at k = m - rho * sigma / sqrt(1 - rho^2)).

    For SVI to produce non-negative variance, we need a >= 0 and the minimum
    total variance >= 0.  The minimum is:

        w_min = a + b * sigma * sqrt(1 - rho^2)

    Returns
    -------
    float
        Minimum total variance value.
    """
    return params.a + params.b * params.sigma * np.sqrt(1.0 - params.rho**2)


def clip_params_to_valid(params: SviParams) -> SviParams:
    """Clip SVI parameters to valid ranges.

    Useful as a safety measure after an unconstrained optimization step.

    Parameters
    ----------
    params : SviParams
        Raw (possibly invalid) parameters.

    Returns
    -------
    SviParams
        Clipped parameters within valid bounds.
    """
    # Bypass __post_init__ validation: build values first, then construct
    a = max(params.a, 1e-12)
    a = a if a > 0 else 1e-12
    b = max(params.b, 0.0)
    b = b if b >= 0 else 0.0
    rho = max(-0.999, min(0.999, params.rho))
    sigma = max(params.sigma, 1e-12)
    sigma = sigma if sigma > 0 else 1e-12
    return SviParams(a=a, b=b, rho=rho, m=params.m, sigma=sigma)