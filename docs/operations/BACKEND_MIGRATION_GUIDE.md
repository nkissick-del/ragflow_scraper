# Backend Migration Guide

**Version:** 2.0
**Date:** 2026-02-05

## Overview

The PDF Scraper now supports modular backends for parsing, archiving, and RAG indexing. This guide explains how to configure and switch between different backends.

## Quick Start

### Default Configuration (No Changes Required)

The system works out of the box with these defaults:

```bash
PARSER_BACKEND=docling          # PDF parsing
ARCHIVE_BACKEND=paperless       # Document archiving
RAG_BACKEND=ragflow             # Vector indexing
METADATA_MERGE_STRATEGY=smart   # Metadata merging
```

**No action required** if you're using RAGFlow and don't need Paperless archiving.

### Enable Paperless Archiving

Add to your `.env` file:

```bash
# Paperless-ngx Configuration
PAPERLESS_API_URL=http://localhost:8000
PAPERLESS_API_TOKEN=your_paperless_token_here
```

Run scraper:

```bash
make dev-up
docker exec scraper-app python -m scripts.run_scraper --scraper aemo
```

Documents will be:
1. Parsed to Markdown
2. Archived to Paperless (original PDF)
3. Verified in Paperless
4. Indexed in RAGFlow (Markdown)
5. Deleted from local storage (after verification)

### Switch to AnythingLLM

Change RAG backend in `.env`:

```bash
# Switch from RAGFlow to AnythingLLM
RAG_BACKEND=anythingllm
ANYTHINGLLM_API_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=your_api_key_here
ANYTHINGLLM_WORKSPACE_ID=your_workspace_id
```

Restart:

```bash
make dev-restart
```

**Note:** AnythingLLM backend is currently a stub. Contributions welcome!

## Backend Options

### Parser Backends

| Backend   | Status          | Description                  |
|-----------|-----------------|------------------------------|
| `docling` | ✅ Implemented  | IBM Docling (recommended)    |
| `mineru`  | 🚧 Stub         | MinerU parser                |
| `tika`    | 🚧 Stub         | Apache Tika                  |

**To switch:**

```bash
PARSER_BACKEND=docling  # or mineru, tika
```

### Archive Backends

| Backend     | Status          | Description                    |
|-------------|-----------------|--------------------------------|
| `paperless` | ✅ Implemented  | Paperless-ngx (recommended)    |
| `s3`        | 🚧 Stub         | AWS S3 storage                 |
| `local`     | 🚧 Stub         | Local filesystem               |

**To switch:**

```bash
ARCHIVE_BACKEND=paperless  # or s3, local
```

### RAG Backends

| Backend       | Status          | Description                    |
|---------------|-----------------|--------------------------------|
| `ragflow`     | ✅ Implemented  | RAGFlow (default)              |
| `anythingllm` | 🚧 Stub         | AnythingLLM                    |

**To switch:**

```bash
RAG_BACKEND=ragflow  # or anythingllm
```

## Metadata Merge Strategies

### Smart Strategy (Default)

**Best for:** Most use cases

```bash
METADATA_MERGE_STRATEGY=smart
```

**Behavior:**
- Context (URL, date, org) from **scraper**
- Content (title, author) from **parser**

**Example:**

```python
# Input:
scraper_meta = {"url": "https://...", "title": "ViewDocument.aspx", "organization": "AEMO"}
parser_meta = {"title": "Annual Report 2024", "author": "John Smith"}

# Output (merged):
{
    "url": "https://...",           # From scraper
    "title": "Annual Report 2024",  # From parser (better!)
    "organization": "AEMO",         # From scraper
    "extra": {"author": "John Smith"}  # From parser
}
```

### Parser Wins Strategy

**Best for:** Trusting parser metadata over scraper

```bash
METADATA_MERGE_STRATEGY=parser_wins
```

**Behavior:** Parser overwrites all matching fields

### Scraper Wins Strategy

**Best for:** Trusting scraper metadata, adding parser details

```bash
METADATA_MERGE_STRATEGY=scraper_wins
```

**Behavior:** Keep scraper metadata, only add new fields from parser

## Troubleshooting

### Problem: ValueError - Invalid backend name

```
ValueError: Invalid PARSER_BACKEND 'doclin'. Must be one of: docling, mineru, tika
```

**Solution:** Fix typo in `.env` file. Valid names are case-sensitive.

### Problem: Parser backend not available

```
ValueError: Parser backend 'docling' not available (check dependencies)
```

**Solution:** Install missing dependency:

```bash
docker exec scraper-app pip install docling
# Or rebuild container:
make dev-build
make dev-up
```

### Problem: Paperless verification timeout

```
WARNING: Document verification timed out after 60s for task abc123
```

**Solution:**

1. Check Paperless is running:
   ```bash
   curl http://localhost:8000/api/
   ```

2. Check Paperless logs:
   ```bash
   docker logs paperless-ngx
   ```

3. Increase timeout (future enhancement - not yet configurable)

### Problem: RAG ingestion failed

```
ERROR: RAG ingestion failed: Connection refused
```

**Solution:**

1. Check RAG service is running:
   ```bash
   curl http://localhost:9380/api/
   ```

2. Verify API key is correct in `.env`

3. Check logs:
   ```bash
   make logs | grep -i rag
   ```

**Note:** RAG failures are non-fatal. The document was still archived to Paperless.

## Configuration Reference

### Complete .env Example

```bash
# Backend Selection
PARSER_BACKEND=docling
ARCHIVE_BACKEND=paperless
RAG_BACKEND=ragflow
METADATA_MERGE_STRATEGY=smart

# Paperless-ngx
PAPERLESS_API_URL=http://localhost:8000
PAPERLESS_API_TOKEN=your_paperless_token_here

# RAGFlow
RAGFLOW_API_URL=http://localhost:9380
RAGFLOW_API_KEY=your_ragflow_key_here
RAGFLOW_DATASET_ID=your_dataset_id

# AnythingLLM (optional)
ANYTHINGLLM_API_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=your_anythingllm_key_here
ANYTHINGLLM_WORKSPACE_ID=your_workspace_id
```

## Migration from v1.x

### No Breaking Changes

The modular architecture is **100% backward compatible**. Default ENV vars maintain v1.x behavior:

- Scrapers download PDFs (unchanged)
- Documents uploaded to RAGFlow (if configured)
- No parsing step (unless Docling is installed)
- No archiving (unless Paperless is configured)

### Opt-In Features

To enable new features:

1. **PDF Parsing:** Install Docling (`PARSER_BACKEND=docling`)
2. **Paperless Archiving:** Add Paperless credentials
3. **Metadata Merge:** Keep default `METADATA_MERGE_STRATEGY=smart`

### Testing Your Migration

```bash
# 1. Update .env file
cp .env.example .env
# Edit .env with your credentials

# 2. Rebuild and start
make dev-build
make dev-up

# 3. Run a test scraper
docker exec scraper-app python -m scripts.run_scraper --scraper aemo --dry-run

# 4. Check logs
make logs | tail -100

# 5. Verify Paperless has documents
curl -H "Authorization: Token $PAPERLESS_API_TOKEN" \
  http://localhost:8000/api/documents/

# 6. Verify RAGFlow has documents
# (Use RAGFlow web UI or API)
```

## Advanced Configuration

### Custom Filename Templates (Future)

**Not yet implemented** - would allow:

```bash
# Year/Month folders
FILENAME_TEMPLATE="{{ year }}/{{ month }}/{{ org }}_{{ title }}{{ extension }}"

# Include document type
FILENAME_TEMPLATE="{{ date_prefix }}_{{ org }}_{{ document_type }}_{{ title }}{{ extension }}"
```

Current implementation uses hardcoded default template.

### Multiple Archive Backends (Future)

**Not yet implemented** - would allow archiving to multiple destinations:

```bash
ARCHIVE_BACKENDS=paperless,s3
```

### Backend-Specific Configuration (Future)

**Not yet implemented** - would allow per-backend settings:

```bash
DOCLING_TIMEOUT=300
DOCLING_MODEL=advanced
PAPERLESS_VERIFY_TIMEOUT=120
```

## Getting Help

1. **Documentation:**
   - [Modular Pipeline Implementation](plans/modular_pipeline_implementation.md)
   - [Developer Guide](development/DEVELOPER_GUIDE.md)
   - [Troubleshooting](operations/troubleshooting/ragflow_scraper_audit.md)

2. **Logs:**
   ```bash
   make logs
   make logs | grep -i error
   ```

3. **GitHub Issues:**
   - Report bugs: https://github.com/your-repo/issues
   - Request features: Use "enhancement" label

4. **Community:**
   - Discussions: https://github.com/your-repo/discussions

---

**Last Updated:** 2026-02-05
**For:** PDF Scraper v2.0
