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
