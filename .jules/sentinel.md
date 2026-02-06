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

## 2026-02-06 - Archiver Stored XSS Vulnerability
**Vulnerability:** The `Archiver` service injected unescaped metadata and content into the HTML template used for PDF generation. This allowed Stored XSS attacks where malicious scripts in scraped content (or metadata) would execute within the Selenium WebDriver context.
**Learning:** "Internal" components like PDF generators are valid XSS vectors. Existing documentation/memory claiming security controls exist must be verified against the code.
**Prevention:** Always use `html.escape()` when inserting strings into HTML templates. Sanitize HTML content using libraries like `BeautifulSoup` or `bleach` before rendering.
