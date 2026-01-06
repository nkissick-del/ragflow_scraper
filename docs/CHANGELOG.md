# Changelog

## 2026-01-06 – Phase 1 Completion
- Centralized service container for shared dependencies (settings, RAGFlow, FlareSolverr, scheduler, state trackers).
- Config/schema hardening: JSON schema validation for settings, clear env vs settings precedence, ensured directories and logging defaults.
- Metadata pipeline: flat metadata validators, RAGFlow upload/parse structured events, duplicate handling, and metadata push coverage.
- Observability: structured logging across pipeline/scheduler/web routes, FlareSolverr metrics/events, pipeline metrics endpoint, step timing capture.
- Security posture: TLS/HSTS + proxy guidance (`TRUST_PROXY_COUNT`), basic-auth defaults documented, secrets kept in `.env` with tightened checklist.
- Tests: added integration coverage for pipeline upload/failure, scheduler, registry discovery; unit coverage for auth, validation, and RAGFlow metadata uploads. Last run: `pytest tests/unit/test_basic_auth.py tests/unit/test_validation.py tests/unit/test_ragflow_upload_metadata.py tests/integration/test_pipeline_mocked.py tests/integration/test_pipeline_upload_flow.py tests/integration/test_pipeline_failure_flow.py tests/integration/test_scheduler_mocked.py tests/integration/test_registry_discovery.py`.
- Dependency hardening: pinned constraints, documented `pip-audit` security scan.
