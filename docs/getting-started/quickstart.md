# Quickstart

Ten lines to a calibrated volatility surface from live Deribit data:

```python
from volfoundry import DeribitClient, SurfaceBuilder

snapshot = DeribitClient().fetch("BTC")
result = SurfaceBuilder().fit(snapshot, validation="strict")

print(result.surface.iv(strike=70_000, maturity=30 / 365.25))
print(result.validation.is_valid)          # True when all checks pass
print(result.calibration_status)           # "converged", "converged_invalid", or "did_not_converge"
print(result.global_diagnostics["r2"])     # Overall fit quality
```

That's it.  The pipeline under the hood:

```text
Deribit option chain
  → quote cleaning (zero bid, crossed, near-expiry)
  → put-call parity forward extraction per expiry
  → Black-76 implied volatility inversion
  → raw SVI calibration per slice (Zeliade quasi-explicit)
  → global SSVI calibration (Gatheral–Jacquier 2014)
  → static-arbitrage validation
  → SurfaceFitResult
```

## Offline data

```python
from volfoundry import SurfaceBuilder
import pandas as pd

df = pd.read_parquet("btc-snapshot.parquet")
result = SurfaceBuilder().fit_dataframe(df, validation="report")

print(f"Valid: {result.validation.is_valid}")
print(f"Butterfly pass: {result.validation.butterfly_passed}")
print(f"Calendar pass: {result.validation.calendar_passed}")
```

## Diagnostics

The `SurfaceFitResult` object carries everything:

```python
print(result.quote_cleaning_stats)     # raw: 794, retained: 711, ...
print(result.per_expiry_diagnostics)   # per-slice RMSE, R², g(k) min
print(result.optimizer_diagnostics)    # success, message, ...
print(result.validation.rejected_slices)
print(result.validation.rejection_reasons)
```

## Research mode vs strict mode

```python
# Report mode: always returns a result, even if invalid
result = builder.fit(snapshot, validation="report")
print(result.validation.is_valid)  # might be False — inspect why

# Strict mode: raises ArbitrageViolationError if surface fails checks
result = builder.fit(snapshot, validation="strict")
```

## Units

- **Strike**: USD (or quote currency)
- **Maturity**: years (e.g. `30 / 365.25` for 30 days)
- **Volatility**: decimal (0.60 = 60% annualised)
- **Prices**: same units as the source (Deribit mid = USD for BTC/ETH)