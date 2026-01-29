## 2024-05-22 - Copy to Clipboard Fallback
**Learning:** `navigator.clipboard` is only available in secure contexts (HTTPS/localhost). Many self-hosted apps run on HTTP within private networks.
**Action:** Always include a fallback to `document.execCommand('copy')` for internal tools or self-hosted apps to ensure accessibility for all users.

## 2026-01-29 - Dynamic Content Accessibility
**Learning:** Dynamic content like toast notifications and client-side navigation updates are often invisible to screen readers without explicit ARIA roles.
**Action:** Always add `role="alert"` or `role="status"` to toast notifications, and ensure `aria-current="page"` is updated on navigation links.
