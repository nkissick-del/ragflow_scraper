# Test Suite Organization

This document describes the organization of the test suite for the RAGFlow Scraper project.

## Directory Structure

The test suite is organized into three main categories with logical subdirectories for better organization and discoverability:

```
tests/
├── unit/                      # Unit tests (81 tests)
│   ├── api_routes/           # API endpoint and blueprint tests (4 tests)
│   ├── backends/             # RAG backend implementations (4 tests)
│   ├── clients/              # External service clients (12 tests)
│   ├── configuration/        # Settings and config validation (7 tests)
│   ├── data_processing/      # Parsing, chunking, vector stores (8 tests)
│   ├── infrastructure/       # Core system components (8 tests)
│   ├── pipeline/             # Pipeline processing and workflows (8 tests)
│   ├── scrapers/             # Scraper implementations (19 tests)
│   └── utilities/            # Helper functions and utilities (11 tests)
├── integration/              # Integration tests (24 tests)
│   ├── api/                  # API integration tests (2 tests)
│   ├── external_systems/     # External service integrations (3 tests)
│   ├── pipeline/             # End-to-end pipeline tests (4 tests)
│   ├── security/             # Security-focused integration tests (7 tests)
│   └── (root)                # General integration tests (8 tests)
└── stack/                    # Infrastructure stack tests (9 tests)
```

## Test Categories

### Unit Tests (`tests/unit/`)

Component-level tests that verify individual classes, functions, and modules in isolation.

#### Subdirectories:

- **api_routes/**: Tests for Flask blueprints and API endpoints
  - Scraper API, RAGFlow API, Search API endpoints
  
- **backends/**: Tests for RAG backend implementations
  - AnythingLLM, Vector RAG, Backend registry
  
- **clients/**: Tests for external service clients
  - RAGFlow, Paperless, AnythingLLM, Tika, Gotenberg, FlareSolverr, LLM, Embedding clients
  
- **configuration/**: Tests for configuration management
  - Settings validation, configuration helpers, reconciliation
  
- **data_processing/**: Tests for data parsing and processing
  - Docling parsers, chunking, metadata handling, vector stores
  
- **infrastructure/**: Tests for core system infrastructure
  - Service container, scheduler, job queue, state management, main app entry point
  
- **pipeline/**: Tests for pipeline processing
  - Pipeline steps, enrichment, LLM processing, RAGFlow workflows
  
- **scrapers/**: Tests for web scraper implementations
  - Individual scrapers (AEMC, AEMO, AER, ECA, ENA, Guardian, RenewEconomy, etc.)
  - Scraper mixins, base classes, registry
  
- **utilities/**: Tests for utility functions
  - File utilities, web helpers, validation, error handling, retry logic, authentication

### Integration Tests (`tests/integration/`)

Feature-level tests that verify how multiple components work together, including external integrations.

#### Subdirectories:

- **api/**: API integration tests
  - Blueprint routing, web integration
  
- **external_systems/**: Tests for external service integrations
  - RAGFlow ingestion, AnythingLLM integration, Paperless integration
  
- **pipeline/**: End-to-end pipeline workflow tests
  - E2E flows, mocked pipelines, upload flows, failure handling
  
- **security/**: Security-focused integration tests
  - Headers, CSRF, input validation, rate limiting, auth logging, settings security

#### Root-level integration tests:

- Accessibility testing
- Bulk polling
- Docling integration
- Error handlers
- HTMX authentication
- Registry discovery
- Scheduler mocking
- Individual scraper integration (AEMC)

### Stack Tests (`tests/stack/`)

Infrastructure component tests that verify Docker services and external dependencies.

These tests verify that external services (Tika, Docling, Gotenberg, Paperless, AnythingLLM, pgvector, LLM enrichment, embedding services) are properly configured and accessible.

## Running Tests

### Run all tests:
```bash
make test
```

### Run tests by category:
```bash
make test-unit           # Run all unit tests
make test-int            # Run all integration tests
make test-stack          # Run all stack tests
```

### Run tests from a specific subdirectory:
```bash
make test-file FILE=tests/unit/scrapers/
make test-file FILE=tests/integration/security/
```

### Run a specific test file or test:
```bash
make test-file FILE=tests/unit/scrapers/test_aemc_scraper.py
make test-file FILE=tests/unit/scrapers/test_aemc_scraper.py::TestAEMCScraper::test_parse_document
```

## Test Markers

Tests are marked with pytest markers for selective execution:

- `@pytest.mark.unit`: Unit tests (fast, no external dependencies)
- `@pytest.mark.integration`: Integration tests (may use network/mocked services)
- `@pytest.mark.stack`: Stack tests (require real external services)
- `@pytest.mark.slow`: Slow-running tests

### Run tests by marker:
```bash
docker compose -f docker-compose.dev.yml exec scraper python -m pytest -m unit
docker compose -f docker-compose.dev.yml exec scraper python -m pytest -m integration
docker compose -f docker-compose.dev.yml exec scraper python -m pytest -m "not slow"
```

## Benefits of the Organization

1. **Discoverability**: Easier to find tests related to specific functionality
2. **Maintainability**: Clear ownership and responsibility for test suites
3. **Selective Testing**: Run only relevant test subsets during development
4. **Onboarding**: New developers can quickly understand the test structure
5. **IDE Navigation**: Better code navigation and test discovery in IDEs
6. **Coverage Analysis**: Easier to identify gaps in test coverage by functional area

## Adding New Tests

When adding new tests, follow these guidelines:

1. **Determine the test type**: Unit, Integration, or Stack?
2. **Choose the appropriate subdirectory** based on what's being tested
3. **Follow naming conventions**: `test_<feature>.py`
4. **Use pytest markers** to categorize the test appropriately
5. **Add `__init__.py`** if creating a new subdirectory (already present in all current subdirs)

### Example:

```python
# tests/unit/scrapers/test_my_new_scraper.py
import pytest

@pytest.mark.unit
class TestMyNewScraper:
    def test_parse_page(self):
        # Test implementation
        pass
```

## Migration Notes

The test reorganization was completed on 2026-02-13. All tests were moved from a flat structure to a hierarchical organization:

- **Integration tests**: Organized by feature type (security, pipeline, external_systems, api)
- **Unit tests**: Organized by functional area (scrapers, clients, pipeline, etc.)
- **Stack tests**: Kept flat (only 9 tests, infrastructure-focused)

No tests were modified—only moved to new locations. All `__init__.py` files were added to maintain Python package structure.
