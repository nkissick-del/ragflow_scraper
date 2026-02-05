# Prioritized TODO (2026-01-08)

Legend: [Code] coding-only; [Local] requires local docker/compose; [External] needs RAGFlow/FlareSolverr or other outside services.

## 0) Completed

- **Phase 1 (2026-01-07):** All critical refactors complete with test coverage.
  - ✅ ServiceContainer: property-only API (removed all backward-compatible getters).
  - ✅ BaseScraper: mixins extracted (IncrementalStateMixin, ExclusionRulesMixin, WebDriverLifecycleMixin, CloudflareBypassMixin, MetadataIOMixin, HttpDownloadMixin).
  - ✅ Data models: DocumentMetadata, ExcludedDocument, ScraperResult consolidated in app/scrapers/models.py.
  - ✅ All 10 scrapers: migrated to property-based container access, updated imports for models.
  - ✅ Blueprint modularization: auth, scrapers, settings, metrics_logs, ragflow_api, api_scrapers split from monolithic routes.py.
  - ✅ JobQueue: async job management with per-scraper exclusivity, cancel/status/preview support.
  - ✅ Test coverage: **117 tests passing** (test_job_queue.py with 12 tests for JobQueue, test_scraper_mixins.py with 18 tests for mixin behaviors, all existing tests updated to new structure).
- **Phase 2 (2026-01-08):** RAGFlow ingestion workflow & routes.py consolidation complete with integration tests.
  - ✅ Phase 2.1: RAGFlowIngestionWorkflow extracted with full upload/poll/metadata workflow, error handling, and 14 unit tests.
  - ✅ Phase 2.2: routes.py deleted - all routes migrated to blueprints (scrapers, settings, metrics_logs, api_scrapers, ragflow_api, auth).
  - ✅ Phase 2.3: Integration test coverage - 4 web integration tests for blueprint registration and app creation.
  - ✅ Test coverage: **139 tests passing** (135 baseline + 4 new web integration tests).
- **Phase 3 (2026-01-08):** Documentation & Enablement complete - operations & developer docs delivered.
  - ✅ Track A (Operations): 4 documents created
    - ✅ DEPLOYMENT_GUIDE.md (500+ lines) - Prerequisites, environment config, compose profiles, setup, connectivity, troubleshooting
    - ✅ RUNBOOK_COMMON_OPERATIONS.md (450+ lines) - Start/stop, running scrapers, monitoring, backup, scaling, updates, emergency procedures
    - ✅ MIGRATION_AND_STATE_REPAIR.md (400+ lines) - State schema, operations, metadata management, common scenarios
    - ✅ README.md updates - Deployment section, operations links, enhanced project structure
  - ✅ Track B (Developer): 3 documents created
    - ✅ DEVELOPER_GUIDE.md (350+ lines) - Setup, structure, adding scrapers, best practices, debugging, testing
    - ✅ EXAMPLE_SCRAPER_WALKTHROUGH.md - Line-by-line AEMO scraper explanation with patterns
    - ✅ CLAUDE.md enhancements - Common tasks section with 5 task templates, documentation links
  - ✅ Total: 7 documents delivered, ~1,700 lines, 100% cross-referenced
  - ✅ Test coverage: **140 tests passing** (no code changes in Phase 3, documentation only)

## 0.5) Phase 1.5 - Integration Test Coverage (COMPLETE) [Code]

- ✅ Web integration tests created (test_web_integration.py) covering:
  - App creation and configuration
  - Blueprint registration verification
  - Root route rendering
  - Static file configuration
- Note: Detailed blueprint route testing deferred - requires complex mocking of container/job_queue dependencies.

## 1) Critical Refactors (COMPLETE) [Code]

**Status:** Phase 2 complete! All major refactorings done.

- ✅ ragflow_client.py: RAGFlowIngestionWorkflow extracted with 14 unit tests covering upload/poll/metadata workflows.
- ✅ base_scraper.py: Mixins extracted and wired; data classes moved to models.py.
- ✅ routes.py: Deleted - all routes migrated to 6 blueprints (auth, scrapers, settings, metrics_logs, ragflow_api, api_scrapers).
- ✅ container wiring: ServiceContainer consolidated with property-only API.

## 2) Ops & Deployment Readiness ✅ COMPLETE [Local/External]

**Status:** Phase 3 Track A complete - all operations documentation delivered.

- ✅ DEPLOYMENT_GUIDE.md: Environment setup, platform notes, .env configuration, compose profiles (base/full/flaresolverr-only), connectivity tests, deployment scenarios, troubleshooting matrix, production checklist
- ✅ RUNBOOK_COMMON_OPERATIONS.md: Common operations (start/stop/scale/monitor/backup/recover/update), emergency procedures, quick reference commands
- ✅ MIGRATION_AND_STATE_REPAIR.md: State file schema/paths, migrate/repair/reset/export-import operations, metadata management, common scenarios, troubleshooting
- ✅ README.md updates: Deployment section with link to guide, operations section with RUNBOOK link, enhanced project structure

## 3) Contributor Enablement ✅ COMPLETE [Code]

**Status:** Phase 3 Track B complete - all developer documentation delivered.

- ✅ DEVELOPER_GUIDE.md: Project structure, add-scraper workflow (5 steps), debugging with Chrome VNC/logs/state inspection/pdb, error-handling patterns, testing approach, code standards, service container usage
- ✅ EXAMPLE_SCRAPER_WALKTHROUGH.md: Line-by-line AEMO scraper walkthrough covering class definition, initialization, scrape() method, pagination, document extraction, metadata, state management, error handling, testing, key takeaways (7 best practices), common patterns (5 code snippets)
- ✅ CLAUDE.md enhancements: "Common Tasks for AI Assistants" section with 5 task templates (adding scraper, debugging, web UI, RAGFlow, documentation lookup), updated references with all Phase 3 docs

## 4) External/RAGFlow-Dependent Validation [External]

Status: Awaiting live services; keep after refactors unless blocking release.

- RAGFlow metadata end-to-end validation (API assumptions, status polling, hash/dedup, flat meta) per docs/ragflow_scraper_audit.md.
- FlareSolverr/Cloudflare bypass observability (success-rate metrics, timeouts, fallback rules) per audit doc.
- Production security hardening (TLS termination, UI auth, secrets rotation) validated against live stack.

## Quick commands (when services are available)

- RAGFlow health: `curl -sS --fail --connect-timeout 5 --max-time 10 http://localhost:9380/`
- Auth check: `curl -sS --fail -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
- Scraper dry-run example: `docker compose exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run`

## 4) Phase 4: Pre-Deployment Readiness [Code/Local/External]

**Status:** 🚧 In Progress  
**Goal:** Complete critical features and validation before production deployment  
**Target:** AnythingLLM as primary RAG backend (RAGFlow deferred)

### Phase 4.1: AnythingLLM Implementation [Code] 🟡 MOSTLY COMPLETE

**Priority:** BLOCKER - ~~Currently stub implementation~~ **IMPLEMENTED** (manual testing pending)

**Tasks:**
- [x] Research AnythingLLM API documentation
  - Document upload endpoints
  - Workspace/collection management
  - Authentication patterns
  - Metadata support
- [x] Implement `AnythingLLMBackend.test_connection()`
  - Health check endpoint
  - Workspace validation
- [x] Implement `AnythingLLMBackend.ingest_document()`
  - Document upload workflow
  - Metadata mapping
  - Workspace selection
- [x] Create `AnythingLLMClient` service
  - HTTP adapter with Bearer auth
  - Multipart file upload
  - Retry logic
- [x] Add unit tests
  - Client tests (17 tests)
  - Backend tests (22 tests)
  - Container integration tests (2 tests)
- [x] Add integration tests (mocked API)
  - Created but requires `responses` library
- [ ] Manual testing with live AnythingLLM instance
  - Connection test
  - Document upload
  - Metadata verification
- [ ] E2E pipeline test

**Files:**
- ✅ `app/services/anythingllm_client.py` (NEW)
- ✅ `app/backends/rag/anythingllm_adapter.py` (UPDATED)
- ✅ `tests/unit/test_anythingllm_client.py` (NEW)
- ✅ `tests/unit/test_anythingllm_backend.py` (NEW)
- ✅ `tests/integration/test_anythingllm_integration.py` (NEW)

**Test Results:** 41/41 unit tests passing ✅

**Estimated Effort:** 8-12h  
**Actual Effort:** ~4-5h

---

### Phase 4.2: Paperless Metadata Enhancement [Code] 🔴 CRITICAL

**Priority:** BLOCKER - Metadata upload currently incomplete

**Tasks:**
- [ ] Implement correspondent ID lookup
  - `get_or_create_correspondent(name: str) -> int`
  - Cache lookups to reduce API calls
  - Handle creation if not exists
- [ ] Implement tag ID lookup
  - `get_or_create_tags(names: list[str]) -> list[int]`
  - Batch tag creation
  - Cache tag mappings
- [ ] Update `post_document()` to use ID lookups
  - Replace string names with integer IDs
  - Add validation
  - Improve error messages
- [ ] Add integration tests
  - Test correspondent creation
  - Test tag creation
  - Test full metadata upload workflow
- [ ] Remove TODO comments

**Reference:** 
- [app/services/paperless_client.py](app/services/paperless_client.py#L98-L113)
- [docs/plans/paperless_metadata.md](docs/plans/paperless_metadata.md)

**Estimated Effort:** 4-6 hours

---

### Phase 4.3: Jinja2 Filename Templating [Code] 🟡 HIGH

**Priority:** HIGH - Improves file organization and consistency

**Tasks:**
- [ ] Verify `jinja2` in requirements.txt (already in constraints.txt)
- [ ] Add filename template configuration
  - Add `FILENAME_TEMPLATE` to Config
  - Default: `"{{ date_prefix }}_{{ org }}_{{ title | slugify }}{{ extension }}"`
  - Validate template on startup
- [ ] Implement custom Jinja2 filters
  - `slugify` - Convert to filesystem-safe names
  - `shorten(n)` - Truncate long titles
  - `secure_filename` - Remove dangerous characters
- [ ] Update `generate_filename_from_template()`
  - Use Jinja2 rendering
  - Handle template errors gracefully
  - Add template variable documentation
- [ ] Add unit tests
  - Test various template patterns
  - Test filter functions
  - Test error handling
- [ ] Update documentation
  - Document available template variables
  - Provide example templates
  - Add customization guide

**Reference:**
- [docs/plans/naming_strategy.md](docs/plans/naming_strategy.md)
- [docs/plans/consolidated_architecture.md](docs/plans/consolidated_architecture.md#L60-L64)
- [app/utils/file_utils.py](app/utils/file_utils.py)

**Estimated Effort:** 3-4 hours

---

### Phase 4.4: Testing & Quality Assurance [Code/Local] 🟡 HIGH

**Priority:** HIGH - Ensure stability before deployment

**Tasks:**
- [ ] Fix test collection errors (2 failing)
  - Identify problematic test files
  - Fix import/dependency issues
  - Verify all 148 tests collect successfully
- [ ] Create `.env.test` for local testing
  - Override Docker-specific paths
  - Document test environment setup
  - Add to .gitignore
- [ ] Expand integration test coverage
  - E2E pipeline test (happy path)
  - AnythingLLM integration test
  - Paperless integration test
  - Docling parser integration test
- [ ] Add performance benchmarks (optional)
  - PDF parsing benchmark
  - Concurrent download benchmark
  - Metadata merge benchmark

**Reference:** [walkthrough.md](../../../.gemini/antigravity/brain/ca76dfe9-5ce0-4f09-a2f6-8db2f54a5b5a/walkthrough.md)

**Estimated Effort:** 8-12 hours

---

### Phase 4.5: Production Validation [Local/External] 🟡 HIGH

**Priority:** HIGH - Validate with real services before deployment

**Tasks:**
- [ ] Test with live AnythingLLM instance
  - Verify document upload
  - Verify metadata handling
  - Test workspace management
  - Validate search/retrieval
- [ ] Test with live Paperless-ngx instance
  - Verify correspondent/tag creation
  - Test document archiving
  - Validate verification polling
  - Check metadata accuracy
- [ ] Test Docling parser with real PDFs
  - Complex layouts (tables, images)
  - Various PDF formats
  - Metadata extraction accuracy
- [ ] Test full pipeline end-to-end
  - Run real scraper (AEMO, Guardian, etc.)
  - Verify all stages complete
  - Check file cleanup
  - Validate metrics
- [ ] Security validation
  - Test TLS/HTTPS with reverse proxy
  - Verify basic auth works
  - Test CSRF protection
  - Validate security headers
- [ ] Backup/restore procedures
  - Test state file backup
  - Test metadata backup
  - Test restore process

**Estimated Effort:** 6-8 hours

---

## Phase 4 Summary

**Total Estimated Effort:** 29-42 hours (4-6 days)

**Critical Path:**
1. ✅ AnythingLLM implementation (8-12h) - COMPLETE (manual testing pending)
2. Paperless metadata (4-6h) - BLOCKER
3. Jinja2 templating (3-4h) - HIGH
4. Testing (8-12h) - HIGH
5. Production validation (6-8h) - HIGH

**Target Completion Criteria:**
- 🟡 AnythingLLM backend fully functional (implemented, manual validation pending)
- [ ] Paperless metadata upload working (correspondents + tags)
- [ ] Jinja2 filename templating implemented
- [ ] All 148 tests passing
- [ ] Integration tests for critical paths
- [ ] Validated with live AnythingLLM instance
- [ ] Validated with live Paperless instance
- [ ] Security hardening verified

**Current Status:**
- ✅ 146/148 tests passing (98.6%)
- ✅ AnythingLLM backend implemented with 41 unit tests
- 🔴 2 test collection errors to fix
- 🔴 Paperless metadata mapping incomplete
- 🔴 Jinja2 templating not started

---

## 5) Future Enhancements (Post-Deployment) [Code/External]

**Status:** Deferred - Not required for initial deployment

### Optional Improvements

**Gotenberg Archiver Refactoring** 🟢 LOW
- Replace Selenium-based PDF generation with Gotenberg
- Unified Markdown source for RAG and Archive
- Simpler deployment (no Chrome dependency for archiving)
- Reference: [docs/plans/archiver_refactoring.md](docs/plans/archiver_refactoring.md)

**Apache Tika Integration** 🟢 LOW
- Enhanced metadata extraction (page count, language, creation date)
- Fallback for missing web metadata
- Better search capabilities
- Reference: [docs/plans/tika_integration.md](docs/plans/tika_integration.md)

**Additional Parser Backends** 🟢 LOW
- MinerU parser implementation
- Tika parser implementation
- Parser backend registry pattern

**Additional Archive Backends** 🟢 LOW
- S3 storage backend
- Local filesystem backend
- Multi-archive support

**CI/CD Pipeline** 🟢 LOW
- GitHub Actions workflow
- Automated testing on PR
- Security scanning (pip-audit)
- Docker image builds

**Monitoring & Observability** 🟢 LOW
- Prometheus metrics endpoint
- Grafana dashboard template
- Health check endpoints
- Alerting rules

---

## Next Steps

**Immediate Actions (Phase 4.2-4.3):**
1. 🔴 Fix Paperless metadata mapping (4-6 hours) - BLOCKER
2. 🟡 Implement Jinja2 templating (3-4 hours)
3. 🟡 Complete AnythingLLM manual testing (1-2 hours)

**Then (Phase 4.3-4.5):**
4. 🟡 Fix test collection errors and expand coverage (8-12 hours)
5. 🟡 Production validation with live services (6-8 hours)

**Target:** Production-ready deployment in 4-6 days

---

## Notes

- Testing harness: 146/148 tests passing (98.6%)
- Documentation: 7 comprehensive guides (~1,700 lines)
- Architecture: Modular backend system complete
- **RAGFlow:** Deferred - focusing on AnythingLLM
- **Current blockers:** Paperless metadata mapping, AnythingLLM manual validation pending
- **Ready after Phase 4:** Production deployment
