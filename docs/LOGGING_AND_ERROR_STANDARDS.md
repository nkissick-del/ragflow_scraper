# Logging & Error Standards

This document defines how to use logging consistently across scrapers, how to interpret logs, and how to diagnose common failures.

---

## Log Level Mapping

Each log level serves a specific purpose. Choose the right level for your message:

### DEBUG

**Use when:** Detailed diagnostic information for troubleshooting specific issues.  
**Audience:** Developers debugging a failing scraper.  
**Frequency:** Rarely in production (disabled by default via `LOG_LEVEL=INFO`).

```python
logger.debug(f"Parsing HTML: {len(html)} bytes, encoding={charset}")
logger.debug(f"FlareSolverr response headers: {response.headers}")
logger.debug(f"Retrying request (attempt {attempt}/{max_attempts}, backoff={delay}s)")
```

**When to use:**

- Function entry/exit (with parameters)
- Loop iterations over large datasets
- Conditional branch selection logic
- Raw HTTP request/response data (headers, body)
- Regex matches and parsing steps

### INFO

**Use when:** Normal operation milestones that operators should see.  
**Audience:** Operators monitoring scraper runs in production.  
**Frequency:** 5–20 log lines per scraper run.

```python
logger.info(f"Downloaded: {filename} ({file_size_str})")
logger.info(f"Processed 25 documents from {source_url}")
logger.info(f"Dataset '{dataset_name}' created (id={dataset_id})")
logger.info(f"RAGFlow metadata push completed: 25 docs")
```

**When to use:**

- Scraper start/stop
- Documents downloaded, skipped, or failed
- Major milestone completions
- External service connections (RAGFlow, FlareSolverr)
- Run statistics (total processed, deduped, errors)

### WARNING

**Use when:** Unexpected condition that scraper can recover from, but operator should investigate.  
**Audience:** Operators scanning logs for issues.  
**Frequency:** 1–5 per run (should be rare).

```python
logger.warning(f"Document missing author metadata: {title}")
logger.warning(f"FlareSolverr timed out (60s), falling back to direct request")
logger.warning(f"RAGFlow API slow (8s), consider checking server load")
logger.warning(f"HTML parsing failed for {url}, using fallback title extraction")
```

**When to use:**

- Missing optional metadata (recovered with default)
- Retries triggered (will continue)
- Service timeouts with fallback (e.g., FlareSolverr → direct)
- Data validation warnings (unusual but valid)
- Rate limiting (will backoff and retry)

### ERROR

**Use when:** Recoverable error; operation failed but scraper continues with next item.  
**Audience:** Operators assessing scraper health.  
**Frequency:** 1–3 per failed document.

```python
logger.error(f"Failed to download {url}: HTTP 403 (retrying...)")
logger.error(f"Document validation failed: missing required field 'title'")
logger.error(f"RAGFlow upload failed for {filename}: dataset not found (will retry)")
```

**When to use:**

- Document download failed (but will retry or skip)
- Required metadata missing (document skipped)
- API call failed (will retry)
- Parsing error on single document (move to next)
- State corruption (will reset and continue)

### CRITICAL

**Use when:** Unrecoverable error; scraper must stop or entire run is compromised.  
**Audience:** Operators; triggers alerts.  
**Frequency:** 0–1 per run (should be exceptional).

```python
logger.critical(f"Configuration file corrupted: {config_path}")
logger.critical(f"RAGFlow server unreachable: {ragflow_url}")
logger.critical(f"Disk full: cannot write to {data_dir}")
```

**When to use:**

- Configuration or secrets missing
- External service permanently unreachable
- Filesystem errors (no write permission, disk full)
- Database corruption
- Unrecoverable exception in main loop

---

## Structured Logging Format

### Standard Message Structure

All log messages should include:

```logs
<action>: <resource> | <context> | <result>
```

**Parts:**

- **Action:** Verb (Downloaded, Parsed, Validated, Failed, Started, etc.)
- **Resource:** Object being acted upon (filename, URL, dataset_id, document count)
- **Context:** Relevant details (size, duration, attempt number, reason)
- **Result:** Outcome (success, skipped, retried, error code)

### Examples

✅ **Good:**

```python
logger.info(f"Downloaded: aemo_2025_q1.pdf (2.0 MB, 1.2s)")
logger.warning(f"FlareSolverr timeout: {url} (60s limit), retrying with direct request")
logger.error(f"Parse failed: {filename} (missing title, skipping)")
```

❌ **Poor:**

```python
logger.info("Done")  # No context
logger.error("Error")  # No details
logger.info("Processing started")  # No resource identifier
```

### Structured JSON Logging

When `STRUCTURED_LOGGING_ENABLED=true`, logs are emitted as JSON for machine parsing:

```json
{
  "timestamp": "2026-01-07T14:32:45.123456",
  "level": "INFO",
  "logger": "scraper.aemo",
  "message": "Downloaded: aemo_2025_q1.pdf (2.0 MB, 1.2s)",
  "scraper": "aemo",
  "document": "aemo_2025_q1.pdf",
  "duration_seconds": 1.2,
  "file_size_bytes": 2097152,
  "operation": "download",
  "status": "success"
}
```

### Emitting Structured Logs

Use [logging_config.py](../app/utils/logging_config.py) utilities:

```python
from app.utils.logging_config import get_logger, log_event, log_exception

logger = get_logger("aemo")

# Simple message
logger.info("Documents downloaded: 25")

# Structured event with context dict
log_event(
    logger, 
    "info", 
    "aemo.download.complete",
    document="aemo_2025_q1.pdf",
    size_bytes=2097152,
    duration_seconds=1.2,
    status="success"
)

# Exception with context
try:
    upload_to_ragflow(doc_metadata)
except Exception as e:
    log_exception(
        logger, 
        e, 
        "ragflow.upload.failed",
        dataset_id="dataset_123",
        document="aemo_2025_q1.pdf",
        retry_count=2
    )
```

---

## Log File Rotation & Retention

### Configuration

Controlled by environment variables consumed in [app/utils/logging_config.py](../app/utils/logging_config.py#L19) via [app/config.py](../app/config.py#L53):

```bash
LOG_LEVEL=INFO                # Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_JSON_FORMAT=true          # Emit JSON logs to file handler
LOG_TO_FILE=true              # Enable file handler; console is always on
LOG_FILE_MAX_BYTES=10485760   # Single file size limit (10 MB by default)
LOG_FILE_BACKUP_COUNT=5       # Number of rolled-over files to keep
LOG_DIR=/app/data/logs        # Optional override for log directory
```

### Log Directory

By default logs are written under `data/logs` (from `Config.LOG_DIR`). When the logger name is `scraper`, the primary file is `data/logs/scraper.log` with rotated siblings.

```tree
data/logs/
├── scraper.log              # Current log file
├── scraper.log.1            # Previous rotation
├── scraper.log.2
├── scraper.log.3
├── scraper.log.4
└── scraper.log.5            # Oldest retained file
```

### Rotation Policy

- **Max file size:** 10 MB (configurable via `LOG_FILE_MAX_SIZE_MB`)
- **Backup count:** 5 files retained (configurable via `LOG_FILE_BACKUP_COUNT`)
- **Total retention:** ~50 MB on disk
- **Behavior:** When `scraper.log` reaches 10 MB, it is renamed to `scraper.log.1`, `scraper.log.1` → `scraper.log.2`, etc. Files older than `scraper.log.5` are deleted.

### Archival Strategy

For long-term retention:

1. Copy logs to external storage before rotation:

   ```bash
   gsutil cp logs/scraper.log.* gs://archive-bucket/logs/$(date +%Y-%m-%d)/
   ```

2. Or use a monitoring service (e.g., Splunk, Datadog) to ingest logs before rotation.

---

## Web UI Log Access

The web dashboard exposes logs for operators without SSH access.

### Routes

**[GET /](../app/web/routes.py)**  
Dashboard homepage. Shows:

- List of all configured scrapers
- Last run timestamp per scraper
- Next scheduled run (if applicable)

**[GET /scraper/{scraper_name}](../app/web/routes.py)**  
Scraper detail page. Shows:

- Current configuration (filters, tags, dataset_id)
- Recent logs (last 50 lines from `logs/scraper.log`)
- Run history and statistics

### Log Viewing

1. Navigate to `http://localhost:5000/scraper/aemo`
2. Scroll to **Recent Logs** section
3. Click **Download Logs** to export full `logs/scraper.log`
4. Use browser search (Ctrl+F / Cmd+F) to find keyword

### Optional Authentication

If `WEB_AUTH_ENABLED=true`, basic authentication is enforced:

```bash
export WEB_AUTH_USERNAME=admin
export WEB_AUTH_PASSWORD=secret123
```

**Access:** `http://admin:secret123@localhost:5000/`

---

## Error Telemetry & Alerting

### Error Types to Track

Track these error types for metrics and alerts:

| Error Type | Code | Count In | Alert Threshold |
| ---------- | ---- | -------- | --------------- |
| Network timeout | NET_TIMEOUT | `logs/` | 5+ in single run |
| HTTP 403/401 | AUTH_ERROR | `logs/` | Any (likely credentials expired) |
| Parsing failure | PARSE_ERROR | `logs/` | 20%+ of documents |
| Missing metadata | VALIDATION_ERROR | `logs/` | Any required field |
| RAGFlow unavailable | RAGFLOW_UNREACHABLE | `logs/` | Any (external dependency) |
| Duplicate document | DEDUP_SKIPPED | Dashboard | High count (check hash logic) |
| Disk full | IO_ERROR | `logs/` | Any (investigate storage) |

### How to Capture Metrics

Log errors with consistent event names:

```python
# In scraper
logger.error(f"NET_TIMEOUT: {url} (attempt {attempt}/{max_attempts})")

# In RAGFlow client
logger.critical(f"RAGFLOW_UNREACHABLE: {ragflow_url} (no response)")

# In state tracking
logger.error(f"DEDUP_SKIPPED: {url} (hash match)")
```

Then parse logs to extract counts:

```bash
# Count network timeouts
grep "NET_TIMEOUT" logs/scraper.log | wc -l

# Count all errors
grep "ERROR\|CRITICAL" logs/scraper.log | wc -l

# Filter by scraper
grep "scraper.aemo" logs/scraper.log | grep "ERROR" | wc -l
```

### Alert Examples

**Automatic alerts** (if using Splunk/DataDog integration):

```alerts
- Alert: CRITICAL logs found
  Condition: count(level=CRITICAL) >= 1
  Action: Email ops@example.com

- Alert: High error rate
  Condition: count(level=ERROR) / count(level=INFO) > 0.5 in 1 hour
  Action: Slack #alerts

- Alert: RAGFLOW_UNREACHABLE
  Condition: count(message contains "RAGFLOW_UNREACHABLE") >= 1
  Action: PagerDuty escalation
```

---

## Common Errors & Troubleshooting Flowchart

### Troubleshooting Flowchart

```tree
SCRAPER RUN FAILED
│
├─ Check last 10 lines of logs/scraper.log
│  │
│  ├─ Contains "CRITICAL" or "RAGFLOW_UNREACHABLE"?
│  │  └─ YES → External service unavailable (see below)
│  │  └─ NO  → Continue
│  │
│  └─ Contains "PARSE_ERROR" or "VALIDATION_ERROR"?
│     └─ YES → Scraper logic error (see below)
│     └─ NO  → Continue
│
├─ Check scraper-specific error patterns (below)
│
└─ If no clear match: Enable DEBUG logging and re-run
   LOG_LEVEL=DEBUG docker compose exec scraper python scripts/run_scraper.py --scraper <name>
```

### Error Pattern Reference

#### Network & Connectivity Errors

**Error:** `NET_TIMEOUT` or `connect timed out`  
**Cause:** Network unreachable or host slow  
**Fix:**

1. Check network: `ping <host>`
2. Increase timeout: `SCRAPER_REQUEST_TIMEOUT=30`
3. Check firewall rules (port 80, 443)

**Error:** `HTTP 403 Forbidden` or `HTTP 401 Unauthorized`  
**Cause:** Credentials expired or missing  
**Fix:**

1. Verify API keys in `.env`
2. Re-authenticate with service (login page)
3. Check if IP is blocklisted (contact support)

**Error:** `SSL_ERROR` or `certificate verify failed`  
**Cause:** TLS certificate invalid or expired  
**Fix:**

1. Update CA bundle: `pip install --upgrade certifi`
2. Check system clock is accurate
3. If on custom network, check corporate proxy config

#### FlareSolverr Errors

**Error:** `FlareSolverr timeout` or `no response from FlareSolverr`  
**Cause:** FlareSolverr service down or slow  
**Fix:**

1. Check FlareSolverr status: `docker compose ps flaresolverr`
2. Restart: `docker compose restart flaresolverr`
3. Check logs: `docker compose logs flaresolverr | tail -20`
4. Fallback: Set `FLARESOLVERR_ENABLED=false` (direct requests only)

**Error:** `FlareSolverr max retries exceeded`  
**Cause:** Page contains anti-bot challenges FlareSolverr cannot solve  
**Fix:**

1. Try manual inspection of page in browser
2. Check if CloudFlare rules have changed
3. Report to FlareSolverr project if consistently failing

#### RAGFlow Errors

**Error:** `RAGFLOW_UNREACHABLE` or `Connection refused`  
**Cause:** RAGFlow server not running  
**Fix:**

1. Start services: `docker compose --profile full up -d`
2. Verify RAGFlow: `curl http://localhost:9380/`
3. Check logs: `docker compose logs ragflow | tail -30`

**Error:** `Authentication failed` or `Bearer token invalid`  
**Cause:** API key expired or missing  
**Fix:**

1. Regenerate API key in RAGFlow UI
2. Update `.env` with new key: `RAGFLOW_API_KEY=<key>`
3. Restart scraper: `docker compose restart scraper`

**Error:** `Dataset not found` or `404`  
**Cause:** Dataset ID is wrong or deleted  
**Fix:**

1. List datasets: `curl -H "Authorization: Bearer $RAGFLOW_API_KEY" http://localhost:9380/api/v1/datasets`
2. Update config with correct dataset_id
3. Or create new dataset: `RAGFLOW_AUTO_CREATE_DATASET=true`

**Error:** `Document parse timeout` or `parsing stuck`  
**Cause:** RAGFlow overloaded or document very large  
**Fix:**

1. Wait (parsing can take minutes for large files)
2. Check RAGFlow status: `docker compose logs ragflow | grep -i "parse\|timeout"`
3. Reduce `RAGFLOW_PARSER_CHUNK_TOKEN_NUM` (default 128) to 64
4. Split large documents before upload

#### Parsing & Metadata Errors

**Error:** `PARSE_ERROR: failed to extract title`  
**Cause:** Page HTML structure changed or page is broken  
**Fix:**

1. Inspect page: `curl -s <url> | head -50`
2. Update scraper CSS selectors in [config/scrapers/{scraper}.json](../config/scrapers/)
3. Test locally with single page: `python scripts/run_scraper.py --scraper <name> --max-pages 1`

**Error:** `VALIDATION_ERROR: missing required field 'title'`  
**Cause:** Scraper extracted empty or malformed title  
**Fix:**

1. Check HTML structure: does page have a title?
2. Enable DEBUG logs: `LOG_LEVEL=DEBUG`
3. Add fallback logic in scraper (e.g., use URL as title)

**Error:** `VALIDATION_ERROR: publication_date not ISO 8601`  
**Cause:** Date format wrong (e.g., "Jan 7, 2026" instead of "2026-01-07")  
**Fix:**

1. Normalize date in scraper before creating metadata:

   ```python
   publication_date = datetime.strptime(date_str, "%b %d, %Y").isoformat().split('T')[0]
   ```

2. Update date extraction regex in scraper

#### State & Deduplication Errors

**Error:** `STATE_ERROR: state file corrupted`  
**Cause:** Interrupted write or filesystem corruption  
**Fix:**

1. Inspect state file: `cat data/state/{scraper}_state.json | jq .`
2. If invalid JSON, delete it: `rm data/state/{scraper}_state.json`
3. Restart scraper (will recreate from scratch)

**Error:** `Duplicate detected (hash match)` but document is new  
**Cause:** Hash algorithm gave false positive or document content didn't change  
**Fix:**

1. Use `--force` flag to re-process: `python scripts/run_scraper.py --scraper {name} --force`
2. Or delete state and re-run: `rm data/state/{scraper}_state.json` (loses history)
3. If document is already in RAGFlow, manually delete and re-upload
4. Check if document content was actually updated

#### Resource & System Errors

**Error:** `Disk full` or `No space left on device`  
**Cause:** `/data` or `/logs` directories full  
**Fix:**

1. Check disk: `df -h`
2. Clean up old files: `rm -rf data/scraped/*/older_than_30_days`
3. Compress logs: `gzip logs/scraper.log.*`
4. Expand volume if using Docker

**Error:** `Out of memory` or `OOMKilled`  
**Cause:** Too many concurrent downloads or Chrome memory leak  
**Fix:**

1. Reduce concurrency: `MAX_CONCURRENT_DOWNLOADS=1` (in env)
2. Restart Chrome container: `docker compose restart chrome`
3. Increase container memory limit in `docker-compose.yml`

---

## Logging Checklist for Contributors

When adding a new scraper or feature:

- [ ] Log scraper start: `logger.info(f"Starting {self.name} scraper")`
- [ ] Log each document download: `logger.info(f"Downloaded: {filename}")`
- [ ] Log skipped documents with reason: `logger.warning(f"Skipped {url}: {reason}")`
- [ ] Log errors with context: `logger.error(f"Failed {action}: {url} ({error})")`
- [ ] Log RAGFlow interactions: `logger.info(f"Pushed metadata: {count} docs")`
- [ ] Use structured logging for metrics: `log_event(logger, "info", "event.name", key=value)`
- [ ] Catch exceptions and log before re-raising: `log_exception(logger, e, "operation.failed")`
- [ ] Test with DEBUG level: `LOG_LEVEL=DEBUG python scripts/run_scraper.py ...`
- [ ] Verify logs are human-readable and actionable (no cryptic messages)

---

## References

- [logging_config.py](../app/utils/logging_config.py) – Logging setup and structured utilities
- [BaseScraper](../app/scrapers/base_scraper.py) – Example logging patterns
- [AEMO Scraper](../app/scrapers/aemo_scraper.py) – Concrete logging examples
- [Pipeline](../app/orchestrator/pipeline.py) – Pipeline-level structured logging
- [Web Routes](../app/web/routes.py) – Log exposure via web UI
