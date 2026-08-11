"""Central numerical tolerances for VolFoundry.

Every tolerance used in production code should be defined here (or
derived from these constants) so that users and maintainers can
understand the numerical sensitivity of the library in one place.

Categories
----------
PRICE_TOL        – absolute tolerance for price-level comparisons (USD or coin units)
VOL_TOL          – absolute tolerance for volatility (decimal, e.g. 1e-8 on σ)
ARBITRAGE_TOL    – absolute tolerance for arbitrage-condition checks
CALIBRATION_TOL  – default tolerance for optimizer convergence

Do not force one tolerance on numerically different quantities.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Primary named tolerances
# ---------------------------------------------------------------------------

PRICE_TOL: float = 1e-12
"""Absolute tolerance for price comparisons and implied-vol convergence.

Used in Black-76 price match checks (e.g. convergence in Brent IV solver)
and as the default price-level tolerance across pricing infrastructure.
"""

VOL_TOL: float = 1e-8
"""Absolute tolerance for volatility comparisons.

Primary use: implied-volatility solver convergence criterion.
Also used for volatility-level comparisons in calibration and
parameter recovery tests.
"""

ARBITRAGE_TOL: float = -1e-12
"""Absolute tolerance for no-arbitrage checks.

Negative value signals a one-sided inequality: g(k) >= ARBITRAGE_TOL.
A negative tolerance (e.g. -1e-12) allows machine-epsilon violations while
catching genuine static-arbitrage breaks.

Used in butterfly spread, calendar spread, and Breeden-Litzenberger
density checks.
"""

CALIBRATION_TOL: float = 1e-8
"""Default tolerance for calibration optimizer convergence.

Used as the default ``outer_tol`` / ``ftol`` for SVI and SSVI optimisation.
"""

# ---------------------------------------------------------------------------
# Derived / convenience constants
# ---------------------------------------------------------------------------

# Machine-precision flooring to avoid numerical singularities
EPSILON: float = 1e-15
"""Tiny positive number for flooring denominators and other guards."""

VEGA_FLOOR: float = 1e-12
"""Below this vega value, Newton-Raphson IV iteration is considered unsafe."""

SIGMA_FLOOR: float = 1e-12
"""Minimum allowed value for sigma / vol parameters (strict floor)."""

A_FLOOR: float = 1e-8
"""Floor for SVI parameter 'a' (overall variance level)."""

B_FLOOR: float = 1e-15
"""Floor for SVI parameter 'b' (wing slope)."""

RHO_TOL: float = 0.999
"""Hard clip bound for rho: |rho| < RHO_TOL (strict inequality)."""

R2_FLOOR: float = 1e-15
"""Below this total sum-of-squares, R² is reported as 0.0."""


# ---------------------------------------------------------------------------
# Convenience accessor
# ---------------------------------------------------------------------------


def get_tolerances() -> dict[str, float]:
    """Return a dictionary of all named tolerances for diagnostic/report use.

    Returns
    -------
    dict
        Keys: 'price_tol', 'vol_tol', 'arbitrage_tol', 'calibration_tol'.
    """
    return {
        "price_tol": PRICE_TOL,
        "vol_tol": VOL_TOL,
        "arbitrage_tol": ARBITRAGE_TOL,
        "calibration_tol": CALIBRATION_TOL,
    }