"""SurfaceBuilder — high-level calibration orchestrator.

``SurfaceBuilder`` is the primary entry point for constructing volatility
surfaces.  It accepts a ``Snapshot``, ``OptionChain``, or raw DataFrame and
runs the full pipeline:

1. Quote cleaning with diagnostic counts.
2. Forward extraction via put-call parity regression.
3. Raw SVI calibration per expiry slice.
4. Global SSVI calibration across all slices.
5. No-arbitrage validation (report or strict mode).

Offline usage is a first-class path: supply a DataFrame or ``OptionChain``
and no network call is ever made.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Union

import numpy as np
import pandas as pd

from volfoundry.arbitrage.checks import (
    SliceValidationReport,
    check_slice_arbitrage,
    validate_surface,
)
from volfoundry.data.fetcher import Snapshot
from volfoundry.data.filters import clean_quotes as _clean_quotes
from volfoundry.data.forwards import extract_forwards
from volfoundry.iv.black_scholes import (
    OptionType,
    black76_price,
    implied_vol_brent,
)
from volfoundry.surface.calibration import (
    SsviCalibrationResult,
    calibrate_ssvi_surface,
)
from volfoundry.surface.result_types import (
    OptionChain,
    SurfaceFitResult,
    ValidationReport,
)
from volfoundry.surface.ssvi import SsviParams
from volfoundry.surface.volatility_surface import VolatilitySurface
from volfoundry.svi.calibration import (
    SviCalibrationResult,
    build_vega_weights,
    calibrate_svi_slice,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_K_RANGE = (-3.0, 3.0)
DEFAULT_N_K = 501
DEFAULT_MIN_QUOTES_PER_SLICE = 4


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class SurfaceBuilder:
    """Orchestrate the full calibration pipeline for volatility surfaces.

    The builder accepts market data (live snapshot, DataFrame, or
    ``OptionChain``) and produces a ``SurfaceFitResult`` containing the
    calibrated ``VolatilitySurface`` and a structured ``ValidationReport``.

    Parameters
    ----------
    min_quotes_per_slice : int
        Minimum number of cleaned quotes required for a single expiry slice
        to be calibrated.  Slices with fewer quotes are skipped.
    min_expiry_days : float
        Minimum days to expiry for quote filtering (default 2.0).
    svi_outer_tol : float
        Outer optimization tolerance for raw SVI calibration.
    ssvi_tol : float
        Optimization tolerance for global SSVI calibration.
    k_range : tuple[float, float]
        Default log-moneyness range for arbitrage validation.
    n_k : int
        Number of points in the validation k-grid.
    butterfly_tol : float
        Tolerance for butterfly (g(k) >= tol for no arbitrage).
    calendar_tol : float
        Tolerance for calendar monotonicity.
    """

    def __init__(
        self,
        min_quotes_per_slice: int = DEFAULT_MIN_QUOTES_PER_SLICE,
        min_expiry_days: float = 2.0,
        svi_outer_tol: float = 1e-8,
        ssvi_tol: float = 1e-8,
        k_range: tuple[float, float] = DEFAULT_K_RANGE,
        n_k: int = DEFAULT_N_K,
        butterfly_tol: float = -1e-12,
        calendar_tol: float = -1e-12,
    ) -> None:
        self.min_quotes_per_slice = min_quotes_per_slice
        self.min_expiry_days = min_expiry_days
        self.svi_outer_tol = svi_outer_tol
        self.ssvi_tol = ssvi_tol
        self.k_range = k_range
        self.n_k = n_k
        self.butterfly_tol = butterfly_tol
        self.calendar_tol = calendar_tol

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def fit(
        self,
        data: Union[Snapshot, OptionChain, pd.DataFrame],
        validation: str = "report",
        rho: Optional[float] = None,
        r: float = 0.0,
    ) -> SurfaceFitResult:
        """Fit a volatility surface to market data.

        Parameters
        ----------
        data : Snapshot, OptionChain, or DataFrame
            Market data.  A ``Snapshot`` triggers the full pipeline
            (cleaning → forwards → calibration).  An ``OptionChain`` or
            DataFrame of cleaned quotes skips the raw-data cleaning step.
        validation : str
            ``"report"`` — always returns a result, even if the surface
            fails arbitrage checks.  The ``ValidationReport.is_valid``
            flag distinguishes valid from invalid fits.
            ``"strict"`` — raises ``ArbitrageViolationError`` if the
            calibrated surface fails validation.
        rho : float, optional
            Fix the SSVI correlation parameter.  If ``None``, rho is
            calibrated jointly with eta and lambda.
        r : float
            Risk-free rate used in calibration diagnostics (default 0).

        Returns
        -------
        SurfaceFitResult

        Raises
        ------
        ValueError
            If the input data is empty or cannot be processed.
        ArbitrageViolationError
            Only in ``validation="strict"`` mode when the surface fails
            no-arbitrage checks.
        """
        # --- Normalise input to a DataFrame ----------------------------------
        source_meta: dict = {}
        if isinstance(data, Snapshot):
            source_meta = {
                "currency": data.currency,
                "timestamp": data.timestamp.isoformat(),
                "source": "deribit",
            }
            df_raw = data.to_dataframe()
            if df_raw.empty:
                raise ValueError("Snapshot contains no quotes")
            df, cleaning_stats = self._clean_from_raw(df_raw)
        elif isinstance(data, OptionChain):
            source_meta = {
                "currency": data.currency,
                "timestamp": data.timestamp.isoformat(),
                "source": data.source,
            }
            df = data.quotes.copy()
            cleaning_stats = {"raw": len(df), "retained": len(df)}
            if data.forwards:
                source_meta["forwards_provided"] = len(data.forwards)
                self._precomputed_forwards = data.forwards
            else:
                self._precomputed_forwards = None
        elif isinstance(data, pd.DataFrame):
            source_meta = {
                "currency": data.get("underlying", pd.Series(["UNKNOWN"])).iloc[0]
                if "underlying" in data.columns
                else "UNKNOWN",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "dataframe",
            }
            df = data.copy()
            cleaning_stats = {"raw": len(df), "retained": len(df)}
            self._precomputed_forwards = None
        else:
            raise TypeError(
                f"data must be Snapshot, OptionChain, or DataFrame, got {type(data)}"
            )

        if df.empty:
            raise ValueError("No quotes available after cleaning")

        # --- Extract forwards -------------------------------------------------
        forwards = getattr(self, "_precomputed_forwards", None)
        if forwards:
            forward_results = forwards
        else:
            reference_time = datetime.now(timezone.utc)
            forward_results = extract_forwards(df, reference_time=reference_time)

        if not forward_results:
            raise ValueError("Could not extract any forward prices from the data")

        # --- Prepare slices for calibration ----------------------------------
        slices_data, slice_ids, expiry_times, T_list = self._prepare_slices(
            df, forward_results, r
        )

        if len(slices_data) < 1:
            raise ValueError("No valid expiry slices for calibration")

        # --- Raw SVI per slice -----------------------------------------------
        raw_svi_results: list[SviCalibrationResult] = []
        for (k, w_obs, T_i) in slices_data:
            try:
                svi_result = calibrate_svi_slice(
                    k=k,
                    w_observed=w_obs,
                    T=T_i,
                    outer_tol=self.svi_outer_tol,
                )
                raw_svi_results.append(svi_result)
            except Exception as exc:
                logger.warning("SVI calibration failed for slice T=%.4f: %s", T_i, exc)
                raw_svi_results.append(
                    SviCalibrationResult(
                        params=None,  # type: ignore[arg-type]
                        outer_success=False,
                        outer_message=str(exc),
                        r2=0.0,
                        rmse=np.inf,
                        rmse_unweighted=np.inf,
                        n_points=len(k),
                        k_min=float(np.min(k)),
                        k_max=float(np.max(k)),
                    )
                )

        # --- Global SSVI calibration -----------------------------------------
        ssvi_result = calibrate_ssvi_surface(
            slices_data=slices_data,
            expiration_times=T_list,
            rho=rho,
            tol=self.ssvi_tol,
        )

        # --- Build VolatilitySurface -----------------------------------------
        surface = VolatilitySurface(
            params=ssvi_result.params,
            expiry_times=ssvi_result.expiry_times,
            currency=source_meta.get("currency", ""),
            r=r,
        )

        # --- Validation -------------------------------------------------------
        validation_report = self._validate(
            ssvi_result=ssvi_result,
            slice_ids=slice_ids,
            surface=surface,
        )

        # --- Determine status -------------------------------------------------
        if not ssvi_result.success:
            status = "did_not_converge"
            validation_report.warnings.append(
                f"SSVI optimizer: {ssvi_result.message}"
            )
        elif validation_report.is_valid:
            status = "converged"
        else:
            status = "converged_invalid"

        # --- Per-expiry diagnostics ------------------------------------------
        per_expiry = []
        for i, (svi_r, sid) in enumerate(zip(raw_svi_results, slice_ids)):
            per_expiry.append({
                "slice_id": sid,
                "T": float(T_list[i]),
                "svi_success": svi_r.outer_success,
                "svi_rmse": svi_r.rmse,
                "svi_r2": svi_r.r2,
                "n_points": svi_r.n_points,
            })

        # --- Global diagnostics -----------------------------------------------
        global_diag = {
            "rho": ssvi_result.rho,
            "eta": ssvi_result.eta,
            "lambda": ssvi_result.lamb,
            "rmse": ssvi_result.rmse,
            "r2": ssvi_result.r2,
            "calendar_violations": ssvi_result.calendar_violations,
            "n_slices": len(slices_data),
            "n_total_quotes": sum(len(sd[0]) for sd in slices_data),
        }

        result = SurfaceFitResult(
            surface=surface,
            validation=validation_report,
            calibration_status=status,
            optimizer_diagnostics={
                "success": ssvi_result.success,
                "message": ssvi_result.message,
            },
            quote_cleaning_stats=cleaning_stats,
            per_expiry_diagnostics=per_expiry,
            global_diagnostics=global_diag,
            source_snapshot=source_meta,
            warnings=validation_report.warnings,
            theta_raw=ssvi_result.theta_values.copy(),
            theta_adjusted=ssvi_result.theta_values.copy(),
        )

        # --- Strict mode ------------------------------------------------------
        if validation == "strict" and not validation_report.is_valid:
            from volfoundry.exceptions import ArbitrageViolationError  # deferred

            raise ArbitrageViolationError(
                f"Surface failed strict no-arbitrage validation: "
                f"{len(validation_report.rejected_slices)} slice(s) rejected. "
                f"Reasons: {validation_report.rejection_reasons}"
            )

        return result

    def fit_dataframe(
        self,
        df: pd.DataFrame,
        validation: str = "report",
        rho: Optional[float] = None,
        r: float = 0.0,
    ) -> SurfaceFitResult:
        """Fit a surface from a cleaned DataFrame (offline path).

        Convenience wrapper around ``fit()``.  No network calls are made.

        Parameters
        ----------
        df : DataFrame
            Cleaned quotes with columns: ``strike``, ``expiry``, ``mid``,
            ``bid``, ``ask``, ``option_type`` (``"C"`` or ``"P"``).
        validation : str
            ``"report"`` or ``"strict"``.
        rho : float, optional
            Fixed correlation.
        r : float
            Risk-free rate.

        Returns
        -------
        SurfaceFitResult
        """
        return self.fit(data=df, validation=validation, rho=rho, r=r)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _clean_from_raw(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """Apply quote filters and return (cleaned_df, cleaning_stats)."""
        cleaned_df, cleaning_report = _clean_quotes(
            df, min_days=self.min_expiry_days
        )
        stats = {**cleaning_report.removed_counts,
                 "raw": cleaning_report.raw_count,
                 "retained": cleaning_report.retained_count}
        return cleaned_df, stats

    def _prepare_slices(
        self,
        df: pd.DataFrame,
        forward_results: dict,
        r: float,
    ) -> tuple[list, list, np.ndarray, list]:
        """Build calibration slices from cleaned quotes and forwards."""
        slices_data = []
        slice_ids = []
        T_list = []

        for expiry, fwd_result in sorted(forward_results.items(),
                                          key=lambda x: x[0]):
            # Match on date only to avoid microsecond mismatch between
            # the expiry column and the forward-results key
            exp_date = pd.Timestamp(expiry).date()
            exp_df = df[pd.to_datetime(df["expiry"], utc=True).dt.date == exp_date]
            if exp_df.empty:
                continue

            T = fwd_result.T
            F = fwd_result.F

            # Compute log-moneyness and total implied variance
            k_vals = []
            w_vals = []

            for _, row in exp_df.iterrows():
                strike = float(row["strike"])
                mid_price = float(row["mid"])
                if mid_price <= 0 or strike <= 0:
                    continue

                # Compute IV from mid price
                ot = OptionType.CALL if row["option_type"] == "C" else OptionType.PUT
                try:
                    iv = implied_vol_brent(mid_price, F, strike, T, r, ot)
                except (ValueError, RuntimeError):
                    continue
                if not np.isfinite(iv) or iv <= 0:
                    continue

                k = np.log(strike / F)
                w = iv * iv * T
                k_vals.append(k)
                w_vals.append(w)

            if len(k_vals) < self.min_quotes_per_slice:
                continue

            k_arr = np.array(k_vals)
            w_arr = np.array(w_vals)
            slices_data.append((k_arr, w_arr, T))
            slice_ids.append(f"{fwd_result.expiry.date()}")
            T_list.append(T)

        expiry_times = np.array(T_list)
        return slices_data, slice_ids, expiry_times, T_list

    def _validate(
        self,
        ssvi_result: SsviCalibrationResult,
        slice_ids: list[str],
        surface: VolatilitySurface,
    ) -> ValidationReport:
        """Run no-arbitrage validation on the calibrated surface."""
        k_grid = np.linspace(self.k_range[0], self.k_range[1], self.n_k)

        # Build SVI parameter slices for the existing validator
        svi_slices = []
        for i, (T_i, theta_i) in enumerate(
            zip(ssvi_result.expiry_times, ssvi_result.theta_values)
        ):
            phi_i = ssvi_result.params.phi(float(theta_i))
            from volfoundry.surface.ssvi import ssvi_to_raw_svi

            raw_params = ssvi_to_raw_svi(float(theta_i), float(phi_i), ssvi_result.params.rho)
            svi_slices.append((slice_ids[i] if i < len(slice_ids) else f"slice_{i}",
                               raw_params, float(T_i)))

        # Run the existing multi-slice validator
        arb_report = validate_surface(
            slices=svi_slices,
            k_grid=k_grid,
        )

        # Build analytical conditions
        lee_ok = ssvi_result.params.satisfies_lee_bound()
        theta_positive = bool(np.all(ssvi_result.theta_values > 0))
        lam_domain = 0.0 <= ssvi_result.lamb <= 1.0
        analytical = {
            "rho_domain": -0.999 < ssvi_result.rho < 0.999,
            "theta_positive": theta_positive,
            "lambda_domain": lam_domain,
            "lee_bound": lee_ok,
        }

        is_valid = arb_report.all_passed and all(
            v for v in analytical.values() if v is not None
        )

        # Per-slice details
        per_slice = []
        for ar in arb_report.slice_results:
            per_slice.append({
                "slice_id": ar.slice_id,
                "T": ar.T,
                "butterfly_passed": ar.butterfly_passed,
                "butterfly_min_g": ar.butterfly_min_g,
                "bl_passed": ar.bl_passed,
                "k_range": ar.k_range,
            })

        # Rejection reasons
        rejection_reasons: dict[str, list[str]] = {}
        for sid in arb_report.rejected_slices:
            reasons = []
            for ar in arb_report.slice_results:
                if ar.slice_id == sid:
                    if not ar.butterfly_passed:
                        reasons.append(f"butterfly (min g={ar.butterfly_min_g:.4e})")
                    if ar.bl_passed is not None and not ar.bl_passed:
                        reasons.append("BL density negative")
                    break
            rejection_reasons[sid] = reasons
        if arb_report.calendar_passed is not None and not arb_report.calendar_passed:
            rejection_reasons["_calendar"] = [
                f"{len(arb_report.calendar_violations)} calendar violation pair(s)"
            ]

        return ValidationReport(
            is_valid=is_valid,
            butterfly_passed=arb_report.slice_results
            and all(sr.butterfly_passed for sr in arb_report.slice_results),
            calendar_passed=arb_report.calendar_passed,
            density_passed=(
                all(sr.bl_passed for sr in arb_report.slice_results if sr.bl_passed is not None)
                if any(sr.bl_passed is not None for sr in arb_report.slice_results)
                else None
            ),
            analytical_conditions=analytical,
            rejected_slices=arb_report.rejected_slices,
            rejection_reasons=rejection_reasons,
            evaluation_domain={
                "k_min": float(self.k_range[0]),
                "k_max": float(self.k_range[1]),
                "n_k": self.n_k,
                "n_slices": len(ssvi_result.theta_values),
            },
            tolerances={
                "butterfly_tol": self.butterfly_tol,
                "calendar_tol": self.calendar_tol,
            },
            per_slice=per_slice,
            warnings=(
                [f"SSVI optimizer: {ssvi_result.message}"] if not ssvi_result.success else []
            ),
        )