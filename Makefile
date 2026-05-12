.PHONY: install install-dev test test-all lint typecheck coverage clean run

# ── Installation ──────────────────────────────────────────────────────────────

install:
	pip install -e .

install-dev:
	pip install -e .[dev]

# ── Quality ───────────────────────────────────────────────────────────────────

lint:
	ruff check src tests

typecheck:
	mypy src

test:
	pytest -q -m "not integration and not e2e"

test-all:
	pytest -q

coverage:
	pytest -q --cov-report=term-missing --cov-report=xml -m "not integration and not e2e"

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# ── Run ───────────────────────────────────────────────────────────────────────

run:
	mergemate run-bot --config ./config/config.yaml