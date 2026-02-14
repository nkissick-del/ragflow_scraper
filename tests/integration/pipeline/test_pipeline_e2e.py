"""End-to-end pipeline integration tests.

Tests the full workflow: scrape → parse → archive → RAG
"""

import pytest
from unittest.mock import Mock, patch

from app.orchestrator.pipeline import Pipeline, PipelineResult
from app.scrapers import ScraperRegistry
from app.backends.parsers.base import ParserResult
from app.backends.archives.base import ArchiveResult


class DummyScraperResult:
    """Mock scraper result with documents."""

    def __init__(self, doc_count=1, tmp_path=None):
        self.scraped_count = doc_count
        self.downloaded_count = doc_count
        self.errors = []
        self.status = "completed"
        self.documents = []

        # Create mock documents
        for i in range(doc_count):
            pdf_path = f"{tmp_path.as_posix()}/test_doc_{i + 1}.pdf"

            self.documents.append(
                {
                    "title": f"Test Document {i + 1}",
                    "url": f"http://example.com/doc{i + 1}",
                    "organization": "TestOrg",
                    "publication_date": "2024-01-15",
                    "filename": f"test_doc_{i + 1}.pdf",
                    "pdf_path": pdf_path,
                    "hash": f"hash{i + 1}",
                }
            )


class DummyScraper:
    """Mock scraper that yields documents as a generator."""

    def __init__(self, doc_count=1, tmp_path=None):
        if tmp_path is None:
            raise ValueError("tmp_path is required for DummyScraper")
        self.doc_count = doc_count
        self.tmp_path = tmp_path

    def run(self):
        result = DummyScraperResult(self.doc_count, self.tmp_path)
        yield from result.documents
        return result


def _scraper_gen(scraper_result):
    """Create a generator from a DummyScraperResult."""
    yield from scraper_result.documents
    return scraper_result


@pytest.fixture
def mock_container():
    """Create mock service container."""
    container = Mock()
    container.parser_backend = Mock()
    container.archive_backend = Mock()
    container.rag_backend = Mock()
    # Pipeline reads settings overrides (e.g. merge strategy); return empty = use Config default
    container.settings.get.return_value = ""
    return container


@pytest.fixture
def temp_pdf(tmp_path):
    """Create a temporary PDF file."""
    pdf_file = tmp_path / "test_doc_1.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\nTest PDF content")
    return pdf_file


class TestE2EPipelineHappyPath:
    """Test successful end-to-end pipeline execution."""

    def test_full_pipeline_success(self, mock_container, tmp_path, temp_pdf):
        """Should successfully process document through all stages."""
        # Setup: Create markdown output path
        markdown_file = tmp_path / "test_doc_1.md"
        markdown_file.write_text("# Test Document 1\n\nContent here.")

        # Mock scraper
        scraper = DummyScraper(doc_count=1, tmp_path=tmp_path)

        # Mock parser backend
        parser_result = ParserResult(
            success=True,
            markdown_path=markdown_file,
            metadata={
                "title": "Test Document 1",
                "author": "Test Author",
                "page_count": 5,
            },
            parser_name="docling",
        )
        mock_container.parser_backend.parse_document.return_value = parser_result

        # Mock archive backend
        archive_result = ArchiveResult(
            success=True,
            document_id="123",
            archive_name="paperless",
        )
        mock_container.archive_backend.archive_document.return_value = archive_result

        # Mock RAG backend
        rag_result = Mock()
        rag_result.success = True
        rag_result.document_id = "rag-doc-789"
        rag_result.collection_id = "workspace-123"
        mock_container.rag_backend.ingest_document.return_value = rag_result

        # Create pipeline
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                dataset_id="test-dataset",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                verify_document_timeout=5,
                container=mock_container,
            )

            # Execute
            result = pipeline.run()

        # Verify
        assert isinstance(result, PipelineResult)
        assert result.status == "completed"
        assert result.scraped_count == 1
        assert result.downloaded_count == 1
        assert result.parsed_count == 1
        assert result.archived_count == 1
        assert result.verified_count == 1
        assert result.rag_indexed_count == 1
        assert result.failed_count == 0
        assert len(result.errors) == 0

        # Verify backends were called
        mock_container.parser_backend.parse_document.assert_called_once()
        mock_container.archive_backend.archive_document.assert_called_once()
        mock_container.rag_backend.ingest_document.assert_called_once()

    def test_pipeline_with_multiple_documents(self, mock_container, tmp_path):
        """Should process multiple documents successfully."""
        # Create temp PDFs
        for i in range(3):
            pdf_file = tmp_path / f"test_doc_{i + 1}.pdf"
            pdf_file.write_bytes(b"%PDF-1.4\nTest PDF content")

            markdown_file = tmp_path / f"test_doc_{i + 1}.md"
            markdown_file.write_text(f"# Test Document {i + 1}\n\nContent here.")

        # Mock scraper with 3 documents
        scraper = DummyScraper(doc_count=3, tmp_path=tmp_path)

        # Mock parser backend to return different results
        def mock_parse(file_path, context_metadata):
            doc_num = file_path.stem.split("_")[-1]
            markdown_path = tmp_path / f"test_doc_{doc_num}.md"
            return ParserResult(
                success=True,
                markdown_path=markdown_path,
                metadata={
                    "title": f"Test Document {doc_num}",
                    "page_count": 5,
                },
                parser_name="docling",
            )

        mock_container.parser_backend.parse_document.side_effect = mock_parse

        # Mock archive backend
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=True,
            document_id="123",
            archive_name="paperless",
        )

        # Mock RAG backend
        rag_result = Mock()
        rag_result.success = True
        rag_result.document_id = "rag-doc"
        mock_container.rag_backend.ingest_document.return_value = rag_result

        # Create pipeline
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                dataset_id="test-dataset",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )

            # Execute
            result = pipeline.run()

        # Verify
        assert result.status == "completed"
        assert result.scraped_count == 3
        assert result.downloaded_count == 3
        assert result.parsed_count == 3
        assert result.archived_count == 3
        assert result.rag_indexed_count == 3
        assert result.failed_count == 0


class TestE2EPipelineErrorHandling:
    """Test error handling in pipeline stages."""

    def test_parser_failure_continues_pipeline(self, mock_container, tmp_path):
        """Should continue processing other documents when parser fails."""
        # Create temp PDFs
        pdf1 = tmp_path / "test_doc_1.pdf"
        pdf1.write_bytes(b"%PDF-1.4\nTest PDF")
        pdf2 = tmp_path / "test_doc_2.pdf"
        pdf2.write_bytes(b"%PDF-1.4\nTest PDF")

        markdown_file = tmp_path / "test_doc_2.md"
        markdown_file.write_text("# Test Document 2\n\nContent.")

        # Mock scraper with 2 documents
        scraper = DummyScraper(doc_count=2, tmp_path=tmp_path)

        # Mock parser: first fails, second succeeds
        def mock_parse(file_path, context_metadata):
            if "doc_1" in str(file_path):
                raise Exception("Parser error")
            return ParserResult(
                success=True,
                markdown_path=markdown_file,
                metadata={"title": "Test Document 2"},
                parser_name="docling",
            )

        mock_container.parser_backend.parse_document.side_effect = mock_parse

        # Mock archive and RAG
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=True, document_id="123", archive_name="paperless"
        )
        rag_result = Mock()
        rag_result.success = True
        mock_container.rag_backend.ingest_document.return_value = rag_result

        # Execute
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                dataset_id="test-dataset",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )
            result = pipeline.run()

        # Verify: one failed (parser error → FAIL FAST), one succeeded
        assert result.status == "partial"
        assert result.parsed_count == 1
        assert result.failed_count == 1
        assert len(result.errors) == 1

    def test_archive_failure_fails_document(self, mock_container, tmp_path):
        """Archive failure should FAIL FAST for the document (ArchiveError)."""
        # Setup
        pdf_file = tmp_path / "test_doc_1.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\nTest")
        markdown_file = tmp_path / "test_doc_1.md"
        markdown_file.write_text("# Test\n\nContent.")

        scraper = DummyScraper(doc_count=1, tmp_path=tmp_path)

        # Parser succeeds
        mock_container.parser_backend.parse_document.return_value = ParserResult(
            success=True,
            markdown_path=markdown_file,
            metadata={"title": "Test"},
            parser_name="docling",
        )

        # Archive fails
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=False,
            error="Archive service unavailable",
            archive_name="paperless",
        )

        # RAG succeeds (but won't be reached due to archive FAIL FAST)
        rag_result = Mock()
        rag_result.success = True
        mock_container.rag_backend.ingest_document.return_value = rag_result

        # Execute
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                dataset_id="test-dataset",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )
            result = pipeline.run()

        # Verify: Archive FAIL FAST means document counted as failed
        assert result.parsed_count == 0  # Caught by outer handler before counter
        assert result.archived_count == 0  # Archive failed
        assert result.rag_indexed_count == 0  # Not reached
        assert result.failed_count == 1  # Document failed
        assert len(result.errors) == 1
        assert "Archive service unavailable" in result.errors[0]

    def test_scraper_failure_stops_pipeline(self, mock_container):
        """Should stop pipeline when scraper fails."""
        # Mock failed scraper
        scraper_result = DummyScraperResult(doc_count=0)
        scraper_result.status = "failed"
        scraper_result.errors = ["Scraper connection failed"]
        scraper = Mock()
        scraper.run.return_value = _scraper_gen(scraper_result)

        # Execute
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                container=mock_container,
            )
            result = pipeline.run()

        # Verify: pipeline stopped, no processing
        assert result.status == "failed"
        assert result.parsed_count == 0
        assert result.archived_count == 0
        assert "Scraper failed" in result.errors

    def test_no_documents_downloaded_completes_successfully(self, mock_container):
        """Should complete successfully when no new documents."""
        # Mock scraper with no downloads
        scraper_result = DummyScraperResult(doc_count=0)
        scraper_result.downloaded_count = 0
        scraper_result.documents = []
        scraper = Mock()
        scraper.run.return_value = _scraper_gen(scraper_result)

        # Execute
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                container=mock_container,
            )
            result = pipeline.run()

        # Verify
        assert result.status == "completed"
        assert result.downloaded_count == 0
        assert result.parsed_count == 0
        assert len(result.errors) == 0


class TestE2EPipelineMetadata:
    """Test metadata handling through pipeline."""

    def test_metadata_merging(self, mock_container, tmp_path):
        """Should merge scraper and parser metadata correctly."""
        # Setup
        pdf_file = tmp_path / "test_doc_1.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\nTest")
        markdown_file = tmp_path / "test_doc_1.md"
        markdown_file.write_text("# Test\n\nContent.")

        # Scraper provides URL, org, date
        scraper = DummyScraper(doc_count=1, tmp_path=tmp_path)

        # Parser provides title, author, page_count
        parser_result = ParserResult(
            success=True,
            markdown_path=markdown_file,
            metadata={
                "title": "Extracted Title",
                "author": "Extracted Author",
                "page_count": 10,
            },
            parser_name="docling",
        )
        mock_container.parser_backend.parse_document.return_value = parser_result

        # Mock archive and RAG
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=True, document_id="123", archive_name="paperless"
        )
        rag_result = Mock()
        rag_result.success = True
        mock_container.rag_backend.ingest_document.return_value = rag_result

        # Execute
        with patch.object(ScraperRegistry, "get_scraper", return_value=scraper):
            pipeline = Pipeline(
                scraper_name="test_scraper",
                dataset_id="test-dataset",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )
            result = pipeline.run()

        # Verify: check that archive was called with merged metadata
        archive_call = mock_container.archive_backend.archive_document.call_args
        assert archive_call is not None

        # Extract the metadata from call_args (args, kwargs)
        call_kwargs = archive_call[1]
        merged_metadata = call_kwargs.get("metadata")
        assert merged_metadata is not None, (
            "metadata should be passed to archive_document"
        )

        # Verify merged metadata contains expected scraper fields
        assert merged_metadata.get("url") == "http://example.com/doc1"
        assert merged_metadata.get("organization") == "TestOrg"
        assert merged_metadata.get("publication_date") == "2024-01-15"

        # Verify merged metadata contains expected parser fields
        # 'author' is a standard DocumentMetadata field (promoted from extra)
        assert merged_metadata.get("author") == "Extracted Author"
        assert merged_metadata.get("page_count") == 10

        # Verify the title (could be from scraper or parser depending on merge strategy)
        assert "title" in merged_metadata

        assert result.parsed_count == 1
        assert result.archived_count == 1


class TestE2EPipelineFormatRouting:
    """Test format-aware document routing."""

    def test_markdown_skips_parsing(self, mock_container, tmp_path):
        """Markdown files should skip the parser backend entirely."""
        # Create a markdown file (not a PDF)
        md_file = tmp_path / "test_doc_1.md"
        md_file.write_text("# Test Article\n\nSome content here.\n")

        # Scraper result with local_path pointing to .md
        scraper_result = DummyScraperResult(doc_count=1, tmp_path=tmp_path)
        scraper_result.documents[0]["pdf_path"] = None
        scraper_result.documents[0]["local_path"] = str(md_file)
        scraper = Mock()
        scraper.run.return_value = _scraper_gen(scraper_result)

        # Mock archive backend
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=True, document_id="123", archive_name="paperless"
        )

        # Mock RAG backend
        rag_result = Mock()
        rag_result.success = True
        mock_container.rag_backend.ingest_document.return_value = rag_result

        # Execute
        with (
            patch.object(ScraperRegistry, "get_scraper", return_value=scraper),
            patch("app.orchestrator.pipeline.Config") as mock_config,
        ):
            mock_config.METADATA_MERGE_STRATEGY = "smart"
            mock_config.RAGFLOW_DATASET_ID = "test-dataset"
            mock_config.GOTENBERG_URL = ""
            mock_config.TIKA_ENRICHMENT_ENABLED = False
            mock_config.TIKA_SERVER_URL = ""

            pipeline = Pipeline(
                scraper_name="test_scraper",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )
            result = pipeline.run()

        # Parser backend should NOT have been called
        mock_container.parser_backend.parse_document.assert_not_called()

        assert result.parsed_count == 1
        assert result.archived_count == 1

    def test_markdown_with_gotenberg_conversion(self, mock_container, tmp_path):
        """Markdown files should use Gotenberg to create archive PDF."""
        md_file = tmp_path / "test_doc_1.md"
        md_file.write_text("# Test\n\nContent.")

        scraper_result = DummyScraperResult(doc_count=1, tmp_path=tmp_path)
        scraper_result.documents[0]["pdf_path"] = None
        scraper_result.documents[0]["local_path"] = str(md_file)
        scraper = Mock()
        scraper.run.return_value = _scraper_gen(scraper_result)

        # Mock Gotenberg client
        mock_gotenberg = Mock()
        mock_gotenberg.convert_markdown_to_pdf.return_value = b"%PDF-1.4 gotenberg"
        mock_container.gotenberg_client = mock_gotenberg

        # Mock archive backend
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=True, document_id="456", archive_name="paperless"
        )

        # Mock RAG
        rag_result = Mock()
        rag_result.success = True
        mock_container.rag_backend.ingest_document.return_value = rag_result

        with (
            patch.object(ScraperRegistry, "get_scraper", return_value=scraper),
            patch("app.orchestrator.pipeline.Config") as mock_config,
        ):
            mock_config.METADATA_MERGE_STRATEGY = "smart"
            mock_config.RAGFLOW_DATASET_ID = "test-dataset"
            mock_config.GOTENBERG_URL = "http://gotenberg:3156"
            mock_config.TIKA_ENRICHMENT_ENABLED = False
            mock_config.TIKA_SERVER_URL = ""

            pipeline = Pipeline(
                scraper_name="test_scraper",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )
            result = pipeline.run()

        # Gotenberg should have been called for MD→PDF
        mock_gotenberg.convert_markdown_to_pdf.assert_called_once()

        # Archive should receive the .archive.pdf path
        archive_call = mock_container.archive_backend.archive_document.call_args
        archive_path = archive_call[1]["file_path"]
        assert str(archive_path).endswith(".archive.pdf")

        assert result.parsed_count == 1
        assert result.archived_count == 1

    def test_office_format_uses_tika(self, mock_container, tmp_path):
        """Office formats should use Tika for text extraction."""
        docx_file = tmp_path / "test_doc_1.docx"
        docx_file.write_bytes(b"fake docx content")

        scraper_result = DummyScraperResult(doc_count=1, tmp_path=tmp_path)
        scraper_result.documents[0]["pdf_path"] = None
        scraper_result.documents[0]["local_path"] = str(docx_file)
        scraper = Mock()
        scraper.run.return_value = _scraper_gen(scraper_result)

        # Mock Tika client
        mock_tika = Mock()
        mock_tika.extract_text.return_value = "Extracted office text."
        mock_tika.extract_metadata.return_value = {"title": "Office Doc"}
        mock_container.tika_client = mock_tika

        # Mock Gotenberg
        mock_gotenberg = Mock()
        mock_gotenberg.convert_to_pdf.return_value = b"%PDF-1.4 office"
        mock_container.gotenberg_client = mock_gotenberg

        # Mock archive
        mock_container.archive_backend.archive_document.return_value = ArchiveResult(
            success=True, document_id="789", archive_name="paperless"
        )

        # Mock RAG
        rag_result = Mock()
        rag_result.success = True
        mock_container.rag_backend.ingest_document.return_value = rag_result

        with (
            patch.object(ScraperRegistry, "get_scraper", return_value=scraper),
            patch("app.orchestrator.pipeline.Config") as mock_config,
        ):
            mock_config.METADATA_MERGE_STRATEGY = "smart"
            mock_config.RAGFLOW_DATASET_ID = "test-dataset"
            mock_config.GOTENBERG_URL = "http://gotenberg:3156"
            mock_config.TIKA_ENRICHMENT_ENABLED = False
            mock_config.TIKA_SERVER_URL = "http://tika:9998"

            pipeline = Pipeline(
                scraper_name="test_scraper",
                upload_to_ragflow=True,
                upload_to_paperless=True,
                container=mock_container,
            )
            result = pipeline.run()

        # Tika should have been used for extraction
        mock_tika.extract_text.assert_called_once()
        mock_tika.extract_metadata.assert_called_once()

        # Parser backend should NOT have been called
        mock_container.parser_backend.parse_document.assert_not_called()

        assert result.parsed_count == 1
        assert result.archived_count == 1
