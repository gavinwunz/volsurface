"""Quote filters for cleaning raw option-chain data.

Filters applied in order:
1. Remove quotes with zero bid or zero ask.
2. Remove quotes with crossed markets (bid > ask).
3. Remove quotes with fewer than 2 calendar days to expiry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

MIN_DAYS_TO_EXPIRY = 2.0


def filter_zero_bid_ask(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows where bid <= 0 or ask <= 0.

    Returns a filtered copy; does not mutate the original.
    """
    if df.empty:
        return df.copy()
    before = len(df)
    result = df[(df["bid"] > 0) & (df["ask"] > 0)].copy()
    dropped = before - len(result)
    if dropped:
        logger.debug("Zero-bid/ask filter: dropped %d/%d rows", dropped, before)
    return result


def filter_crossed(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows where bid > ask (crossed market).

    Returns a filtered copy; does not mutate the original.
    """
    if df.empty:
        return df.copy()
    before = len(df)
    result = df[df["bid"] <= df["ask"]].copy()
    dropped = before - len(result)
    if dropped:
        logger.debug("Crossed-market filter: dropped %d/%d rows", dropped, before)
    return result


def filter_min_days_to_expiry(
    df: pd.DataFrame,
    min_days: float = MIN_DAYS_TO_EXPIRY,
    reference_time: Optional[datetime] = None,
) -> pd.DataFrame:
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
    DataFrame
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    if df.empty:
        return df.copy()
    before = len(df)
    # Ensure expiry column is datetime
    expiry = pd.to_datetime(df["expiry"], utc=True)
    tte = (expiry - reference_time).dt.total_seconds() / 86400.0
    result = df[tte >= min_days].copy()
    dropped = before - len(result)
    if dropped:
        logger.debug(
            "Min-days-to-expiry filter (< %.1f days): dropped %d/%d rows",
            min_days,
            dropped,
            before,
        )
    return result


def clean_quotes(
    df: pd.DataFrame,
    min_days: float = MIN_DAYS_TO_EXPIRY,
    reference_time: Optional[datetime] = None,
) -> pd.DataFrame:
    """Apply all data-layer filters: zero-bid/ask, crossed, min-days.

    Returns a cleaned copy.  Logs how many rows were dropped at each stage.
    """
    before = len(df)
    df = filter_zero_bid_ask(df)
    df = filter_crossed(df)
    df = filter_min_days_to_expiry(df, min_days=min_days, reference_time=reference_time)
    after = len(df)
    logger.info("clean_quotes: %d -> %d rows (dropped %d)", before, after, before - after)
    return df