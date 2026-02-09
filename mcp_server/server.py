#!/usr/bin/env python3
"""MCP server for document search.

Exposes pgvector search capabilities as MCP tools that any LLM can call.

Usage:
    uvicorn mcp_server.server:app --host 0.0.0.0 --port 8100

    Or with mcp CLI:
    mcp run mcp_server/server.py

Environment:
    DATABASE_URL - PostgreSQL connection string
    EMBEDDING_URL - Embedding service URL (Ollama or OpenAI-compatible)
    EMBEDDING_BACKEND - Backend type (ollama, openai, api)
    EMBEDDING_MODEL - Model name (default: nomic-embed-text)
    EMBEDDING_DIMENSIONS - Vector dimensions (default: 768)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path, PurePosixPath

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(os.getenv("DOTENV_PATH", ".env"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional

from mcp_server.tools import search_documents, list_sources, get_document

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Document Search MCP Server",
    description="Semantic search across indexed documents via pgvector",
    version="1.0.0",
)


class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query")
    sources: Optional[list[str]] = Field(None, description="Filter by source names")
    limit: int = Field(10, ge=1, le=50, description="Maximum results")
    metadata_filter: Optional[dict[str, Any]] = Field(None, description="JSONB containment filter")


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[dict[str, Any]]


class SourcesResponse(BaseModel):
    sources: list[dict[str, Any]]
    stats: dict[str, Any]


class DocumentResponse(BaseModel):
    source: str
    filename: str
    chunk_count: int
    chunks: list[dict[str, Any]]


@app.post("/tools/search_documents", response_model=SearchResponse)
async def api_search_documents(req: SearchRequest):
    """Search documents by semantic similarity."""
    try:
        result = await asyncio.to_thread(
            search_documents,
            query=req.query,
            sources=req.sources,
            limit=req.limit,
            metadata_filter=req.metadata_filter,
        )
        return result
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/tools/list_sources", response_model=SourcesResponse)
async def api_list_sources():
    """List available document sources."""
    try:
        return await asyncio.to_thread(list_sources)
    except Exception as e:
        logger.exception("List sources failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/tools/get_document/{source}/{filename:path}", response_model=DocumentResponse)
async def api_get_document(source: str, filename: str):
    """Get all chunks for a specific document."""
    # Validate no path traversal — normalize and reject if path escapes
    if not source or not filename:
        raise HTTPException(status_code=400, detail="Invalid source or filename")
    normalized_source = PurePosixPath(source).as_posix()
    normalized_filename = PurePosixPath(filename).as_posix()
    if (
        normalized_source != source
        or normalized_filename != filename
        or ".." in normalized_source.split("/")
        or ".." in normalized_filename.split("/")
        or "." in PurePosixPath(source).parts
        or "." in PurePosixPath(filename).parts
        or source.startswith("/")
        or filename.startswith("/")
        or "%" in source
        or "%" in filename
        or "\x00" in source
        or "\x00" in filename
    ):
        raise HTTPException(status_code=400, detail="Invalid source or filename")
    try:
        return await asyncio.to_thread(get_document, source, filename)
    except Exception as e:
        logger.exception("Get document failed")
        raise HTTPException(status_code=500, detail="Failed to retrieve document")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
