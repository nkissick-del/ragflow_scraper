#!/usr/bin/env python3
"""
Test script for RAGFlow connection and basic operations.

Usage:
    python scripts/test_ragflow.py
    python scripts/test_ragflow.py --url http://localhost:9380 --key your_api_key
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services import RAGFlowClient
from app.utils import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Test RAGFlow connection",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="RAGFlow API URL (overrides env)",
    )
    parser.add_argument(
        "--key",
        type=str,
        help="RAGFlow API key (overrides env)",
    )
    parser.add_argument(
        "--create-test-dataset",
        action="store_true",
        help="Create a test dataset",
    )
    parser.add_argument(
        "--dataset-id",
        type=str,
        help="Dataset ID to test with",
    )
    parser.add_argument(
        "--upload",
        type=str,
        help="Path to a PDF file to test upload",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    setup_logging(level="INFO")

    print("\n" + "=" * 60)
    print("RAGFlow Connection Test")
    print("=" * 60 + "\n")

    # Initialize client
    client = RAGFlowClient(
        api_url=args.url,
        api_key=args.key,
    )

    print(f"API URL: {client.api_url}")
    print(f"API Key: {'*' * 8}...{client.api_key[-4:] if client.api_key else 'NOT SET'}")
    print()

    # Test connection
    print("Testing connection...")
    if not client.test_connection():
        print("\n❌ Connection failed!")
        print("Please check:")
        print("  1. RAGFlow is running and accessible")
        print("  2. API URL is correct")
        print("  3. API key is valid")
        return 1

    print("✅ Connection successful!\n")

    # List datasets
    print("Listing datasets...")
    datasets = client.list_datasets()
    if datasets:
        print(f"Found {len(datasets)} dataset(s):")
        for ds in datasets:
            print(f"  - {ds.name} (ID: {ds.id}, docs: {ds.document_count})")
    else:
        print("No datasets found.")
    print()

    # Create test dataset if requested
    if args.create_test_dataset:
        print("Creating test dataset...")
        dataset_id = client.create_dataset(
            name="scraper-test-dataset",
            description="Test dataset created by PDF scraper",
        )
        if dataset_id:
            print(f"✅ Created dataset: {dataset_id}")
        else:
            print("❌ Failed to create dataset")
        print()

    # Test upload if requested
    if args.upload and args.dataset_id:
        file_path = Path(args.upload)
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
        else:
            print(f"Uploading {file_path.name} to dataset {args.dataset_id}...")
            result = client.upload_document(args.dataset_id, file_path)
            if result.success:
                print(f"✅ Upload successful! Document ID: {result.document_id}")

                # Trigger parsing
                print("Triggering parsing...")
                if client.trigger_parsing(args.dataset_id, [result.document_id]):
                    print("✅ Parsing triggered!")

                    # Check status
                    print("Checking parsing status...")
                    status = client.get_parsing_status(args.dataset_id)
                    print(f"Status: {status}")
            else:
                print(f"❌ Upload failed: {result.error}")
        print()

    print("=" * 60)
    print("Test complete!")
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
