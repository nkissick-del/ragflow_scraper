## 2024-05-22 - Copy to Clipboard Fallback
**Learning:** `navigator.clipboard` is only available in secure contexts (HTTPS/localhost). Many self-hosted apps run on HTTP within private networks.
**Action:** Always include a fallback to `document.execCommand('copy')` for internal tools or self-hosted apps to ensure accessibility for all users.

## 2026-01-30 - HTMX Loading States
**Learning:** HTMX requests on buttons (like `hx-post`) don't provide visual feedback by default. This can lead to double-submissions and uncertainty for long-running tasks like scraper jobs.
**Action:** Use `hx-disabled-elt="this"` and `hx-indicator="this"` combined with `.btn-with-loader` CSS class to easily add loading spinners and prevent double-clicks without writing custom JS.
