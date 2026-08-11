"""Quote filters for cleaning raw option-chain data.

Filters applied in order:
1. Remove quotes with zero bid or zero ask.
2. Remove quotes with crossed markets (bid > ask).
3. Remove quotes with fewer than 2 calendar days to expiry.

Each filter returns both the filtered DataFrame and diagnostic records so
callers can inspect exactly what was removed and why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from volfoundry.data.fetcher import QuoteCleaningReport, QuoteRemovalRecord

logger = logging.getLogger(__name__)

MIN_DAYS_TO_EXPIRY = 2.0


@dataclass
class _FilterResult:
    """Internal: a filter's output --- filtered data + removal records."""

    df: pd.DataFrame
    removals: list[QuoteRemovalRecord] = field(default_factory=list)


def filter_zero_bid_ask(df: pd.DataFrame) -> _FilterResult:
    """Drop rows where bid <= 0 or ask <= 0.  Also drops negative bid/ask.

    Returns a filtered copy; does not mutate the original.
    """
    if df.empty:
        return _FilterResult(df=df.copy())

    removals: list[QuoteRemovalRecord] = []
    before = len(df)
    mask = (df["bid"] > 0) & (df["ask"] > 0)
    result = df[mask].copy()
    dropped = before - len(result)

    if dropped:
        df.loc[~mask, "instrument_name"].tolist()
        # Distinguish zero-bid, zero-ask, and negative for diagnostics
        for _i, row in df[~mask].iterrows():
            name = row.get("instrument_name", "")
            if row["bid"] <= 0:
                reason = "negative_bid" if row["bid"] < 0 else "zero_bid"
                removals.append(QuoteRemovalRecord(name, reason))
            elif row["ask"] <= 0:
                reason = "negative_ask" if row["ask"] < 0 else "zero_ask"
                removals.append(QuoteRemovalRecord(name, reason))
        logger.debug("Zero-bid/ask filter: dropped %d/%d rows", dropped, before)

    return _FilterResult(df=result, removals=removals)


def filter_crossed(df: pd.DataFrame) -> _FilterResult:
    """Drop rows where bid > ask (crossed market).

    Returns a filtered copy; does not mutate the original.
    """
    if df.empty:
        return _FilterResult(df=df.copy())

    removals: list[QuoteRemovalRecord] = []
    before = len(df)
    mask = df["bid"] <= df["ask"]
    result = df[mask].copy()
    dropped = before - len(result)

    if dropped:
        for _, row in df[~mask].iterrows():
            name = row.get("instrument_name", "")
            removals.append(
                QuoteRemovalRecord(name, "crossed_market", f"bid={row['bid']} > ask={row['ask']}")
            )
        logger.debug("Crossed-market filter: dropped %d/%d rows", dropped, before)

    return _FilterResult(df=result, removals=removals)


def filter_min_days_to_expiry(
    df: pd.DataFrame,
    min_days: float = MIN_DAYS_TO_EXPIRY,
    reference_time: datetime | None = None,
) -> _FilterResult:
    """Drop rows where time-to-expiry is less than *min_days*.

    Parameters
    ----------
    df : DataFrame
        Must contain an ``expiry`` column of timezone-aware datetimes.
    min_days : float
        Minimum calendar days to expiry (default 2.0).
    reference_time : datetime, optional
        Reference timestamp (default: now UTC).

    Returns
    -------
    _FilterResult
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    if df.empty:
        return _FilterResult(df=df.copy())

    removals: list[QuoteRemovalRecord] = []
    before = len(df)
    expiry = pd.to_datetime(df["expiry"], utc=True)
    tte = (expiry - reference_time).dt.total_seconds() / 86400.0
    mask = tte >= min_days
    result = df[mask].copy()
    dropped = before - len(result)

    if dropped:
        for _, row in df[~mask].iterrows():
            name = row.get("instrument_name", "")
            tte_val = (row["expiry"] - reference_time).total_seconds() / 86400.0
            removals.append(
                QuoteRemovalRecord(
                    name, "near_expiry", f"{tte_val:.2f} days to expiry < {min_days} minimum"
                )
            )
        logger.debug(
            "Min-days-to-expiry filter (< %.1f days): dropped %d/%d rows",
            min_days,
            dropped,
            before,
        )

    return _FilterResult(df=result, removals=removals)


def clean_quotes(
    df: pd.DataFrame,
    min_days: float = MIN_DAYS_TO_EXPIRY,
    reference_time: datetime | None = None,
) -> tuple[pd.DataFrame, QuoteCleaningReport]:
    """Apply all data-layer filters and return a cleaning report.

    Parameters
    ----------
    df : DataFrame
        Raw quote DataFrame with columns: instrument_name, bid, ask, expiry.
    min_days : float
        Minimum calendar days to expiry.
    reference_time : datetime, optional
        Reference timestamp for expiry calculation.

    Returns
    -------
    tuple[DataFrame, QuoteCleaningReport]
        Cleaned DataFrame and a diagnostic report.
    """
    raw_count = len(df)
    all_removals: list[QuoteRemovalRecord] = []
    removed_counts: dict[str, int] = {}

    current = df
    for filter_fn in (filter_zero_bid_ask, filter_crossed, filter_min_days_to_expiry):
        if filter_fn is filter_min_days_to_expiry:
            result = filter_fn(current, min_days=min_days, reference_time=reference_time)  # type: ignore[call-arg]
        else:
            result = filter_fn(current)
        current = result.df
        for r in result.removals:
            all_removals.append(r)
            removed_counts[r.reason] = removed_counts.get(r.reason, 0) + 1

    retained = len(current)
    report = QuoteCleaningReport(
        raw_count=raw_count,
        retained_count=retained,
        removed_counts=removed_counts,
        removal_records=tuple(all_removals),
    )
    logger.info(
        "clean_quotes: %d -> %d rows (dropped %d)", raw_count, retained, raw_count - retained
    )
    return current, report
