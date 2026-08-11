"""VolFoundry exception taxonomy.

All VolFoundry-specific exceptions inherit from ``VolFoundryError`` so that
callers can catch library errors as a group.  Detailed exception classes
allow granular handling of different failure modes.

Exceptions are always **raised** by library code (never ``sys.exit()``), and
original exceptions are preserved as ``__cause__`` when wrapping.
"""

from __future__ import annotations


class VolFoundryError(Exception):
    """Base class for all VolFoundry exceptions."""


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------


class DataError(VolFoundryError):
    """Base for data-layer errors (fetch, validation, persistence)."""


class MarketDataError(DataError):
    """Error fetching or parsing market data from an external source."""


class QuoteValidationError(DataError):
    """Quote data failed validation checks."""


class PersistenceError(DataError):
    """Error reading or writing snapshot data."""


# ---------------------------------------------------------------------------
# Pricing layer
# ---------------------------------------------------------------------------


class PricingError(VolFoundryError):
    """Base for pricing errors."""


class ImpliedVolError(PricingError):
    """Implied volatility inversion failed or returned non-finite result."""


# ---------------------------------------------------------------------------
# Calibration layer
# ---------------------------------------------------------------------------


class CalibrationError(VolFoundryError):
    """Base for calibration errors."""


class CalibrationConvergenceError(CalibrationError):
    """The calibration optimizer did not converge."""


class InvalidSurfaceError(CalibrationError):
    """The calibrated surface does not satisfy required conditions."""


class ArbitrageViolationError(InvalidSurfaceError):
    """The surface fails no-arbitrage validation in strict mode.

    This is raised when ``SurfaceBuilder.fit(..., validation="strict")``
    produces a surface that violates one or more no-arbitrage conditions
    within the configured tolerance and evaluation domain.
    """


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigurationError(VolFoundryError):
    """Invalid configuration or parameter values."""
