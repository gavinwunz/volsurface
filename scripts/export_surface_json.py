#!/usr/bin/env python
"""Export a calibrated SSVI surface to surface.json for the VolFoundry landing page.

Produces exactly the schema consumed by volfoundry-site/app.js::renderCalibrated:

    {
      "as_of": ISO8601,
      "currency": "BTC",
      "volfoundry_version": "0.1.0",
      "validation": {
        "is_valid": bool,
        "butterfly": bool|null,
        "calendar": bool|null,
        "density_crosscheck": bool|null,
        "domain": "k in [kmin, kmax], nk x nT",
        "tolerance": float|null
      },
      "grid": { "k": [nk], "T": [nT years], "w": [[nT x nk] total variance] },
      "slices": [ {"T": years, "n": points}, ... ]
    }

z rendered by the page is sqrt(w / T) * 100  (annualised vol in %).

Usage:  python scripts/export_surface_json.py [--currency BTC] [--out PATH]
Runs a LIVE Deribit fetch; nothing is simulated.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import numpy as np

from volfoundry import DeribitClient, SurfaceBuilder, __version__
from volfoundry.exceptions import InvalidSurfaceError


def build_payload(currency: str, n_k: int = 61) -> dict:
    snapshot = DeribitClient().fetch(currency)

    builder = SurfaceBuilder()
    try:
        result = builder.fit(snapshot, validation="strict")
    except InvalidSurfaceError:
        # Honest fallback: keep the flagged fit so the page shows "flagged"
        # rather than silently hiding a real-but-arbitrage-violating surface.
        result = builder.fit(snapshot, validation="report")

    surface = result.surface
    if surface is None:
        raise SystemExit("calibration produced no surface")

    v = result.validation
    dom = v.evaluation_domain or {}
    k_min = float(dom.get("k_min", -1.5))
    k_max = float(dom.get("k_max", 1.5))

    T = [float(t) for t in np.asarray(surface.expiry_times(), dtype=float)]
    k = np.linspace(k_min, k_max, n_k)
    w = [[float(x) for x in np.atleast_1d(surface.total_variance(k, t))] for t in T]

    tols = v.tolerances or {}
    tolerance = None
    for key in ("butterfly_tol", "calendar_tol", "bl_tol"):
        if key in tols:
            tolerance = float(tols[key])
            break

    per_slice = v.per_slice or []
    slices = [
        {"T": T[i], "n": int((per_slice[i] or {}).get("n_quotes", 0)) if i < len(per_slice) else 0}
        for i in range(len(T))
    ]

    return {
        "as_of": snapshot.timestamp.astimezone(timezone.utc).isoformat()
        if getattr(snapshot, "timestamp", None)
        else datetime.now(timezone.utc).isoformat(),
        "currency": currency,
        "volfoundry_version": __version__,
        "calibration_status": result.calibration_status,
        "validation": {
            "is_valid": bool(v.is_valid),
            "butterfly": v.butterfly_passed,
            "calendar": v.calendar_passed,
            "density_crosscheck": v.density_passed,
            "domain": f"k in [{k_min:g}, {k_max:g}], {n_k}x{len(T)}",
            "tolerance": tolerance,
        },
        "grid": {"k": [float(x) for x in k], "T": T, "w": w},
        "slices": slices,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", default="BTC")
    ap.add_argument("--out", default="surface.json")
    ap.add_argument("--n-k", type=int, default=61)
    args = ap.parse_args(argv)

    payload = build_payload(args.currency, n_k=args.n_k)
    with open(args.out, "w") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    v = payload["validation"]
    print(
        f"wrote {args.out}: {args.currency} {payload['volfoundry_version']} "
        f"status={payload['calibration_status']} is_valid={v['is_valid']} "
        f"slices={len(payload['slices'])} k={len(payload['grid']['k'])}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
