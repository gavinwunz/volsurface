"""Tests for volfoundry.data.filters --- quote cleaning with diagnostics."""

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
    # Ensure required columns exist
    df = pd.DataFrame(rows)
    if "instrument_name" not in df.columns:
        df["instrument_name"] = [f"INSTR_{i}" for i in range(len(df))]
    return df


@pytest.fixture
def reference_time():
    return datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)


class TestFilterZeroBidAsk:
    def test_passes_valid_quotes(self):
        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.17},
                {"bid": 1.0, "ask": 1.2},
            ]
        )
        result = filter_zero_bid_ask(df)
        assert len(result.df) == 2
        assert len(result.removals) == 0

    def test_drops_zero_bid(self):
        df = _make_df(
            [
                {"bid": 0.0, "ask": 0.17},
                {"bid": 0.15, "ask": 0.17},
            ]
        )
        result = filter_zero_bid_ask(df)
        assert len(result.df) == 1
        assert len(result.removals) == 1
        assert result.removals[0].reason == "zero_bid"

    def test_drops_zero_ask(self):
        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.0},
                {"bid": 0.15, "ask": 0.17},
            ]
        )
        result = filter_zero_bid_ask(df)
        assert len(result.df) == 1
        assert result.removals[0].reason == "zero_ask"

    def test_drops_negative_bid(self):
        df = _make_df(
            [
                {"bid": -0.01, "ask": 0.17},
                {"bid": 0.15, "ask": 0.17},
            ]
        )
        result = filter_zero_bid_ask(df)
        assert len(result.df) == 1
        assert result.removals[0].reason == "negative_bid"


class TestFilterCrossed:
    def test_passes_non_crossed(self):
        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.17},
                {"bid": 0.17, "ask": 0.17},
            ]
        )
        result = filter_crossed(df)
        assert len(result.df) == 2
        assert len(result.removals) == 0

    def test_drops_crossed(self):
        df = _make_df(
            [
                {"bid": 0.18, "ask": 0.17},
                {"bid": 0.15, "ask": 0.17},
            ]
        )
        result = filter_crossed(df)
        assert len(result.df) == 1
        assert result.removals[0].reason == "crossed_market"


class TestFilterMinDaysToExpiry:
    def test_passes_far_expiry(self, reference_time):
        far = reference_time + timedelta(days=30)
        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.17, "expiry": far},
            ]
        )
        result = filter_min_days_to_expiry(df, min_days=2, reference_time=reference_time)
        assert len(result.df) == 1
        assert len(result.removals) == 0

    def test_drops_near_expiry(self, reference_time):
        near = reference_time + timedelta(hours=24)  # 1 day
        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.17, "expiry": near},
            ]
        )
        result = filter_min_days_to_expiry(df, min_days=2, reference_time=reference_time)
        assert len(result.df) == 0
        assert result.removals[0].reason == "near_expiry"

    def test_exactly_min_days_kept(self, reference_time):
        exactly = reference_time + timedelta(days=2)
        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.17, "expiry": exactly},
            ]
        )
        result = filter_min_days_to_expiry(df, min_days=2, reference_time=reference_time)
        assert len(result.df) == 1
        assert len(result.removals) == 0


class TestCleanQuotes:
    def test_pipeline_removes_all_bad(self, reference_time):
        far = reference_time + timedelta(days=10)
        near = reference_time + timedelta(hours=12)

        df = _make_df(
            [
                {"bid": 0.15, "ask": 0.17, "expiry": far},  # good
                {"bid": 0.0, "ask": 0.17, "expiry": far},  # zero bid
                {"bid": 0.15, "ask": 0.17, "expiry": near},  # too close
                {"bid": 0.19, "ask": 0.17, "expiry": far},  # crossed
            ]
        )
        result_df, report = clean_quotes(df, reference_time=reference_time)
        assert len(result_df) == 1
        assert report.raw_count == 4
        assert report.retained_count == 1
        assert report.total_removed == 3
        # Verify per-reason counts
        assert "zero_bid" in report.removed_counts
        assert "crossed_market" in report.removed_counts
        assert "near_expiry" in report.removed_counts

    def test_empty_df(self):
        df = _make_df([])
        result_df, report = clean_quotes(df)
        assert len(result_df) == 0
        assert report.raw_count == 0
        assert report.retained_count == 0
