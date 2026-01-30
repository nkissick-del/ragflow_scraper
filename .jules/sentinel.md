## 2024-05-23 - Dead Code Removal (Security Debt)
**Vulnerability:** The file `app/web/routes.py` contained unpatched Path Traversal and Reflected XSS vulnerabilities. Although not currently registered in the application, it posed a significant risk of accidental re-enablement or copy-paste propagation.
**Learning:** Vulnerabilities can hide in dead or legacy code. Static analysis tools might flag them, but runtime context determines exploitability. Leaving dead code with known vulnerabilities is technical/security debt.
**Prevention:** Regularly audit the codebase for unused files and remove them. Use coverage tools to identify dead code.
