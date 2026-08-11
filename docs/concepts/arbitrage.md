# Arbitrage-Free Surface Validation

## Definition

A volatility surface is **free of static arbitrage** when the call prices it
implies satisfy:

1. **Butterfly arbitrage**: The implied risk-neutral density is everywhere
   non-negative.  No positive portfolio of butterfly spreads has a negative price.
2. **Calendar arbitrage**: Total implied variance $`w(k, T)`$ is non-decreasing
   in $`T`$ at every $`k`$.  A longer-dated option cannot be cheaper than a
   shorter-dated one for the same moneyness.

## Assumptions

- European exercise (no early-exercise arbitrage to consider).
- No dividends or discrete corporate actions.
- Continuous, frictionless markets with no bid-ask spread in the arbitrage
  arguments themselves (though spreads are used in calibration weighting).

## Formulas

### Butterfly condition — $`g(k)`$

For a total variance parameterisation $`w(k)`$ on a single expiry slice, the
**Gatheral butterfly function** is:

```math
g(k) = \left(1 - \frac{k w'(k)}{2 w(k)}\right)^2
       - \frac{w'(k)^2}{4}\left(\frac{1}{w(k)} + \frac{1}{4}\right)
       + \frac{w''(k)}{2}
```

A necessary condition for no butterfly arbitrage is:

```math
g(k) \geq 0 \quad \forall k \in \mathbb{R}
```

VolFoundry checks this on a discrete grid over a configurable log-moneyness range
(default $`k \in [-3, 3]`$, 501 points).

### Calendar condition

For two maturities $`T_1 < T_2`$ and the same $`k`$:

```math
w(k, T_1) \leq w(k, T_2)
```

This is checked at every grid point.  A single violation pair is flagged.

For the SSVI surface with the power-law curvature function, the calendar
condition is **analytically sufficient** when $`\lambda \in [0, 1/2]`$ and
$`\eta(1 + |\rho|) \leq 2`$ is satisfied.

### Breeden–Litzenberger density cross-check

As an independent diagnostic, the risk-neutral density is approximated via
finite differences of call prices:

```math
q(K) = e^{rT} \left.\frac{\partial^2 C}{\partial K^2}\right|_{K}
```

Non-negativity of $`q(K)`$ is a necessary condition for no butterfly arbitrage.
VolFoundry uses a non-uniform 3-point finite-difference formula suitable for
log-spaced strike grids.

**Important**: The BL density check is a **cross-check**, not the primary
arbitrage proof.  It is sensitive to strike spacing, interpolation, and
numerical differentiation error.

## Implementation

VolFoundry implements arbitrage checks in `volfoundry.arbitrage.checks`:

| Function | Purpose |
|----------|---------|
| `butterfly_g(k, params, T)` | Compute $`g(k)`$ |
| `butterfly_is_arbitrage_free(k, params, T, tol)` | Check $`g(k) \geq \text{tol}`$ |
| `find_butterfly_violations(k, params, T, tol)` | Locate violating $`k`$ |
| `calendar_monotonicity(k, Ts, ws)` | Check monotonicity |
| `find_calendar_violations(k, Ts, ws)` | Find violating maturity pairs |
| `breeden_litzenberger_density(K, Ts, C, F, r)` | Compute $`q(K)`$ |
| `breeden_litzenberger_is_nonnegative(...)` | Check $`q \geq 0`$ |
| `check_slice_arbitrage(...)` | Run all checks on one slice |
| `validate_surface(slices, k_grid)` | Run all checks on full surface → `SliceValidationReport` |

### Validation modes

```python
# Report mode — always returns a result, even if invalid
result = builder.fit(snapshot, validation="report")
# result.validation.is_valid may be False — inspect why

# Strict mode — raises ArbitrageViolationError on failure
result = builder.fit(snapshot, validation="strict")
```

### What every report records

```python
report = result.validation
print(report.evaluation_domain)   # {"k_min": -3.0, "k_max": 3.0, "n_k": 501, ...}
print(report.tolerances)          # {"butterfly_tol": -1e-12, "calendar_tol": -1e-12}
print(report.analytical_conditions)  # {"rho_domain": True, "lee_bound": True, ...}
print(report.rejection_reasons)   # per-slice failure reasons
print(report.per_slice)           # per-slice butterfly min-g, RMSE, ...
```

## Numerical caveats

- **Finite grid**: Numerical checks on a discrete $`k`$-grid prove nothing about
  behaviour between grid points or outside the grid range.  The grid range and
  resolution are always recorded.
- **Tolerance**: A negative tolerance (`ARBITRAGE_TOL = -1e-12`) allows
  machine-epsilon violations while catching genuine arbitrage breaks.  Changing
  the tolerance changes what's flagged — tolerances are in the report metadata.
- **BL density**: Finite-difference estimates are sensitive to strike spacing
  and interpolation.  The density check is an independent cross-check; its
  failure alongside a butterfly pass suggests the resolution needs attention.
- **Calendar sufficiency**: The analytical proofs for the SSVI power-law form
  cover $`\lambda \in [0, 1/2]`$.  Beyond that range, calendar absence is
  verified numerically and should be treated as diagnostic, not proof.
- **Not a mathematical guarantee**: VolFoundry does not and cannot claim that
  passing its numerical checks proves the surface is arbitrage-free over the
  entire real line.  The checks are explicit, inspectable diagnostics.

## References

- Gatheral, J. and Jacquier, A. (2014). "Arbitrage-free SVI volatility surfaces."
  *Quantitative Finance*, 14(1), 59–71.
- Breeden, D. T. and Litzenberger, R. H. (1978). "Prices of state-contingent
  claims implicit in option prices." *Journal of Business*, 51(4), 621–651.
- Lee, R. W. (2004). "The moment formula for implied volatility at extreme
  strikes." *Mathematical Finance*, 14(3), 469–480.

## See also

- [Arbitrage derivations](../derivations/arbitrage.md)
- [SVI parameterization](./svi.md)
- [SSVI surface](./ssvi.md)