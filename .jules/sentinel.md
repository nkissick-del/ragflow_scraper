# Sentinel Security Journal

## 2024-05-22 - Missing CSRF Protection in HTMX Apps
**Vulnerability:** The application had no CSRF protection on POST endpoints (`/run`, `/cancel`, etc.), allowing attackers to trigger scraper actions via malicious sites.
**Learning:** HTMX applications are vulnerable to CSRF just like traditional forms. Unlike standard forms where `Flask-WTF` injects tokens automatically, HTMX requires explicit header injection (`X-CSRFToken`) via JavaScript listeners (`htmx:configRequest`).
**Prevention:** Always enable global CSRF protection (`Flask-WTF`) and ensure a global JavaScript listener attaches the token to all HTMX requests. Verify with a specific integration test that forces `WTF_CSRF_ENABLED=True`.
