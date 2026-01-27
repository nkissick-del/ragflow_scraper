## 2026-01-27 - Missing CSRF Protection in HTMX App
**Vulnerability:** The application used HTMX for state-changing POST requests (e.g., running scrapers, changing settings) but lacked CSRF protection. Flask-WTF was not installed or configured.
**Learning:** HTMX applications require explicit CSRF token handling, often via `hx-headers` or `htmx:configRequest` event, as they don't submit standard forms that Flask-WTF auto-instruments.
**Prevention:** Always install `Flask-WTF` in Flask apps and configure a global `htmx:configRequest` listener to inject the CSRF token from a meta tag into headers for all AJAX/HTMX requests.
