# Installing VolFoundry

VolFoundry is distributed as `volfoundry` on PyPI. A pure-Python core is always
available; no compiler is needed to install or use the basic package.

## Requirements

- Python 3.10 or later
- pip 23.0 or later

## Quick install

```bash
pip install volfoundry
```

## Optional extras

```bash
pip install volfoundry[plot]       # matplotlib for surface visualisation
pip install volfoundry[dev]        # pytest, ruff, mypy, pre-commit
pip install volfoundry[docs]       # documentation build tools
pip install volfoundry[benchmark]  # QuantLib + py_vollib for benchmarks
```

## Verify

```bash
python -c "import volfoundry; print(volfoundry.__version__)"
```

## Editable install (development)

```bash
git clone https://github.com/gavinwunz/volsurface.git
cd volsurface
pip install -e ".[dev]"
python -m pytest -m "not live and not benchmark"
```

## From a wheel / sdist

```bash
python -m build
pip install dist/*.whl
```

The base wheel contains only the core runtime dependencies (NumPy, pandas,
scipy, requests).  Plotting, benchmarking, and development tooling are all
optional extras.  QuantLib and py_vollib are never required at runtime.

## C++ acceleration

A C++ pricing extension is available in the repository source (`cpp/`) but is
**experimental** and not shipped in the bundled wheel.  The Python path is
functionally identical and is used automatically when the extension is absent.