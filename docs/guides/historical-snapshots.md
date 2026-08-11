# Working with Historical Snapshots

Snapshots are the unit of reproducibility in VolFoundry.  A snapshot captures
everything needed to reconstruct a surface later: raw quotes, retrieval
timestamp, source metadata, and a schema version for compatibility.

## Saving a live snapshot

```python
from volfoundry import DeribitClient
from volfoundry.data.persistence import write_snapshot

client = DeribitClient()
snapshot = client.fetch("BTC")
path = write_snapshot(snapshot)
print(f"Saved to {path}")
# → data/snapshots/BTC-20260810T205600-158937.parquet
```

The filename encodes the currency and retrieval timestamp so historical
snapshots are never overwritten.

## Listing saved snapshots

```python
from volfoundry.data.persistence import list_snapshots

btc_snapshots = list_snapshots("BTC")
for f in btc_snapshots:
    print(f.name)
# BTC-20260810T205231-435056.parquet
# BTC-20260810T205600-158937.parquet
```

## Loading the most recent

```python
from volfoundry.data.persistence import load_snapshot

snapshot = load_snapshot("BTC")
print(f"Loaded snapshot from {snapshot.timestamp}")
print(f"{len(snapshot.raw_quotes)} quotes")
```

## Loading a specific file

```python
from volfoundry.data.persistence import read_snapshot
from pathlib import Path

snapshot = read_snapshot(Path("data/snapshots/BTC-20260810T205600-158937.parquet"))
```

## Fitting from a saved snapshot

```python
from volfoundry import SurfaceBuilder
from volfoundry.data.persistence import load_snapshot

snapshot = load_snapshot("BTC")
result = SurfaceBuilder().fit(snapshot, validation="strict")
```

The calibration is deterministic given the same snapshot, builder configuration,
and NumPy random state — making research results reproducible.

## Schema versioning

Every snapshot stores its schema version in parquet metadata:

```python
print(snapshot.schema_version)  # 1
```

When loading, VolFoundry checks the schema version:
- Known version → loads normally.
- Future version → raises `PersistenceError` rather than attempting to parse
  unknown data.

The current schema version is 1.

## Round-trip integrity

```python
from volfoundry import DeribitClient
from volfoundry.data.persistence import write_snapshot, read_snapshot

# Write
client = DeribitClient()
original = client.fetch("ETH")
path = write_snapshot(original)

# Read back
restored = read_snapshot(path)

# Verify equivalence
assert original.currency == restored.currency
assert original.timestamp == restored.timestamp
assert original.schema_version == restored.schema_version
assert len(original.raw_quotes) == len(restored.raw_quotes)
```

## Atomic writes

Writes use a tempfile + rename strategy:
1. Write to a temporary file in the target directory.
2. Flush and close.
3. Atomically rename to the final filename.

This guarantees that a partial write (process crash, disk full, etc.) never
appears as a valid snapshot file.

## Custom data directory

```python
from volfoundry.data.persistence import write_snapshot

path = write_snapshot(snapshot, data_dir="/mnt/research/options-data/")
```

Or set the `VOLSURFACE_DATA_DIR` environment variable for a persistent default.

## Metadata captured

Each persisted snapshot records:

```python
# Parquet metadata keys:
#   volfoundry_schema_version   → "1"
#   volfoundry_package_version  → "0.1.0"
#   currency                    → "BTC"
#   retrieval_timestamp         → ISO 8601 UTC string
```

This is sufficient to reproduce results and to attribute them to the specific
VolFoundry version that created them.

## Exporting to DataFrame for external use

```python
snapshot = load_snapshot("BTC")
df = snapshot.to_dataframe()
print(df.columns)
# Index(['instrument_name', 'strike', 'expiry', 'option_type',
#        'bid', 'ask', 'mid', 'underlying_price', 'underlying', 'retrieved_at'], ...)

df.to_csv("btc_snapshot.csv")
df.to_parquet("btc_snapshot_external.parquet")
```

## Limitations

- Snapshots are flat files — there is no database, no indexing, and no query
  language.  For large collections, organise by directory or build your own index.
- The schema version system detects future-version snapshots but does not
  provide automatic migration between versions.  When the schema changes, a
  migration guide will be published.