# Configuration and Service Architecture

This document describes the configuration management system and service layer architecture of the PDF Scraper project, including patterns for dependency management and extensibility.

---

## 1. Configuration Sources and Precedence

The application uses a **layered configuration approach** with clear separation of concerns:

### Configuration Layers (in precedence order)

```
┌────────────────────────────────────────────┐
│ 1. Environment Variables (.env)            │ Highest Priority
│    └─ Deployment-level secrets & URLs      │ (Production-critical)
├────────────────────────────────────────────┤
│ 2. Per-Scraper JSON Configs                │
│    └─ Scraper-specific overrides           │ (Optional customization)
├────────────────────────────────────────────┤
│ 3. Runtime Settings (settings.json)        │ 
│    └─ UI-modifiable settings               │ (Non-persistent tuning)
├────────────────────────────────────────────┤
│ 4. Default Values                          │
│    └─ Hardcoded fallbacks in code          │ Lowest Priority
└────────────────────────────────────────────┘
```

### Configuration Sources in Detail

#### 1. Environment Variables (`.env`) – Single Source of Truth

**Responsibility:** Deployment-level secrets and critical URLs

**Examples:**
```bash
# Secrets (NEVER in code or version control)
RAGFLOW_API_KEY=sk-xxx-yyy-zzz
GUARDIAN_API_KEY=abc123def456
BASIC_AUTH_PASSWORD=secure_password

# Service URLs (environment-dependent)
RAGFLOW_API_URL=http://localhost:9380
FLARESOLVERR_URL=http://localhost:8191
SELENIUM_REMOTE_URL=http://chrome:4444/wd/hub

# Feature flags
RAGFLOW_PUSH_METADATA=true
BASIC_AUTH_ENABLED=true
FLASK_DEBUG=0
```

**Storage:** Project root as `.env` (untracked in git)

**Access in Code:** Via `Config` class in `app/config.py`

```python
from app.config import Config

api_key = Config.RAGFLOW_API_KEY  # ← Read from .env
url = Config.RAGFLOW_API_URL
```

**Best Practices:**
- Never commit `.env` to version control
- Use `.env.example` (with dummy values) as a reference
- Rotate secrets regularly in production
- Use different `.env` files per environment (`dev`, `staging`, `prod`)

---

#### 2. Per-Scraper Configuration JSONs

**Responsibility:** Scraper-specific overrides and advanced settings

**Location:** `config/scrapers/{scraper_name}.json` (optional)

**Example:** `config/scrapers/aemo.json`
```json
{
  "cloudflare_enabled": true,
  "max_pages": 10,
  "url_patterns": ["statement", "report"],
  "exclude_patterns": ["draft", "superseded"],
  "ragflow": {
    "dataset_id": "dataset-aemo-official",
    "embedding_model": "custom-energy-model",
    "chunk_method": "paper"
  }
}
```

**Purpose:**
- Override SettingsManager defaults for specific scrapers
- Store scraper-specific constants (URL patterns, page limits)
- Enable advanced RAGFlow configuration (custom embedding models)

**Access in Code:**
```python
from app.services.settings_manager import get_settings

settings = get_settings()
scraper_config = settings.get_scraper_config("aemo")
# Merged result: global defaults + aemo.json overrides
```

---

#### 3. Runtime Settings (`config/settings.json`)

**Responsibility:** UI-modifiable application settings

**Location:** `config/settings.json` (auto-created on first run)

**Example Structure:**
```json
{
  "flaresolverr": {
    "enabled": false,
    "timeout": 60,
    "max_timeout": 120
  },
  "ragflow": {
    "default_dataset_id": "general-documents",
    "auto_upload": true,
    "auto_create_dataset": false,
    "default_embedding_model": "default",
    "default_chunk_method": "paper",
    "wait_for_parsing": true,
    "parser_config": {
      "chunk_token_num": 128,
      "layout_recognize": "DeepDOC"
    }
  },
  "scraping": {
    "default_request_delay": 2.0,
    "default_timeout": 60,
    "default_retry_attempts": 3,
    "use_flaresolverr_by_default": false,
    "max_concurrent_downloads": 3
  },
  "scheduler": {
    "enabled": false,
    "run_on_startup": false
  }
}
```

**Features:**
- Lazy-loaded by `SettingsManager` singleton
- JSON schema validation on write (see `SETTINGS_SCHEMA` in `settings_manager.py`)
- UI accessible via Flask routes
- Runtime-modifiable without application restart

**Access in Code:**
```python
from app.services.settings_manager import get_settings

settings = get_settings()
flaresolverr_enabled = settings.flaresolverr_enabled
timeout = settings.ragflow_timeout
```

---

#### 4. Default Hardcoded Values

**Responsibility:** Fallback values when no configuration is provided

**Examples:**
- Flask `DEBUG=False` (unless `FLASK_DEBUG=1` in env)
- `REQUEST_TIMEOUT=60` seconds (unless `REQUEST_TIMEOUT` in env)
- `RETRY_ATTEMPTS=3` (unless `RETRY_ATTEMPTS` in env)

**Access in Code:**
```python
from app.config import Config

timeout = Config.REQUEST_TIMEOUT  # Defaults to 60 if not set
```

---

### Configuration Validation

The system validates configuration at **two points**:

1. **Load Time** (e.g., application startup)
   - Env vars are loaded by `app/config.py`
   - JSON schemas validated by `SettingsManager`
   - Custom validation in `app/utils/config_validation.py`

2. **Use Time** (when accessed by scrapers/services)
   - Services check required fields exist
   - Raise meaningful errors if config is missing

**Example Validation:**
```python
from app.utils.config_validation import validate_ragflow_config

# This raises ValidationError with descriptive message
validate_ragflow_config(Config.RAGFLOW_API_URL, Config.RAGFLOW_API_KEY)
```

---

## 2. Service Layer Architecture

The service layer provides **centralized access to external dependencies** (RAGFlow, FlareSolverr, state tracking, settings).

### Current Service Structure

```
app/services/
├── settings_manager.py      # Runtime settings (UI-modifiable)
├── state_tracker.py         # State persistence (processed URLs, statistics)
├── ragflow_client.py        # RAGFlow API integration
├── flaresolverr_client.py   # Cloudflare bypass proxy
└── [future] container.py    # DI container (proposed)
```

### Service Responsibilities

#### SettingsManager – Configuration Access
**Purpose:** Provide singleton access to runtime settings

**Instantiation Pattern:**
```python
from app.services.settings_manager import get_settings

settings = get_settings()  # Always returns same instance
```

**Key Features:**
- Singleton pattern (one instance per application)
- JSON file persistence (`config/settings.json`)
- JSON schema validation
- Lazy-loading (settings loaded on first access)
- Property-based access (type-safe, IDE autocomplete)

**Typical Usage:**
```python
# Check if feature is enabled
if settings.flaresolverr_enabled:
    # Use FlareSolverr proxy
    
# Access RAGFlow settings
dataset_id = settings.ragflow_default_dataset_id

# Update at runtime
settings.flaresolverr_enabled = True
settings.save()  # Persist to file
```

---

#### StateTracker – URL and Statistics Tracking
**Purpose:** Track which URLs have been processed to prevent duplicates

**Instantiation Pattern:**
```python
from app.services.state_tracker import StateTracker

tracker = StateTracker("aemo")  # Per-scraper instance
```

**Key Features:**
- Per-scraper state files (`data/state/{scraper_name}_state.json`)
- Track processed URLs, statistics, and timestamps
- Prevent duplicate downloads
- Persistent storage (survives application restart)

**Typical Usage:**
```python
# Check if URL already processed
if tracker.is_processed(url):
    logger.info("URL already downloaded, skipping")
    continue

# Process URL...
document_info = scrape_document(url)

# Mark as processed
tracker.mark_processed(
    url=url,
    metadata={"filename": "report.pdf", "size": 1024000},
    status="downloaded"  # or "skipped", "failed"
)
tracker.save()  # Persist to file
```

**State File Structure:**
```json
{
  "scraper_name": "aemo",
  "created_at": "2026-01-06T10:30:00.000000",
  "last_updated": "2026-01-06T11:45:30.000000",
  "processed_urls": {
    "https://www.aemo.com.au/.../report.pdf": {
      "processed_at": "2026-01-06T11:30:00.000000",
      "status": "downloaded",
      "filename": "aemo_report_2025.pdf",
      "size": 1024000
    }
  },
  "statistics": {
    "total_processed": 42,
    "total_downloaded": 40,
    "total_skipped": 1,
    "total_failed": 1
  }
}
```

---

#### RAGFlowClient – Document Ingestion
**Purpose:** Upload documents and metadata to RAGFlow for RAG indexing

**Instantiation Pattern:**
```python
from app.services.ragflow_client import RAGFlowClient

client = RAGFlowClient(
    api_url=Config.RAGFLOW_API_URL,
    api_key=Config.RAGFLOW_API_KEY
)
```

**Key Features:**
- API key authentication
- Document upload (PDF, Markdown)
- Metadata attachment
- Parsing status polling
- Deduplication hash calculation
- Error handling with retries

**Typical Usage:**
```python
# Upload a document with metadata
result = client.upload_document(
    dataset_id="dataset-123",
    filepath="report.pdf",
    metadata={
        "title": "AEMO 2025 Annual Report",
        "tags": ["aemo", "annual-report"],
        "publication_date": "2025-01-01",
        "organization": "AEMO"
    },
    chunk_method="paper"  # For academic PDFs
)

# Check parsing status
if result.get("doc_id"):
    status = client.poll_parsing_status(
        dataset_id="dataset-123",
        doc_id=result["doc_id"],
        timeout=30  # seconds
    )
    logger.info(f"Document parsed: {status}")
```

---

#### FlareSolverrClient – Cloudflare Bypass
**Purpose:** Bypass Cloudflare and other anti-bot protections

**Instantiation Pattern:**
```python
from app.services.flaresolverr_client import FlareSolverrClient

proxy = FlareSolverrClient(
    url=Config.FLARESOLVERR_URL,
    timeout=60,
    max_timeout=120
)
```

**Key Features:**
- Challenge solving (Cloudflare, DDoS-Guard)
- Session caching (reuse cookies)
- User-agent rotation
- Metrics tracking (success rate, timeouts)
- Optional (graceful fallback if disabled)

**Typical Usage:**
```python
if proxy.is_enabled:
    # Solve Cloudflare challenge
    result = proxy.solve_challenge(
        url="https://example.com/protected-page",
        max_timeout=120
    )
    
    if result.success:
        html = result.html
        cookies = result.cookies
        user_agent = result.user_agent
    else:
        logger.error(f"Challenge failed: {result.error}")
        # Fallback to direct Selenium?
else:
    # Fall back to direct Selenium
    html = driver.page_source
```

---

## 3. Dependency Injection Pattern (Proposed)

### Motivation

Currently, services are created **ad-hoc** throughout the codebase:

```python
# ❌ Current approach (scattered creation)
# In scraper A:
from app.services.ragflow_client import RAGFlowClient
client1 = RAGFlowClient(url, key)

# In scraper B:
from app.services.ragflow_client import RAGFlowClient
client2 = RAGFlowClient(url, key)

# In web/routes.py:
from app.services.ragflow_client import RAGFlowClient
client3 = RAGFlowClient(url, key)
# → Multiple instances, inconsistent initialization, hard to mock for tests
```

### Proposed Solution: ServiceContainer

A **centralized container** manages service creation and lifecycle:

```python
# ✅ Proposed approach (centralized DI)
from app.services.container import get_container

container = get_container()
client = container.ragflow_client  # Lazy-loaded, reused singleton
```

### Implementation Example

**File:** `app/services/container.py` (NEW)

```python
"""
Service container for dependency injection.

Manages creation and lifecycle of all application services.
Provides lazy-loading and singleton pattern for efficiency.
"""

from __future__ import annotations

from typing import Optional
from app.config import Config
from app.services.settings_manager import get_settings, SettingsManager
from app.services.ragflow_client import RAGFlowClient
from app.services.flaresolverr_client import FlareSolverrClient
from app.services.state_tracker import StateTracker
from app.utils import get_logger


class ServiceContainer:
    """
    Dependency injection container for application services.
    
    Provides centralized access to all external services (RAGFlow, FlareSolverr, etc.)
    with consistent initialization and error handling.
    
    Usage:
        container = get_container()
        client = container.ragflow_client
        tracker = container.state_tracker("aemo")
    """
    
    _instance: Optional[ServiceContainer] = None
    
    def __init__(self):
        """Initialize service container (singleton)."""
        self.logger = get_logger("container")
        
        # Service instances (lazy-loaded)
        self._settings: Optional[SettingsManager] = None
        self._ragflow_client: Optional[RAGFlowClient] = None
        self._flaresolverr_client: Optional[FlareSolverrClient] = None
        
        # State trackers (cached by scraper name)
        self._state_trackers: dict[str, StateTracker] = {}
    
    def __new__(cls) -> ServiceContainer:
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__dict__['_instance'] = None
            cls._instance.__dict__['_settings'] = None
            cls._instance.__dict__['_ragflow_client'] = None
            cls._instance.__dict__['_flaresolverr_client'] = None
            cls._instance.__dict__['_state_trackers'] = {}
        return cls._instance
    
    @property
    def settings(self) -> SettingsManager:
        """
        Get settings manager (lazy-loaded singleton).
        
        Returns:
            SettingsManager instance
        """
        if self._settings is None:
            self._settings = get_settings()
            self.logger.debug("Initialized SettingsManager")
        return self._settings
    
    @property
    def ragflow_client(self) -> RAGFlowClient:
        """
        Get RAGFlow client (lazy-loaded singleton).
        
        Raises:
            ValueError: If RAGFlow configuration is missing
        
        Returns:
            RAGFlowClient instance
        """
        if self._ragflow_client is None:
            if not Config.RAGFLOW_API_URL or not Config.RAGFLOW_API_KEY:
                raise ValueError(
                    "RAGFlow configuration missing. Set RAGFLOW_API_URL and "
                    "RAGFLOW_API_KEY environment variables."
                )
            self._ragflow_client = RAGFlowClient(
                api_url=Config.RAGFLOW_API_URL,
                api_key=Config.RAGFLOW_API_KEY,
                username=Config.RAGFLOW_USERNAME,
                password=Config.RAGFLOW_PASSWORD,
            )
            self.logger.debug("Initialized RAGFlowClient")
        return self._ragflow_client
    
    @property
    def flaresolverr_client(self) -> FlareSolverrClient:
        """
        Get FlareSolverr client (lazy-loaded singleton).
        
        Note: FlareSolverr is optional. Check is_configured/is_enabled before use.
        
        Returns:
            FlareSolverrClient instance
        """
        if self._flaresolverr_client is None:
            settings = self.settings
            self._flaresolverr_client = FlareSolverrClient(
                url=Config.FLARESOLVERR_URL,
                timeout=settings.flaresolverr_timeout,
                max_timeout=settings.flaresolverr_max_timeout,
            )
            self.logger.debug("Initialized FlareSolverrClient")
        return self._flaresolverr_client
    
    def state_tracker(self, scraper_name: str) -> StateTracker:
        """
        Get or create state tracker for a scraper (factory pattern).
        
        Args:
            scraper_name: Name of the scraper (e.g., "aemo")
        
        Returns:
            StateTracker instance (cached per scraper)
        """
        if scraper_name not in self._state_trackers:
            tracker = StateTracker(scraper_name)
            self._state_trackers[scraper_name] = tracker
            self.logger.debug(f"Initialized StateTracker for {scraper_name}")
        return self._state_trackers[scraper_name]
    
    def reset(self):
        """
        Reset all cached service instances.
        
        Useful for testing and debugging. Forces re-initialization on next access.
        """
        self._settings = None
        self._ragflow_client = None
        self._flaresolverr_client = None
        self._state_trackers = {}
        self.logger.debug("Service container reset")


# Module-level singleton accessor
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """
    Get the global service container instance.
    
    Returns:
        ServiceContainer singleton
    """
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container():
    """Reset the global service container (for testing)."""
    global _container
    if _container:
        _container.reset()
    _container = None
```

### Benefits of Dependency Injection

| Aspect | Without DI | With ServiceContainer |
|--------|-----------|----------------------|
| **Service Creation** | Scattered throughout code | Centralized in container |
| **Instantiation** | Multiple instances | Single instance (lazy-loaded) |
| **Testing** | Hard to mock services | Easy to mock/replace |
| **Configuration** | Passed to each service | Accessed from container |
| **Lifecycle** | Implicit, unclear | Explicit and managed |
| **Error Handling** | Per-service validation | Centralized validation |

### Migration Path

1. **Phase 1** (Current): Create `container.py` as optional alternative
   - Services still created ad-hoc elsewhere
   - New code can use container
   - No breaking changes

2. **Phase 2**: Migrate scrapers to use container
   ```python
   # Old way (deprecated)
   from app.services.ragflow_client import RAGFlowClient
   client = RAGFlowClient(url, key)
   
   # New way
   from app.services.container import get_container
   client = get_container().ragflow_client
   ```

3. **Phase 3**: Migrate web routes to use container

4. **Phase 4**: Remove ad-hoc service creation

---

## 4. How Configuration Flows Through the Application

### Typical Request Flow

```
1. Application Startup
   ├─ Load .env → Config class (environment variables)
   ├─ Initialize SettingsManager (loads config/settings.json)
   ├─ Create ServiceContainer (lazy-loads services as needed)
   └─ Server ready

2. HTTP Request (e.g., Start Scraper)
   ├─ Flask route receives request with scraper name
   ├─ Route gets ServiceContainer
   ├─ Container provides StateTracker("aemo")
   ├─ Container provides RAGFlowClient (if configured)
   ├─ Scraper runs, uses StateTracker and RAGFlowClient
   └─ Response sent back to client

3. Configuration Update (e.g., Toggle FlareSolverr)
   ├─ User submits form via web UI
   ├─ Route validates input
   ├─ SettingsManager.update() called
   ├─ config/settings.json updated
   ├─ Services notified of change (or pick up on next request)
   └─ Next request uses new settings
```

### Scraper-to-Service Interaction

```python
# In a scraper's run() method:

def run(self):
    from app.services.container import get_container
    
    container = get_container()
    settings = container.settings
    state = container.state_tracker(self.name)
    ragflow = container.ragflow_client  # May raise if not configured
    
    for url in self.get_urls():
        # Check if already processed
        if state.is_processed(url):
            continue
        
        # Use FlareSolverr if enabled
        if settings.flaresolverr_enabled:
            from_flaresolverr = container.flaresolverr_client
            # ... use proxy
        
        # Download document
        document = self.download(url)
        
        # Upload to RAGFlow
        if settings.ragflow_auto_upload:
            result = ragflow.upload_document(
                dataset_id=settings.ragflow_default_dataset_id,
                filepath=document.filepath,
                metadata=document.metadata
            )
        
        # Mark as processed
        state.mark_processed(url, metadata={...}, status="downloaded")
        state.save()
```

---

## 5. Configuration Best Practices

### For Configuration Developers

1. **Use `.env` for secrets**
   - API keys, passwords, URLs
   - Never hardcode, never commit

2. **Use `config/settings.json` for tuning**
   - Feature flags (enable/disable FlareSolverr)
   - Timeouts, retry counts
   - UI-modifiable values

3. **Use per-scraper JSONs for specialization**
   - Scraper-specific URL patterns
   - Custom chunk methods for RAGFlow
   - Max pages or rate limits

### For Scraper Developers

1. **Always inject dependencies**
   ```python
   from app.services.container import get_container
   container = get_container()
   ```

2. **Handle optional services gracefully**
   ```python
   try:
       ragflow = container.ragflow_client
       # Use RAGFlow
   except ValueError:
       logger.warning("RAGFlow not configured, skipping upload")
   ```

3. **Check if optional features are enabled**
   ```python
   if container.settings.flaresolverr_enabled:
       proxy = container.flaresolverr_client
   else:
       # Fallback to direct Selenium
   ```

### For Testing

```python
# tests/conftest.py

import pytest
from app.services.container import reset_container, get_container

@pytest.fixture(autouse=True)
def clean_services():
    """Reset service container before each test."""
    reset_container()
    yield
    reset_container()

@pytest.fixture
def mock_ragflow():
    """Provide mocked RAGFlow client."""
    from unittest.mock import Mock, patch
    
    mock = Mock()
    with patch.object(
        get_container(), 
        '_ragflow_client', 
        mock
    ):
        yield mock
```

---

## Summary

- **Configuration** is layered: `.env` (secrets) → per-scraper JSONs → `settings.json` → hardcoded defaults
- **Services** are centralized: RAGFlowClient, FlareSolverrClient, StateTracker, SettingsManager
- **Dependency Injection** (via ServiceContainer) improves testability and maintainability
- **Single source of truth** for each configuration level prevents inconsistencies
