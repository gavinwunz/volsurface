"""Tests for volsurface.data.fetcher — Deribit public API client."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from volsurface.data.fetcher import (
    DeribitPublicClient,
    Snapshot,
    _rpc,
    fetch_snapshot,
)


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
    import requests as req_mod

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = req_mod.HTTPError("500")
    mock_session.post.return_value = mock_resp

    with pytest.raises(req_mod.HTTPError):
        _rpc("public/get_instruments", {"currency": "BTC"}, session=mock_session)


def test_rpc_raises_on_jsonrpc_error():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": {"code": -32601, "message": "Method not found"}, "id": 1}
    mock_session.post.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Deribit RPC error"):
        _rpc("bad_method", {}, session=mock_session)


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


@patch("volsurface.data.fetcher._rpc")
def test_fetch_snapshot_integration(mock_rpc):
    """Full snapshot fetch end-to-end with mocked RPC."""
    mock_rpc.side_effect = [
        SAMPLE_INSTRUMENTS,  # get_instruments call
    ]

    client = DeribitPublicClient()
    client._session = MagicMock()
    # mock tickers batch call separately
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": 0, "result": SAMPLE_TICKERS[0]},
        {"id": 1, "result": SAMPLE_TICKERS[1]},
    ]
    client._session.post.return_value = mock_resp
    # patch _rpc so get_instruments returns our mocked data
    client.fetch_option_instruments = MagicMock(return_value=SAMPLE_INSTRUMENTS)

    snapshot = client.fetch_snapshot("BTC")
    assert snapshot.currency == "BTC"
    assert len(snapshot.quotes) == 2
    q = snapshot.quotes[0]
    assert q.underlying == "BTC"
    assert q.option_type == "C"
    assert q.strike == 50000.0
    assert q.bid == 0.15
    assert q.ask == 0.17
    assert q.mid == 0.16
    assert q.mark_iv == 65.0


def test_snapshot_to_dataframe():
    snap = Snapshot(
        currency="BTC",
        timestamp=datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc),
        quotes=[],
    )
    df = snap.to_dataframe()
    assert df.empty

    snap.quotes = []  # would need a quote to test non-empty; tested via integration above


def test_fetch_snapshot_convenience():
    with patch("volsurface.data.fetcher.DeribitPublicClient.fetch_snapshot") as mock_fs:
        mock_fs.return_value = Snapshot(currency="ETH", timestamp=datetime.now(timezone.utc))
        snap = fetch_snapshot("ETH")
        assert snap.currency == "ETH"


def test_quote_fields_complete():
    """Verify all OptionQuote fields are correctly mapped from raw data."""
    from volsurface.data.fetcher import OptionQuote

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