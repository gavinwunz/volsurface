"""Deribit public API client for fetching option chains.

Uses the public JSON-RPC 2.0 REST endpoint — no authentication required.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DERIBIT_REST_URL = "https://www.deribit.com/api/v2/"
REQUEST_TIMEOUT = 30  # seconds
MAX_BATCH_SIZE = 100  # max concurrent ticker calls


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class OptionQuote:
    """A single cleaned option quote."""

    instrument_name: str
    underlying: str  # "BTC" | "ETH"
    option_type: str  # "C" | "P"
    strike: float
    expiry: datetime
    settlement_period: str  # "day" | "week" | "month" | "quarter" | "perpetual"
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
    """A full option-chain snapshot."""

    currency: str
    timestamp: datetime
    quotes: list[OptionQuote] = field(default_factory=list)
    forwards: dict[str, float] = field(default_factory=dict)

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


def _rpc(method: str, params: dict, session: Optional[requests.Session] = None) -> dict:
    """Send a single JSON-RPC 2.0 request to Deribit.  Returns the ``result`` field."""
    s = session or requests.Session()
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    resp = s.post(DERIBIT_REST_URL, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Deribit RPC error: {data['error']}")
    if "result" not in data:
        raise RuntimeError(f"Deribit RPC: missing result in {data}")
    return data["result"]


def _batch_rpc(
    calls: list[tuple[str, dict]], session: Optional[requests.Session] = None
) -> list[dict]:
    """Send multiple JSON-RPC calls in one HTTP request.  Returns results in order.

    Deribit's public HTTP endpoint has, at times, rejected JSON-RPC 2.0 batch
    arrays with ``bad_request``/``invalid json``.  If the single batched POST
    fails for any reason, we transparently fall back to issuing the calls
    sequentially so ``fetch_snapshot`` keeps working against the live API.
    """
    s = session or requests.Session()
    payload = [
        {"jsonrpc": "2.0", "method": m, "params": p, "id": i}
        for i, (m, p) in enumerate(calls)
    ]
    try:
        resp = s.post(DERIBIT_REST_URL, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        results = resp.json()
        if isinstance(results, dict):
            # API returned a single response: treat as first item
            results = [results]
        results.sort(key=lambda r: r.get("id", 0))
        out = []
        for r in results:
            if "error" in r:
                raise RuntimeError(f"Deribit batch error: {r['error']}")
            out.append(r.get("result"))
        return out
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        logger.warning(
            "Batch RPC failed (%s); falling back to sequential requests for %d calls",
            exc,
            len(calls),
        )
        return [_rpc(m, p, s) for m, p in calls]


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------


class DeribitPublicClient:
    """Stateless client for Derbyit's public REST JSON-RPC API."""

    def __init__(self) -> None:
        self._session = requests.Session()

    # -- instruments ---------------------------------------------------------

    def fetch_option_instruments(
        self, currency: str, kind: str = "option", expired: bool = False
    ) -> list[dict]:
        """Return all active option instruments for *currency* (e.g. ``"BTC"``, ``"ETH"``)."""
        result = _rpc(
            "public/get_instruments",
            {"currency": currency.upper(), "kind": kind, "expired": expired},
            self._session,
        )
        return result

    # -- tickers -------------------------------------------------------------

    def fetch_ticker(self, instrument_name: str) -> dict:
        """Fetch ticker for a single instrument."""
        return _rpc("public/ticker", {"instrument_name": instrument_name}, self._session)

    def fetch_tickers(self, instrument_names: list[str]) -> list[dict]:
        """Fetch tickers for multiple instruments in parallel batches."""
        results = []
        for i in range(0, len(instrument_names), MAX_BATCH_SIZE):
            batch = instrument_names[i : i + MAX_BATCH_SIZE]
            calls = [("public/ticker", {"instrument_name": n}) for n in batch]
            results.extend(_batch_rpc(calls, self._session))
            if i + MAX_BATCH_SIZE < len(instrument_names):
                time.sleep(0.05)  # gentle rate-limit
        return results

    # -- snapshot ------------------------------------------------------------

    def fetch_snapshot(self, currency: str) -> Snapshot:
        """Fetch a full option-chain snapshot for *currency*.

        1. Get all active option instruments.
        2. Fetch current ticker data for each instrument.
        3. Return a structured ``Snapshot``.
        """
        currency = currency.upper()
        now = datetime.now(timezone.utc)
        logger.info("Fetching instruments for %s...", currency)
        instruments = self.fetch_option_instruments(currency)

        if not instruments:
            logger.warning("No instruments returned for %s", currency)
            return Snapshot(currency=currency, timestamp=now)

        names = [inst["instrument_name"] for inst in instruments]
        logger.info("Fetching tickers for %d instruments...", len(names))
        tickers = self.fetch_tickers(names)

        # Build a lookup from ticker results
        ticker_map = {}
        for t in tickers:
            if t:
                ticker_map[t.get("instrument_name", "")] = t

        quotes: list[OptionQuote] = []
        for inst in instruments:
            name = inst["instrument_name"]
            tk = ticker_map.get(name, {})
            if not tk:
                continue

            bid = float(tk.get("best_bid_price", 0) or 0)
            ask = float(tk.get("best_ask_price", 0) or 0)
            bid_size = float(tk.get("best_bid_amount", 0) or 0)
            ask_size = float(tk.get("best_ask_amount", 0) or 0)
            mid = float(tk.get("mark_price", 0) or 0)
            mark_iv = float(tk.get("mark_iv", 0) or 0)
            underlying_price = float(tk.get("underlying_price", 0) or 0)
            oi = float(tk.get("open_interest", 0) or 0)
            raw_type = inst.get("option_type", "").upper()
            # Normalise "CALL" -> "C", "PUT" -> "P"
            opt_type = "C" if raw_type == "CALL" else ("P" if raw_type == "PUT" else raw_type)
            strike = float(inst["strike"])
            expiry_ms = int(inst["expiration_timestamp"])
            expiry = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)
            settlement = inst.get("settlement_period", "")

            quotes.append(
                OptionQuote(
                    instrument_name=name,
                    underlying=currency,
                    option_type=opt_type,
                    strike=strike,
                    expiry=expiry,
                    settlement_period=settlement,
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    bid_size=bid_size,
                    ask_size=ask_size,
                    mark_iv=mark_iv,
                    underlying_price=underlying_price,
                    open_interest=oi,
                    snapshot_ts=now,
                )
            )

        logger.info("Fetched %d quotes for %s", len(quotes), currency)
        return Snapshot(currency=currency, timestamp=now, quotes=quotes)


def fetch_snapshot(currency: str) -> Snapshot:
    """Convenience wrapper — single-snapshot fetch."""
    return DeribitPublicClient().fetch_snapshot(currency)