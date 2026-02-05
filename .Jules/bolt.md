## 2026-01-31 - In-memory Hashing vs Disk I/O
**Learning:** Calculating hash from a file on disk (read + hash) is significantly slower (2x) than hashing bytes in memory, especially when combined with redundant text encoding.
**Action:** When saving content to a file and needing its hash, compute the hash from the in-memory bytes before writing, avoiding the read-back and extra encoding steps.

## 2026-02-01 - Optimizing Download Streams
**Learning:** Increasing chunk size from 8KB to 64KB and computing hash on-the-fly during download saves ~10% time and avoids redundant disk reads.
**Action:** Use `CHUNK_SIZE` (65536) for all file I/O and stream processing; prefer `hashlib.update(chunk)` inside the write loop over reading the file again.
