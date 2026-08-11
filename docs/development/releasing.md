# Releasing VolFoundry

This checklist covers cutting and publishing a new VolFoundry release.

## Prerequisites

- Maintainer access to the GitHub repository and PyPI (and TestPyPI)
  projects.
- Trusted Publisher configured on both PyPI and TestPyPI pointing at the
  repository and `release.yml` workflow.
- A clean local clone of `main` at the desired release commit.

## Release checklist

### 1. Verify CI

- [ ] `pytest -m "not live and not benchmark"` is green locally.
- [ ] `python -m build` and `twine check dist/*` pass.
- [ ] Ruff and mypy pass (`ruff check src tests`, `mypy src/volfoundry`).
- [ ] GitHub Actions CI is green for the target commit.

### 2. Prepare the release

- [ ] Update `CHANGELOG.md`: add a heading for the new version with the
      date, a summary, and notable changes since the last release.
- [ ] Verify the version in `src/volfoundry/_version.py` matches the
      intended release version (it is the single canonical source).
- [ ] Regenerate any stale README claims from reproducible scripts
      (benchmarks, test counts, example output).
- [ ] Build documentation if applicable and check for warnings.

### 3. Test the release artifact

- [ ] Build: `rm -rf dist && python -m build`.
- [ ] Check: `twine check dist/*`.
- [ ] Install wheel in a clean venv:
      ```bash
      python -m venv /tmp/volfoundry-test
      /tmp/volfoundry-test/bin/pip install dist/*.whl
      /tmp/volfoundry-test/bin/python -c "import volfoundry; print(volfoundry.__version__)"
      ```
- [ ] Run a quick smoke test: `black76_price` round-trip with a known
      benchmark value.
- [ ] Install the sdist in a separate clean venv and repeat.

### 4. TestPyPI dry run (first release or major packaging changes)

- [ ] Push a `v`-prefixed tag (e.g. `v0.1.0rc1`) to trigger the release
      workflow against TestPyPI, or trigger it manually.
- [ ] Wait for the TestPyPI publish to succeed.
- [ ] Install from TestPyPI in a clean venv:
      ```bash
      python -m venv /tmp/volfoundry-testpypi
      /tmp/volfoundry-testpypi/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ volfoundry
      /tmp/volfoundry-testpypi/bin/python -c "import volfoundry; print(volfoundry.__version__)"
      ```

### 5. Publish

- [ ] Tag the release: `git tag -a v0.1.0 -m "VolFoundry v0.1.0"`.
- [ ] Push the tag: `git push origin v0.1.0`.
- [ ] Monitor the `release.yml` workflow. Wait until the PyPI publish job
      succeeds.
- [ ] Verify the PyPI page: https://pypi.org/project/volfoundry/
- [ ] Create a GitHub Release from the tag with release notes.

### 6. Post-release

- [ ] Verify `pip install volfoundry` works in a clean environment
      (no extra index, no git clone).
- [ ] Bump the version to the next development version (e.g. `0.1.1.dev0`)
      and push.
- [ ] Announce if desired.

## Environment setup for maintainers

The `pypi` and `testpypi` environments in GitHub must be configured with
Trusted Publishing (OIDC) pointing at this repository. No long-lived
`PYPI_TOKEN` secrets are needed.

The workflow file at `.github/workflows/release.yml` contains the build
and publish logic. It is triggered by tags matching `v*.*.*`.