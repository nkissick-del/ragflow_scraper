# Phased TODO (use "plan phase X")

Legend: [Code] coding-only; [Local] requires local docker/compose; [External] needs RAGFlow/FlareSolverr or other outside services.

## Phase 1 – Completed (see docs/CHANGELOG.md)

## Phase 2 – Completed (see docs/CHANGELOG.md 2026-01-06 entry)

## Phase 3 – External/RAGFlow-dependent work
- [External] RAGFlow metadata end-to-end validation (reuse existing checklist when server is up): API assumptions, status polling, hash/dedup, and flat meta enforcement (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1278)).
- [External] FlareSolverr/Cloudflare bypass observability: success-rate metrics, timeouts, fallback rules (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L325)).
- [External] Production security hardening: TLS termination, auth on web UI, secrets rotation; verify against live stack (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1387)).

## Phase 4 – Documentation and ops maturity

### 4.1 Configuration & Service Architecture Documentation [Code]
**Goal:** Document patterns for reuse; make dependency injection explicit  
**References:** [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L347), [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L390)

**Tasks:**
- [x] Create `docs/CONFIG_AND_SERVICES.md`:
  - Configuration sources (`.env`, `settings.json`, per-scraper JSONs) and precedence rules
  - Single source of truth principle and how to apply it
  - SettingsManager pattern (lazy-load, validation, runtime updates)
  - StateTracker lifecycle and persistence patterns
  - Container/DI pattern proposal and implementation roadmap
  - Code examples for each pattern
- [x] Create `docs/SERVICE_CONTAINER_MIGRATION.md`:
  - Step-by-step guide for moving to unified ServiceContainer
  - Current state of `ragflow_client.py`, `state_tracker.py`, `settings_manager.py`, `flaresolverr_client.py`
  - Testing strategy for service mocking
  - Backward-compatibility approach during migration
- [x] Update `CLAUDE.md` Section 2 (System Overview) with:
  - Service layer architecture diagram (ASCII or reference to visual docs)
  - Configuration flow and precedence
  - Example: "How to add a new scraper service"
- [x] **DONE:** Created working `app/services/container.py` with:
  - ServiceContainer singleton class
  - Lazy-loaded properties for services
  - Factory pattern for StateTracker per-scraper
  - reset() method for testing
- [x] **DONE:** Created `tests/unit/test_service_container.py` with:
  - Unit tests for singleton pattern
  - Lazy-loading verification
  - Factory pattern tests
  - Integration tests with real services
  - Error handling and clarity tests

**Acceptance:** ✅ Docs created + implementation complete + tests ready for Docker environment

---

### 4.2 Metadata Schema & Logging Standards [Code]
**Goal:** Make schema discoverable and logging consistent across scrapers  
**References:** [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1205), [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1157)

**Tasks:**
- [ ] Create `docs/METADATA_SCHEMA.md`:
  - Full DocumentMetadata dataclass definition (fields, types, examples)
  - How metadata flows from scraper → StateTracker → RAGFlow API
  - Deduplication and hash logic (reference `article_converter.py`)
  - Flat metadata enforcement rule and validation
  - Example metadata payload for each scraper type (PDF, article)
  - Schema versioning strategy
- [ ] Create `docs/LOGGING_AND_ERROR_STANDARDS.md`:
  - Log level mapping and when to use each (DEBUG/INFO/WARNING/ERROR/CRITICAL)
  - Structured logging format (example with scraper name, document count, duration, errors)
  - Log file rotation policy and retention
  - How to read logs via web UI (reference web/routes.py)
  - Error telemetry: error types to track, counts, alert thresholds
  - Common errors by scraper and troubleshooting flowchart
- [ ] Add code examples to `CLAUDE.md`:
  - "How to log a scraper lifecycle event" (start, fetch, store, error recovery)
  - "How to construct and validate metadata"
  - "How to interpret logs when debugging a failed scrape"
- [ ] Add tests `tests/unit/test_metadata_validation.py`:
  - Validate all required fields for each scraper type
  - Test deduplication hash consistency
  - Test metadata serialization to JSON for RAGFlow

**Acceptance:** Docs + passing validation tests

---

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

## Quick commands (when services are available)
- RAGFlow health: `curl -sS --fail --connect-timeout 5 --max-time 10 http://localhost:9380/`
- Auth check: `curl -sS --fail -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
- Scraper dry-run example: `docker compose exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run`

## Notes
- Testing harness is largely in place; focus now is on consolidation, validation tooling, and production hardening.
- When asking for details, you can say "plan phase 2" (or any phase) and we will expand into a concrete task list with owners/tests.
