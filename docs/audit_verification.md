# Audit Verification Notes

- Orchestrator exists: pipeline and scheduler modules live under `app/orchestrator/` and manage scrape→upload→parse and cron-style scheduling.
- Templates/static assets: present under `app/web/templates` and `app/web/static`; audit lacked full visibility.
- Scraper inventory: 9 concrete scrapers discovered via `ScraperRegistry` (aemc, aemo, aer, eca, ena, guardian, reneweconomy, the-conversation, theenergy).
- Error handling: previously broad `except Exception` blocks; no custom exceptions or retry helpers. Added standardized errors/retry in this sprint.
- Testing: no pytest/tests existed prior to this work; Dockerfile installed only runtime deps.
- Config: per-scraper config files only for aemo/template in `config/scrapers/`; settings manager persists to `config/settings.json`.
