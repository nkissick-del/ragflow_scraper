#!/usr/bin/env python3
"""
Test scrape: run each news scraper with max_pages=1, dry_run=True,
capture yielded documents, and generate a Paperless mapping report.

Output: docs/scrape_report/ with one JSON + one mapping report per scraper.
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Set environment BEFORE any app imports so Config picks up local paths
local_data = Path(__file__).parent / "data"
log_dir = local_data / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

os.environ["BASIC_AUTH_ENABLED"] = "true"
os.environ["DATA_DIR"] = str(local_data)
os.environ["LOG_DIR"] = str(log_dir)

# Load .env (won't override vars we just set)
from dotenv import load_dotenv
load_dotenv()

from app.config import Config

from app.services.paperless_client import (
    CUSTOM_FIELD_MAPPING,
    build_paperless_native_fields,
    flatten_metadata_extras,
)

OUTPUT_DIR = Path("docs/scrape_report")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_scraper(scraper_cls, name, **kwargs):
    """Instantiate and run a scraper, returning (docs, result, error)."""
    # Mock the container to avoid needing all services
    mock_container = Mock()

    # State tracker must return proper values (not Mock objects)
    mock_state = {}
    mock_container.state_tracker = Mock()
    mock_container.state_tracker.is_processed.return_value = False
    mock_container.state_tracker.get_state.return_value = mock_state
    mock_container.state_tracker.get_value.return_value = None

    with patch("app.container.get_container", return_value=mock_container):
        try:
            scraper = scraper_cls(max_pages=1, dry_run=True, **kwargs)
            scraper.state_tracker = mock_container.state_tracker
            scraper.setup()
        except Exception as e:
            return [], None, f"Setup failed: {e}\n{traceback.format_exc()}"

        docs = []
        result = None
        try:
            gen = scraper.scrape()
            for doc in gen:
                docs.append(doc)
                # Just grab a handful of documents for the report
                if len(docs) >= 5:
                    break
        except StopIteration as e:
            result = e.value
        except Exception as e:
            if docs:
                # Got some docs before error — that's fine for the report
                pass
            else:
                return docs, None, f"Scrape failed: {e}\n{traceback.format_exc()}"
        finally:
            try:
                scraper.teardown()
            except Exception:
                pass

    return docs, result, None


def paperless_mapping_report(doc: dict) -> dict:
    """Show how a document's fields would map to Paperless."""
    native = build_paperless_native_fields(doc)
    native["correspondent_source"] = (
        "author" if doc.get("author") else "organization (fallback)"
    )

    report = {
        "native_fields": native,
        "custom_fields": {},
        "unmapped_fields": {},
    }

    # Custom field mapping
    flattened = flatten_metadata_extras(doc)

    for meta_key, (field_name, data_type) in CUSTOM_FIELD_MAPPING.items():
        value = flattened.get(meta_key)
        if value is not None and value != "" and value != [] and value != {}:
            report["custom_fields"][field_name] = {
                "value": value,
                "source_key": meta_key,
                "paperless_type": data_type,
            }

    # Find unmapped fields (not in native or custom mapping)
    native_keys = {"title", "publication_date", "tags", "document_type", "filename",
                   "local_path", "hash", "pdf_path", "paperless_id", "scraped_at",
                   "file_size", "file_size_str", "page_count", "extra"}
    custom_keys = set(CUSTOM_FIELD_MAPPING.keys())
    all_mapped = native_keys | custom_keys

    for key, value in doc.items():
        if key not in all_mapped and value is not None and value != "" and value != [] and value != {}:
            report["unmapped_fields"][key] = value

    return report


def write_report(f, scraper_name, docs, mapping):
    """Write human-readable report for a scraper."""
    sample_doc = docs[0]

    f.write(f"{'='*70}\n")
    f.write(f"SCRAPE REPORT: {scraper_name}\n")
    f.write(f"Generated: {datetime.now().isoformat()}\n")
    f.write(f"Documents collected: {len(docs)}\n")
    f.write(f"{'='*70}\n\n")

    for i, doc in enumerate(docs):
        doc_mapping = paperless_mapping_report(doc)

        f.write(f"DOCUMENT {i+1} of {len(docs)}\n")
        f.write(f"{'-'*70}\n\n")

        # Document metadata
        f.write("METADATA FIELDS:\n")
        for key in ["url", "title", "filename", "author", "description",
                    "organization", "document_type", "publication_date",
                    "language", "image_url", "source_page"]:
            val = doc.get(key)
            if val:
                val_str = str(val)
                if len(val_str) > 120:
                    val_str = val_str[:117] + "..."
                f.write(f"  {key:20s} = {val_str}\n")
            else:
                f.write(f"  {key:20s} = (empty)\n")

        f.write(f"\n  tags                 = {doc.get('tags', [])}\n")
        f.write(f"  keywords             = {doc.get('keywords', [])}\n")

        extra = doc.get("extra", {})
        if extra:
            f.write(f"\n  extra dict keys: {list(extra.keys())}\n")
            for k, v in extra.items():
                v_str = str(v)
                if len(v_str) > 100:
                    v_str = v_str[:97] + "..."
                f.write(f"    extra.{k:16s} = {v_str}\n")

        f.write(f"\n\nPAPERLESS FIELD MAPPING:\n")
        f.write(f"{'-'*70}\n\n")

        f.write("Native fields (set at upload time):\n")
        native = doc_mapping["native_fields"]
        for key in ["title", "created", "correspondent", "correspondent_source",
                    "document_type", "tags"]:
            val = native.get(key)
            val_str = str(val) if val else "(empty)"
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
            f.write(f"  {key:25s} = {val_str}\n")

        f.write(f"\nCustom fields (PATCH after upload):\n")
        for field_name, info in doc_mapping["custom_fields"].items():
            val_str = str(info["value"])
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            f.write(f"  {field_name:25s} = {val_str}\n")
            f.write(f"  {'':25s}   (from: {info['source_key']}, type: {info['paperless_type']})\n")

        if not doc_mapping["custom_fields"]:
            f.write("  (none)\n")

        f.write(f"\nUnmapped fields (not sent to Paperless):\n")
        for key, val in doc_mapping["unmapped_fields"].items():
            val_str = str(val)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            f.write(f"  {key:25s} = {val_str}\n")

        if not doc_mapping["unmapped_fields"]:
            f.write("  (none — all fields mapped)\n")

        # Completeness summary
        f.write(f"\n\nFIELD COMPLETENESS:\n")
        f.write(f"{'-'*70}\n")
        all_meta_fields = ["url", "title", "filename", "author", "description",
                           "organization", "document_type", "publication_date",
                           "language", "image_url", "source_page", "tags", "keywords"]
        filled = 0
        for fld in all_meta_fields:
            val = doc.get(fld)
            is_filled = bool(val) if not isinstance(val, list) else len(val) > 0
            status = "FILLED" if is_filled else "EMPTY"
            filled += 1 if is_filled else 0
            f.write(f"  {fld:20s} : {status}\n")
        f.write(f"\n  Completeness: {filled}/{len(all_meta_fields)} fields ({100*filled//len(all_meta_fields)}%)\n")
        f.write(f"\n{'='*70}\n\n")

    return filled, len(all_meta_fields)


def main():
    scrapers = [
        ("theenergy", "app.scrapers.theenergy_scraper", "TheEnergyScraper", {}),
        ("reneweconomy", "app.scrapers.reneweconomy_scraper", "RenewEconomyScraper", {}),
        ("guardian", "app.scrapers.guardian_scraper", "GuardianScraper", {}),
        ("the_conversation", "app.scrapers.the_conversation_scraper", "TheConversationScraper", {}),
    ]

    summary = {
        "generated_at": datetime.now().isoformat(),
        "scrapers": {},
    }

    for scraper_name, module_path, class_name, extra_kwargs in scrapers:
        print(f"\n{'='*60}")
        print(f"Running: {scraper_name}")
        print(f"{'='*60}")

        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
        except Exception as e:
            print(f"  IMPORT ERROR: {e}")
            summary["scrapers"][scraper_name] = {"error": str(e)}
            continue

        docs, result, error = run_scraper(cls, scraper_name, **extra_kwargs)

        if error:
            print(f"  ERROR: {error}")
            summary["scrapers"][scraper_name] = {"error": error}
            continue

        print(f"  Documents yielded: {len(docs)}")
        if result:
            print(f"  Result: scraped={result.scraped_count}, downloaded={result.downloaded_count}, failed={result.failed_count}")

        # Save raw documents
        raw_path = OUTPUT_DIR / f"{scraper_name}_documents.json"
        with open(raw_path, "w") as f:
            json.dump(docs, f, indent=2, default=str)
        print(f"  Raw output: {raw_path}")

        # Generate mapping report for first doc (if any)
        if docs:
            sample_doc = docs[0]
            mapping = paperless_mapping_report(sample_doc)

            mapping_path = OUTPUT_DIR / f"{scraper_name}_paperless_mapping.json"
            with open(mapping_path, "w") as f:
                json.dump(mapping, f, indent=2, default=str)
            print(f"  Mapping report: {mapping_path}")

            report_path = OUTPUT_DIR / f"{scraper_name}_report.txt"
            with open(report_path, "w") as f:
                filled, total = write_report(f, scraper_name, docs, mapping)
            print(f"  Human report: {report_path}")

            summary["scrapers"][scraper_name] = {
                "documents_count": len(docs),
                "sample_title": sample_doc.get("title", ""),
                "fields_filled": filled,
                "fields_total": total,
                "completeness_pct": 100 * filled // total,
            }
        else:
            summary["scrapers"][scraper_name] = {
                "documents_count": 0,
                "note": "No documents yielded",
            }

    # Save summary
    summary_path = OUTPUT_DIR / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n\nSummary: {summary_path}")
    print(f"All reports saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
