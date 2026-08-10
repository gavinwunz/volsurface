# Numerical Optimizers and Tolerances Inventory

All numerical routines, their optimizers, tolerances, and configuration.

## Implied volatility inversion

`volsurface/iv/black_scholes.py` — `implied_volatility()`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Method | Newton-Raphson + Brent fallback | NR with vega, Brent bracketing on small vega |
| NR tolerance | 1e-8 | Vol points |
| NR max iterations | 100 | |
| Brent tolerance | 1e-8 | |
| Seed | Brenner-Subrahmanyam | `sigma_guess = sqrt(2*abs(log(F/K) + r*T) / T)` |

## SVI calibration

`volsurface/svi/calibration.py` — `calibrate_svi_slice()`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Outer method | L-BFGS-B (scipy) | Two parameters: (m, sigma) |
| Inner method | Constrained linear least squares | numpy.linalg.lstsq |
| Outer tolerance | 1e-8 | `ftol` and `tol` |
| Max iterations | 500 | |
| m bounds | [-5.0, 5.0] | |
| sigma bounds | [1e-6, 5.0] | |
| Regularisation | 1e-6 | Penalty for prior deviation |
| Minimum data points | 4 | |
| Initial m | Weighted mean of k | |
| Initial sigma | 0.1 | |
| Deterministic? | Yes | L-BFGS-B with deterministic initial conditions |
| Multi-start? | No | Single initial guess |

## SSVI global calibration

`volsurface/surface/calibration.py` — `calibrate_ssvi_surface()`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Method | L-BFGS-B (scipy) | 2 or 3 parameters |
| Stage 1 | ATM interpolation | Linear/quadratic/nearest |
| Stage 2 | Global weighted sum of squares | eta, lambda (optional rho) |
| Tolerance | 1e-8 | `ftol` and `tol` |
| Max iterations | 500 | |
| eta bounds | [1e-6, 20.0] | |
| lambda bounds | [0.0, 1.0] | |
| rho bounds | [-0.99, 0.99] | |
| Initial eta | 1.0 | |
| Initial lambda | 0.25 | |
| Deterministic? | Yes | |

## SVI parameter validation

`volsurface/svi/parameterization.py` — `SviParams.__post_init__()`

| Constraint | Range | Enforced? |
|------------|-------|-----------|
| a > 0 | (0, inf) | Yes — ValueError |
| b >= 0 | [0, inf) | Yes |
| -1 < rho < 1 | (-1, 1) | Yes |
| sigma > 0 | (0, inf) | Yes |
| Lee bound | eta*(1+|rho|) <= 2 | Checked via `satisfies_lee_bound()` but NOT enforced |

## Butterfly arbitrage check

`volsurface/arbitrage/checks.py` — `butterfly_is_arbitrage_free()`

| Parameter | Default | Notes |
|-----------|---------|-------|
| Tolerance | -1e-12 | Negative values below tol are violations |
| k domain | linspace(-5, 5, 500) | Default when not specified |

## Calendar monotonicity check

| Parameter | Default | Notes |
|-----------|---------|-------|
| Tolerance | -1e-12 | For numerical fuzz |

## Breeden-Litzenberger density

| Parameter | Default | Notes |
|-----------|---------|-------|
| Tolerance | -1e-12 | |
| Min strikes | 3 | |
| FD method | Non-uniform 3-point | Proper quadratic fit |

## Monte Carlo

`volsurface/pricers/monte_carlo.py` — `mc_price()`

| Parameter | Default | Notes |
|-----------|---------|-------|
| n_paths | 100,000 | |
| Antithetic | Yes | Always |
| Control variate | Yes (BS delta-hedged) | Optional via `use_control_variate` |
| Second-level CV | Yes | F_T regression residual |
| Seed | None (user-specified) | Uses `np.random.default_rng(seed)` |
| SE estimation | Sample SD / sqrt(n) | |
| CI level | 1.96 × SE | 95% |

## CRR binomial

`volsurface/pricers/binomial.py`

| Parameter | Value | Notes |
|-----------|-------|-------|
| Default N | 200 | Steps |
| Exercise | European, American | |
| Greeks | Finite difference on tree | |

## Floating-point tolerances (scattered)

No central tolerance constants exist. Literal values used throughout:

| Literal | Where | Purpose |
|---------|-------|---------|
| `1e-15` | `butterfly_g()` | Avoid div by zero in w |
| `1e-12` | `monte_carlo.py` | Sigma/T/F/K <= 0 check → intrinsic value |
| `1e-20` | `monte_carlo.py` | var_f > 0 check for second-level CV |
| `1e-15` | `ssvi_total_variance` | Not used directly |
| `1e-8` | `_inner_lls()` | Floor for `a` parameter |
| `-1e-12` | multiple arbitrage checks | Butterfly/calendar/BL tolerance |
| `1e-15` | `build_vega_weights()` | Floor for vega weight |
| `1e-12` | `clip_params_to_valid()` | Floor for a/sigma |
| `0.999` | `clip_params_to_valid()` | rho clamp |

## Gap analysis

1. **No central tolerance constants.** Scattered `1e-12`, `1e-15`, etc.
   Plan §7 requires named constants (PRICE_TOL, VOL_TOL, ARBITRAGE_TOL,
   CALIBRATION_TOL).

2. **No multi-start SVI calibration.** Single deterministic initial guess.
   May miss the global minimum for pathological smiles.

3. **No explicit optimizer result capture beyond success/message.** 
   Missing: objective value history, iteration count, bound proximity
   diagnostics, gradient norm.

4. **Lee bound is checked but not enforced** in SVI calibration.
   SSVI does enforce via `satisfies_lee_bound()`.

5. **SSVI constraints partially enforced.** Parameter ranges are enforced
   but analytical sufficient conditions (plan §6) are not systematically
   applied during calibration — only checked post-hoc.

6. **No calendar repair mechanism.** If theta_t is not monotone in T,
   the calibration uses it as-is with no isotonic adjustment.