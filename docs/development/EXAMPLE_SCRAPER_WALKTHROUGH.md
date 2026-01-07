# Example Scraper Walkthrough: AEMO

This document provides a line-by-line walkthrough of the AEMO scraper implementation, explaining patterns and best practices.

---

## Overview

**File:** `app/scrapers/aemo_scraper.py`  
**Purpose:** Scrapes PDFs from Australian Energy Market Operator's Major Publications library  
**Complexity:** Medium - uses Selenium for JavaScript rendering, pagination, and metadata extraction

**Why this example:**
- Demonstrates common patterns (Selenium, pagination, metadata)
- Shows state management and exclusion rules
- Includes error handling and logging
- Real-world complexity

---

## Class Definition & Structure

```python
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.models import DocumentMetadata, ScraperResult

class AEMOScraper(BaseScraper):
    """Scraper for AEMO Major Publications."""
    
    NAME = "aemo"
    DISPLAY_NAME = "Australian Energy Market Operator"
    DESCRIPTION = "Scrapes PDFs from AEMO Major Publications"
    BASE_URL = "https://www.aemo.com.au/library/major-publications"
```

**Key points:**
- Inherits from `BaseScraper` (provides common functionality)
- Class-level constants define scraper identity
- `BASE_URL` is the starting point for scraping

---

## Configuration

```python
documents_per_page = 10
request_delay = 2.0  # Be polite
```

**Explanation:**
- `documents_per_page`: Used for pagination calculations
- `request_delay`: Time to wait between requests (respect rate limits)

---

## Initialization

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.log_event("scraper_initialized", scraper=self.NAME)
```

**What happens:**
1. Call parent `__init__` to set up base functionality
2. Log initialization event for tracking
3. Base class handles:
   - Loading state from `data/state/aemo_state.json`
   - Setting up directories
   - Configuring logging

---

## Main Scrape Method

```python
def scrape(self) -> ScraperResult:
    """Main scraping logic."""
    self.log_event("scrape_started", scraper=self.NAME)
    
    try:
        driver = self.get_driver()  # From WebDriverLifecycleMixin
        driver.get(self.BASE_URL)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "search-result-list"))
        )
        
        # Scrape documents
        documents = self._scrape_all_pages(driver)
        
        return ScraperResult(
            status="completed",
            scraper=self.NAME,
            documents_processed=len(documents)
        )
    
    except Exception as e:
        self.log_exception("scrape_failed", e, scraper=self.NAME)
        return ScraperResult(status="failed", scraper=self.NAME, error=str(e))
    
    finally:
        self.quit_driver()  # Always clean up
```

**Flow:**
1. Log start event
2. Get Selenium WebDriver instance
3. Navigate to target URL
4. Wait for page content (JavaScript rendering)
5. Scrape all pages
6. Return result with statistics
7. Handle errors gracefully
8. Always quit driver (even on error)

---

## Pagination Logic

```python
def _scrape_all_pages(self, driver) -> list[dict]:
    """Scrape documents from all pages."""
    all_documents = []
    page = 1
    
    while True:
        self.log_event("scraping_page", page=page, scraper=self.NAME)
        
        # Extract documents from current page
        documents = self._extract_documents_from_page(driver)
        
        if not documents:
            break  # No more documents
        
        all_documents.extend(documents)
        
        # Check if we've hit max pages
        if self.max_pages and page >= self.max_pages:
            break
        
        # Navigate to next page
        if not self._go_to_next_page(driver):
            break  # No more pages
        
        page += 1
        time.sleep(self.request_delay)
    
    return all_documents
```

**Pattern:**
- Loop through pages until no more documents
- Extract documents from each page
- Respect `max_pages` limit (from config)
- Navigate to next page
- Add delay between pages (rate limiting)

---

## Document Extraction

```python
def _extract_documents_from_page(self, driver) -> list[dict]:
    """Extract document info from current page."""
    documents = []
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    for item in soup.select("ul.search-result-list li"):
        # Extract URL
        link = item.select_one("a.pub-title")
        if not link:
            continue
        
        url = urljoin(self.BASE_URL, link["href"])
        
        # Check exclusions
        if self.should_exclude_url(url):
            self.log_event("skipped_duplicate", url=url)
            continue
        
        # Extract metadata
        title = link.get_text(strip=True)
        date_str = item.select_one(".pub-date")
        
        # Download document
        filepath = self.download_file(url, filename=sanitize_filename(title))
        
        if filepath:
            # Save metadata
            metadata = self.get_metadata(filepath, url, title, date_str)
            self.save_metadata(metadata)
            
            # Mark as processed
            self.mark_url_processed(url)
            
            documents.append({"url": url, "title": title})
    
    return documents
```

**Steps:**
1. Parse HTML with BeautifulSoup
2. Find document list items
3. Extract URL from link
4. Check if already processed (skip duplicates)
5. Extract metadata (title, date)
6. Download document
7. Save metadata
8. Mark URL as processed
9. Return list of processed documents

---

## Metadata Extraction

```python
def get_metadata(self, filepath, url, title=None, date_str=None) -> dict:
    """
    Extract document metadata.
    
    Args:
        filepath: Path to downloaded file
        url: Source URL
        title: Document title (optional)
        date_str: Date string from page (optional)
    
    Returns:
        Metadata dict matching METADATA_SCHEMA
    """
    metadata = {
        "title": title or filepath.stem,
        "source": self.NAME,
        "url": url,
        "file_path": str(filepath),
        "file_hash": self._calculate_file_hash(filepath),
        "scraped_at": datetime.now().isoformat()
    }
    
    if date_str:
        # Parse date from string
        try:
            date = datetime.strptime(date_str, "%d %B %Y")
            metadata["date"] = date.strftime("%Y-%m-%d")
        except ValueError:
            pass  # Keep date empty if parsing fails
    
    return metadata
```

**Metadata fields:**
- `title`: Document title
- `source`: Scraper name
- `url`: Original URL
- `file_path`: Local path to downloaded file
- `file_hash`: SHA256 hash (for deduplication)
- `scraped_at`: Timestamp
- `date`: Document date (optional, parsed from page)

See [METADATA_SCHEMA.md](METADATA_SCHEMA.md) for full schema.

---

## State Management

**Checking if URL already processed:**
```python
if self.should_exclude_url(url):
    continue  # Skip
```

**Marking URL as processed:**
```python
self.mark_url_processed(url)
```

**State file structure** (`data/state/aemo_state.json`):
```json
{
  "scraper_name": "aemo",
  "last_updated": "2026-01-08T14:30:00",
  "processed_urls": {
    "https://aemo.com.au/doc1.pdf": {
      "processed_at": "2026-01-08T14:29:00",
      "file_hash": "abc123...",
      "status": "completed"
    }
  },
  "statistics": {
    "total_processed": 42,
    "total_downloaded": 40,
    "total_skipped": 2
  }
}
```

**Benefits:**
- Incremental scraping (only new documents)
- Resumable (can restart after interruption)
- Statistics tracking

---

## Error Handling

**Try-except pattern:**
```python
try:
    filepath = self.download_file(url)
except DownloadError as e:
    self.log_exception("download_failed", e, url=url)
    continue  # Skip this document, process others
```

**Logging with context:**
```python
self.log_exception("extraction_failed", e, 
    url=url,
    page=page,
    scraper=self.NAME
)
```

**Result status:**
```python
return ScraperResult(
    status="failed",  # or "completed"
    scraper=self.NAME,
    error=str(e),
    documents_processed=count
)
```

---

## Testing the Scraper

**Unit test example:**
```python
def test_aemo_extracts_metadata(mock_driver):
    """Test metadata extraction."""
    scraper = AEMOScraper()
    filepath = Path("/tmp/test.pdf")
    url = "https://aemo.com.au/doc.pdf"
    title = "Market Report 2024"
    
    metadata = scraper.get_metadata(filepath, url, title)
    
    assert metadata["source"] == "aemo"
    assert metadata["title"] == "Market Report 2024"
    assert metadata["url"] == url
```

**Integration test example:**
```python
def test_aemo_full_scrape(tmp_path):
    """Test complete scrape workflow."""
    scraper = AEMOScraper()
    scraper.download_dir = tmp_path / "scraped"
    scraper.max_pages = 1  # Limit for test
    
    result = scraper.scrape()
    
    assert result.status == "completed"
    assert result.documents_processed > 0
    assert (tmp_path / "scraped" / "aemo").exists()
```

---

## Key Takeaways

1. **Use Mixins:** Don't reimplement common functionality
   - `IncrementalStateMixin` - State tracking
   - `WebDriverLifecycleMixin` - Selenium management
   - `MetadataIOMixin` - Metadata storage

2. **Structured Logging:** Always include context
   ```python
   log_event("event_name", key=value, scraper=self.NAME)
   ```

3. **Error Handling:** Fail gracefully, continue processing
   ```python
   try:
       process_document()
   except Exception as e:
       log_exception("failed", e)
       continue  # Don't stop entire scrape
   ```

4. **Incremental Scraping:** Check state before processing
   ```python
   if self.should_exclude_url(url):
       continue
   ```

5. **Clean Up:** Always release resources
   ```python
   finally:
       self.quit_driver()
   ```

6. **Rate Limiting:** Be respectful
   ```python
   time.sleep(self.request_delay)
   ```

7. **Metadata:** Extract rich metadata for RAGFlow
   ```python
   metadata = {
       "title": ...,
       "source": ...,
       "date": ...,
       # See METADATA_SCHEMA.md
   }
   ```

---

## Common Patterns

### Pattern 1: Selenium Page Wait
```python
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CLASS_NAME, "content"))
)
```

### Pattern 2: BeautifulSoup Parsing
```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(driver.page_source, "html.parser")
items = soup.select("ul.list li.item")
```

### Pattern 3: URL Construction
```python
from urllib.parse import urljoin

full_url = urljoin(self.BASE_URL, relative_path)
```

### Pattern 4: Filename Sanitization
```python
from app.utils import sanitize_filename

safe_name = sanitize_filename(title) + ".pdf"
```

### Pattern 5: Pagination
```python
page = 1
while True:
    documents = extract_page(driver, page)
    if not documents or (max_pages and page >= max_pages):
        break
    page += 1
    navigate_to_next_page(driver)
```

---

## See Also

- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Full development guide
- [METADATA_SCHEMA.md](METADATA_SCHEMA.md) - Metadata requirements
- [LOGGING_AND_ERROR_STANDARDS.md](LOGGING_AND_ERROR_STANDARDS.md) - Logging patterns
- [SCRAPER_TEMPLATE.md](SCRAPER_TEMPLATE.md) - Base scraper documentation
