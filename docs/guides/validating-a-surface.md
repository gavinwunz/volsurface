# Validating a Surface

Every surface produced by `SurfaceBuilder` comes with a `ValidationReport` that
describes exactly which no-arbitrage conditions were checked, over what domain,
with what tolerances, and with what result.

## The validation report

```python
result = builder.fit(snapshot)
report = result.validation

print(report.is_valid)             # overall pass/fail
print(report.butterfly_passed)     # all g(k) >= tol?
print(report.calendar_passed)      # total variance monotonic in T?
print(report.density_passed)       # BL density >= 0?
```

## Analytical conditions

SSVI-specific constraints that are checked at the parameter level:

```python
for condition, passed in report.analytical_conditions.items():
    print(f"  {condition}: {'PASS' if passed else 'FAIL'}")

# Example output:
#   rho_domain: PASS       (-1 < rho < 1)
#   theta_positive: PASS    (all theta > 0)
#   lambda_domain: PASS     (0 <= lambda <= 1)
#   lee_bound: PASS         (eta*(1+|rho|) <= 2)
```

These are enforced during calibration — not merely inspected after the fact.

## Understanding failures

```python
if not report.is_valid:
    for slice_id, reasons in report.rejection_reasons.items():
        print(f"Slice {slice_id}:")
        for reason in reasons:
            print(f"  - {reason}")
```

Rejection reasons are human-readable strings like:

- `butterfly (min g=-0.0003)` — butterfly violation with the minimum g(k) value
- `BL density negative` — Breeden-Litzenberger cross-check failed
- `theta not positive` — an SSVI parameter constraint violated
- `Lee bound violation (eta*(1+|rho|) = 2.3415)` — Lee moment formula exceeded
- `3 calendar violation pair(s)` — total variance decreased with maturity

## Evaluation domain

Every report records exactly what was tested:

```python
print(report.evaluation_domain)
# {'k_min': -3.0, 'k_max': 3.0, 'n_k': 501, 'n_slices': 6}
```

This means butterfly checks ran on $k \in [-3, 3]$ at 501 points over 6
expiry slices.  Nothing is claimed about behaviour outside this domain or
between grid points.

## Tolerances

```python
print(report.tolerances)
# {'butterfly_tol': -1e-12, 'calendar_tol': -1e-12}
```

The negative tolerance means $g(k) \geq -10^{-12}$, i.e. machine-epsilon-level
violations are tolerated but genuine violations are flagged.

## Per-slice detail

```python
for s in report.per_slice:
    print(f"{s['slice_id']}  T={s['T']:.4f}  "
          f"butterfly={'OK' if s['butterfly_passed'] else 'FAIL'}  "
          f"min_g={s['butterfly_min_g']:.4e}  "
          f"BL={'OK' if s['bl_passed'] else 'FAIL'}")
```

## Distinguishing failure types

The `calibration_status` field helps distinguish different problems:

| Status | Meaning |
|--------|---------|
| `converged` | Optimizer converged + all validation checks passed |
| `converged_invalid` | Optimizer converged but the result fails one or more checks |
| `did_not_converge` | Optimizer did not converge; surface may be nonsense |
| `failed` | Catastrophic failure (no surface at all) |

### Optimizer failure ≠ arbitrage failure

When `calibration_status == "did_not_converge"`, check:

```python
print(result.optimizer_diagnostics)
# {'success': False, 'message': '...'}
print(result.global_diagnostics)
# Look at the per-expiry svi_status fields
```

An optimizer failure means the calibration itself didn't work — this is
different from an arbitrage violation (where the optimizer succeeded but
the result is invalid).

### Strict mode exception

```python
from volfoundry import ArbitrageViolationError

try:
    result = builder.fit(snapshot, validation="strict")
except ArbitrageViolationError as e:
    # e contains the rejected slices and reasons
    print(e)
```

The exception message includes the failing slices and reasons so you can
diagnose without needing the (non-existent) result object.

## What validation does NOT prove

- **Not a mathematical proof**: Passing on a grid of 501 $k$-points does not
  guarantee no arbitrage on the entire real line.
- **Not a trading guarantee**: No-arbitrage conditions are model-internal.
  Real markets have bid-ask spreads, funding costs, and execution constraints.
- **Model assumptions still apply**: SSVI is a parameterization — it smooths
  and extrapolates.  The model may be valid while market prices admit arbitrage
  outside the model.

## Programmatic use

The low-level validation functions are independently callable:

```python
from volfoundry.arbitrage.checks import (
    butterfly_g, butterfly_is_arbitrage_free,
    calendar_monotonicity, validate_surface,
)
import numpy as np

k = np.linspace(-3, 3, 1001)
g = butterfly_g(k, svi_params, T=0.25)
valid = butterfly_is_arbitrage_free(k, svi_params, T=0.25, tol=-1e-12)
```

These return typed result objects, not loose dictionaries.