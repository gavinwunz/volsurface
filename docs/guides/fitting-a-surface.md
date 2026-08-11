# Fitting a Volatility Surface

This guide covers the full calibration pipeline from market data to a usable
`VolatilitySurface`.

## The pipeline

```text
Market Data (Snapshot / DataFrame / OptionChain)
  → Quote cleaning (if Snapshot)
  → Forward extraction (if not pre-computed)
  → Black-76 IV per quote
  → Raw SVI calibration per expiry slice
  → SSVI global calibration across all slices
  → No-arbitrage validation
  → VolatilitySurface
```

All of this happens inside `SurfaceBuilder.fit()`.

## Basic usage

```python
from volfoundry import DeribitClient, SurfaceBuilder

snapshot = DeribitClient().fetch("BTC")
builder = SurfaceBuilder()
result = builder.fit(snapshot)
```

## Report mode (default)

```python
result = builder.fit(snapshot, validation="report")

print(result.calibration_status)
# "converged"          — surface is valid
# "converged_invalid"  — fit worked but arbitrage checks failed
# "did_not_converge"   — optimizer did not converge

if not result.validation.is_valid:
    for slice_id, reasons in result.validation.rejection_reasons.items():
        print(f"{slice_id}: {reasons}")
```

In report mode the surface is always returned.  You inspect `is_valid` to
decide whether to use it.

## Strict mode

```python
from volfoundry import ArbitrageViolationError

try:
    result = builder.fit(snapshot, validation="strict")
    # If we reach here, the surface passed all checks
except ArbitrageViolationError as e:
    print(f"Surface could not be made arbitrage-free: {e}")
```

Strict mode raises an exception rather than returning an invalid surface.
Use this when you need a programmatic guarantee that the result satisfies
the documented constraints.

## Tuning the builder

```python
builder = SurfaceBuilder(
    min_quotes_per_slice=6,     # skip very sparse expiries
    min_expiry_days=1.0,        # keep very short-dated options
    svi_outer_tol=1e-6,         # tighter SVI tolerance
    ssvi_tol=1e-6,              # tighter SSVI tolerance
    k_range=(-4.0, 4.0),        # wider validation domain
    n_k=1001,                   # finer validation grid
    butterfly_tol=-1e-14,       # tighter butterfly tolerance
    calendar_tol=-1e-14,        # tighter calendar tolerance
)
```

## Using pre-computed forwards

```python
from volfoundry import OptionChain
from datetime import datetime, timezone

chain = OptionChain(
    currency="BTC",
    timestamp=datetime.now(timezone.utc),
    source="manual",
    quotes=my_clean_df,
    forwards=my_forward_dict,  # {expiry_dt: float}
)
result = builder.fit(chain)
```

When `forwards` is provided on the `OptionChain`, the builder skips its own
forward extraction.

## Fixing the SSVI correlation

```python
# Force rho = -0.3 (calibrate only eta and lambda)
result = builder.fit(snapshot, rho=-0.3)
```

This is useful when you have a strong prior on the skew direction or want to
compare surfaces with different correlation assumptions.

## Offline from a DataFrame

```python
# df must have: strike, expiry (datetime), mid, bid, ask, option_type ("C"/"P")
result = builder.fit_dataframe(df, validation="report")
```

No network call is made.  This is the recommended path for research with
historical data.

## Inspecting the diagnostics

```python
result = builder.fit(snapshot)

# Cleaning
print(result.quote_cleaning_stats)
# {'raw': 794, 'removed_zero_bid': 41, 'removed_crossed': 2,
#  'removed_near_expiry': 36, 'retained': 711}

# Per-expiry
for d in result.per_expiry_diagnostics:
    print(f"{d['slice_id']} T={d['T']:.3f}  "
          f"RMSE={d['svi_rmse']:.4f}  R²={d['svi_r2']:.4f}  "
          f"status={d['svi_status']}  g_min={d['g_min']}")

# Global
print(f"R²={result.global_diagnostics['r2']:.4f}")
print(f"rho={result.global_diagnostics['rho']:.4f}")
print(f"eta={result.global_diagnostics['eta']:.4f}")
print(f"lambda={result.global_diagnostics['lambda']:.4f}")
```

## What can go wrong

| Problem | Symptom | Fix |
|---------|---------|-----|
| Too few quotes | `ValueError: No valid expiry slices` | Lower `min_quotes_per_slice`, use a richer snapshot |
| SVI fails | `svi_status: did_not_converge` in per-expiry diagnostics | Increase `svi_outer_tol`, check slice data |
| SSVI fails | `calibration_status: did_not_converge` | Check `optimizer_diagnostics`, try different `rho` |
| Arbitrage violation | `is_valid: False` | Inspect `rejection_reasons`, widen `k_range`, adjust tolerances |
| No forwards | `ValueError: Could not extract forward prices` | Provide `forwards` in `OptionChain`, use paired C/P data |