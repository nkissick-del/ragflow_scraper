# Changelog

## 2026-01-06 – Phase 4.1 Configuration and Service Architecture
- Service container (DI): Implemented ServiceContainer singleton with lazy-loaded services (SettingsManager, RAGFlowClient, FlareSolverrClient, StateTracker factory).
- Configuration reference: CONFIG_AND_SERVICES.md documents three-layer config (env vars, per-scraper JSONs, runtime settings), service responsibilities, and dependency injection benefits.
- Migration guide: SERVICE_CONTAINER_MIGRATION.md provides four-phase roadmap (create container, migrate scrapers, migrate routes, cleanup) with before/after code examples, testing strategy, and rollback plan.
- Developer docs: CLAUDE.md Section 2 (Service Layer Architecture) with practical usage patterns, error handling for optional services, and links to detailed references.
- Testing: Comprehensive test suite (268 lines) for container singleton, lazy-loading, state tracker factory, configuration validation, and integration scenarios.

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
