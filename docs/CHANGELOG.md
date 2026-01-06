# Changelog

## 2026-01-07 – Phase 4.2 Metadata Schema & Logging Standards (COMPLETE)

**Documentation:**
- `docs/METADATA_SCHEMA.md`: Aligned required fields with `validate_metadata()`/`prepare_metadata_for_ragflow()` (organization, source_url, scraped_at, document_type), updated flattening rules to match implementation, and refreshed PDF/Article payload examples.
- `docs/LOGGING_AND_ERROR_STANDARDS.md`: Documented actual logging env vars (`LOG_JSON_FORMAT`, `LOG_TO_FILE`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`, `LOG_DIR`) and clarified default log directory/rotation behavior.

**Tests:**
- `tests/unit/test_metadata_validation.py`: Added coverage for boolean/dict flattening, incorrect optional-type rejection, hash consistency via `get_file_hash`, and `to_ragflow_metadata` default/abstract fallback behavior. Ran `make test-file FILE=tests/unit/test_metadata_validation.py` (pass).

**Outcome:**
- Metadata schema docs and logging standards are now in sync with code; validation/serialization edge cases covered by unit tests.

## 2026-01-06 – Phase 4.1 Configuration and Service Architecture (COMPLETE)

**Documentation (1,503 lines):**
- `CONFIG_AND_SERVICES.md` (800 lines): Complete reference for configuration sources (env vars → per-scraper JSONs → settings.json → defaults), service layer architecture, and dependency injection patterns. Covers SettingsManager (runtime config), StateTracker (URL deduplication), RAGFlowClient (document ingestion), FlareSolverrClient (Cloudflare bypass), and ServiceContainer proposal with benefits/drawbacks.
- `SERVICE_CONTAINER_MIGRATION.md` (703 lines): Step-by-step four-phase migration guide (Weeks 1-4) from scattered service instantiation to centralized ServiceContainer. Includes current state analysis, before/after code examples, testing strategies with mocked containers, rollback procedures, and success criteria per phase.
- `CLAUDE.md` Section 2 (Service Layer Architecture): New practical guide with usage patterns for all services, error handling for optional services (RAGFlow, FlareSolverr), and cross-references to detailed documentation. Section numbering updated (Sections 2-21).

**Implementation (435 lines):**
- `app/services/container.py` (167 lines): Working ServiceContainer with singleton pattern, lazy-loaded service properties (SettingsManager, RAGFlowClient, FlareSolverrClient), per-scraper StateTracker factory with caching, comprehensive error messages, and reset() for testing.
- `tests/unit/test_service_container.py` (268 lines): Comprehensive test suite (15+ test cases) covering singleton pattern, lazy-loading behavior, factory pattern, configuration validation, integration scenarios, and error message clarity.

**Key Design:**
- Singleton pattern with global `get_container()` accessor for consistent service access
- Lazy-loading: services initialized only on first access (zero overhead until used)
- Factory pattern: StateTracker created per-scraper, cached by name for efficiency
- Clear error handling: missing config raises ValueError with hints about required env vars
- Test-friendly: `reset_container()` clears cache for isolated test runs
- Backward compatible: old ad-hoc service creation still works during migration

**Quality:**
- Syntax validated with py_compile
- No circular dependencies
- Proper separation of concerns (singleton vs initialization logic)
- Fixed __new__ method to avoid conflated class/instance state (2026-01-07)

**Deliverables:**
- All 5 Phase 4.1 tasks complete with checkmarks
- 1,938 new lines of documentation and code
- 3 commits (feat, docs, fix)
- Ready for Docker integration testing
- Migration roadmap for 8+ scrapers and web routes

## 2026-01-06 – Phase 2 Local Validation & Tooling
- Docker/compose hardening: pinned Python and Chromium images, added OCI labels, resource limits, and no-new-privileges for services.
- New maintenance CLI: `scripts/run_scraper.py state validate|repair` (checksums, schema checks, optional repair/write) and `config validate|migrate` (JSON schema + defaults for settings/scraper configs).
- Resilience: retry backoff now supports jitter and max delay; state and config validators reuse shared helpers.
- Web UI polish: skip link, focus outlines, aria-live status/log widgets, and responsive nav/layout tweaks.
- Build fixes: include `constraints.txt` in image builds for pinned installs.

- Config/schema hardening: JSON schema validation for settings, clear env vs settings precedence, ensured directories and logging defaults.
- Metadata pipeline: flat metadata validators, RAGFlow upload/parse structured events, duplicate handling, and metadata push coverage.
- Observability: structured logging across pipeline/scheduler/web routes, FlareSolverr metrics/events, pipeline metrics endpoint, step timing capture.
- Security posture: TLS/HSTS + proxy guidance (`TRUST_PROXY_COUNT`), basic-auth defaults documented, secrets kept in `.env` with tightened checklist.
- Tests: added integration coverage for pipeline upload/failure, scheduler, registry discovery; unit coverage for auth, validation, and RAGFlow metadata uploads. Last run: `pytest tests/unit/test_basic_auth.py tests/unit/test_validation.py tests/unit/test_ragflow_upload_metadata.py tests/integration/test_pipeline_mocked.py tests/integration/test_pipeline_upload_flow.py tests/integration/test_pipeline_failure_flow.py tests/integration/test_scheduler_mocked.py tests/integration/test_registry_discovery.py`.
- Dependency hardening: pinned constraints, documented `pip-audit` security scan.
