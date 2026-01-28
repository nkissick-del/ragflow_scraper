## 2026-01-28 - Missing CSRF Protection
**Vulnerability:** Global CSRF protection was missing in the Flask application, despite documentation stating it was enforced via `Flask-WTF`.
**Learning:** Documentation can drift from implementation. Reliance on documentation for security assurances is dangerous without code verification.
**Prevention:** Implement integration tests that specifically verify security controls (e.g., asserting that POST requests without CSRF tokens are rejected).
