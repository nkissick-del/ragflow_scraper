# TODO — Prioritized Roadmap

Last updated: 2026-02-09

---

## 1. Production Config & Secrets (Critical)

**Priority:** CRITICAL | **Effort:** 1h | **Type:** [Config]

Configuration fixes required before production deployment. No code changes — all environment and compose file edits.

- [ ] **Rotate all credentials** — RAGFlow, Paperless, AnythingLLM, Guardian API keys are in `.env` plaintext; regenerate after deployment
- [ ] **Enforce `SECRET_KEY`** — remove insecure default (`"dev-secret-key"`) from `config.py:119` and `docker-compose.yml:24`; fail fast if unset
- [ ] **Set `FLASK_DEBUG=0`** in production `.env` (currently `1` — enables interactive debugger)
- [ ] **Docker log rotation** — add `logging: { driver: json-file, options: { max-size: 10m, max-file: "3" } }` to all services in `docker-compose.yml`
- [ ] **Chrome resource limits** — add `mem_limit` and `cpus` to chrome service (scraper and gotenberg already have them)
- [ ] **Disable VNC in production** — remove `SE_VNC_NO_PASSWORD=1`, don't expose port 7900, or set a real password
- [ ] **Restrict service ports** — bind Selenium (4444) and Gotenberg (3156) to `127.0.0.1` or remove from production compose
- [ ] **Remove orphaned named volumes** — `scraper-data`, `scraper-config`, `scraper-logs` declared in `docker-compose.yml:119-121` but never used

---

## 2. Security Hardening (High)

**Priority:** HIGH | **Effort:** 3-4h | **Type:** [Code]

Address authentication, authorization, and header gaps found in pre-deployment audit.

- [ ] **Rate limiting** — add Flask-Limiter on `/api/scrapers/<name>/run` and auth endpoints to prevent brute-force/DoS
- [ ] **Security headers** — add `Content-Security-Policy`, `Strict-Transport-Security` (HSTS), `X-XSS-Protection` in `web/__init__.py:45-49`
- [ ] **SSRF DNS failure handling** — `settings.py:85-86` silently ignores `socket.gaierror`; log and reject instead
- [ ] **Auth bypass logging** — `auth.py:49-53` catches malformed auth header with bare `except Exception`; log decode errors for audit trail
- [ ] **Input validation tightening** — add length limits (max 255 chars) to form fields in `scrapers.py:242-280`; restrict embedding model regex

---

## 3. Resilience & Thread Safety (High)

**Priority:** HIGH | **Effort:** 4-6h | **Type:** [Code]

Harden core runtime for production reliability under load.

- [ ] **Scheduler exception guard** — `scheduler.py:235-239` has no try/except around `schedule.run_pending()`; unhandled exception kills scheduler thread permanently
- [ ] **StateTracker thread safety** — `state_tracker.py:71-81` reads `_state` dict without lock; add `threading.Lock` for concurrent read/write
- [ ] **ServiceContainer singleton lock** — `container.py:67-71` uses bare `if _instance is None`; add double-checked locking
- [ ] **Settings page timeout isolation** — `settings.py:174-200` health check HTTP calls can hang; add per-request timeout (5s) and catch exceptions per-service
- [ ] **Paperless retry logic** — `paperless_client.py:87-88` has no retry; add exponential backoff for transient 503/429/connection errors
- [ ] **Job error traceback** — `job_queue.py:73` only saves `str(exc)`; capture `traceback.format_exc()` for debugging
- [ ] **FlareSolverr session cache eviction** — `flaresolverr_client.py:64-65` grows unbounded; add TTL or LRU eviction
- [ ] **File size limits** — `tika_client.py:83-84` and `gotenberg_client.py` read full files into memory; add configurable max size check

---

## 4. Pipeline Refactor (High)

**Priority:** HIGH | **Effort:** 3-4h | **Type:** [Code]

`Pipeline._process_document()` is 276 lines (`pipeline.py:314-589`). Break into focused methods for testability and maintainability.

- [ ] Extract `_archive_document()` — upload to Paperless/archive backend
- [ ] Extract `_parse_document()` — PDF-to-markdown conversion
- [ ] Extract `_verify_document()` — poll archive until confirmed
- [ ] Extract `_ingest_to_rag()` — markdown ingestion to RAG backend
- [ ] Extract `_cleanup_local_files()` — post-verification file removal
- [ ] Add unit tests for each extracted method

---

## 5. Test Coverage (Medium)

**Priority:** MEDIUM | **Effort:** 8-12h | **Type:** [Tests]

527 tests passing but significant gaps in unit coverage. Integration tests cover happy paths; unit tests needed for edge cases and failure modes.

### Orchestrator (critical gap)
- [ ] `test_pipeline.py` — unit tests for `run()`, `_process_document()` with mocked backends
- [ ] `test_scheduler.py` — unit tests for job scheduling, error recovery, thread lifecycle

### Service clients (5 untested)
- [ ] `test_ragflow_client.py` — API interaction, retry logic, session management
- [ ] `test_flaresolverr_client.py` — Cloudflare bypass, session cache, timeout handling
- [ ] `test_settings_manager.py` — load/save, schema validation, defaults
- [ ] `test_container.py` — singleton lifecycle, backend resolution, effective config helpers
- [ ] `test_ragflow_metadata.py` — metadata preparation, field mapping

### Scrapers (11 without dedicated tests)
- [ ] Unit tests for each scraper (AEMO, AER, ECA, ENA, Guardian, RenewEconomy, The Conversation, TheEnergy)
- [ ] Unit tests for `base_scraper.py`, `mixins.py`, `models.py`

### Backends (7 without dedicated tests)
- [ ] `test_docling_parser.py`, `test_paperless_adapter.py`, `test_ragflow_adapter.py`, `test_anythingllm_adapter.py`
- [ ] Base class contract tests for `ParserBackend`, `ArchiveBackend`, `RAGBackend`

---

## 6. CI/CD Improvements (Medium)

**Priority:** MEDIUM | **Effort:** 2-3h | **Type:** [Config]

Strengthen the CI pipeline with additional scanning and enforcement.

- [ ] **SAST scanning** — add bandit or semgrep to CI workflow
- [ ] **Dockerfile linting** — add hadolint step
- [ ] **Container image scanning** — add trivy or snyk for vulnerability detection
- [ ] **Codecov threshold** — set `fail_ci_if_error: true` and minimum coverage target
- [ ] **Pin top-level deps** — `requirements.txt` uses unpinned top-level packages (constraints.txt handles transitives)
- [ ] **Makefile prod targets** — add `prod-build`, `prod-up`, `validate`, `health-check`, `push`

---

## 7. Code Quality & Deduplication (Medium)

**Priority:** MEDIUM | **Effort:** 4-6h | **Type:** [Code]

Address code smells and duplication identified in audit.

- [ ] **Scraper deduplication** — `reneweconomy` and `theenergy` are 50% similar; extract `JSONLDDateExtractionMixin`
- [ ] **Scraper deduplication** — `aer` and `eca` are 44% similar; extract `CardListPaginationMixin`
- [ ] **Split `settings.py`** (784 lines) — separate into `settings_ui.py` + `settings_api.py`
- [ ] **Split `mixins.py`** (595 lines) — separate into `download_mixin.py` + `common_mixin.py`
- [ ] **Refactor `flaresolverr_client.get_page()`** (147 lines) — extract retry loop and browser state management
- [ ] **Refactor `paperless_client.post_document()`** (139 lines) — extract multipart payload construction

---

## 8. New Scrapers

**Priority:** LOW | **Effort:** 2-3h each | **Type:** [Code]

The scraper pattern is well-established (9 scrapers, documented walkthrough). Adding new sources is straightforward.

- [ ] blog.energy-insights.com.au (per [websites_to_add.md](plans/websites_to_add.md))

---

## 9. Additional Backends (As Needed)

**Priority:** LOW | **Effort:** varies | **Type:** [Code]

Only implement when there's a concrete use case. Stubs exist in container.py for S3 and local archive.

- [ ] **Local filesystem archive** — useful for development/testing without Paperless
- [ ] **S3 archive** — cloud storage for large-scale deployments
- [ ] **MinerU parser** — alternative to Docling for specific document types

---

## 10. Backup & Restore Procedures

**Priority:** LOW | **Effort:** 2-3h | **Type:** [Local]

Deferred from Phase 4.5. State files and scraper configs are the primary data to protect.

- [ ] Document state file backup/restore procedure
- [ ] Script for exporting/importing scraper state
- [ ] Validate restore from backup works end-to-end

---

## 11. UI Polish (Low)

**Priority:** LOW | **Effort:** 2-3h | **Type:** [Code]

Minor UI/UX improvements identified in audit.

- [ ] **Custom 403 error page** — only 404 and 500 handlers exist in `web/__init__.py`
- [ ] **Accessibility** — audit remaining templates for missing ARIA labels, form labels, skip navigation

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
<summary>Phase 5 (2026-02-07 to 2026-02-08) — Backend Expansion & Quality</summary>

- Gotenberg client — HTML/Markdown/Office→PDF conversion, stack-tested
- Tika client & parser backend — 18+ format support, Dublin Core normalization, stack-tested
- Format-aware pipeline routing in ServiceContainer
- Selenium Archiver removal — deleted dead `archiver.py`, removed `bleach` dependency
- Settings UI — backend dropdowns, service URLs/timeouts, merge strategy, filename template, Tika enrichment toggle
- SandboxedEnvironment for Jinja2 templates (SSTI protection), SSRF mitigation on user-configurable URLs
- Paperless custom fields — `CUSTOM_FIELD_MAPPING`, auto-create, per-task metadata, non-fatal PATCH
- Backend Registry — `(type, name) → factory` lookup, simplified ServiceContainer properties
- Jules PR triage — reviewed 4 PRs, input validation, ARIA labels, operator precedence fix
- Tika enrichment toggle — `_run_tika_enrichment()` helper, settings UI checkbox
- **481→527 tests**, fixed 35+ pre-existing test failures

</details>

<details>
<summary>Phase 6 (2026-02-08 to 2026-02-09) — CI/CD & Security</summary>

- CI pipeline — 4 parallel jobs (lint, security, unit tests, integration tests), ruff linter, pip-audit
- Docker publish workflow — builds runtime target, pushes to GHCR on main merge
- Security hardening — HTMX 401 handling, secrets rotation guide, BASIC_AUTH in `.env.example`
- State reconciliation & disaster recovery from Paperless-ngx
- **527 tests passing** (all green locally)

</details>

---

## Current State

- **527 unit/integration tests passing** (all green locally; stack tests excluded from default collection)
- **20+ stack tests** against live services (Paperless, AnythingLLM, docling-serve, Gotenberg, Tika)
- **Parsers:** Docling (local), DoclingServe (HTTP), Tika | Stubs: MinerU
- **Archives:** Paperless-ngx (with custom fields) | Stubs: S3, Local
- **RAG:** AnythingLLM, RAGFlow
- **Conversion:** Gotenberg (HTML/MD/Office→PDF)
- **Scrapers:** 9 (AEMO, AEMC, AER, ECA, ENA, Guardian, RenewEconomy, The Conversation, TheEnergy)
- **Settings UI:** Full coverage (backend selection, service URLs/timeouts, merge strategy, filename template, Tika enrichment toggle)
- **Security:** CSRF, security headers, SSRF mitigation, input validation, Basic Auth HTMX support, secrets rotation docs
- **CI:** GitHub Actions — lint (ruff), security (pip-audit), unit tests, integration tests; Docker publish on main merge
- **Architecture:** Backend Registry pattern — adding a new backend is a single-line factory registration
- **Pre-deployment audit completed** — findings tracked in items 1-7 above
