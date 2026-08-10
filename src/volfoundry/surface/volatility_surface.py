"""VolatilitySurface — a callable object that interpolates IV from
a calibrated SSVI surface.

The surface is backed by SSVI global parameters and a maturity grid,
providing implied volatility for any (strike, maturity) pair within
the calibrated domain via the SSVI functional form.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from volfoundry.surface.ssvi import (
    SsviParams,
    ssvi_implied_vol,
    ssvi_total_variance,
)


class VolatilitySurface:
    """A calibrated volatility surface backed by SSVI parameters.

    The surface is constructed from global SSVI parameters and a gridded
    set of ATM total variance values across maturities.  Interpolation
    of ``theta(T)`` between grid points uses log-linear interpolation
    in $T$ — log for positivity, linear for smoothness.

    Parameters
    ----------
    params : SsviParams
        Global SSVI parameters (rho, eta, lambda, theta_grid).
    expiry_times : ndarray
        Time-to-expiry values (years) matching ``params.theta_grid``,
        sorted in ascending order.
    currency : str, optional
        Identifier for the underlying (e.g. ``"BTC"``).
    r : float, optional
        Risk-free / implied discount rate (continuous) for pricing helpers.
        Default 0.0 (no discounting).
    """

    def __init__(
        self,
        params: SsviParams,
        expiry_times: np.ndarray,
        currency: str = "",
        r: float = 0.0,
    ) -> None:
        if params.theta_grid is None:
            raise ValueError("SsviParams.theta_grid must be populated")
        if len(expiry_times) != len(params.theta_grid):
            raise ValueError(
                f"expiry_times length ({len(expiry_times)}) must match "
                f"theta_grid length ({len(params.theta_grid)})"
            )

        self._params = params
        self._T = np.asarray(expiry_times, dtype=float)
        self._theta = np.asarray(params.theta_grid, dtype=float)
        self.currency = currency
        self.r = r

        # Sort by expiry time
        sort_idx = np.argsort(self._T)
        self._T = self._T[sort_idx]
        self._theta = self._theta[sort_idx]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def params(self) -> SsviParams:
        """Global SSVI parameters (read-only copy)."""
        return self._params

    @property
    def expiry_times(self) -> np.ndarray:
        """Grid of time-to-expiry values in years."""
        return self._T.copy()

    @property
    def min_expiry(self) -> float:
        """Minimum expiry time (years) covered by the surface grid."""
        return float(self._T[0])

    @property
    def max_expiry(self) -> float:
        """Maximum expiry time (years) covered by the surface grid."""
        return float(self._T[-1])

    @property
    def n_slices(self) -> int:
        """Number of expiry slices in the surface."""
        return len(self._T)

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def _interpolate_theta(self, T: float) -> float:
        """Interpolate theta at maturity *T* using log-linear interpolation.

        log(theta(T)) is linear between grid points; this ensures
        positivity and smooth monotonic behaviour.
        """
        if T <= self._T[0]:
            return float(self._theta[0])
        if T >= self._T[-1]:
            return float(self._theta[-1])

        idx = np.searchsorted(self._T, T)  # first index where T[i] > T
        T_lo, T_hi = self._T[idx - 1], self._T[idx]
        th_lo, th_hi = self._theta[idx - 1], self._theta[idx]

        # Log-linear interpolation
        frac = (np.log(T) - np.log(T_lo)) / (np.log(T_hi) - np.log(T_lo))
        log_theta = np.log(th_lo) + frac * (np.log(th_hi) - np.log(th_lo))
        return float(np.exp(log_theta))

    def total_variance(self, k: np.ndarray | float, T: float) -> np.ndarray | float:
        """Evaluate total implied variance $w(k, T)$.

        Parameters
        ----------
        k : float or ndarray
            Log-moneyness k = log(K/F).
        T : float
            Time to expiry in years.  Must be positive and within
            ``[min_expiry, max_expiry]`` for reliable interpolation.

        Returns
        -------
        float or ndarray
            Total implied variance $w(k, T)$.
        """
        if T <= 0:
            raise ValueError(f"T must be positive, got {T}")
        theta = self._interpolate_theta(T)
        phi_val = float(self._params.phi(theta))
        return ssvi_total_variance(k, theta, phi_val, self._params.rho)

    def iv(self, strike: float, maturity: float, F: Optional[float] = None) -> float:
        """Evaluate implied volatility for a given strike and maturity.

        Parameters
        ----------
        strike : float
            Strike price (must be positive).
        maturity : float
            Time to expiry in **years** (e.g. 30/365.25 for 30 days).
            Must be positive.
        F : float, optional
            Forward price.  If not provided, the surface was constructed
            without forward information and only ATM IV (k=0, so
            sigma_IV = sqrt(theta / T)) will be meaningful.

        Returns
        -------
        float
            Implied volatility as a decimal (0.60 = 60 %).
        """
        if strike <= 0:
            raise ValueError(f"strike must be positive, got {strike}")
        if maturity <= 0:
            raise ValueError(f"maturity must be positive, got {maturity}")

        if F is None:
            # Without a forward, we can only give ATM IV
            theta = self._interpolate_theta(maturity)
            return float(np.sqrt(np.maximum(theta / maturity, 0.0)))

        k = np.log(strike / F)
        theta = self._interpolate_theta(maturity)
        phi_val = float(self._params.phi(theta))
        return float(
            ssvi_implied_vol(k, theta, phi_val, self._params.rho, maturity)
        )

    def iv_grid(self, strikes: np.ndarray, maturities: np.ndarray,
                 F: float) -> np.ndarray:
        """Evaluate implied volatility on a grid of strikes and maturities.

        Parameters
        ----------
        strikes : ndarray, shape (n_K,)
            Strike prices.
        maturities : ndarray, shape (n_T,)
            Times to expiry in years.
        F : float
            Forward price.

        Returns
        -------
        ndarray, shape (n_K, n_T)
            Implied volatilities for each (strike, maturity) pair.
        """
        K = np.asarray(strikes, dtype=float)
        T = np.asarray(maturities, dtype=float)
        iv_grid = np.empty((len(K), len(T)))
        for j, T_j in enumerate(T):
            for i, K_i in enumerate(K):
                iv_grid[i, j] = self.iv(strike=K_i, maturity=T_j, F=F)
        return iv_grid

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        cy = f" {self.currency}" if self.currency else ""
        return (
            f"VolatilitySurface({self.n_slices} slices, "
            f"T in [{self.min_expiry:.4f}, {self.max_expiry:.2f}] yr, "
            f"rho={self._params.rho:.3f}, eta={self._params.eta:.3f}, "
            f"lambda={self._params.lamb:.3f}{cy})"
        )