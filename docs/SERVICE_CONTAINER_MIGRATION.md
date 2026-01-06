# Service Container Migration Guide

This document provides a step-by-step guide for migrating the application from scattered service instantiation to a centralized **ServiceContainer** with dependency injection.

---

## 1. Executive Summary

### Current State

Services are created **ad-hoc** throughout the codebase:
- `RAGFlowClient` instantiated in multiple scrapers
- `FlareSolverrClient` instantiated separately in each component
- `StateTracker` created per-scraper without caching
- Testing requires mocking scattered instances

### Target State

Services managed by **ServiceContainer**:
- Single point of creation (container)
- Lazy-loaded, cached instances
- Testable via mocking the container
- Consistent error handling
- Clear dependency graph

### Migration Timeline

- **Phase 1** (Week 1): Create container, add tests
- **Phase 2** (Week 2): Migrate scrapers
- **Phase 3** (Week 3): Migrate web routes
- **Phase 4** (Week 4): Remove ad-hoc creation, cleanup

---

## 2. Current Service Instantiation Patterns

### RAGFlowClient

**Current Pattern (Scattered):**
```python
# In scrapers/aemc_scraper.py
from app.services.ragflow_client import RAGFlowClient

class AEMCScraper:
    def __init__(self):
        if Config.RAGFLOW_API_KEY:
            self.ragflow = RAGFlowClient(
                api_url=Config.RAGFLOW_API_URL,
                api_key=Config.RAGFLOW_API_KEY,
                username=Config.RAGFLOW_USERNAME,
                password=Config.RAGFLOW_PASSWORD,
            )

# In web/routes.py (different instantiation)
from app.services.ragflow_client import RAGFlowClient

@app.route("/api/datasets")
def list_datasets():
    client = RAGFlowClient(
        Config.RAGFLOW_API_URL,
        Config.RAGFLOW_API_KEY,
    )
    return client.list_datasets()
```

**Issues:**
- Multiple instances created
- Inconsistent initialization
- Duplicate error handling code
- Hard to mock in tests

---

### FlareSolverrClient

**Current Pattern:**
```python
# In scrapers/base_scraper.py
from app.services.flaresolverr_client import FlareSolverrClient

class BaseScraper:
    def __init__(self):
        self.flaresolverr = FlareSolverrClient()  # Uses defaults from Config
```

**Issues:**
- Created per-scraper instance
- Settings not passed correctly
- No caching mechanism

---

### StateTracker

**Current Pattern:**
```python
# In scrapers/base_scraper.py
from app.services.state_tracker import StateTracker

class BaseScraper:
    def __init__(self, name):
        self.state = StateTracker(name)  # New instance each time
```

**Issues:**
- State loaded from file multiple times
- No caching across requests
- Inefficient file I/O

---

## 3. Phase 1: Create ServiceContainer

### Step 1: Create Container Class

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
        """Get settings manager (lazy-loaded singleton)."""
        if self._settings is None:
            self._settings = get_settings()
            self.logger.debug("Initialized SettingsManager")
        return self._settings
    
    @property
    def ragflow_client(self) -> RAGFlowClient:
        """Get RAGFlow client (lazy-loaded singleton)."""
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
        """Get FlareSolverr client (lazy-loaded singleton)."""
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
        """Get or create state tracker for a scraper (factory pattern)."""
        if scraper_name not in self._state_trackers:
            tracker = StateTracker(scraper_name)
            self._state_trackers[scraper_name] = tracker
            self.logger.debug(f"Initialized StateTracker for {scraper_name}")
        return self._state_trackers[scraper_name]
    
    def reset(self):
        """Reset all cached service instances (for testing)."""
        self._settings = None
        self._ragflow_client = None
        self._flaresolverr_client = None
        self._state_trackers = {}
        self.logger.debug("Service container reset")


# Module-level singleton accessor
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """Get the global service container instance."""
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

### Step 2: Create Container Tests

**File:** `tests/unit/test_service_container.py` (NEW)

```python
"""
Tests for the ServiceContainer dependency injection container.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.services.container import ServiceContainer, get_container, reset_container
from app.services.settings_manager import SettingsManager
from app.services.ragflow_client import RAGFlowClient
from app.services.flaresolverr_client import FlareSolverrClient
from app.services.state_tracker import StateTracker


class TestServiceContainer:
    """Test ServiceContainer functionality."""
    
    def teardown_method(self):
        """Reset container after each test."""
        reset_container()
    
    def test_singleton_pattern(self):
        """Container should return same instance."""
        container1 = get_container()
        container2 = get_container()
        assert container1 is container2
    
    def test_settings_lazy_loaded(self):
        """Settings should be lazy-loaded on first access."""
        container = get_container()
        assert container._settings is None
        
        settings = container.settings
        assert settings is not None
        assert container._settings is not None
        
        # Second access should return cached instance
        settings2 = container.settings
        assert settings is settings2
    
    def test_ragflow_client_lazy_loaded(self):
        """RAGFlow client should be lazy-loaded on first access."""
        container = get_container()
        assert container._ragflow_client is None
        
        with patch('app.services.container.Config') as mock_config:
            mock_config.RAGFLOW_API_URL = "http://localhost:9380"
            mock_config.RAGFLOW_API_KEY = "test-key"
            mock_config.RAGFLOW_USERNAME = ""
            mock_config.RAGFLOW_PASSWORD = ""
            
            with patch('app.services.container.RAGFlowClient') as mock_client:
                client = container.ragflow_client
                assert mock_client.called
    
    def test_ragflow_client_requires_config(self):
        """RAGFlow client should raise if config missing."""
        container = get_container()
        
        with patch('app.services.container.Config') as mock_config:
            mock_config.RAGFLOW_API_URL = ""
            mock_config.RAGFLOW_API_KEY = ""
            
            with pytest.raises(ValueError, match="RAGFlow configuration missing"):
                _ = container.ragflow_client
    
    def test_state_tracker_factory(self):
        """State tracker should be created per scraper (factory pattern)."""
        container = get_container()
        
        tracker1 = container.state_tracker("aemo")
        tracker2 = container.state_tracker("aemo")
        tracker3 = container.state_tracker("aer")
        
        # Same scraper returns cached instance
        assert tracker1 is tracker2
        
        # Different scraper returns new instance
        assert tracker1 is not tracker3
        assert tracker1.scraper_name == "aemo"
        assert tracker3.scraper_name == "aer"
    
    def test_reset_clears_all_services(self):
        """Reset should clear all cached services."""
        container = get_container()
        
        # Access services to populate cache
        with patch('app.services.container.Config') as mock_config:
            mock_config.RAGFLOW_API_URL = "http://localhost:9380"
            mock_config.RAGFLOW_API_KEY = "test-key"
            mock_config.RAGFLOW_USERNAME = ""
            mock_config.RAGFLOW_PASSWORD = ""
            mock_config.FLARESOLVERR_URL = "http://localhost:8191"
            
            _ = container.settings
            _ = container.state_tracker("aemo")
            
            # Verify cache populated
            assert container._settings is not None
            assert len(container._state_trackers) > 0
        
        # Reset
        container.reset()
        
        # Verify cache cleared
        assert container._settings is None
        assert container._ragflow_client is None
        assert container._flaresolverr_client is None
        assert len(container._state_trackers) == 0


class TestContainerIntegration:
    """Integration tests with actual services."""
    
    def teardown_method(self):
        """Reset container after each test."""
        reset_container()
    
    def test_get_multiple_services(self):
        """Container should provide multiple services."""
        container = get_container()
        
        # Get multiple services
        settings = container.settings
        tracker = container.state_tracker("test_scraper")
        
        # Both should be valid
        assert isinstance(settings, SettingsManager)
        assert isinstance(tracker, StateTracker)
        assert tracker.scraper_name == "test_scraper"
```

### Step 3: Update `__init__.py` to Export Container

**File:** `app/services/__init__.py`

```python
"""Services module."""

from app.services.container import get_container, reset_container

__all__ = [
    "get_container",
    "reset_container",
]
```

---

## 4. Phase 2: Migrate Scrapers to Use Container

### Before Migration

```python
# scrapers/aemo_scraper.py (BEFORE)
from app.services.ragflow_client import RAGFlowClient
from app.services.state_tracker import StateTracker
from app.config import Config

class AEMOScraper(BaseScraper):
    def __init__(self):
        super().__init__("aemo")
        
        if Config.RAGFLOW_API_KEY:
            self.ragflow = RAGFlowClient(
                api_url=Config.RAGFLOW_API_URL,
                api_key=Config.RAGFLOW_API_KEY,
            )
        else:
            self.ragflow = None
        
        self.state = StateTracker("aemo")
```

### After Migration

```python
# scrapers/aemo_scraper.py (AFTER)
from app.services.container import get_container

class AEMOScraper(BaseScraper):
    def __init__(self):
        super().__init__("aemo")
        
        self.container = get_container()
        self.settings = self.container.settings
        self.state = self.container.state_tracker("aemo")
    
    def run(self):
        """Run the scraper."""
        try:
            # Try to use RAGFlow if configured
            ragflow = self.container.ragflow_client
        except ValueError:
            self.logger.info("RAGFlow not configured, will skip uploads")
            ragflow = None
        
        # Use FlareSolverr if enabled
        if self.settings.flaresolverr_enabled:
            proxy = self.container.flaresolverr_client
        else:
            proxy = None
        
        # ... rest of scraper logic
```

### Migration Checklist

- [ ] Update `base_scraper.py` to use container
- [ ] Update `aemo_scraper.py`
- [ ] Update `aer_scraper.py`
- [ ] Update `aemc_scraper.py`
- [ ] Update `ena_scraper.py`
- [ ] Update `eca_scraper.py`
- [ ] Update `aemo_scraper.py`
- [ ] Update all article scrapers
- [ ] Add tests for each migrated scraper

---

## 5. Phase 3: Migrate Web Routes to Use Container

### Before Migration

```python
# web/routes.py (BEFORE)
from app.services.ragflow_client import RAGFlowClient
from app.config import Config

@app.route("/api/datasets")
def list_datasets():
    if not Config.RAGFLOW_API_KEY:
        return {"error": "RAGFlow not configured"}, 400
    
    client = RAGFlowClient(
        Config.RAGFLOW_API_URL,
        Config.RAGFLOW_API_KEY,
    )
    datasets = client.list_datasets()
    return {"datasets": datasets}
```

### After Migration

```python
# web/routes.py (AFTER)
from app.services.container import get_container

@app.route("/api/datasets")
def list_datasets():
    try:
        container = get_container()
        client = container.ragflow_client
        datasets = client.list_datasets()
        return {"datasets": datasets}
    except ValueError as e:
        return {"error": str(e)}, 400
```

### Migration Checklist

- [ ] Update all routes in `web/routes.py` that use RAGFlowClient
- [ ] Update all routes that use FlareSolverrClient
- [ ] Update all routes that use SettingsManager
- [ ] Update all routes that need StateTracker
- [ ] Add tests for each migrated route

---

## 6. Testing Strategy

### Unit Tests (Mock the Container)

```python
# tests/unit/test_scrapers_with_di.py
import pytest
from unittest.mock import Mock, patch, MagicMock

from scrapers.aemo_scraper import AEMOScraper
from app.services.container import reset_container


@pytest.fixture
def mock_container():
    """Provide a mocked container."""
    from app.services.container import get_container, reset_container
    
    reset_container()
    
    with patch('scrapers.aemo_scraper.get_container') as mock_get:
        mock_container = MagicMock()
        mock_get.return_value = mock_container
        yield mock_container
    
    reset_container()


def test_scraper_with_ragflow(mock_container):
    """Test scraper when RAGFlow is configured."""
    # Setup mock services
    mock_ragflow = Mock()
    mock_ragflow.upload_document.return_value = {"doc_id": "123"}
    mock_container.ragflow_client = mock_ragflow
    
    mock_settings = Mock()
    mock_settings.flaresolverr_enabled = False
    mock_container.settings = mock_settings
    
    mock_state = Mock()
    mock_container.state_tracker.return_value = mock_state
    
    # Run scraper
    scraper = AEMOScraper()
    results = scraper.run()
    
    # Verify container was used
    mock_container.ragflow_client
    assert mock_ragflow.upload_document.called


def test_scraper_without_ragflow(mock_container):
    """Test scraper when RAGFlow is not configured."""
    # Setup mock to raise error
    mock_container.ragflow_client = Mock(
        side_effect=ValueError("RAGFlow not configured")
    )
    
    # Run scraper - should handle error gracefully
    scraper = AEMOScraper()
    results = scraper.run()  # Should not raise
```

### Integration Tests (Use Real Container)

```python
# tests/integration/test_container_integration.py
import pytest
from app.services.container import get_container, reset_container


@pytest.fixture(autouse=True)
def clean_container():
    """Reset container before and after each test."""
    reset_container()
    yield
    reset_container()


def test_container_provides_all_services():
    """Container should provide all required services."""
    container = get_container()
    
    # All services should be accessible
    assert container.settings is not None
    assert container.state_tracker("test") is not None
    
    # RAGFlow client requires config, so test separately
    # assert container.ragflow_client is not None  # Only if configured
```

---

## 7. Phase 4: Cleanup and Remove Ad-Hoc Creation

Once all code is migrated to use the container:

### Search for Old Patterns

```bash
# Find remaining ad-hoc instantiations
grep -r "RAGFlowClient(" app/
grep -r "FlareSolverrClient()" app/
grep -r "StateTracker(" app/
```

### Remove Anti-Patterns

Delete any remaining code that directly instantiates services outside the container.

### Update Documentation

- [ ] Update CLAUDE.md with new import patterns
- [ ] Add "How to use ServiceContainer" section
- [ ] Document testing with mocked containers
- [ ] Update architecture diagrams

---

## 8. Rollback Plan

If issues arise during migration:

1. **Keep old code paths alive** during Phase 1-3
   - Don't delete old service instantiation code
   - Have both old and new code coexist

2. **Feature flag the container** (optional)
   ```python
   from app.config import Config
   
   USE_SERVICE_CONTAINER = Config.USE_SERVICE_CONTAINER or True
   
   if USE_SERVICE_CONTAINER:
       container = get_container()
   else:
       # Use old pattern
   ```

3. **Rollback** if needed
   - Revert to old patterns
   - Delete container code
   - No data loss since container is just a wrapper

---

## 9. Success Criteria

### Phase 1
- [ ] `container.py` created and all tests pass
- [ ] Container integrated without breaking existing code

### Phase 2
- [ ] All scrapers migrated and tests passing
- [ ] No remaining ad-hoc RAGFlowClient/FlareSolverrClient creation in scrapers

### Phase 3
- [ ] All web routes migrated
- [ ] Integration tests passing with container

### Phase 4
- [ ] All ad-hoc service creation removed
- [ ] Code coverage maintained or improved
- [ ] Documentation updated
- [ ] One minor release deployed with container

---

## 10. Benefits After Migration

✅ **Testability:** Mock container instead of patching imports  
✅ **Consistency:** Services created the same way everywhere  
✅ **Maintainability:** Clear dependency graph  
✅ **Performance:** Lazy-loading and caching reduce overhead  
✅ **Clarity:** Dependencies explicit, not hidden  
✅ **Error Handling:** Validation happens once in container  

---

## References

- See [CONFIG_AND_SERVICES.md](CONFIG_AND_SERVICES.md) for architecture details
- See [docs/CLAUDE.md](../CLAUDE.md) for usage examples
- See [tests/unit/test_service_container.py](../tests/unit/test_service_container.py) for test patterns
