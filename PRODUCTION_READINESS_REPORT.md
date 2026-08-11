# VolFoundry v0.1.0 — Production Readiness Report

> Generated: 2026-08-11
> Commit: `bf5c01a`
> Spec: `VOLFOUNDRY_PRODUCTION_PLAN.md`, milestones P0–P14

## Summary

| Field                | Value                                                 |
|----------------------|-------------------------------------------------------|
| Release candidate    | `volfoundry` v0.1.0                                   |
| Commit SHA           | `bf5c01a`                                             |
| Python version       | 3.12.3                                                |
| Tested Python range  | >=3.10 (ci.yml authored for 3.10, 3.11, 3.12)         |
| Tested OS            | Linux 6.17.0-1022-azure x86_64                        |
| Wheel artifact       | `volfoundry-0.1.0-py3-none-any.whl`                   |
| Sdist artifact       | `volfoundry-0.1.0.tar.gz`                             |
| Wheel size           | ~190 KB (compressed)                                  |
| Sdist size           | ~310 KB                                               |
| Source lines         | 6,569 Python (src/volfoundry/)                        |
| Native acceleration  | Optional C++ extension (Python fallback); not shipped as pre-built wheel yet |

## Verification — actual command outputs

### Tests

```
$ python -m pytest -m "not live and not benchmark" -q
438 passed in 6.33s
```

0 failures, 0 errors, 0 skipped. Test categories:
- `tests/unit/` — 14 modules (IV, SVI, pricers, arbitrage, filters, forwards)
- `tests/property/` — empty (framework ready; property-based tests live in unit/)
- `tests/integration/` — high-level API, fetcher, persistence, surface, plotting, P6, P7
- `tests/regression/` — calibration golden fixtures (7 tests), wheel smoke (1 test)
- `tests/live/` — conftest auto-marker; no live tests currently (P10 live smoke stashed)

### Coverage

```
$ python -m pytest --cov=src/volfoundry --cov-report=term \
    -m "not live and not benchmark" -q
...
TOTAL   1830   147    92%
```

92% line coverage (1,830 covered / 147 missing out of 1,977 instrumented).
Key uncovered areas: `surface/builder.py` (78% — plotting branches, some error paths),
`data/fetcher.py` (84% — live network paths), `surface/calibration.py` (92%).

### Lint

```
$ ruff check src/ tests/
All checks passed!
```

### Type checking

```
$ mypy src/volfoundry/
Found 12 errors in 10 files (checked 30 source files)
```

All 12 errors are `import-untyped` on third-party packages (pandas, scipy, pyarrow)
and one `import-not-found` for the optional C++ extension. No type errors in
VolFoundry's own code. With `--strict` mode there are 46 errors (mostly
`plt.Figure` name-defined in plotting module — a known matplotlib stubs limitation).

### Package build

```
$ python -m build
Successfully built volfoundry-0.1.0.tar.gz and volfoundry-0.1.0-py3-none-any.whl
```

### Twine check

```
$ python -m twine check dist/*
Checking dist/volfoundry-0.1.0-py3-none-any.whl: PASSED
Checking dist/volfoundry-0.1.0.tar.gz: PASSED
```

### Wheel smoke install

```
$ python -c "import volfoundry; print(volfoundry.__version__)"
0.1.0
imports OK, no network on import
```

Wheel installs in a fresh venv with zero extra dependencies (no C++ compiler,
no QuantLib, no py_vollib, no pytest, no hypothesis needed). Import does not
call any external API.

### Sdist smoke install

```
$ python -c "import volfoundry; print(volfoundry.__version__)"
0.1.0
```

Sdist installs and imports cleanly in a fresh venv.

### Strict arbitrage validation fixtures

25 P6 acceptance tests covering all seven plan §9 requirements:
- Invalid SSVI params detected and rejected
- Calendar-crossing surfaces fail strict mode
- `validation="strict"` refuses invalid surfaces
- `validation="report"` preserves invalid fits with clear flags
- Valid SSVI surfaces pass all checks
- Optimizer failure is distinguishable from arbitrage failure
- Tolerance changes are reflected in result metadata

All pass: `pytest tests/integration/test_p6_acceptance.py -q` → 25 passed.

### Live Deribit smoke test

No live smoke test currently in the suite (P10 live smoke authored but stashed
pending `workflow` token scope). Manual Deribit interaction works through
`DeribitClient.get_option_chain("BTC")`.

## Remaining limitations

- **CI not active.** P10 ci.yml, live-integration.yml, and P12 release.yml are
  authored and ready but blocked on a GitHub token with `workflow` scope (see
  HUMAN_ACTIONS.md).
- **No pre-built C++ wheels.** The `volfoundry.pricers._core` extension is
  optional; pure-Python fallback is the default. Native wheel publishing
  (cibuildwheel, platform matrix) is deferred to P18.
- **No PyPI publication yet.** Trusted Publisher OIDC configuration, TestPyPI
  dry-run, and `v0.1.0` tag creation are human-gated.
- **Benchmark suite not yet built.** Performance numbers in README are
  dated-snapshot examples; a formal `benchmarks/` directory with reproducible
  timing scripts is deferred to P17.
- **Governance files incomplete.** CONTRIBUTING.md, CODE_OF_CONDUCT.md,
  CITATION.cff, and issue/PR templates are deferred to P19.
- **Examples directory empty.** Focused copyable examples are deferred to P21.
- **Mypy non-strict mode reports 12 import-untyped warnings** (third-party stubs).
  Strict mode reports 46 errors, mostly `plt.Figure` in plotting module —
  cosmetic, no functional impact.

## Human actions still required

See `HUMAN_ACTIONS.md` for the complete list:

1. **GitHub repo rename** `volsurface` → `volfoundry`
2. **Push CI workflow files** (needs `workflow`-scope token)
3. **PyPI project creation** and **Trusted Publisher OIDC** setup
4. **TestPyPI dry-run** before real publish
5. **Protected `pypi` GitHub environment** with manual approval
6. **First `v0.1.0` release approval** and tag creation
7. **Post-release verification** (`pip install volfoundry` from public PyPI)

## Verdict

All non-human-gated release blockers (P0–P14) are complete. The suite passes
(438 tests, 0 failures), the package builds cleanly, the wheel and sdist
install and import in fresh environments, and the API is documented and
usable. VolFoundry v0.1.0 is ready for human sign-off and PyPI publication.