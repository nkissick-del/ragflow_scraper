# Phased TODO (use "plan phase X")

Legend: [Code] coding-only; [Local] requires local docker/compose; [External] needs RAGFlow/FlareSolverr or other outside services.

## Phase 1 – Completed (see docs/CHANGELOG.md)

## Phase 2 – Local validation and tooling (completed)
- Docker/compose hardening shipped: pinned images, labels, resource limits, no-new-privileges, Chrome isolation.
- State integrity tools added: checksum/schema validation and repair via CLI.
- Settings migration CLI added: validate/migrate settings.json and scraper configs against JSON schema.
- UI polish/accessibility done: ARIA roles/live regions, skip link, focus styles, responsive nav/layout.
- Resilience CLI delivered: state scan/repair commands and retry jitter/max-delay support.

## Phase 3 – External/RAGFlow-dependent work
- [External] RAGFlow metadata end-to-end validation (reuse existing checklist when server is up): API assumptions, status polling, hash/dedup, and flat meta enforcement (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1278)).
- [External] FlareSolverr/Cloudflare bypass observability: success-rate metrics, timeouts, fallback rules (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L325)).
- [External] Production security hardening: TLS termination, auth on web UI, secrets rotation; verify against live stack (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1387)).

## Phase 4 – Documentation and ops maturity
- [Code] Document unified config and service container patterns; add runbooks for migrations and state repair (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L347) and [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L390)).
- [Code] Update README/CLAUDE with metadata schema examples and logging/error standards (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1205) and [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L1157)).
- [Local/External] Add deployment guide covering compose profiles, FlareSolverr optionality, and RAGFlow connectivity tests (ref: [docs/ragflow_scraper_audit.md](docs/ragflow_scraper_audit.md#L757)).

## Quick commands (when services are available)
- RAGFlow health: `curl -sS --fail --connect-timeout 5 --max-time 10 http://localhost:9380/`
- Auth check: `curl -sS --fail -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
- Scraper dry-run example: `docker compose exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run`

## Notes
- Testing harness is largely in place; focus now is on consolidation, validation tooling, and production hardening.
- When asking for details, you can say "plan phase 2" (or any phase) and we will expand into a concrete task list with owners/tests.
