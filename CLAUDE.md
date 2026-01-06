# PDF Scraper AI Coding Agent Instructions

**Purpose:** Enable fast, safe contributions to the Multi-Site PDF Scraper with RAGFlow integration.

---

## 1. System Overview

**Stack:**

- Flask backend with HTMX web interface (Pure JS, NO Alpine.js)
- Selenium + BeautifulSoup4 for scraping
- FlareSolverr for Cloudflare bypass
- RAGFlow integration for document ingestion
- Docker Compose orchestration (macOS, Linux, or Unraid)

**Purpose:**

- Modular scraper for Australian energy sector documents and news
- **PDF scrapers**: AEMO, AEMC, AER, ENA, ECA (download and store files)
- **Article scrapers**: RenewEconomy, TheEnergy, Guardian (extract content as Markdown)
- HTMX-based admin UI for configuration and monitoring
- CLI interface for n8n integration

**Key Organizations:** AEMO, AEMC, AER, ENA (Australian energy sector bodies)
**News Sources:** RenewEconomy, TheEnergy, The Guardian Australia, The Conversation

---

## 2. Deployment Context

**Configuration:**

- Location: Project root directory
- **Single source of truth:** `.env` file for ALL runtime config
- **NEVER duplicate keys** in `docker-compose.yml` `environment:` blocks

**Containers:**

- `pdf-scraper-dev`: Flask backend + HTMX UI (port 5050 external, 5000 internal)
- `pdf-scraper-chrome-dev`: Selenium/Chromium (port 4444, VNC 7900)

**Note:** Use `docker compose exec scraper` or `docker exec pdf-scraper-dev` for commands.

---

## 3. Pre-Session Verification Checklist

**Before starting work on this project:**

- [ ] **Containers running:** `docker compose ps`
- [ ] **Health check:** `curl http://localhost:5050/` (Dashboard loads)
- [ ] **Selenium ready:** `curl http://localhost:4444/wd/hub/status`

**Container Rebuild Required When:**

```bash
# ALWAYS rebuild after these changes:
docker compose build --no-cache scraper && docker compose up -d
```

**Rebuild Triggers (CRITICAL):**

1. **Dependencies changed** (`requirements.txt` modified)
2. **New Python files created** (new scrapers, utils, services)
3. **Core module changes** (imports, class names, package structure)
4. **Before running integration tests** (ensures consistent environment)

**Why rebuild matters:**

- Volume mounts sync host→container for EXISTING files only
- NEW files may not appear in container immediately
- Dependencies must be installed in container Python environment
- Import caches need to be refreshed

**Hot-Reload Workflow (EXISTING FILES ONLY):**

- Volume mounts: `./app`, `./data`, `./config`, `./logs`
- Flask debug mode reloads on Python changes to existing files
- Template changes reflect immediately
- **Exception:** NEW files always require rebuild or restart

---

## 4. Critical File Storage Rules

**CRITICAL:** Container filesystem is ephemeral. Wrong storage = data loss on restart.

### Storage Decision Table

| Use Case | Location | Persistence |
| -------- | -------- | ----------- |
| Downloaded PDFs | `/app/data/scraped/` | **Persistent** |
| Document metadata | `/app/data/metadata/` | **Persistent** |
| Scraper state (processed URLs) | `/app/data/state/` | **Persistent** |
| Application logs | `/app/data/logs/` | **Persistent** |
| Scraper configs | `/app/config/scrapers/` | **Persistent** |
| Short-lived temp (in-request) | `/tmp/` | **Ephemeral** |

### Volume Mounts (docker-compose.yml)

```yaml
volumes:
  - ./data:/app/data      # All persistent data
  - ./config:/app/config  # Configuration files
  - ./logs:/app/logs      # Application logs
```

---

## 5. Architecture Quick Reference

### Core Flow

**PDF Scrapers:**

```
Website -> Selenium/FlareSolverr -> Parse Listing HTML -> Extract Metadata ->
Download PDF -> Save to /app/data/scraped/{scraper}/ -> Update State ->
Optional: Upload to RAGFlow
```

**Article Scrapers (HTML-based):**

```
Website -> Selenium -> Parse Listing HTML -> Extract Article URLs ->
Visit Each Article -> Extract JSON-LD Dates -> Convert HTML to Markdown ->
Save .md + .json to /app/data/scraped/{scraper}/ -> Update State
```

**Article Scrapers (Feed/API-based):**

```
Feed/API -> HTTP Request -> Parse Feed Entries -> Extract Full Content ->
Convert HTML to Markdown -> Save .md + .json to /app/data/scraped/{scraper}/ ->
Update State (no Selenium required, much more efficient)
```

### Project Structure

```
scraper/
├── app/
│   ├── main.py                 # Flask entry point
│   ├── config.py               # Configuration management
│   ├── scrapers/               # Scraper modules
│   │   ├── base_scraper.py     # Abstract base class
│   │   ├── aemo_scraper.py     # PDF scraper example
│   │   ├── reneweconomy_scraper.py  # HTML article scraper example
│   │   ├── guardian_scraper.py # API-based article scraper
│   │   ├── the_conversation_scraper.py  # Feed-based article scraper
│   │   └── scraper_registry.py # Auto-discovery
│   ├── services/               # External integrations
│   │   ├── ragflow_client.py   # RAGFlow API
│   │   ├── state_tracker.py    # URL tracking
│   │   ├── settings_manager.py # Settings persistence
│   │   └── flaresolverr_client.py
│   ├── orchestrator/           # Scheduling/pipelines
│   ├── web/                    # Flask routes + templates
│   └── utils/
│       ├── markdown_converter.py  # GFMConverter for articles
│       └── file_utils.py       # File handling utilities
├── config/                     # Configuration files
├── data/                       # Persistent data
└── scripts/                    # CLI tools
```

### Adding a New Scraper

1. Create file in `app/scrapers/` (e.g., `my_scraper.py`)
2. Inherit from `BaseScraper`
3. Implement required methods: `scrape()`, `parse_page()`
4. Set class attributes: `name`, `display_name`, `description`, `base_url`
5. Scraper auto-discovered via registry
6. **Restart container:** `docker compose restart scraper`

```python
from app.scrapers.base_scraper import BaseScraper, DocumentMetadata, ScraperResult

class MyScraper(BaseScraper):
    name = "my-site"  # lowercase, unique
    display_name = "My Site"  # Human-readable name for UI
    description = "Scrapes documents from example.com"
    base_url = "https://example.com/documents"

    def scrape(self) -> ScraperResult:
        # Implementation
        pass

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        # Parse HTML and return document metadata
        pass
```

### PDF vs Article Scrapers

**PDF Scrapers** (AEMO, AEMC, AER, ENA, ECA):

- Download binary PDF files directly
- Single-stage: parse listing page → download files
- Output: PDF files + JSON metadata sidecar
- RAGFlow settings: `default_chunk_method = "paper"`, `default_parser = "DeepDOC"`

**Article Scrapers - HTML** (RenewEconomy, TheEnergy):

- Extract HTML content and convert to Markdown
- Two-stage: listing page → visit each article page for full content
- Uses Selenium WebDriver for page fetching
- Output: Markdown (.md) files with YAML frontmatter + JSON sidecar
- RAGFlow settings: `default_chunk_method = "naive"`, `default_parser = "Naive"`
- Use `ArticleConverter` from `app/utils/article_converter.py` (trafilatura-based)
- Extract JSON-LD for accurate dates (listing pages often omit year)

**Article Scrapers - Feed/API** (Guardian, The Conversation):

- Use RSS/Atom feeds or APIs instead of HTML scraping
- Single-stage: feed/API returns full content (no individual page visits needed)
- Override `run()` to skip Selenium WebDriver (uses `requests.Session`)
- Much more efficient: ~40 HTTP requests vs ~1000+ for HTML scraping
- Output: Markdown (.md) files with YAML frontmatter + JSON sidecar
- RAGFlow settings: `default_chunk_method = "naive"`, `default_parser = "Naive"`
- Requires `feedparser` library for Atom/RSS feeds

**Article Scraper Pattern:**

```python
from app.utils import ArticleConverter

class MyArticleScraper(BaseScraper):
    default_chunk_method = "naive"
    default_parser = "Naive"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._markdown = ArticleConverter()
        self._session_processed_urls: set[str] = set()  # Cross-category dedup

    def _extract_jsonld_dates(self, html: str) -> dict:
        # Parse <script type="application/ld+json"> for datePublished
        pass

    def _extract_article_content(self, html: str) -> str:
        # ArticleConverter automatically extracts main content (no selectors needed)
        return self._markdown.convert(html)
```

**Feed/API Scraper Pattern:**

```python
import feedparser
import requests
from app.utils import GFMConverter

class MyFeedScraper(BaseScraper):
    FEED_URL = "https://example.com/feed.atom"
    default_chunk_method = "naive"
    default_parser = "Naive"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: Optional[requests.Session] = None
        self._markdown = GFMConverter(extra_exclude_selectors=[".ads"])

    def run(self) -> ScraperResult:
        """Override to skip Selenium WebDriver."""
        self._session = requests.Session()
        try:
            result = self.scrape()
        finally:
            self._session.close()
        return result

    def _fetch_feed_page(self, url: str) -> list:
        response = self._session.get(url, timeout=30)
        feed = feedparser.parse(response.content)
        return feed.entries

    def _extract_content_html(self, entry) -> str:
        # Feed content is in entry.content[0].value
        if entry.get("content"):
            return entry["content"][0].get("value", "")
        return entry.get("summary", "")

    def parse_page(self, page_source: str) -> list[DocumentMetadata]:
        return []  # Not used for feed-based scrapers
```

---

## 6. Base Scraper API

### Key Methods Available

| Method | Description |
|--------|-------------|
| `init_cloudflare_and_fetch_first_page()` | Bypass + fetch first page. Returns `(success, html)` |
| `fetch_page(url)` | Fetch page (auto FlareSolverr fallback) |
| `_is_processed(url)` | Check if URL already scraped |
| `_mark_processed(url, metadata)` | Mark URL as scraped |
| `_should_exclude(tags)` | Check against `excluded_tags` |
| `_download_file(url, filename, metadata)` | Download with retries |
| `_polite_delay()` | Wait `request_delay` seconds |
| `check_cancelled()` | Check if user cancelled |

### Key Attributes

| Attribute | Description |
|-----------|-------------|
| `self.logger` | Logger for this scraper |
| `self.dry_run` | True if preview mode |
| `self.max_pages` | Max pages to scrape (or None) |
| `self.excluded_tags` | Tags to filter out |
| `self.request_delay` | Delay between requests (seconds) |

---

## 7. Frontend Rules (HTMX)

**Stack:** HTMX + Pure JavaScript (NO Alpine.js, NO Vue, NO React)

### Key Rules

- **HTMX partials:** Return partial HTML for `hx-get`/`hx-post` targets
- **Full pages:** Return complete templates for direct navigation
- **Status updates:** Use `hx-trigger="every Xs"` for polling
- **Forms:** Use `hx-post` with `hx-swap` for dynamic updates

### HTMX Pattern Examples

```html
<!-- Status badge with auto-refresh -->
<span class="status-badge"
      hx-get="/scrapers/aemo/status"
      hx-trigger="every 5s"
      hx-swap="outerHTML">
  Running...
</span>

<!-- Run scraper button -->
<button hx-post="/scrapers/aemo/run"
        hx-target="#scraper-status"
        hx-swap="outerHTML">
  Run Now
</button>
```

---

## 8. Testing Quick Reference

### CRITICAL: Testing After Code Changes

After modifying code (new files, dependencies, imports), follow this EXACT workflow:

```bash
# 1. REBUILD CONTAINER FIRST (required for new files/dependencies)
docker compose build --no-cache scraper
docker compose up -d

# 2. VERIFY CONTAINER HEALTH
docker compose ps  # Should show "healthy"
curl -s http://localhost:5050/ | head -5  # Should return HTML

# 3. THEN run tests
docker compose exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run
```

**Why rebuild first:**

- NEW Python files won't exist in running container
- NEW dependencies (requirements.txt) won't be installed
- Import caches may be stale
- Volume mounts don't sync new files immediately

**Quick Tests (After Rebuild):**

```bash
# Syntax check (on host)
python3 -m py_compile app/scrapers/my_scraper.py

# Container health
curl -s http://localhost:5050/ | head -5
curl -s http://localhost:4444/wd/hub/status | jq .value.ready

# List scrapers via CLI
docker compose exec scraper python scripts/run_scraper.py --list-scrapers

# Run scraper (dry run)
docker compose exec scraper python scripts/run_scraper.py --scraper aemo --max-pages 1 --dry-run

# View logs
docker logs pdf-scraper -f --tail=100
```

---

## 9. Top 10 Critical Pitfalls

### 1. Edit Tool File Not Read

- **Symptom:** "File has not been read yet" error
- **Fix:** ALWAYS use Read tool before Edit tool

### 2. Cloudflare Blocking

- **Symptom:** Empty page content, challenge page HTML
- **Fix:** Enable FlareSolverr in settings, use `init_cloudflare_and_fetch_first_page()`

### 3. Selenium Session Timeout

- **Symptom:** "Session not found" or stale session errors
- **Fix:** Check Chrome container health, restart if needed

### 4. State File Corruption

- **Symptom:** Duplicate downloads or missed documents
- **Fix:** Check JSON validity in `/app/data/state/`, reset if corrupted

### 5. Shell Working Directory Reset

- **Symptom:** Commands fail after successful prior commands
- **Fix:** ALWAYS use absolute paths, never rely on shell state

### 6. Package Version Assumptions

- **Symptom:** `pip install` fails
- **Fix:** Verify versions exist on PyPI before adding to requirements.txt

### 7. Circular Imports

- **Symptom:** `ImportError: cannot import name 'X'`
- **Fix:** Use lazy imports within functions for shared modules

### 8. HTMX Response Mismatch

- **Symptom:** Partial HTML appears wrong or full page loads in div
- **Fix:** Check `hx-target` and `hx-swap` match response format

### 9. Selenium Selector Changes

- **Symptom:** Scraper returns 0 documents
- **Fix:** Re-analyze target website, update CSS selectors

### 10. RAGFlow API Errors

- **Symptom:** Upload failures, 401/403 errors
- **Fix:** Verify `RAGFLOW_API_KEY` and `RAGFLOW_API_URL` in `.env`

---

## 10. Verification Checklist

Before deploying changes:

**Code Quality:**

- [ ] All file changes applied with tools (not code blocks)
- [ ] Changes verified with Read immediately after Edit
- [ ] No syntax errors (`python3 -m py_compile`)

**Functional Verification:**

- [ ] Health endpoint returns 200 OK
- [ ] Scraper list loads in UI
- [ ] New scraper appears in registry (if added)
- [ ] Dry run completes without errors

**Docker:**

- [ ] Container builds without errors
- [ ] Volume mounts configured correctly
- [ ] Environment variables set in `.env`

---

## 11. CLI Interface

```bash
# List available scrapers
python scripts/run_scraper.py --list-scrapers

# Run scraper
python scripts/run_scraper.py --scraper aemo

# Run with options
python scripts/run_scraper.py --scraper aemo --max-pages 5 --output-format json

# Dry run (preview mode)
python scripts/run_scraper.py --scraper aemo --dry-run

# Upload to RAGFlow after scraping
python scripts/run_scraper.py --scraper aemo --upload-to-ragflow --dataset-id abc123
```

**Exit codes:**

- `0` = success
- `1` = failure
- `2` = partial success (some documents failed)

---

## 12. Quick Reference Commands

```bash
# Start/stop services
docker compose up -d
docker compose down

# Rebuild after code changes
docker compose build --no-cache && docker compose up -d

# Restart Flask to pick up new scraper files
docker compose restart scraper

# Container shell
docker exec -it pdf-scraper-dev bash
# Or using service name:
docker compose exec scraper bash

# List scrapers (verify new scraper is registered)
docker exec pdf-scraper-dev python scripts/run_scraper.py --list-scrapers

# Dry run a scraper
docker exec pdf-scraper-dev python scripts/run_scraper.py --scraper guardian --max-pages 1 --dry-run

# View Selenium VNC (debugging)
open vnc://localhost:7900  # password: secret (or none if SE_VNC_NO_PASSWORD=1)

# Check scraper state
cat data/state/aemo_processed.json | jq . | head -20

# Clear scraper state (re-download all)
rm data/state/aemo_processed.json
```

---

## 13. Environment Variables

Key variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_ENV` | Environment mode | production |
| `FLASK_DEBUG` | Debug mode (1=on) | 0 |
| `PORT` | Web UI port | 5050 |
| `RAGFLOW_API_URL` | RAGFlow endpoint | <http://localhost:9380> |
| `RAGFLOW_API_KEY` | RAGFlow auth token | (required) |
| `SELENIUM_REMOTE_URL` | Chrome container URL | <http://chrome:4444/wd/hub> |
| `LOG_LEVEL` | Logging verbosity | INFO |

---

## 14. Agent Communication Preferences

**CRITICAL:** Respect these output preferences:

### What NOT to Do

- Do NOT create single-use README files
- Do NOT generate visual summary documents
- Do NOT provide unsolicited documentation
- Do NOT over-explain completed work

### What TO Do

- Answer direct questions concisely
- Provide code changes, then stop
- Ask clarifying questions if needed
- Report completion status briefly

### Output Pattern

1. **Execute the task** (use tools to make changes)
2. **Verify the task** (confirm changes took effect)
3. **Report completion** (one sentence status)
4. **Stop and wait** for next instruction

---

## 15. When Unsure

1. **Check project knowledge:** Search for patterns in existing scrapers
2. **Inspect existing code:** Mimic structure from `aemo_scraper.py`
3. **Verify against codebase:** Don't assume - grep and verify
4. **Ask for clarification:** Better to confirm than implement wrong pattern
5. **Keep changes incremental:** Avoid speculative refactors

---

## 16. Periodic Re-Reading Requirement

**When to Re-Read:**

- After every 10-15 tool invocations
- After encountering errors
- Before starting a new phase
- When about to do something "obvious"

| Situation | Section to Re-Read |
|-----------|-------------------|
| Adding new scraper | Section 5 (Architecture), Section 6 (Base Scraper API) |
| File storage decisions | Section 4 (Critical File Storage Rules) |
| HTMX issues | Section 7 (Frontend Rules) |
| Testing failures | Section 8 (Testing), Section 9 (Pitfalls) |

---

## 17. Curl Timeout Policy

All curl commands MUST include explicit timeouts:

```bash
# Health check (fast)
curl -sS --fail --connect-timeout 1 --max-time 2 http://localhost:5050/

# Selenium status
curl -sS --fail --connect-timeout 2 --max-time 5 http://localhost:4444/wd/hub/status

# Scraper action
curl -sS --fail --connect-timeout 5 --max-time 30 -X POST http://localhost:5050/scrapers/aemo/run
```

---

## 18. Type Annotation Pitfalls (Pylance/Pyright)

### Missing Future Import for Modern Type Syntax

- **Symptom:** Pylance shows errors like `"list" is not subscriptable` or `"dict" is not subscriptable`
- **Cause:** Using `list[str]`, `dict[str, Any]`, `tuple[int, int]` without future import
- **Fix:** Add `from __future__ import annotations` as first import after docstring

### Dataclass Mutable Default

- **Symptom:** `Mutable default argument` warning
- **Cause:** Using `field: list = []` or `field: list = None` in dataclass
- **Fix:** Use `field: list[T] = field(default_factory=list)`

### Required Pattern for All New Python Files

```python
"""
Module docstring here.
"""

from __future__ import annotations  # ALWAYS add this line

import ...
```

### Third-Party Libraries Without Type Stubs

- **Symptom:** `Import "X" could not be resolved` or `Type of "X" is unknown`
- **Cause:** Library (e.g., `bs4`, `schedule`) doesn't have type stubs
- **Fix:** Add `# type: ignore[import-untyped]` comment to import

```python
from bs4 import BeautifulSoup  # type: ignore[import-untyped]
```

### Common Pylance Error Patterns

| Error Message | Cause | Fix |
|--------------|-------|-----|
| `"list" is not subscriptable` | Missing future import | Add `from __future__ import annotations` |
| `"dict" is not subscriptable` | Missing future import | Add `from __future__ import annotations` |
| `Mutable default argument` | `list = []` in dataclass | Use `field(default_factory=list)` |
| `Missing type parameter` | `list` without `[T]` | Specify type: `list[str]` |
| `Import could not be resolved` | Missing type stubs | Add `# type: ignore[import-untyped]` |
| `Type of parameter is unknown` | Missing annotation on `*args`/`**kwargs` | Use `*args: Any, **kwargs: Any` |

---

## 19. Markdown Linting Rules

When creating or editing Markdown files, follow these rules to avoid linter warnings:

### Headings

- Always add a blank line before AND after headings
- Don't place content immediately after a heading without a blank line

```markdown
## Good Example

Content here with blank line above.

## Another Heading

More content.
```

### Lists

- Always add a blank line before AND after lists
- Use consistent list markers (all `-` or all `*`, not mixed)
- For checklists, use `- [ ]` format (unordered) not numbered `1. [ ]`

```markdown
Some paragraph text.

- Item one
- Item two
- Item three

Next paragraph.
```

### Ordered Lists

- Use consistent numbering: either all `1.` (auto-number) or sequential `1. 2. 3.`
- Don't continue numbering across separate list sections (start fresh at 1)

### Code Blocks

- Always add a blank line before AND after fenced code blocks

```markdown
Some text.

\`\`\`python
code here
\`\`\`

More text.
```

### Tables

- Use consistent spacing around pipes
- Align header separator row with content

```markdown
| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
```

---

## 20. RAGFlow Metadata Integration Patterns

### Overview

The RAGFlow metadata integration implements a **global solution** that works across all scrapers without duplicating code. This section documents critical patterns learned during implementation.

### Architecture: Global vs Per-Scraper

**Design Decision:** Centralize metadata workflow in shared services, not individual scrapers.

**Implementation:**

- **Scrapers set**: `organization` and `document_type` fields only (2 fields)
- **RAGFlowClient handles**: Upload, deduplication, status polling, metadata push (all workflow logic)
- **run_scraper.py coordinates**: Loading sidecars, calling client methods, reporting statistics

**Why this works:**

- Avoids duplicating API integration code across 9 scrapers
- Single point of maintenance for metadata push logic
- Scrapers focus on domain-specific data extraction

### Standard Metadata Fields

When integrating with external APIs, always get explicit field requirements upfront.

**RAGFlow Metadata Schema:**

**Required fields (always included):**

```python
{
    "organization": str,      # Required - use "Unknown" if unavailable
    "source_url": str,        # Required - from DocumentMetadata.url
    "scraped_at": str,        # Required - ISO timestamp
    "document_type": str,     # Required - "Report", "Article", etc.
}
```

**Optional fields (only included if available):**

```python
{
    "publication_date": str,  # ISO format - omitted if not available
    "author": str,            # From extra dict - omitted if not available
    "abstract": str,          # From extra dict - omitted if not available
}
```

**Critical Lessons:**

- "Standard fields" is ambiguous - always get specific list with data types and null handling requirements
- Per RAGFlow docs: "If a parameter does not exist or is None, it won't be updated"
- Omit optional fields entirely rather than sending "null" strings

### Poll-Until-Ready Pattern for Async APIs

When external APIs process uploads asynchronously, implement polling before dependent operations.

**Pattern:**

```python
def wait_for_document_ready(dataset_id: str, document_id: str,
                           timeout: float = 10.0,
                           poll_interval: float = 0.5) -> bool:
    """Poll document status until ready or timeout."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        status = self.get_document_status(dataset_id, document_id)

        if status in ["registered", "parsing", "parsed"]:
            return True
        elif status == "failed":
            return False

        time.sleep(poll_interval)

    # Timeout - log warning but allow workflow to continue
    logger.warning(f"Document {document_id} not ready after {timeout}s")
    return False
```

**Why this matters:**

- RAGFlow (and similar APIs) may not be immediately ready for metadata after upload
- Attempting metadata push too early results in 404 or similar errors
- Graceful timeout allows workflow to continue (metadata push attempted anyway)

### Deduplication by Content Hash

Prevent duplicate uploads by comparing SHA256 file hashes before upload.

**Implementation:**

```python
def check_document_exists(dataset_id: str, file_hash: str) -> Optional[str]:
    """Query dataset for document with matching hash."""
    # GET /api/v1/datasets/{dataset_id}/documents
    # Iterate through documents, compare hash field
    # Return document_id if match found, None otherwise
```

**Trade-offs:**

- **Pro:** Prevents duplicate processing and storage
- **Con:** May be slow for large datasets (N documents queried)
- **Alternative:** Consider server-side hash indexing if available

**Note:** Assumes RAGFlow API returns `hash` or `file_hash` field in document objects (UNTESTED).

### Fallback Chains for Optional Fields

Use multi-level fallbacks when metadata fields may be unavailable, and omit fields entirely if no value is found.

**Pattern:**

```python
def to_ragflow_metadata(self) -> dict:
    metadata = {
        "organization": self.organization or "Unknown",  # Required
        "source_url": self.url,  # Required
        "scraped_at": self.scraped_at,  # Required
        "document_type": self.document_type or "Unknown",  # Required
    }

    # Add optional fields only if they have actual values
    if self.publication_date:
        metadata["publication_date"] = self.publication_date

    if self.extra.get("author"):
        metadata["author"] = self.extra["author"]

    # Abstract with fallback chain (try multiple keys)
    abstract = self.extra.get("abstract") or self.extra.get("description")
    if abstract:
        metadata["abstract"] = abstract

    return metadata
```

**Why this works:**

- Different scrapers may store same semantic data under different keys
- Guardian API provides "trail_text", The Conversation provides "summary"
- Both map to same "abstract" field in RAGFlow
- Per RAGFlow docs: "If a parameter does not exist or is None, it won't be updated"
- Omitting fields is cleaner than sending string "null" values

### Markdown Content Separation

When storing article content as Markdown, ensure metadata doesn't duplicate in both frontmatter and body.

**Implementation (already correct in base_scraper.py:721-800):**

```python
# YAML frontmatter contains metadata
frontmatter = "---\n"
frontmatter += f"title: {metadata.title}\n"
frontmatter += f"url: {metadata.url}\n"
# ... more metadata fields
frontmatter += "---\n\n"

# Markdown body contains ONLY article content (no metadata duplication)
markdown_body = self._markdown.convert(article_html)

full_content = frontmatter + markdown_body
```

**Why this matters:**

- RAGFlow receives metadata via API (structured data)
- Markdown file contains content for chunking/embedding
- Duplicating metadata in both wastes tokens and confuses retrieval

### Graceful Degradation for Metadata Failures

Upload workflow must succeed even if metadata push fails.

**Pattern:**

```python
# Phase 1: Upload document (critical - must succeed)
upload_result = self.upload_document(dataset_id, filepath)
if not upload_result.success:
    return upload_result  # FAIL - stop here

# Phase 2: Wait for ready (best effort)
ready = self.wait_for_document_ready(dataset_id, upload_result.document_id)

# Phase 3: Push metadata (optional - log warning on failure)
if metadata:
    metadata_success = self.set_document_metadata(
        dataset_id, upload_result.document_id, metadata
    )
    if not metadata_success:
        logger.warning(f"Metadata push failed for {filename}, but upload succeeded")
else:
    logger.info(f"No metadata sidecar found for {filename}")

# ALWAYS return success if upload succeeded
upload_result.metadata_pushed = metadata_success
return upload_result
```

**Result Tracking:**

```python
@dataclass
class UploadResult:
    success: bool             # Upload succeeded (critical)
    skipped_duplicate: bool   # Skipped due to hash match
    metadata_pushed: bool     # Metadata push succeeded (optional)
```

### Circular Import Avoidance

When shared services need to import from scrapers, use runtime imports inside methods.

**Problem:**

```python
# ragflow_client.py (top level)
from app.scrapers.base_scraper import DocumentMetadata  # May cause circular import
```

**Solution:**

```python
# ragflow_client.py
def upload_documents_with_metadata(self, docs: list[dict]) -> list[UploadResult]:
    from pathlib import Path  # Runtime import
    from app.scrapers.base_scraper import DocumentMetadata  # Runtime import
    from app.services.ragflow_metadata import prepare_metadata_for_ragflow

    # ... implementation
```

**Why this works:**

- Import happens when method is called, not when module is loaded
- Breaks circular dependency chain
- Acceptable for service methods (not called at module load time)

### Testing Documentation for Unavailable APIs

When external APIs are down during development, create comprehensive testing guides for future validation.

**Template:** See [docs/TODO-metadata-testing.md](docs/TODO-metadata-testing.md)

**Contents:**

1. Pre-testing setup (verify containers, config)
2. Test suites (single upload, bulk upload, deduplication, error handling)
3. Verification steps (check RAGFlow UI, query API)
4. Troubleshooting guide (common errors and fixes)
5. Success criteria checklist
6. Document untested API assumptions

**Benefits:**

- Enables systematic testing when API becomes available
- Documents expected behavior for future maintainers
- Tracks untested assumptions that need verification

### Critical Untested Assumptions

When implementing against unavailable APIs, document all assumptions for future verification.

**RAGFlow API Assumptions (2026-01-06 - NEEDS TESTING):**

1. **Metadata endpoint**: `PUT /api/v1/datasets/{id}/documents/{doc_id}` with `{"meta_fields": {...}}`
2. **Status endpoint**: `GET /api/v1/datasets/{id}/documents/{doc_id}` returns `{"status": "registered|parsing|parsed|failed"}`
3. **Hash field name**: Documents include `hash` or `file_hash` field (for deduplication)
4. **Optional field handling**: Omitting fields works correctly (based on RAGFlow docs stating "If a parameter does not exist or is None, it won't be updated")

**Action Required:** Test all assumptions when RAGFlow server is available using testing guide.

### Configuration Options for Metadata

Provide environment variables to disable/tune metadata behavior without code changes.

**Added to config.py:**

```python
# RAGFlow Metadata Settings
RAGFLOW_PUSH_METADATA = os.getenv("RAGFLOW_PUSH_METADATA", "true").lower() == "true"
RAGFLOW_METADATA_TIMEOUT = float(os.getenv("RAGFLOW_METADATA_TIMEOUT", "10.0"))
RAGFLOW_METADATA_POLL_INTERVAL = float(os.getenv("RAGFLOW_METADATA_POLL_INTERVAL", "0.5"))
RAGFLOW_METADATA_RETRIES = int(os.getenv("RAGFLOW_METADATA_RETRIES", "3"))
RAGFLOW_CHECK_DUPLICATES = os.getenv("RAGFLOW_CHECK_DUPLICATES", "true").lower() == "true"
```

**Use cases:**

- Disable metadata push during testing: `RAGFLOW_PUSH_METADATA=false`
- Increase timeout for slow servers: `RAGFLOW_METADATA_TIMEOUT=30.0`
- Disable deduplication: `RAGFLOW_CHECK_DUPLICATES=false`

### Key Learnings Summary

1. **Always clarify "standard fields"** - get explicit lists with data types and null handling
2. **Runtime imports are acceptable** for avoiding circular dependencies in service methods
3. **Global solution beats per-scraper duplication** - centralize workflow logic
4. **Poll-until-ready pattern required** for async API operations
5. **Fallback chains handle missing metadata** gracefully across different scrapers
6. **Document untested assumptions** extensively when APIs are unavailable
7. **Graceful degradation is critical** - don't fail uploads due to metadata issues

### Sprint Learnings (2026-01-06)

- Added optional basic auth gate across web routes; when running tests on host, set DOWNLOAD_DIR/METADATA_DIR/STATE_DIR/LOG_DIR/CONFIG_DIR to writable paths to avoid read-only `/app` during Config.ensure_directories().
- Logging now defaults to JSON lines with size-based rotation and backup retention; tune via LOG_JSON_FORMAT, LOG_FILE_MAX_BYTES, LOG_FILE_BACKUP_COUNT, LOG_TO_FILE, LOG_LEVEL in [app/config.py](app/config.py) and ensure container rebuild after env/requirements changes.
- Introduced [constraints.txt](constraints.txt) and linked requirements to it; resolved lxml pin to 5.2.2 to satisfy trafilatura. Use pip-compile or equivalent to refresh pins.
- New auth smoke tests live in [tests/unit/test_basic_auth.py](tests/unit/test_basic_auth.py); they pass when env paths are overridden as above. pytest-asyncio emits deprecation warnings on Python 3.14—safe to ignore or pin once an updated release lands.

---

## Documentation Links

- [instructions.md](instructions.md) - Original project requirements
- [docs/SCRAPER_PROMPT.md](docs/SCRAPER_PROMPT.md) - Website analysis prompt for new scrapers
- [README.md](README.md) - User-facing project overview
- [docs/TODO-metadata-testing.md](docs/TODO-metadata-testing.md) - RAGFlow metadata testing guide

---

**Last Updated:** January 6, 2026
