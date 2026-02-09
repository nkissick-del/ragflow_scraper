# TODO — Prioritized Roadmap

Last updated: 2026-02-09

---

## 1. Security Hardening ~~(High)~~ DONE

**Priority:** ~~HIGH~~ DONE | **Effort:** 3-4h | **Type:** [Code]

Address authentication, authorization, and header gaps found in pre-deployment audit.

- [x] **Rate limiting** — Flask-Limiter on scraper-run (10/min), search (30/min); custom 429 error handler
- [x] **Security headers** — CSP, Permissions-Policy, HSTS (HTTPS-only), X-XSS-Protection: 0 (OWASP)
- [x] **SSRF DNS failure handling** — `socket.gaierror` now logs warning and rejects URL
- [x] **Auth bypass logging** — malformed auth headers log `auth.header.malformed` with remote addr (never raw creds)
- [x] **Input validation tightening** — URL length (2048), field length (255), template length (1024), timeout/retry ranges, chunk token ranges
- [x] **Error handlers** — custom 403/404/429/500/CSRF pages with JSON content negotiation for API clients

---

## 2. Resilience & Thread Safety (High)

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

## 3. Pipeline Refactor (High)

**Priority:** HIGH | **Effort:** 3-4h | **Type:** [Code]

`Pipeline._process_document()` is 276 lines (`pipeline.py:314-589`). Break into focused methods for testability and maintainability.

- [ ] Extract `_archive_document()` — upload to Paperless/archive backend
- [ ] Extract `_parse_document()` — PDF-to-markdown conversion
- [ ] Extract `_verify_document()` — poll archive until confirmed
- [ ] Extract `_ingest_to_rag()` — markdown ingestion to RAG backend
- [ ] Extract `_cleanup_local_files()` — post-verification file removal
- [ ] Add unit tests for each extracted method

---

## 4. Test Coverage (Medium)

**Priority:** MEDIUM | **Effort:** 8-12h | **Type:** [Tests]

662 tests passing but significant gaps in unit coverage. Integration tests cover happy paths; unit tests needed for edge cases and failure modes.

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

## 5. CI/CD Improvements (Medium)

**Priority:** MEDIUM | **Effort:** 2-3h | **Type:** [Config]

Strengthen the CI pipeline with additional scanning and enforcement.

- [ ] **SAST scanning** — add bandit or semgrep to CI workflow
- [ ] **Dockerfile linting** — add hadolint step
- [ ] **Container image scanning** — add trivy or snyk for vulnerability detection
- [ ] **Codecov threshold** — set `fail_ci_if_error: true` and minimum coverage target
- [ ] **Pin top-level deps** — `requirements.txt` uses unpinned top-level packages (constraints.txt handles transitives)
- [ ] **Makefile prod targets** — add `prod-build`, `prod-up`, `validate`, `health-check`, `push`

---

## 6. Code Quality & Deduplication (Medium)

**Priority:** MEDIUM | **Effort:** 4-6h | **Type:** [Code]

Address code smells and duplication identified in audit.

- [ ] **Scraper deduplication** — `reneweconomy` and `theenergy` are 50% similar; extract `JSONLDDateExtractionMixin`
- [ ] **Scraper deduplication** — `aer` and `eca` are 44% similar; extract `CardListPaginationMixin`
- [ ] **Split `settings.py`** (784 lines) — separate into `settings_ui.py` + `settings_api.py`
- [ ] **Split `mixins.py`** (595 lines) — separate into `download_mixin.py` + `common_mixin.py`
- [ ] **Refactor `flaresolverr_client.get_page()`** (147 lines) — extract retry loop and browser state management
- [ ] **Refactor `paperless_client.post_document()`** (139 lines) — extract multipart payload construction

---

## 7. New Scrapers

**Priority:** LOW | **Effort:** 2-3h each | **Type:** [Code]

The scraper pattern is well-established (9 scrapers, documented walkthrough). Adding new sources is straightforward.

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

- [ ] Document state file backup/restore procedure
- [ ] Script for exporting/importing scraper state
- [ ] Validate restore from backup works end-to-end

---

## 10. UI Polish (Low)

**Priority:** LOW | **Effort:** 2-3h | **Type:** [Code]

Minor UI/UX improvements identified in audit.

- [x] **Custom error pages** — 403, 404, 429, 500, CSRF handlers with JSON/HTML content negotiation
- [ ] **Accessibility** — audit remaining templates for missing ARIA labels, form labels, skip navigation

---

## 11. Future Considerations

**Priority:** WATCH | **Type:** [Research]

Technology to monitor for potential future adoption. Not actionable yet.

- [ ] **Docling DocTags format** — IBM's LLM-optimized document representation ([discussion](https://github.com/docling-project/docling/discussions/354), [announcement](https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion)). Uses XML-like tags with bounding box coordinates to preserve visual structure and element relationships (caption→figure linking, reading order). Currently designed for LLM fine-tuning and layout-aware tasks — overkill for text-based RAG chunking. However, as Granite-Docling matures, DocTags could enable richer chunk metadata (e.g., "this chunk contains a table from page 3, related to figure 2") which would improve retrieval precision for complex documents. Revisit when DocTags→chunk pipelines become standardized.

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
- Production config hardening — SECRET_KEY enforcement, Docker log rotation, Chrome resource limits, VNC/port removal
- State reconciliation & disaster recovery from Paperless-ngx
- **527 tests passing** (all green locally)

</details>

<details>
<summary>Phase 7 (2026-02-09) — pgvector RAG Pipeline</summary>

Self-owned chunking → embedding → pgvector pipeline replacing RAGFlow/AnythingLLM as required RAG infrastructure. RAG platforms become optional frontends; any LLM can query the corpus directly via REST API or MCP.

- **1.1** Embedding client — `EmbeddingClient` ABC with `OllamaEmbeddingClient` (POST /api/embed) and `APIEmbeddingClient` (OpenAI-compatible /v1/embeddings), factory function, batch support (batch_size=32), 29 unit tests, stack test
- **1.2** Chunking module — `ChunkingStrategy` ABC with `FixedChunker` (word-boundary splitting, overlap, heading context detection) and `HybridDoclingChunker` (falls back to Fixed), factory function, 24 unit tests
- **1.3** pgvector storage client — `PgVectorClient` with psycopg connection pooling, partitioned `document_chunks` table (one partition per source), HNSW indexes, cosine similarity search with source/metadata filtering, 20 unit tests, stack test
- **1.4** PgVector RAG backend — `PgVectorRAGBackend` implements `RAGBackend` ABC (chunk → embed → store), registered in backend registry, Settings UI fields for embedding/chunking/pgvector config, `.env.example` + `docker-compose.yml` updated, 19 unit tests
- **1.5** Search API & UI — Flask blueprint with `POST /api/search`, `GET /api/sources`, `GET /api/search/document/<source>/<filename>`, HTMX search page with source checkboxes and similarity scores, CSRF-exempt, 6 unit tests
- **1.6** Backfill script — `scripts/backfill_vectors.py` fetches from Paperless API, chunks, embeds, stores; supports `--source`, `--dry-run`, `--skip-existing`
- **1.7** MCP server — `mcp_server/` FastAPI service with `search_documents`, `list_sources`, `get_document` tool endpoints; separate process sharing same pgvector + embedding modules
- Config: `DATABASE_URL`, `EMBEDDING_BACKEND/MODEL/URL/API_KEY/DIMENSIONS/TIMEOUT`, `CHUNKING_STRATEGY`, `CHUNK_MAX_TOKENS/OVERLAP_TOKENS`
- Dependencies: `psycopg[binary]`, `psycopg-pool`, `pgvector`
- 9 CodeRabbit review passes (22→11→12→15→11→8→3→4→7 findings) — thread-safe lazy init, SQL savepoints, path traversal prevention, SSRF validation, input sanitization, defensive API handling, resource cleanup, partition atomicity
- **527→625 tests**, pyright 0 errors

</details>

<details>
<summary>Phase 8 (2026-02-09) — Security Hardening</summary>

Closed all 5 TODO Section 1 items + error handlers + numeric range validation. CodeRabbit review pass: 2 findings → 0.

- **Auth logging** — `auth.header.malformed` warning on decode errors (never logs raw credentials)
- **SSRF hardening** — DNS failures now log + reject (was silent `pass`)
- **Security headers** — CSP (self + unpkg HTMX), Permissions-Policy (camera/mic/geo/payment disabled), HSTS (HTTPS-only via `request.is_secure`), X-XSS-Protection: 0 (OWASP guidance)
- **Rate limiting** — Flask-Limiter: scraper run 10/min, search 30/min; `RATELIMIT_ENABLED=False` in all existing test fixtures
- **Input validation** — URL length 2048, field length 255, template length 1024, FlareSolverr timeout 1-600 + max≥timeout, scraping delay 0-60/timeout 1-600/retry 0-10, chunk tokens 1-8192/overlap 0-4096
- **Error handlers** — 403/404/429/500/CSRF with JSON/HTML content negotiation via `request.accept_mimetypes`; 5 error templates extending `base.html`
- **Dependencies** — Flask-Limiter 4.1.1
- **625→662 tests**, pyright 0 errors, CodeRabbit 0 findings

</details>

---

## Current State

- **662 unit/integration tests passing** (all green locally; stack tests excluded from default collection)
- **20+ stack tests** against live services (Paperless, AnythingLLM, docling-serve, Gotenberg, Tika, Ollama, pgvector)
- **Parsers:** Docling (local), DoclingServe (HTTP), Tika | Stubs: MinerU
- **Archives:** Paperless-ngx (with custom fields) | Stubs: S3, Local
- **RAG:** pgvector (self-owned), AnythingLLM, RAGFlow
- **Embedding:** Ollama, OpenAI-compatible API
- **Chunking:** Fixed (word-boundary with overlap), Hybrid (Docling fallback)
- **Search:** REST API (`/api/search`, `/api/sources`) + HTMX web UI + MCP server
- **Conversion:** Gotenberg (HTML/MD/Office→PDF)
- **Scrapers:** 9 (AEMO, AEMC, AER, ECA, ENA, Guardian, RenewEconomy, The Conversation, TheEnergy)
- **Settings UI:** Full coverage (backend selection, service URLs/timeouts, merge strategy, filename template, Tika enrichment toggle, embedding/chunking/pgvector config)
- **Security:** CSRF, CSP, Permissions-Policy, HSTS, SSRF mitigation, rate limiting (Flask-Limiter), input validation (length/range), custom error handlers (403/404/429/500/CSRF), Basic Auth HTMX support, secrets rotation docs
- **CI:** GitHub Actions — lint (ruff), security (pip-audit), unit tests, integration tests; Docker publish on main merge
- **Architecture:** Backend Registry pattern — adding a new backend is a single-line factory registration
- **Infrastructure:** Unraid (192.168.1.101) — Paperless (:8000), PostgreSQL+pgvector (:5432), Ollama (:11434), AnythingLLM (:3151), docling-serve (:4949)
