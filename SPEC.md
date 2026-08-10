# Project: Arbitrage-Free Implied Volatility Surface

## Deliverable
Python package `volsurface/` + C++ hot path, reproducible, tested, documented.

## Milestones (complete in order, commit after each)

### M1 — Data layer
- Pull option chains (Deribit public API for BTC/ETH; no auth needed).
- Persist raw snapshots to parquet with timestamps. Never overwrite.
- Extract forwards per expiry via put-call parity regression:
  C - P = e^{-rT}(F - K). Do NOT assume constant r or zero dividends.
- Filter: drop quotes with zero bid, crossed markets, or < 2 days to expiry.

### M2 — Implied vol inversion
- Newton-Raphson on vega, seeded with Brenner-Subrahmanyam.
- Brent bracketing fallback when |vega| < tol (deep ITM/OTM wings).
- Target: correct to 1e-8 vol points. Benchmark vs py_vollib.
- Write docs/derivations/vega.md deriving vega from BS first principles.

### M3 — Raw SVI calibration (the core)
- w(k) = a + b[rho(k-m) + sqrt((k-m)^2 + sigma^2)], k = log(K/F).
- Implement Zeliade quasi-explicit method: outer 2-param search over
  (m, sigma), inner (a, b, rho) as constrained linear least squares.
- Weight residuals by vega or inverse bid-ask spread, NOT unweighted mids.
- Write docs/derivations/svi.md explaining why wings are linear
  (Lee's moment formula bounds slope at 2).

### M4 — No-arbitrage enforcement (do not skip)
- Butterfly: verify g(k) >= 0 across all slices, where
  g(k) = (1 - k w'/(2w))^2 - (w'^2/4)(1/w + 1/4) + w''/2
- Calendar: verify total variance non-decreasing in T at fixed k.
- Plot g(k) per slice into reports/. If violated, reject the fit — log it,
  do not silently accept.
- Cross-check: Breeden-Litzenberger density e^{rT} d2C/dK2 must be >= 0.

### M5 — Pricers + benchmark
- Black-Scholes, CRR binomial, Monte Carlo with antithetic variates and
  BS control variate. C++ hot path with pybind11.
- Benchmark all three against QuantLib: report max abs error and wall time.

### M6 — Surface + reporting
- SSVI global fit tying slices via theta_t and phi(theta_t).
- 3D surface plot, skew term structure, g(k) diagnostics.

## Hard rules
- Every module gets pytest coverage. Arbitrage checks get property-based
  tests (hypothesis) over randomized parameter draws.
- No look-ahead: only use data timestamped <= the snapshot time.
- Report failures honestly in reports/. A rejected fit is a result.
- Commit granular, conventional-commit messages.
- For every non-obvious formula, write the derivation into
  docs/derivations/ in full, with the assumptions stated.
