## 2026-01-31 - In-memory Hashing vs Disk I/O
**Learning:** Calculating hash from a file on disk (read + hash) is significantly slower (2x) than hashing bytes in memory, especially when combined with redundant text encoding.
**Action:** When saving content to a file and needing its hash, compute the hash from the in-memory bytes before writing, avoiding the read-back and extra encoding steps.

## 2026-01-31 - File I/O Chunk Size
**Learning:** Default file read/write chunk sizes (often 8KB) are suboptimal for modern hardware. Increasing to 64KB significantly reduces system calls and overhead for file operations.
**Action:** Use `CHUNK_SIZE = 65536` for all file copy, hash, and download operations involving streams.
