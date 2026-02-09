# Defaults to the dev stack; override with COMPOSE=... if needed
COMPOSE ?= docker-compose.dev.yml
SERVICE ?= scraper
DC := docker compose -f $(COMPOSE)
PROD_DC := docker compose -f docker-compose.yml

.PHONY: help dev-build dev-up dev-down dev-restart logs shell test test-unit test-int test-file test-stack fmt lint clean
.PHONY: prod-build prod-up prod-down validate health-check

help:
	@echo "Dev targets:"
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
	@echo ""
	@echo "Prod targets:"
	@echo "  prod-build    - Build production image (no cache)"
	@echo "  prod-up       - Start production stack"
	@echo "  prod-down     - Stop production stack"
	@echo "  validate      - Validate docker-compose.yml syntax"
	@echo "  health-check  - Check app and selenium health endpoints"

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

# Production targets

prod-build:
	$(PROD_DC) build --no-cache

prod-up:
	$(PROD_DC) up -d

prod-down:
	$(PROD_DC) down

validate:
	$(PROD_DC) config --quiet

health-check:
	@echo "Checking app health..."
	@curl -sf http://localhost:5000/ > /dev/null && echo "  App: OK" || echo "  App: FAILED"
	@echo "Checking Selenium health..."
	@curl -sf http://localhost:4444/wd/hub/status > /dev/null && echo "  Selenium: OK" || echo "  Selenium: FAILED"

# Danger zone
clean:
	$(DC) down -v --remove-orphans
