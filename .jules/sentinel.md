## 2025-02-12 - Missing CSRF Protection and Security Headers

**Vulnerability:** The application lacked CSRF protection (Flask-WTF was missing) and basic security headers, despite memory indicating CSRF was enforced.
**Learning:** Documentation/Memory can drift from reality. The memory stated "CSRF protection is enforced using Flask-WTF", but the library was not installed nor initialized. Always verify security controls in code.
**Prevention:** Verify dependencies and initialization code for critical security controls. Use automated security headers testing.
