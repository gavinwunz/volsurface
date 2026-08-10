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
- [ ] Move to `src/volfoundry/` layout (data/ iv/ svi/ arbitrage/ pricers/ surface/ cli/)
- [ ] Mechanical import migration `volsurface.*` → `volfoundry.*` (src, tests, examples, docs, cpp, scripts)
- [ ] `CHANGELOG.md` migration note + `docs/migration/volsurface-to-volfoundry.md`
- [ ] No `volsurface` compatibility shim shipped
- [ ] `python -c "import volfoundry; print(volfoundry.__version__)"` works after editable install

### P2 — Modernize packaging
- [ ] `pyproject.toml`: name volfoundry, requires-python >=3.10, MIT, authors, URLs, classifiers, keywords
- [ ] Extras: [plot] [dev] [docs] [benchmark]; benchmark-only deps (QuantLib/py_vollib) out of base
- [ ] One canonical version source; `__version__` matches build metadata; bump to 0.1.0
- [ ] `python -m build` + `twine check dist/*`; wheel AND sdist install in clean venvs
- [ ] Base install needs no C++ compiler, no QuantLib/py_vollib/pytest/hypothesis

### P3 — Small stable public API
- [ ] High-level `DeribitClient`, `SurfaceBuilder`, `VolatilitySurface`, `ValidationReport`
- [ ] Structured result objects (`SurfaceFitResult`, `ValidationReport`, `MarketSnapshot`/`OptionChain`)
- [ ] Offline path (`fit_dataframe` / `MarketSnapshot.read_parquet`) — no network needed for calibration
- [ ] Small `__init__.py` with `__all__`; low-level modules still importable
- [ ] Main workflow achievable in <~15 lines without private imports

### P4 — Real error model
- [ ] `exceptions.py` taxonomy (VolFoundryError → Data/Pricing/Calibration/Config, ArbitrageViolationError, etc.)
- [ ] Preserve `__cause__` on wrap; no bare `except Exception` in core; library raises, does not `sys.exit`

### P5 — Reliable market data
- [ ] Hardened Deribit HTTP: timeouts, reusable session, UA w/ version, bounded retries + backoff+jitter, 429/5xx only
- [ ] Typed quote schema + validation; JSON-RPC error handling; never empty-success on API error
- [ ] Quote-cleaning diagnostics (per-reason counts + machine-readable reasons)
- [ ] Atomic snapshot writes; never overwrite historical snapshots; reproducible metadata
- [ ] Offline fixture tests; live tests marked `@pytest.mark.live`

### P6 — Strict no-arbitrage construction contract  *(most important quant change)*
- [ ] `validation="report"` (research fit, may be invalid but clearly flagged) vs `validation="strict"` (raises `ArbitrageViolationError`)
- [ ] Enforce SSVI analytical conditions during/for parameter acceptance (not post-hoc print)
- [ ] rho domain, positive theta, valid eta/lambda, monotone ATM total variance (or documented repair w/ raw+adjusted retained)
- [ ] Per-slice SVI fit status; distinguish converged vs valid; g(k) min + domain exposed
- [ ] Every numerical arbitrage report states domain + tolerance; BL density as cross-check only
- [ ] Acceptance tests (plan §9): invalid params detected, calendar-crossing fails strict, strict refuses invalid, report keeps invalid, valid SSVI passes, optimizer≠arbitrage failure, tolerance in metadata

### P7 — Numerical robustness & reproducibility
- [ ] IV inversion edge cases (below/above bounds, ~0 maturity, deep ITM/OTM, tiny vega, NaN/Inf) → consistent errors
- [ ] SVI: deterministic init, multi-start, optimizer diagnostics, bound-proximity warnings, degenerate smiles
- [ ] Monte Carlo: `numpy.random.Generator`, seeds, standard error/CI, seeded regression tests
- [ ] Central named tolerances (PRICE_TOL/VOL_TOL/ARBITRAGE_TOL/CALIBRATION_TOL)

### P8 — Test architecture
- [ ] tests/{unit,property,integration,regression,live}; markers unit/integration/live/slow/benchmark registered
- [ ] Golden/regression fixtures with expected outputs+tolerances; wheel install smoke test
- [ ] `pytest-cov` gate at measured baseline (target ~90% meaningful core, no filler tests)
- [ ] `pytest -q`, `pytest -m "not live and not benchmark"`, `-m live`, `-m benchmark` all work

### P9 — Static quality gates
- [ ] Ruff lint + formatter policy; mypy/pyright on public/core; pre-commit hooks
- [ ] `py.typed` if type coverage sufficient; one dev command (nox/tox/Make) runs format+lint+type+tests+build

### P10 — CI (GitHub Actions)
- [ ] `.github/workflows/ci.yml`: lint, type, tests across supported Pythons, build, wheel install smoke
- [ ] Minimal token perms, concurrency cancellation, dep caching, pinned actions
- [ ] `.github/workflows/live-integration.yml` (scheduled + dispatch, never publishes)

### P11 — Dependency & supply-chain security
- [ ] `.github/dependabot.yml` (pip + actions, weekly); `SECURITY.md`
- [ ] Release via PyPI Trusted Publishing OIDC, protected `pypi` env, `id-token: write` only at publish job  [H]

### P12 — Release automation
- [ ] `.github/workflows/release.yml`: build job → separate publish job (test the artifact that ships)
- [ ] TestPyPI dry-run documented  [H]
- [ ] `docs/development/releasing.md` checklist

### P13 — Documentation restructure
- [ ] `docs/` tree (getting-started, concepts, api, guides, derivations, development, migration)
- [ ] Every math page: Definition/Assumptions/Formula/Implementation/Numerical caveats/References
- [ ] Public API docs: purpose, params, return, units, exceptions, example, limitations

### P14 — README for distribution
- [ ] First screen: what/why/see/install; hero visual; 10-line quickstart; badges
- [ ] Claims policy: every number reproducible or dated-snapshot/hardware-tagged; no stale figures
- [ ] `pip install volfoundry` as headline install; dev instructions lower  [partial H — PyPI]

## Post-first-release (do NOT block v0.1.0)
- [ ] P15 CLI polish · P16 logging · P17 benchmarks · P18 native wheels · P19 governance files
- [ ] P20 disclaimer · P21 examples · P22 architecture cleanup · P23 schemas/units · P24 snapshot versioning
- [ ] P25 historical helpers · P26 model assumptions · P27 regeneratable reports · P28 capabilities · P29 final audit

## Definition of Done — v0.1.0 (release blockers only; [H] = needs human)
- [ ] Wheel + sdist install in clean env; base install needs no C++ compiler; import does no network
- [ ] Branding + import path + distribution all `volfoundry`; repo rename tracked  [H]
- [ ] Core unit/property/regression tests pass; strict validation refuses invalid surfaces
- [ ] SSVI restrictions enforced or accurately scoped; arbitrage checks report domain+tolerance
- [ ] IV solver invalid-price tested; Monte Carlo reproducible
- [ ] High-level fetch/load + fit without private imports; offline flow; typed + documented API; structured results; domain exceptions
- [ ] Deribit errors can't become empty-success; bounded retries; explicit timeouts; observable cleaning reasons; snapshot schema version + round-trip tests
- [ ] Ruff passes; type checking passes; CI green; build artifacts tested; live workflow separate; Dependabot on
- [ ] README first-screen value prop; PyPI install; public-API quickstart; derivations kept; assumptions explicit; claims reproducible; governance docs
- [ ] TestPyPI tested  [H]; PyPI OIDC publishing  [H]; release workflow ships tested artifact; CHANGELOG current; `v0.1.0` tag  [H]

## Completion criterion for the autonomous builder
When every non-`[H]` release-blocking box above is checked AND
`pytest -m "not live and not benchmark"` is green AND `python -m build` +
`twine check` pass AND the wheel installs+imports in a clean venv: write
`PRODUCTION_READINESS_REPORT.md` (plan §39) with real command outputs, then
create `.VOLFOUNDRY_COMPLETE` and commit it. Human-gated `[H]` items remain in
`HUMAN_ACTIONS.md` and do not block the marker.

## Session log (newest first)
- 2026-08-10: **P0 complete.** Baseline recorded (319 tests, py3.12, Linux x86_64,
  commit 27f5949). API inventory (55 public symbols), network inventory (2 HTTP
  surfaces, no import-time calls), numerics inventory (scattered tolerances, no
  multi-start SVI, Lee bound post-hoc only). Grep sweep clean: 0 TODO/FIXME, 0
  library print(), seeds controlled throughout. Build succeeds.
- 2026-08-10: Phase 2 kicked off. Plan committed as spec, tracker created,
  builder repointed from M-milestones to P-milestones. Phase 1 (M1–M6, 319
  tests) preserved.
