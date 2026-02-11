#!/usr/bin/env python3
"""Backfill pgvector from Paperless-ngx documents.

Lists all documents in Paperless, downloads markdown content,
chunks, embeds, and stores in pgvector.

Usage:
    python scripts/backfill_vectors.py [--source SOURCE] [--dry-run] [--skip-existing]

Environment:
    Reads from .env or .env.stack (set DOTENV_PATH to override).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(os.getenv("DOTENV_PATH", ".env"))
os.environ.setdefault("BASIC_AUTH_ENABLED", "true")

import requests

from app.config import Config
from app.services.embedding_client import create_embedding_client
from app.services.chunking import create_chunker
from app.backends.vectorstores.pgvector_store import PgVectorVectorStore


def _mask_database_url(url: str) -> str:
    """Mask credentials in database URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            host_part = parsed.hostname or ""
            if parsed.port:
                host_part += f":{parsed.port}"
            masked = parsed._replace(
                netloc=f"{parsed.username}:***@{host_part}"
            )
            return urlunparse(masked)
        return url
    except Exception:
        return "<unparseable>"


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters invalid in filenames."""
    sanitized = re.sub(r'[:/\\|?*"<>]', '_', name).strip()
    return sanitized if sanitized else "untitled"


def get_paperless_documents(api_url: str, token: str) -> list[dict]:
    """Fetch all documents from Paperless-ngx API."""
    documents = []
    url = f"{api_url.rstrip('/')}/api/documents/?page_size=100"

    while url:
        resp = requests.get(
            url,
            headers={"Authorization": f"Token {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        documents.extend(data.get("results", []))
        url = data.get("next")
        print(f"  Fetched {len(documents)} documents...")

    return documents


def get_document_content(api_url: str, token: str, doc_id: int) -> str:
    """Download document content as text from Paperless."""
    api_url = api_url.rstrip("/")
    # Try to get the document content (text representation)
    resp = requests.get(
        f"{api_url}/api/documents/{doc_id}/download/",
        headers={"Authorization": f"Token {token}"},
        timeout=60,
    )
    resp.raise_for_status()

    # If it's a non-text type (PDF, image, Office doc, etc.), fall back to
    # the preview or metadata endpoint for text content.
    content_type = resp.headers.get("Content-Type", "")
    if "text" not in content_type:
        # Try the preview endpoint for text content
        try:
            preview_resp = requests.get(
                f"{api_url}/api/documents/{doc_id}/preview/",
                headers={"Authorization": f"Token {token}"},
                timeout=60,
            )
            if preview_resp.ok and "text" in preview_resp.headers.get("Content-Type", ""):
                return preview_resp.text
        except requests.RequestException:
            pass  # Fall through to metadata fallback

        # Fallback: use the document's content field if available
        meta_resp = requests.get(
            f"{api_url}/api/documents/{doc_id}/",
            headers={"Authorization": f"Token {token}"},
            timeout=30,
        )
        meta_resp.raise_for_status()
        doc_meta = meta_resp.json()
        return doc_meta.get("content", "")

    return resp.text


def get_correspondents(api_url: str, token: str) -> dict[int, str]:
    """Fetch correspondent id->name mapping."""
    mapping = {}
    url = f"{api_url.rstrip('/')}/api/correspondents/?page_size=100"
    while url:
        resp = requests.get(
            url, headers={"Authorization": f"Token {token}"}, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        for c in data.get("results", []):
            if "id" in c and "name" in c:
                mapping[c["id"]] = c["name"]
        url = data.get("next")
    return mapping


def _get_existing_filenames(pgvector: PgVectorVectorStore) -> set[str]:
    """Query pgvector for all existing (source, filename) pairs."""
    existing: set[str] = set()
    try:
        pool = pgvector._get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT source || '/' || filename FROM document_chunks"
                )
                for row in cur.fetchall():
                    existing.add(row[0])
    except Exception as e:
        print(f"  WARNING: Could not query existing documents: {e}", file=sys.stderr)
    return existing


def _apply_contextual_enrichment_backfill(chunks: list, content: str) -> list[str]:
    """Apply contextual chunk enrichment via LLM for backfill."""
    try:
        from app.services.llm_client import create_llm_client
        from app.services.document_enrichment import DocumentEnrichmentService

        llm = create_llm_client(
            backend=Config.LLM_BACKEND,
            model=Config.LLM_MODEL,
            url=Config.LLM_URL or Config.EMBEDDING_URL,
            api_key=Config.LLM_API_KEY,
            timeout=Config.LLM_TIMEOUT,
        )
        if not llm.is_configured():
            print("  WARNING: LLM not configured, skipping enrichment")
            return [c.content for c in chunks]

        service = DocumentEnrichmentService(llm, max_tokens=Config.LLM_ENRICHMENT_MAX_TOKENS)
        return service.enrich_chunks(
            chunks, content, window=Config.CONTEXTUAL_ENRICHMENT_WINDOW
        )
    except Exception as e:
        print(f"  WARNING: Contextual enrichment failed, using raw content: {e}")
        return [c.content for c in chunks]


def main():
    parser = argparse.ArgumentParser(description="Backfill pgvector from Paperless-ngx")
    parser.add_argument("--source", default=None, help="Source name for pgvector partition (default: correspondent name or 'paperless')")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without storing")
    parser.add_argument("--skip-existing", action="store_true", help="Skip documents already in pgvector")
    parser.add_argument("--enrich", action="store_true", help="Enable contextual chunk enrichment via LLM")
    args = parser.parse_args()

    # Configuration — validate before using string methods
    if not Config.PAPERLESS_API_URL:
        print("ERROR: PAPERLESS_API_URL not configured")
        sys.exit(1)
    if not Config.PAPERLESS_API_TOKEN:
        print("ERROR: PAPERLESS_API_TOKEN not configured")
        sys.exit(1)
    if not Config.DATABASE_URL:
        print("ERROR: DATABASE_URL not configured")
        sys.exit(1)
    if not Config.EMBEDDING_URL:
        print("ERROR: EMBEDDING_URL not configured")
        sys.exit(1)

    if args.enrich and not Config.LLM_URL:
        print("WARNING: --enrich specified but LLM_URL not configured; falling back to EMBEDDING_URL")

    paperless_url = Config.PAPERLESS_API_URL.rstrip("/")
    paperless_token = Config.PAPERLESS_API_TOKEN
    database_url = Config.DATABASE_URL
    embedding_url = Config.EMBEDDING_URL

    print(f"Paperless: {paperless_url}")
    print(f"Database: {_mask_database_url(database_url)}")
    print(f"Embedding: {embedding_url}")
    print()

    # Initialize clients
    embedder = create_embedding_client(
        backend=Config.EMBEDDING_BACKEND,
        model=Config.EMBEDDING_MODEL,
        url=embedding_url,
        api_key=Config.EMBEDDING_API_KEY,
        dimensions=Config.EMBEDDING_DIMENSIONS,
        timeout=Config.EMBEDDING_TIMEOUT,
    )
    chunker = create_chunker(
        strategy=Config.CHUNKING_STRATEGY,
        max_tokens=Config.CHUNK_MAX_TOKENS,
        overlap_tokens=Config.CHUNK_OVERLAP_TOKENS,
    )
    pgvector = PgVectorVectorStore(
        database_url=database_url,
        dimensions=Config.EMBEDDING_DIMENSIONS,
    )

    try:
        # Test connections
        print("Testing connections...")
        if not embedder.test_connection():
            print("ERROR: Cannot connect to embedding service")
            sys.exit(1)
        if not pgvector.test_connection():
            print("ERROR: Cannot connect to PostgreSQL")
            sys.exit(1)
        print("Connections OK\n")

        # Ensure schema
        if not args.dry_run:
            pgvector.ensure_ready()

        # Fetch correspondents for source naming
        print("Fetching correspondents...")
        correspondents = get_correspondents(paperless_url, paperless_token)
        print(f"  Found {len(correspondents)} correspondents\n")

        # Fetch all documents
        print("Fetching documents from Paperless...")
        documents = get_paperless_documents(paperless_url, paperless_token)
        print(f"Total documents: {len(documents)}\n")

        # Get existing documents in pgvector for skip-existing
        existing_files: set[str] = set()
        if args.skip_existing:
            if args.dry_run:
                print("NOTE: --skip-existing ignored during --dry-run (no pgvector query)\n")
            else:
                print("Fetching existing documents from pgvector...")
                existing_files = _get_existing_filenames(pgvector)
                print(f"  Found {len(existing_files)} existing documents\n")

        # Process each document
        processed = 0
        skipped = 0
        errors = 0

        for i, doc in enumerate(documents, 1):
            doc_id = doc.get("id")
            if doc_id is None:
                print(f"[{i}/{len(documents)}] SKIP: Document missing 'id' field")
                skipped += 1
                continue
            title = doc.get("title", f"document_{doc_id}")
            correspondent_id = doc.get("correspondent")
            source = args.source or (
                correspondents.get(correspondent_id, "paperless")
                if correspondent_id
                else "paperless"
            )
            filename = f"{_sanitize_filename(title)}.md"

            print(f"[{i}/{len(documents)}] {source}/{filename}")

            # Skip if already exists
            if args.skip_existing and f"{source}/{filename}" in existing_files:
                print("  SKIP: Already exists in pgvector")
                skipped += 1
                continue

            if args.dry_run:
                print(f"  DRY RUN: Would process document {doc_id}")
                processed += 1
                continue

            try:
                # Get document content
                content = get_document_content(paperless_url, paperless_token, doc_id)
                if not content or not content.strip():
                    print("  SKIP: No text content")
                    skipped += 1
                    continue

                # Chunk
                metadata = {
                    "title": title,
                    "source": source,
                    "document_id": str(doc_id),
                    "paperless_id": doc_id,
                }
                chunks = chunker.chunk(content, metadata)
                if not chunks:
                    print("  SKIP: No chunks produced")
                    skipped += 1
                    continue

                # Optional contextual enrichment
                if args.enrich:
                    texts = _apply_contextual_enrichment_backfill(chunks, content)
                else:
                    texts = [c.content for c in chunks]

                # Embed
                embedding_result = embedder.embed(texts)

                if len(embedding_result.embeddings) != len(chunks):
                    print(
                        f"  ERROR: Embedding count mismatch: "
                        f"got {len(embedding_result.embeddings)}, expected {len(chunks)}"
                    )
                    errors += 1
                    continue

                # Prepare storage chunks
                storage_chunks = [
                    {
                        "content": chunk.content,
                        "embedding": emb,
                        "chunk_index": chunk.index,
                        "metadata": chunk.metadata,
                    }
                    for chunk, emb in zip(chunks, embedding_result.embeddings)
                ]

                # Store
                count = pgvector.store_chunks(
                    source=source,
                    filename=filename,
                    chunks=storage_chunks,
                    document_id=str(doc_id),
                )
                print(f"  OK: {count} chunks stored")
                processed += 1

            except Exception as e:
                print(f"  ERROR: {e}")
                errors += 1

        print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Errors: {errors}")

    finally:
        pgvector.close()


if __name__ == "__main__":
    main()
