#!/usr/bin/env python3
"""Live Deribit volatility-surface demo.

Pulls a LIVE public-API snapshot from Deribit (no auth), runs the full
volfoundry pipeline end to end, and writes diagnostic PNGs to ``reports/``:

    1. 3D SSVI implied-vol surface            (reports/live_surface_3d.png)
    2. Skew / term-structure                  (reports/live_skew_term_structure.png)
    3. Butterfly g(k) diagnostics per slice   (reports/live_butterfly_gk.png)
    4. Per-expiry SVI smiles: market IV vs fit (reports/live_svi_smiles.png)

Pipeline:
    fetch -> persist -> clean -> per-expiry forwards (put-call parity)
    -> invert implied vol per (OTM) quote -> raw SVI per expiry
    -> global SSVI surface -> no-arbitrage checks (butterfly + calendar).

Deribit lists option premiums in *coin* units (BTC/ETH); strikes are in USD.
Put-call parity is a USD relationship, so premiums are converted to USD via
the per-instrument ``underlying_price`` before the forward regression / IV
inversion.

Run:
    .venv/bin/python examples/live_surface_demo.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from volfoundry.arbitrage.checks import (
    calendar_monotonicity,
    check_slice_arbitrage,
    find_calendar_violations,
)
from volfoundry.data.fetcher import DERIBIT_REST_URL, DeribitPublicClient
from volfoundry.data.filters import clean_quotes
from volfoundry.data.forwards import extract_forwards
from volfoundry.data.persistence import write_snapshot
from volfoundry.iv.black_scholes import OptionType, implied_volatility
from volfoundry.surface.calibration import calibrate_ssvi_surface
from volfoundry.surface.plotting import (
    plot_3d_surface,
    plot_gk_diagnostics,
    plot_skew_term_structure,
)
from volfoundry.svi.calibration import build_vega_weights, calibrate_svi_slice
from volfoundry.svi.parameterization import svi_implied_vol

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"

# How many expiries (by usable-quote count) to feed the surface.
MAX_EXPIRIES = 6
# Minimum usable OTM smile points required to calibrate a slice.
MIN_SLICE_POINTS = 6
# A currency is "usable" if at least this many expiries clear MIN_SLICE_POINTS.
MIN_USABLE_EXPIRIES = 2


def fetch_index_price(currency: str) -> float:
    """Fetch the spot index price (USD) for a currency from Deribit."""
    index_name = f"{currency.lower()}_usd"
    try:
        resp = requests.post(
            DERIBIT_REST_URL,
            json={
                "jsonrpc": "2.0",
                "method": "public/get_index_price",
                "params": {"index_name": index_name},
                "id": 1,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return float(resp.json()["result"]["index_price"])
    except Exception:  # pragma: no cover - best-effort diagnostic value
        return float("nan")


def build_usd_frame(snapshot) -> pd.DataFrame:
    """DataFrame of the snapshot with premiums converted from coin to USD."""
    df = snapshot.to_dataframe()
    if df.empty:
        return df
    # Deribit premiums (bid/ask/mid) are in coin; strikes in USD. Convert.
    for col in ("bid", "ask", "mid"):
        df[col] = df[col] * df["underlying_price"]
    return df


def build_smile(expiry_df: pd.DataFrame, F: float):
    """Build an OTM implied-vol smile for one expiry.

    Uses the out-of-the-money wing at each strike (puts below F, calls above F)
    because OTM options have the cleanest vega and no intrinsic-value noise.

    Returns (K, k, iv, opt_type_str) arrays sorted by strike, IV-valid only.
    """
    rows = []
    for _, q in expiry_df.iterrows():
        K = float(q["strike"])
        is_call = q["option_type"] == "C"
        # Keep only the OTM side at each strike.
        if is_call and K < F:
            continue
        if (not is_call) and K >= F:
            continue
        rows.append((K, q["mid"], is_call))
    return rows


def calibrate_currency(currency: str):
    """Run the full pipeline for a currency. Returns a result dict or None."""
    client = DeribitPublicClient()
    print(f"Fetching live Deribit snapshot for {currency} ...", flush=True)
    snapshot = client.fetch_snapshot(currency)
    n_raw = len(snapshot.quotes)
    print(f"  raw quotes: {n_raw}", flush=True)
    if n_raw == 0:
        return None

    # Persist the raw snapshot (coin-denominated premiums).
    snap_path = write_snapshot(snapshot)

    ref_time = snapshot.timestamp
    df_usd = build_usd_frame(snapshot)

    # Clean: zero-bid/ask, crossed, min-days-to-expiry.
    df_clean = clean_quotes(df_usd, reference_time=ref_time)
    if df_clean.empty:
        return None

    # Per-expiry forwards via put-call parity.
    forwards = extract_forwards(df_clean, reference_time=ref_time)
    if not forwards:
        return None

    # Build a smile per expiry; keep those with enough usable IV points.
    slices = []  # list of dicts
    for expiry, fwd in forwards.items():
        exp_df = df_clean[df_clean["expiry"] == expiry]
        F, T, r = fwd.F, fwd.T, fwd.r
        if F <= 0 or T <= 0:
            continue

        Ks, ks, ivs, otypes = [], [], [], []
        for K, price_usd, is_call in build_smile(exp_df, F):
            ot = OptionType.CALL if is_call else OptionType.PUT
            try:
                iv = implied_volatility(float(price_usd), F, float(K), T, r, ot)
            except Exception:
                continue
            # Discard degenerate inversions.
            if not np.isfinite(iv) or iv <= 1e-4 or iv > 5.0:
                continue
            Ks.append(float(K))
            ks.append(float(np.log(K / F)))
            ivs.append(float(iv))
            otypes.append("C" if is_call else "P")

        if len(ks) < MIN_SLICE_POINTS:
            continue

        order = np.argsort(ks)
        Ks = np.asarray(Ks)[order]
        ks = np.asarray(ks)[order]
        ivs = np.asarray(ivs)[order]
        otypes = np.asarray(otypes)[order]
        w_obs = ivs**2 * T

        slices.append(
            dict(
                expiry=expiry,
                T=T,
                F=F,
                r=r,
                days=T * 365.25,
                K=Ks,
                k=ks,
                iv=ivs,
                otype=otypes,
                w=w_obs,
                n=len(ks),
            )
        )

    if len(slices) < MIN_USABLE_EXPIRIES:
        return None

    # Keep the expiries with the most usable quotes, then order by T.
    slices.sort(key=lambda s: s["n"], reverse=True)
    slices = slices[:MAX_EXPIRIES]
    slices.sort(key=lambda s: s["T"])

    # ---- Raw SVI per expiry ------------------------------------------------
    good_slices = []
    for s in slices:
        weights = build_vega_weights(
            s["k"],
            s["T"],
            s["F"],
            s["r"],
            sigma_guess=float(np.median(s["iv"])),
            option_type_strs=s["otype"],
        )
        try:
            res = calibrate_svi_slice(s["k"], s["w"], s["T"], weights=weights)
        except Exception as exc:  # pragma: no cover - defensive on live data
            print(
                f"  skipping {pd.Timestamp(s['expiry']).date()} slice "
                f"(SVI calibration failed: {exc})",
                flush=True,
            )
            continue
        s["svi"] = res
        s["weights"] = weights
        # RMSE in vol points (implied-vol space), the intuitive units.
        iv_fit = svi_implied_vol(s["k"], res.params, s["T"])
        s["rmse_vol"] = float(np.sqrt(np.mean((s["iv"] - iv_fit) ** 2)))
        good_slices.append(s)

    slices = good_slices
    if len(slices) < MIN_USABLE_EXPIRIES:
        return None

    # ---- Global SSVI surface ----------------------------------------------
    slices_data = [(s["k"], s["w"], s["T"]) for s in slices]
    weights_all = [s["weights"] for s in slices]
    T_values = np.array([s["T"] for s in slices])
    ssvi = calibrate_ssvi_surface(
        slices_data,
        expiration_times=[s["T"] for s in slices],
        weights_all=weights_all,
        rho=None,  # joint (rho, eta, lambda) calibration
    )

    # ---- No-arbitrage checks (on raw SVI slices) --------------------------
    k_grid = np.linspace(-1.5, 1.5, 400)
    arb_results = []
    for s in slices:
        r_check = check_slice_arbitrage(
            slice_id=f"{currency}-{pd.Timestamp(s['expiry']).strftime('%d%b%y').upper()}",
            params=s["svi"].params,
            T=s["T"],
            k=k_grid,
            F=s["F"],
            r=s["r"],
        )
        s["arb"] = r_check
        arb_results.append(r_check)

    raw_pairs = [(s["svi"].params, s["T"]) for s in slices]
    calendar_ok = calendar_monotonicity(k_grid, raw_pairs)
    calendar_viol = find_calendar_violations(k_grid, raw_pairs)

    return dict(
        currency=currency,
        snapshot=snapshot,
        snapshot_path=snap_path,
        index_price=fetch_index_price(currency),
        n_raw=n_raw,
        n_clean=len(df_clean),
        slices=slices,
        ssvi=ssvi,
        T_values=T_values,
        arb_results=arb_results,
        calendar_ok=calendar_ok,
        calendar_viol=calendar_viol,
    )


def plot_svi_smiles(result, output_path: Path) -> Path:
    """Per-expiry SVI smiles: market IV scatter vs fitted raw-SVI curve."""
    slices = result["slices"]
    n = len(slices)
    ncols = min(3, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows), squeeze=False)
    axes = axes.flatten()

    for i, s in enumerate(slices):
        ax = axes[i]
        k = s["k"]
        kk = np.linspace(k.min(), k.max(), 200)
        iv_fit = svi_implied_vol(kk, s["svi"].params, s["T"])
        is_call = s["otype"] == "C"
        ax.scatter(
            k[~is_call],
            s["iv"][~is_call] * 100,
            s=22,
            color="crimson",
            label="market IV (put)",
            zorder=3,
        )
        ax.scatter(
            k[is_call],
            s["iv"][is_call] * 100,
            s=22,
            color="royalblue",
            label="market IV (call)",
            zorder=3,
        )
        ax.plot(kk, iv_fit * 100, color="black", linewidth=1.4, label="fitted SVI")
        ax.axvline(0.0, color="gray", linestyle="--", linewidth=0.7)
        ax.set_xlabel("k = log(K/F)")
        ax.set_ylabel("implied vol (%)")
        ax.set_title(
            f"{s['days']:.0f}d  F={s['F']:,.0f}  n={s['n']}  RMSE={s['rmse_vol'] * 100:.2f}vp"
        )
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc="best")

    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle(
        f"{result['currency']} raw-SVI smiles — market IV vs fit "
        f"({result['snapshot'].timestamp:%Y-%m-%d %H:%M UTC})",
        fontsize=13,
        y=1.01,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path


def print_summary(result) -> None:
    cur = result["currency"]
    snap = result["snapshot"]
    ssvi = result["ssvi"]
    slices = result["slices"]

    total_quotes = sum(s["n"] for s in slices)
    line = "=" * 78
    print("\n" + line)
    print(f"LIVE DERIBIT VOLATILITY SURFACE — {cur}")
    print(line)
    print(f"Snapshot UTC time : {snap.timestamp.isoformat()}")
    print(f"Currency          : {cur}")
    print(f"Spot index (USD)  : {result['index_price']:,.2f}")
    print(f"Raw quotes fetched: {result['n_raw']}")
    print(f"Quotes post-clean : {result['n_clean']}")
    print(f"Expiries used     : {len(slices)}")
    print(f"Smile pts used    : {total_quotes}")
    print(f"Snapshot saved to : {result['snapshot_path']}")
    print("-" * 78)
    print(
        f"{'expiry':<12}{'days':>7}{'#pts':>6}{'forward F':>14}"
        f"{'SVI RMSE(vp)':>14}{'butterfly':>11}"
    )
    print("-" * 78)
    for s in slices:
        exp = pd.Timestamp(s["expiry"]).strftime("%d%b%y").upper()
        bf = "PASS" if s["arb"].butterfly_passed else "FAIL"
        print(
            f"{exp:<12}{s['days']:>7.1f}{s['n']:>6}{s['F']:>14,.1f}"
            f"{s['rmse_vol'] * 100:>14.3f}{bf:>11}"
        )
    print("-" * 78)
    print("GLOBAL SSVI FIT")
    print(f"  success   : {ssvi.success}  ({ssvi.message})")
    print(f"  rho       : {ssvi.rho:+.4f}")
    print(f"  eta       : {ssvi.eta:.4f}")
    print(f"  lambda    : {ssvi.lamb:.4f}")
    print(f"  R^2       : {ssvi.r2:.5f}")
    print(f"  RMSE (w)  : {ssvi.rmse:.6f}  (total-variance units)")
    print(f"  Lee bound : {'OK' if ssvi.params.satisfies_lee_bound() else 'VIOLATED'}")
    print("-" * 78)
    print("NO-ARBITRAGE CHECKS")
    n_bf_pass = sum(r.butterfly_passed for r in result["arb_results"])
    n_bf = len(result["arb_results"])
    print(f"  Butterfly (raw SVI g(k)>=0): {n_bf_pass}/{n_bf} slices pass")
    for r in result["arb_results"]:
        if not r.butterfly_passed:
            print(f"    VIOLATION {r.slice_id} (T={r.T:.4f}): min g(k) = {r.butterfly_min_g:.3e}")
    bl_states = [r.bl_passed for r in result["arb_results"] if r.bl_passed is not None]
    if bl_states:
        print(f"  Breeden-Litzenberger density >=0: {sum(bl_states)}/{len(bl_states)} slices pass")
    print(f"  Calendar monotonicity (raw SVI): {'PASS' if result['calendar_ok'] else 'FAIL'}")
    if result["calendar_viol"]:
        for T_i, T_j, k_v in result["calendar_viol"]:
            print(f"    VIOLATION T={T_i:.4f} -> T={T_j:.4f}: {len(k_v)} k-points")
    print(f"  SSVI calendar violations (fitted surface): {ssvi.calendar_violations}")
    print(line)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    result = None
    for currency in ("BTC", "ETH"):
        try:
            result = calibrate_currency(currency)
        except Exception as exc:  # pragma: no cover
            print(f"  {currency} pipeline failed: {exc}", flush=True)
            result = None
        if result is not None:
            break
        print(f"  {currency}: too few usable quotes; trying fallback ...", flush=True)

    if result is None:
        print("ERROR: could not build a surface from live data.", file=sys.stderr)
        return 1

    ssvi = result["ssvi"]
    T_values = result["T_values"]

    # (a) 3D implied-vol surface
    p3d = REPORTS_DIR / "live_surface_3d.png"
    plot_3d_surface(ssvi.params, T_values, k_min=-1.2, k_max=1.2, output_path=p3d)
    plt.close("all")

    # (b) skew / term-structure
    pskew = REPORTS_DIR / "live_skew_term_structure.png"
    plot_skew_term_structure(ssvi.params, T_values, output_path=pskew)
    plt.close("all")

    # (c) butterfly g(k) diagnostics per slice
    pgk = REPORTS_DIR / "live_butterfly_gk.png"
    plot_gk_diagnostics(result["arb_results"], k_min=-1.5, k_max=1.5, output_path=pgk)
    plt.close("all")

    # (d) per-expiry SVI smiles: market IV vs fitted curve
    psmile = REPORTS_DIR / "live_svi_smiles.png"
    plot_svi_smiles(result, psmile)

    print_summary(result)

    print("\nPNGs written:")
    for p in (p3d, pskew, pgk, psmile):
        print(f"  {p.resolve()}  ({p.stat().st_size} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
