# VolFoundry Architecture

This document describes the high-level architecture of the VolFoundry library,
its module dependencies, and the design principles that guide development.

## Architecture diagram

```text
                         ┌───────────────┐
                         │ CLI / examples │
                         └───────┬───────┘
                                 │
                       ┌─────────▼─────────┐
                       │ high-level service │
                       │ SurfaceBuilder     │
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

## Dependency rules

1. **Plotting must not be required by calibration.**  `surface.plotting` and
   `arbitrage.plotting` are optional and depend on the optional `[plot]` extra.
2. **Live Deribit code must not be imported by pure pricing routines.**
   `volfoundry.pricers`, `volfoundry.iv`, `volfoundry.svi`, and
   `volfoundry.surface` are importable without network effects.
3. **Core mathematical modules must not perform network I/O.**
4. **Result objects must use typed dataclasses at public boundaries** — no
   opaque dictionaries at the top-level API.
5. **Avoid circular imports.**
6. **Keep low-level functions available and testable.**

## Module map

### `volfoundry` (root)

Public API entry point.  Exports `DeribitClient`, `SurfaceBuilder`,
`VolatilitySurface`, `SurfaceFitResult`, `ValidationReport`, `OptionChain`,
`Snapshot`, exception taxonomy, and `__version__`.  Small; everything else is
imported from subpackages.

### `volfoundry.data`

Market data ingestion and preparation.

| Module | Purpose |
|--------|---------|
| `data.fetcher` | Deribit REST JSON-RPC client, `Snapshot`, `OptionQuote` |
| `data.filters` | Quote cleaning (zero bid, crossed, near-expiry) |
| `data.forwards` | Put-call parity OLS forward extraction |
| `data.persistence` | Parquet snapshot save/load with schema versioning |

### `volfoundry.iv`

Implied volatility inversion.

| Module | Purpose |
|--------|---------|
| `iv.black_scholes` | Black-76 price, vega, IV solver (Newton-Raphson + Brent) |

### `volfoundry.svi`

Raw SVI parameterization and calibration.

| Module | Purpose |
|--------|---------|
| `svi.parameterization` | `SviParams`, w(k), derivatives, Lee check |
| `svi.calibration` | Zeliade quasi-explicit calibration, weighting functions |

### `volfoundry.surface`

SSVI surface construction and high-level API.

| Module | Purpose |
|--------|---------|
| `surface.ssvi` | `SsviParams`, SSVI functional form, SVI mapping |
| `surface.calibration` | Two-stage global SSVI calibration |
| `surface.builder` | `SurfaceBuilder` — full pipeline orchestrator |
| `surface.volatility_surface` | `VolatilitySurface` — IV interpolation object |
| `surface.result_types` | `SurfaceFitResult`, `ValidationReport`, `OptionChain` |
| `surface.plotting` | 3D surface, skew, smile, diagnostics plots |

### `volfoundry.arbitrage`

Static-arbitrage validation.

| Module | Purpose |
|--------|---------|
| `arbitrage.checks` | Butterfly g(k), calendar, BL density, surface validation |
| `arbitrage.plotting` | g(k) plots, human-readable validation reports |

### `volfoundry.pricers`

Pricing engines.

| Module | Purpose |
|--------|---------|
| `pricers.black_scholes` | Black-76 analytical price and all Greeks |
| `pricers.binomial` | CRR tree (European and American, FD Greeks) |
| `pricers.monte_carlo` | MC with antithetic variates and control variate |

### `volfoundry.cli`

Command-line entry points (`volfoundry` script).  Thin wrapper over the library.

### `volfoundry.tolerances`

Central named numerical tolerances: `PRICE_TOL`, `VOL_TOL`, `ARBITRAGE_TOL`,
`CALIBRATION_TOL`, plus derived constants (`VEGA_FLOOR`, `SIGMA_FLOOR`, etc.).

### `volfoundry.exceptions`

Exception taxonomy: `VolFoundryError` base class with domain-specific
subclasses for data, pricing, calibration, and configuration errors.

## Design decisions

### Why src layout?

The `src/volfoundry/` layout prevents accidental imports of the source tree
during development.  `pip install -e` is required; `python -c "import
volfoundry"` in the repo root without installation will fail — this is
intentional and prevents subtle test-vs-installed discrepancies.

### Why dataclasses instead of NumPy structured arrays or named tuples?

Dataclasses provide:
- Type annotations visible to editors and mypy.
- Default values and validation in `__post_init__`.
- `__repr__` for inspectability.
- Compatibility across Python versions without extra dependencies.

### Why SSVI instead of a more flexible model?

SSVI provides:
- Analytical constraints (Lee bound, calendar sufficiency conditions) that can
  be enforced during calibration.
- A small, interpretable global parameter set.
- Provenance in the academic literature (Gatheral–Jacquier 2014).

This makes it appropriate for a first production release where mathematical
honesty and inspectability matter more than maximum flexibility.

### Why the Zeliade method for SVI?

The quasi-explicit method (outer 2D optimisation, inner constrained LLS) is faster
and more stable than a brute-force 5D optimisation.  It separates the well-behaved
parameters (a, b, rho) from the harder geometry parameters (m, sigma).

### Why parquet for persistence?

Parquet provides:
- Schema-safe, columnar storage.
- Built-in compression.
- Metadata storage (used for schema versioning).
- Wide ecosystem support (pandas, Polars, Arrow).
- Not Python-pickle-dependent — data can be read by non-Python tools.

## Adding a new feature

1. Determine which layer it belongs to (data, calibration, pricing, arbitrage).
2. Add the implementation in the appropriate subpackage.
3. Add type annotations and docstrings.
4. Add tests in the corresponding `tests/` directory.
5. If it's public, document it in the API reference and guides.

## See also

- [API inventory](api_inventory.md)
- [Numerics inventory](numerics_inventory.md)
- [Network inventory](network_inventory.md)
- [Baseline report](baseline.md)
- [Releasing guide](releasing.md)