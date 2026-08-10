"""Surface SVI (SSVI) parameterization — Gatheral & Jacquier (2014).

The SSVI parameterization defines a full volatility surface by linking
individual maturity slices through a common asymptotic structure. Unlike
raw SVI (which calibrates each expiry independently), SSVI ensures:

1. **Consistent wing asymptotics** across all maturities — the same $rho$
   parameter governs the skew for every slice.
2. **ATM total variance** $theta_t$ is monotonic in $T$ (calendar consistency).
3. **Curvature function** $phi(theta_t)$ controls the smile flattening with
   maturity, typically following a power-law:

       $$phi(theta) = frac{eta}{theta^{lambda}}$$

   where $eta > 0$ and $lambda in [0, 1/2]$ (or $lambda in [0, 1]$ for
   the extended form).

Functional Form
---------------
For a given slice with ATM total variance $theta_t$:

    $$w(k, theta) = frac{theta}{2}
    left(1 + rho,phi(theta), k + sqrt{(phi(theta),k + rho)^2 + (1 - rho^2)}right)$$

where $k = log(K/F)$ is log-forward-moneyness.

This satisfies the Gatheral-Jacquier no-arbitrage conditions when:
    - $theta_t > 0$ (positive variance)
    - $theta_t$ is non-decreasing in $t$ (calendar)
    - $rho in (-1, 1)$ (correlation)
    - $phi(theta) > 0$ (positive curvature)
    - $theta , phi(theta) , (1 + |rho|) leq 2$ (Lee moment formula)
    - $partial_theta w(k, theta) geq 0$ for all $k$ (calibration-free calendar)

The power-law form $phi(theta) = eta / theta^lambda$ is commonly used
because it guarantees $partial_theta w(k, theta) geq 0$ when
$lambda in [0, 1/2]$ and $eta(1+|rho|) leq 2$.

References
----------
Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
    Quantitative Finance, 14(1), 59–71.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from volfoundry.svi.parameterization import SviParams


# ---------------------------------------------------------------------------
# SSVI global parameters
# ---------------------------------------------------------------------------


@dataclass
class SsviParams:
    """Global SSVI surface parameters.

    These parameters define the entire volatility surface across all
    maturities via the SSVI functional form.

    Attributes
    ----------
    rho : float
        Correlation parameter, common across all slices. Must satisfy
        -1 < rho < 1. Negative values produce equity-like downward skew.
    eta : float
        Curvature scale parameter ($eta > 0$). Controls the magnitude of
        the smile/skew curvature. Larger η means more pronounced smile.
    lamb : float
        Power-law exponent ($lambda in [0, 1]$). Controls how fast the
        smile flattens with increasing maturity:
        - $lambda = 0$: constant curvature across maturities
        - $lambda = 0.5$: smile decays as $1/sqrt{T}$ (diffusive scaling)
        - $lambda = 1$: smile decays as $1/T$ (fast flattening)
    theta_grid : ndarray or None
        Pre-computed ATM total variance values for each slice.
        Set during calibration or surface construction.
    """

    rho: float
    eta: float
    lamb: float
    theta_grid: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        if not (-1.0 < self.rho < 1.0):
            raise ValueError(f"rho must be in (-1, 1), got {self.rho}")
        if self.eta <= 0:
            raise ValueError(f"eta must be positive, got {self.eta}")
        if not (0.0 <= self.lamb <= 1.0):
            raise ValueError(f"lambda must be in [0, 1], got {self.lamb}")

    def phi(self, theta: float | np.ndarray) -> float | np.ndarray:
        """Evaluate the curvature function $phi(theta) = eta / theta^lambda$.

        Parameters
        ----------
        theta : float or ndarray
            ATM total variance value(s).

        Returns
        -------
        float or ndarray
            Curvature parameter(s).
        """
        theta = np.asarray(theta, dtype=float)
        if np.any(theta <= 0):
            raise ValueError("theta must be positive")
        return self.eta / (theta ** self.lamb)

    def satisfies_lee_bound(self) -> bool:
        """Check Lee moment formula bound: $eta (1 + |rho|) leq 2$.

        Since $phi(theta) leq eta$ when $lambda >= 0$ and $theta >= 1$,
        the most restrictive check is at $theta = 1$ (for $lambda > 0$).
        For robustness check the worst-case: $eta(1+|rho|) <= 2$.
        """
        return self.eta * (1.0 + abs(self.rho)) <= 2.0


# ---------------------------------------------------------------------------
# SSVI functional form
# ---------------------------------------------------------------------------


def ssvi_total_variance(
    k: np.ndarray | float,
    theta: float,
    phi_val: float,
    rho: float,
) -> np.ndarray | float:
    """Evaluate SSVI total variance at a single slice.

    Parameters
    ----------
    k : array-like or float
        Log-moneyness $k = log(K/F)$.
    theta : float
        ATM total variance $theta_t = sigma_ATM^2 * T$.
    phi_val : float
        Curvature $phi(theta)$ at this theta.
    rho : float
        Correlation (common across all slices).

    Returns
    -------
    array-like or float
        Total implied variance $w(k, theta)$.
    """
    if theta <= 0:
        raise ValueError(f"theta must be positive, got {theta}")
    if phi_val <= 0:
        raise ValueError(f"phi must be positive, got {phi_val}")

    k_scalar = np.atleast_1d(np.asarray(k, dtype=float))
    phi_k_plus_rho = phi_val * k_scalar + rho
    disc = np.sqrt(phi_k_plus_rho**2 + (1.0 - rho**2))

    result = 0.5 * theta * (1.0 + rho * phi_val * k_scalar + disc)

    if np.ndim(k) == 0 or (isinstance(k, float) and not isinstance(k, np.ndarray)):
        return float(result.item())
    return result.reshape(np.asarray(k).shape)


def ssvi_implied_vol(
    k: np.ndarray | float,
    theta: float,
    phi_val: float,
    rho: float,
    T: float,
) -> np.ndarray | float:
    """Evaluate SSVI implied volatility.

    Parameters
    ----------
    k : array-like or float
        Log-moneyness.
    theta : float
        ATM total variance.
    phi_val : float
        Curvature value.
    rho : float
        Correlation.
    T : float
        Time to expiry (must match theta / sigma_ATM^2).

    Returns
    -------
    array-like or float
        Implied volatility $sigma_IV(k) = sqrt(w(k, theta) / T)$.
    """
    w = ssvi_total_variance(k, theta, phi_val, rho)
    if T <= 0:
        raise ValueError(f"T must be positive, got {T}")
    return np.sqrt(np.maximum(w, 0.0) / T)


def ssvi_total_variance_surface(
    k_grid: np.ndarray,
    params: SsviParams,
) -> np.ndarray:
    """Evaluate the full SSVI surface across k and theta grid.

    Parameters
    ----------
    k_grid : ndarray, shape (n_k,)
        Log-moneyness values.
    params : SsviParams
        SSVI parameters with theta_grid populated.

    Returns
    -------
    ndarray, shape (n_k, n_T)
        $w(k_i, theta_j)$ for each (k, theta) pair.
    """
    if params.theta_grid is None:
        raise ValueError("SsviParams.theta_grid must be populated")
    theta_arr = np.asarray(params.theta_grid, dtype=float)
    k_arr = np.asarray(k_grid, dtype=float)

    n_k = len(k_arr)
    n_T = len(theta_arr)

    w_surface = np.empty((n_k, n_T))

    for j, theta_j in enumerate(theta_arr):
        phi_j = params.phi(theta_j)
        w_surface[:, j] = ssvi_total_variance(k_arr, float(theta_j), float(phi_j), params.rho)

    return w_surface


# ---------------------------------------------------------------------------
# SSVI -> raw SVI mapping (for diagnostics)
# ---------------------------------------------------------------------------


def ssvi_to_raw_svi(
    theta: float, phi_val: float, rho: float
) -> SviParams:
    """Map an SSVI slice to equivalent raw SVI parameters.

    The SSVI form:
        w(k) = theta/2 * (1 + rho*phi*k + sqrt((phi*k + rho)^2 + (1 - rho^2)))

    is equivalent to raw SVI:
        w(k) = a + b * [rho_raw * (k - m) + sqrt((k - m)^2 + sigma^2)]

    with the mapping:
        a     = theta/2 * (1 - rho^2)
        b     = theta * phi / 2
        rho_raw = rho
        m     = -rho / phi
        sigma = sqrt(1 - rho^2) / phi

    Parameters
    ----------
    theta : float
        ATM total variance.
    phi_val : float
        Curvature value.
    rho : float
        Correlation.

    Returns
    -------
    SviParams
        Equivalent raw SVI parameters.
    """
    half_theta = 0.5 * theta
    one_minus_rho2 = 1.0 - rho**2

    a = half_theta * one_minus_rho2
    b = half_theta * phi_val
    m = -rho / phi_val
    sigma = np.sqrt(one_minus_rho2) / phi_val

    return SviParams(a=float(a), b=float(b), rho=float(rho),
                     m=float(m), sigma=float(sigma))


def ssvi_to_raw_svi_surface(params: SsviParams) -> list[tuple[float, SviParams]]:
    """Convert all SSVI slices to raw SVI parameters.

    Parameters
    ----------
    params : SsviParams
        SSVI parameters with theta_grid populated.

    Returns
    -------
    list of (theta, SviParams)
        Raw SVI parameters for each slice, keyed by theta.
    """
    if params.theta_grid is None:
        raise ValueError("SsviParams.theta_grid must be populated")
    slices = []
    for theta_j in params.theta_grid:
        phi_j = params.phi(float(theta_j))
        raw = ssvi_to_raw_svi(float(theta_j), float(phi_j), params.rho)
        slices.append((float(theta_j), raw))
    return slices