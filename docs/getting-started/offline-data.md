# Working Offline

VolFoundry's core calibration and pricing routines never require network access.
Importing `volfoundry` makes no external calls.  Only the `DeribitClient.fetch()`
method initiates HTTP traffic.

## Building surfaces from a DataFrame

The minimal required columns:

| Column | dtype | Unit | Notes |
|--------|-------|------|-------|
| `strike` | `float64` | quote currency | Must be positive |
| `expiry` | `datetime64[ns, UTC]` | — | Timezone-aware |
| `mid` | `float64` | quote currency | Mid price |
| `bid` | `float64` | quote currency | Optional for calibration, used for weighting |
| `ask` | `float64` | quote currency | Optional for calibration, must be ≥ bid |
| `option_type` | `str` | — | `"C"` or `"P"` |
| `underlying_price` | `float64` | quote currency | Spot or index price |

```python
import pandas as pd
from volfoundry import SurfaceBuilder

df = pd.DataFrame({
    "strike": [60000, 62000, 64000, 66000, 68000],
    "expiry": pd.to_datetime(["2026-09-30T08:00:00Z"] * 5, utc=True),
    "mid": [5200, 3400, 1800, 700, 200],
    "bid": [5180, 3380, 1780, 680, 180],
    "ask": [5220, 3420, 1820, 720, 220],
    "option_type": ["C", "C", "C", "P", "P"],
    "underlying_price": [64000] * 5,
})

result = SurfaceBuilder().fit_dataframe(df, validation="report")
print(result.surface.iv(strike=64000, maturity=30 / 365.25, F=64000))
```

## Using `OptionChain`

For typed offline input:

```python
from datetime import datetime, timezone
from volfoundry import SurfaceBuilder, OptionChain

chain = OptionChain(
    currency="BTC",
    timestamp=datetime.now(timezone.utc),
    source="manual",
    quotes=df,          # cleaned DataFrame as above
)

result = SurfaceBuilder().fit(chain, validation="strict")
```

## Saving and loading snapshots

Snapshots fetched live can be persisted and reloaded:

```python
from volfoundry import DeribitClient
from volfoundry.data.persistence import write_snapshot, load_snapshot, list_snapshots

# Fetch and save
client = DeribitClient()
snapshot = client.fetch("BTC")
path = write_snapshot(snapshot)              # → data/snapshots/BTC-20260810T...parquet

# Later, offline
snapshots = list_snapshots("BTC")            # list available files
snapshot2 = load_snapshot("BTC")             # load most recent
print(snapshot2.currency, snapshot2.timestamp)
```

Atomic writes (tempfile + rename) ensure partial writes are never observed.
Historical snapshots are never overwritten by default.

## Snapshot schema versioning

Every snapshot carries `schema_version` in its parquet metadata.  VolFoundry will
reject snapshots with a future, unknown schema version rather than attempting to
parse them incorrectly.  The current schema version is 1.