# TODO — Prioritized Roadmap

Last updated: 2026-02-10

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

## 2. Resilience & Thread Safety ~~(High)~~ DONE

**Priority:** ~~HIGH~~ DONE | **Effort:** ~~4-6h~~ 0 | **Type:** [Code]

Harden core runtime for production reliability under load.

- [x] **Scheduler exception guard** — try/except around `schedule.run_pending()` with `log_exception()` — scheduler thread survives exceptions
- [x] **StateTracker thread safety** — `threading.RLock` wrapping all 12 methods that touch `_state`; `copy.deepcopy()` on all getters
- [x] **ServiceContainer singleton lock** — double-checked locking on `__new__()`, `_trackers_lock` for `state_tracker()`, locks in `reset()`/`reset_container()`
- [x] **Settings page timeout isolation** — `settings.py:174-200` health check HTTP calls now have `timeout=10` and `_check_service_status()` wrapper catches all exceptions per-service
- [x] **Paperless retry logic** — `urllib3.util.retry.Retry` adapter on session (GET-only, 3 retries, backoff=1s, status 429/500/502/503/504)
- [x] **Job error traceback** — `traceback.format_exc()` captures full stack trace instead of `str(exc)`
- [x] **FlareSolverr session cache eviction** — TTL (3600s) + LRU (max 50) eviction via `_evict_stale_sessions()` called at start of `get_page()`
- [x] **File size limits** — `MAX_UPLOAD_FILE_SIZE` env var (default 500MB, 0=disabled); guards in `TikaClient` and `GotenbergClient` using `getattr()` for safe access

---

## 3. Pipeline Refactor ~~(High)~~ DONE

**Priority:** ~~HIGH~~ DONE | **Effort:** ~~3-4h~~ 0 | **Type:** [Code]

`Pipeline._process_document()` was 276 lines (`pipeline.py:314-589`). Broken into 6 focused methods with `_process_document()` as a ~45-line orchestrator.

- [x] Extract `_parse_document()` — PDF/markdown/office-to-markdown conversion with Tika enrichment
- [x] Extract `_prepare_archive_file()` — Gotenberg PDF conversion for non-PDF documents
- [x] Extract `_archive_document()` — upload to Paperless/archive backend
- [x] Extract `_verify_document()` — poll archive until confirmed
- [x] Extract `_ingest_to_rag()` — markdown ingestion to RAG backend
- [x] Extract `_cleanup_local_files()` — post-verification file removal with orphan warning
- [x] Add unit tests for each extracted method (28 tests in `test_pipeline_steps.py`)

---

## 4. Test Coverage ~~(Medium)~~ DONE

**Priority:** ~~MEDIUM~~ DONE | **Effort:** ~~8-12h~~ 0 | **Type:** [Tests]

984 tests passing. All identified coverage gaps closed — orchestrator, service clients, scrapers, and data models now have dedicated unit tests.

### Orchestrator ~~(critical gap)~~ DONE
- [x] `test_pipeline_steps.py` — 28 unit tests for extracted pipeline methods (`_parse_document`, `_prepare_archive_file`, `_archive_document`, `_verify_document`, `_ingest_to_rag`, `_cleanup_local_files`)
- [x] `test_pipeline_enrichment.py` — 10 tests for Tika enrichment helper
- [x] `test_pipeline_run.py` — 19 unit tests for `run()` orchestration logic (scraper failures, document processing, error recovery, status determination, preflight reconciliation, finalization)
- [x] `test_scheduler.py` — 24 unit tests for job scheduling, cron parsing, start/stop lifecycle, load from config, error recovery

### Service clients DONE
- [x] `test_ragflow_client.py` — 18 tests: HttpAdapter retry/auth, client init, list_datasets, upload, check_exists, wait_for_ready, test_connection, catalogs
- [x] `test_flaresolverr_client.py` — 27 tests: properties, get_page (success/error/timeout/unconfigured), session management, test_connection, metrics, cache eviction
- [x] `test_settings_manager.py` — 21 tests: singleton, load/save, dot-notation get/set, sections, merge_defaults, properties, scraper settings
- [x] `test_container.py` — covered by `test_service_container.py` + `test_container_refactoring.py` (23 tests)
- [x] `test_ragflow_metadata.py` — covered by `test_ragflow_upload_metadata.py` (2 tests)

### Scrapers DONE
- [x] Unit tests for each scraper — `test_aemo_scraper.py` (16), `test_aer_scraper.py` (15), `test_aemc_scraper.py` (16), `test_eca_scraper.py` (16), `test_ena_scraper.py` (17), `test_guardian_scraper.py` (16), `test_reneweconomy_scraper.py` (18), `test_the_conversation_scraper.py` (15), `test_theenergy_scraper.py` (18)
- [x] `test_base_scraper.py` — 9 tests: run lifecycle, cancellation, finalize_result
- [x] `test_models.py` — 9 tests: DocumentMetadata (fields, defaults, to_dict, merge strategies), ScraperResult (defaults, to_dict, to_json)
- [x] `test_scraper_mixins.py` (18 tests), `test_download_mixin.py`, `test_metadata_io.py` — mixin coverage exists

### Backends DONE
- [x] Docling — `test_docling_headings.py`, `test_docling_integration.py`, `test_docling_serve_parser.py` (16 tests)
- [x] Tika — `test_tika_parser.py`, `test_tika_client.py` (20+ tests)
- [x] Paperless — `test_paperless_client.py`, `test_paperless_query.py`, `test_paperless_integration.py` (43+ tests)
- [x] RAGFlow — `test_ragflow_client.py` (18), `test_ragflow_ingestion_workflow.py`, `test_ragflow_ingestion.py` (58 tests total)
- [x] AnythingLLM — `test_anythingllm_backend.py`, `test_anythingllm_client.py` (22+ tests)
- [x] pgvector — `test_pgvector_backend.py`, `test_pgvector_client.py` (39+ tests)
- [x] Base class contract tests — `test_backend_abstractions.py` (23 tests)

---

## 5. CI/CD Improvements ~~(Medium)~~ ~~(High)~~ DONE

**Priority:** ~~HIGH~~ DONE | **Effort:** ~~1-2h~~ 0 | **Type:** [Config]

All CI/CD items resolved. Pipeline fully green.

### CI green baseline
- [x] **Codecov token** — added `CODECOV_TOKEN` secret and `token:` parameter to codecov-action v4
- [x] **constraints.txt pip 26 fix** — removed extras syntax (`psycopg[binary]`) incompatible with pip 26.0.1
- [x] **Unit test CI failures** — `test_basic_auth.py` now has proper mocking via `_make_app()` helper; CI sets `BASIC_AUTH_ENABLED=false`, `LOG_TO_FILE=false`, `SECRET_KEY`
- [x] **Integration test collection errors** — added `responses` and `requests-toolbelt` to `requirements-dev.txt`; `test_scraper_registry.py` uses lazy `_get_logger()` class method
- [x] **pip-audit security job** — verified passing locally and in CI; `setuptools>=70.0.0` pinned in `constraints.txt`

### CI enhancements
- [x] **Codecov threshold** — `codecov.yml` sets project: 50% target / 5% threshold, patch: 60% target / 5% threshold; `fail_ci_if_error: true` in CI
- [x] **SAST scanning** — covered by ruff `S` rules (bandit equivalent) in `ruff.toml`; runs in lint job
- [x] **Dockerfile linting** — `hadolint/hadolint-action@v3.1.0` in `dockerfile-lint` job
- [x] **Container image scanning** — `aquasecurity/trivy-action@0.28.0` with `ignore-unfixed: true`; base image updated to `python:3.11-slim-bookworm` for latest security patches
- [x] **Pin top-level deps** — all packages in `requirements.txt` now pinned (e.g., `flask==3.0.3`, `selenium==4.25.0`) with `-c constraints.txt` for transitives
- [x] **Makefile prod targets** — `prod-build`, `prod-up`, `prod-down`, `validate`, `health-check` all implemented

---

## 6. Code Quality & Deduplication ~~(Medium)~~ DONE

**Priority:** ~~MEDIUM~~ DONE | **Effort:** ~~4-6h~~ 0 | **Type:** [Code]

Address code smells and duplication identified in audit.

- [x] **Refactor `flaresolverr_client.get_page()`** (147→~40 lines) — extracted `_execute_request`, `_handle_success_response`, `_handle_error_response`, `_handle_request_failure`
- [x] **Refactor `paperless_client.post_document()`** (139→~60 lines) — extracted `_resolve_tag_ids`, `_extract_task_id_from_response`, `_validate_task_id`
- [x] **Scraper deduplication** — `reneweconomy` and `theenergy` JSON-LD date extraction → `JSONLDDateExtractionMixin` (`app/scrapers/jsonld_mixin.py`), 20 mixin tests
- [x] **Scraper deduplication** — `aer` and `eca` card pagination → `CardListPaginationMixin` (`app/scrapers/card_pagination_mixin.py`), 12 mixin tests
- [x] **Split `mixins.py`** (599 lines) → `download_mixin.py` + `common_mixins.py` + re-export shim
- [x] **Split `settings.py`** (969 lines) → `settings/` sub-package with `helpers.py`, `ui.py`, `api.py`, `reconciliation.py`

---

## 7. LLM-Powered Document Enrichment ~~(Medium)~~ DONE

**Priority:** ~~MEDIUM~~ DONE | **Effort:** ~~6-8h~~ 0 | **Type:** [Code]

Two-tier LLM enrichment using local Ollama models (7-8B params, 128k context). Uses the same Ollama instance already deployed for embeddings. Both tiers optional (default off), non-fatal on failure.

### Tier 1 — Document-level metadata extraction DONE

- [x] **`LLMClient` ABC + implementations** — `app/services/llm_client.py`: `OllamaLLMClient` (POST `/api/chat`), `APILLMClient` (POST `/v1/chat/completions`), `create_llm_client()` factory. Mirrors `embedding_client.py` pattern
- [x] **`DocumentEnrichmentService`** — `app/services/document_enrichment.py`: `enrich_metadata()` reads markdown, truncates to token limit, calls LLM with structured JSON prompt. Returns dict or None on failure
- [x] **Config env vars** — `LLM_BACKEND`, `LLM_MODEL`, `LLM_URL` (falls back to `EMBEDDING_URL`), `LLM_API_KEY`, `LLM_TIMEOUT`, `LLM_ENRICHMENT_ENABLED`, `LLM_ENRICHMENT_MAX_TOKENS`. Validation in `Config.validate()`
- [x] **`llm_client` property in ServiceContainer** — lazy-loading, URL fallback to `EMBEDDING_URL`, added to `reset_services()`
- [x] **Pipeline integration** — `_run_llm_enrichment()` after `_run_tika_enrichment()`, fill-gaps merge (title, document_type), tags dedup, list→string conversion for Paperless custom fields
- [x] **Paperless custom fields** — 4 new `CUSTOM_FIELD_MAPPING` entries: LLM Summary, LLM Keywords, LLM Entities, LLM Topics
- [x] **Settings UI** — LLM Enrichment section in Pipeline Settings (toggles, backend, model, max tokens, window) + LLM service row in Services card (URL, timeout, test button, status badge)
- [x] **Unit tests** — 30 tests (`test_llm_client.py`), 17 tests (`test_document_enrichment.py`), 10 tests (`test_pipeline_llm_enrichment.py`)

### Tier 2 — Chunk-level contextual enrichment DONE

- [x] **`enrich_chunks()` method** — in `DocumentEnrichmentService`. Short docs: full text context. Long docs: outline + surrounding chunks (windowed). Per-chunk fallback on failure
- [x] **`_apply_contextual_enrichment()` in pgvector adapter** — enriched texts used for embedding, raw `chunk.content` preserved for storage. Config + settings override toggle
- [x] **Backfill support** — `scripts/backfill_vectors.py` `--enrich` flag with `_apply_contextual_enrichment_backfill()` helper
- [x] **Unit tests** — 8 tests (`test_contextual_enrichment.py`): toggle on/off, settings override, LLM not configured, failure fallback, enriched vs raw storage

### Performance budget

| Step | Calls | Time (7B model) | Notes |
|------|-------|------------------|-------|
| Tier 1: Document metadata | 1 per document | ~2-3s | Full markdown → structured JSON |
| Tier 2: Chunk context | 1 per chunk | ~1-2s/chunk | 400 chunks (ISP) ≈ 10-13 min |
| Embedding (existing) | 1 batch per document | ~5-10s | Unchanged, batch_size=32 |

### Deferred (evaluated, not adopted)

- **Static metadata injection (`ChunkFormatter`)** — original Section 7 approach. Rejected: prepending identical `Source: AEMO` / `Title: ...` / `Date: ...` to every chunk pollutes embeddings with boilerplate
- **Pre-generated questions per chunk** — doubles embedding storage. Revisit after Tier 2 proves out
- **Async Tier 2 processing** — CodeRabbit identified Tier 2 as a potential bottleneck for large documents (10-13 min for 400 chunks). Future improvement: queue chunk enrichment as background job with progress tracking

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

- [x] **Custom error pages** — 403, 404, 429, 500, CSRF handlers with JSON/HTML content negotiation
- [ ] **Accessibility** — audit remaining templates for missing ARIA labels, form labels, skip navigation

---

## 12. Future Considerations

**Priority:** WATCH | **Type:** [Research]

Technology to monitor for potential future adoption. Not actionable yet.

- [ ] **Docling DocTags format** — IBM's LLM-optimized document representation ([discussion](https://github.com/docling-project/docling/discussions/354), [announcement](https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion)). Uses XML-like tags with bounding box coordinates to preserve visual structure and element relationships (caption→figure linking, reading order). Currently designed for LLM fine-tuning and layout-aware tasks — overkill for text-based RAG chunking. However, as Granite-Docling matures, DocTags could enable richer chunk metadata (e.g., "this chunk contains a table from page 3, related to figure 2") which would improve retrieval precision for complex documents. Revisit when DocTags→chunk pipelines become standardized.
- [ ] **pgai vectorizer** — [Timescale pgai](https://github.com/timescale/pgai) moves the entire vectorization pipeline (chunking, formatting, embedding) into PostgreSQL via SQL-defined vectorizers with automatic trigger-based re-indexing. Currently requires pgai extension installed in PostgreSQL and tight coupling to their schema. Interesting if we move to a Timescale-managed database, but our current approach (application-level pipeline with psycopg + pgvector) gives more flexibility over parsing, formatting, and backend choice. Revisit if trigger-based re-indexing becomes a real need (see Section 7 deferred items)
- [ ] **paperless based ingestion** - I would like the option to be able to select from my paperless database items for ingestion. This could use the paperless get API which lists all documents in a table, and then then the user can select individual or multi documents to send through the processing pipeline - obviously this would need to respect the fact that the document already lives in paperless (thus rendering the archiving phase of the processing pipeline redundant)
- [ ] **html scrape (individual)** - a box where users can just input a html address and then it applies a generic scrape/ingestion/archive. this would be for one offs etc where it doesn't make sense to build a scraping script.

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

<details>
<summary>Phase 9 (2026-02-10) — Resilience & Thread Safety</summary>

Closed all 8 TODO Section 2 items. CodeRabbit review pass: 7 findings → 0. CI fully green.

- **Job error traceback** — `traceback.format_exc()` replaces `str(exc)` in job_queue.py for full stack traces
- **Scheduler exception guard** — try/except around `schedule.run_pending()` prevents scheduler thread death
- **StateTracker thread safety** — `threading.RLock` on all 12 methods, `copy.deepcopy()` on all getters
- **ServiceContainer singleton lock** — double-checked locking on `__new__()`, `_trackers_lock` for state trackers
- **File size limits** — `MAX_UPLOAD_FILE_SIZE` env var (default 500MB), guards in TikaClient + GotenbergClient
- **FlareSolverr cache eviction** — TTL (1hr) + LRU (max 50) via `_evict_stale_sessions()`
- **Paperless retry logic** — `urllib3 Retry` adapter on session (GET-only, 3 retries, backoff=1s)
- **662→679 tests**, pyright 0 errors, CodeRabbit 0 findings

</details>

<details>
<summary>Phase 10 (2026-02-10) — Pipeline Refactor</summary>

Closed all TODO Section 3 items. CodeRabbit review pass: 3 findings → 0.

- **Pipeline method extraction** — `_process_document()` (276 lines) split into 6 focused methods; orchestrator reduced to ~45 lines
- **Extracted methods** — `_parse_document()`, `_prepare_archive_file()`, `_archive_document()`, `_verify_document()`, `_ingest_to_rag()`, `_cleanup_local_files()`
- **CodeRabbit fixes** — `archived` flag deferred until `document_id` validated; orphan file warning when RAG succeeds but Paperless verification times out
- **28 new unit tests** in `test_pipeline_steps.py` — each extracted method tested in isolation
- **679→715 tests**, pyright 0 errors, ruff 0 findings, CodeRabbit 0 findings

</details>

<details>
<summary>Phase 11 (2026-02-10) — Test Coverage</summary>

Closed all TODO Section 4 items. 269 new tests across 16 files (14 new + 2 extended). CodeRabbit review pass: 5 findings → 0. CI fully green.

- **Phase 1 (Orchestrator)** — `test_pipeline_run.py` (19 tests for `run()` orchestration), `test_scheduler.py` rewritten from 2→24 tests (cron parsing, start/stop, load_schedules, error recovery)
- **Phase 2 (Service Clients)** — `test_ragflow_client.py` (18 tests: HttpAdapter, client init, API methods), `test_settings_manager.py` (21 tests: singleton, load/save, schema validation, dot-notation, properties), `test_flaresolverr_client.py` extended from 3→27 tests (properties, get_page, sessions, metrics)
- **Phase 3 (Scrapers)** — `test_base_scraper.py` (9 tests: lifecycle, cancellation, finalize), `test_models.py` (9 tests: dataclass fields, merge strategies), 9 individual scraper test files (147 tests total: parse_page, date parsing, pagination, helpers)
- **CodeRabbit fixes** — `yield` vs `return` in patch fixtures (10 files), `copy.deepcopy()` for nested dict fixtures, misleading docstring
- **715→984 tests**, pyright 0 errors, ruff 0 findings, CodeRabbit 0 findings

</details>

<details>
<summary>Phase 12 (2026-02-10) — Code Quality & Deduplication</summary>

Closed all 6 TODO Section 6 items. 24 new tests (32 new mixin tests, offset by removed duplicates). CodeRabbit review pending.

- **`flaresolverr_client.get_page()` refactored** — 150→40 lines; extracted `_execute_request`, `_handle_success_response`, `_handle_error_response`, `_handle_request_failure`
- **`paperless_client.post_document()` refactored** — 139→60 lines; extracted `_resolve_tag_ids`, `_extract_task_id_from_response`, `_validate_task_id`
- **JSONLDDateExtractionMixin** — shared JSON-LD Article date extraction for reneweconomy + theenergy scrapers; `app/scrapers/jsonld_mixin.py`, 20 unit tests
- **CardListPaginationMixin** — shared date parsing + detail-page document discovery for aer + eca scrapers; `app/scrapers/card_pagination_mixin.py`, 12 unit tests
- **`mixins.py` split** — `download_mixin.py` (HttpDownloadMixin) + `common_mixins.py` (6 classes) + re-export shim
- **`settings.py` split** — `settings/` sub-package with `helpers.py` (constants + shared utils), `ui.py` (1 route), `api.py` (16 routes), `reconciliation.py` (3 routes)
- **984→1008 tests**, pyright 0 errors, ruff 0 findings

</details>

<details>
<summary>Phase 13 (2026-02-10) — LLM-Powered Document Enrichment</summary>

Closed all TODO Section 7 items. 74 new tests across 4 test files (+ 3 existing tests updated). Two CodeRabbit review passes: 5→3→0 findings. CI fully green.

- **LLM Client** — `app/services/llm_client.py`: `LLMResult` dataclass, `LLMClient` ABC, `OllamaLLMClient` (POST `/api/chat`), `APILLMClient` (POST `/v1/chat/completions`), `create_llm_client()` factory. Mirrors `embedding_client.py` pattern
- **Document Enrichment** — `app/services/document_enrichment.py`: `DocumentEnrichmentService` with `enrich_metadata()` (Tier 1 JSON) and `enrich_chunks()` (Tier 2 plain-text context). Logger in `__init__` not module level
- **Config** — 10 env vars (LLM_BACKEND, LLM_MODEL, LLM_URL, LLM_API_KEY, LLM_TIMEOUT, LLM_ENRICHMENT_ENABLED, LLM_ENRICHMENT_MAX_TOKENS, CONTEXTUAL_ENRICHMENT_ENABLED, CONTEXTUAL_ENRICHMENT_WINDOW, VALID_LLM_BACKENDS). Validation in `Config.validate()`
- **Container** — `llm_client` property with URL fallback `LLM_URL → settings → EMBEDDING_URL`
- **Pipeline** — `_run_llm_enrichment()` after `_run_tika_enrichment()`, fill-gaps merge, tags dedup, list→string for custom fields
- **Paperless** — 4 new CUSTOM_FIELD_MAPPING entries (LLM Summary, Keywords, Entities, Topics)
- **pgvector** — `_apply_contextual_enrichment()` enriched texts for embedding, raw content for storage
- **Backfill** — `--enrich` flag in `scripts/backfill_vectors.py`
- **Settings UI** — LLM Enrichment section (toggles, backend, model, max tokens, window) + LLM service row (URL, timeout, test, status)
- **CodeRabbit fixes** — case-insensitive boolean parsing, Config.validate() for LLM, context size safety margin, backfill URL warning, no-op test assertion
- **1008→1085 tests**, pyright 0 errors, ruff 0 findings, CodeRabbit 0 findings

</details>

---

## Current State

- **1085 unit/integration tests passing** (all green locally and CI; stack tests excluded from default collection)
- **20+ stack tests** against live services (Paperless, AnythingLLM, docling-serve, Gotenberg, Tika, Ollama, pgvector)
- **Parsers:** Docling (local), DoclingServe (HTTP), Tika | Stubs: MinerU
- **Archives:** Paperless-ngx (with custom fields) | Stubs: S3, Local
- **RAG:** pgvector (self-owned), AnythingLLM, RAGFlow
- **Embedding:** Ollama, OpenAI-compatible API
- **LLM Enrichment:** Tier 1 (document-level metadata) + Tier 2 (chunk-level contextual descriptions) via Ollama/OpenAI-compatible API
- **Chunking:** Fixed (word-boundary with overlap), Hybrid (Docling fallback)
- **Search:** REST API (`/api/search`, `/api/sources`) + HTMX web UI + MCP server
- **Conversion:** Gotenberg (HTML/MD/Office→PDF)
- **Scrapers:** 9 (AEMO, AEMC, AER, ECA, ENA, Guardian, RenewEconomy, The Conversation, TheEnergy)
- **Settings UI:** Full coverage (backend selection, service URLs/timeouts, merge strategy, filename template, Tika/LLM enrichment toggles, LLM backend/model config, embedding/chunking/pgvector config)
- **Security:** CSRF, CSP, Permissions-Policy, HSTS, SSRF mitigation, rate limiting (Flask-Limiter), input validation (length/range), custom error handlers (403/404/429/500/CSRF), Basic Auth HTMX support, secrets rotation docs
- **CI:** GitHub Actions — lint (ruff), security (pip-audit), unit tests, integration tests, Dockerfile lint (hadolint), container scan (Trivy); Docker publish on main merge
- **Architecture:** Backend Registry pattern — adding a new backend is a single-line factory registration
- **Infrastructure:** Unraid (192.168.1.101) — Paperless (:8000), PostgreSQL+pgvector (:5432), Ollama (:11434), AnythingLLM (:3151), docling-serve (:4949)
