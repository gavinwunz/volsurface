"""Tests for volsurface.data.forwards — put-call parity forward extraction."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from volsurface.data.forwards import ForwardResult, compute_time_to_expiry, extract_forwards


def _make_df(
    expiry: datetime,
    strikes: list[float],
    option_type: str,
    mids: list[float],
    snapshot_ts: datetime | None = None,
) -> pd.DataFrame:
    """Build a minimal DataFrame with option_type, strike, mid, expiry."""
    snap = snapshot_ts or datetime(2025, 3, 21, 0, 0, tzinfo=timezone.utc)
    return pd.DataFrame({
        "expiry": [expiry] * len(strikes),
        "option_type": [option_type] * len(strikes),
        "strike": strikes,
        "mid": mids,
        "snapshot_ts": [snap] * len(strikes),
    })


class TestExtractForwards:
    """Tests for extract_forwards with synthetic data satisfying put-call parity."""

    def test_perfect_parity_no_noise(self):
        """With exact put-call parity, F should be recovered exactly."""
        # Setup: F=52000, r=0.02, T=0.25 years
        F_true = 52000.0
        r = 0.02
        T = 0.25
        df_factor = np.exp(-r * T)

        expiry = datetime(2025, 6, 21, 8, 0, tzinfo=timezone.utc)
        ref = datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)

        strikes = np.linspace(40000, 65000, 20)
        calls_mid = []
        puts_mid = []

        for K in strikes:
            # Black-76 style: C - P = df*(F - K)
            # Pick C = df * max(F - K, 0) + small OTM spread; P = C - df*(F - K)
            cp_diff = df_factor * (F_true - K)
            C = max(df_factor * (F_true - K), 0.01) + 0.001
            P = C - cp_diff
            calls_mid.append(C)
            puts_mid.append(P)

        calls = _make_df(expiry, strikes.tolist(), "C", calls_mid, snapshot_ts=ref)
        puts = _make_df(expiry, strikes.tolist(), "P", puts_mid, snapshot_ts=ref)
        df = pd.concat([calls, puts], ignore_index=True)

        results = extract_forwards(df, reference_time=ref)

        assert len(results) == 1
        result = list(results.values())[0]
        assert abs(result.F - F_true) < 1.0  # within 1 dollar
        assert abs(result.r - r) < 0.01
        assert result.r2 > 0.999
        assert result.n_pairs == 20

    def test_noise_tolerance(self):
        """With small random noise, F is still close."""
        rng = np.random.default_rng(42)
        F_true = 50000.0
        r = 0.05
        T = 0.5
        df_factor = np.exp(-r * T)

        expiry = datetime(2025, 9, 21, 8, 0, tzinfo=timezone.utc)
        ref = datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)

        strikes = np.linspace(42000, 58000, 15)
        calls_mid = []
        puts_mid = []

        for K in strikes:
            cp_diff = df_factor * (F_true - K)
            # Mid with noise ~ 0.5% of price
            noise_c = rng.normal(0, 0.002)
            noise_p = rng.normal(0, 0.002)
            C = max(df_factor * max(F_true - K, 0) + 0.01, 0.01) + noise_c
            P = C - cp_diff + noise_p
            calls_mid.append(max(C, 0.001))
            puts_mid.append(max(P, 0.001))

        calls = _make_df(expiry, strikes.tolist(), "C", calls_mid, snapshot_ts=ref)
        puts = _make_df(expiry, strikes.tolist(), "P", puts_mid, snapshot_ts=ref)
        df = pd.concat([calls, puts], ignore_index=True)

        results = extract_forwards(df, reference_time=ref)
        assert len(results) == 1
        result = list(results.values())[0]
        assert abs(result.F - F_true) / F_true < 0.02  # within 2%
        assert result.r2 > 0.95

    def test_insufficient_pairs_skipped(self):
        """Fewer than min_pairs C-P pairs should be skipped."""
        expiry = datetime(2025, 4, 21, 8, 0, tzinfo=timezone.utc)
        ref = datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)

        calls = _make_df(expiry, [50000], "C", [0.16], snapshot_ts=ref)
        puts = _make_df(expiry, [50000], "P", [0.09], snapshot_ts=ref)
        df = pd.concat([calls, puts], ignore_index=True)

        results = extract_forwards(df, reference_time=ref, min_pairs=3)
        assert len(results) == 0

    def test_multiple_expiries(self):
        """Two expiries are extracted independently."""
        F1, F2 = 52000, 54000
        r = 0.03
        T1, T2 = 0.25, 0.50
        df1, df2 = np.exp(-r * T1), np.exp(-r * T2)

        ref = datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)
        exp1 = datetime(2025, 6, 21, 8, 0, tzinfo=timezone.utc)
        exp2 = datetime(2025, 9, 19, 8, 0, tzinfo=timezone.utc)

        frames = []
        for (exp, T, df, F) in [(exp1, T1, df1, F1), (exp2, T2, df2, F2)]:
            strikes = np.linspace(F * 0.8, F * 1.2, 10)
            cm, pm = [], []
            for K in strikes:
                diff = df * (F - K)
                C = max(df * max(F - K, 0) + 0.01, 0.001)
                P = C - diff
                cm.append(C)
                pm.append(P)
            frames.append(_make_df(exp, strikes.tolist(), "C", cm, snapshot_ts=ref))
            frames.append(_make_df(exp, strikes.tolist(), "P", pm, snapshot_ts=ref))

        df = pd.concat(frames, ignore_index=True)
        results = extract_forwards(df, reference_time=ref)

        assert len(results) == 2
        fwds = [r.F for r in results.values()]
        assert abs(fwds[0] - F1) < 2 or abs(fwds[1] - F1) < 2
        assert abs(fwds[0] - F2) < 2 or abs(fwds[1] - F2) < 2

    def test_degenerate_beta_skipped(self):
        """When beta is near-zero or positive, the expiry is skipped."""
        expiry = datetime(2025, 6, 21, 8, 0, tzinfo=timezone.utc)
        ref = datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)

        # Create random mids that don't follow parity => beta can be wrong
        strikes = [40000, 50000, 60000]
        calls_mid = [1.0, 1.0, 1.0]
        puts_mid = [1.0, 1.0, 1.0]

        calls = _make_df(expiry, strikes, "C", calls_mid, snapshot_ts=ref)
        puts = _make_df(expiry, strikes, "P", puts_mid, snapshot_ts=ref)
        df = pd.concat([calls, puts], ignore_index=True)

        results = extract_forwards(df, reference_time=ref, min_pairs=3)
        # beta ~ 0, should be skipped
        assert len(results) == 0


class TestForwardResult:
    def test_dataclass_fields(self):
        fr = ForwardResult(
            expiry=datetime(2025, 6, 21, 8, 0, tzinfo=timezone.utc),
            T=0.25,
            F=52000.0,
            discount_factor=0.995,
            r=0.02,
            r2=0.999,
            n_pairs=20,
            n_calls=25,
            n_puts=25,
        )
        assert fr.F == 52000.0
        assert fr.T == 0.25


class TestComputeTimeToExpiry:
    def test_basic(self):
        ref = datetime(2025, 3, 21, 12, 0, tzinfo=timezone.utc)
        exp = datetime(2025, 6, 21, 12, 0, tzinfo=timezone.utc)
        T = compute_time_to_expiry([exp], ref)
        # 92 days / 365.25 ≈ 0.252
        assert abs(T[0] - 92 / 365.25) < 0.01