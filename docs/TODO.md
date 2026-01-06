# Phased TODO (use "plan phase X")

Legend: [Code] coding-only; [Local] requires local docker/compose; [External] needs RAGFlow/FlareSolverr or other outside services.

## Phase 1 – Completed (see docs/CHANGELOG.md)

## Phase 2 – Completed (see docs/CHANGELOG.md 2026-01-06 entry)

## Phase 3 – External/RAGFlow-dependent work
- [External] RAGFlow metadata end-to-end validation (reuse existing checklist when server is up): API assumptions, status polling, hash/dedup, and flat meta enforcement (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1278)).
- [External] FlareSolverr/Cloudflare bypass observability: success-rate metrics, timeouts, fallback rules (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L325)).
- [External] Production security hardening: TLS termination, auth on web UI, secrets rotation; verify against live stack (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1387)).

## Phase 4 – Documentation and ops maturity

### 4.3 Deployment & Connectivity Guide [Local/External]
**Goal:** Enable operators to deploy in any environment (local, staging, prod) with clarity on optional services  
**References:** [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L757)

**Tasks:**
- [ ] Create `docs/DEPLOYMENT_GUIDE.md`:
  - **Environment Setup:**
    - System requirements (Python 3.11+, Docker, Docker Compose)
    - Platform notes (macOS Apple Silicon, Linux x86_64, Unraid)
  - **Configuration:**
    - `.env` file setup with all variables and defaults
    - Per-environment `.env.development`, `.env.staging`, `.env.production`
    - Secret rotation policy and tools
  - **Docker Compose Profiles:**
    - `base`: Flask + Chrome only (no RAGFlow, no FlareSolverr)
    - `full`: + RAGFlow + FlareSolverr
    - `flaresolverr-only`: + FlareSolverr, RAGFlow optional
    - How to run with `--profile` flag (e.g., `docker compose --profile full up`)
  - **Service Connectivity Tests:**
    - RAGFlow health check: `curl -sS --fail --connect-timeout 5 http://localhost:9380/`
    - RAGFlow auth: `curl -sS --fail -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
    - FlareSolverr health: test Cloudflare page scrape with fallback logic
    - Chrome/Selenium liveness
  - **Troubleshooting Matrix:** (service, symptom, cause, fix)
- [ ] Create `docs/MIGRATION_AND_STATE_REPAIR.md`:
  - State file format and location (`data/state/{scraper}_state.json`)
  - How to migrate state between versions
  - How to repair corrupted state files
  - How to reset a single scraper's state
  - How to export/import state for backup/restore
  - Metadata repair: fixing orphaned or stale documents
- [ ] Create `docs/RUNBOOK_COMMON_OPERATIONS.md`:
  - **Starting:** `docker compose --profile full up -d` with verification steps
  - **Stopping & cleanup:** service ordering, data preservation
  - **Scaling:** running multiple scraper instances in parallel
  - **Monitoring:** log tailing, web UI check, health dashboard (if implemented)
  - **Emergency recovery:** clearing Chrome cache, resetting RAGFlow state, force-reindex
  - **Update & downtime:** blue/green strategies
- [ ] Update `README.md`:
  - Link to DEPLOYMENT_GUIDE.md in Quick Start section
  - Add "Profiles & Optional Services" section describing `--profile` usage
  - Example: deploying without RAGFlow for local-only PDF collection

**Acceptance:** Guides testable on local machine and (with services) on staging; QA-verified for clarity

---

### 4.4 Code Examples & Common Patterns [Code]
**Goal:** Lower onboarding friction for future contributors  

**Tasks:**
- [ ] Create `docs/DEVELOPER_GUIDE.md`:
  - **Project Structure:** explain `app/{scrapers,services,orchestrator,web}/` layout
  - **Adding a New Scraper:** step-by-step (inherit BaseScraper, add to registry, add config, test)
  - **Debugging a Scraper:** using Chrome VNC, reading logs, testing locally
  - **Error Handling:** using `errors.py` custom exceptions, retry decorator, fallback patterns
- [ ] Update `CLAUDE.md` with:
  - Quick reference: **"Common tasks"** section (see end of current TODO)
  - Link to METADATA_SCHEMA.md and LOGGING_AND_ERROR_STANDARDS.md
  - Link to SERVICE_CONTAINER_MIGRATION.md for service-layer contributors
- [ ] Create `docs/EXAMPLE_SCRAPER_WALKTHROUGH.md`:
  - Line-by-line explanation of an existing scraper (e.g., AEMO)
  - How state tracking works during a run
  - How metadata gets built and validated
  - How errors are caught and logged

**Acceptance:** New contributor can add a scraper without asking questions

---

### Phase 4 Execution Order

**Recommended sequence** (to unblock parallel work):

1. **Week 1:** Metadata schema + Logging standards (docs + tests)  
   → Enables Phase 3 audit validation  
2. **Week 2:** Deployment guide + Connectivity tests  
   → Enables operators to run services reliably  
3. **Week 3:** Config & Service architecture docs  
   → Inform future service-layer refactoring  
4. **Week 4:** Developer guide + Example walkthrough  
   → Reduce onboarding friction

---

## Phase 5 - Refactor

ragflow_client.py

Slice into focused modules (auth/session, datasets, documents/upload, parsing/polling, metadata) or mixins; current single class mixes concerns (session login, dataset CRUD, uploads, polling, metadata push).
Extract a small API wrapper with shared retry/backoff, headers, and error logging; reuse across session and API-key flows instead of per-method request scaffolding.
Move static catalog data (chunk methods, PDF parsers, pipelines/models grouping) behind a “RagflowCatalog” helper so routes/templates can consume one normalized shape.
Isolate duplicate/exists checks + wait_for_document_ready + metadata push into an “IngestionWorkflow” helper to keep the client lean.
Consider a polling utility (status waiters) shared with routes/tests; reduces bespoke loops and makes timeouts/backoff configurable.
base_scraper.py

Split into mixins: WebDriverLifecycle, CloudflareBypass, HttpDownload, MetadataIO, ExclusionRules, IncrementalState. The base class currently owns all concerns, making it hard to reason about or extend.
Move data classes (DocumentMetadata, ExcludedDocument, ScraperResult) to a lightweight models.py; this simplifies reuse by tests and Ragflow ingestion without importing the heavy base.
Centralize fetch/save paths (download dir, metadata dir, hash computation) in a small storage helper to DRY across scrapers and decouple from Selenium concerns.
Make the template method explicit: setup() -> scrape() -> teardown() with overridable hooks instead of embedding many side effects inside run().
Encapsulate exclusion logic (should_exclude_document) and incremental date tracking into dedicated helpers; keeps scrape implementations focused on parsing.
routes.py

Split the blueprint into submodules: auth middleware, scraper control (run/cancel/preview), settings, metrics/logs, ragflow API. The single file holds UI, API, settings, and threading concerns.
Wrap _running_scrapers + threads in a “ScraperJobManager” service (start/stop/status, error/result storage) to avoid scattered lock handling and repeated inline thread functions.
DRY Ragflow option fetching/grouping (models, chunk methods) into a shared helper/service; currently repeated in scrapers/settings endpoints.
Extract log streaming/download helpers and HTMX response builders into utilities to reduce inline string HTML and repeated file reads.
Consider request/response schemas (pydantic-like or simple dataclasses) for settings/ragflow endpoints to validate inputs and shrink per-route boilerplate.

## Quick commands (when services are available)
- RAGFlow health: `curl -sS --fail --connect-timeout 5 --max-time 10 http://localhost:9380/`
- Auth check: `curl -sS --fail -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
- Scraper dry-run example: `docker compose exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run`

## Notes
- Testing harness is largely in place; focus now is on consolidation, validation tooling, and production hardening.
- When asking for details, you can say "plan phase 2" (or any phase) and we will expand into a concrete task list with owners/tests.
