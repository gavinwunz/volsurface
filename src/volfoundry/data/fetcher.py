"""Deribit public API client for fetching option chains.

Uses the public JSON-RPC 2.0 REST endpoint --- no authentication required.

Hardened for production:
- Explicit connect/read timeouts.
- Reusable session with descriptive User-Agent.
- Bounded retries with exponential backoff and jitter for transient failures.
- Validates JSON-RPC responses before conversion.
- Raises ``MarketDataError`` on failure; never returns empty-success.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from volfoundry._version import __version__
from volfoundry.exceptions import MarketDataError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DERIBIT_REST_URL = "https://www.deribit.com/api/v2/"
_CONNECT_TIMEOUT = 10  # seconds
_READ_TIMEOUT = 30  # seconds
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 1.0  # exponential backoff base in seconds
_BACKOFF_MAX = 10.0  # cap on backoff wait
_MAX_BATCH_SIZE = 100  # max concurrent ticker calls
_STATUS_FORCELIST = [429, 500, 502, 503, 504]

_USER_AGENT = f"VolFoundry/{__version__}"


def _build_session() -> requests.Session:
    """Create a ``requests.Session`` with retry logic and a User-Agent header.

    Only retries on transient status codes (429, 5xx).  Does NOT retry on
    4xx client errors other than 429.

    Returns
    -------
    requests.Session
        Reusable session with retry adapter and User-Agent header.
    """
    retry_strategy = Retry(
        total=_MAX_RETRIES,
        backoff_factor=_BACKOFF_FACTOR,
        backoff_max=_BACKOFF_MAX,
        status_forcelist=_STATUS_FORCELIST,
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": _USER_AGENT})
    return session


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class QuoteRemovalRecord:
    """Why a quote was removed during cleaning / validation."""

    instrument_name: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class QuoteCleaningReport:
    """Diagnostic summary of quote cleaning and validation."""

    raw_count: int
    retained_count: int
    removed_counts: dict[str, int]  # reason -> count
    removal_records: tuple[QuoteRemovalRecord, ...] = ()

    @property
    def total_removed(self) -> int:
        return self.raw_count - self.retained_count

    def summary(self) -> str:
        """Human-readable cleaning summary."""
        lines = [f"raw: {self.raw_count}"]
        for reason, count in sorted(self.removed_counts.items(), key=lambda x: -x[1]):
            lines.append(f"removed_{reason}: {count}")
        lines.append(f"retained: {self.retained_count}")
        return "\n".join(lines)


@dataclass
class OptionQuote:
    """A single cleaned option quote."""

    instrument_name: str
    underlying: str  # "BTC" | "ETH"
    option_type: str  # "C" | "P"
    strike: float
    expiry: datetime
    settlement_period: str
    bid: float
    ask: float
    mid: float
    bid_size: float
    ask_size: float
    mark_iv: float
    underlying_price: float
    open_interest: float
    snapshot_ts: datetime


@dataclass
class Snapshot:
    """A full option-chain snapshot with schema versioning."""

    currency: str
    timestamp: datetime
    quotes: list[OptionQuote] = field(default_factory=list)
    forwards: dict[str, float] = field(default_factory=dict)
    schema_version: int = 1
    cleaning_report: Optional[QuoteCleaningReport] = None

    def to_dataframe(self) -> pd.DataFrame:
        """Convert quotes to a DataFrame."""
        if not self.quotes:
            return pd.DataFrame()
        records = [
            {
                "instrument_name": q.instrument_name,
                "underlying": q.underlying,
                "option_type": q.option_type,
                "strike": q.strike,
                "expiry": q.expiry,
                "settlement_period": q.settlement_period,
                "bid": q.bid,
                "ask": q.ask,
                "mid": q.mid,
                "bid_size": q.bid_size,
                "ask_size": q.ask_size,
                "mark_iv": q.mark_iv,
                "underlying_price": q.underlying_price,
                "open_interest": q.open_interest,
                "snapshot_ts": q.snapshot_ts,
            }
            for q in self.quotes
        ]
        return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _rpc(
    method: str,
    params: dict,
    session: Optional[requests.Session] = None,
    timeout: tuple[float, float] = (_CONNECT_TIMEOUT, _READ_TIMEOUT),
) -> dict:
    """Send a single JSON-RPC 2.0 request to Deribit.

    Raises MarketDataError on any failure.
    """
    s = session or _build_session()
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        resp = s.post(DERIBIT_REST_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise MarketDataError(
            f"Deribit RPC call '{method}' failed: {exc}"
        ) from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise MarketDataError(
            f"Deribit RPC call '{method}' returned invalid JSON"
        ) from exc

    if "error" in data:
        err = data["error"]
        raise MarketDataError(
            f"Deribit RPC error on '{method}': code={err.get('code')} "
            f"message={err.get('message')}"
        )
    if "result" not in data:
        raise MarketDataError(
            f"Deribit RPC call '{method}': missing 'result' in response"
        )
    return data["result"]


def _batch_rpc(
    calls: list[tuple[str, dict]],
    session: Optional[requests.Session] = None,
    timeout: tuple[float, float] = (_CONNECT_TIMEOUT, _READ_TIMEOUT),
) -> list[dict]:
    """Send multiple JSON-RPC calls in one HTTP request.

    Falls back to sequential calls on batch failure.
    """
    s = session or _build_session()
    payload = [
        {"jsonrpc": "2.0", "method": m, "params": p, "id": i}
        for i, (m, p) in enumerate(calls)
    ]
    try:
        resp = s.post(DERIBIT_REST_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        results = resp.json()
        if isinstance(results, dict):
            results = [results]
        results.sort(key=lambda r: r.get("id", 0))
        out: list[dict] = []
        for r in results:
            if "error" in r:
                raise MarketDataError(
                    f"Deribit batch RPC error on id={r.get('id')}: "
                    f"code={r['error'].get('code')} message={r['error'].get('message')}"
                )
            if "result" not in r:
                raise MarketDataError(
                    f"Deribit batch RPC: missing 'result' for id={r.get('id')}"
                )
            out.append(r["result"])
        return out
    except (requests.RequestException, MarketDataError, ValueError) as exc:
        logger.warning(
            "Batch RPC failed (%s); falling back to sequential for %d calls",
            exc,
            len(calls),
        )
        return [_rpc(m, p, s, timeout) for m, p in calls]


# ---------------------------------------------------------------------------
# Quote validation
# ---------------------------------------------------------------------------


def _validate_raw_quote(
    inst: dict, tk: dict, currency: str
) -> list[QuoteRemovalRecord]:
    """Validate a single raw quote and return removal reasons (empty if valid)."""
    removals: list[QuoteRemovalRecord] = []
    name = inst.get("instrument_name", "")

    if not name:
        removals.append(QuoteRemovalRecord(
            instrument_name="<unknown>", reason="missing_instrument_name"
        ))
        return removals

    raw_type = inst.get("option_type", "").upper()
    if raw_type not in ("CALL", "PUT", "C", "P"):
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="invalid_option_type",
            detail=f"option_type={raw_type!r}"
        ))

    try:
        strike = float(inst["strike"])
    except (KeyError, ValueError, TypeError):
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="invalid_strike"
        ))
        return removals

    if strike <= 0 or not np.isfinite(strike):
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="invalid_strike",
            detail=f"strike={strike}"
        ))

    try:
        expiry_ms = int(inst["expiration_timestamp"])
        datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)
    except (KeyError, ValueError, TypeError, OverflowError):
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="invalid_expiry"
        ))
        return removals

    if not tk:
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="non_finite_price",
            detail="no ticker data"
        ))
        return removals

    try:
        bid = float(tk.get("best_bid_price", 0) or 0)
    except (ValueError, TypeError):
        bid = float("nan")
    try:
        ask = float(tk.get("best_ask_price", 0) or 0)
    except (ValueError, TypeError):
        ask = float("nan")
    try:
        mid = float(tk.get("mark_price", 0) or 0)
    except (ValueError, TypeError):
        mid = float("nan")
    try:
        underlying_price = float(tk.get("underlying_price", 0) or 0)
    except (ValueError, TypeError):
        underlying_price = float("nan")

    if not (np.isfinite(bid) and np.isfinite(ask) and np.isfinite(mid)):
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="non_finite_price",
            detail=f"bid={bid}, ask={ask}, mid={mid}"
        ))

    if not np.isfinite(underlying_price) or underlying_price <= 0:
        removals.append(QuoteRemovalRecord(
            instrument_name=name, reason="non_finite_underlying",
            detail=f"underlying_price={underlying_price}"
        ))

    return removals


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------


class DeribitPublicClient:
    """Client for Deribit's public REST JSON-RPC API.

    Uses a reusable session with retry logic, explicit timeouts, and a
    descriptive User-Agent header.  All public methods raise
    ``MarketDataError`` on failure.

    Parameters
    ----------
    connect_timeout : float
        HTTP connect timeout in seconds (default 10).
    read_timeout : float
        HTTP read timeout in seconds (default 30).
    """

    def __init__(
        self,
        connect_timeout: float = _CONNECT_TIMEOUT,
        read_timeout: float = _READ_TIMEOUT,
    ) -> None:
        self._timeout = (connect_timeout, read_timeout)
        self._session = _build_session()

    # -- instruments ---------------------------------------------------------

    def fetch_option_instruments(
        self, currency: str, kind: str = "option", expired: bool = False
    ) -> list[dict]:
        """Return all active option instruments for *currency*."""
        result = _rpc(
            "public/get_instruments",
            {"currency": currency.upper(), "kind": kind, "expired": expired},
            self._session,
            self._timeout,
        )
        if not isinstance(result, list):
            raise MarketDataError(
                f"Expected list of instruments, got {type(result).__name__}"
            )
        return result

    # -- tickers -------------------------------------------------------------

    def fetch_ticker(self, instrument_name: str) -> dict:
        """Fetch ticker for a single instrument."""
        return _rpc(
            "public/ticker",
            {"instrument_name": instrument_name},
            self._session,
            self._timeout,
        )

    def fetch_tickers(self, instrument_names: list[str]) -> list[dict]:
        """Fetch tickers for multiple instruments in parallel batches."""
        if not instrument_names:
            return []
        results: list[dict] = []
        for i in range(0, len(instrument_names), _MAX_BATCH_SIZE):
            batch = instrument_names[i : i + _MAX_BATCH_SIZE]
            calls = [("public/ticker", {"instrument_name": n}) for n in batch]
            results.extend(_batch_rpc(calls, self._session, self._timeout))
            if i + _MAX_BATCH_SIZE < len(instrument_names):
                time.sleep(0.05)
        return results

    # -- snapshot ------------------------------------------------------------

    def fetch_snapshot(self, currency: str) -> Snapshot:
        """Fetch a full option-chain snapshot for *currency*.

        Raises MarketDataError on failure; never returns empty-success.
        """
        currency = currency.upper()
        now = datetime.now(timezone.utc)
        logger.info("Fetching instruments for %s...", currency)
        instruments = self.fetch_option_instruments(currency)

        if not instruments:
            raise MarketDataError(
                f"No instruments returned for {currency}. "
                f"The Deribit API returned an empty instrument list."
            )

        names = [inst["instrument_name"] for inst in instruments]
        logger.info("Fetching tickers for %d instruments...", len(names))
        tickers = self.fetch_tickers(names)

        ticker_map: dict[str, dict] = {}
        for t in tickers:
            if t and isinstance(t, dict):
                ticker_map[t.get("instrument_name", "")] = t

        raw_count = len(instruments)
        validated_quotes: list[OptionQuote] = []
        removal_records: list[QuoteRemovalRecord] = []
        removed_counts: dict[str, int] = {}

        for inst in instruments:
            name = inst.get("instrument_name", "")
            tk = ticker_map.get(name, {})

            vr = _validate_raw_quote(inst, tk, currency)
            if vr:
                removal_records.extend(vr)
                for r in vr:
                    removed_counts[r.reason] = removed_counts.get(r.reason, 0) + 1
                continue

            # Build a valid quote
            bid = float(tk["best_bid_price"])
            ask = float(tk["best_ask_price"])
            mid = float(tk["mark_price"])
            raw_type = inst["option_type"].upper()
            opt_type = "C" if raw_type in ("CALL", "C") else "P"
            strike = float(inst["strike"])
            expiry_ms = int(inst["expiration_timestamp"])
            expiry = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)

            validated_quotes.append(
                OptionQuote(
                    instrument_name=name,
                    underlying=currency,
                    option_type=opt_type,
                    strike=strike,
                    expiry=expiry,
                    settlement_period=inst.get("settlement_period", ""),
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    bid_size=float(tk.get("best_bid_amount", 0) or 0),
                    ask_size=float(tk.get("best_ask_amount", 0) or 0),
                    mark_iv=float(tk.get("mark_iv", 0) or 0),
                    underlying_price=float(tk.get("underlying_price", 0) or 0),
                    open_interest=float(tk.get("open_interest", 0) or 0),
                    snapshot_ts=now,
                )
            )

        cleaning_report = QuoteCleaningReport(
            raw_count=raw_count,
            retained_count=len(validated_quotes),
            removed_counts=removed_counts,
            removal_records=tuple(removal_records),
        )

        logger.info(
            "Fetched %s: %d raw -> %d valid quotes",
            currency, raw_count, len(validated_quotes),
        )
        logger.debug("Cleaning report:\n%s", cleaning_report.summary())

        return Snapshot(
            currency=currency,
            timestamp=now,
            quotes=validated_quotes,
            cleaning_report=cleaning_report,
        )


def fetch_snapshot(currency: str) -> Snapshot:
    """Convenience wrapper --- single-snapshot fetch."""
    return DeribitPublicClient().fetch_snapshot(currency)
