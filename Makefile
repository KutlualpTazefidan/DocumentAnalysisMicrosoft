.PHONY: bootstrap test test-cov lint fmt clean curate eval schema help

help:
	@echo "Targets:"
	@echo "  bootstrap   Create .venv and install workspace in editable mode"
	@echo "  test        Run unit tests"
	@echo "  test-cov    Run unit tests with coverage report"
	@echo "  lint        Run ruff and mypy"
	@echo "  fmt         Auto-fix ruff issues and format"
	@echo "  clean       Remove .venv and caches"
	@echo "  curate      Run query-eval curate (interactive)"
	@echo "  eval        Run query-eval eval"
	@echo "  schema      Run query-eval schema-discovery"

bootstrap:
	./bootstrap.sh

test:
	pytest features/ || [ $$? -eq 5 ]

test-cov:
	pytest features/ --cov=features --cov-report=term-missing || [ $$? -eq 5 ]

lint:
	ruff check features/ scripts/
	mypy features/

fmt:
	ruff check --fix features/ scripts/
	ruff format features/ scripts/

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

curate:
	query-eval curate

eval:
	query-eval eval

schema:
	query-eval schema-discovery
