# API Reference

This page documents the stable public API of VolFoundry v0.1.0.  Advanced users
may also import directly from submodules (`volfoundry.svi`, `volfoundry.iv`,
etc.) — those interfaces are considered stable but are not re-exported from the
package root.

## High-level API (`volfoundry`)

These are the symbols exported from `volfoundry.__init__`.

### `DeribitClient`

```python
from volfoundry import DeribitClient
```

High-level client for fetching Deribit option-chain snapshots.

**Purpose**: Fetch live public option chain data from Deribit's REST API.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connect_timeout` | `float` | `10` | TCP connect timeout (seconds) |
| `read_timeout` | `float` | `30` | Read timeout (seconds) |

| Method | Returns | Description |
|--------|---------|-------------|
| `fetch(currency)` | `Snapshot` | Fetch full option chain for `"BTC"` or `"ETH"` |

**Raises**: `MarketDataError` on JSON-RPC errors, HTTP failures, or empty
instrument lists.  Never returns an empty snapshot as a proxy for failure.

**Example**:
```python
client = DeribitClient()
snapshot = client.fetch("BTC")
```

**Notes**: The client lazily creates a `requests.Session` with retry logic
(3 retries, exponential backoff with jitter, only on 429/5xx).  Importing
this module makes no network calls.

---

### `SurfaceBuilder`

```python
from volfoundry import SurfaceBuilder
```

Orchestrate the full calibration pipeline.

**Purpose**: Accept market data and produce a `SurfaceFitResult` containing
a calibrated `VolatilitySurface` and structured `ValidationReport`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_quotes_per_slice` | `int` | `4` | Minimum quotes needed per expiry |
| `min_expiry_days` | `float` | `2.0` | Exclude quotes with < N days to expiry |
| `svi_outer_tol` | `float` | `1e-8` | Outer optimization tolerance for SVI |
| `ssvi_tol` | `float` | `1e-8` | Optimization tolerance for SSVI |
| `k_range` | `(float, float)` | `(-3.0, 3.0)` | Log-moneyness range for validation |
| `n_k` | `int` | `501` | Number of points in validation grid |
| `butterfly_tol` | `float` | `-1e-12` | Tolerance for g(k) ≥ tol |
| `calendar_tol` | `float` | `-1e-12` | Tolerance for calendar monotonicity |

| Method | Returns | Description |
|--------|---------|-------------|
| `fit(data, validation, rho, r)` | `SurfaceFitResult` | Fit surface from Snapshot/OptionChain/DataFrame |
| `fit_dataframe(df, validation, rho, r)` | `SurfaceFitResult` | Fit from cleaned DataFrame (offline path) |

**`fit()` parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `Snapshot | OptionChain | DataFrame` | — | Market data |
| `validation` | `str` | `"report"` | `"report"` or `"strict"` |
| `rho` | `float | None` | `None` | Fix SSVI correlation; `None` = calibrate |
| `r` | `float` | `0.0` | Risk-free rate for diagnostics |

**Raises**:
- `ValueError` if input data is empty or cannot be processed.
- `ArbitrageViolationError` in `validation="strict"` when surface fails checks.
- `TypeError` if `data` is not a recognised type.

**Example**:
```python
builder = SurfaceBuilder()
snapshot = DeribitClient().fetch("BTC")
result = builder.fit(snapshot)
print(result.surface.iv(strike=70000, maturity=30/365.25))
```

**Notes**: The pipeline runs sequentially: clean → forwards → SVI → SSVI → validate.
When `data` is a `Snapshot`, quote cleaning and forward extraction are automatic.
For an `OptionChain` or DataFrame, those steps are skipped (data is presumed cleaned).

---

### `VolatilitySurface`

```python
from volfoundry import VolatilitySurface
```

A callable object that interpolates IV from a calibrated SSVI surface.

**Purpose**: Evaluate implied volatility at any (strike, maturity) pair within
the calibrated domain.

**Constructed by** `SurfaceBuilder`; typically not instantiated directly.

| Property | Type | Description |
|----------|------|-------------|
| `params` | `SsviParams` | Global SSVI parameters (read-only copy) |
| `expiry_times` | `ndarray` | Grid of time-to-expiry values (years) |
| `min_expiry` | `float` | Minimum expiry covered (years) |
| `max_expiry` | `float` | Maximum expiry covered (years) |
| `n_slices` | `int` | Number of expiry slices |

| Method | Returns | Description |
|--------|---------|-------------|
| `iv(strike, maturity, F)` | `float` | IV at a single point |
| `total_variance(k, T)` | `float or ndarray` | Total variance w(k,T) |
| `iv_grid(strikes, maturities, F)` | `ndarray (n_K, n_T)` | IV on a full grid |

**`iv()` parameters**:

| Parameter | Type | Description | Units |
|-----------|------|-------------|-------|
| `strike` | `float` | Strike price (must be > 0) | Quote currency |
| `maturity` | `float` | Time to expiry (must be > 0) | Years |
| `F` | `float or None` | Forward price | Quote currency |

**Raises**: `ValueError` if `strike ≤ 0` or `maturity ≤ 0`.

**Example**:
```python
iv = surface.iv(strike=70000, maturity=30/365.25, F=64000)
```

**Notes**: If `F` is `None`, only at-the-money IV ($k=0$, so
$\sigma_{\text{IV}} = \sqrt{\theta/T}$) is meaningful.  Log-linear
interpolation in $T$ is used between SSVI grid points.

---

### `SurfaceFitResult`

Structured result from `SurfaceBuilder.fit()`.

| Attribute | Type | Description |
|-----------|------|-------------|
| `surface` | `VolatilitySurface or None` | Calibrated surface (`None` on total failure) |
| `validation` | `ValidationReport` | Structured no-arbitrage report |
| `calibration_status` | `str` | `"converged"`, `"converged_invalid"`, `"did_not_converge"`, `"failed"` |
| `optimizer_diagnostics` | `dict` | Optimizer termination info |
| `quote_cleaning_stats` | `dict` | Per-reason quote removal counts |
| `per_expiry_diagnostics` | `list[dict]` | Per-slice RMSE, R², g(k) min, SVI status |
| `global_diagnostics` | `dict` | Overall R², RMSE, global params, violations |
| `source_snapshot` | `dict` | Currency, timestamp, source |
| `warnings` | `list[str]` | Non-fatal warnings |
| `theta_raw` | `ndarray or None` | Raw ATM variances before repair |
| `theta_adjusted` | `ndarray or None` | ATM variances used by surface |

**Example**:
```python
result = builder.fit(snapshot)
if result.calibration_status == "converged":
    sigma_atm = result.surface.iv(strike=F, maturity=30/365.25, F=F)
```

---

### `ValidationReport`

Structured no-arbitrage validation report.

| Attribute | Type | Description |
|-----------|------|-------------|
| `is_valid` | `bool` | All checks pass within tolerance |
| `butterfly_passed` | `bool or None` | Butterfly g(k) ≥ tol for all slices |
| `calendar_passed` | `bool or None` | Total variance monotonic in T |
| `density_passed` | `bool or None` | BL density non-negative |
| `analytical_conditions` | `dict` | per-condition True/False/None |
| `rejected_slices` | `list[str]` | Slice IDs that failed |
| `rejection_reasons` | `dict[str, list[str]]` | Human-readable failure reasons |
| `evaluation_domain` | `dict` | k range, n_k, n_slices |
| `tolerances` | `dict` | Tolerances used in each check |
| `per_slice` | `list[dict]` | Per-slice diagnostic summaries |
| `warnings` | `list[str]` | Non-fatal warnings |

---

### `OptionChain`

Typed offline data container.

| Attribute | Type | Description |
|-----------|------|-------------|
| `currency` | `str` | Underlying currency |
| `timestamp` | `datetime` | Retrieval time (UTC) |
| `source` | `str` | Data source identifier |
| `quotes` | `DataFrame` | Cleaned quote records |
| `forwards` | `dict` | Pre-computed forwards (optional) |
| `schema_version` | `int` | Schema version (current: 1) |
| `metadata` | `dict` | Arbitrary extra metadata |

---

### `Snapshot`

Live Deribit snapshot (from `DeribitClient.fetch()`).

| Attribute | Type | Description |
|-----------|------|-------------|
| `currency` | `str` | `"BTC"` or `"ETH"` |
| `timestamp` | `datetime` | Retrieval timestamp (UTC) |
| `raw_quotes` | `list[OptionQuote]` | Raw quote objects |
| `cleaning_report` | `QuoteCleaningReport` | Cleaning diagnostics |
| `schema_version` | `int` | Schema version |

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dataframe()` | `DataFrame` | Quotes as a DataFrame |

---

### `QuoteCleaningReport`

| Attribute | Type | Description |
|-----------|------|-------------|
| `raw_count` | `int` | Quotes before cleaning |
| `retained_count` | `int` | Quotes after cleaning |
| `removed_counts` | `dict[str, int]` | Per-reason removal counts |
| `removals` | `list[QuoteRemovalRecord]` | Per-quote removal reasons (when detailed) |

---

### Exceptions

All exceptions inherit from `VolFoundryError`.

| Exception | Base | When raised |
|-----------|------|-------------|
| `VolFoundryError` | `Exception` | Base for all VolFoundry errors |
| `DataError` | `VolFoundryError` | Generic data-layer failure |
| `MarketDataError` | `DataError` | Deribit HTTP/RPC failure |
| `QuoteValidationError` | `DataError` | Invalid quote data |
| `PersistenceError` | `DataError` | Snapshot read/write failure |
| `PricingError` | `VolFoundryError` | Generic pricing failure |
| `ImpliedVolError` | `PricingError` | IV inversion failure |
| `CalibrationError` | `VolFoundryError` | Generic calibration failure |
| `CalibrationConvergenceError` | `CalibrationError` | Optimizer did not converge |
| `InvalidSurfaceError` | `CalibrationError` | Surface is invalid |
| `ArbitrageViolationError` | `InvalidSurfaceError` | Strict-mode arbitrage failure |
| `ConfigurationError` | `VolFoundryError` | Invalid configuration |

---

## Submodule imports (advanced)

For users who need direct access to lower-level functions:

```python
from volfoundry.pricers import black76_price, black76_all_greeks, crr_price, mc_price
from volfoundry.iv import implied_volatility, black76_vega
from volfoundry.svi import calibrate_svi_slice, SviParams, svi_total_variance
from volfoundry.surface import calibrate_ssvi_surface, SsviParams
from volfoundry.arbitrage import validate_surface, butterfly_g
from volfoundry.data import write_snapshot, load_snapshot, extract_forwards
```

These functions are stable and tested but are not re-exported from the root
package.  See the [full API inventory](../development/api_inventory.md) for
a complete listing.