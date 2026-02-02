## 2024-05-22 - Copy to Clipboard Fallback
**Learning:** `navigator.clipboard` is only available in secure contexts (HTTPS/localhost). Many self-hosted apps run on HTTP within private networks.
**Action:** Always include a fallback to `document.execCommand('copy')` for internal tools or self-hosted apps to ensure accessibility for all users.

## 2026-02-02 - HTMX Loading States
**Learning:** HTMX `hx-indicator` with `this` works best when coupled with a CSS class pattern like `.btn-with-loader`. Legacy JS handlers might interfere with text replacement.
**Action:** Use `.btn-with-loader` class and ensure JS handlers check for this class before manual DOM manipulation.
