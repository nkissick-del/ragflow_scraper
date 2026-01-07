# Metadata Schema & Flow

## Overview

This document defines the complete metadata schema, how documents flow through the system with their metadata, deduplication logic, and validation rules.

---

## DocumentMetadata Dataclass

All scraped documents are represented internally as `DocumentMetadata` objects. This dataclass is the contract between scrapers, state tracking, and RAGFlow.

### Definition

```python
@dataclass
class DocumentMetadata:
    """Metadata for a scraped document."""
    url: str
    title: str
    filename: str
    file_size: Optional[int] = None
    file_size_str: Optional[str] = None
    publication_date: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    source_page: Optional[str] = None
    organization: Optional[str] = None
    document_type: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    local_path: Optional[str] = None
    hash: Optional[str] = None
    extra: dict = field(default_factory=dict)
```

### Field Reference

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `url` | str | ✅ Yes | Source document URL | `"https://aemo.com.au/doc/2025-01.pdf"` |
| `title` | str | ✅ Yes | Human-readable document title | `"2025 Q1 Electricity Report"` |
| `filename` | str | ✅ Yes | Local filename (for file identification) | `"2025_q1_electricity_report.pdf"` |
| `file_size` | int | ❌ Optional | File size in bytes | `2048576` |
| `file_size_str` | str | ❌ Optional | Human-readable file size | `"2.0 MB"` |
| `publication_date` | str | ❌ Optional | ISO 8601 date when document was published | `"2025-01-15"` |
| `tags` | list[str] | ❌ Optional | Category/domain tags for filtering and search | `["Electricity", "Quarterly Report"]` |
| `source_page` | str | ❌ Optional | The page/listing URL where document was found | `"https://aemo.com.au/reports/"` |
| `organization` | str | ❌ Optional | Publishing organization | `"Australian Energy Market Operator"` |
| `document_type` | str | ❌ Optional | Type of document | `"PDF Report"` or `"Article"` |
| `scraped_at` | str | ✅ Yes (auto) | ISO 8601 timestamp when scraped | `"2026-01-07T14:32:45.123456"` |
| `local_path` | str | ❌ Optional | Absolute path to downloaded file | `"/data/scraped/aemo/2025_q1_electricity_report.pdf"` |
| `hash` | str | ❌ Optional | SHA-256 hash of file content (for deduplication) | `"a1b2c3d4e5f6..."` |
| `extra` | dict | ❌ Optional | Scraper-specific metadata (author, abstract, etc.) | `{"author": "John Doe", "abstract": "..."}`  |

---

## Metadata Flow

Metadata travels through four stages:

```
1. SCRAPER EXTRACTION
   └─> DocumentMetadata object created with scraped content
       Fields populated: url, title, filename, file_size, publication_date, tags, etc.
       ↓
2. STATE TRACKING
   └─> StateTracker persists metadata to data/state/{scraper}_state.json
       Minimal storage: URL key, processed_at timestamp, status
       ↓
3. ARTICLE PROCESSING
   └─> ArticleConverter extracts additional metadata (author, abstract, etc.)
       Stores as JSON sidecar file alongside document
       Populates `extra` dict with article-specific fields
       ↓
4. RAGFLOW SUBMISSION
   └─> RAGFlowClient.upload_documents_with_metadata()
       Validates all required fields (see "RAGFlow Format" section)
       Sends flattened metadata dict to RAGFlow API
       Receives document_id on success
```

### Stage 1: Scraper Creation

Each scraper creates `DocumentMetadata` objects while processing documents:

```python
from app.services.container import DocumentMetadata

metadata = DocumentMetadata(
    url="https://example.com/doc.pdf",
    title="Example Document",
    filename="example_document.pdf",
    file_size=1024576,
    file_size_str="1.0 MB",
    publication_date="2026-01-07",
    tags=["Energy", "Report"],
    organization="Example Org",
    document_type="PDF Report"
)
```

**Scraper responsibility:**
- Ensure `url`, `title`, and `filename` are always populated
- Extract `publication_date` in ISO 8601 format when available
- Populate `tags` based on scraper's `required_tags` and `excluded_tags` logic (see [BaseScraper](../app/scrapers/base_scraper.py))
- Set `organization` to scraper's publishing organization
- Set `document_type` based on file extension (PDF, Article, etc.)

### Stage 2: State Persistence

[StateTracker](../app/services/state_tracker.py) stores minimal metadata in JSON for recovery:

```json
{
  "scraper_name": "aemo",
  "created_at": "2026-01-04T09:01:04.183966",
  "last_updated": "2026-01-07T14:32:45.123456",
  "processed_urls": {
    "https://aemo.com.au/doc/2025-01.pdf": {
      "processed_at": "2026-01-07T14:32:45.123456",
      "status": "downloaded",
      "metadata": {
        "title": "2025 Q1 Electricity Report"
      }
    }
  },
  "statistics": {
    "total_processed": 1,
    "total_downloaded": 1,
    "total_skipped": 0,
    "total_failed": 0
  }
}
```

**When to update state:**
- After downloading a document: `state_tracker.mark_processed(url, status="downloaded", metadata=...)`
- After skipping (duplicate/filtered): `state_tracker.mark_processed(url, status="skipped")`
- After failure: `state_tracker.mark_processed(url, status="failed")`

### Stage 3: Article Processing

For HTML articles, [ArticleConverter](../app/utils/article_converter.py) extracts additional metadata:

```python
from app.utils.article_converter import convert_article_to_markdown

markdown, metadata_dict = convert_article_to_markdown(html_content, source_url)
# metadata_dict now contains:
# {
#   "title": "...",
#   "author": "...",
#   "date": "...",
#   "source": "...",
#   "description": "...",
#   "categories": ["..."],
#   "tags": ["..."]
# }

# Update DocumentMetadata.extra with extracted fields
doc_metadata.extra.update(metadata_dict)
```

**Article-specific fields in `extra`:**
- `author`: Article author name
- `abstract` or `description`: Short summary
- `categories`: Categorical tags from page metadata
- `sitename`: Publishing website name

### Stage 4: RAGFlow Submission

[RAGFlowClient](../app/services/ragflow_client.py) validates and submits metadata to RAGFlow:

```python
client = RAGFlowClient(...)
doc_id = client.upload_documents_with_metadata(
    document_metadata=metadata,
    dataset_id="dataset_123",
    document_file_path="/data/scraped/aemo/2025_q1_electricity_report.pdf"
)
```

**Flow:**
1. **Deduplication Check** – Compute hash, check if document exists in dataset
2. **Upload Document** – POST file to RAGFlow (if not duplicate)
3. **Register Document** – Poll RAGFlow API until document is indexed
4. **Push Metadata** – Call `/api/v1/datasets/{dataset_id}/docs_metadata_update` with flattened metadata

---

## Deduplication & Hash Logic

### Hash Computation

Documents are deduplicated using SHA-256 hash of file content:

```python
import hashlib

def compute_hash(file_path: str) -> str:
    """Compute SHA-256 hash of file content."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()
```

**When hash is computed:**
- In [RAGFlowClient._check_document_deduplication()](../app/services/ragflow_client.py#L200)
- Hash is **not** stored in state (only in memory during upload)
- Hash is **computed from file bytes**, not metadata (immune to metadata changes)

### Deduplication Process

```
1. Scraper downloads document to local path
2. RAGFlowClient computes SHA-256 hash
3. Query RAGFlow: GET /api/v1/datasets/{dataset_id}/docs
4. Search returned docs for matching hash
5. If found:
   - Metadata may be updated (no re-upload)
   - Return existing document_id
6. If not found:
   - Upload document file
   - Register document
   - Push metadata
```

### Hash Field in DocumentMetadata

The `DocumentMetadata.hash` field is optional and intended for:
- **Future enhancement:** Store hash in state for offline dedup checks
- **Audit trail:** Verify document integrity across migrations
- **Schema evolution:** Support content-addressed storage

**Current usage:**
- Set by RAGFlowClient during dedup check (in-memory only)
- Not persisted to state or database

---

## Flat Metadata Enforcement

RAGFlow requires metadata as a flat dictionary of strings, numbers, and booleans. The system enforces flattening at submission time:

### RAGFlow Required Fields

These four fields **must** be present and non-empty in every metadata submission. They are enforced by `validate_metadata()` in [app/services/ragflow_metadata.py](../app/services/ragflow_metadata.py#L15).

```python
{
    "organization": str,      # Publishing organization (defaults to "Unknown")
    "source_url": str,        # Original URL
    "scraped_at": str,        # ISO 8601 timestamp when scraped
    "document_type": str,     # Document type (PDF, Article, etc.; defaults to "Unknown")
}
```

### RAGFlow Optional Fields

```python
{
    "source_page": str,       # Listing/index page URL
    "organization": str,      # Publishing organization
    "publication_date": str,  # Publication date
    "author": str,            # Author name
    "abstract": str,          # Summary/description
    # ... any custom fields
}
```

### Flattening Rules

Flattening for the RAGFlow API is handled by `prepare_metadata_for_ragflow()` in [app/services/ragflow_metadata.py](../app/services/ragflow_metadata.py#L45):

```python
def prepare_metadata_for_ragflow(metadata: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for key, value in metadata.items():
        if value is None:
            continue
        elif isinstance(value, (list, tuple)):
            cleaned[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            cleaned[key] = str(value).lower()
        elif isinstance(value, (str, int, float)):
            cleaned[key] = value
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                cleaned[f"{key}.{nested_key}"] = str(nested_value)
        else:
            cleaned[key] = str(value)
    return cleaned
```

**Example transformations:**

| Input | Output |
|-------|--------|
| `{"tags": ["Energy", "Report"]}` | `{"tags": "Energy, Report"}` |
| `{"extra": {"author": "John", "year": 2025}}` | `{"extra.author": "John", "extra.year": 2025}` |
| `{"boolean_flag": True}` | `{"boolean_flag": true}` |

---

## Validation & Constraints

### Required Field Validation

[RAGFlowMetadata.validate_metadata()](../app/services/ragflow_metadata.py#L50):

```python
def validate_metadata(metadata: DocumentMetadata) -> dict:
    """Validate DocumentMetadata has all required fields for RAGFlow."""
    if not metadata.title or not metadata.title.strip():
        raise ValidationError("title is required and cannot be empty")
    if not metadata.url or not metadata.url.strip():
        raise ValidationError("url is required and cannot be empty")
    if not metadata.organization or not metadata.organization.strip():
        raise ValidationError("organization is required for RAGFlow submission")
    if not metadata.document_type or not metadata.document_type.strip():
        raise ValidationError("document_type is required and cannot be empty")
    
    # Ensure scraped_at is set
    if not metadata.scraped_at:
        metadata.scraped_at = datetime.now().isoformat()
    
    return metadata.to_ragflow_dict()
```

### Type Enforcement

- All required fields must be `str` (non-empty)
- Optional fields accept `str | int | float | bool | None`
- Lists are flattened to comma-separated strings
- Nested dicts are flattened with dot notation
- Null/None values are filtered out (except explicitly set)

### Scraper-Specific Constraints

#### PDF Scrapers
- `document_type` must be "PDF Report" or similar
- `file_size` and `file_size_str` should be populated
- No `extra.author` required (PDF metadata may be extracted by RAGFlow)

#### Article Scrapers
- `document_type` must be "Article" or similar
- `extra` should contain: `author`, `abstract`, `publication_date`, `categories`
- `source_page` should be the listing URL

**Example validation per scraper:**

```python
# In AEMO scraper (PDF reports)
if not metadata.file_size:
    raise ValidationError(f"PDF {metadata.filename} missing file_size")
if metadata.publication_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', metadata.publication_date):
    raise ValidationError(f"publication_date must be ISO 8601: {metadata.publication_date}")

# In Guardian scraper (articles)
if not metadata.extra.get('author'):
    logger.warning(f"Article {metadata.title} missing author metadata")
```

---

## Example Metadata Payloads

### Example 1: PDF Report (AEMO)

**DocumentMetadata (in memory):**
```python
DocumentMetadata(
    url="https://aemo.com.au/reports/electricity/2025-q1-operations.pdf",
    title="2025 Q1 Electricity Operations Report",
    filename="aemo_2025_q1_operations.pdf",
    file_size=2048576,
    file_size_str="2.0 MB",
    publication_date="2025-01-15",
    tags=["Electricity", "Quarterly Report", "Operations"],
    source_page="https://aemo.com.au/reports/electricity",
    organization="Australian Energy Market Operator",
    document_type="PDF Report",
    scraped_at="2026-01-07T14:32:45.123456",
    local_path="/data/scraped/aemo/aemo_2025_q1_operations.pdf",
    hash="a1b2c3d4e5f6...",
    extra={}
)
```

**RAGFlow submission (after flattening):**
```json
{
    "organization": "Australian Energy Market Operator",
    "source_url": "https://aemo.com.au/reports/electricity/2025-q1-operations.pdf",
    "document_type": "PDF Report",
    "scraped_at": "2026-01-07T14:32:45.123456",
    "source_page": "https://aemo.com.au/reports/electricity",
    "publication_date": "2025-01-15",
    "tags": "Electricity, Quarterly Report, Operations",
    "file_size": "2048576"
}
```

### Example 2: News Article (Guardian)

**DocumentMetadata (in memory):**
```python
DocumentMetadata(
    url="https://theguardian.com/environment/2026/jan/07/energy-crisis",
    title="Australia Faces New Energy Crisis",
    filename="guardian_energy_crisis_2026.md",
    publication_date="2026-01-07",
    tags=["Energy", "Climate", "Australia"],
    source_page="https://theguardian.com/environment",
    organization="The Guardian",
    document_type="Article",
    scraped_at="2026-01-07T15:10:30.456789",
    local_path="/data/scraped/guardian/guardian_energy_crisis_2026.md",
    hash="b2c3d4e5f6g7...",
    extra={
        "author": "Jane Smith",
        "abstract": "Australia's energy sector faces unprecedented challenges...",
        "categories": ["Environment", "News"],
        "sitename": "The Guardian"
    }
)
```

**RAGFlow submission (after flattening):**
```json
{
    "organization": "The Guardian",
    "source_url": "https://theguardian.com/environment/2026/jan/07/energy-crisis",
    "document_type": "Article",
    "scraped_at": "2026-01-07T15:10:30.456789",
    "source_page": "https://theguardian.com/environment",
    "publication_date": "2026-01-07",
    "tags": "Energy, Climate, Australia",
    "extra.author": "Jane Smith",
    "extra.abstract": "Australia's energy sector faces unprecedented challenges...",
    "extra.categories": "Environment, News",
    "extra.sitename": "The Guardian"
}
```

---

## Schema Changes Policy (No Backward Compatibility)

- State files do **not** carry a schema version and are assumed to match the current code at all times.
- We do **not** provide migration or backward-compatibility layers for old state/metadata. Breaking changes require regenerating state (delete `data/state/{scraper}_state.json` and re-run the scraper).
- If new fields are added to `DocumentMetadata`, update code/tests/docs in lockstep and rely on fresh state and re-scrapes rather than migrations.
- Unknown fields sent to RAGFlow are ignored by the API, but local state must be recreated when schema changes.

---

## References

- [BaseScraper](../app/scrapers/base_scraper.py) – Document creation and filtering logic
- [StateTracker](../app/services/state_tracker.py) – State persistence
- [ArticleConverter](../app/utils/article_converter.py) – HTML article metadata extraction
- [RAGFlowClient](../app/services/ragflow_client.py) – RAGFlow submission and deduplication
- [RAGFlowMetadata](../app/services/ragflow_metadata.py) – Metadata validation and formatting
- [Errors](../app/utils/errors.py) – Custom exception types

