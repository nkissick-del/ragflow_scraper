## 2024-05-23 - Dead Code Removal (Security Debt)
**Vulnerability:** The file `app/web/routes.py` contained unpatched Path Traversal and Reflected XSS vulnerabilities. Although not currently registered in the application, it posed a significant risk of accidental re-enablement or copy-paste propagation.
**Learning:** Vulnerabilities can hide in dead or legacy code. Static analysis tools might flag them, but runtime context determines exploitability. Leaving dead code with known vulnerabilities is technical/security debt.
**Prevention:** Regularly audit the codebase for unused files and remove them. Use coverage tools to identify dead code.

## 2026-02-03 - Missing CSRF Protection in Flask App
**Vulnerability:** The application exposed state-changing endpoints (POST /scrapers/run) without Cross-Site Request Forgery (CSRF) protection. While Basic Auth was enabled, browsers automatically attach these credentials, allowing malicious sites to trigger actions on behalf of authenticated users.
**Learning:** The codebase was missing the standard `Flask-WTF` library despite documentation/memory suggesting it was present. This highlights the importance of verifying configuration against actual dependencies.
**Prevention:**
1. Initialize `CSRFProtect(app)` in the application factory.
2. Ensure `<meta name="csrf-token" content="{{ csrf_token() }}">` is present in base templates.
3. Add specific integration tests that verify requests fail without a token (400 Bad Request) to prevent regression.

## 2025-02-18 - Missing Security Headers
**Vulnerability:** The Flask application was missing critical security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), exposing it to clickjacking and MIME sniffing attacks.
**Learning:** Security headers must be explicitly added via an `@app.after_request` hook in `app/web/__init__.py`, as Flask does not provide them by default.
**Prevention:** Ensure `app/web/__init__.py` always includes the `add_security_headers` function and that integration tests verify their presence.

## 2026-02-07 - Inconsistent Input Validation & Logic Bug in Scraper Blueprint
**Vulnerability:** The `app/web/blueprints/scrapers.py` endpoints failed to validate `name` parameter format and `max_pages` values, unlike the API blueprint. This allowed:
1.  Modifying settings for non-existent scrapers (polluting `settings.json`).
2.  Passing negative `max_pages` values (which were ignored due to a precedence bug: `max_pages or 1 if dry_run else None`).
**Learning:**
1.  **Inconsistent Validation:** When duplicating logic between UI and API blueprints, ensure validation is applied consistently.
2.  **Operator Precedence:** Python's `if else` has lower precedence than `or`. `x or y if c else z` parses as `x or (y if c else z)`, not `(x or y) if c else z`.
**Prevention:**
1.  Centralize validation logic where possible.
2.  Use explicit parentheses in complex boolean expressions.
3.  Verify inputs against the registry/database before performing actions (defense in depth).

## 2026-02-08 - Unvalidated Configuration Injection in Scraper Settings
**Vulnerability:** The `save_scraper_ragflow_settings` endpoint in `app/web/blueprints/scrapers.py` accepted arbitrary strings for configuration values (e.g., `chunk_method`, `pdf_parser`). This allowed persisting invalid or potentially malicious payloads (e.g., XSS vectors) into the settings file, which could be executed if rendered unsafe or used in sensitive contexts.
**Learning:**
1.  **Trust Boundary Violation:** Input from the web UI was trusted implicitly and saved directly to the backend configuration.
2.  **Missing Schema Validation:** While `SettingsManager` uses JSON schema, the `scrapers` section was defined as `{"type": "object"}`, bypassing validation for dynamic keys.
**Prevention:**
1.  Validate all user input against allowlists (enums) where possible (e.g., `CHUNK_METHODS`).
2.  Use strict regex for identifiers (e.g., `pipeline_id`, `dataset_id`).
3.  Do not rely solely on frontend validation or generic schema validation for critical settings.
