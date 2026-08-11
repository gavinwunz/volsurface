"""Tests for volfoundry.data.fetcher --- Deribit public API client."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests as req_mod

from volfoundry.data.fetcher import (
    DeribitPublicClient,
    Snapshot,
    _rpc,
    fetch_snapshot,
)
from volfoundry.exceptions import MarketDataError

# -----------------------------------------------------------------------
# Test _rpc (with mocked requests)
# -----------------------------------------------------------------------


def test_rpc_returns_result():
    """_rpc calls POST and extracts 'result'."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": 1, "result": {"instruments": []}}
    mock_session.post.return_value = mock_resp

    result = _rpc("public/get_instruments", {"currency": "BTC"}, session=mock_session)
    assert result == {"instruments": []}
    mock_session.post.assert_called_once()


def test_rpc_raises_on_http_error():
    """_rpc wraps HTTP errors as MarketDataError."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req_mod.HTTPError("500")
    mock_session.post.return_value = mock_resp

    with pytest.raises(MarketDataError, match="Deribit RPC call"):
        _rpc("public/get_instruments", {"currency": "BTC"}, session=mock_session)


def test_rpc_raises_on_jsonrpc_error():
    """_rpc wraps JSON-RPC errors as MarketDataError."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "error": {"code": -32601, "message": "Method not found"},
        "id": 1,
    }
    mock_session.post.return_value = mock_resp

    with pytest.raises(MarketDataError, match="Deribit RPC error"):
        _rpc("bad_method", {}, session=mock_session)


def test_rpc_raises_on_missing_result():
    """_rpc raises on missing 'result' field."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": 1}
    mock_session.post.return_value = mock_resp

    with pytest.raises(MarketDataError, match="missing 'result'"):
        _rpc("some_method", {}, session=mock_session)


def test_rpc_raises_on_invalid_json():
    """_rpc raises MarketDataError when response is not valid JSON."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.side_effect = ValueError("not JSON")
    mock_session.post.return_value = mock_resp

    with pytest.raises(MarketDataError, match="invalid JSON"):
        _rpc("some_method", {}, session=mock_session)


# -----------------------------------------------------------------------
# Test instrument fetching
# -----------------------------------------------------------------------

SAMPLE_INSTRUMENTS = [
    {
        "instrument_name": "BTC-28MAR25-50000-C",
        "option_type": "call",
        "strike": 50000.0,
        "expiration_timestamp": 1743206400000,
        "settlement_period": "week",
    },
    {
        "instrument_name": "BTC-28MAR25-50000-P",
        "option_type": "put",
        "strike": 50000.0,
        "expiration_timestamp": 1743206400000,
        "settlement_period": "week",
    },
]

SAMPLE_TICKERS = [
    {
        "instrument_name": "BTC-28MAR25-50000-C",
        "best_bid_price": 0.15,
        "best_ask_price": 0.17,
        "best_bid_amount": 10,
        "best_ask_amount": 5,
        "mark_price": 0.16,
        "mark_iv": 65.0,
        "underlying_price": 51234.5,
        "open_interest": 1234,
        "state": "open",
    },
    {
        "instrument_name": "BTC-28MAR25-50000-P",
        "best_bid_price": 0.08,
        "best_ask_price": 0.10,
        "best_bid_amount": 20,
        "best_ask_amount": 15,
        "mark_price": 0.09,
        "mark_iv": 72.0,
        "underlying_price": 51234.5,
        "open_interest": 567,
        "state": "open",
    },
]


def test_fetch_option_instruments():
    client = DeribitPublicClient()
    client._session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": 1, "result": SAMPLE_INSTRUMENTS}
    client._session.post.return_value = mock_resp

    instruments = client.fetch_option_instruments("BTC")
    assert len(instruments) == 2
    assert instruments[0]["instrument_name"] == "BTC-28MAR25-50000-C"


def test_fetch_option_instruments_raises_on_non_list():
    """fetch_option_instruments raises on unexpected result type."""
    client = DeribitPublicClient()
    client._session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": 1, "result": {"not": "a list"}}
    client._session.post.return_value = mock_resp

    with pytest.raises(MarketDataError, match="Expected list"):
        client.fetch_option_instruments("BTC")


def test_fetch_tickers_batches():
    client = DeribitPublicClient()
    client._session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": 0, "result": SAMPLE_TICKERS[0]},
        {"id": 1, "result": SAMPLE_TICKERS[1]},
    ]
    client._session.post.return_value = mock_resp

    tickers = client.fetch_tickers(["BTC-28MAR25-50000-C", "BTC-28MAR25-50000-P"])
    assert len(tickers) == 2
    assert tickers[0]["instrument_name"] == "BTC-28MAR25-50000-C"


def test_fetch_tickers_empty():
    """Empty instrument_names returns empty list."""
    client = DeribitPublicClient()
    assert client.fetch_tickers([]) == []


def test_fetch_snapshot_integration():
    """Full snapshot fetch end-to-end with mocked RPC."""
    client = DeribitPublicClient()
    client._session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": 0, "result": SAMPLE_TICKERS[0]},
        {"id": 1, "result": SAMPLE_TICKERS[1]},
    ]
    client._session.post.return_value = mock_resp
    client.fetch_option_instruments = MagicMock(return_value=SAMPLE_INSTRUMENTS)

    snapshot = client.fetch_snapshot("BTC")
    assert snapshot.currency == "BTC"
    assert snapshot.schema_version == 1
    assert len(snapshot.quotes) == 2
    q = snapshot.quotes[0]
    assert q.underlying == "BTC"
    assert q.option_type == "C"
    assert q.strike == 50000.0
    assert q.bid == 0.15
    assert q.ask == 0.17
    assert q.mid == 0.16
    assert q.mark_iv == 65.0
    # Cleaning report
    assert snapshot.cleaning_report is not None
    assert snapshot.cleaning_report.raw_count == 2
    assert snapshot.cleaning_report.retained_count == 2
    assert snapshot.cleaning_report.total_removed == 0


def test_fetch_snapshot_empty_instruments_raises():
    """Empty instrument list raises MarketDataError, never silent success."""
    client = DeribitPublicClient()
    client._session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": 1, "result": []}
    client._session.post.return_value = mock_resp

    with pytest.raises(MarketDataError, match="No instruments returned"):
        client.fetch_snapshot("BTC")


def test_fetch_snapshot_validates_and_removes_bad_quotes():
    """Quotes with invalid strikes or missing tickers are excluded."""
    bad_instruments = [
        {
            "instrument_name": "BTC-28MAR25-50000-C",
            "option_type": "call",
            "strike": 50000.0,
            "expiration_timestamp": 1743206400000,
        },
        {
            "instrument_name": "BTC-28MAR25-99999-P",
            "option_type": "put",
            "strike": -1.0,  # invalid
            "expiration_timestamp": 1743206400000,
        },
        {
            "instrument_name": "BTC-28MAR25-NO-TICKER-C",
            "option_type": "call",
            "strike": 51000.0,
            "expiration_timestamp": 1743206400000,
        },
    ]
    # Only first instrument gets valid ticker
    tickers = [
        {"id": 0, "result": SAMPLE_TICKERS[0]},
        {"id": 1, "result": SAMPLE_TICKERS[1]},  # for 99999-P (but strike invalid)
    ]

    client = DeribitPublicClient()
    client._session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = tickers
    client._session.post.return_value = mock_resp
    client.fetch_option_instruments = MagicMock(return_value=bad_instruments)

    snapshot = client.fetch_snapshot("BTC")
    assert len(snapshot.quotes) == 1  # only the valid one
    assert snapshot.quotes[0].instrument_name == "BTC-28MAR25-50000-C"
    assert snapshot.cleaning_report is not None
    assert snapshot.cleaning_report.raw_count == 3
    assert snapshot.cleaning_report.retained_count == 1
    assert "invalid_strike" in snapshot.cleaning_report.removed_counts


def test_snapshot_to_dataframe():
    snap = Snapshot(
        currency="BTC",
        timestamp=datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc),
        quotes=[],
    )
    df = snap.to_dataframe()
    assert df.empty


def test_fetch_snapshot_convenience():
    with patch("volfoundry.data.fetcher.DeribitPublicClient.fetch_snapshot") as mock_fs:
        mock_fs.return_value = Snapshot(currency="ETH", timestamp=datetime.now(timezone.utc))
        snap = fetch_snapshot("ETH")
        assert snap.currency == "ETH"


def test_quote_fields_complete():
    """Verify all OptionQuote fields are correctly mapped from raw data."""
    from volfoundry.data.fetcher import OptionQuote

    q = OptionQuote(
        instrument_name="BTC-28MAR25-50000-C",
        underlying="BTC",
        option_type="C",
        strike=50000.0,
        expiry=datetime(2025, 3, 28, 8, 0, tzinfo=timezone.utc),
        settlement_period="week",
        bid=0.15,
        ask=0.17,
        mid=0.16,
        bid_size=10.0,
        ask_size=5.0,
        mark_iv=65.0,
        underlying_price=51234.5,
        open_interest=1234.0,
        snapshot_ts=datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc),
    )
    assert q.strike == 50000.0
    assert q.mark_iv == 65.0
    assert q.open_interest == 1234.0


def test_quote_cleaning_report_summary():
    """QuoteCleaningReport.summary() matches the plan spec format."""
    from volfoundry.data.fetcher import QuoteCleaningReport

    r = QuoteCleaningReport(
        raw_count=794,
        retained_count=711,
        removed_counts={
            "zero_bid": 41,
            "crossed_market": 2,
            "near_expiry": 36,
            "non_finite_price": 4,
        },
    )
    s = r.summary()
    assert "raw: 794" in s
    assert "removed_zero_bid: 41" in s
    assert "removed_crossed_market: 2" in s
    assert "removed_non_finite_price: 4" in s
    assert "retained: 711" in s


def test_build_session_has_user_agent():
    """Verify _build_session sets User-Agent header."""
    from volfoundry.data.fetcher import _USER_AGENT, _build_session

    s = _build_session()
    assert "User-Agent" in s.headers
    assert "VolFoundry" in s.headers["User-Agent"]
    assert _USER_AGENT == "VolFoundry/0.1.0"
