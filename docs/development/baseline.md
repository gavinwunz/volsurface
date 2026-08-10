# Pre-VolFoundry Production Baseline

Recorded before the P1 rename and any refactoring. This is the snapshot of
the `volfoundry` package at the start of the VolFoundry production upgrade.

## System

| Field             | Value |
|-------------------|-------|
| Commit SHA        | `27f5949` |
| Python            | 3.12.3 (main, Jun 19 2026, GCC 13.3.0) |
| OS                | Linux-6.17.0-1022-azure-x86_64-with-glibc2.39 |
| Architecture      | x86_64 |
| Git branch        | `main` |
| Git remote        | `https://github.com/gavinwunz/volfoundry` |

## Test suite

| Metric                     | Value |
|----------------------------|-------|
| Total test files           | 10 |
| Total test functions       | 319 |
| Passing                    | 319 |
| Failing                    | 0 |
| Skipped (opt-deps missing) | 0 |
| Marked `live`              | 0 |
| Marked `benchmark`         | 0 |

Test file breakdown:
- `test_arbitrage.py`: 31 (includes hypothesis property-based tests)
- `test_fetcher.py`: 9
- `test_filters.py`: 11
- `test_forwards.py`: 7
- `test_iv.py`: 48 (includes py_vollib benchmark skip test)
- `test_persistence.py`: 5
- `test_pricers.py`: 88 (includes QuantLib benchmark skip tests, C++ hot path tests)
- `test_surface.py`: 56
- `test_surface_plotting.py`: 27
- `test_svi.py`: 37

Run command: `pytest -m "not live and not benchmark" -q`
Time: ~4.5 s

## Package build

| Field           | Value |
|-----------------|-------|
| Build backend   | setuptools.build_meta |
| Wheel name      | `volfoundry-0.0.1-py3-none-any.whl` |
| Sdist name      | `volfoundry-0.0.1.tar.gz` |
| Version         | 0.0.1 |
| Requires-Python | >=3.10 |
| License         | MIT |
| Layout          | Flat (not `src/`) |

`python -m build` succeeds. `twine check dist/*` not yet validated.

## Live demo

The demo at `examples/live_surface_demo.py` runs end-to-end against the
Deribit public REST API. It fetches BTC/ETH option chains, cleans quotes,
calibrates raw SVI per expiry, fits a global SSVI surface, runs
butterfly/calendar/Breeden-Litzenberger checks, and writes diagnostic PNGs.

Sample diagnostic PNGs from a live run are committed at:
- `docs/images/live_surface_3d.png`
- `docs/images/live_skew_term_structure.png`
- `docs/images/live_svi_smiles.png`
- `docs/images/live_butterfly_gk.png`

## C++ extension

The C++ hot path (`volfoundry/pricers/_core.cpython-312-x86_64-linux-gnu.so`)
is built via pybind11. It provides vectorised Black-76 price + Greeks.
Import failure falls back gracefully to the pure-Python path.
Benchmark claims (~3× vs QuantLib) are from a specific run on this machine
and need regeneration on controlled hardware before including in public
marketing.

## Installed dependencies (including dev/benchmark)

| Package     | Version    |
|-------------|------------|
| numpy       | 2.5.2      |
| scipy       | 1.18.0     |
| pandas      | 3.0.5      |
| pyarrow     | 25.0.0     |
| requests    | 2.34.2     |
| matplotlib  | 3.11.1     |
| pytest      | 9.1.1      |
| hypothesis  | 6.165.2    |
| py_vollib   | installed  |
| QuantLib    | 1.43       |
| ruff        | installed  |

## Stochastic test seed audit

- Monte Carlo: uses `np.random.default_rng(seed)` with optional seed parameter
  in `mc_price()` and `mc_price_with_confidence()`. Regression tests pass
  `seed=42`.
- SVI calibration: deterministic (L-BFGS-B with deterministic initial
  conditions). No stochastic element.
- Test helpers: use `np.random.RandomState(123)`, `RandomState(42)`,
  `RandomState(7)`, `RandomState(99)` for fixture generation.
- Hypothesis: uses its internal seed management (deterministic by default
  with `derandomize=True` in CI).
- No unseeded `np.random.*` calls found in library or test code.

## Key observations before refactoring

1. Package layout is flat (not `src/` layout).
2. Root `__init__.py` exports only `__version__`.
3. Subpackage `__init__.py` files (iv, svi, arbitrage, surface) are
   mostly empty stubs.
4. Only `pricers/__init__.py` and `data/__init__.py` have real re-exports.
5. `print()` calls exist only in the example script and benchmark test
   output; zero in library code.
6. No `TODO` or `FIXME` markers found in source code.
7. Package version 0.0.1 appears in `pyproject.toml` and `volfoundry/__init__.py`
   (two locations — not a single source of truth).
8. `pyproject.toml` has no extras groups — all dev deps lumped in `[project.optional-dependencies] dev`.
9. No pytest markers registered in configuration.
10. No CI/CD workflows present.
11. No `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`.
12. README says "arbitrage-free" prominently — needs scoping per plan §6.