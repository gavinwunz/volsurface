# Forward Price Extraction

## Definition

The **forward price** $`F`$ for a given expiry is the agreed-upon price today for
delivery of the underlying at time $`T`$.  In option pricing, $`F`$ anchors the
moneyness scale — every strike is measured relative to $`F`$ via
$`k = \log(K/F)`$.

## Assumptions

- European option prices are observed (C for calls, P for puts).
- Put-call parity holds:
  ```math
  C - P = e^{-rT} (F - K)
  ```
- The discount factor $`e^{-rT}`$ (or equivalently the rate $`r`$) is constant
  or separable from the forward extraction.

## Formula

For a given expiry, VolFoundry regresses the observed $(C - P)$ against $K$:

```math
C_i - P_i = e^{-rT} F - e^{-rT} K_i
```

This is an **OLS regression** of the form $y = \alpha + \beta x$ where:

- $`y = C_i - P_i`$ (observed call-put mid-price differences)
- $`x = K_i`$ (strikes)
- $`\beta = -e^{-rT}`$ → recover $r$ from the slope
- $`\alpha = e^{-rT} F`$ → recover $F = \alpha / (-\beta)$

The regression approach:

1. Uses **all paired strikes** (where both a call and put trade), reducing
   sensitivity to individual stale quotes.
2. Does **not** assume a constant risk-free rate — the implied $r$ can vary
   by expiry.
3. Naturally handles illiquid strikes by their small influence on the regression
   line.

## Implementation

VolFoundry implements forward extraction in `volfoundry.data.forwards`:

- `compute_time_to_expiry(expiry_dt, reference_dt)` — $T$ in years.
- `extract_forwards(df, reference_time)` — runs the OLS for every expiry,
  returning a dict of `ForwardResult` dataclasses keyed by expiry.

### `ForwardResult`

| Field | Type | Description |
|-------|------|-------------|
| `F` | float | Extracted forward price |
| `r` | float | Implied discount rate |
| `T` | float | Time to expiry in years |
| `expiry` | datetime | Expiry datetime |
| `r2` | float | $R^2$ of the regression |
| `n_pairs` | int | Number of paired call-put quotes used |
| `diagnostics` | dict | Parameter estimates and standard errors |

## Numerical caveats

- **Minimum pairs**: At least 2 paired quotes are needed for regression.  An
  expiry with only a single strike cannot produce a forward estimate.
- **Stale/illiquid quotes**: A low $R^2$ or a small number of pairs is a warning
  signal.  The diagnostics are passed through to `SurfaceBuilder` and available
  for inspection.
- **Zero or negative slope**: If $e^{-rT} \leq 0$ from the regression (pathological
  case), the extraction is invalid.  VolFoundry raises an error rather than
  silently returning a nonsensical forward.
- **Sparse expiries**: If most strikes for a given expiry are calls-only or
  puts-only, forward extraction may be unreliable or impossible.
- **Discount rate interpretation**: The implied $r$ from the regression may differ
  from a risk-free rate due to funding spreads, borrowing costs, or data noise.
  It should be interpreted as an effective discount rate, not a macro-economic
  rate.

## References

- Hull, J. C. (2022). *Options, Futures, and Other Derivatives* (11th ed.).
  Pearson.  Chapter 11: "Properties of stock options."

## See also

- [VolFoundry quickstart](../getting-started/quickstart.md)
- [Deribit data guide](../guides/deribit.md)