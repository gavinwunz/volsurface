"""volfoundry.pricers — option pricing engines.

Provides three complementary pricing engines for European and American options
under the Black-76 (forwards/futures) formulation:

    black_scholes  — Analytical Black-76 pricing with full Greek computations,
                     vectorised operations, and put-call parity helpers.

    binomial       — Cox-Ross-Rubinstein (CRR) binomial tree supporting both
                     European and American exercise styles, with tree-based
                     finite-difference Greeks.

    monte_carlo    — Monte Carlo engine with antithetic variates and Black-Scholes
                     delta-hedged control variate for variance reduction.

    _core          — C++ hot path (pybind11) with vectorised price + all Greeks
                     in a single pass for maximum throughput.

All pricers operate on the forward price F (not spot S), consistent with the
rest of the VolFoundry pipeline.
"""

from __future__ import annotations

from volfoundry.pricers.black_scholes import (
    OptionType,
    black76_all_greeks,
    black76_delta,
    black76_gamma,
    black76_price,
    black76_rho,
    black76_theta,
    black76_vega,
    norm_cdf,
    norm_pdf,
    parity_check_call,
    parity_check_put,
    price_and_greeks_vectorized,
)
from volfoundry.pricers.binomial import crr_greeks, crr_price
from volfoundry.pricers.monte_carlo import (
    mc_price,
    mc_price_with_confidence,
)

# The C++ extension is loaded when available; gracefully degrade to pure
# Python otherwise (the Python implementations cover the same interface).
try:
    from volfoundry.pricers._core import (  # noqa: F401
        black76_price as _cpp_black76_price,
        black76_price_greeks_vectorized as _cpp_black76_price_greeks_vectorized,
    )
    _HAS_CPP = True
except ImportError:
    _HAS_CPP = False

__all__ = [
    "OptionType",
    "black76_all_greeks",
    "black76_delta",
    "black76_gamma",
    "black76_price",
    "black76_rho",
    "black76_theta",
    "black76_vega",
    "norm_cdf",
    "norm_pdf",
    "parity_check_call",
    "parity_check_put",
    "price_and_greeks_vectorized",
    "crr_greeks",
    "crr_price",
    "mc_price",
    "mc_price_with_confidence",
    "_HAS_CPP",
]