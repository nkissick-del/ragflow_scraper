## 2025-02-18 - Missing Security Headers
**Vulnerability:** The Flask application was missing critical security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), exposing it to clickjacking and MIME sniffing attacks.
**Learning:** Security headers must be explicitly added via an `@app.after_request` hook in `app/web/__init__.py`, as Flask does not provide them by default.
**Prevention:** Ensure `app/web/__init__.py` always includes the `add_security_headers` function and that integration tests verify their presence.
