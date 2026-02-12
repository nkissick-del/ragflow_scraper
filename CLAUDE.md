# PDF Scraper AI Coding Agent Instructions

**Purpose:** Enable fast, safe contributions to the Multi-Site PDF Scraper with RAGFlow integration.

---

## 1. System Overview

**Stack:**

- Flask backend with HTMX web interface (Pure JS, NO Alpine.js)
- FlareSolverr + BeautifulSoup4 for scraping (Cloudflare bypass built-in)
- RAGFlow integration for document ingestion
- Docker Compose orchestration (macOS, Linux, or Unraid)

## AI Agent Instruction Set

Purpose: Provide a tight, actionable playbook for AI coding agents contributing to this repository. Keep responses concise, make precise changes, verify, report, and stop.

Stuck or encountering a failure? First re-read this file. If the answer isn’t here, consult the deeper background in docs/AI_AGENT_REFERENCE.md and then proceed with the smallest viable change.

---

## Mission & Scope

- Implement requested changes safely and exactly within this repo.
- Use the dev Docker stack and Make targets for all runs/tests.
- Prioritize minimal, scoped diffs that match existing patterns.

## Golden Rules

- Use dev compose always: `make dev-up`, not local Python.
- Run tests in the container: `make test` or `make test-file FILE=...`.
- Keep changes focused; avoid speculative refactors or new files unless asked.
- Follow existing style and structure; prefer smallest viable diff.
- Don’t add new READMEs or sprawling docs—link to existing docs instead.

## Environment & Commands

- Build/run: `make dev-build` then `make dev-up`.
- Shell/logs: `make shell`, `make logs`.
- Tests: `make test`, `make test-unit`, `make test-int`, `make test-file FILE=...`.
- Dev UI: <http://localhost:5001> (container listens on 5000).
- FlareSolverr: <http://localhost:8191> (rendered page fetching).

Notes:

- Tests and docs are bind-mounted; edits apply without rebuilds.
- Rebuild image only when dependencies or new Python files are added.

## Workflow (Do This Every Time)

1) Plan: State brief intent and steps. 2) Change: Apply minimal diffs. 3) Verify: Run the smallest relevant tests/commands. 4) Report: One-sentence status and next optional step.

## Backend Architecture (v2.0)

**Modular Pipeline** with swappable backends:
- **Parser**: PDF → Markdown (Docling, MinerU, Tika)
- **Archive**: Document storage (Paperless-ngx, S3, local)
- **RAG**: Vector indexing (RAGFlow, AnythingLLM)

**Pipeline Flow:**
1. Scraper downloads PDF
2. Parser converts PDF → Markdown + extracts metadata
3. Metadata merge (smart strategy: context from scraper, content from parser)
4. Jinja2 canonical filename generation
5. Archive to Paperless (source of truth for originals)
6. Verify document (poll archive API until document is confirmed stored)
7. RAG ingest Markdown (not PDF)
8. Delete local files (after verification)

**Configuration (ENV vars):**
- `PARSER_BACKEND=docling` (docling, mineru, tika)
- `ARCHIVE_BACKEND=paperless` (paperless, s3, local)
- `RAG_BACKEND=ragflow` (ragflow, anythingllm, pgvector)
- `METADATA_MERGE_STRATEGY=smart` (smart, parser_wins, scraper_wins)

**ServiceContainer access:**
```python
parser = container.parser_backend  # ParserBackend instance
archive = container.archive_backend  # ArchiveBackend instance
rag = container.rag_backend  # RAGBackend instance
```

**Error handling:**
- Parser/Archive failures: FAIL FAST (raise error, stop pipeline)
- RAG failures: Non-fatal (log error, continue to cleanup)

## Coding Guidelines

- Respect public APIs; don't rename or move modules casually.
- Add types where obvious; avoid intrusive annotation rewrites.
- Prefer existing utilities (logging, retry, metadata prep) over duplicates.
- Data/State/Logs paths must remain under `/app/data` inside the container.
- ServiceContainer: use properties (`settings`, `ragflow_client`, `flaresolverr_client`, `parser_backend`, `archive_backend`, `rag_backend`, `state_tracker()`, `scheduler`); legacy getters (e.g., `get_parser_backend()`, `get_rag_backend()`, `get_archive_backend()`, `get_scheduler()`) are removed. Replace with property access (e.g., `container.parser_backend`).

## Testing & Rebuild Rules

- Quick test cycle: `make test-file FILE=tests/unit/...`.
- Full run for confidence: `make test`.
- Rebuild required when: `requirements*.txt` change or you add new Python files.
- After rebuild: `make dev-up` and rerun tests.

## Communication Contract

- Keep answers short. Provide code changes, the exact commands you ran, and final status.
- Ask only necessary clarifying questions. Avoid long explanations.
- When blocked by environment or missing data, state the blocker and propose a narrow next step.

## Safety & Access

- Do not hardcode secrets or URLs; use `.env`/settings.
- Use structured logging helpers for errors and events.
- Avoid wide file edits; touch only what’s necessary.

## Quick Checks Before You Start

- Dev stack running: `make dev-up`.
- Health endpoints reachable (optional):
  - App: `curl -sS --fail http://localhost:5001/ | head -5`.
  - FlareSolverr: `curl -sS --fail http://localhost:8191/health`.

## Common Tasks for AI Assistants

### Task 1: Adding a New Scraper

1. Create `app/scrapers/{name}_scraper.py` with class inheriting `BaseScraper`
2. Define `NAME`, `DISPLAY_NAME`, `DESCRIPTION`, `BASE_URL`
3. Implement `scrape()` returning `ScraperResult`
4. Implement `get_metadata()` returning metadata dict
5. Test with `make test-file FILE=tests/unit/test_{name}_scraper.py`

See [DEVELOPER_GUIDE.md](docs/development/DEVELOPER_GUIDE.md) and [EXAMPLE_SCRAPER_WALKTHROUGH.md](docs/development/EXAMPLE_SCRAPER_WALKTHROUGH.md).

### Task 2: Debugging Scraper Issues

```bash
# Check recent logs
make logs | tail -100

# View scraper state
cat data/state/{scraper_name}_state.json | jq

# Run in dry-run mode (no downloads)
docker exec scraper-app python -m scripts.run_scraper --scraper {name} --dry-run

# FlareSolverr handles rendered page fetching automatically
```

### Task 3: Modifying Web UI

- Web UI uses **Flask blueprints**, not routes.py (that was deleted in Phase 2)
- Edit `app/web/routes.py` for HTTP endpoints
- Templates in `app/web/templates/`, static files in `app/web/static/`
- HTMX for dynamic UI (NO Alpine.js)

### Task 4: RAGFlow Integration

- Client: `container.ragflow_client` (property access)
- Workflow: Create dataset → Add documents → Parse → Check status
- Metadata: Prepared by `prepare_for_ragflow()` in `ragflow_metadata.py`
- See [CONFIG_AND_SERVICES.md](docs/development/CONFIG_AND_SERVICES.md)

### Task 5: Quick Documentation Lookup

- **Operations:** [DEPLOYMENT_GUIDE.md](docs/operations/DEPLOYMENT_GUIDE.md), [RUNBOOK_COMMON_OPERATIONS.md](docs/operations/RUNBOOK_COMMON_OPERATIONS.md)
- **Development:** [DEVELOPER_GUIDE.md](docs/development/DEVELOPER_GUIDE.md), [EXAMPLE_SCRAPER_WALKTHROUGH.md](docs/development/EXAMPLE_SCRAPER_WALKTHROUGH.md)
- **Standards:** [ERROR_HANDLING.md](docs/development/ERROR_HANDLING.md), [METADATA_SCHEMA.md](docs/reference/METADATA_SCHEMA.md)

---

## References (Read When Needed)

- Metadata: [docs/reference/METADATA_SCHEMA.md](docs/reference/METADATA_SCHEMA.md)
- Error Handling & Logging: [docs/development/ERROR_HANDLING.md](docs/development/ERROR_HANDLING.md)
- Config & Services: [docs/development/CONFIG_AND_SERVICES.md](docs/development/CONFIG_AND_SERVICES.md)
- Deployment: [docs/operations/DEPLOYMENT_GUIDE.md](docs/operations/DEPLOYMENT_GUIDE.md)
- Operations: [docs/operations/RUNBOOK_COMMON_OPERATIONS.md](docs/operations/RUNBOOK_COMMON_OPERATIONS.md)
- Development: [docs/development/DEVELOPER_GUIDE.md](docs/development/DEVELOPER_GUIDE.md)
- Example: [docs/development/EXAMPLE_SCRAPER_WALKTHROUGH.md](docs/development/EXAMPLE_SCRAPER_WALKTHROUGH.md)
- Troubleshooting: [docs/operations/troubleshooting/ragflow_scraper_audit.md](docs/operations/troubleshooting/ragflow_scraper_audit.md)

---

Last Updated: 2026-02-13
