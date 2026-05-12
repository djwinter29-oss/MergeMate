.PHONY: install install-dev test test-all lint typecheck coverage clean run \
        branches-clean branches-list branches-merged

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

# ── Branch maintenance ────────────────────────────────────────────────────────

branches-merged:
	@echo "=== Local branches merged into main (safe to delete) ==="
	@git branch --merged main | grep -v "main\|*" | sed 's/^/  /'
	@echo
	@echo "=== Remote tracking branches merged into main (safe to prune) ==="
	@git branch -r --merged origin/main | grep -v "origin/main\|origin/HEAD" | sed 's/^/  /'

branches-list:
	@echo "=== All local branches ==="
	@git branch | sed 's/^/  /'
	@echo
	@echo "=== Stale branches (no remote tracking) ==="
	@git branch -vv | grep ': gone]' | sed 's/^/  /'

branches-clean: branches-merged
	@echo
	@echo "To delete merged local branches, run:"
	@echo '  git branch --merged main | grep -v "main\|*" | xargs -r git branch -d'
	@echo
	@echo "To prune stale remote tracking, run:"
	@echo '  git remote prune origin'

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# ── Run ───────────────────────────────────────────────────────────────────────

run:
	mergemate run-bot --config ./config/config.yaml