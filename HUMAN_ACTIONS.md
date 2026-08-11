# Human Actions Required

These VolFoundry v0.1.0 release-blockers require account/settings access the
build agent does not have. They are tracked here so the automated build never
silently claims them done. Nothing below is safe for the agent to fake.

## GitHub repository
- [ ] Settings → General → rename `gavinwunz/volsurface` → `gavinwunz/volfoundry`.
- [ ] Verify the old URL redirects to the new repository.
- [ ] Update repository description and topics (plan §36).
- [ ] Enable branch protection / required checks as desired.
- [ ] Enable CodeQL / security features if wanted (plan §13).
- [ ] **PUSH BLOCKER — CI workflow files.** The `gh` OAuth token lacks the
      `workflow` scope. Run `git stash pop` to restore the P10 CI files
      (`.github/workflows/ci.yml`, `.github/workflows/live-integration.yml`,
      `tests/live/test_live_smoke.py`), then `git commit` and `git push`. Or
      generate a personal access token with `workflow` scope and use that.

## PyPI distribution
- [ ] Confirm the `volfoundry` project name is available / claim it on PyPI.
- [ ] Configure a PyPI **Trusted Publisher** (OIDC) pointing at the renamed repo
      and `.github/workflows/release.yml` (no long-lived `PYPI_TOKEN`). Docs:
      https://docs.pypi.org/trusted-publishers/
- [ ] Do the same on **TestPyPI** for the dry-run.
- [ ] Create a protected GitHub `pypi` environment with manual approval.

## First release
- [ ] Run the release workflow against TestPyPI; install from TestPyPI in a clean env.
- [ ] Approve the real `v0.1.0` publish once CI is green.
- [ ] Verify the public PyPI page and `pip install volfoundry` in a clean env.

The agent will complete all in-repo engineering (rename, packaging, API, tests,
CI workflow files, docs) up to these walls and mark the corresponding
`VOLFOUNDRY_PROGRESS.md` items `[H]`.
