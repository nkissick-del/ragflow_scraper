# Enhancement Plan: Integrate Apache Tika for Metadata Enrichment

## Context
Currently, the scraper relies on **contextual metadata**—information extracted from the HTML page where a file is hosted (e.g., date, author, title text next to the download link). This is generally high accuracy but relies on the website structure.

The user suggested using **Apache Tika**, a toolkit for detecting and extracting metadata and text from over a thousand different file types (such as PPT, XLS, and PDF).

## Strategy
We should **NOT** replace the existing contextual extraction, as embedded PDF metadata is often low quality (e.g., Author="Microsoft Word User"). Instead, we will use Tika as a **fallback and enrichment layer**.

### Proposed Data Flow
1.  **Scraper**: Extracts high-confidence metadata from the Web (Title, Date, Source).
2.  **Download**: File is saved to disk.
3.  **Enrichment (New Step via Tika)**:
    *   Send file to Tika service.
    *   Extract `Creation-Date`, `Author`, `Content-Type`, and full text.
    *   **Merge Policy**: If Web metadata is missing a field, fill it with Tika metadata.
    *   **Text Extraction**: Use Tika's robust text extraction to generate the `.md` content for binary files (PDFs) that don't have an HTML equivalent.

## Architecture Changes
1.  **Infrastructure**: Add `apache/tika` container to the Docker stack.
2.  **Service**: Create `app/services/tika_client.py`.
3.  **Pipeline**: Update `Pipeline` to pass downloaded binary files through the Tika client before final sizing/hashing.

## Implementation Steps
1.  **Add Container**: Update `docker-compose.yml` (if applicable) or run instructions.
2.  **Create Client**: Build a lightweight Python client for the Tika REST API (`PUT /tika` or `/rmeta`).
3.  **Integration**:
    *   When a PDF is downloaded, query Tika.
    *   Update `DocumentMetadata` with any found extra keys (e.g., `meta:language`, `meta:page_count`).
    *   If no Markdown content exists for the file (pure PDF scrape), save Tika's text output as the content.

## Benefits
*   **Better Search**: Searching for "Page count > 50" or "Language = French" becomes possible.
*   **Gap Filling**: If a scraper fails to find a date on the web page, Tika might find the PDF creation date.
*   **Content Indexing**: Superior text extraction for RAG compared to basic libraries.
