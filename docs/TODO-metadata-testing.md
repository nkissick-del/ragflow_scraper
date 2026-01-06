# RAGFlow Metadata Integration - Testing Checklist

**Status:** RAGFlow server currently down - execute this checklist when server is available

**Implementation Date:** 2026-01-06

**Purpose:** Verify metadata capture and push to RAGFlow API integration

---

## Pre-Testing Setup

### 1. Verify RAGFlow Server Status

```bash
# Test RAGFlow connection
curl -sS --fail --connect-timeout 5 --max-time 10 http://localhost:9380/

# Check API authentication
curl -sS --fail -H "Authorization: Bearer $RAGFLOW_API_KEY" \
  http://localhost:9380/api/v1/datasets
```

**Expected:** HTTP 200 with JSON response

### 2. Verify Container Health

```bash
# Check scraper container
docker compose ps scraper
docker logs pdf-scraper-dev --tail=50

# Verify Python imports
docker compose exec scraper python -c "from app.services.ragflow_metadata import prepare_metadata_for_ragflow; print('✓ Imports OK')"
```

**Expected:** Container healthy, no import errors

### 3. Configuration Check

```bash
# Verify environment variables
docker compose exec scraper python -c "
from app.config import Config
print(f'Push Metadata: {Config.RAGFLOW_PUSH_METADATA}')
print(f'Check Duplicates: {Config.RAGFLOW_CHECK_DUPLICATES}')
print(f'Metadata Timeout: {Config.RAGFLOW_METADATA_TIMEOUT}s')
print(f'API URL: {Config.RAGFLOW_API_URL}')
"
```

**Expected:** All settings shown correctly

---

## Test Suite 1: Single PDF Upload (AEMO)

### Test 1.1: Scrape with Metadata Capture

```bash
# Dry run to verify metadata structure
docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --dry-run

# Check metadata sidecar was created
ls -lh data/metadata/aemo/
cat data/metadata/aemo/<filename>.json | jq .
```

**Expected Output:**
- Metadata JSON contains: `organization`, `document_type`, `url`, `publication_date`, `hash`
- `organization` = "AEMO"
- `document_type` = "Report"

### Test 1.2: Upload with Metadata to RAGFlow

```bash
# Actual scrape and upload
docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected Output:**
```
Upload complete: 1 uploaded, 0 skipped (duplicates), 1 with metadata
Metadata: 1 documents with metadata pushed
```

**Verify in Logs:**
- `✓ <filename>.pdf: uploaded with metadata`
- No errors about metadata push failures

### Test 1.3: Verify Metadata in RAGFlow UI

1. Open RAGFlow UI: `http://localhost:9380`
2. Navigate to dataset (should be auto-created as "AEMO")
3. Find the uploaded document
4. Check document metadata fields:
   - `organization` = "AEMO"
   - `source_url` = document URL
   - `publication_date` = ISO date or "null"
   - `scraped_at` = ISO timestamp
   - `document_type` = "Report"
   - `author` = "null" (PDFs typically don't have authors)
   - `abstract` = "null" or extracted text

**Expected:** All metadata fields populated correctly

---

## Test Suite 2: Article Upload with Abstract (Guardian)

### Test 2.1: Scrape Article with Abstract Capture

```bash
# Scrape Guardian articles
docker compose exec scraper python scripts/run_scraper.py \
  --scraper guardian \
  --max-pages 1 \
  --dry-run

# Check metadata
cat data/metadata/guardian/<article-filename>.json | jq .extra
```

**Expected Output:**
- `extra.abstract` contains trail_text from Guardian API
- `extra.author` contains author name

### Test 2.2: Upload Article with Metadata

```bash
docker compose exec scraper python scripts/run_scraper.py \
  --scraper guardian \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected Output:**
- Upload succeeds
- Metadata pushed for all articles

### Test 2.3: Verify Article Metadata in RAGFlow

Check in RAGFlow UI:
- `organization` = "The Guardian Australia"
- `document_type` = "Article"
- `author` = actual author name (not "null")
- `abstract` = trail text summary (not "null")

**Expected:** Author and abstract populated correctly

---

## Test Suite 3: Deduplication by Hash

### Test 3.1: Upload Same Document Twice

```bash
# First upload
docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow

# Second upload (should skip due to hash match)
docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected Output (Second Run):**
```
Upload complete: 0 uploaded, 1 skipped (duplicates), 0 with metadata
Skipping duplicate: <filename>.pdf
```

**Verify in Logs:**
- `Found existing document with hash <hash>...`
- `Skipping duplicate: <filename>.pdf`

### Test 3.2: Verify No Duplicate in RAGFlow

Check RAGFlow dataset:
- Only ONE copy of the document exists
- No duplicate entries

**Expected:** Deduplication working correctly

---

## Test Suite 4: Bulk Upload (Multiple Documents)

### Test 4.1: Upload 5-10 Documents

```bash
docker compose exec scraper python scripts/run_scraper.py \
  --scraper reneweconomy \
  --max-pages 2 \
  --upload-to-ragflow
```

**Expected Output:**
```
Upload complete: 8 uploaded, 0 skipped (duplicates), 8 with metadata
```

### Test 4.2: Verify All Metadata Pushed

Check logs for each document:
- All show `✓ <filename>: uploaded with metadata`
- NO warnings about metadata push failures

### Test 4.3: Verify in RAGFlow

Navigate to RenewEconomy dataset:
- All 8 documents present
- All have complete metadata
- Organization field = "RenewEconomy"
- Document type = "Article"

---

## Test Suite 5: Error Handling

### Test 5.1: Upload Without Metadata Sidecar

```bash
# Delete a metadata sidecar file
rm data/metadata/aemo/<some-file>.json

# Try to upload
docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected Output:**
- Warning: `No metadata sidecar found for <filename>.pdf, uploading without metadata`
- Upload succeeds but without metadata
- `uploaded: 1, metadata_pushed: 0`

### Test 5.2: RAGFlow API Timeout

Test metadata push with very short timeout:

```bash
# Temporarily set low timeout
export RAGFLOW_METADATA_TIMEOUT=0.1

docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected Output:**
- Warning: `Document <id> not ready, will attempt metadata push anyway`
- Upload may succeed but metadata push might fail
- Graceful degradation - no crash

---

## Test Suite 6: Metadata Field Validation

### Test 6.1: Check All Standard Fields

**IMPORTANT:** Optional fields (publication_date, author, abstract) are OMITTED if not available.
Per RAGFlow docs: "If a parameter does not exist or is None, it won't be updated"

**PDF Scrapers (AEMO, AEMC, AER, ENA, ECA):**

Minimum required fields (always present):
```json
{
  "organization": "<Org Name>",
  "source_url": "https://...",
  "scraped_at": "2026-01-06T10:30:45.123456",
  "document_type": "Report"
}
```

With optional fields (if available):
```json
{
  "organization": "<Org Name>",
  "source_url": "https://...",
  "publication_date": "2024-01-15",
  "scraped_at": "2026-01-06T10:30:45.123456",
  "document_type": "Report"
}
```

Note: PDFs typically don't have author/abstract, so those fields are omitted.

**Article Scrapers (RenewEconomy, TheEnergy, Guardian, The Conversation):**

Minimum required fields (always present):
```json
{
  "organization": "<Site Name>",
  "source_url": "https://...",
  "scraped_at": "2026-01-06T10:30:45.123456",
  "document_type": "Article"
}
```

With all optional fields populated:
```json
{
  "organization": "<Site Name>",
  "source_url": "https://...",
  "publication_date": "2024-01-15",
  "scraped_at": "2026-01-06T10:30:45.123456",
  "document_type": "Article",
  "author": "John Doe",
  "abstract": "Article summary..."
}
```

### Test 6.2: Verify No Nested Objects

Query RAGFlow API to inspect metadata:

```bash
curl -H "Authorization: Bearer $RAGFLOW_API_KEY" \
  "http://localhost:9380/api/v1/datasets/<dataset-id>/documents/<doc-id>" | jq .data.meta_fields
```

**Expected:** All values are strings or numbers, NO nested objects or arrays

---

## Test Suite 7: Configuration Options

### Test 7.1: Disable Metadata Push

```bash
# Set env var to disable metadata
export RAGFLOW_PUSH_METADATA=false

docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected:** Upload succeeds but no metadata pushed

### Test 7.2: Disable Deduplication

```bash
export RAGFLOW_CHECK_DUPLICATES=false

# Upload same doc twice
docker compose exec scraper python scripts/run_scraper.py \
  --scraper aemo \
  --max-pages 1 \
  --upload-to-ragflow
```

**Expected:** Both uploads succeed (no deduplication)

---

## Troubleshooting Guide

### Issue: "Failed to check document existence"

**Cause:** RAGFlow API not responding or wrong endpoint

**Fix:**
1. Verify RAGFlow server is running
2. Check API URL in `.env`: `RAGFLOW_API_URL=http://localhost:9380`
3. Test API manually: `curl http://localhost:9380/api/v1/datasets`

### Issue: "Metadata set failed: code != 0"

**Cause:** RAGFlow rejected metadata (invalid format)

**Fix:**
1. Check metadata contains only flat key-value pairs
2. Verify no nested objects or arrays
3. Check logs for specific error message from RAGFlow
4. Validate metadata with: `python -c "from app.services.ragflow_metadata import prepare_metadata_for_ragflow; print(prepare_metadata_for_ragflow({'test': 'value'}))" `

### Issue: "Document not ready, timeout waiting"

**Cause:** RAGFlow taking longer than expected to register document

**Fix:**
1. Increase timeout: `export RAGFLOW_METADATA_TIMEOUT=20.0`
2. Check RAGFlow server load (may be processing many documents)
3. Verify document actually uploaded (check RAGFlow UI)

### Issue: "Skipping duplicate" for new document

**Cause:** Hash collision or state file corruption

**Fix:**
1. Check if document actually exists in RAGFlow
2. Clear state file: `rm data/state/aemo_state.json`
3. Try upload again

### Issue: No metadata in RAGFlow despite success message

**Cause:** RAGFlow UI may not show custom metadata fields

**Fix:**
1. Query via API to verify metadata exists:
   ```bash
   curl -H "Authorization: Bearer $RAGFLOW_API_KEY" \
     "http://localhost:9380/api/v1/datasets/<id>/documents/<doc-id>" | jq .data.meta_fields
   ```
2. Check RAGFlow version supports custom metadata
3. Try retrieval with metadata filters to confirm metadata is indexed

---

## Success Criteria Checklist

After completing all tests, verify:

- [ ] ✅ All 9 scrapers set `organization` and `document_type` correctly
- [ ] ✅ PDF scrapers: `organization` = org name, `document_type` = "Report"
- [ ] ✅ Article scrapers: `organization` = site name, `document_type` = "Article"
- [ ] ✅ Article scrapers with abstract: Guardian, TheEnergy, The Conversation populate `abstract` field
- [ ] ✅ Metadata pushed to RAGFlow for all uploads
- [ ] ✅ Deduplication by hash works (no duplicate uploads)
- [ ] ✅ Upload succeeds even if metadata push fails (graceful degradation)
- [ ] ✅ All metadata fields are flat (no nested objects)
- [ ] ✅ Statistics show correct counts: uploaded, skipped, metadata_pushed
- [ ] ✅ Configuration options work (disable metadata, disable dedup)
- [ ] ✅ No crashes or unhandled exceptions

---

## Post-Testing Actions

### If All Tests Pass:

1. Document any RAGFlow API quirks discovered
2. Update CLAUDE.md with metadata field examples
3. Consider adding automated integration tests
4. Monitor production uploads for metadata accuracy

### If Tests Fail:

1. Document failure mode in issue tracker
2. Check RAGFlow API version compatibility
3. Review RAGFlow server logs for errors
4. Consider API endpoint changes or RAGFlow updates
5. Update implementation as needed

---

## Additional Notes

### RAGFlow Metadata API Assumptions (Needs Verification):

1. **Endpoint:** `PUT /api/v1/datasets/{id}/documents/{doc_id}` with `{"meta_fields": {...}}`
2. **Status polling:** `GET /api/v1/datasets/{id}/documents/{doc_id}` returns `{... "status": "registered|parsing|parsed|failed"}`
3. **Hash field:** Documents returned from `GET /api/v1/datasets/{id}/documents` include `hash` or `file_hash` field
4. **Timing:** Documents must be "registered" before metadata can be set

**Action:** Verify these assumptions during testing and update code if API differs

### Known Limitations:

- Tags array not pushed to RAGFlow (too complex for flat metadata)
- Extra dict fields (except author/abstract) not pushed
- File size not pushed (internal detail)
- Local path not pushed (security concern)

---

**Testing Completed:** [ ] YES [ ] NO

**Tested By:** _______________

**Date:** _______________

**RAGFlow Version:** _______________

**Notes:**
