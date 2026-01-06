#!/usr/bin/env python3
"""
CLI interface for running scrapers.

Designed to be n8n-compatible with JSON output and proper exit codes.

Exit codes:
    0 - Success
    1 - Failure
    2 - Partial success (some documents failed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import Config
from app.container import get_container
from app.scrapers import ScraperRegistry
from app.scrapers.base_scraper import DocumentMetadata
from app.utils import setup_logging, get_logger
from typing import Optional

logger = get_logger("cli")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run PDF scrapers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s --list-scrapers
    %(prog)s --scraper aemo
    %(prog)s --scraper aemo --max-pages 5
    %(prog)s --scraper aemo --output-format json
    %(prog)s --scraper aemo --dry-run
        """,
    )

    # Scraper selection
    parser.add_argument(
        "--scraper", "-s",
        type=str,
        help="Name of the scraper to run",
    )
    parser.add_argument(
        "--list-scrapers", "-l",
        action="store_true",
        help="List all available scrapers",
    )

    # Scraper options
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to scrape (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't download files, just log what would be done",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force redownload of already processed URLs",
    )

    # RAGFlow options
    parser.add_argument(
        "--upload-to-ragflow",
        action="store_true",
        help="Upload scraped documents to RAGFlow",
    )
    parser.add_argument(
        "--dataset-id",
        type=str,
        help="RAGFlow dataset ID for upload",
    )

    # Output options
    parser.add_argument(
        "--output-format", "-o",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output (only show final result)",
    )

    return parser.parse_args()


def load_metadata_sidecar(filepath: Path) -> Optional[DocumentMetadata]:
    """
    Load metadata sidecar JSON for a file.

    Searches in: /app/data/metadata/{scraper_name}/{filename}.json

    Args:
        filepath: Path to the scraped file

    Returns:
        DocumentMetadata object or None if not found
    """
    # Determine scraper name from filepath
    # Expected: /app/data/scraped/{scraper_name}/{filename}.pdf
    # Metadata: /app/data/metadata/{scraper_name}/{filename}.json

    scraper_name = filepath.parent.name
    metadata_file = Config.METADATA_DIR / scraper_name / f"{filepath.stem}.json"

    if not metadata_file.exists():
        return None

    try:
        with open(metadata_file, "r") as f:
            data = json.load(f)
        return DocumentMetadata(**data)
    except Exception as e:
        logger.error(f"Failed to load metadata from {metadata_file}: {e}")
        return None


def upload_to_ragflow(
    scraper_name: str,
    downloaded_files: list[Path],
    dataset_id: str | None = None,
    output_format: str = "text",
) -> dict:
    """
    Upload downloaded files to RAGFlow.

    Args:
        scraper_name: Name of the scraper (used for auto-create dataset)
        downloaded_files: List of file paths to upload
        dataset_id: Explicit dataset ID (overrides settings)
        output_format: Output format for logging

    Returns:
        Dict with upload statistics
    """
    container = get_container()
    settings = container.get_settings_manager()

    # Get scraper class to access default settings
    scraper_class = ScraperRegistry.get_scraper_class(scraper_name)
    scraper_defaults = {
        "default_chunk_method": getattr(scraper_class, 'default_chunk_method', 'naive'),
        "default_parser": getattr(scraper_class, 'default_parser', 'DeepDOC'),
    }
    ragflow_settings = settings.get_scraper_ragflow_settings(scraper_name, scraper_defaults)

    # Determine dataset ID (CLI arg > per-scraper > global default)
    target_dataset_id = dataset_id or ragflow_settings.get("dataset_id")

    # Initialize RAGFlow client
    client = container.get_ragflow_client()

    if not client.test_connection():
        logger.error("RAGFlow connection failed")
        return {"success": False, "error": "RAGFlow connection failed"}

    # Resolve or create dataset if needed
    # Use display_name for human-readable dataset names (e.g., "Australian Energy Market Operator")
    dataset_name = getattr(scraper_class, 'display_name', scraper_name)

    if not target_dataset_id and ragflow_settings.get("auto_create_dataset", True):
        # First, check if dataset already exists in RAGFlow
        logger.info(f"Checking for existing dataset: {dataset_name}")
        existing_id = client.find_dataset_by_name(dataset_name)

        if existing_id:
            # Found existing dataset - use it
            target_dataset_id = existing_id
            logger.info(f"Using existing dataset: {dataset_name} (ID: {target_dataset_id})")
        else:
            # Create new dataset based on ingestion mode
            ingestion_mode = ragflow_settings.get("ingestion_mode", "builtin")
            logger.info(f"Auto-creating dataset: {dataset_name} (mode: {ingestion_mode})")

            if ingestion_mode == "custom":
                # Custom pipeline mode
                pipeline_id = ragflow_settings.get("pipeline_id")
                if not pipeline_id:
                    logger.error("Custom ingestion mode selected but no pipeline configured")
                    return {"success": False, "error": "No pipeline configured for custom mode"}

                target_dataset_id = client.create_dataset(
                    name=dataset_name,
                    description=f"Documents from {dataset_name}",
                    pipeline_id=pipeline_id,
                )
            else:
                # Built-in mode - use chunk_method, pdf_parser, and embedding_model
                embedding_model = ragflow_settings.get("embedding_model") or None
                chunk_method = ragflow_settings.get("chunk_method", "naive")
                pdf_parser = ragflow_settings.get("pdf_parser", "DeepDOC")

                # Build parser_config with layout_recognize
                parser_config = {"layout_recognize": pdf_parser}

                target_dataset_id = client.create_dataset(
                    name=dataset_name,
                    description=f"Documents from {dataset_name}",
                    embedding_model=embedding_model,
                    chunk_method=chunk_method,
                    parser_config=parser_config,
                )

            if not target_dataset_id:
                logger.error("Failed to auto-create dataset")
                return {"success": False, "error": "Failed to auto-create dataset"}

            logger.info(f"Created dataset: {dataset_name} (ID: {target_dataset_id})")

        # Save the dataset ID to settings (whether found or created)
        settings.set_scraper_ragflow_settings(scraper_name, {
            "dataset_id": target_dataset_id
        })
        logger.info(f"Saved dataset ID to settings for scraper: {scraper_name}")

    if not target_dataset_id:
        logger.error("No dataset ID configured and auto-create is disabled")
        return {"success": False, "error": "No dataset ID configured"}

    # Filter to only uploadable files (PDF, etc.)
    uploadable_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls"}
    files_to_upload = [
        f for f in downloaded_files
        if f.suffix.lower() in uploadable_extensions and f.exists()
    ]

    if not files_to_upload:
        logger.warning("No uploadable files found")
        return {"success": True, "uploaded": 0, "failed": 0}

    # Build documents with metadata from sidecar files
    docs_with_metadata = []
    for filepath in files_to_upload:
        metadata = load_metadata_sidecar(filepath)
        if metadata:
            docs_with_metadata.append({"filepath": filepath, "metadata": metadata})
        else:
            logger.warning(f"No metadata sidecar found for {filepath.name}, uploading without metadata")
            docs_with_metadata.append({"filepath": filepath, "metadata": None})

    # Upload documents with metadata
    logger.info(f"Uploading {len(docs_with_metadata)} files to RAGFlow dataset {target_dataset_id}")
    results = client.upload_documents_with_metadata(
        dataset_id=target_dataset_id,
        docs=docs_with_metadata,
        check_duplicates=Config.RAGFLOW_CHECK_DUPLICATES,
        wait_timeout=Config.RAGFLOW_METADATA_TIMEOUT,
        poll_interval=Config.RAGFLOW_METADATA_POLL_INTERVAL,
    )

    uploaded = sum(1 for r in results if r.success and not r.skipped_duplicate)
    skipped = sum(1 for r in results if r.skipped_duplicate)
    metadata_pushed = sum(1 for r in results if r.metadata_pushed)
    failed = sum(1 for r in results if not r.success)

    # Trigger parsing if configured
    if uploaded > 0 and ragflow_settings.get("wait_for_parsing", False):
        logger.info("Triggering document parsing...")
        document_ids = [r.document_id for r in results if r.success and r.document_id]
        if document_ids:
            client.trigger_parsing(target_dataset_id, document_ids)

    if output_format != "json":
        print("-" * 60)
        print(f"RAGFlow Upload: {uploaded} uploaded, {skipped} skipped (duplicates), {failed} failed")
        print(f"Metadata: {metadata_pushed} documents with metadata pushed")

    return {
        "success": True,
        "dataset_id": target_dataset_id,
        "uploaded": uploaded,
        "skipped": skipped,
        "metadata_pushed": metadata_pushed,
        "failed": failed,
        "errors": [r.error for r in results if not r.success and r.error],
    }


def list_scrapers(output_format: str):
    """List all available scrapers."""
    scrapers = ScraperRegistry.list_scrapers()

    if output_format == "json":
        print(json.dumps({"scrapers": scrapers}, indent=2))
    else:
        if not scrapers:
            print("No scrapers found.")
            return

        print("\nAvailable scrapers:")
        print("-" * 60)
        for scraper in scrapers:
            print(f"  {scraper['name']:<20} {scraper['description']}")
        print()


def run_scraper(args):
    """Run the specified scraper."""
    # Get the scraper
    scraper = ScraperRegistry.get_scraper(
        args.scraper,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
        force_redownload=args.force,
    )

    if scraper is None:
        error = {"error": f"Scraper not found: {args.scraper}"}
        if args.output_format == "json":
            print(json.dumps(error))
        else:
            print(f"Error: {error['error']}")
            print("Use --list-scrapers to see available scrapers.")
        return 1

    # Run the scraper
    result = scraper.run()

    # Handle RAGFlow upload if requested or auto-upload enabled
    settings = get_settings()
    ragflow_settings = settings.get_section("ragflow")
    should_upload = args.upload_to_ragflow or ragflow_settings.get("auto_upload", False)

    if should_upload and result.downloaded_count > 0 and not args.dry_run:
        # Get list of downloaded files from the scraper's output directory
        scraper_dir = Config.DOWNLOAD_DIR / args.scraper
        if scraper_dir.exists():
            downloaded_files = list(scraper_dir.iterdir())
            upload_result = upload_to_ragflow(
                scraper_name=args.scraper,
                downloaded_files=downloaded_files,
                dataset_id=args.dataset_id,
                output_format=args.output_format,
            )

            if not upload_result.get("success"):
                if args.output_format != "json":
                    print(f"RAGFlow upload error: {upload_result.get('error')}")

    # Output results
    if args.output_format == "json":
        print(result.to_json())
    else:
        print("\n" + "=" * 60)
        print(f"Scraper: {result.scraper}")
        print(f"Status: {result.status}")
        print(f"Duration: {result.duration_seconds:.1f} seconds")
        print("-" * 60)
        print(f"  Scraped:    {result.scraped_count}")
        print(f"  Downloaded: {result.downloaded_count}")
        print(f"  Excluded:   {result.excluded_count}")
        print(f"  Skipped:    {result.skipped_count}")
        print(f"  Failed:     {result.failed_count}")
        if result.excluded:
            print("-" * 60)
            print("Excluded documents:")
            for exc in result.excluded[:10]:  # Show first 10 excluded
                print(f"  [{exc['reason']}] {exc['title'][:50]}...")
            if len(result.excluded) > 10:
                print(f"  ... and {len(result.excluded) - 10} more excluded")
        if result.errors:
            print("-" * 60)
            print("Errors:")
            for error in result.errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more errors")
        print("=" * 60 + "\n")

    # Return appropriate exit code
    if result.status == "completed":
        return 0
    elif result.status == "partial":
        return 2
    else:
        return 1


def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    log_level = "WARNING" if args.quiet else Config.LOG_LEVEL
    setup_logging(level=log_level)

    # Handle list scrapers
    if args.list_scrapers:
        list_scrapers(args.output_format)
        return 0

    # Validate scraper argument
    if not args.scraper:
        print("Error: --scraper is required unless using --list-scrapers")
        print("Use --help for usage information.")
        return 1

    # Run the scraper
    return run_scraper(args)


if __name__ == "__main__":
    sys.exit(main())
