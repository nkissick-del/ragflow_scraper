# Developer Guide

Complete guide for developers working on the PDF Scraper system.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Adding a New Scraper](#adding-a-new-scraper)
4. [Scraper Best Practices](#scraper-best-practices)
5. [Debugging Scrapers](#debugging-scrapers)
6. [Testing](#testing)
7. [Code Standards](#code-standards)
8. [Service Container Usage](#service-container-usage)

---

## Development Setup

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose** (for Selenium)
- **Git**

### Initial Setup

```bash
# 1. Clone repository
git clone <repository-url>
cd scraper

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
nano .env  # Configure as needed

# 5. Start Chrome container
docker run -d -p 4444:4444 -p 7900:7900 --shm-size=2g \
  seleniarm/standalone-chromium:120.0

# 6. Verify setup
python -m pytest tests/ -v
```

### IDE Setup (VS Code Recommended)

**Install extensions:**
- Python
- Pylance
- Pytest
- Docker

**Workspace settings** (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false
}
```

### Running the Application

**Web UI:**
```bash
python app/main.py
```
Access at http://localhost:5000

**CLI scraper:**
```bash
python scripts/run_scraper.py --scraper aemo --dry-run
```

---

## Project Structure

```
scraper/
├── app/
│   ├── __init__.py
│   ├── config.py                    # Configuration management
│   ├── main.py                      # Flask app entry point
│   ├── container.py                 # Service container
│   │
│   ├── scrapers/                    # Scraper implementations
│   │   ├── __init__.py
│   │   ├── base_scraper.py          # Base class with mixins
│   │   ├── models.py                # Data models (Result, Metadata, etc.)
│   │   ├── scraper_registry.py     # Auto-discovery
│   │   ├── mixins/                  # Reusable behaviors
│   │   │   ├── incremental_state.py
│   │   │   ├── metadata_io.py
│   │   │   ├── webdriver_lifecycle.py
│   │   │   └── ...
│   │   ├── aemo_scraper.py          # Example scrapers
│   │   ├── guardian_scraper.py
│   │   └── ...
│   │
│   ├── services/                    # External integrations
│   │   ├── __init__.py
│   │   ├── container.py             # Service container implementation
│   │   ├── ragflow_client.py        # RAGFlow API wrapper
│   │   ├── ragflow_ingestion.py     # Upload/poll workflow
│   │   ├── flaresolverr_client.py   # Cloudflare bypass
│   │   ├── settings_manager.py      # Runtime settings
│   │   └── state_tracker.py         # Per-scraper state
│   │
│   ├── orchestrator/                # Job scheduling
│   │   ├── pipeline.py              # Scrape → RAGFlow pipeline
│   │   └── scheduler.py             # Future: scheduled runs
│   │
│   ├── web/                         # Web interface
│   │   ├── __init__.py              # App factory
│   │   ├── runtime.py               # Container/queue instances
│   │   ├── job_queue.py             # Async job management
│   │   ├── helpers.py               # Template helpers
│   │   ├── blueprints/              # Modular routes
│   │   │   ├── scrapers.py          # Scraper control
│   │   │   ├── settings.py          # Settings management
│   │   │   ├── metrics_logs.py      # Monitoring
│   │   │   ├── api_scrapers.py      # REST API
│   │   │   └── ...
│   │   ├── templates/               # Jinja2 templates
│   │   └── static/                  # CSS, JS, images
│   │
│   └── utils/                       # Shared utilities
│       ├── logging_config.py        # Logging setup
│       ├── errors.py                # Custom exceptions
│       ├── retry.py                 # Retry decorator
│       ├── file_utils.py            # File operations
│       └── ...
│
├── config/                          # Configuration files
│   ├── settings.json                # Runtime settings (UI-editable)
│   └── scrapers/                    # Per-scraper configs
│       ├── aemo.json
│       ├── template.json
│       └── ...
│
├── data/                            # Runtime data (gitignored)
│   ├── scraped/{scraper}/           # Downloaded documents
│   ├── metadata/{scraper}/          # Document metadata
│   ├── state/{scraper}_state.json   # Incremental state
│   └── logs/scraper.log             # Application logs
│
├── docs/                            # Documentation
│   ├── DEPLOYMENT_GUIDE.md
│   ├── DEVELOPER_GUIDE.md (this file)
│   ├── EXAMPLE_SCRAPER_WALKTHROUGH.md
│   ├── METADATA_SCHEMA.md
│   ├── ERROR_HANDLING.md
│   └── ...
│
├── scripts/                         # CLI utilities
│   ├── run_scraper.py               # Main CLI entry point
│   └── ...
│
├── tests/                           # Test suite
│   ├── conftest.py                  # Pytest fixtures
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
│
├── .env.example                     # Environment template
├── requirements.txt                 # Production dependencies
├── requirements-dev.txt             # Development dependencies
├── docker-compose.yml               # Production compose
├── docker-compose.dev.yml           # Development compose
├── Makefile                         # Dev workflow shortcuts
└── README.md                        # Project overview
```

---

## Adding a New Scraper

### Step 1: Create Scraper File

Create `app/scrapers/my_scraper.py`:

```python
"""My Scraper - scrapes documents from example.com"""

from __future__ import annotations

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ScraperResult

class MyScraperImplementation(BaseScraper):
    """Scraper for Example Website."""
    
    NAME = "my-scraper"
    DISPLAY_NAME = "My Website"
    DESCRIPTION = "Scrapes PDFs from example.com"
    BASE_URL = "https://example.com/documents"
    
    def scrape(self) -> ScraperResult:
        """Main scraping logic."""
        self.log_event("scrape_started", scraper=self.NAME)
        
        try:
            # Your scraping logic here
            urls = self._get_document_urls()
            
            for url in urls:
                # Check if already processed
                if self.should_exclude_url(url):
                    continue
                
                # Download document
                filepath = self.download_file(url)
                
                # Extract metadata
                metadata = self.get_metadata(filepath, url)
                
                # Save metadata
                self.save_metadata(metadata)
                
                # Mark as processed
                self.mark_url_processed(url)
            
            return ScraperResult(
                status="completed",
                scraper=self.NAME,
                documents_processed=len(urls)
            )
        
        except Exception as e:
            self.log_exception("scrape_failed", e, scraper=self.NAME)
            return ScraperResult(
                status="failed",
                scraper=self.NAME,
                error=str(e)
            )
    
    def get_metadata(self, filepath, url) -> dict:
        """Extract document metadata."""
        return {
            "title": "Document Title",
            "source": self.NAME,
            "url": url,
            "file_path": str(filepath),
            "scraped_at": datetime.now().isoformat()
        }
    
    def _get_document_urls(self) -> list[str]:
        """Get list of document URLs to scrape."""
        # Implementation depends on website structure
        pass
```

### Step 2: Configure Scraper (Optional)

Create `config/scrapers/my-scraper.json`:

```json
{
  "enabled": true,
  "max_pages": 10,
  "request_delay": 1.0,
  "cloudflare_bypass": false,
  "exclusion_rules": {
    "excluded_tags": [],
    "excluded_keywords": [],
    "required_tags": []
  }
}
```

### Step 3: Test Scraper

Create `tests/unit/test_my_scraper.py`:

```python
"""Tests for MyScraperImplementation."""

import pytest
from unittest.mock import Mock, patch
from app.scrapers.my_scraper import MyScraperImplementation

@pytest.fixture
def scraper():
    """Create scraper instance."""
    with patch("app.scrapers.base_scraper.container"):
        return MyScraperImplementation()

def test_scraper_initialization(scraper):
    """Test scraper initializes correctly."""
    assert scraper.NAME == "my-scraper"
    assert scraper.DISPLAY_NAME == "My Website"

def test_get_metadata(scraper):
    """Test metadata extraction."""
    from pathlib import Path
    filepath = Path("/tmp/test.pdf")
    url = "https://example.com/doc.pdf"
    
    metadata = scraper.get_metadata(filepath, url)
    
    assert metadata["source"] == "my-scraper"
    assert metadata["url"] == url
    assert "title" in metadata
```

### Step 4: Run Scraper

```bash
# Dry run (no downloads)
python scripts/run_scraper.py --scraper my-scraper --dry-run

# Real run
python scripts/run_scraper.py --scraper my-scraper

# Via web UI
# Navigate to http://localhost:5000, find scraper card, click "Run Now"
```

### Step 5: Verify Results

```bash
# Check state file
cat data/state/my-scraper_state.json | jq .

# Check downloaded documents
ls -la data/scraped/my-scraper/

# Check metadata
ls -la data/metadata/my-scraper/

# Check logs
grep "my-scraper" data/logs/scraper.log
```

---

## Scraper Best Practices

### Use Mixins for Common Functionality

**IncrementalStateMixin** - Track processed URLs:
```python
class MyS craper(BaseScraper, IncrementalStateMixin):
    def scrape(self):
        if self.should_exclude_url(url):
            continue  # Already processed
        
        # ... download ...
        
        self.mark_url_processed(url)
```

**MetadataIOMixin** - Save/load metadata:
```python
class MyScraper(BaseScraper, MetadataIOMixin):
    def scrape(self):
        metadata = self.get_metadata(filepath, url)
        self.save_metadata(metadata)
```

**WebDriverLifecycleMixin** - Manage Selenium:
```python
class MyScraper(BaseScraper, WebDriverLifecycleMixin):
    def scrape(self):
        driver = self.get_driver()
        driver.get(self.BASE_URL)
        # ... use driver ...
        self.quit_driver()  # Automatic cleanup
```

**CloudflareBypassMixin** - Handle Cloudflare:
```python
class MyScraper(BaseScraper, CloudflareBypassMixin):
    def scrape(self):
        content = self.get_with_flaresolverr(url)
        # FlareSolverr bypasses Cloudflare
```

### Structured Logging

Use `log_event()` and `log_exception()`:

```python
from app.utils.logging_config import log_event, log_exception

# Log events
log_event("scrape_started", scraper=self.NAME)
log_event("document_downloaded", url=url, size_bytes=file_size)
log_event("scrape_completed", documents=count)

# Log exceptions with context
try:
    download_file(url)
except Exception as e:
    log_exception("download_failed", e, url=url, scraper=self.NAME)
```

### Error Handling

Use custom exceptions from `app.utils.errors`:

```python
from app.utils.errors import (
    ScraperError,
    ContentExtractionError,
    DownloadError
)

try:
    content = extract_content(html)
except ValueError as e:
    raise ContentExtractionError(f"Failed to parse: {e}")
```

### Incremental Scraping

Always use state tracking to avoid re-scraping:

```python
def scrape(self):
    urls = self.get_document_urls()
    
    for url in urls:
        # Skip if already processed
        if self.should_exclude_url(url):
            self.log_event("skipped_duplicate", url=url)
            continue
        
        # Process new document
        filepath = self.download_file(url)
        self.mark_url_processed(url)
```

### Respect Rate Limits

Add delays between requests:

```python
import time

REQUEST_DELAY = 1.0  # seconds

def scrape(self):
    for url in urls:
        self.download_file(url)
        time.sleep(REQUEST_DELAY)  # Be polite
```

---

## Debugging Scrapers

### Local Execution

```bash
# Dry run with debug logging
LOG_LEVEL=DEBUG python scripts/run_scraper.py \
  --scraper my-scraper \
  --dry-run \
  --max-pages 1
```

### View Logs

```bash
# Follow live logs
tail -f data/logs/scraper.log

# Filter by scraper
grep "my-scraper" data/logs/scraper.log

# Filter by level
grep "ERROR" data/logs/scraper.log
```

### Chrome VNC Debugging

Access Selenium browser at http://localhost:7900 (password: `secret`)

**Use cases:**
- See what the browser sees
- Debug JavaScript issues
- Verify selectors work
- Watch scraper in action

### Inspect State Files

```bash
# Pretty print state
cat data/state/my-scraper_state.json | jq .

# Check specific fields
cat data/state/my-scraper_state.json | jq '.statistics'
cat data/state/my-scraper_state.json | jq '.processed_urls | length'
```

### Python Debugger

Add breakpoints with `pdb`:

```python
def scrape(self):
    urls = self._get_document_urls()
    
    import pdb; pdb.set_trace()  # Breakpoint here
    
    for url in urls:
        # ... debug from here ...
```

---

## Testing

### Unit Tests

**Location:** `tests/unit/`

**Run unit tests:**
```bash
pytest tests/unit/ -v
```

**Example unit test:**
```python
def test_scraper_handles_404(scraper, mock_requests):
    """Test scraper handles 404 gracefully."""
    mock_requests.get.return_value.status_code = 404
    
    result = scraper.scrape()
    
    assert result.status == "failed"
    assert "404" in result.error
```

### Integration Tests

**Location:** `tests/integration/`

**Run integration tests:**
```bash
pytest tests/integration/ -v
```

**Example integration test:**
```python
def test_scraper_full_workflow(scraper, tmp_path):
    """Test complete scrape → metadata → state workflow."""
    scraper.download_dir = tmp_path / "scraped"
    scraper.metadata_dir = tmp_path / "metadata"
    
    result = scraper.scrape()
    
    assert result.status == "completed"
    assert len(list(scraper.download_dir.glob("*.pdf"))) > 0
    assert len(list(scraper.metadata_dir.glob("*.json"))) > 0
```

### Test Fixtures

**Location:** `tests/conftest.py`

**Common fixtures:**
- `mock_container` - Mocked service container
- `temp_dirs` - Temporary directories
- `mock_requests` - Mocked HTTP requests
- `sample_html` - Sample HTML for parsing

### Coverage

```bash
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Code Standards

### Follow Existing Patterns

See `app/scrapers/aemo_scraper.py` for reference implementation.

### Use Type Hints

```python
from typing import Optional
from pathlib import Path

def download_file(self, url: str) -> Optional[Path]:
    """Download file from URL."""
    pass
```

### Document Public Methods

```python
def scrape(self) -> ScraperResult:
    """
    Main scraping method.
    
    Returns:
        ScraperResult with status and statistics
    
    Raises:
        ScraperError: If scraping fails critically
    """
    pass
```

### Handle Errors Gracefully

```python
try:
    filepath = download_file(url)
except DownloadError as e:
    log_exception("download_failed", e, url=url)
    continue  # Skip this document, process others
```

### Log Important Events

See [LOGGING_AND_ERROR_STANDARDS.md](LOGGING_AND_ERROR_STANDARDS.md)

---

## Service Container Usage

### Accessing Services

```python
from app.container import container

# RAGFlow client
ragflow = container.ragflow_client
documents = ragflow.list_documents(dataset_id)

# State tracker
state = container.state_tracker("my-scraper")
status = state.get_status()

# Settings manager
settings = container.settings_manager
config = settings.get_settings()

# FlareSolverr client
flaresolverr = container.flaresolverr_client
response = flaresolverr.solve(url)
```

### Lazy Loading

Services are initialized on first access:

```python
# No initialization yet
container = container

# Initializes RAGFlowClient on first access
client = container.ragflow_client
```

### See Also

- [SERVICE_CONTAINER_MIGRATION.md](SERVICE_CONTAINER_MIGRATION.md) - Container patterns
- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Error handling guide
- [METADATA_SCHEMA.md](METADATA_SCHEMA.md) - Metadata structure
- [EXAMPLE_SCRAPER_WALKTHROUGH.md](EXAMPLE_SCRAPER_WALKTHROUGH.md) - Detailed example

---

## Next Steps

1. Read [EXAMPLE_SCRAPER_WALKTHROUGH.md](EXAMPLE_SCRAPER_WALKTHROUGH.md) for detailed AEMO scraper explanation
2. Review [METADATA_SCHEMA.md](METADATA_SCHEMA.md) for metadata requirements
3. Check [LOGGING_AND_ERROR_STANDARDS.md](LOGGING_AND_ERROR_STANDARDS.md) for logging patterns
4. See [CONFIG_AND_SERVICES.md](CONFIG_AND_SERVICES.md) for architecture overview
