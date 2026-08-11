# VolFoundry

**Open-source volatility infrastructure for derivatives.**

VolFoundry turns live or historical option chains into calibrated volatility
surfaces with explicit numerical diagnostics and reproducible market snapshots.

```
Deribit option chain  →  quote cleaning  →  forward extraction (put-call parity)
  →  Black-76 implied vol  →  raw SVI per expiry  →  global SSVI surface
  →  static-arbitrage validation  →  pricing and research APIs
```

---

## See it in action

![3D SSVI implied volatility surface](docs/images/live_surface_3d.png)

*Snapshot: 2026-08-10 20:56 UTC · BTC spot $64,094 · 794 raw quotes → 663 cleaned · 6 expiries (17d–318d).*

---

## Quickstart

```bash
pip install volfoundry[plot]
```

```python
from volfoundry import DeribitClient, SurfaceBuilder

# Fetch live Deribit data and build a surface in ~10 lines
snapshot = DeribitClient().fetch("BTC")
result = SurfaceBuilder().fit(snapshot, validation="strict")

print(result.surface.iv(strike=70_000, maturity=30 / 365.25))
print(result.validation.is_valid)          # True → all checks passed
print(result.calibration_status)           # converged, converged_invalid, or did_not_converge
print(result.global_diagnostics["r2"])     # overall fit quality
```

**Offline data — no network needed:**

```python
from volfoundry import SurfaceBuilder
import pandas as pd

df = pd.read_parquet("btc-snapshot.parquet")
result = SurfaceBuilder().fit_dataframe(df, validation="report")

print(f"Valid: {result.validation.is_valid}")
print(f"Butterfly: {result.validation.butterfly_passed}")
print(f"Calendar:  {result.validation.calendar_passed}")
```

---

## Key features

- **End-to-end pipeline.** Feeds on live Deribit option chains or DataFrames.
  Quotes are validated and cleaned; stale, crossed, and tiny-premium quotes are
  filtered with machine-readable reasons.

- **Forward extraction.** Forwards are recovered per expiry by regressing
  C − P = e^{−rT}(F − K) — no assumption of constant rates or zero dividends.

- **Implied-vol inversion.** Newton–Raphson on vega with a Brent bracketing
  fallback.  Accurate to machine precision on typical inputs and resilient to the
  edges of the domain (deep ITM/OTM, near-zero maturity, tiny vega).

- **SVI / SSVI calibration.** Raw SVI smiles are fit with the Zeliade
  quasi-explicit method.  A global SSVI surface (Gatheral–Jacquier 2014) unifies
  the slices with a shared parameter structure, enforcing analytical
  no-arbitrage constraints *during* the fit — not merely printing a diagnostic
  afterwards.

- **Explicit static-arbitrage validation.** Two modes:
  - `validation="report"` — returns every fit for inspection.
  - `validation="strict"` — refuses to return a surface that fails
    butterfly / calendar / Breeden–Litzenberger checks.  Every report
    includes the evaluation domain and numerical tolerances used.

- **Three pricing engines.** Analytical Black-76 with full Greeks, CRR binomial
  tree (European + American), and Monte Carlo with antithetic variates and a
  Black-Scholes delta-hedged control variate.  Validated against QuantLib.

- **C++ acceleration (optional).** A pybind11 hot path for vectorised pricing is
  available when compiled; the library falls back to pure Python transparently.
  No C++ compiler is required to install or use VolFoundry.

- **Snapshot reproducibility.** Market snapshots are persisted with metadata
  (timestamp, currency, package version, schema version) so every surface can
  be rebuilt later.

- **Every formula is derived.** Mathematical derivations with explicit
  assumptions live in [`docs/derivations/`](docs/derivations/).

- **Pure Python core.** Importing `volfoundry` makes no network calls.
  Live market data is fetched only by explicit user action.

---

## Validation: why it matters

VolFoundry distinguishes **"the optimizer terminated"** from **"the surface
satisfies its advertised no-arbitrage contract."**

Two concrete examples of what the pipeline catches:

| Issue | Detection |
|-------|-----------|
| Butterfly arbitrage | `g(k) ≥ 0` check per slice; negative region = arbitrage |
| Calendar arbitrage | Total-variance monotonicity across expiries |
| SSVI Lee bound | `η·(1+\|ρ\|) ≤ 2` enforced as a hard penalty in the objective |
| Breeden–Litzenberger | Finite-difference density cross-check |

Per-slice SVI diagnostics distinguish four states — `valid`,
`converged_invalid`, `did_not_converge`, `not_fitted` — so an optimizer success
is never silently equated with a usable slice.

![Butterfly g(k) diagnostics](docs/images/live_butterfly_gk.png)

---

## Architecture

```
                         ┌───────────────┐
                         │ CLI / examples │
                         └───────┬───────┘
                                 │
                       ┌─────────▼─────────┐
                       │   SurfaceBuilder   │
                       └──────┬─────┬──────┘
                              │     │
               ┌──────────────┘     └──────────────┐
               ▼                                   ▼
        market data                         calibration/surface
               │                                   │
               ▼                                   ▼
         typed quotes                           SVI / SSVI
                                                   │
                          ┌────────────────────────┼───────────────┐
                          ▼                        ▼               ▼
                      IV/pricers              arbitrage        plotting
```

- **Plotting** is optional (`[plot]` extra) and never required by calibration.
- **Network I/O** lives only in the data layer; core mathematics are pure and
  importable offline.
- **Result objects** are typed dataclasses — never opaque dicts at the public API.

---

## Installation

```bash
pip install volfoundry        # core: numpy, scipy, pandas, pyarrow, requests
pip install volfoundry[plot]  # with matplotlib for surface/arbitrage plots
pip install volfoundry[dev]   # dev tools: pytest, hypothesis, mypy, ruff, pre-commit
```

Python ≥ 3.10 required.  No C++ compiler needed — the pure-Python path is the
guaranteed baseline.

### From source

```bash
git clone https://github.com/gavinwunz/volsurface
cd volsurface
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## Documentation

| Section | |
|---------|----|
| [Quickstart](docs/getting-started/quickstart.md) | 10-line workflow |
| [Installation](docs/getting-started/installation.md) | Full install guide |
| [Offline data](docs/getting-started/offline-data.md) | No-network workflows |
| [Deribit guide](docs/guides/deribit.md) | Fetching live data |
| [Fitting a surface](docs/guides/fitting-a-surface.md) | `SurfaceBuilder` in depth |
| [Validating a surface](docs/guides/validating-a-surface.md) | Arbitrage checks |
| [Querying a surface](docs/guides/querying-a-surface.md) | IV interpolation |
| [Historical snapshots](docs/guides/historical-snapshots.md) | Reproducibility |
| [API reference](docs/api/index.md) | All stable public objects |
| [Derivations](docs/derivations/) | Full formula derivations |

**Concept pages** cover implied volatility, the volatility smile, SVI, SSVI,
arbitrage conditions, and forward extraction — each with Definition, Assumptions,
Formula, Implementation, Numerical Caveats, and References sections.

---

## Mathematical models

| Model | Reference | Role |
|-------|-----------|------|
| Black-76 | Black (1976) | Forward-based pricing and IV inversion |
| Raw SVI | Gatheral (2004) | Per-expiry smile parameterization |
| SSVI | Gatheral & Jacquier (2014) | Global no-arbitrage surface |
| CRR binomial | Cox, Ross & Rubinstein (1979) | American exercise / tree methods |

Full derivations, assumptions, and numerical caveats for each model are in
[`docs/derivations/`](docs/derivations/) and the
[`docs/concepts/`](docs/concepts/) pages.

---

## Unit conventions

- **Strike**: quote currency (USD for Deribit BTC/ETH)
- **Maturity**: years (e.g. `30 / 365.25`)
- **Volatility**: decimal (0.60 = 60% annualised)
- **Prices**: same as source (Deribit mid converted to USD)

---

## Contributing

Bug reports, feature requests, and pull requests are welcome.  See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, test commands, code style, and PR
expectations.  Report security issues via [`SECURITY.md`](SECURITY.md).

---

## Disclaimer

VolFoundry is open-source research/educational software.  It is **not**
investment advice.  There is no warranty of market-data completeness or
correctness.  Models carry assumptions and numerical limitations documented in
the project; users are responsible for independent validation before any
financial use.

---

## License

MIT