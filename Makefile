.PHONY: bootstrap test test-cov lint fmt clean eval schema ingest-and-eval help

help:
	@echo "Targets:"
	@echo "  bootstrap        Create .venv and install workspace in editable mode"
	@echo "  test             Run unit tests"
	@echo "  test-cov         Run unit tests with coverage report"
	@echo "  lint             Run ruff and mypy"
	@echo "  fmt              Auto-fix ruff issues and format"
	@echo "  clean            Remove .venv and caches"
	@echo "  eval             Run query-eval eval"
	@echo "  schema           Run query-eval schema-discovery"
	@echo "  ingest-and-eval  Run analyze->chunk->embed->upload->eval for one doc"

bootstrap:
	./bootstrap.sh

test:
	pytest features/ || [ $$? -eq 5 ]

test-cov:
	pytest features/ --cov=features --cov-report=term-missing || [ $$? -eq 5 ]

lint:
	ruff check features/ scripts/
	mypy features/ || [ $$? -eq 2 ]

fmt:
	ruff check --fix features/ scripts/
	ruff format features/ scripts/

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

eval:
	query-eval eval

schema:
	query-eval schema-discovery

ingest-and-eval:
	@if [ -z "$(DOC)" ] || [ -z "$(STRATEGY)" ] || [ -z "$(PDF)" ]; then \
	    echo 'Usage: make ingest-and-eval DOC=<slug> STRATEGY=<name> PDF=<path>'; \
	    echo 'Example: make ingest-and-eval DOC=gnb-b-147-2001-rev-1 STRATEGY=section PDF="data/GNB B 147_2001 Rev. 1.pdf"'; \
	    exit 1; \
	fi
	ingest analyze --in "$(PDF)"
	ingest chunk --in $$(ls -1t outputs/$(DOC)/analyze/*.json | head -1) --strategy $(STRATEGY)
	ingest embed --in $$(ls -1t outputs/$(DOC)/chunk/*-$(STRATEGY).jsonl | head -1)
	ingest upload --in $$(ls -1t outputs/$(DOC)/embed/*-$(STRATEGY).jsonl | head -1)
	query-eval eval --doc $(DOC) --strategy $(STRATEGY)
