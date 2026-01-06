# PDF Scraper AI Coding Agent Instructions

**Purpose:** Enable fast, safe contributions to the Multi-Site PDF Scraper with RAGFlow integration.

---

## 1. System Overview

**Stack:**

- Flask backend with HTMX web interface (Pure JS, NO Alpine.js)
- Selenium + BeautifulSoup4 for scraping
- FlareSolverr for Cloudflare bypass
- RAGFlow integration for document ingestion
- Docker Compose orchestration (macOS, Linux, or Unraid)

# AI Agent Instruction Set

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
- Dev UI: http://localhost:5001 (container listens on 5000).
- Chrome: Selenium on 4444; VNC on 7900.

Notes:
- Tests and docs are bind-mounted; edits apply without rebuilds.
- Rebuild image only when dependencies or new Python files are added.

## Workflow (Do This Every Time)

1) Plan: State brief intent and steps. 2) Change: Apply minimal diffs. 3) Verify: Run the smallest relevant tests/commands. 4) Report: One-sentence status and next optional step.

## Coding Guidelines

- Respect public APIs; don’t rename or move modules casually.
- Add types where obvious; avoid intrusive annotation rewrites.
- Prefer existing utilities (logging, retry, metadata prep) over duplicates.
- Data/State/Logs paths must remain under `/app/data` inside the container.

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
  - Selenium: `curl -sS --fail http://localhost:4444/wd/hub/status`.

## References (Read When Needed)

- Metadata: docs/METADATA_SCHEMA.md
- Logging: docs/LOGGING_AND_ERROR_STANDARDS.md
- Config & Services: docs/CONFIG_AND_SERVICES.md
- Error Handling: docs/ERROR_HANDLING.md
- Scraper Template: docs/SCRAPER_TEMPLATE.md

---

Last Updated: 2026-01-07
```
