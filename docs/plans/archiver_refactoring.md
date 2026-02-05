# Refactoring Plan: Replace Selenium Archiver with Gotenberg

## Context
Currently, the application uses a Selenium-based `Archiver` service (`app/services/archiver.py`) to generate archival-quality PDFs.
1.  **Scraping**: Content is scraped and saved as **Markdown** (`.md`) and JSON metadata.
2.  **RAGFlow**: The **Markdown** files are uploaded to RAGFlow for indexing.
3.  **Paperless-ngx**: The `Archiver` class takes the raw HTML, wraps it in a custom "Reader View" sanitization and CSS template, and uses a **Selenium WebDriver** (via Chrome) to "print" the page to a PDF. This PDF is then uploaded to Paperless.

## Problem
*   **Heavy Dependency**: Maintaining a Selenium Grid or local Chrome instance just for PDF generation is resource-intensive and adds complexity (driver compatibility, crashes, memory leaks).
*   **Dual Pipelines**: We have one logic flow for RAG (Markdown) and a completely separate rendering flow for PDFs (HTML + CSS injection).

## Recommendation
**Replace the Selenium-based `Archiver` with a Gotenberg integration.**

Gotenberg is a Docker-based API for converting documents to PDF. It supports converting **Markdown** directly to PDF (via Chromium under the hood, but managed externally).

### Proposed Architecture
1.  **Scraper**: Continues to produce Markdown as the primary artifact.
2.  **RAGFlow**: Continues to ingest the Markdown files directly.
3.  **Archiver (New)**:
    *   Instead of spinning up a browser, it constructs a request to the Gotenberg API (`/forms/chromium/convert/markdown`).
    *   It sends the **Markdown** file (same one sent to RAG) + an optional `index.html` wrapper (for header/footer styling) to Gotenberg.
    *   Gotenberg returns the generated PDF.
    *   This PDF is uploaded to Paperless.

### Benefits
1.  **Unified Source of Truth**: both RAG and Archive use the exact same Markdown source.
2.  **Simplicity**: usage of `selenium` and `webdriver_manager` can be removed from the project if not used by scrapers themselves (though some scrapers might still use it for dynamic sites, the *archiving* step no longer depends on it).
3.  **Performance**: Gotenberg is optimized for this task and runs as a separate, stateless container.
4.  **Stability**: No more managing zombie Chrome processes or driver version mismatches in the main app.

## Implementation Steps
1.  **Verify Gotenberg**: Ensure a Gotenberg container is available in the stack.
2.  **Create Client**: Implement a simple `GotenbergClient` or update `Archiver` to post to Gotenberg.
3.  **Update Pipeline**: modify `app/orchestrator/pipeline.py` to use the new PDF generation method.
4.  **Cleanup**: Deprecate/remove the Selenium logic from `Archiver`.
