# Backend Developer Guide

**Version:** 2.0
**Date:** 2026-02-05
**Audience:** Developers adding new backend implementations

## Overview

This guide explains how to implement new Parser, Archive, and RAG backends for the modular pipeline.

## Architecture Overview

The modular pipeline uses three backend types:

1. **Parser Backend**: PDF → Markdown conversion
2. **Archive Backend**: Document storage
3. **RAG Backend**: Vector indexing

Each backend type has:
- An abstract base class (ABC) defining the interface
- A result dataclass for return values
- One or more concrete implementations

## Adding a New Parser Backend

### Step 1: Create Implementation File

```bash
touch app/backends/parsers/my_parser.py
```

### Step 2: Implement ParserBackend ABC

```python
# app/backends/parsers/my_parser.py
from pathlib import Path
from typing import Optional

from app.backends.parsers.base import ParserBackend, ParserResult
from app.scrapers.models import DocumentMetadata
from app.utils import get_logger


class MyParser(ParserBackend):
    """Parser using MyPDFLibrary."""

    def __init__(self, config: Optional[dict] = None):
        """Initialize parser with optional configuration."""
        self.config = config or {}
        self.logger = get_logger("backends.parser.my_parser")
        self._available = None

    @property
    def name(self) -> str:
        """Get parser name."""
        return "my_parser"

    def is_available(self) -> bool:
        """Check if parser dependencies are available."""
        if self._available is not None:
            return self._available

        try:
            import my_pdf_library  # noqa: F401
            self._available = True
            self.logger.info("MyParser available")
        except ImportError:
            self._available = False
            self.logger.warning("MyPDFLibrary not installed")

        return self._available

    def get_supported_formats(self) -> list[str]:
        """Get supported file extensions."""
        return [".pdf", ".docx"]

    def parse_document(
        self, pdf_path: Path, context_metadata: DocumentMetadata
    ) -> ParserResult:
        """Parse PDF to Markdown."""
        if not self.is_available():
            return ParserResult(
                success=False,
                error="MyPDFLibrary not available",
                parser_name=self.name
            )

        if not pdf_path.exists():
            return ParserResult(
                success=False,
                error=f"File not found: {pdf_path}",
                parser_name=self.name
            )

        try:
            # Lazy import
            from my_pdf_library import parse_pdf

            self.logger.info(f"Parsing: {pdf_path.name}")

            # Parse PDF
            result = parse_pdf(str(pdf_path))

            # Convert to Markdown
            markdown = result.to_markdown()

            # Write Markdown file
            markdown_path = pdf_path.with_suffix(".md")
            markdown_path.write_text(markdown, encoding="utf-8")

            # Extract metadata
            metadata = {
                "title": result.title or context_metadata.title,
                "author": result.author,
                "page_count": len(result.pages),
                "parsed_by": self.name,
            }

            return ParserResult(
                success=True,
                markdown_path=markdown_path,
                metadata=metadata,
                parser_name=self.name,
            )

        except Exception as e:
            self.logger.error(f"Parsing failed: {e}")
            return ParserResult(
                success=False,
                error=str(e),
                parser_name=self.name
            )
```

### Step 3: Register in ServiceContainer

```python
# app/services/container.py

@property
def parser_backend(self):
    """Get parser backend."""
    if self._parser_backend is None:
        backend_name = Config.PARSER_BACKEND

        if backend_name == "docling":
            from app.backends.parsers.docling_parser import DoclingParser
            self._parser_backend = DoclingParser()
        elif backend_name == "my_parser":  # Add this
            from app.backends.parsers.my_parser import MyParser
            self._parser_backend = MyParser()
        else:
            raise ValueError(f"Unknown parser: {backend_name}")

        if not self._parser_backend.is_available():
            raise ValueError(f"Parser '{backend_name}' not available")

    return self._parser_backend
```

### Step 4: Add to Config Validation

```python
# app/config.py

@classmethod
def validate(cls):
    """Validate config."""
    # ...

    valid_parsers = ["docling", "mineru", "tika", "my_parser"]  # Add here
    if cls.PARSER_BACKEND not in valid_parsers:
        raise ValueError(f"Invalid PARSER_BACKEND: {cls.PARSER_BACKEND}")
```

### Step 5: Test Your Parser

```python
# tests/unit/test_my_parser.py
import pytest
from pathlib import Path
from app.backends.parsers.my_parser import MyParser
from app.scrapers.models import DocumentMetadata


class TestMyParser:
    """Tests for MyParser backend."""

    def test_parser_name(self):
        """Test parser name."""
        parser = MyParser()
        assert parser.name == "my_parser"

    def test_supported_formats(self):
        """Test supported formats."""
        parser = MyParser()
        assert ".pdf" in parser.get_supported_formats()

    def test_parse_nonexistent_file(self):
        """Test parsing nonexistent file."""
        parser = MyParser()
        metadata = DocumentMetadata(
            url="http://test.com",
            title="Test",
            filename="test.pdf"
        )

        result = parser.parse_document(Path("/nonexistent.pdf"), metadata)
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.integration
    def test_parse_real_pdf(self, tmp_path):
        """Test parsing real PDF."""
        # Requires MyPDFLibrary installed
        parser = MyParser()
        if not parser.is_available():
            pytest.skip("MyPDFLibrary not available")

        # Create test PDF or use fixture
        pdf_path = tmp_path / "test.pdf"
        # ... create test PDF ...

        metadata = DocumentMetadata(
            url="http://test.com",
            title="Test",
            filename="test.pdf"
        )

        result = parser.parse_document(pdf_path, metadata)
        assert result.success
        assert result.markdown_path.exists()
        assert result.metadata.get("page_count", 0) > 0
```

### Step 6: Add Dependencies

```bash
# requirements.txt
my-pdf-library>=1.0.0
```

### Step 7: Update Documentation

- Add to `docs/operations/BACKEND_MIGRATION_GUIDE.md` parser table
- Add example configuration to `.env.example`
- Update `.claude/instructions.md` if necessary

## Adding a New Archive Backend

### Step 1: Create Implementation File

```bash
touch app/backends/archives/my_archive.py
```

### Step 2: Implement ArchiveBackend ABC

```python
# app/backends/archives/my_archive.py
from pathlib import Path
from typing import Optional

from app.backends.archives.base import ArchiveBackend, ArchiveResult
from app.utils import get_logger


class MyArchiveBackend(ArchiveBackend):
    """Archive backend using MyStorageService."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """Initialize archive backend."""
        from app.config import Config

        self.api_url = api_url or Config.MY_ARCHIVE_API_URL
        self.api_key = api_key or Config.MY_ARCHIVE_API_KEY
        self.logger = get_logger("backends.archive.my_archive")

    @property
    def name(self) -> str:
        """Get archive name."""
        return "my_archive"

    def is_configured(self) -> bool:
        """Check if backend is configured."""
        return bool(self.api_url and self.api_key)

    def archive_document(
        self,
        file_path: Path,
        title: str,
        created: Optional[str] = None,
        correspondent: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> ArchiveResult:
        """Archive document."""
        if not self.is_configured():
            return ArchiveResult(
                success=False,
                error="MyArchive not configured",
                archive_name=self.name
            )

        if not file_path.exists():
            return ArchiveResult(
                success=False,
                error=f"File not found: {file_path}",
                archive_name=self.name
            )

        try:
            import requests

            # Upload file
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                data = {
                    "title": title,
                    "created": created,
                    "correspondent": correspondent,
                    "tags": ",".join(tags or []),
                }

                response = requests.post(
                    f"{self.api_url}/api/upload",
                    files=files,
                    data=data,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=60
                )

            response.raise_for_status()
            result_data = response.json()

            document_id = result_data["id"]
            url = f"{self.api_url}/documents/{document_id}"

            self.logger.info(f"Archived: {document_id}")
            return ArchiveResult(
                success=True,
                document_id=document_id,
                url=url,
                archive_name=self.name,
            )

        except Exception as e:
            self.logger.error(f"Archive failed: {e}")
            return ArchiveResult(
                success=False,
                error=str(e),
                archive_name=self.name
            )

    def verify_document(self, document_id: str, timeout: int = 60) -> bool:
        """Verify document was archived (Sonarr-style polling)."""
        import time
        import requests

        if not self.is_configured():
            return False

        start_time = time.time()
        poll_interval = 2

        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.api_url}/api/documents/{document_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10
                )

                if response.ok:
                    data = response.json()
                    if data.get("status") == "ready":
                        self.logger.info(f"Verified: {document_id}")
                        return True

            except Exception as e:
                self.logger.warning(f"Verification check failed: {e}")

            time.sleep(poll_interval)

        self.logger.warning(f"Verification timeout: {document_id}")
        return False
```

### Step 3: Add Config Variables

```python
# app/config.py
class Config:
    # ...

    # MyArchive
    MY_ARCHIVE_API_URL = os.getenv("MY_ARCHIVE_API_URL", "")
    MY_ARCHIVE_API_KEY = os.getenv("MY_ARCHIVE_API_KEY", "")
```

### Step 4: Register in ServiceContainer

```python
# app/services/container.py

@property
def archive_backend(self):
    """Get archive backend."""
    if self._archive_backend is None:
        backend_name = Config.ARCHIVE_BACKEND

        if backend_name == "paperless":
            from app.backends.archives.paperless_adapter import PaperlessArchiveBackend
            self._archive_backend = PaperlessArchiveBackend()
        elif backend_name == "my_archive":  # Add this
            from app.backends.archives.my_archive import MyArchiveBackend
            self._archive_backend = MyArchiveBackend()
        else:
            raise ValueError(f"Unknown archive: {backend_name}")

    return self._archive_backend
```

### Step 5: Add Validation and Documentation

Same as parser backend (steps 4-7).

## Adding a New RAG Backend

### Step 1: Create Implementation File

```bash
touch app/backends/rag/my_rag.py
```

### Step 2: Implement RAGBackend ABC

```python
# app/backends/rag/my_rag.py
from pathlib import Path
from typing import Optional

from app.backends.rag.base import RAGBackend, RAGResult
from app.utils import get_logger


class MyRAGBackend(RAGBackend):
    """RAG backend using MyVectorDB."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection: Optional[str] = None,
    ):
        """Initialize RAG backend."""
        from app.config import Config

        self.api_url = api_url or Config.MY_RAG_API_URL
        self.api_key = api_key or Config.MY_RAG_API_KEY
        self.collection = collection or Config.MY_RAG_COLLECTION
        self.logger = get_logger("backends.rag.my_rag")

    @property
    def name(self) -> str:
        """Get RAG backend name."""
        return "my_rag"

    def is_configured(self) -> bool:
        """Check if backend is configured."""
        return bool(self.api_url and self.api_key)

    def test_connection(self) -> bool:
        """Test connection to RAG service."""
        try:
            import requests
            response = requests.get(
                f"{self.api_url}/api/health",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5
            )
            return response.ok
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    def ingest_document(
        self,
        markdown_path: Path,
        metadata: dict,
        collection_id: Optional[str] = None,
    ) -> RAGResult:
        """Ingest Markdown document into RAG system."""
        if not self.is_configured():
            return RAGResult(
                success=False,
                error="MyRAG not configured",
                rag_name=self.name
            )

        if not markdown_path.exists():
            return RAGResult(
                success=False,
                error=f"Markdown not found: {markdown_path}",
                rag_name=self.name
            )

        try:
            import requests

            # Read Markdown content
            content = markdown_path.read_text(encoding="utf-8")

            # Prepare payload
            collection = collection_id or self.collection
            payload = {
                "content": content,
                "metadata": metadata,
                "collection": collection,
            }

            # Upload to RAG
            response = requests.post(
                f"{self.api_url}/api/ingest",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60
            )

            response.raise_for_status()
            result_data = response.json()

            document_id = result_data["document_id"]
            self.logger.info(f"Ingested: {document_id}")

            return RAGResult(
                success=True,
                document_id=document_id,
                collection_id=collection,
                rag_name=self.name,
            )

        except Exception as e:
            self.logger.error(f"Ingestion failed: {e}")
            return RAGResult(
                success=False,
                error=str(e),
                rag_name=self.name
            )
```

### Step 3: Add Config, Register, Validate

Same process as parser/archive backends.

## Testing Checklist

- [ ] Unit tests for all methods
- [ ] Integration tests with real service
- [ ] Error handling (network failures, timeouts)
- [ ] Configuration validation
- [ ] Lazy import behavior
- [ ] Logging at appropriate levels
- [ ] Documentation updated

## Best Practices

### Lazy Imports

```python
# Good: Lazy import
def parse_document(self, ...):
    from my_library import Parser  # Import only when needed
    parser = Parser()
    # ...

# Bad: Top-level import
from my_library import Parser  # Fails if library not installed

class MyBackend:
    def parse_document(self, ...):
        parser = Parser()
        # ...
```

### Error Handling

```python
# Good: Return result object with error
try:
    # ... operation ...
    return ParserResult(success=True, ...)
except Exception as e:
    self.logger.error(f"Operation failed: {e}")
    return ParserResult(success=False, error=str(e), parser_name=self.name)

# Bad: Raise exception
try:
    # ... operation ...
except Exception as e:
    raise RuntimeError(f"Failed: {e}")  # Don't do this
```

### Logging

```python
# Use structured logging with appropriate levels
self.logger.info(f"Starting parse: {filename}")      # Info: Normal operations
self.logger.warning(f"Retrying after failure: {e}")   # Warning: Recoverable issues
self.logger.error(f"Parse failed: {e}")               # Error: Operation failed
self.logger.debug(f"Metadata: {metadata}")            # Debug: Detailed info
```

### Configuration

```python
# Good: Fallback to Config, allow override
def __init__(self, api_url: Optional[str] = None):
    from app.config import Config
    self.api_url = api_url or Config.MY_SERVICE_URL

# Bad: Hardcoded values
def __init__(self):
    self.api_url = "http://localhost:8000"  # Don't do this
```

## Common Pitfalls

### 1. Forgetting is_available() Check

```python
# Bad
def parse_document(self, pdf_path, metadata):
    from my_library import Parser  # May fail
    # ...

# Good
def parse_document(self, pdf_path, metadata):
    if not self.is_available():
        return ParserResult(success=False, error="Library not available", ...)
    # ...
```

### 2. Not Handling File Paths Properly

```python
# Bad
markdown_path = pdf_path.replace(".pdf", ".md")  # String manipulation

# Good
markdown_path = pdf_path.with_suffix(".md")  # Path method
```

### 3. Blocking Operations

```python
# Bad: Synchronous, blocks pipeline
def verify_document(self, doc_id, timeout=60):
    time.sleep(60)  # Always sleeps 60s
    return self.check_status(doc_id)

# Good: Poll with early exit
def verify_document(self, doc_id, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        if self.check_status(doc_id) == "ready":
            return True
        time.sleep(2)
    return False
```

## Example Pull Request

See [example PR](https://github.com/your-repo/pull/123) for adding MinerU parser backend.

**PR Checklist:**
- [ ] Implementation follows ABC interface
- [ ] Unit tests added
- [ ] Integration tests added (or marked as skipped)
- [ ] ServiceContainer updated
- [ ] Config validation updated
- [ ] Documentation updated (.env.example, migration guide, developer guide)
- [ ] Dependencies added to requirements.txt
- [ ] Lazy imports used
- [ ] Error handling comprehensive
- [ ] Logging appropriate

---

**Last Updated:** 2026-02-05
**For:** PDF Scraper v2.0
