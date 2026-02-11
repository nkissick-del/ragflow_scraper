#!/usr/bin/env python3
"""Create and validate the AnythingLLM pgvector VIEW.

Creates a PostgreSQL VIEW that adapts the scraper's document_chunks table
to AnythingLLM's expected pgvector schema, enabling zero-duplication
similarity search from AnythingLLM against scraper-ingested embeddings.

Usage:
    python scripts/create_anythingllm_view.py [--validate-only] [--drop] [--dry-run]

Environment:
    Reads from .env or .env.stack (set DOTENV_PATH to override).
    Set ANYTHINGLLM_VIEW_NAME to override the default view name.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(os.getenv("DOTENV_PATH", ".env"))
os.environ.setdefault("BASIC_AUTH_ENABLED", "true")

from app.config import Config


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


EXPECTED_COLUMNS = {
    "id": "uuid",
    "namespace": "text",
    "embedding": "USER-DEFINED",
    "metadata": "jsonb",
    "created_at": "timestamp with time zone",
}


def validate_view(conn, view_name: str) -> bool:
    """Validate the VIEW exists and has the expected schema."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (view_name,),
        )
        rows = cur.fetchall()

    if not rows:
        print(f"  FAIL: VIEW '{view_name}' does not exist")
        return False

    actual = {row[0]: row[1] for row in rows}
    ok = True
    for col_name, expected_type in EXPECTED_COLUMNS.items():
        actual_type = actual.get(col_name)
        if actual_type is None:
            print(f"  FAIL: Missing column '{col_name}'")
            ok = False
        elif actual_type != expected_type:
            print(f"  FAIL: Column '{col_name}' type is '{actual_type}', expected '{expected_type}'")
            ok = False
        else:
            print(f"  OK: {col_name} ({actual_type})")

    return ok


def list_namespaces(conn, view_name: str) -> None:
    """List available namespaces (sources) with chunk counts."""
    from psycopg import sql

    with conn.cursor() as cur:
        cur.execute(sql.SQL("""
            SELECT namespace, COUNT(*) as chunk_count
            FROM {}
            GROUP BY namespace
            ORDER BY namespace
        """).format(sql.Identifier(view_name)))
        rows = cur.fetchall()

    if not rows:
        print("\n  No data in VIEW (document_chunks table is empty)")
        return

    print(f"\n  Available namespaces ({len(rows)}):")
    for ns, count in rows:
        print(f"    {ns}: {count} chunks")


def print_anythingllm_instructions(database_url: str, view_name: str) -> None:
    """Print configuration instructions for AnythingLLM."""
    masked_url = _mask_database_url(database_url)
    print("\n--- AnythingLLM Configuration ---")
    print("Set these environment variables in your AnythingLLM instance:")
    print("  VECTOR_DB=pgvector")
    print(f"  PGVECTOR_CONNECTION_STRING={masked_url}")
    print(f"  PGVECTOR_TABLE_NAME={view_name}")
    print()
    print("NOTE: Connection string shown with masked credentials.")
    print()
    print("Then create workspaces in AnythingLLM matching your scraper source names.")
    print("AnythingLLM will query the VIEW automatically for similarity search.")


def main():
    parser = argparse.ArgumentParser(
        description="Create/validate AnythingLLM pgvector VIEW"
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Only validate the VIEW exists with correct schema"
    )
    parser.add_argument(
        "--drop", action="store_true",
        help="Drop the VIEW instead of creating it"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without executing"
    )
    args = parser.parse_args()

    database_url = Config.DATABASE_URL
    if not database_url:
        print("ERROR: DATABASE_URL not configured")
        sys.exit(1)

    view_name = Config.ANYTHINGLLM_VIEW_NAME
    print(f"Database: {_mask_database_url(database_url)}")
    print(f"VIEW name: {view_name}")
    print()

    import psycopg
    from psycopg import sql

    try:
        conn = psycopg.connect(database_url, autocommit=True)
    except Exception as e:
        print(f"ERROR: Cannot connect to PostgreSQL: {e}")
        sys.exit(1)

    try:
        if args.drop:
            if args.dry_run:
                print(f"DRY RUN: Would drop VIEW '{view_name}'")
            else:
                print(f"Dropping VIEW '{view_name}'...")
                with conn.cursor() as cur:
                    cur.execute(sql.SQL("DROP VIEW IF EXISTS {}").format(
                        sql.Identifier(view_name)
                    ))
                print("  Done.")
            return

        if args.validate_only:
            print("Validating VIEW schema...")
            ok = validate_view(conn, view_name)
            if ok:
                list_namespaces(conn, view_name)
                print_anythingllm_instructions(database_url, view_name)
            sys.exit(0 if ok else 1)

        # Create the VIEW
        if args.dry_run:
            print("DRY RUN: Would create/replace VIEW with SQL:")
            print(f"  CREATE OR REPLACE VIEW {view_name} AS ...")
            return

        print("Creating VIEW...")
        from app.services.pgvector_client import PgVectorClient

        client = PgVectorClient(database_url=database_url, view_name=view_name)
        try:
            client.ensure_schema()
        finally:
            client.close()

        print("  VIEW created via ensure_schema().")
        print()

        # Validate
        print("Validating VIEW schema...")
        ok = validate_view(conn, view_name)
        if ok:
            list_namespaces(conn, view_name)
            print_anythingllm_instructions(database_url, view_name)
        else:
            print("\nVIEW validation failed!")
            sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
