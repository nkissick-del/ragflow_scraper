# Migration and State Repair Guide

This guide covers managing scraper state files, metadata, and recovery procedures.

---

## Table of Contents

1. [State File Schema](#state-file-schema)
2. [State Operations](#state-operations)
3. [Metadata Management](#metadata-management)
4. [Common Scenarios](#common-scenarios)
5. [Troubleshooting](#troubleshooting)

---

## State File Schema

### Location

State files are stored in `data/state/{scraper_name}_state.json`

**Example paths:**
```
data/state/aemo_state.json
data/state/guardian_state.json
data/state/reneweconomy_state.json
```

### Schema Structure

```json
{
  "scraper_name": "aemo",
  "created_at": "2026-01-01T00:00:00.000000",
  "last_updated": "2026-01-08T12:00:00.000000",
  "processed_urls": {
    "https://example.com/doc1.pdf": {
      "title": "Document Title",
      "processed_at": "2026-01-08T11:30:00.000000",
      "file_hash": "abc123...",
      "status": "completed"
    }
  },
  "statistics": {
    "total_processed": 42,
    "total_downloaded": 40,
    "total_skipped": 2,
    "total_failed": 0
  }
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scraper_name` | string | Yes | Name of the scraper (matches class NAME) |
| `created_at` | ISO datetime | Yes | Timestamp when state was first created |
| `last_updated` | ISO datetime | Yes | Timestamp of last state update |
| `processed_urls` | object | Yes | Map of URL → processing metadata |
| `statistics` | object | Yes | Aggregate statistics |

**processed_urls entry:**
| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title |
| `processed_at` | ISO datetime | When document was processed |
| `file_hash` | string | SHA256 hash of downloaded file |
| `status` | string | "completed", "failed", "skipped" |

**statistics object:**
| Field | Type | Description |
|-------|------|-------------|
| `total_processed` | int | Total documents attempted |
| `total_downloaded` | int | Successfully downloaded |
| `total_skipped` | int | Skipped (duplicates, exclusions) |
| `total_failed` | int | Failed downloads/processing |

### State File Example

```json
{
  "scraper_name": "guardian",
  "created_at": "2026-01-01T10:00:00.000000",
  "last_updated": "2026-01-08T14:30:22.123456",
  "processed_urls": {
    "https://www.theguardian.com/energy/article1": {
      "title": "Australia's renewable energy targets",
      "processed_at": "2026-01-08T14:29:10.000000",
      "file_hash": "3a7bd3e2360a3d29eea436fcfb7e44c3",
      "status": "completed"
    },
    "https://www.theguardian.com/energy/article2": {
      "title": "Coal phase-out timeline",
      "processed_at": "2026-01-08T14:30:15.000000",
      "file_hash": "8f14e45fceea167a5a36dedd4bea2543",
      "status": "completed"
    }
  },
  "statistics": {
    "total_processed": 15,
    "total_downloaded": 14,
    "total_skipped": 1,
    "total_failed": 0
  }
}
```

---

## State Operations

### View Current State

**Via command line:**
```bash
# Pretty print state file
cat data/state/aemo_state.json | jq .

# View specific fields
cat data/state/aemo_state.json | jq '.statistics'
cat data/state/aemo_state.json | jq '.last_updated'
```

**Via container:**
```bash
docker compose exec scraper cat /app/data/state/aemo_state.json | jq .
```

### Reset Scraper State

**Use case:** Start scraper from scratch, ignore previous runs

**Method 1: Delete state file**
```bash
# Backup first
cp data/state/aemo_state.json data/state/aemo_state.json.backup

# Delete state
rm data/state/aemo_state.json

# Restart scraper - will create fresh state
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo
```

**Method 2: Use --force flag**
```bash
# Ignores state, scrapes all
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo --force
```

**Note:** `--force` doesn't delete state, just ignores it during run.

### Export State (Backup)

**Single scraper:**
```bash
cp data/state/aemo_state.json /path/to/backup/
```

**All scrapers:**
```bash
tar -czf state-backup-$(date +%Y%m%d).tar.gz data/state/
```

**With timestamp:**
```bash
cp data/state/aemo_state.json \
   data/state/aemo_state.json.$(date +%Y%m%d-%H%M%S)
```

### Import State (Restore)

**From backup:**
```bash
# Stop scraper
docker compose stop scraper

# Restore state
cp /path/to/backup/aemo_state.json data/state/

# Verify JSON validity
cat data/state/aemo_state.json | jq . > /dev/null

# Restart scraper
docker compose start scraper
```

**Verify restoration:**
```bash
# Check last_updated timestamp
cat data/state/aemo_state.json | jq '.last_updated'

# Check statistics
cat data/state/aemo_state.json | jq '.statistics'
```

### Migrate State Schema

**Use case:** Scraper state schema changed in new version

**Example migration script** (create `scripts/migrate_state.py`):
```python
#!/usr/bin/env python3
"""Migrate state files to new schema."""
import json
from pathlib import Path

def migrate_v1_to_v2(state_data):
    """Migrate from v1 to v2 schema."""
    # Add new fields if missing
    if 'version' not in state_data:
        state_data['version'] = 2
    
    if 'processed_urls' not in state_data:
        state_data['processed_urls'] = {}
    
    # Migrate old format
    if 'processed_documents' in state_data:
        for doc in state_data['processed_documents']:
            state_data['processed_urls'][doc['url']] = {
                'title': doc.get('title', 'Unknown'),
                'processed_at': doc['timestamp'],
                'file_hash': doc.get('hash', ''),
                'status': 'completed'
            }
        del state_data['processed_documents']
    
    return state_data

def migrate_state_file(filepath):
    """Migrate a single state file with safe atomic operations."""
    import os
    print(f"Migrating {filepath}...")
    
    try:
        # Load original
        with open(filepath, 'r') as f:
            state = json.load(f)
        
        migrated = migrate_v1_to_v2(state)
        
        # Write to temporary file first
        temp_path = filepath.with_suffix('.json.tmp')
        with open(temp_path, 'w') as f:
            json.dump(migrated, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Ensure durability
        
        # Atomically replace original with migrated
        os.replace(temp_path, filepath)
        
        # Create backup with rotation if needed
        backup_path = filepath.with_suffix('.json.backup')
        if backup_path.exists():
            counter = 1
            while backup_path.with_stem(f"{filepath.stem}.backup.{counter}").exists():
                counter += 1
            backup_path = backup_path.with_stem(f"{filepath.stem}.backup.{counter}")
        
        print(f"✓ Migrated {filepath}")
        print(f"  Backup: {backup_path}")
    
    except Exception as e:
        # Clean up temp file if it exists
        temp_path = filepath.with_suffix('.json.tmp')
        if temp_path.exists():
            temp_path.unlink()
        print(f"✗ Migration failed for {filepath}: {e}")
        raise

if __name__ == '__main__':
    state_dir = Path('data/state')
    for state_file in state_dir.glob('*_state.json'):
        migrate_state_file(state_file)
```

**Run migration:**
```bash
# Stop scrapers
docker compose stop scraper

# Run migration
python scripts/migrate_state.py

# Verify results
for file in data/state/*_state.json; do
    echo "Checking $file"
    cat "$file" | jq . > /dev/null && echo "✓ Valid"
done

# Restart scrapers
docker compose start scraper
```

### Manual State Repair

**Fix corrupted JSON:**
```bash
# 1. Validate JSON
cat data/state/broken_state.json | jq .
# Error: parse error

# 2. Identify issue (missing bracket, comma, etc.)
cat data/state/broken_state.json

# 3. Edit file
nano data/state/broken_state.json

# 4. Validate fix
cat data/state/broken_state.json | jq .
# Should return formatted JSON

# 5. Restart scraper
docker compose restart scraper
```

**Common JSON errors:**
- Missing closing brace `}`
- Missing/extra commas
- Unescaped quotes in strings
- Invalid timestamps (must be ISO format)

---

## Metadata Management

### Metadata File Format

**Location:** `data/metadata/{scraper_name}/{document_id}.json`

**Example:**
```json
{
  "title": "Market Conditions Report 2024",
  "source": "AEMO",
  "url": "https://aemo.com.au/reports/market-report-2024.pdf",
  "date": "2024-12-15",
  "category": "Market Reports",
  "file_path": "/app/data/scraped/aemo/market-report-2024.pdf",
  "file_hash": "3a7bd3e2360a3d29eea436fcfb7e44c3",
  "scraped_at": "2026-01-08T14:30:00.000000"
}
```

### Metadata Operations

**List all metadata for scraper:**
```bash
ls -la data/metadata/aemo/
```

**View specific metadata:**
```bash
cat data/metadata/aemo/document123.json | jq .
```

**Find metadata by field:**
```bash
# Find all reports from 2024
grep -r '"date": "2024-' data/metadata/aemo/

# Find by category
grep -r '"category": "Market Reports"' data/metadata/aemo/
```

### Repair Missing Metadata

**Use case:** Metadata file deleted/corrupted but document exists

**Re-extract metadata (Future enhancement):**

A metadata extraction script (`scripts/extract_metadata.py`) is planned to automatically reconstruct metadata from PDF files, but is not yet implemented. The planned usage would be:

```
# Planned syntax (not yet available):
python scripts/extract_metadata.py \
  --file data/scraped/aemo/document.pdf \
  --scraper aemo
```

**Current workaround: Manual reconstruction**

Until the extraction script is available, manually create the metadata file by examining the document and filling in available fields:

```json
{
  "title": "Extract from PDF filename or content",
  "source": "AEMO",
  "url": "Original URL if known",
  "date": "Estimate from file timestamp",
  "category": "Best guess",
  "file_path": "/app/data/scraped/aemo/document.pdf",
  "file_hash": "Run: sha256sum document.pdf",
  "scraped_at": "Use file modification time"
}
```

Save as `data/metadata/aemo/{document_id}.json` where `{document_id}` matches the document reference in your state file.

### Metadata Validation

**Check all metadata files are valid JSON:**
```bash
find data/metadata -name "*.json" | while read file; do
    echo "Checking $file"
    if jq . "$file" > /dev/null 2>&1; then
        echo "✓ VALID: $file"
    else
        echo "✗ INVALID: $file"
    fi
done
```

**Validate metadata schema:**
```bash
docker compose exec scraper \
  python -c "
from pathlib import Path
import json

required_fields = ['title', 'source', 'url', 'file_path']

for meta_file in Path('/app/data/metadata').rglob('*.json'):
    with open(meta_file) as f:
        data = json.load(f)
    missing = [f for f in required_fields if f not in data]
    if missing:
        print(f'{meta_file}: Missing fields: {missing}')
"
```

---

## Common Scenarios

### Starting Fresh

**Goal:** Reset all scraper state, re-scrape everything

**Steps:**
```bash
# 1. Backup current state (optional)
tar -czf state-backup-$(date +%Y%m%d).tar.gz data/state/

# 2. Delete all state files
rm data/state/*_state.json

# 3. Optionally clear downloaded documents
# WARNING: Only if you want to re-download everything
# rm -rf data/scraped/*
# rm -rf data/metadata/*

# 4. Restart scraper
docker compose restart scraper

# 5. Run scrapers
# Each will start from scratch
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo
```

### Re-scraping Specific Documents

**Goal:** Force re-download of specific URLs

**Method 1: Edit state file**
```bash
# 1. Stop scraper
docker compose stop scraper

# 2. Edit state file
nano data/state/aemo_state.json

# 3. Remove entries from processed_urls
# Delete the URL entries you want to re-scrape

# 4. Save and restart
docker compose start scraper

# 5. Run scraper
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo
```

**Method 2: Use exclusion rules** (if scraper supports)
```python
# In scraper config (config/scrapers/aemo.json)
{
  "exclusion_rules": {
    "url_patterns": [
      "old-pattern-to-skip"
    ]
  }
}
```

### Fixing Duplicate Detection

**Problem:** Scraper re-downloading documents it should skip

**Cause:** State file missing or file_hash changed

**Solution:**
```bash
# 1. Check state file exists
ls data/state/aemo_state.json

# 2. Verify URL is in processed_urls
cat data/state/aemo_state.json | jq '.processed_urls'

# 3. Verify file_hash matches
sha256sum data/scraped/aemo/document.pdf
# Compare with hash in state file

# 4. If hash mismatch, delete state file and re-run scraper
rm data/state/aemo_state.json
python scripts/run_scraper.py --scraper aemo
```

**Note:** A state hash update script (`scripts/update_state_hashes.py`) is planned for the future to automatically update hashes after manual document replacement, but is not yet implemented. The current workaround is to delete the state file and re-run the scraper.

### Migrating to New RAGFlow Instance

**Goal:** Move to different RAGFlow server, re-upload all documents

**Steps:**
```bash
# 1. Update RAGFlow config
nano .env
# Update RAGFLOW_API_URL, RAGFLOW_API_KEY, RAGFLOW_DATASET_ID

# 2. Restart scraper
docker compose restart scraper

# 3. Test connection
# Via web UI: Settings → Test RAGFlow Connection

# 4. Re-upload existing documents
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo --force
```

**Explanation:** The `--force` flag tells the scraper to re-process all documents, ignoring the local `data/state/{scraper}_state.json` file. This causes documents to be re-downloaded and re-uploaded to the new RAGFlow instance with updated metadata. (RAGFlow's API has only one upload endpoint—there's no separate "bulk" vs "single" upload method; the workflow handles batching by repeatedly calling the same API for each document.)

### Cleaning Orphaned Metadata

**Problem:** Metadata files exist but corresponding documents don't

**Find orphans:**
```bash
# List metadata files
find data/metadata/ -name "*.json" > /tmp/metadata_files

# For each metadata file, check if document exists
while read meta_file; do
    doc_path=$(cat "$meta_file" | jq -r '.file_path' | sed 's|/app/||')
    if [ ! -f "$doc_path" ]; then
        echo "Orphan: $meta_file (missing: $doc_path)"
    fi
done < /tmp/metadata_files
```

**Clean orphans:**
```bash
# Same loop but with rm
while read meta_file; do
    doc_path=$(cat "$meta_file" | jq -r '.file_path' | sed 's|/app/||')
    if [ ! -f "$doc_path" ]; then
        echo "Removing orphan: $meta_file"
        rm "$meta_file"
    fi
done < /tmp/metadata_files
```

---

## Troubleshooting

### State File Parse Errors

**Error:** `JSONDecodeError: Expecting property name enclosed in double quotes`

**Diagnosis:**
```bash
# Check JSON validity
cat data/state/broken_state.json | jq .
# Will show error location
```

**Solutions:**
1. Restore from backup
2. Manually fix JSON syntax
3. Delete and recreate (loses incremental state)

### Missing State Causing Re-scrapes

**Symptoms:**
- Scraper downloads documents again
- Duplicate files in scraped directory
- State file doesn't exist

**Solutions:**
```bash
# 1. Check if state file exists
ls -la data/state/

# 2. Check file permissions
ls -la data/state/missing_state.json

# 3. Check container can write
docker compose exec scraper touch /app/data/state/test.txt
docker compose exec scraper rm /app/data/state/test.txt

# 4. If permissions issue
chmod 755 data/state/
chown -R $(id -u):$(id -g) data/state/

# 5. Restore from backup if available
cp backup/state/scraper_state.json data/state/
```

### Metadata Out of Sync with RAGFlow

**Problem:** RAGFlow has different metadata than local files

**Diagnosis:**
```bash
# 1. Check local metadata
cat data/metadata/aemo/doc123.json | jq .

# 2. Check RAGFlow metadata (via API)
curl -H "Authorization: Bearer $RAGFLOW_API_KEY" \
  "$RAGFLOW_API_URL/api/v1/datasets/$RAGFLOW_DATASET_ID/documents/doc123"
```

**Solutions:**
1. Re-upload metadata to RAGFlow (use `--force` flag)
2. Download metadata from RAGFlow (if it's correct)
3. Manually reconcile differences

**Re-upload metadata:**
```bash
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo --force
```

This re-processes all documents and pushes their metadata to RAGFlow.

### Orphaned Metadata Files

**Problem:** Metadata exists but document file missing

**Find orphans:**
```bash
# Script above in "Cleaning Orphaned Metadata"
```

**Solutions:**
1. Re-download documents (scraper will skip if already uploaded to RAGFlow)
2. Delete orphaned metadata
3. Restore documents from backup

### State File Growing Too Large

**Problem:** State file becomes megabytes in size, slow to read/write

**Solutions:**

**Option 1: Archive old entries**
```bash
# Create archive state (last 90 days only)
docker compose exec scraper python -c "
import json
from datetime import datetime, timedelta
from pathlib import Path

state_file = Path('/app/data/state/large_state.json')
with open(state_file) as f:
    state = json.load(f)

cutoff = datetime.now() - timedelta(days=90)

# Keep only recent entries
filtered_urls = {
    url: data for url, data in state['processed_urls'].items()
    if datetime.fromisoformat(data['processed_at']) > cutoff
}

state['processed_urls'] = filtered_urls

# Save archived state
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
"
```

**Option 2: Compress with gzip** (not supported yet)

**Option 3: Use database** (future enhancement)

---

## State Best Practices

1. **Regular backups:** Backup state files daily
2. **Validate after changes:** Always run `jq .` to validate JSON
3. **Use version control:** Commit state files for critical scrapers
4. **Monitor file size:** Alert if state file > 10 MB
5. **Test migrations:** Always test state migrations on copy first
6. **Document schema changes:** Update this guide when adding fields

---

## Future Enhancements (Planned, Not Yet Implemented)

### Metadata Sync Script
**Planned:** `scripts/sync_metadata_to_ragflow.py`

**Purpose:** Bulk synchronize metadata to RAGFlow without re-scraping

**Status:** Not yet implemented

**Current workaround:** Use `--force` flag to re-process and re-upload:
```bash
python scripts/run_scraper.py --scraper aemo --force
```

### Bulk Upload Script
**Planned:** `scripts/bulk_upload.py`

**Purpose:** Upload existing documents to RAGFlow without re-scraping

**Status:** Not yet implemented

**Current workaround:** Same as above—use `--force` flag

### State Hash Update Script
**Planned:** `scripts/update_state_hashes.py`

**Purpose:** Automatically update file hashes in state files when documents are manually replaced

**Status:** Not yet implemented

**Current workaround:** Delete state file and re-run scraper:
```bash
rm data/state/{scraper}_state.json
python scripts/run_scraper.py --scraper {name}
```

### Metadata Extraction Script
**Planned:** `scripts/extract_metadata.py`

**Purpose:** Automatically extract and structure metadata from PDF documents during scraping

**Status:** Not yet implemented

**Current workaround:** Manually reconstruct metadata by examining documents, or use `--force` flag to re-process existing documents

---

## See Also

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Initial setup
- [RUNBOOK_COMMON_OPERATIONS.md](RUNBOOK_COMMON_OPERATIONS.md) - Daily operations
- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Error handling
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Development and scraper creation
