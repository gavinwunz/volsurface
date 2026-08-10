# Public API Inventory

Generated from the `volfoundry` package at commit `27f5949`. All symbols
accessible from each top-level subpackage.

## `volfoundry.data` — market data, persistence, cleaning, forwards

Exported via `__init__.py`.

| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| `DeribitPublicClient` | class | `data.fetcher` | Stateless Deribit REST JSON-RPC client |
| `OptionQuote` | dataclass | `data.fetcher` | Cleaned option quote with all fields |
| `Snapshot` | dataclass | `data.fetcher` | Full option-chain snapshot (currency, timestamp, quotes) |
| `fetch_snapshot` | function | `data.fetcher` | Convenience wrapper for single-snapshot fetch |
| `clean_quotes` | function | `data.filters` | Run all quote filters, return cleaned DataFrame + diagnostics |
| `filter_crossed` | function | `data.filters` | Remove crossed bid-ask quotes |
| `filter_min_days_to_expiry` | function | `data.filters` | Remove quotes near expiry |
| `filter_zero_bid_ask` | function | `data.filters` | Remove quotes with zero bid or ask |
| `ForwardResult` | dataclass | `data.forwards` | Forward extraction result (F, r, diagnostics) |
| `compute_time_to_expiry` | function | `data.forwards` | Time to expiry in years from datetime |
| `extract_forwards` | function | `data.forwards` | Put-call parity OLS forward extraction |
| `list_snapshots` | function | `data.persistence` | List parquet snapshots on disk |
| `load_snapshot` | function | `data.persistence` | Load most recent snapshot for currency |
| `read_snapshot` | function | `data.persistence` | Read a specific snapshot file |
| `write_snapshot` | function | `data.persistence` | Persist snapshot to timestamped parquet |

## `volfoundry.iv` — implied volatility and Black-76 pricing

`__init__.py` is empty (no re-exports). Users import from `volfoundry.iv.black_scholes`.

| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| `OptionType` | enum | `iv.black_scholes` | CALL or PUT |
| `black76_price` | function | `iv.black_scholes` | Black-76 forward-price formula |
| `black76_vega` | function | `iv.black_scholes` | Black-76 vega (derivative w.r.t. sigma) |
| `implied_volatility` | function | `iv.black_scholes` | Newton-Raphson + Brent IV inversion |
| `norm_cdf` | function | `iv.black_scholes` | Standard normal CDF |
| `norm_pdf` | function | `iv.black_scholes` | Standard normal PDF |
| `brenner_subrahmanyam_seed` | function | `iv.black_scholes` | Approximate IV seed |

## `volfoundry.pricers` — pricing engines

Fully exported via `__init__.py` with `__all__`.

| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| `OptionType` | enum | re-export | CALL / PUT |
| `black76_price` | function | `pricers.black_scholes` | Black-76 analytical price |
| `black76_delta` | function | `pricers.black_scholes` | Discounted delta |
| `black76_gamma` | function | `pricers.black_scholes` | Gamma |
| `black76_vega` | function | `pricers.black_scholes` | Vega |
| `black76_theta` | function | `pricers.black_scholes` | Theta |
| `black76_rho` | function | `pricers.black_scholes` | Rho |
| `black76_all_greeks` | function | `pricers.black_scholes` | All Greeks in one call |
| `price_and_greeks_vectorized` | function | `pricers.black_scholes` | Vectorised price + Greeks |
| `parity_check_call` | function | `pricers.black_scholes` | Put-call parity call from put |
| `parity_check_put` | function | `pricers.black_scholes` | Put-call parity put from call |
| `norm_cdf` | function | `pricers.black_scholes` | Standard normal CDF |
| `norm_pdf` | function | `pricers.black_scholes` | Standard normal PDF |
| `crr_price` | function | `pricers.binomial` | CRR tree price (European + American) |
| `crr_greeks` | function | `pricers.binomial` | CRR tree Greeks (FD) |
| `mc_price` | function | `pricers.monte_carlo` | MC with antithetic + control variate |
| `mc_price_with_confidence` | function | `pricers.monte_carlo` | MC with 95% CI |
| `_HAS_CPP` | bool | `pricers.__init__` | Whether C++ extension loaded |

## `volfoundry.svi` — SVI parameterization and calibration

`__init__.py` is empty.

| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| `SviParams` | dataclass | `svi.parameterization` | SVI parameters (a,b,rho,m,sigma) with validation |
| `svi_total_variance` | function | `svi.parameterization` | w(k) total variance |
| `svi_implied_vol` | function | `svi.parameterization` | sigma_IV(k) = sqrt(w(k)/T) |
| `svi_first_derivative` | function | `svi.parameterization` | w'(k) |
| `svi_second_derivative` | function | `svi.parameterization` | w''(k) |
| `svi_min_total_variance` | function | `svi.parameterization` | Minimum w(k) analytical formula |
| `clip_params_to_valid` | function | `svi.parameterization` | Project parameters to valid domain |
| `SviCalibrationResult` | dataclass | `svi.calibration` | Slice calibration result with diagnostics |
| `calibrate_svi_slice` | function | `svi.calibration` | Zeliade quasi-explicit calibration |
| `build_vega_weights` | function | `svi.calibration` | Vega-proportional observation weights |
| `build_inverse_spread_weights` | function | `svi.calibration` | Inverse bid-ask spread weights |

## `volfoundry.surface` — SSVI surface construction

`__init__.py` is empty.

| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| `SsviParams` | dataclass | `surface.ssvi` | SSVI global parameters (rho, eta, lamb, theta_grid) |
| `ssvi_total_variance` | function | `surface.ssvi` | w(k, theta) for a single slice |
| `ssvi_implied_vol` | function | `surface.ssvi` | sigma_IV(k, theta) for a single slice |
| `ssvi_total_variance_surface` | function | `surface.ssvi` | Full w(k, T) surface matrix |
| `ssvi_to_raw_svi` | function | `surface.ssvi` | Map SSVI slice → equivalent raw SVI params |
| `ssvi_to_raw_svi_surface` | function | `surface.ssvi` | Full surface to raw SVI list |
| `SsviCalibrationResult` | dataclass | `surface.calibration` | Global SSVI calibration result |
| `calibrate_ssvi_surface` | function | `surface.calibration` | Two-stage global SSVI fit |
| `extract_atm_variance` | function | `surface.calibration` | Extract theta from k=0 interpolation |
| `extract_theta_grid` | function | `surface.calibration` | Extract theta per expiry slice |
| `plot_surface_3d` | function | `surface.plotting` | 3D IV surface plot |
| `plot_skew_term_structure` | function | `surface.plotting` | ATM skew vs expiry |
| `plot_iv_smiles` | function | `surface.plotting` | IV smile cross-section overlay |
| `save_surface_diagnostics` | function | `surface.plotting` | Write full diagnostic PNG set |

## `volfoundry.arbitrage` — no-arbitrage validation

`__init__.py` is empty.

| Symbol | Kind | Module | Description |
|--------|------|--------|-------------|
| `butterfly_g` | function | `arbitrage.checks` | Compute g(k) butterfly function |
| `butterfly_is_arbitrage_free` | function | `arbitrage.checks` | Check g(k) >= tol over domain |
| `find_butterfly_violations` | function | `arbitrage.checks` | Find k where g(k) < tol |
| `calendar_monotonicity` | function | `arbitrage.checks` | Check w(k,T) non-decreasing in T |
| `find_calendar_violations` | function | `arbitrage.checks` | Find violating maturity pairs |
| `breeden_litzenberger_density` | function | `arbitrage.checks` | FD risk-neutral density |
| `breeden_litzenberger_is_nonnegative` | function | `arbitrage.checks` | Check q(K) >= 0 |
| `ArbitrageCheckResult` | dataclass | `arbitrage.checks` | Per-slice check result |
| `check_slice_arbitrage` | function | `arbitrage.checks` | Run all checks on one slice |
| `SliceValidationReport` | dataclass | `arbitrage.checks` | Multi-slice validation report |
| `validate_surface` | function | `arbitrage.checks` | Validate full surface |
| `plot_butterfly_g` | function | `arbitrage.plotting` | g(k) diagnostic plot |
| `write_validation_report` | function | `arbitrage.plotting` | Human-readable validation text |
| `save_arbitrage_diagnostics` | function | `arbitrage.plotting` | Full diagnostic output |

## Root `volfoundry`

| Symbol | Kind | Description |
|--------|------|-------------|
| `__version__` | str | `"0.0.1"` |

## Total count

- 55 public symbols across 6 subpackages
- ~15 dataclass/result types
- ~40 public functions
- 1 public enum type (`OptionType`)