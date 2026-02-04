## 2024-05-22 - Copy to Clipboard Fallback
**Learning:** `navigator.clipboard` is only available in secure contexts (HTTPS/localhost). Many self-hosted apps run on HTTP within private networks.
**Action:** Always include a fallback to `document.execCommand('copy')` for internal tools or self-hosted apps to ensure accessibility for all users.

## 2026-02-04 - Standardized Button Loading State
**Learning:** HTMX buttons can easily support loading states by toggling visibility of text/loader elements based on the `htmx-request` class. This pattern is robust and should be applied to all async buttons.
**Action:** Use `.btn-with-loader` wrapper with `.btn-text` and `.btn-loader` children, plus `hx-indicator` pointing to self.
