"""Forward-price extraction via put-call parity regression.

For each expiry, we regress the mid-market put-call parity:

    C - P = exp(-rT) * (F - K)   =>   C - P = alpha + beta * K

where:
   alpha = exp(-rT) * F
   beta  = -exp(-rT)

and we recover:
   F = -alpha / beta        (unbiased forward)
   r = -log(-beta) / T      (implied discount rate)

We do NOT assume constant r or zero dividends — the discount factor exp(-rT)
embeds any cash/coin dividend yield.

The regression is OLS with intercept and slope.  Pairs whose mid is zero or
negative are excluded before the fit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from volfoundry.tolerances import EPSILON, R2_FLOOR

logger = logging.getLogger(__name__)


@dataclass
class ForwardResult:
    """Per-expiry result of the put-call parity regression."""

    expiry: datetime
    T: float  # time to expiry in years
    F: float  # forward price
    discount_factor: float  # exp(-rT)
    r: float  # implied discount rate (continuous)
    r2: float  # OLS R-squared
    n_pairs: int  # number of C-P pairs used
    n_calls: int  # calls available at this expiry
    n_puts: int  # puts available at this expiry


def extract_forwards(
    df: pd.DataFrame,
    reference_time: datetime | None = None,
    min_pairs: int = 3,
) -> dict[datetime, ForwardResult]:
    """Extract forward prices per expiry from put-call parity.

    Parameters
    ----------
    df : DataFrame
        Cleaned quotes with columns: expiry, option_type, strike, mid.
        ``option_type`` must be "C" or "P".
    reference_time : datetime, optional
        Reference time for T calculation (default: snapshot_ts or now UTC).
    min_pairs : int
        Minimum number of C-P pairs required to fit for an expiry.

    Returns
    -------
    dict
        Map from expiry datetime to ForwardResult.
    """
    if reference_time is None:
        # Try to use snapshot_ts from the data; fall back to now
        ref_candidates = pd.to_datetime(df.get("snapshot_ts", pd.NaT), utc=True)
        if ref_candidates.notna().any():
            reference_time = ref_candidates.iloc[0]
        else:
            reference_time = pd.Timestamp.now(tz="UTC")
    reference_time = pd.Timestamp(reference_time)

    # Split into calls and puts
    calls = df[df["option_type"] == "C"].copy()
    puts = df[df["option_type"] == "P"].copy()

    # Group by expiry
    call_groups = calls.groupby("expiry")
    put_groups = puts.groupby("expiry")

    all_expiries = sorted(set(calls["expiry"].unique()) | set(puts["expiry"].unique()))

    results: dict[datetime, ForwardResult] = {}

    for expiry in all_expiries:
        expiry_dt = pd.Timestamp(expiry)
        T = max((expiry_dt - reference_time).total_seconds() / 365.25 / 86400, EPSILON)

        cdf = call_groups.get_group(expiry) if expiry in call_groups.groups else pd.DataFrame()
        pdf = put_groups.get_group(expiry) if expiry in put_groups.groups else pd.DataFrame()

        n_calls = len(cdf)
        n_puts = len(pdf)

        # Merge calls and puts on strike
        merged = pd.merge(
            cdf[["strike", "mid"]],
            pdf[["strike", "mid"]],
            on="strike",
            suffixes=("_call", "_put"),
        )

        # Drop rows where either mid is non-positive
        merged = merged[(merged["mid_call"] > 0) & (merged["mid_put"] > 0)]

        if len(merged) < min_pairs:
            logger.debug(
                "Expiry %s: only %d pairs (need %d), skipping",
                expiry_dt.date(),
                len(merged),
                min_pairs,
            )
            continue

        # Put-call parity: C - P = exp(-rT)(F - K) => C - P = alpha + beta * K
        y = merged["mid_call"].values - merged["mid_put"].values  # C - P
        X = np.column_stack([np.ones_like(y), merged["strike"].values])  # [1, K]

        # OLS: theta = (X^T X)^{-1} X^T y
        theta, _residuals, _rank, _singular = np.linalg.lstsq(X, y, rcond=None)

        alpha, beta = theta[0], theta[1]  # alpha = exp(-rT) * F, beta = -exp(-rT)

        if abs(beta) < EPSILON or beta >= 0:
            logger.warning(
                "Expiry %s: degenerate beta=%.6f (should be negative), skipping",
                expiry_dt.date(),
                beta,
            )
            continue

        discount_factor = -beta
        F = alpha / (-beta)  # = alpha / discount_factor
        r = -np.log(discount_factor) / T  # continuous rate

        # R-squared
        y_pred = X @ theta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = float(1 - ss_res / ss_tot) if ss_tot > R2_FLOOR else 0.0

        results[expiry_dt] = ForwardResult(
            expiry=expiry_dt,
            T=float(T),
            F=float(F),
            discount_factor=float(discount_factor),
            r=float(r),
            r2=float(r2),
            n_pairs=len(merged),
            n_calls=n_calls,
            n_puts=n_puts,
        )

        logger.info(
            "Expiry %s: F=%.2f, r=%.4f, df=%.6f, R²=%.4f, n=%d pairs",
            expiry_dt.date(),
            F,
            r,
            discount_factor,
            r2,
            len(merged),
        )

    return results


def compute_time_to_expiry(expiries: list[datetime], reference_time: datetime) -> np.ndarray:
    """Compute time-to-expiry in years for a list of expiry datetimes."""
    ref = pd.Timestamp(reference_time)
    return np.array(
        [max((pd.Timestamp(e) - ref).total_seconds() / 86400.0 / 365.25, EPSILON) for e in expiries]
    )
