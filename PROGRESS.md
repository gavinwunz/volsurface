# Build Progress

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
- [ ] Raw SVI parameterization w(k)
- [ ] Zeliade quasi-explicit (outer (m,sigma), inner (a,b,rho) constrained LLS)
- [ ] Vega / inverse-spread residual weighting
- [ ] docs/derivations/svi.md (Lee's moment formula, wing slope bound)
- [ ] pytest coverage

### M4 — No-arbitrage enforcement
- [ ] Butterfly g(k) >= 0 check across slices
- [ ] Calendar monotonicity of total variance
- [ ] g(k) plots per slice into reports/
- [ ] Breeden-Litzenberger density non-negativity cross-check
- [ ] Reject + log violated fits (never silently accept)
- [ ] hypothesis property-based tests

### M5 — Pricers + benchmark
- [ ] Black-Scholes
- [ ] CRR binomial
- [ ] Monte Carlo (antithetic + BS control variate)
- [ ] C++ hot path via pybind11
- [ ] Benchmark vs QuantLib (max abs error + wall time)
- [ ] pytest coverage

### M6 — Surface + reporting
- [ ] SSVI global fit (theta_t, phi(theta_t))
- [ ] 3D surface plot
- [ ] Skew term structure
- [ ] g(k) diagnostics report
- [ ] pytest coverage

## Session log
_(append newest at top: date/time, milestone touched, what changed, blockers)_

- 2026-08-10 12:00 UTC — M1 complete. Implemented Deribit JSON-RPC client (fetcher.py), timestamped parquet persistence (persistence.py), put-call parity forward extraction via OLS regression (forwards.py), and quote filters (filters.py). 32 pytest tests all passing. Created docs/derivations/ and reports/ directories.

- 2026-08-10 13:30 UTC — M2 complete. Black-76 pricing (black_scholes.py) with Newton-Raphson IV solver, Brent bracketing fallback, Brenner-Subrahmanyam seed, and unified `implied_volatility()` entry point. Fixed NR convergence ordering (sigma change before price diff) for 1e-8 accuracy on deep ITM. Fixed Brent bracket-widening bug (incorrect for-else with early break). Rewrote py_vollib benchmark test for vollib API compatibility. 48 pytest tests passing (80 total). Wrote docs/derivations/vega.md with full first-principles derivation.
