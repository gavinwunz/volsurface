"""VolFoundry -- open-source volatility infrastructure for derivatives.

VolFoundry turns live or historical option chains into calibrated volatility
surfaces with explicit numerical diagnostics and reproducible market snapshots.

.. code-block:: python

    from volfoundry import DeribitClient, SurfaceBuilder

    snapshot = DeribitClient().fetch("BTC")
    result = SurfaceBuilder().fit(snapshot, validation="strict")
    print(result.surface.iv(strike=70000, maturity=30 / 365.25))
    print(result.validation.is_valid)
"""

from volfoundry._version import __version__ as __version__
from volfoundry.client import DeribitClient
from volfoundry.exceptions import (
    ArbitrageViolationError,
    CalibrationConvergenceError,
    CalibrationError,
    ConfigurationError,
    DataError,
    ImpliedVolError,
    InvalidSurfaceError,
    MarketDataError,
    PersistenceError,
    PricingError,
    QuoteValidationError,
    VolFoundryError,
)
from volfoundry.surface.builder import SurfaceBuilder
from volfoundry.surface.result_types import (
    OptionChain,
    SurfaceFitResult,
    ValidationReport,
)
from volfoundry.surface.volatility_surface import VolatilitySurface

__all__ = [
    "__version__",
    # High-level API
    "DeribitClient",
    "SurfaceBuilder",
    "VolatilitySurface",
    # Structured results
    "SurfaceFitResult",
    "ValidationReport",
    "OptionChain",
    # Exceptions
    "VolFoundryError",
    "DataError",
    "MarketDataError",
    "QuoteValidationError",
    "PersistenceError",
    "PricingError",
    "ImpliedVolError",
    "CalibrationError",
    "CalibrationConvergenceError",
    "InvalidSurfaceError",
    "ArbitrageViolationError",
    "ConfigurationError",
]