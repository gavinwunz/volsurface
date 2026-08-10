# Build Progress

> **Phase 1 (M1–M6) is complete.** Production upgrade work (VolFoundry rename,
> packaging, release) now tracks in `VOLFOUNDRY_PROGRESS.md`, spec in
> `VOLFOUNDRY_PRODUCTION_PLAN.md`. This file is the historical phase-1 record —
> do not regress it.

This file is the single source of truth for build state. Update it after every
work session: check off completed items, note what's in flight, record blockers.

## Status legend
- [ ] not started
- [~] in progress
- [x] complete (code + tests passing + committed + pushed)

## Milestones

### M1 — Data layer
- [x] Deribit public API client (BTC/ETH option chains)
- [x] Raw snapshot persistence to parquet (timestamped, never overwrite)
- [x] Forward extraction via put-call parity regression C - P = e^{-rT}(F - K)
- [x] Quote filters (zero bid, crossed, < 2 days to expiry)
- [x] pytest coverage (32 tests)

### M2 — Implied vol inversion
- [x] Newton-Raphson on vega, Brenner-Subrahmanyam seed
- [x] Brent bracketing fallback for small |vega|
- [x] 1e-8 accuracy, benchmark vs py_vollib
- [x] docs/derivations/vega.md
- [x] pytest coverage (48 tests)

### M3 — Raw SVI calibration
- [x] Raw SVI parameterization w(k)
- [x] Zeliade quasi-explicit (outer (m,sigma), inner (a,b,rho) constrained LLS)
- [x] Vega / inverse-spread residual weighting
- [x] docs/derivations/svi.md (Lee's moment formula, wing slope bound)
- [x] pytest coverage (37 tests)

### M4 — No-arbitrage enforcement
- [x] Butterfly g(k) >= 0 check across slices
- [x] Calendar monotonicity of total variance
- [x] g(k) plots per slice into reports/
- [x] Breeden-Litzenberger density non-negativity cross-check
- [x] Reject + log violated fits (never silently accept)
- [x] hypothesis property-based tests

### M5 — Pricers + benchmark
- [x] Black-Scholes
- [x] CRR binomial
- [x] Monte Carlo (antithetic + BS control variate)
- [x] C++ hot path via pybind11
- [x] Benchmark vs QuantLib (max abs error + wall time)
- [x] pytest coverage

### M6 — Surface + reporting
- [x] SSVI global fit (theta_t, phi(theta_t))
- [x] 3D surface plot
- [x] Skew term structure
- [x] g(k) diagnostics report
- [x] pytest coverage

## Session log
_(append newest at top: date/time, milestone touched, what changed, blockers)_

- 2026-08-10 20:15 UTC — M4 bugfix. Fixed `test_g_symmetric_for_rho_zero` hypothesis property-based test: g(k) symmetry only holds when both rho=0 AND m=0 exactly, because term1 = (1 - k*w'/(2w))^2 contains an explicit k factor that breaks symmetry about k=m when m ≠ 0. Forced m=0 in the derived test params (rather than relying on near-zero assume filter). All 319 tests passing.

- 2026-08-10 20:00 UTC — M6 complete. SSVI global fit (Gatheral-Jacquier 2014) with two-stage calibration: ATM theta_t extraction from market data, then global (eta, lambda) fit with optional fixed rho. Surface visualisation suite: 3D implied vol surface plot (matplotlib 3D), skew term structure (ATM dsigma/dk vs expiry), g(k) butterfly diagnostics grid, IV smile cross-section plot, and human-readable surface validation report writer. 83 new tests (56 surface SSVI/calibration, 27 plotting) — 319 total, all passing. Full SSVI->raw SVI mapping, calendar-no-arbitrage check, Lee bound enforcement. Wrote docs/derivations/ssvi.md with full derivations of SSVI functional form, wing asymptotics, raw SVI equivalence mapping, calendar-free condition proof sketch, and Lee bound constraint.

- 2026-08-10 18:00 UTC — M5 complete. Black-Scholes full Greeks (delta, gamma, vega, theta, rho as discounted sensitivities), CRR binomial tree (European + American, tree-based FD Greeks), Monte Carlo with antithetic variates and BS delta-hedged control variate (two-level: delta hedge + residual F_T regression). C++ hot path via pybind11 (vectorised price + all Greeks in one pass, ~3× faster than QuantLib). Benchmark: all three pricers validated against QuantLib BlackCalculator to <1e-10 on price and <1e-9 on vega; CRR converges to <0.01 with N=2000; MC within 3 SE of analytical. 88 pricer tests (236 total, all passing). Pricers __init__.py exposes clean public API with graceful C++ fallback.

- 2026-08-10 17:30 UTC — M4 complete. Butterfly g(k) check, calendar monotonicity, Breeden-Litzenberger density cross-check using proper non-uniform 3-point finite-difference formula, full slice/surface validation with rejection logging. 31 arbitrage tests (including hypothesis property-based tests over randomized SVI parameter draws). g(k) plotting to reports/ via matplotlib Agg backend, human-readable validation report writer. Fixed BL density import (black76_price + OptionType vs nonexistent black76_call), corrected non-uniform FD formula (previous h_avg approximation was inaccurate for log-spaced grids), fixed hypothesis symmetry test (g(k) symmetric around k=0 only when both rho=0 AND m=0), replaced false property "g(k) non-negative near ATM for all valid SVI" with test that g(k) is well-behaved (finite, bounded magnitude). Wrote docs/derivations/arbitrage.md with full derivations of butterfly g(k), calendar monotonicity, and BL density formulas including limit analysis.

- 2026-08-10 12:00 UTC — M1 complete. Implemented Deribit JSON-RPC client (fetcher.py), timestamped parquet persistence (persistence.py), put-call parity forward extraction via OLS regression (forwards.py), and quote filters (filters.py). 32 pytest tests all passing. Created docs/derivations/ and reports/ directories.

- 2026-08-10 15:00 UTC — M3 complete. SVI parameterization (SviParams dataclass, svi_total_variance, svi_implied_vol, first/second derivatives, Lee moment formula check, clip_params_to_valid). Zeliade quasi-explicit calibration (inner constrained LLS, outer 2-param optimisation over (m, sigma) via scipy L-BFGS-B). Vega and inverse-spread weighting functions. Fixed bug in inner LLS where a >= b*sigma*sqrt(1-rho²) was incorrectly enforced — the minimum total variance formula is a sum, not a difference, so a>0 alone guarantees positivity. Fixed test discretization artifact in wpp_max_at_k_equals_m (grid missed k=m by ~0.005). 37 tests passing, 117 total across all modules. Wrote docs/derivations/svi.md with full derivations of w'(k), w''(k), wing slopes, Lee bound, minimum total variance.

- 2026-08-10 13:30 UTC — M2 complete. Black-76 pricing (black_scholes.py) with Newton-Raphson IV solver, Brent bracketing fallback, Brenner-Subrahmanyam seed, and unified `implied_volatility()` entry point. Fixed NR convergence ordering (sigma change before price diff) for 1e-8 accuracy on deep ITM. Fixed Brent bracket-widening bug (incorrect for-else with early break). Rewrote py_vollib benchmark test for vollib API compatibility. 48 pytest tests passing (80 total). Wrote docs/derivations/vega.md with full first-principles derivation.