# Secrets Rotation Guide

How to rotate every credential used by the PDF Scraper stack.

---

## Quick Reference

| Variable | Service | Impact of Rotation |
|---|---|---|
| `SECRET_KEY` | Flask | Invalidates all sessions and CSRF tokens |
| `BASIC_AUTH_USERNAME` | Web UI | Users must re-authenticate |
| `BASIC_AUTH_PASSWORD` | Web UI | Users must re-authenticate |
| `PAPERLESS_API_TOKEN` | Paperless-ngx | Archive uploads fail until updated |
| `RAGFLOW_API_KEY` | RAGFlow | RAG ingestion fails until updated |
| `RAGFLOW_USERNAME` | RAGFlow | Admin session auth fails until updated |
| `RAGFLOW_PASSWORD` | RAGFlow | Admin session auth fails until updated |
| `ANYTHINGLLM_API_KEY` | AnythingLLM | RAG ingestion fails until updated |
| `GUARDIAN_API_KEY` | The Guardian | Guardian scraper returns 403 |
| `OPENROUTER_API_KEY` | OpenRouter VLM | VLM graph extraction fails (optional) |
| `AWS_SECRET_ACCESS_KEY` | S3 archive | S3 uploads fail until updated |

---

## General Process

1. Generate the new credential in the upstream service.
2. Update `.env` with the new value.
3. Recreate the scraper container: `make dev-down && make dev-up` (or `docker compose down && docker compose up -d`). Note: `docker compose restart` does **not** reload `.env` changes — you must recreate containers.
4. Verify using the command listed for each credential below.

> **Tip:** Rotate one credential at a time. Verify before moving to the next.

---

## Per-Credential Instructions

### `SECRET_KEY` — Flask Sessions & CSRF

**Generate:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Apply:** Set `SECRET_KEY=<new_value>` in `.env` and restart.

**Impact:** All active browser sessions are invalidated. Users must re-authenticate (if Basic Auth is enabled) and any in-flight CSRF tokens become invalid.

**Verify:**
```bash
curl -sS -o /dev/null -w "%{http_code}" http://localhost:5001/scrapers
# Expect: 200 (or 401 if Basic Auth is enabled — that's correct)
```

---

### `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD` — Web UI Login

**Generate:** Choose a strong username and password. For the password:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

**Apply:** Set both `BASIC_AUTH_USERNAME` and `BASIC_AUTH_PASSWORD` in `.env` and restart. Both must be set when `BASIC_AUTH_ENABLED=true`.

**Impact:** All users must re-authenticate with the new credentials.

**Verify:**
```bash
curl -sS -u "newuser:newpass" -o /dev/null -w "%{http_code}" http://localhost:5001/scrapers
# Expect: 200
```

---

### `PAPERLESS_API_TOKEN` — Paperless-ngx

**Generate:** In Paperless-ngx web UI:
1. Go to **Settings → Users & Groups → your user**.
2. Under **Token**, click **Regenerate**.
3. Copy the new token.

Alternatively, via CLI:
```bash
docker exec paperless python manage.py generate_auth_token <username>
```

**Apply:** Set `PAPERLESS_API_TOKEN=<new_token>` in `.env` and restart.

**Impact:** All archive uploads and document verification fail until updated.

**Verify:**
```bash
curl -sS -H "Authorization: Token <new_token>" http://localhost:8000/api/documents/ | head -c 100
# Expect: JSON response with document list
```

---

### `RAGFLOW_API_KEY` — RAGFlow

**Generate:** In RAGFlow web UI:
1. Go to **User Settings → API Keys**.
2. Create a new key or regenerate the existing one.

**Apply:** Set `RAGFLOW_API_KEY=<new_key>` in `.env` and restart.

**Impact:** RAG ingestion via the RAGFlow backend fails until updated.

**Verify:**
```bash
curl -sS -H "Authorization: Bearer <new_key>" http://localhost:9380/api/v1/datasets | head -c 100
# Expect: JSON with dataset list
```

---

### `RAGFLOW_USERNAME` / `RAGFLOW_PASSWORD` — RAGFlow Admin

**Generate:** Change the password via RAGFlow's admin UI or API.

**Apply:** Set `RAGFLOW_USERNAME` and `RAGFLOW_PASSWORD` in `.env` and restart.

**Impact:** Admin session authentication fails until updated. Used for operations that require session-based auth rather than API key auth.

**Verify:** Log in to the RAGFlow web UI with the new credentials.

---

### `ANYTHINGLLM_API_KEY` — AnythingLLM

**Generate:** In AnythingLLM:
1. Go to **Settings → API Keys**.
2. Create a new key.
3. Delete the old key after verifying the new one works.

**Apply:** Set `ANYTHINGLLM_API_KEY=<new_key>` in `.env` and restart.

**Impact:** RAG ingestion via the AnythingLLM backend fails until updated.

**Verify:**
```bash
curl -sS -H "Authorization: Bearer <new_key>" http://localhost:3001/api/v1/auth | head -c 100
# Expect: JSON with authenticated: true
```

---

### `GUARDIAN_API_KEY` — The Guardian Open Platform

**Generate:** Visit [open-platform.theguardian.com](https://open-platform.theguardian.com/access/) to register a new key or manage existing ones.

**Apply:** Set `GUARDIAN_API_KEY=<new_key>` in `.env` and restart.

**Impact:** The Guardian scraper returns 403 errors until updated.

**Verify:**
```bash
curl -sS "https://content.guardianapis.com/search?api-key=<new_key>&page-size=1" | head -c 100
# Expect: JSON with "ok" status
```

---

### `OPENROUTER_API_KEY` — OpenRouter VLM (Optional)

**Generate:** Visit [openrouter.ai/keys](https://openrouter.ai/keys) to create a new API key.

**Apply:** Set `OPENROUTER_API_KEY=<new_key>` in `.env` and restart.

**Impact:** VLM graph/image extraction from PDFs fails. This feature is optional — the pipeline continues without it.

**Verify:**
```bash
curl -sS -H "Authorization: Bearer <new_key>" https://openrouter.ai/api/v1/models | head -c 100
# Expect: JSON with model list
```

---

### `AWS_SECRET_ACCESS_KEY` / `AWS_ACCESS_KEY_ID` — S3 Archive (Optional)

**Generate:** In AWS IAM:
1. Go to the IAM user → **Security credentials**.
2. Create a new access key pair.
3. Delete the old key after verifying.

**Apply:** Set both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env` and restart.

**Impact:** S3 archive uploads fail until updated. Only relevant when `ARCHIVE_BACKEND=s3`.

**Verify:**
```bash
aws s3 ls s3://<bucket-name>/ --region <region>
# Expect: bucket contents listed
```

---

## Rotation Schedule Recommendations

| Credential | Recommended Frequency |
|---|---|
| `SECRET_KEY` | Every 90 days or after any suspected compromise |
| `BASIC_AUTH_PASSWORD` | Every 90 days |
| `PAPERLESS_API_TOKEN` | Every 90 days |
| `RAGFLOW_API_KEY` | Every 90 days |
| `ANYTHINGLLM_API_KEY` | Every 90 days |
| `GUARDIAN_API_KEY` | Annually (low-risk, read-only) |
| `OPENROUTER_API_KEY` | Every 90 days (has billing implications) |
| `AWS_*` keys | Every 90 days (IAM best practice) |

---

## Troubleshooting

**Symptom: 401 errors after rotation**
- Verify the new value is in `.env` (no extra whitespace or quotes).
- Confirm the container was restarted after updating `.env`.
- Check that the upstream service accepted the new credential.

**Symptom: CSRF errors after `SECRET_KEY` rotation**
- Expected. Users need to reload the page to get a fresh CSRF token.

**Symptom: Pipeline runs fail after rotation**
- Check `data/logs/scraper.log` for the specific service returning auth errors.
- Use the Settings UI health checks to test each service connection.
