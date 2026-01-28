# Bolt's Journal

## 2024-05-22 - [Project Start]
**Learning:** Initial exploration of the codebase. It's a Flask-based scraper with Selenium and RAGFlow integration.
**Action:** Look for performance bottlenecks in job queue management and file I/O operations.

## 2024-05-22 - [IO Optimization]
**Learning:** File hashing was reading files back from disk immediately after writing.
**Action:** Use in-memory hashing of bytes before writing to avoid redundant IO and encoding.
