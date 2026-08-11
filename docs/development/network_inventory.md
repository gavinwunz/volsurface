# Network / External I/O Inventory

Every location in the codebase that makes an HTTP call, reads the filesystem,
or depends on external state.  Updated for the VolFoundry v0.1.0 release.

## HTTP / Network calls

### `volfoundry/data/fetcher.py`

| Location | Function | Method | Target | Notes |
|----------|----------|--------|--------|-------|
| L95-106 | `_rpc()` | `requests.Session.post` | `https://www.deribit.com/api/v2/` | Single JSON-RPC call. Timeout 30s. |
| L119-144 | `_batch_rpc()` | `requests.Session.post` | `https://www.deribit.com/api/v2/` | Batched JSON-RPC. Falls back to sequential on failure. |
| L155-156 | `DeribitPublicClient.__init__()` | `requests.Session()` | — | Creates reusable session (no call on init). |
| L164 | `fetch_option_instruments()` | via `_rpc` | Deribit | `public/get_instruments` |
| L175 | `fetch_ticker()` | via `_rpc` | Deribit | `public/ticker` |
| L177-186 | `fetch_tickers()` | via `_batch_rpc` | Deribit | Batch ticker fetch with rate-limit sleep |
| L190-260 | `fetch_snapshot()` | composes above | Deribit | Full pipeline: instruments → tickers → Snapshot |

**Hardened for production (P5):**
- Explicit connect (10s) and read (30s) timeouts.
- Reusable `requests.Session` with `urllib3.Retry`: 3 retries, exponential
  backoff with jitter, only on 429/5xx.
- Descriptive `User-Agent: VolFoundry/<version>`.
- JSON-RPC error fields validated before conversion.
- Raises `MarketDataError` on failure; never returns empty-success.
- Required response fields validated before object construction.

### Import-time network checks

**None.** Importing `volfoundry` or any submodule does not call any external API.
All HTTP activity requires explicit user invocation of `DeribitPublicClient`
methods.

### `volfoundry/client.py`

Thin wrapper around `DeribitPublicClient`.  Lazily creates the underlying
client so session creation is deferred to first `fetch()`.

## Filesystem I/O

### `volfoundry/data/persistence.py`

| Function | Operation | Format | Notes |
|----------|-----------|--------|-------|
| `write_snapshot()` | write | parquet | **Atomic write** (tempfile + rename). Schema version in metadata. |
| `read_snapshot()` | read | parquet | Validates schema version before loading. |
| `load_snapshot()` | read | parquet | Scans directory, returns most recent for currency. |
| `list_snapshots()` | read (glob) | — | Lists files by pattern. |

**Hardened (P5/P24):**
- Atomic writes via tempfile + rename — partial writes never observed.
- Schema version stored in parquet metadata (`volfoundry_schema_version`).
- Future schema versions rejected with clear error.
- Package version and retrieval timestamp stored for reproducibility.

### `examples/live_surface_demo.py`

| Operation | Path | Notes |
|-----------|------|-------|
| Save PNG | `reports/` | Saves diagnostic plots via matplotlib. |
| Save parquet | `data/snapshots/` | Via `write_snapshot()` — demo only. |

### Plotting modules (`surface/plotting.py`, `arbitrage/plotting.py`)

| Operation | Notes |
|-----------|-------|
| `matplotlib.pyplot.savefig` | Writes PNG files. Only on explicit call. |
| `logging` | Library code uses structured logging, not `print`. |

## External dependency boundary

| Dependency | Required for | Import-time cost |
|------------|-------------|------------------|
| `numpy` | Core computation | Always imported — standard array library |
| `scipy` | Optimisation (L-BFGS-B) | Imported in calibration modules |
| `pandas` | Data handling | Imported in data/surface modules |
| `requests` | Deribit calls | Not imported at package load |
| `matplotlib` | Plotting (optional `[plot]` extra) | Not imported at package load |
| `pyarrow` | Parquet persistence (with pandas) | Required for parquet I/O |
| `QuantLib` | Benchmark tests (optional `[benchmark]` extra) | Test-guarded |
| `py_vollib` | IV benchmark test (optional `[benchmark]` extra) | Test-guarded |
| `cpp/_core` | C++ hot path | Optional, try/except in `pricers/__init__.py` |

## Randomness / external entropy

| Location | Source | Controlled? |
|----------|--------|-------------|
| `mc_price()` | `np.random.default_rng(seed)` | Yes — explicit seed parameter |
| `mc_price_with_confidence()` | via `mc_price()` | Yes |
| Tests (fixtures) | `np.random.RandomState(fixed_seed)` | Yes |
| Hypothesis tests | Hypothesis internal RNG | Yes (deterministic default) |

## Summary

- **Network surface:** All Deribit REST, via hardened `DeribitPublicClient`.
  No network on import. Bounded retries with backoff + jitter. Explicit timeouts.
- **Filesystem surface:** 4 persistence functions with atomic writes and schema
  versioning. Parquet format only.
- **No hidden network, no telemetry, no analytics.**