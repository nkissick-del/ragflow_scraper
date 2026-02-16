"""Initial schema baseline.

Revision ID: 001
Revises: None
Create Date: 2026-02-16

Captures existing schema: scraper_state, processed_urls,
scraper_jobs.
Uses IF NOT EXISTS for safe application to existing databases.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # scraper_state — key-value state per scraper
    op.execute("""
        CREATE TABLE IF NOT EXISTS scraper_state (
            id SERIAL PRIMARY KEY,
            scraper_name TEXT NOT NULL,
            key TEXT NOT NULL,
            value JSONB DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (scraper_name, key)
        )
    """)

    # processed_urls — URL tracking per scraper
    op.execute("""
        CREATE TABLE IF NOT EXISTS processed_urls (
            id SERIAL PRIMARY KEY,
            scraper_name TEXT NOT NULL,
            url TEXT NOT NULL,
            status TEXT DEFAULT 'downloaded',
            metadata JSONB DEFAULT '{}'::jsonb,
            processed_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (scraper_name, url)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_processed_urls_scraper
        ON processed_urls (scraper_name)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_processed_urls_status
        ON processed_urls (scraper_name, status)
    """)

    # scraper_jobs — job queue for async scraping
    op.execute("""
        CREATE TABLE IF NOT EXISTS scraper_jobs (
            id TEXT PRIMARY KEY,
            scraper_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            config JSONB DEFAULT '{}'::jsonb,
            result JSONB,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_scraper_jobs_status
        ON scraper_jobs (status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraper_jobs")
    op.execute("DROP TABLE IF EXISTS processed_urls")
    op.execute("DROP TABLE IF EXISTS scraper_state")
