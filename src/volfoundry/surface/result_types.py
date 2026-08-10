"""Structured result objects for the VolFoundry high-level API.

These dataclasses provide typed, inspectable outputs from the calibration
and validation pipeline instead of loose dictionaries or tuples.

All timestamp fields are timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Market data containers
# ---------------------------------------------------------------------------


@dataclass
class OptionChain:
    """Typed boundary representation for a cleaned option chain.

    This is the input format accepted by ``SurfaceBuilder.fit()`` for
    offline / offline-first workflows.  It can be constructed directly from
    a ``Snapshot`` or from a DataFrame of cleaned quotes.

    Attributes
    ----------
    currency : str
        Underlying currency, e.g. ``"BTC"`` or ``"ETH"``.
    timestamp : datetime
        Retrieval / construction timestamp (timezone-aware UTC).
    source : str
        Where the data came from (``"deribit"``, ``"parquet"``, ``"manual"``).
    quotes : DataFrame
        Cleaned quote records.  Expected columns: ``strike``, ``expiry``
        (timezone-aware datetime), ``option_type`` (``"C"`` or ``"P"``),
        ``mid``, ``bid``, ``ask``, ``underlying_price``.
    forwards : dict, optional
        Pre-computed forwards keyed by expiry datetime.  If empty,
        ``SurfaceBuilder`` will estimate them via put-call parity.
    schema_version : int
        Schema version for serialisation compatibility.
    metadata : dict
        Arbitrary extra metadata (e.g. filtering parameters used).
    """

    currency: str
    timestamp: datetime
    source: str
    quotes: pd.DataFrame = field(default_factory=pd.DataFrame)
    forwards: dict = field(default_factory=dict)
    schema_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quotes is None:
            self.quotes = pd.DataFrame()


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------


@dataclass
class ValidationReport:
    """Structured no-arbitrage validation report for a calibrated surface.

    Every numerical check records its evaluation domain and tolerance so
    that results are interpretable and reproducible.

    Attributes
    ----------
    is_valid : bool
        ``True`` when all requested checks pass within tolerance over the
        evaluation domain.  ``False`` when at least one check fails.
    butterfly_passed : bool or None
        ``True`` if g(k) >= tol for all k in the evaluation grid for every
        slice.  ``None`` when not run.
    calendar_passed : bool or None
        ``True`` if total variance is monotonic in expiry at every grid
        point.  ``None`` for single-slice surfaces.
    density_passed : bool or None
        ``True`` if the Breeden-Litzenberger density cross-check is
        non-negative at all interior strikes.  ``None`` when not run.
    analytical_conditions : dict
        Map from condition name to ``True``/``False``/``None``, e.g.
        ``{"rho_domain": True, "theta_positive": True, "lee_bound": True}``.
    rejected_slices : list[str]
        Identifiers of slices that failed any check.
    rejection_reasons : dict[str, list[str]]
        Map from slice identifier to a list of human-readable failure reasons.
    evaluation_domain : dict
        Description of the numerical domain used, e.g.
        ``{"k_min": -2.0, "k_max": 2.0, "n_k": 1001, "n_T": 15}``.
    tolerances : dict
        Tolerances used during validation, e.g.
        ``{"butterfly_tol": -1e-12, "calendar_tol": -1e-12, "bl_tol": -1e-12}``.
    per_slice : list[dict]
        Per-slice diagnostic summaries (butterfly min-g, RMSE, etc.).
    warnings : list[str]
        Non-fatal warnings collected during calibration and validation.
    """

    is_valid: bool = False
    butterfly_passed: Optional[bool] = None
    calendar_passed: Optional[bool] = None
    density_passed: Optional[bool] = None
    analytical_conditions: dict[str, Optional[bool]] = field(default_factory=dict)
    rejected_slices: list[str] = field(default_factory=list)
    rejection_reasons: dict[str, list[str]] = field(default_factory=dict)
    evaluation_domain: dict[str, Any] = field(default_factory=dict)
    tolerances: dict[str, float] = field(default_factory=dict)
    per_slice: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Surface fit result
# ---------------------------------------------------------------------------


@dataclass
class SurfaceFitResult:
    """Complete result from ``SurfaceBuilder.fit()``.

    Bundles the calibrated surface, validation report, and all diagnostics
    so users can inspect every aspect of the fit without digging into
    internal module state.

    Attributes
    ----------
    surface : VolatilitySurface or None
        The calibrated surface.  ``None`` only when the fit failed entirely.
    validation : ValidationReport
        Structured no-arbitrage validation.
    calibration_status : str
        High-level status: ``"converged"``, ``"converged_invalid"``,
        ``"did_not_converge"``, or ``"failed"``.
    optimizer_diagnostics : dict
        Optimizer termination info (success, message, iterations, objective).
    quote_cleaning_stats : dict
        Per-reason counts of quotes removed before calibration, e.g.
        ``{"raw": 794, "removed_zero_bid": 41, "retained": 711}``.
    per_expiry_diagnostics : list[dict]
        Per-expiry calibration results (RMSE, R², n_points, etc.).
    global_diagnostics : dict
        Global calibration stats (total RMSE, total R², global parameters).
    source_snapshot : dict
        Metadata about the source data (currency, timestamp, source).
    warnings : list[str]
        Non-fatal warnings collected during the full pipeline.
    theta_raw : Optional[ndarray]
        Raw ATM total variances estimated from the market before any
        monotonicity repair.
    theta_adjusted : Optional[ndarray]
        ATM total variances used by the calibrated surface (may differ
        from raw if a monotonicity repair was applied).
    """

    surface: Optional[Any] = None  # VolatilitySurface — forward ref
    validation: ValidationReport = field(default_factory=ValidationReport)
    calibration_status: str = "failed"
    optimizer_diagnostics: dict[str, Any] = field(default_factory=dict)
    quote_cleaning_stats: dict[str, int] = field(default_factory=dict)
    per_expiry_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    global_diagnostics: dict[str, Any] = field(default_factory=dict)
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    theta_raw: Optional[np.ndarray] = None
    theta_adjusted: Optional[np.ndarray] = None