# Enhancement Plan: Pushing Metadata to Paperless-ngx

## Context
The current `PaperlessClient` attempts to send `tags` and `correspondent` as raw strings (names). However, the Paperless-ngx API expects **integer IDs** for these fields. As a result, metadata upload is currently failing or incomplete, as noted by `TODO` comments in the code.

Additionally, the user wants to capture "physical metadata" (analyzed from the file). While tags handle categorization, **Custom Fields** are the correct home for structured data like `original_url`, `author_raw`, or `page_count`.

## Strategy
We need to upgrade `PaperlessClient` to be "smart"—it should auto-resolve names to IDs, creating new tags/correspondents if they don't exist.

### 1. Tag & Correspondent Mapping
Paperless does not accept "Invoice" as a tag. It accepts `42` (where `42` is the ID of the "Invoice" tag).
**Solution**: Implement `get_or_create` logic.
*   **Tags**: Cache all existing tags on startup (or lazy load). If a tag name exists, use its ID. If not, `POST /api/tags/` to create it and get the new ID.
*   **Correspondent**: Same logic. If `Organization` is "AEMO", check for "AEMO" correspondent ID. If missing, create it.

### 2. Custom Fields
Paperless supports "Custom Fields" (e.g., `Original URL`, `Scrape Date`).
**Solution**:
*   Define a standard set of custom fields we want to populate.
*   Check if these fields exist in Paperless; if not, create them (with type `Text`, `Date`, etc.).
*   When uploading, map our `DocumentMetadata` to these Custom Field IDs.

## Implementation Plan

### Phase 1: Client Upgrade (`app/services/paperless_client.py`)
Add the following methods to `PaperlessClient`:
- `_get_tags() -> dict[str, int]`: Fetch name->ID mapping.
- `get_or_create_tag(name: str) -> int`: helper.
- `_get_correspondents() -> dict[str, int]`: Fetch name->ID mapping.
- `get_or_create_correspondent(name: str) -> int`: helper.
- `_get_custom_fields() -> dict[str, int]`: Fetch name->ID mapping.

### Phase 2: Upload Logic Update
Modify `post_document`:
1.  **Resolve Correspondent**: `name -> ID`.
2.  **Resolve Tags**: `list[names] -> list[IDs]`.
3.  **Map Custom Fields**:
    *   `url` -> `Custom Field "Original URL"`
    *   `scraped_at` -> `Custom Field "Scraped At"`
    *   `file_size` -> `Custom Field "File Size Bytes"`
4.  **Send Payload**: `{"tags": [1, 2], "correspondent": 5, "custom_fields": [{"field": 10, "value": "http://..."}]}`

### Phase 3: Pipeline Integration
Ensure `pipeline.py` passes the full `DocumentMetadata` object (or relevant dictionary) to the `PaperlessClient`, allowing it to extract the extra fields.

## Data Mapping Example
| Scraper Metadata | Paperless Field | Type |
| :--- | :--- | :--- |
| `tags` (["Report", "Energy"]) | `tags` | IDs (e.g. `[4, 12]`) |
| `organization` ("AEMO") | `correspondent` | ID (e.g. `7`) |
| `url` | `Original URL` | Custom Field |
| `date` | `created` | Native Field |
| `title` | `title` | Native Field |

## Benefits
*   **Zero-Config**: The scraper doesn't need to know Paperless IDs; it just sends "String" data and the client handles the plumbing.
*   **Rich Search**: You can search in Paperless for `original_url: *aemo*` or filter by properly linked correspondents.
