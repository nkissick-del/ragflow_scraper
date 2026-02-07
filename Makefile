# Defaults to the dev stack; override with COMPOSE=... if needed
COMPOSE ?= docker-compose.dev.yml
SERVICE ?= scraper
DC := docker compose -f $(COMPOSE)

.PHONY: help dev-build dev-up dev-down dev-restart logs shell test test-unit test-int test-file test-stack fmt lint clean

help:
	@echo "Targets:"
	@echo "  dev-build     - Build dev image (no cache) for $(SERVICE)"
	@echo "  dev-up        - Start dev stack in background"
	@echo "  dev-down      - Stop and remove dev stack"
	@echo "  dev-restart   - Rebuild and restart dev stack"
	@echo "  logs          - Tail scraper logs"
	@echo "  shell         - Shell into scraper container (bash/sh)"
	@echo "  test          - Run all tests inside dev container"
	@echo "  test-unit     - Run unit tests"
	@echo "  test-int      - Run integration tests"
	@echo "  test-file     - Run a specific test FILE=..."
	@echo "  test-stack    - Run stack tests against live Unraid services"
	@echo "  fmt           - Format code (black + isort)"
	@echo "  lint          - Lint (ruff)"
	@echo "  clean         - Stop stack and prune (dangerous)"

# Build & lifecycle

dev-build:
	$(DC) build --no-cache $(SERVICE)

dev-up:
	$(DC) up -d

dev-down:
	$(DC) down

dev-restart: dev-build dev-up

# Ops helpers

logs:
	$(DC) logs -f $(SERVICE)

shell:
	$(DC) exec $(SERVICE) bash || $(DC) exec $(SERVICE) sh

# Tests

test:
	$(DC) exec $(SERVICE) python -m pytest -q

test-unit:
	$(DC) exec $(SERVICE) python -m pytest tests/unit -q

test-int:
	$(DC) exec $(SERVICE) python -m pytest tests/integration -q

# Usage: make test-file FILE=tests/unit/test_metadata_validation.py::TestClass::test_case
ifeq ($(FILE),)
TEST_FILE_CMD := echo "Set FILE=..." && exit 1
else
TEST_FILE_CMD := $(DC) exec $(SERVICE) python -m pytest $(FILE) -v
endif

test-file:
	@$(TEST_FILE_CMD)

test-stack:
	DOTENV_PATH=.env.stack python -m pytest tests/stack -v --timeout=120

# Dev tooling (optional, may require tools in container)
fmt:
	$(DC) exec $(SERVICE) bash -lc "black app tests && isort app tests" || true

lint:
	$(DC) exec $(SERVICE) bash -lc "ruff check app tests" || true

# Danger zone
clean:
	$(DC) down -v --remove-orphans
