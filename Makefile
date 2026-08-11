# VolFoundry developer convenience targets
#
# All commands can also be run directly with Python tools — no Make required.
#   ruff check --fix src tests     →  make lint
#   ruff format src tests           →  make format
#   mypy src/volfoundry             →  make typecheck
#   pytest -m "not live and not benchmark"  →  make test
#   python -m build && twine check dist/*   →  make build

.PHONY: help lint format typecheck test test-all test-live test-benchmark build clean

help:
	@echo "VolFoundry dev targets:"
	@echo "  make lint        — run ruff linter"
	@echo "  make format      — run ruff formatter"
	@echo "  make typecheck   — run mypy"
	@echo "  make test        — run unit + integration + property + regression tests"
	@echo "  make test-all    — run full suite (including slow)"
	@echo "  make test-live   — run live Deribit integration tests"
	@echo "  make test-bench  — run benchmark tests"
	@echo "  make build       — build wheel + sdist + twine check"
	@echo "  make clean       — remove build artifacts"
	@echo ""
	@echo "All targets run with: .venv/bin/python -m <tool>"

lint:
	.venv/bin/ruff check src tests

format:
	.venv/bin/ruff format src tests

typecheck:
	.venv/bin/mypy src/volfoundry --ignore-missing-imports

test:
	.venv/bin/python -m pytest -m "not live and not benchmark"

test-all:
	.venv/bin/python -m pytest -m "not live"

test-live:
	.venv/bin/python -m pytest -m live

test-bench:
	.venv/bin/python -m pytest -m benchmark

build:
	.venv/bin/python -m build
	.venv/bin/python -m twine check dist/*

clean:
	rm -rf dist/ build/ src/*.egg-info/ .mypy_cache/ .pytest_cache/ .ruff_cache/