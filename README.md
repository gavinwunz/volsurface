# volsurface

Arbitrage-free implied volatility surface construction for crypto options.

Pulls live option chains (Deribit), inverts Black-Scholes implied vol, calibrates
raw SVI slices via the Zeliade quasi-explicit method, enforces static no-arbitrage
(butterfly + calendar), and ties slices into a global SSVI surface. Includes a
C++ pricing hot path (pybind11) benchmarked against QuantLib.

## Status

Under active construction — see [`PROGRESS.md`](PROGRESS.md) for the live build state
and [`SPEC.md`](SPEC.md) for the full specification.

## Layout

```
volsurface/            # Python package
  data/                # M1: Deribit client, snapshots, forward extraction
  iv/                  # M2: implied vol inversion
  svi/                 # M3: raw SVI calibration
  arbitrage/           # M4: no-arbitrage checks
  pricers/             # M5: BS / CRR / MC pricers (+ C++ hot path)
  surface/             # M6: SSVI global fit + reporting
cpp/                   # pybind11 hot path
docs/derivations/      # full formula derivations
reports/               # diagnostic plots and honest failure logs
tests/                 # pytest + hypothesis
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
