.PHONY: install test lint run

install:
	pip install -e .[dev]

test:
	pytest

lint:
	ruff check src tests

run:
	mergemate run-bot --config ./config/config.yaml