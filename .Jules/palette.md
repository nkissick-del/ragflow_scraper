## 2024-05-22 - Copy to Clipboard Fallback
**Learning:** `navigator.clipboard` is only available in secure contexts (HTTPS/localhost). Many self-hosted apps run on HTTP within private networks.
**Action:** Always include a fallback to `document.execCommand('copy')` for internal tools or self-hosted apps to ensure accessibility for all users.
