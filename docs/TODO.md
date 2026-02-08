# TODO — Prioritized Roadmap

Last updated: 2026-02-09

---

## ~~1. Settings UI — Close Configuration Gaps~~ DONE

Completed 2026-02-07. See [Completed Work](#completed-work) for details.

---

## ~~2. Paperless Custom Fields~~ DONE

Completed 2026-02-08. See [Completed Work](#completed-work) for details.

---

## ~~3. Tika Metadata Enrichment Pipeline~~ DONE

Completed 2026-02-08. See [Completed Work](#completed-work) for details.

---

## ~~4. Backend Registry Pattern~~ DONE

Completed 2026-02-08. See [Completed Work](#completed-work) for details.

---

## ~~5. CI/CD Pipeline~~ DONE

Completed 2026-02-08. See [Completed Work](#completed-work) for details.

---

## ~~6. Security Hardening~~ DONE

Completed 2026-02-09. See [Completed Work](#completed-work) for details.

---

## 7. New Scrapers

**Priority:** LOW | **Effort:** 2-3h each | **Type:** [Code]

The scraper pattern is well-established (9 scrapers, documented walkthrough). Adding new sources is straightforward.

**Identified targets:**
- [ ] blog.energy-insights.com.au (per [websites_to_add.md](plans/websites_to_add.md))

---

## 8. Additional Backends (As Needed)

**Priority:** LOW | **Effort:** varies | **Type:** [Code]

Only implement when there's a concrete use case. Stubs exist in container.py for S3 and local archive.

- [ ] **Local filesystem archive** — useful for development/testing without Paperless
- [ ] **S3 archive** — cloud storage for large-scale deployments
- [ ] **MinerU parser** — alternative to Docling for specific document types

---

## 9. Backup & Restore Procedures

**Priority:** LOW | **Effort:** 2-3h | **Type:** [Local]

Deferred from Phase 4.5. State files and scraper configs are the primary data to protect.

**Tasks:**
- [ ] Document state file backup/restore procedure
- [ ] Script for exporting/importing scraper state
- [ ] Validate restore from backup works end-to-end

---

## Completed Work

<details>
<summary>Phase 1-3 (2026-01-07 to 2026-01-08) — Core Refactoring & Documentation</summary>

- ServiceContainer: property-only API, removed legacy getters
- BaseScraper: 6 mixins extracted (Incremental, Exclusion, WebDriver, Cloudflare, MetadataIO, HttpDownload)
- Data models consolidated in `app/scrapers/models.py`
- All 10 scrapers migrated to new structure
- Blueprint modularization (6 blueprints from monolithic routes.py)
- JobQueue: async management with per-scraper exclusivity
- RAGFlowIngestionWorkflow extracted with full upload/poll/metadata workflow
- 7 documentation guides (~1,700 lines)
- 140 tests passing

</details>

<details>
<summary>Phase 4 (2026-02-05 to 2026-02-07) — Pre-Deployment Readiness</summary>

- **4.1** AnythingLLM backend — full implementation, 41 tests, live-validated
- **4.2** Paperless metadata — correspondent/tag ID lookup with caching, 24 tests
- **4.3** Jinja2 filename templating — custom filters (slugify, shorten, secure_filename)
- **4.4** Testing & QA — 30+ integration tests, config audit (40% UI coverage, 12 gaps)
- **4.5** Stack tests — 15 tests against live Unraid services, DoclingServeParser backend, bug fixes

</details>

<details>
<summary>Post-Phase 4 (2026-02-07) — Gotenberg & Tika</summary>

- Gotenberg client — HTML/Markdown/Office→PDF conversion, stack-tested
- Tika client & parser backend — 18+ format support, Dublin Core normalization, stack-tested
- Format-aware pipeline routing in ServiceContainer
- **Selenium Archiver removal** — deleted dead `archiver.py`, removed `bleach` dependency, added Gotenberg to docker-compose, Chrome retained for scraping only

</details>

<details>
<summary>Settings UI (2026-02-07) — Close Configuration Gaps</summary>

- Pipeline Backends section (read-only badges for parser/archive/RAG/conversion)
- Service Health section with connection test buttons (Gotenberg, Tika, Paperless, Docling-serve, AnythingLLM)
- Pipeline Settings section (editable merge strategy dropdown + filename template editor with live preview)
- Settings overrides persist to `settings.json` pipeline section, read at pipeline execution time
- SandboxedEnvironment for Jinja2 templates (SSTI protection), markupsafe escaping (XSS protection)
- Fixed pre-existing integration test infrastructure (27/27 blueprint route tests now pass)
- Backend selection dropdowns (parser/archive/RAG) — editable with immediate `reset_services()` effect
- Service URL + timeout configuration — editable for all 6 services, persisted to `settings.json`
- `ServiceContainer` helper methods (`_get_effective_backend`, `_get_effective_url`, `_get_effective_timeout`)
- API keys/tokens remain in `.env` only — never exposed in UI or settings.json
- SSRF mitigation — blocks link-local/cloud metadata IPs in user-configurable service URLs
- Fixed 8 outdated/broken integration tests (pipeline e2e, mocked, failure_flow, upload_flow, scheduler, accessibility, CSRF, web_integration)
- Safe patch cleanup in all test fixtures (track started patches for reliable teardown)

</details>

<details>
<summary>Paperless Custom Fields (2026-02-08)</summary>

- `CUSTOM_FIELD_MAPPING` in `paperless_client.py` — maps metadata keys (url, scraped_at, page_count, file_size, source_page) to Paperless custom field names and data types
- `_fetch_custom_fields()`, `get_or_create_custom_field()`, `set_custom_fields()` — cache-first pattern with auto-creation (same as correspondents/tags)
- Metadata stored per-task in `PaperlessArchiveBackend._pending_metadata` (keyed by task_id, bounded at 100 entries), applied via `PATCH /api/documents/{id}/` after verification
- Non-fatal: custom field failure doesn't prevent document verification
- 18 unit tests (fetch, get/create, set) + 6 integration tests (cache, auto-create, PATCH, full flow, non-fatal failure)
- Fixed 6 pre-existing test failures: 3 in TestPaperlessVerification (wrong endpoint mock), 3 in TestPostDocumentWithLookups (missing mock headers)

</details>

<details>
<summary>Jules PR Review & Input Validation (2026-02-08)</summary>

- Reviewed 4 Jules PRs (#28, #30, #31, #32); closed 2 stale/duplicate, selectively merged 2
- Scraper blueprint input validation: `re.match(r'^[a-zA-Z0-9_-]+$', name)` on all `<name>` endpoints
- `max_pages` positivity validation and operator precedence bug fix
- Existence checks before saving scraper RAGFlow/Cloudflare settings (prevents `settings.json` pollution)
- ARIA labels on all scraper action buttons (Run, Cancel, Preview, Configure) for accessibility
- CI workflow fix: added `BASIC_AUTH_ENABLED=false` env var to GitHub Actions
- 6 new security validation integration tests

</details>

<details>
<summary>Tika Enrichment — Tests + Settings UI Toggle (2026-02-08)</summary>

- Extracted `_run_tika_enrichment()` helper in `pipeline.py` — encapsulates enrichment logic, reads settings override before Config fallback
- Settings UI toggle for `TIKA_ENRICHMENT_ENABLED` — checkbox in Pipeline Settings section, persisted as `pipeline.tika_enrichment_enabled` in `settings.json`
- `settings_manager.py` — added `tika_enrichment_enabled` to defaults + schema (string type: empty = env var, "true"/"false" = override)
- 9 unit tests (`test_pipeline_enrichment.py`): fill missing keys, no overwrite, disabled config, no URL, office skip, failure non-fatal, empty response, settings override enable/disable
- Fixed `test_web_integration.py` — patched `app.container.get_container` before runtime import (was crashing on `/app/data/logs/`), fixed wrong 302 assertion (root route serves 200)

</details>

<details>
<summary>Backend Registry Pattern (2026-02-08)</summary>

- Created `app/services/backend_registry.py` — `BackendRegistry` class with `(type, name) → factory` lookup table
- 9 factory functions (docling, docling_serve, tika, mineru, paperless, s3, local, ragflow, anythingllm) — factories receive `ServiceContainer` instance, access Config only through container helpers
- Added `_get_config_attr()` helper to `ServiceContainer`
- Simplified `parser_backend`, `archive_backend`, `rag_backend` properties from ~35 lines each to ~12 lines each
- 10 new unit tests (`test_backend_registry.py`)
- Comprehensive test audit: fixed 35 pre-existing test failures
  - 7 Config fallback failures — patched Config in test modules to prevent `.env` fallback
  - 27 blueprint auth failures — added auth credential patches to `app` fixture
  - 1 pyright failure — fixed `pyrightconfig.json` venv settings + 16 type errors across 9 files
- **481 tests, 0 failures** (all green locally)

</details>

<details>
<summary>CI/CD Pipeline (2026-02-08)</summary>

- Replaced `.github/workflows/test.yml` with `.github/workflows/ci.yml` — 4 parallel jobs: lint (ruff), security (pip-audit), unit-tests (pytest + Codecov), integration-tests
- Added ruff linter (`ruff.toml` with E+F rules), auto-fixed 70 violations + 6 manual fixes across app/ and tests/
- Created `.github/workflows/docker-publish.yml` — builds `runtime` target, pushes to `ghcr.io/nkissick-del/ragflow_scraper` with `latest` + SHA tags on main merge
- Fixed Dockerfile OCI source label
- Added CI + Codecov badges to README.md
- Upgraded actions/cache v3→v4, codecov-action v3→v4

</details>

<details>
<summary>Security Hardening (2026-02-09)</summary>

- HTMX 401 handling — `handleHTMXErrors()` now detects 401 status and triggers `window.location.reload()` to invoke the browser's native Basic Auth dialog (previously showed generic error toast)
- 4 HTMX auth integration tests: unauthenticated 401, valid credentials 200, bad credentials 401, auth-disabled 200
- Secrets rotation guide (`docs/operations/SECRETS_ROTATION.md`) — per-credential instructions for all 11 secrets: generate, apply, impact, verify
- Cross-linked from DEPLOYMENT_GUIDE.md and RUNBOOK_COMMON_OPERATIONS.md
- Added `BASIC_AUTH_*` variables to `.env.example`

</details>

---

## Current State

- **497 unit/integration tests passing** (all green locally; stack tests excluded from default collection)
- **20+ stack tests** against live services (Paperless, AnythingLLM, docling-serve, Gotenberg, Tika)
- **Parsers:** Docling (local), DoclingServe (HTTP), Tika | Stubs: MinerU
- **Archives:** Paperless-ngx (with custom fields) | Stubs: S3, Local
- **RAG:** AnythingLLM, RAGFlow
- **Conversion:** Gotenberg (HTML/MD/Office→PDF)
- **Scrapers:** 9 (AEMO, AEMC, AER, ECA, ENA, Guardian, RenewEconomy, The Conversation, TheEnergy)
- **Settings UI:** Full coverage (backend selection dropdowns, service URLs/timeouts, merge strategy, filename template, Tika enrichment toggle — all editable with immediate effect)
- **Security:** CSRF, security headers, SSRF mitigation, input validation, Basic Auth HTMX support, secrets rotation docs
- **CI:** GitHub Actions — lint (ruff), security (pip-audit), unit tests, integration tests; Docker publish on main merge
- **Architecture:** Backend Registry pattern — adding a new backend is a single-line factory registration
- **No current blockers** — system is deployable
