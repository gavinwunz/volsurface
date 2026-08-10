"""Tests for volfoundry.data.filters — quote cleaning."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from volfoundry.data.filters import (
    clean_quotes,
    filter_crossed,
    filter_min_days_to_expiry,
    filter_zero_bid_ask,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal DataFrame from a list of dicts."""
    return pd.DataFrame(rows)


@pytest.fixture
def reference_time():
    return datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)


class TestFilterZeroBidAsk:
    def test_passes_valid_quotes(self):
        df = _make_df([
            {"bid": 0.15, "ask": 0.17},
            {"bid": 1.0, "ask": 1.2},
        ])
        result = filter_zero_bid_ask(df)
        assert len(result) == 2

    def test_drops_zero_bid(self):
        df = _make_df([{"bid": 0.0, "ask": 0.17}, {"bid": 0.15, "ask": 0.17}])
        result = filter_zero_bid_ask(df)
        assert len(result) == 1

    def test_drops_zero_ask(self):
        df = _make_df([{"bid": 0.15, "ask": 0.0}, {"bid": 0.15, "ask": 0.17}])
        result = filter_zero_bid_ask(df)
        assert len(result) == 1

    def test_drops_negative_bid(self):
        df = _make_df([{"bid": -0.01, "ask": 0.17}])
        result = filter_zero_bid_ask(df)
        assert len(result) == 0


class TestFilterCrossed:
    def test_passes_non_crossed(self):
        df = _make_df([
            {"bid": 0.15, "ask": 0.17},
            {"bid": 0.17, "ask": 0.17},  # exact == ok
        ])
        result = filter_crossed(df)
        assert len(result) == 2

    def test_drops_crossed(self):
        df = _make_df([{"bid": 0.18, "ask": 0.17}])
        result = filter_crossed(df)
        assert len(result) == 0


class TestFilterMinDaysToExpiry:
    def test_passes_far_expiry(self, reference_time):
        far = reference_time + timedelta(days=30)
        df = _make_df([
            {"bid": 0.15, "ask": 0.17, "expiry": far},
        ])
        result = filter_min_days_to_expiry(df, min_days=2, reference_time=reference_time)
        assert len(result) == 1

    def test_drops_near_expiry(self, reference_time):
        near = reference_time + timedelta(hours=24)  # 1 day
        df = _make_df([
            {"bid": 0.15, "ask": 0.17, "expiry": near},
        ])
        result = filter_min_days_to_expiry(df, min_days=2, reference_time=reference_time)
        assert len(result) == 0

    def test_exactly_min_days_kept(self, reference_time):
        exactly = reference_time + timedelta(days=2)
        df = _make_df([
            {"bid": 0.15, "ask": 0.17, "expiry": exactly},
        ])
        result = filter_min_days_to_expiry(df, min_days=2, reference_time=reference_time)
        assert len(result) == 1


class TestCleanQuotes:
    def test_pipeline_removes_all_bad(self, reference_time):
        far = reference_time + timedelta(days=10)
        near = reference_time + timedelta(hours=12)

        df = _make_df([
            {"bid": 0.15, "ask": 0.17, "expiry": far},     # good
            {"bid": 0.0, "ask": 0.17, "expiry": far},      # zero bid
            {"bid": 0.15, "ask": 0.17, "expiry": near},    # too close
            {"bid": 0.19, "ask": 0.17, "expiry": far},     # crossed
        ])
        result = clean_quotes(df, reference_time=reference_time)
        assert len(result) == 1

    def test_empty_df(self):
        df = _make_df([])
        result = clean_quotes(df)
        assert len(result) == 0