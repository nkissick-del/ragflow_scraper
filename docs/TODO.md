# TODO — Prioritized Roadmap

Last updated: 2026-02-07

---

## 1. Settings UI — Close Configuration Gaps

**Priority:** HIGH | **Effort:** 6-10h | **Type:** [Code]

The Phase 4.4 config audit found only 40% of user-facing settings are exposed in the Web UI, with 12 specific gaps. Operators currently need to edit `.env` and restart to change backend selection, timeouts, or service URLs.

**Tasks:**
- [ ] Backend selection dropdowns (PARSER_BACKEND, ARCHIVE_BACKEND, RAG_BACKEND)
- [ ] Service URL configuration (DOCLING_SERVE_URL, TIKA_SERVER_URL, GOTENBERG_URL)
- [ ] Timeout configuration (parser, archive, Gotenberg timeouts)
- [ ] Metadata merge strategy selector
- [ ] Filename template editor with preview
- [ ] Connection test buttons for each service (pattern exists for RAGFlow/FlareSolverr)
- [ ] Persist settings changes (currently settings.json handles per-scraper; extend to global config)

**Reference:** config_audit.md (from Phase 4.4)

---

## 2. Paperless Custom Fields

**Priority:** MEDIUM | **Effort:** 3-5h | **Type:** [Code]

Basic correspondent/tag mapping is complete (Phase 4.2), but the [paperless_metadata.md](plans/paperless_metadata.md) plan includes structured custom fields that unlock rich search and filtering in Paperless.

**What exists today:**
- Correspondent and tag ID lookup with caching
- `post_document()` resolves string names→integer IDs

**What's missing (Phase 2-3 of paperless_metadata plan):**
- [ ] Custom field mapping: Original URL, Scraped Date, Page Count, File Size, Source Scraper
- [ ] `_get_custom_fields()` method to discover Paperless custom field IDs
- [ ] Map `DocumentMetadata` fields to Paperless custom field values during upload
- [ ] Unit tests for custom field resolution
- [ ] Document required Paperless custom field setup

**Value:** Enables filtering documents by source URL, scrape date, page count — directly useful for dedup auditing and provenance tracking.

**Reference:** [docs/plans/paperless_metadata.md](plans/paperless_metadata.md) (Phases 2-3)

---

## 3. Tika Metadata Enrichment Pipeline

**Priority:** MEDIUM | **Effort:** 3-4h | **Type:** [Code]

Tika is implemented as a standalone parser backend, but the [tika_integration.md](plans/tika_integration.md) plan envisions it as a metadata *enrichment* layer that runs *alongside* Docling. The `TIKA_ENRICHMENT_ENABLED` config var already exists but the enrichment pipeline isn't wired.

**Use case:** Docling extracts semantic metadata (title, headings, structure) but misses physical file metadata (creation date, author from PDF properties, page count, language). Tika fills those gaps.

**Tasks:**
- [ ] Wire Tika enrichment step in `pipeline.py` — after Docling parse, optionally run Tika metadata extraction
- [ ] Merge Tika metadata into existing metadata using fill-missing strategy (don't override Docling/scraper data)
- [ ] Gate behind `TIKA_ENRICHMENT_ENABLED` flag (default: false)
- [ ] Unit tests for enrichment merge logic
- [ ] Add to Settings UI (toggle + Tika URL)

**Reference:** [docs/plans/tika_integration.md](plans/tika_integration.md)

---

## 4. Backend Registry Pattern

**Priority:** MEDIUM | **Effort:** 2-3h | **Type:** [Code]

Backend selection in `container.py` uses hardcoded `if/elif` chains. A registry pattern would make adding new backends a single-line registration instead of modifying container code.

**Tasks:**
- [ ] Create `BackendRegistry` with `register(name, factory_fn)` and `get(name)` methods
- [ ] Register existing backends (docling, docling_serve, tika, paperless, ragflow, anythingllm)
- [ ] Replace `if/elif` chains in `container.py` with registry lookups
- [ ] Allow third-party backend registration via entry points or config (optional)

**Value:** Clean architecture, easier to extend, removes container.py as a bottleneck for new backends.

---

## 5. CI/CD Pipeline

**Priority:** MEDIUM | **Effort:** 4-6h | **Type:** [Code]

No automated testing or build pipeline exists. With 438+ tests, this is low-hanging fruit for preventing regressions.

**Tasks:**
- [ ] GitHub Actions workflow: lint + unit tests on PR
- [ ] Integration test job (mocked services, no external deps)
- [ ] Security scanning (`pip-audit` or `safety`)
- [ ] Docker image build + push on merge to main
- [ ] Badge in README for build status

---

## 6. Security Hardening

**Priority:** MEDIUM | **Effort:** 3-5h | **Type:** [Local/External]

Deferred from Phase 4.5. Basic auth exists but production security hasn't been validated.

**Tasks:**
- [ ] TLS termination via reverse proxy (Caddy/Traefik config template)
- [ ] Verify basic auth works end-to-end with HTMX
- [ ] CSRF protection audit (Flask-WTF or manual tokens)
- [ ] Security headers (CSP, X-Frame-Options, etc.)
- [ ] Secrets rotation documentation

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

---

## Current State

- **438+ tests** (unit + integration; stack tests excluded from default collection)
- **20+ stack tests** against live services (Paperless, AnythingLLM, docling-serve, Gotenberg, Tika)
- **Parsers:** Docling (local), DoclingServe (HTTP), Tika | Stubs: MinerU
- **Archives:** Paperless-ngx | Stubs: S3, Local
- **RAG:** AnythingLLM, RAGFlow
- **Conversion:** Gotenberg (HTML/MD/Office→PDF)
- **Scrapers:** 9 (AEMO, AEMC, AER, ECA, ENA, Guardian, RenewEconomy, The Conversation, TheEnergy)
- **No current blockers** — system is deployable
