# Enhancement Plan: Canonical Naming with Jinja2

## Context
The user wants to rename files "canonically" based on the extracted metadata.
Hardware/Software differences mean raw filenames are often messy (`ViewDocument.ashx`, `report_v3_final.pdf`).
A structured naming convention (e.g., `2024-05-12_AEMO_Annual_Report.pdf`) makes the file system much more navigable and Paperless ingestion cleaner.

## Solution: Jinja2 Templating
**Jinja2** is the perfect tool for this. It allows safe, dynamic string processing with logic filters.

### Proposed Workflow
1.  **Metadata Gathering**: Scraper collects data + Tika/Docling enriches it.
    *   `{"title": "Annual Report", "date": "2024-05-12", "org": "AEMO"}`
2.  **Template Rendering**:
    *   Config rule: `{{ date }}_{{ org }}_{{ title | slugify }}.pdf`
    *   Result: `2024-05-12_AEMO_annual-report.pdf`
3.  **Renaming**: The file is moved/renamed on disk before being sent to RAG/Archive.

## Implementation Details

### 1. New Dependency
Add `jinja2` to `pyproject.toml` / `requirements.txt`.

### 2. Configuration (`app/config.py`)
Add a setting for the default naming pattern:
```python
DEFAULT_FILENAME_TEMPLATE = "{{ publication_date | default('0000-00-00') }}_{{ organization }}_{{ title | slugify }}.{{ extension }}"
```

### 3. The `NameGenerator` Service
Create `app/services/name_generator.py`:
-   **Inputs**: `metadata` (dict), `template_string` (str).
-   **Filters**: Register custom filters heavily used for filenames:
    -   `slugify`: Converts "Major Report (2024)" -> "major-report-2024" (safe for FS).
    -   `shorten(n)`: Truncates long titles.
    -   `secure_filename`: Removes `/`, `\`, `..` to prevent directory traversal.

### 4. Pipeline Integration
Update `pipeline.py`:
```python
# ... after enrichment ...
new_filename = name_generator.render(metadata)
file_path = file_path.rename(file_path.parent / new_filename)
metadata.filename = new_filename
# ... proceed to RAG/Paperless ...
```

## Example Patterns
*   **Chronological**: `{{ date }}_{{ title | slugify }}.pdf`
*   **Organizational**: `{{ organization }}/{{ date }}_{{ title | slugify }}.pdf` (Jinja can even suggest directory structures, though we'd need to handle folder creation).
*   **Categorical**: `{{ category | default('Unsorted') }}_{{ title }}.pdf`

## Benefits
-   **Consistency**: All files follow ISO dates and safe naming.
-   **Flexibility**: Change the naming convention in one config string without rewriting code.
-   **Cleanliness**: No more `UE3948_23.pdf`.
