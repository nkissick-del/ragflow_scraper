# AI Agent Reference

Purpose: Deeper background for agents when CLAUDE.md doesn’t answer a question. If you hit a failure, first re-read CLAUDE.md. If still blocked, consult this reference, then proceed minimally.

---

## System Overview

- Flask + HTMX backend (no Alpine/Vue/React), Selenium for fetching, BeautifulSoup4/trafilatura for parsing.
- Optional FlareSolverr for Cloudflare; RAGFlow for ingestion.
- Dev via Docker Compose; all commands run through Make targets.

Key services:
- `scraper` (Flask app + workers) on 5000 (dev host: 5001)
- `chrome` (Selenium) on 4444, VNC on 7900

---

## Architecture Essentials

- Service container: `app/services/container.py` provides `settings`, `ragflow_client`, `flaresolverr_client`, `state_tracker(scraper_name)`.
- Scrapers live in `app/scrapers/` and inherit from `BaseScraper`.
- State tracking per scraper ensures de-duplication (processed URLs persisted under `/app/data/state`).
- Metadata formatting and validation centralized in `app/services/ragflow_metadata.py`.

References:
- Config & services: docs/CONFIG_AND_SERVICES.md
- Metadata schema: docs/METADATA_SCHEMA.md
- Logging standards: docs/LOGGING_AND_ERROR_STANDARDS.md
- Scraper template: docs/SCRAPER_TEMPLATE.md

---

## Dev Environment & Commands

- Start dev stack:
  - Build: `make dev-build`
  - Run: `make dev-up`
- Shell/logs:
  - `make shell`
  - `make logs`
- Tests:
  - All: `make test`
  - Unit: `make test-unit`
  - Integration: `make test-int`
  - Single file/case: `make test-file FILE=tests/unit/test_x.py::TestClass::test_case`
- UI & services:
  - App: http://localhost:5001
  - Selenium: http://localhost:4444/wd/hub/status

Notes:
- `tests/` and `docs/` are bind-mounted in dev; edits don’t require rebuild.
- Rebuild only when dependencies change or you add new Python files.

---

## Testing Workflow

- Smallest-first: run the most specific test you can.
- Validate inside container via Make targets.
- If you add files or change requirements:
  - `make dev-build && make dev-up`
- Integration tests may require network and Selenium.

---

## Logging & Error Handling

- Use structured logging helpers in `app/utils/logging_config.py` (`get_logger`, `log_event`, `log_exception`).
- Default JSONL with rotation under `/app/data/logs`.
- When catching errors in scrapers or services, log with context, continue when safe.

See: docs/LOGGING_AND_ERROR_STANDARDS.md

---

## Metadata Essentials

- Source object: `DocumentMetadata` in `app/scrapers/base_scraper.py`.
- Prepare/validate: `prepare_metadata_for_ragflow()`, `validate_metadata()` in `app/services/ragflow_metadata.py`.
- Required fields (RAGFlow): `organization` (fallback "Unknown"), `source_url`, `scraped_at`, `document_type` (fallback "Unknown").
- Optional fields only when present (omit null/empty).

See: docs/METADATA_SCHEMA.md and docs/TODO-metadata-testing.md

---

## Common Pitfalls & Fixes

- Running outside dev container: Tests or paths fail. Fix: always use Make targets.
- Missing rebuild after dependency/new file: Import/ModuleNotFound errors. Fix: `make dev-build && make dev-up`.
- State duplication: URLs processed twice. Fix: use `state_tracker` consistently; reset state file only as last resort.
- Cloudflare pages: Empty/blocked HTML. Fix: enable FlareSolverr in settings or fall back to requests where possible.
- Test fragility on call ordering: Assert counts before creating new instances (e.g., factory caches).

---

## Quick Troubleshooting Checklist

1) Is the dev stack running? `make dev-up`  
2) Can you reach the app? `curl -sS http://localhost:5001/ | head -5`  
3) Is Selenium healthy? `curl -sS http://localhost:4444/wd/hub/status`  
4) Can you run a single test? `make test-file FILE=tests/unit/test_x.py::TestY::test_z`  
5) Did you change requirements or add files? Rebuild.  
6) Review logs: `make logs` and filter for your component.  
7) Re-read CLAUDE.md; if not covered, use this reference.

---

## Useful Commands

- List scrapers: `docker compose -f docker-compose.dev.yml exec scraper python scripts/run_scraper.py --list-scrapers`
- Dry-run a scraper: `docker compose -f docker-compose.dev.yml exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run`
- Tail logs: `make logs`
- Container shell: `make shell`

---

Last Updated: 2026-01-07
