"""Tests for volfoundry.data.persistence — parquet I/O."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from volfoundry.data.fetcher import OptionQuote, Snapshot
from volfoundry.data.persistence import (
    list_snapshots,
    load_snapshot,
    read_snapshot,
    snapshot_filename,
    write_snapshot,
)


def _make_quote(**kwargs) -> OptionQuote:
    """Factory for a valid OptionQuote with sensible defaults."""
    defaults = {
        "instrument_name": "BTC-28MAR25-50000-C",
        "underlying": "BTC",
        "option_type": "C",
        "strike": 50000.0,
        "expiry": datetime(2025, 3, 28, 8, 0, tzinfo=timezone.utc),
        "settlement_period": "week",
        "bid": 0.15,
        "ask": 0.17,
        "mid": 0.16,
        "bid_size": 10.0,
        "ask_size": 5.0,
        "mark_iv": 65.0,
        "underlying_price": 51234.5,
        "open_interest": 1234.0,
        "snapshot_ts": datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return OptionQuote(**defaults)


def test_snapshot_filename_uniqueness():
    """Filename changes with microseconds."""
    ts1 = datetime(2025, 3, 21, 12, 0, 0, 123456, tzinfo=timezone.utc)
    ts2 = datetime(2025, 3, 21, 12, 0, 0, 789012, tzinfo=timezone.utc)
    assert snapshot_filename("BTC", ts1) != snapshot_filename("BTC", ts2)
    assert snapshot_filename("BTC", ts1).startswith("BTC-")
    assert snapshot_filename("BTC", ts1).endswith(".parquet")


def test_write_and_read_snapshot():
    """Round-trip: write a snapshot, read it back."""
    snap = Snapshot(
        currency="BTC",
        timestamp=datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc),
        quotes=[_make_quote(), _make_quote(instrument_name="BTC-28MAR25-51000-C", strike=51000.0)],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_snapshot(snap, data_dir=tmpdir)
        assert path.exists()

        df = read_snapshot(path)
        assert len(df) == 2
        assert df["strike"].tolist() == [50000.0, 51000.0]

        # Verify no overwrite
        with pytest.raises(FileExistsError):
            write_snapshot(snap, data_dir=tmpdir)


def test_list_snapshots():
    with tempfile.TemporaryDirectory() as tmpdir:
        snap1 = Snapshot(
            currency="BTC",
            timestamp=datetime(2025, 3, 21, 12, 0, 0, 1, tzinfo=timezone.utc),
            quotes=[_make_quote()],
        )
        snap2 = Snapshot(
            currency="ETH",
            timestamp=datetime(2025, 3, 21, 12, 0, 0, 2, tzinfo=timezone.utc),
            quotes=[_make_quote(underlying="ETH")],
        )
        write_snapshot(snap1, data_dir=tmpdir)
        write_snapshot(snap2, data_dir=tmpdir)

        all_files = list_snapshots(data_dir=tmpdir)
        assert len(all_files) == 2

        btc_files = list_snapshots(currency="BTC", data_dir=tmpdir)
        assert len(btc_files) == 1
        assert "BTC" in btc_files[0].name

        eth_files = list_snapshots(currency="ETH", data_dir=tmpdir)
        assert len(eth_files) == 1


def test_load_snapshot_latest():
    with tempfile.TemporaryDirectory() as tmpdir:
        snap1 = Snapshot(
            currency="BTC",
            timestamp=datetime(2025, 3, 21, 12, 0, 0, 1, tzinfo=timezone.utc),
            quotes=[_make_quote(mid=0.10)],
        )
        snap2 = Snapshot(
            currency="BTC",
            timestamp=datetime(2025, 3, 21, 12, 0, 0, 2, tzinfo=timezone.utc),
            quotes=[_make_quote(mid=0.20)],
        )
        write_snapshot(snap1, data_dir=tmpdir)
        write_snapshot(snap2, data_dir=tmpdir)

        df = load_snapshot(currency="BTC", latest=True, data_dir=tmpdir)
        assert len(df) == 1
        assert df["mid"].iloc[0] == 0.20

        df_all = load_snapshot(currency="BTC", latest=False, data_dir=tmpdir)
        assert len(df_all) == 2


def test_load_snapshot_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        df = load_snapshot(currency="BTC", data_dir=tmpdir)
        assert df is None