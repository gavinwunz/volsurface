# Querying a Calibrated Surface

Once you have a `VolatilitySurface` (from `SurfaceBuilder.fit()`), you can
evaluate implied volatility, total variance, and prices at arbitrary
(strike, maturity) points.

## Single-point implied volatility

```python
sigma = surface.iv(strike=70_000, maturity=30/365.25, F=64_000)
print(f"IV = {sigma:.4f} ({sigma*100:.1f}%)")
# IV = 0.6234 (62.3%)
```

**Units**:
- `strike` — in the quote currency (e.g. USD)
- `maturity` — in **years** (e.g. `30/365.25` for 30 days)
- `F` — forward price in the same currency
- Returns decimal volatility (0.60 = 60%)

## Without a forward price

If you don't provide `F`, the surface can only give ATM IV:

```python
sigma_atm = surface.iv(strike=strike, maturity=30/365.25)  # F=None
# Internally: sigma_atm = sqrt(theta(T) / T) regardless of strike
```

The `strike` argument is still required but its value doesn't affect the result
when `F` is `None` — the surface falls back to the ATM variance at the given
maturity.

## Total variance

For advanced use (e.g. computing the butterfly function or doing your own
arbitrage checks):

```python
k = np.log(70_000 / 64_000)  # log-moneyness
w = surface.total_variance(k=k, T=30/365.25)
print(f"Total variance w(k,T) = {w:.6f}")
# Recover IV: sigma = sqrt(w / T)
```

`total_variance` accepts scalar or array `k`.

## Grid evaluation

```python
import numpy as np

strikes = np.array([50_000, 60_000, 64_000, 70_000, 80_000])
maturities = np.array([7/365.25, 30/365.25, 90/365.25, 365/365.25])
grid = surface.iv_grid(strikes, maturities, F=64_000)

# grid.shape == (5, 4)  —  rows = strikes, cols = maturities
# grid[i, j] = IV at (strikes[i], maturities[j])
```

## Extrapolation warnings

The surface extrapolates beyond the calibrated expiry range using flat
extension:

- $T \leq T_{\min}$: uses $\theta(T_{\min})$
- $T \geq T_{\max}$: uses $\theta(T_{\max})$

This is a pragmatic choice — the surface doesn't refuse to evaluate, but
you should be aware that extrapolated values carry no calibration guarantee.
Check the valid range:

```python
print(f"Calibrated range: {surface.min_expiry:.4f} to {surface.max_expiry:.2f} years")
```

## Pricing from the surface

To price an option from surface-implied volatility:

```python
from volfoundry.pricers import black76_price, OptionType

sigma = surface.iv(strike=70_000, maturity=30/365.25, F=64_000)
price = black76_price(F=64_000, K=70_000, T=30/365.25, sigma=sigma,
                      option_type=OptionType.CALL, r=0.0)
print(f"Call price = {price:.2f} USD")
```

## Comparing two surfaces

```python
# Surface A from live data
result_a = builder_a.fit(snapshot_a)
surface_a = result_a.surface

# Surface B from historical data
result_b = builder_b.fit(snapshot_b)
surface_b = result_b.surface

# Compare ATM IV at 30 days
atm_iv_a = surface_a.iv(strike=F_a, maturity=30/365.25, F=F_a)
atm_iv_b = surface_b.iv(strike=F_b, maturity=30/365.25, F=F_b)

print(f"ATM IV change: {(atm_iv_a - atm_iv_b) * 100:.1f} vol points")
```

## Surface properties

```python
print(surface.currency)         # "BTC"
print(surface.n_slices)         # number of calibrated expiry slices
print(surface.expiry_times)     # array of T values (years)
print(surface.params.rho)       # global SSVI correlation
print(surface.params.eta)       # curvature scale
print(surface.params.lamb)      # power-law exponent
```

## Error handling

```python
try:
    sigma = surface.iv(strike=0, maturity=30/365.25, F=64_000)
except ValueError as e:
    print(f"Invalid strike: {e}")

try:
    sigma = surface.iv(strike=70_000, maturity=-1.0, F=64_000)
except ValueError as e:
    print(f"Invalid maturity: {e}")
```

The `VolatilitySurface` raises `ValueError` for invalid inputs rather than
returning NaN or silently producing nonsense values.