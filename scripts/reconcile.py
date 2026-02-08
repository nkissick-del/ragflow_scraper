#!/usr/bin/env python3
"""
CLI for state reconciliation and disaster recovery.

Usage:
    python -m scripts.reconcile report --scraper aemo [-o json]
    python -m scripts.reconcile rebuild --scraper aemo
    python -m scripts.reconcile sync-rag --scraper aemo [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.container import get_container
from app.scrapers import ScraperRegistry
from app.utils import setup_logging, get_logger

logger = get_logger("cli.reconcile")


def handle_report(args) -> int:
    """Generate reconciliation report."""
    from app.services.reconciliation import ReconciliationService

    container = get_container()
    recon = ReconciliationService(container=container)

    try:
        report = recon.get_report(args.scraper)
    except Exception as e:
        logger.error(f"Report failed: {e}")
        if args.output_format == "json":
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}")
        return 1

    if args.output_format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"\nReconciliation Report: {report.scraper_name}")
        print("=" * 60)
        print(f"  State URLs:      {report.state_url_count}")
        print(f"  Paperless URLs:  {report.paperless_url_count}")
        print(f"  RAG Documents:   {report.rag_document_count}")
        print("-" * 60)

        if report.urls_only_in_state:
            print(f"  URLs only in state:     {len(report.urls_only_in_state)}")
        if report.urls_only_in_paperless:
            print(f"  URLs only in Paperless: {len(report.urls_only_in_paperless)}")
        if report.urls_in_paperless_not_rag:
            print(f"  Paperless not in RAG:   {len(report.urls_in_paperless_not_rag)}")

        if report.errors:
            print("-" * 60)
            print("Errors:")
            for err in report.errors:
                print(f"  - {err}")

        print("=" * 60)

    return 0


def handle_rebuild(args) -> int:
    """Rebuild state from Paperless."""
    from app.services.reconciliation import ReconciliationService

    container = get_container()
    recon = ReconciliationService(container=container)

    try:
        added = recon.rebuild_state(args.scraper)
    except Exception as e:
        logger.error(f"Rebuild failed: {e}")
        if args.output_format == "json":
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}")
        return 1

    if args.output_format == "json":
        print(json.dumps({"scraper": args.scraper, "urls_added": added}))
    else:
        print(f"State rebuilt for {args.scraper}: {added} URLs added from Paperless")

    return 0


def handle_sync_rag(args) -> int:
    """Sync RAG gaps from Paperless."""
    from app.services.reconciliation import ReconciliationService

    container = get_container()
    recon = ReconciliationService(container=container)

    try:
        re_ingested = recon.sync_rag_gaps(args.scraper, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"RAG sync failed: {e}")
        if args.output_format == "json":
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}")
        return 1

    if args.output_format == "json":
        print(json.dumps({
            "scraper": args.scraper,
            "dry_run": args.dry_run,
            "count": len(re_ingested),
            "urls": re_ingested,
        }, indent=2))
    else:
        mode = "DRY RUN" if args.dry_run else "SYNC"
        print(f"\n{mode}: {len(re_ingested)} documents for {args.scraper}")
        for url in re_ingested:
            print(f"  - {url}")

    return 0


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="State reconciliation and disaster recovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s report --scraper aemo
    %(prog)s report --scraper aemo -o json
    %(prog)s rebuild --scraper aemo
    %(prog)s sync-rag --scraper aemo --dry-run
    %(prog)s sync-rag --scraper aemo
        """,
    )

    parser.add_argument(
        "--output-format", "-o",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Report
    report_parser = subparsers.add_parser("report", help="Generate reconciliation report")
    report_parser.add_argument("--scraper", "-s", required=True, help="Scraper name")

    # Rebuild
    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild state from Paperless")
    rebuild_parser.add_argument("--scraper", "-s", required=True, help="Scraper name")

    # Sync RAG
    sync_parser = subparsers.add_parser("sync-rag", help="Re-ingest documents missing from RAG")
    sync_parser.add_argument("--scraper", "-s", required=True, help="Scraper name")
    sync_parser.add_argument("--dry-run", action="store_true", help="Only list URLs, don't re-ingest")

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging()

    # Validate scraper exists
    available = ScraperRegistry.get_scraper_names()
    if args.scraper not in available:
        print(f"Error: Unknown scraper '{args.scraper}'")
        print(f"Available: {', '.join(sorted(available))}")
        return 1

    if args.command == "report":
        return handle_report(args)
    elif args.command == "rebuild":
        return handle_rebuild(args)
    else:  # sync-rag
        return handle_sync_rag(args)


if __name__ == "__main__":
    sys.exit(main())
