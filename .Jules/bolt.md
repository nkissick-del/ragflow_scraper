## 2025-01-26 - [Redundant Disk I/O in File Hashing]
**Learning:** The codebase previously wrote content to disk and then immediately read it back to compute a hash (`get_file_hash`). This is a redundant I/O operation, especially for frequent small file writes in scrapers.
**Action:** When content is available in memory (string/bytes), compute the hash directly using `get_content_hash` before or during the write process to save an I/O cycle.
