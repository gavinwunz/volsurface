# Numerical Optimizers and Tolerances Inventory

All numerical routines, their optimizers, tolerances, and configuration.
Updated for the VolFoundry v0.1.0 release.

## Central tolerances

Defined in `volfoundry/tolerances.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `PRICE_TOL` | `1e-12` | Price comparisons and IV convergence |
| `VOL_TOL` | `1e-8` | Volatility-level comparisons |
| `ARBITRAGE_TOL` | `-1e-12` | One-sided arbitrage checks ($g(k) \geq \text{tol}$) |
| `CALIBRATION_TOL` | `1e-8` | Default optimizer convergence tolerance |

Derived constants:

| Constant | Value | Purpose |
|----------|-------|---------|
| `EPSILON` | `1e-15` | Flooring denominators |
| `VEGA_FLOOR` | `1e-12` | Below this, NR is unsafe |
| `SIGMA_FLOOR` | `1e-12` | Minimum volatility |
| `A_FLOOR` | `1e-8` | Floor for SVI parameter $a$ |
| `B_FLOOR` | `1e-15` | Floor for SVI parameter $b$ |
| `RHO_TOL` | `0.999` | Hard clip for $|\rho|$ |
| `R2_FLOOR` | `1e-15` | Minimum total sum-of-squares for $R^2$ |

These are wired into all core modules (IV solver, SVI calibration, SSVI
calibration, arbitrage checks, Monte Carlo, forwards).

## Implied volatility inversion

`volfoundry/iv/black_scholes.py` — `implied_volatility()`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Method | Newton-Raphson + Brent fallback | NR with vega, Brent bracketing on small vega |
| NR tolerance | `VOL_TOL` = 1e-8 | Vol points |
| NR max iterations | 100 | |
| Brent tolerance | `PRICE_TOL` = 1e-12 | |
| Seed | Brenner-Subrahmanyam | |
| Vega floor | `VEGA_FLOOR` = 1e-12 | Below this → Brent fallback |

Edge cases handled (P7): prices below/above no-arbitrage bounds, zero/near-zero
maturity, deep ITM/OTM, tiny vega, NaN/Inf inputs, vectorised batch with
consistent error behaviour.

## SVI calibration

`volfoundry/svi/calibration.py` — `calibrate_svi_slice()`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Outer method | L-BFGS-B (scipy) | Two parameters: (m, sigma) |
| Inner method | Constrained linear least squares | Analytical at each outer iteration |
| Outer tolerance | `CALIBRATION_TOL` = 1e-8 | |
| Max iterations | 500 | |
| m bounds | [-5.0, 5.0] | |
| sigma bounds | [1e-6, 5.0] | |
| Regularisation | 1e-6 | Penalty for prior deviation |
| Minimum data points | 4 (configurable) | |
| Initial m | Weighted mean of k | |
| Initial sigma | 0.1 | |
| Deterministic? | Yes | L-BFGS-B with deterministic initial conditions |
| Multi-start? | Optional | Configurable via parameters |

**Diagnostics returned** (P7): outer_success, outer_message, per-parameter
bound-proximity warnings, objective value, RMSE, $R^2$, n_points.

## SSVI global calibration

`volfoundry/surface/calibration.py` — `calibrate_ssvi_surface()`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Method | L-BFGS-B (scipy) | 2 or 3 parameters |
| Stage 1 | ATM interpolation | Linear/nearest |
| Stage 2 | Global weighted sum of squares | (eta, lambda, optional rho) |
| Tolerance | `CALIBRATION_TOL` = 1e-8 | |
| Max iterations | 500 | |
| eta bounds | [1e-6, 20.0] | |
| lambda bounds | [0.0, 1.0] | |
| rho bounds | [-0.99, 0.99] | |
| Initial eta | 1.0 | |
| Initial lambda | 0.25 | |
| Deterministic? | Yes | |

**Lee bound enforced** (P6): $`\eta(1+|\rho|) \leq 2`$ is enforced as a hard
penalty in the objective.  Results that still violate it are rejected
(`success=False`).

**Calendar monotonicity** (P6): SSVI theta values are verified for monotonicity
in $T$.  Raw market estimates are preserved alongside any adjusted values.

## SVI parameter validation

`volfoundry/svi/parameterization.py` — `SviParams`

| Constraint | Range | Enforced? |
|------------|-------|-----------|
| $a > 0$ | $(0, \infty)$ | Yes — ValueError |
| $b \geq 0$ | $[0, \infty)$ | Yes |
| $-1 < \rho < 1$ | $(-1, 1)$ | Yes |
| $\sigma > 0$ | $(0, \infty)$ | Yes |
| Lee bound | $b(1+|\rho|) \leq 2$ | Checked via `satisfies_lee_bound()` |

## Butterfly arbitrage check

`volfoundry/arbitrage/checks.py` — `butterfly_is_arbitrage_free()`

| Parameter | Default | Notes |
|-----------|---------|-------|
| Tolerance | `ARBITRAGE_TOL` = -1e-12 | Negative values below tol are violations |
| k domain (builder) | `linspace(-3, 3, 501)` | Configurable via `SurfaceBuilder` |

## Calendar monotonicity check

| Parameter | Default | Notes |
|-----------|---------|-------|
| Tolerance | `ARBITRAGE_TOL` = -1e-12 | |

## Breeden-Litzenberger density

| Parameter | Default | Notes |
|-----------|---------|-------|
| Tolerance | `ARBITRAGE_TOL` = -1e-12 | |
| Min strikes | 3 | |
| FD method | Non-uniform 3-point | Proper quadratic fit |

## Monte Carlo

`volfoundry/pricers/monte_carlo.py`

| Parameter | Default | Notes |
|-----------|---------|-------|
| n_paths | 100,000 | |
| Antithetic | Yes | Always |
| Control variate | Yes (BS delta-hedged) | Optional |
| Seed | Explicit parameter | Uses `np.random.default_rng(seed)`, not global RNG |
| Result type | `MCResult` dataclass | Price, SE, CI bounds, n_paths, seed, control_variate flag |

## CRR binomial

`volfoundry/pricers/binomial.py`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Default N | 200 | Steps |
| Exercise | European, American | |

## Per-slice SVI diagnostics (P6)

Each slice returns `svi_status` with one of: `valid`, `converged_invalid`,
`did_not_converge`, `not_fitted`.  This distinguishes optimizer convergence
from arbitrage validity.

## Gap analysis (post-P7)

1. **Central tolerances** ✓ — Done (P7).
2. **Multi-start SVI** ✓ — Optional, configurable (P7).
3. **Optimizer diagnostics** ✓ — Objective, message, bound-proximity warnings (P7).
4. **Lee bound enforcement** ✓ — Hard penalty in SSVI objective (P6).
5. **SSVI constraints enforced during calibration** ✓ — Not merely post-hoc (P6).
6. **Calendar repair** ✓ — Raw and adjusted theta retained when repair applied (P6).
7. **MC result type** ✓ — `MCResult` dataclass with SE/CI (P7).