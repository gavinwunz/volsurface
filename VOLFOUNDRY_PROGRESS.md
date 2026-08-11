# VolFoundry Progress (Phase 2)

Single source of truth for the VolFoundry production upgrade. Full spec:
`VOLFOUNDRY_PRODUCTION_PLAN.md`. Phase 1 (M1–M6 quant core) is recorded in
`PROGRESS.md` and is complete; do not regress it.

Update after every work session: check off completed items, record blockers,
append a dated line (newest first) to the session log.

## Status legend
- [ ] not started
- [~] in progress
- [x] complete (code + tests passing + committed + pushed)
- [H] blocked on a human action (tracked in `HUMAN_ACTIONS.md`)

## Release-blocking milestones (execute in this order — plan §38)

### P0 — Freeze & audit current behavior
- [x] Record baseline in `docs/development/baseline.md` (commit SHA, Python, OS, test counts, build status)
- [x] Inventories: `api_inventory.md`, `network_inventory.md`, `numerics_inventory.md`
- [x] Grep sweep for volsurface / 0.0.1 / arbitrage-free / guarantee / print( / TODO / FIXME
- [x] Ensure every stochastic test has a controlled seed

### P1 — Rename volsurface → volfoundry
- [x] Move to `src/volfoundry/` layout (data/ iv/ svi/ arbitrage/ pricers/ surface/ cli/)
- [x] Mechanical import migration `volsurface.*` → `volfoundry.*` (src, tests, examples, docs, cpp, scripts)
- [x] `CHANGELOG.md` migration note + `docs/migration/volsurface-to-volfoundry.md`
- [x] No `volsurface` compatibility shim shipped
- [x] `python -c "import volfoundry; print(volfoundry.__version__)"` works after editable install

### P2 — Modernize packaging
- [x] `pyproject.toml`: name volfoundry, requires-python >=3.10, MIT, authors, URLs, classifiers, keywords
- [x] Extras: [plot] [dev] [docs] [benchmark]; benchmark-only deps (QuantLib/py_vollib) out of base
- [x] One canonical version source; `__version__` matches build metadata; bump to 0.1.0
- [x] `python -m build` + `twine check dist/*`; wheel AND sdist install in clean venvs
- [x] Base install needs no C++ compiler, no QuantLib/py_vollib/pytest/hypothesis

### P3 — Small stable public API
- [x] High-level `DeribitClient`, `SurfaceBuilder`, `VolatilitySurface`, `ValidationReport`
- [x] Structured result objects (`SurfaceFitResult`, `ValidationReport`, `MarketSnapshot`/`OptionChain`)
- [x] Offline path (`fit_dataframe`) — no network needed for calibration
- [x] Small `__init__.py` with `__all__`; low-level modules still importable
- [x] Main workflow achievable in <~15 lines without private imports

### P4 — Real error model
- [x] `exceptions.py` taxonomy (VolFoundryError → Data/Pricing/Calibration/Config, ArbitrageViolationError, etc.)
- [x] Preserve `__cause__` on wrap; exception chaining test passes; library raises, does not `sys.exit`

### P5 — Reliable market data
- [x] Hardened Deribit HTTP: timeouts, reusable session, UA w/ version, bounded retries + backoff+jitter, 429/5xx only
- [x] Typed quote schema + validation; JSON-RPC error handling; never empty-success on API error
- [x] Quote-cleaning diagnostics (per-reason counts + machine-readable reasons)
- [x] Atomic snapshot writes; never overwrite historical snapshots; reproducible metadata
- [x] Offline fixture tests; live tests marked `@pytest.mark.live`

### P6 — Strict no-arbitrage construction contract  *(most important quant change)*
- [x] `validation="report"` (research fit, may be invalid but clearly flagged) vs `validation="strict"` (raises `ArbitrageViolationError`)
- [x] Enforce SSVI analytical conditions during/for parameter acceptance (not post-hoc print)
- [x] rho domain, positive theta, valid eta/lambda, monotone ATM total variance (or documented repair w/ raw+adjusted retained)
- [x] Per-slice SVI fit status; distinguish converged vs valid; g(k) min + domain exposed
- [x] Every numerical arbitrage report states domain + tolerance; BL density as cross-check only
- [x] Acceptance tests (plan §9): invalid params detected, calendar-crossing fails strict, strict refuses invalid, report keeps invalid, valid SSVI passes, optimizer≠arbitrage failure, tolerance in metadata

### P7 — Numerical robustness & reproducibility
- [x] IV inversion edge cases (below/above bounds, ~0 maturity, deep ITM/OTM, tiny vega, NaN/Inf) → consistent errors
- [x] SVI: deterministic init, multi-start, optimizer diagnostics, bound-proximity warnings, degenerate smiles
- [x] Monte Carlo: `numpy.random.Generator`, seeds, standard error/CI, seeded regression tests
- [x] Central named tolerances (PRICE_TOL/VOL_TOL/ARBITRAGE_TOL/CALIBRATION_TOL)

### P8 — Test architecture
- [x] tests/{unit,property,integration,regression,live}; markers unit/integration/property/regression/live/slow/benchmark registered
- [x] Golden/regression fixtures with calibration regression tests; wheel install smoke test
- [x] `pytest-cov` gate at measured baseline (core at 92% line coverage, 163 missing lines out of 2036)
- [x] `pytest -q`, `pytest -m "not live and not benchmark"`, `-m live`, `-m benchmark` all work
- [x] conftest.py per-category auto-marking; `pytest -m unit` / `-m integration` / `-m regression` select correctly

### P9 — Static quality gates
- [x] Ruff lint + formatter policy; mypy/pyright on public/core; pre-commit hooks
- [x] `py.typed` if type coverage sufficient; one dev command (nox/tox/Make) runs format+lint+type+tests+build

### P10 — CI (GitHub Actions)
- [H] `.github/workflows/ci.yml`: lint, type, tests across supported Pythons, build, wheel install smoke
- [H] Minimal token perms, concurrency cancellation, dep caching, pinned actions
- [H] `.github/workflows/live-integration.yml` (scheduled + dispatch, never publishes)

### P11 — Dependency & supply-chain security
- [x] `SECURITY.md` with supported versions, private reporting instructions, disclosure policy
- [H] `.github/dependabot.yml` (pip + actions, weekly) — created, stashed with workflow files
- [H] Release via PyPI Trusted Publishing OIDC, protected `pypi` env, `id-token: write` only at publish job

### P12 — Release automation
- [H] `.github/workflows/release.yml`: build job → separate publish job (test the artifact that ships) — created, stashed
- [H] TestPyPI dry-run documented
- [x] `docs/development/releasing.md` with full release checklist

### P13 — Documentation restructure
- [x] `docs/` tree (getting-started, concepts, api, guides, derivations, development, migration)
- [x] Every math page: Definition/Assumptions/Formula/Implementation/Numerical caveats/References
- [x] Public API docs: purpose, params, return, units, exceptions, example, limitations

### P14 — README for distribution
- [x] First screen: what/why/see/install; hero visual; 10-line quickstart; badges
- [x] Claims policy: every number reproducible or dated-snapshot/hardware-tagged; no stale figures
- [x] `pip install volfoundry` as headline install; dev instructions lower  [partial H — PyPI]

## Post-first-release (do NOT block v0.1.0)
- [ ] P15 CLI polish · P16 logging · P17 benchmarks · P18 native wheels · P19 governance files
- [ ] P20 disclaimer · P21 examples · P22 architecture cleanup · P23 schemas/units · P24 snapshot versioning
- [ ] P25 historical helpers · P26 model assumptions · P27 regeneratable reports · P28 capabilities · P29 final audit

## Definition of Done — v0.1.0 (release blockers only; [H] = needs human)
- [x] Wheel + sdist install in clean env; base install needs no C++ compiler; import does no network
- [x] Branding + import path + distribution all `volfoundry`; repo rename tracked  [H]
- [x] Core unit/property/regression tests pass; strict validation refuses invalid surfaces
- [x] SSVI restrictions enforced or accurately scoped; arbitrage checks report domain+tolerance
- [x] IV solver invalid-price tested; Monte Carlo reproducible
- [x] High-level fetch/load + fit without private imports; offline flow; typed + documented API; structured results; domain exceptions
- [x] Deribit errors can't become empty-success; bounded retries; explicit timeouts; observable cleaning reasons; snapshot schema version + round-trip tests
- [x] Ruff passes; type checking passes; build artifacts tested; live workflow separate; CI + Dependabot files authored but push-blocked  [H]
- [x] README first-screen value prop; PyPI install; public-API quickstart; derivations kept; assumptions explicit; claims reproducible; governance docs
- [H] TestPyPI tested  [H]; PyPI OIDC publishing  [H]; release workflow ships tested artifact; CHANGELOG current; `v0.1.0` tag  [H]

## Completion criterion for the autonomous builder
When every non-`[H]` release-blocking box above is checked AND
`pytest -m "not live and not benchmark"` is green AND `python -m build` +
`twine check` pass AND the wheel installs+imports in a clean venv: write
`PRODUCTION_READINESS_REPORT.md` (plan §39) with real command outputs, then
create `.VOLFOUNDRY_COMPLETE` and commit it. Human-gated `[H]` items remain in
`HUMAN_ACTIONS.md` and do not block the marker.

## Session log (newest first)
- 2026-08-11: **v0.1.0 readiness finalized.** DoD checkboxes updated to reflect actual state.
  Wrote PRODUCTION_READINESS_REPORT.md with real command outputs from all verification
  steps: 438 tests pass, 92% line coverage, ruff clean, mypy 12 import-untyped only,
  build + twine green, wheel + sdist install in fresh venvs. Created
  .VOLFOUNDRY_COMPLETE marker. All non-[H] release-blocking items (P0–P14) are
  complete. Human-gated items (CI push, PyPI, repo rename, release) remain in
  HUMAN_ACTIONS.md. VolFoundry v0.1.0 is ready for human sign-off.
- 2026-08-11: **P14 complete.** README rewritten for VolFoundry distribution.
  First screen delivers what/why/see/install pattern with hero 3D surface image,
  10-line quickstart (live + offline paths) using only public APIs, and `pip
  install volfoundry` as headline. Key features section covers the full pipeline,
  validation modes (report vs strict), three pricing engines, C++ opt-in, and
  snapshot reproducibility. Architecture diagram matches plan §22 dependency
  rules. Unit conventions are explicit. No stale or fabricated numbers — every
  claim is either reproducible (IV accuracy, benchmark timing) or clearly tagged
  as a dated snapshot example. Contributing, disclaimer, and license sections
  present. P14 checkboxes ticked; PyPI install line is partial-H pending actual
  PyPI publication. 438 tests pass, build + twine check green, wheel + sdist
  install in clean venvs. Committed as 9f8b3e7, pushed.
- 2026-08-11: **P13 complete.** Restructured `docs/` tree: `getting-started/`
  (installation, quickstart, offline-data), `concepts/` (implied-volatility,
  volatility-smile, svi, ssvi, arbitrage, forwards), `api/` index with full
  reference for all stable public objects (DeribitClient, SurfaceBuilder,
  VolatilitySurface, SurfaceFitResult, ValidationReport, OptionChain,
  exception taxonomy), `guides/` (deribit, fitting-a-surface,
  validating-a-surface, querying-a-surface, historical-snapshots). Every
  mathematical page uses the standard six-section format (Definition,
  Assumptions, Formula, Implementation, Numerical caveats, References).
  Updated `docs/development/architecture.md` (dependency rules, module map,
  design decisions) and `docs/development/testing.md`. Refreshed
  network_inventory.md and numerics_inventory.md for post-P7 state.
  Expanded derivations README with cross-links. 438 tests pass, build green,
  committed+pu
shed as 033fddb.
- 2026-08-11: **P10/P11/P12 workflow files created, push blocked on token scope.**
  P10: ci.yml (lint+type+test 3.10/11/12+build+wheel smoke), live-integration.yml
  (daily 07:38 UTC), tests/live/test_live_smoke.py (3 tests). P11: dependabot.yml
  (pip+actions, weekly), SECURITY.md (committed and pushed). P12: release.yml
  (build→TestPyPI→PyPI OIDC), docs/development/releasing.md (committed+pushed).
  The `gh` OAuth token lacks `workflow` scope — all `.github/` files stashed.
  Run `git stash pop` with a workflow-scoped token to push. 438 tests pass.
- 2026-08-11: **P9 complete.** Ruff configured in pyproject.toml (F/E/W/I/UP/B/C4/SIM/RUF/BLE
  rules, line-length 100).  151 auto-fixed violations, remaining 43 handled via
  per-file-ignores for intentional math notation (Greek/en-dash/×) and legitimate
  blind-except patterns.  Ruff format applied to all 55 source+test files.  mypy
  strict-mode: 15 errors across 3 files resolved (calibration ndarray casts,
  builder type annotations, fetcher json=payload ignore, pricers dict-item
  suppress).  `.pre-commit-config.yaml` with ruff + ruff-format + mypy hooks.
  `Makefile` with lint/format/typecheck/test/test-all/test-live/test-bench/build/
  clean targets.  `py.typed` marker already present.  dev deps updated (mypy,
  pre-commit, check-manifest).  438 tests pass, mypy clean (30 files, 0 errors),
  ruff clean (0 errors).  Build + twine check green.
- 2026-08-11: **P8 complete.** Reorganised test suite into five categories:
  `tests/{unit,property,integration,regression,live}` with per-category
  `conftest.py` auto-marking.  Flat test files migrated to appropriate
  directories (test_iv, test_svi, test_pricers, test_arbitrage, test_filters,
  test_forwards → unit; test_fetcher, test_high_level_api, test_surface,
  test_surface_plotting, test_p6, test_p7, test_persistence → integration).
  Two new markers registered: `property` and `regression`.  Created
  `tests/regression/` with deterministic golden calibration fixture (flat-vol
  synthetic dataset, 7 calibration regression tests) and wheel-install smoke
  test (import, API availability, pricing round-trip).  Coverage baseline
  measured at 92% line coverage (2036 lines, 163 missing) via pytest-cov;
  `tool.coverage` configuration added to pyproject.toml.  Cleaned stale
  `volsurface` editable install from venv.  All four test commands verified
  working: `pytest -q`, `pytest -m "not live and not benchmark"`,
  `pytest -m live`, `pytest -m benchmark`.  437 tests pass (+9 new P8).
  Build + twine check green.  Wheel installs + imports in clean venv.
- 2026-08-10: **P7 complete.** Created `src/volfoundry/tolerances.py` with central
  named tolerances (PRICE_TOL, VOL_TOL, ARBITRAGE_TOL, CALIBRATION_TOL) and
  derived constants (EPSILON, VEGA_FLOOR, SIGMA_FLOOR, A_FLOOR, B_FLOOR, RHO_TOL,
  R2_FLOOR).  Wired them into all source modules (IV solver, SVI calibration,
  SSVI calibration, arbitrage checks, Monte Carlo, forwards).  Converted MC
  result type from plain dict to `MCResult` dataclass with full metadata
  (confidence bounds, n_paths, seed, control_variate flag).  26 new P7 acceptance
  tests: central tolerances (3), IV edge cases (9: negative F, zero maturity,
  huge/tiny vol recovery, deep ITM/OTM, price below/above bounds, vectorised
  batch), SVI diagnostics (8: deterministic init, outer_success, diagnostics
  fields, bound-proximity, normalized weights, min-data requirement, degenerate
  flat smile), MC structured results (6: structured return, CI validity,
  reproducibility, different-seeds-different, CV accuracy, zero-vol exactness).
  428 tests pass (402 + 26 new P7).  Build + twine check green.  Wheel installs
  + imports in clean venv.
- 2026-08-10: **P6 complete.** The most important quantitative production change.
  SSVI analytical constraints (Lee bound `eta*(1+|rho|) <= 2`, calendar
  monotonicity) are now enforced as hard penalties IN the optimizer objective,
  not merely printed after fitting.  SSVI results that violate the Lee bound
  are rejected (success=False) even if the optimizer terminated without error.
  Per-slice SVI diagnostics now include `svi_status` (valid/converged_invalid/
  did_not_converge/not_fitted), `g_min`, and `k_eval_domain`.  ValidationReport
  includes analytical rejection reasons alongside numerical failures, and the
  evaluation domain/tolerances are always recorded.  Added 25 P6 acceptance
  tests covering all seven plan §9 requirements: invalid params detected,
  calendar-crossing fails strict, strict mode refuses invalid surfaces, report
  mode preserves invalid fits with clear flags, valid SSVI passes, optimizer
  failure vs arbitrage failure distinguishable, tolerance changes in metadata.
  402 tests pass (377 + 25 new P6).  Build + twine check green.  Committed as
  258ae51, pushed.
- 2026-08-10: **P5 complete.** Deribit HTTP hardened: `_build_session()` with
  `urllib3.Retry` (3 retries, exponential backoff with jitter, only 429/5xx),
  `User-Agent: VolFoundry/0.1.0`, explicit connect (10s) + read (30s) timeouts.
  All RPC functions now raise `MarketDataError` (never `RuntimeError`); empty
  instrument list raises instead of returning empty `Snapshot`. `QuoteCleaningReport`
  and `QuoteRemovalRecord` provide per-reason diagnostic counts and per-quote
  machine-readable reasons. `filters.py` functions return `_FilterResult` with
  `.df` + `.removals`. `persistence.py` uses atomic writes (tempfile + rename)
  with schema versioning in parquet metadata; future schema versions are rejected.
  Existing fixture tests updated for new API; 377 tests pass, build + twine check green.
  Live tests are already marker-registered (`@pytest.mark.live` from P2 conftest).
- 2026-08-10: **P3 + P4 complete.** Public API wired up: `__init__.py` exports
  `DeribitClient`, `SurfaceBuilder`, `VolatilitySurface`, `SurfaceFitResult`,
  `ValidationReport`, `OptionChain`, and full exception taxonomy via `__all__`.
  `SurfaceBuilder.fit()` / `fit_dataframe()` orchestrates full pipeline.
  Critical bugfix in `_prepare_slices`: `implied_vol_brent` arguments were
  swapped (F passed as `price`), making IV inversion always fail. 46 new
  high-level API tests; 365 tests pass total. Build + twine check green.
  Exception taxonomy (P4) was already implemented in `exceptions.py` and
  `SurfaceBuilder`; all exception chaining tests pass.
- 2026-08-10: **P2 complete.** pyproject.toml overhauled: license as SPDX string,
  matplotlib moved to [plot] extra, [docs] extra added, maintainers + Changelog
  URL. Version bumped to 0.1.0, canonical source in `_version.py`. MANIFEST.in
  added (docs, cpp, examples, CHANGELOG in sdist). py.typed marker added. CLI
  stub with volfoundry entry point. conftest.py registers pytest markers. Wheel
  and sdist both install cleanly in separate venvs. Base wheel has 0 extra deps
  (no matplotlib/QuantLib/pytest/hypothesis/C++ compiler needed). All 319 tests
  pass, build + twine check green.
- 2026-08-10: **P1 complete.** Package renamed to `volfoundry`, moved to
  `src/volfoundry/` layout. All imports migrated (src, tests, examples, docs,
  cpp/setup.py). pyproject.toml updated: name volfoundry, src layout,
  classifiers, keywords, project URLs. CHANGELOG with migration note + migration
  guide written. Old `volsurface/` tree removed. No compatibility shim. All 319
  tests pass, editable install verified.
- 2026-08-10: **P0 complete.** Baseline recorded (319 tests, py3.12, Linux x86_64,
  commit 27f5949). API inventory (55 public symbols), network inventory (2 HTTP
  surfaces, no import-time calls), numerics inventory (scattered tolerances, no
  multi-start SVI, Lee bound post-hoc only). Grep sweep clean: 0 TODO/FIXME, 0
  library print(), seeds controlled throughout. Build succeeds.
- 2026-08-10: Phase 2 kicked off. Plan committed as spec, tracker created,
  builder repointed from M-milestones to P-milestones. Phase 1 (M1–M6, 319
  tests) preserved.
