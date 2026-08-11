# Fetching Data from Deribit

VolFoundry's `DeribitClient` fetches public option-chain data from Deribit's
REST JSON-RPC 2.0 endpoint.  No authentication or API key is required.

## Quick fetch

```python
from volfoundry import DeribitClient

client = DeribitClient()
snapshot = client.fetch("BTC")
print(f"Got {len(snapshot.raw_quotes)} raw quotes for {snapshot.currency}")
```

The `Snapshot` object contains:

- `currency` — `"BTC"` or `"ETH"`
- `timestamp` — timezone-aware UTC retrieval timestamp
- `raw_quotes` — list of `OptionQuote` dataclass objects
- `cleaning_report` — `QuoteCleaningReport` with per-reason counts
- `to_dataframe()` — quotes as a pandas DataFrame
- `schema_version` — for compatibility

## What happens under the hood

1. **`get_instruments("BTC")`**: Fetches all active BTC options from
   Deribit's `/public/get_instruments` RPC.

2. **`get_order_book()`** (batched): Fetches order books for each instrument
   in batches of 100, respecting Deribit's concurrent call limit.

3. **Quote construction**: Bid/ask/mid prices are constructed from the best
   bid/ask in the order book.

4. **Cleaning**: Quote filters run automatically — zero bids/asks are removed,
   crossed quotes (bid > ask) are removed, quotes with < 2 days to expiry
   are removed by default.  The `cleaning_report` shows exactly what was
   filtered.

## HTTP behaviour

- **Connect timeout**: 10 seconds
- **Read timeout**: 30 seconds
- **Retries**: 3 retries on transient errors (429, 500, 502, 503, 504) with
  exponential backoff and jitter
- **User-Agent**: `VolFoundry/<version>`
- **Session reuse**: A single `requests.Session` is created lazily and reused

## Error handling

All HTTP and RPC errors raise `MarketDataError`:

```python
from volfoundry import DeribitClient, MarketDataError

try:
    snapshot = DeribitClient(read_timeout=15).fetch("BTC")
except MarketDataError as e:
    print(f"Data fetch failed: {e}")
```

Never does an API error silently return an empty snapshot.  If no instruments
are returned for a currency, `MarketDataError` is raised with an explicit
message.

## Saving for later

```python
from volfoundry.data.persistence import write_snapshot, load_snapshot

path = write_snapshot(snapshot)          # → data/snapshots/BTC-...parquet
later  = load_snapshot("BTC")            # loads most recent BTC snapshot
```

Atomic writes via tempfile + rename ensure partial files are never observed.
Each snapshot is timestamped so historical snapshots are never overwritten.

## Quotes versus raw order book

The `Snapshot` presents cleaned mid-prices by default.  Advanced users can
access raw `OptionQuote` objects from `snapshot.raw_quotes`:

```python
for q in snapshot.raw_quotes:
    print(q.instrument_name, q.bid, q.ask, q.mid, q.strike, q.expiry)
```

## Live test

A scheduled live integration test (`tests/live/test_live_smoke.py`) fetches
a small Deribit sample periodically to verify schema/pipeline health.  It does
not assert specific market values.

## Limitations

- Only public instruments — no private/portfolio endpoints.
- Only BTC and ETH currently supported (Deribit's main crypto option markets).
- The API is polling-based; no websocket streaming in v0.1.0.
- Order book depth is not consumed — only best bid/ask are used for mid
  construction.