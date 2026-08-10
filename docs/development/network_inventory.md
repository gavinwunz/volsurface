# Network / External I/O Inventory

Every location in the codebase that makes an HTTP call, reads the filesystem,
or depends on external state.

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

**Gaps (P5):**
- No explicit connect/read timeout separation (only combined timeout=30s).
- No `User-Agent` header set.
- No retry logic on transient failures.
- No backoff/jitter.
- No 429 handling.
- No retry for 5xx.
- `_rpc` calls `.raise_for_status()` then parses JSON — OK but missing error context.
- `fetch_snapshot` catches no exceptions — bubbles up.

### Import-time network checks

**None.** Importing `volfoundry` or any submodule does not call any external API.
All HTTP activity requires explicit user invocation of `DeribitPublicClient` methods.

## Filesystem I/O

### `volfoundry/data/persistence.py`

| Function | Operation | Format | Notes |
|----------|-----------|--------|-------|
| `write_snapshot()` | write | parquet | Timestamped filename, but **no atomic write** (writes directly to destination). |
| `read_snapshot()` | read | parquet | Reads specific file path. |
| `load_snapshot()` | read | parquet | Scans directory, returns most recent for currency. |
| `list_snapshots()` | read (glob) | — | Lists files by pattern. |

**Gaps (P5/P24):**
- No atomic write (temp + rename).
- No schema version in persisted files.
- No validation of loaded snapshot structure.

### `examples/live_surface_demo.py`

| Operation | Path | Notes |
|-----------|------|-------|
| Save PNG | `reports/` | Saves diagnostic plots via matplotlib. |
| Save parquet | `data/snapshots/` | Via `write_snapshot()` — demo only. |

### Plotting modules (`arbitrage/plotting.py`, `surface/plotting.py`)

| Operation | Notes |
|-----------|-------|
| `matplotlib.pyplot.savefig` | Writes PNG files. Only on explicit call. |
| `print()` | Only in demo script, not in library code. |

## External dependency boundary

| Dependency | Required for | Import-time cost |
|------------|-------------|------------------|
| `requests` | All Deribit calls | None (not imported at package load) |
| `pyarrow` | Parquet persistence | None |
| `matplotlib` | Plotting | Not imported at package load; surfaces only via plot functions |
| `QuantLib` | Benchmark tests | Optional, test-guarded |
| `py_vollib` | IV benchmark test | Optional, test-guarded |
| `cpp/_core` | C++ hot path | Optional, try/except in `pricers/__init__.py` |

## Randomness / external entropy

| Location | Source | Controlled? |
|----------|--------|-------------|
| `mc_price()` | `np.random.default_rng(seed)` | Yes — explicit seed parameter |
| `mc_price_with_confidence()` | via `mc_price()` | Yes |
| Tests (fixtures) | `np.random.RandomState(fixed_seed)` | Yes |
| Hypothesis tests | Hypothesis internal RNG | Yes (deterministic default) |

## Summary

- **Network surface:** 2 RPC helpers + 4 public client methods → all Deribit REST.
  No network on import. No retry/backoff infrastructure. No User-Agent.
- **Filesystem surface:** 4 persistence functions (write parquet, read parquet,
  list, load). No atomic writes. No schema version.
- **No hidden network, no telemetry, no analytics.**