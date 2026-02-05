## 2024-05-22 - File Reading Optimization
**Learning:** Micro-optimizing file reading loops (replacing `iter(lambda: ..., b"")` with `while chunk := ...`) provided negligible performance gains (-1% to +3%) on 100MB files, likely because I/O and SHA256 hashing dominate execution time.
**Action:** Prioritize this optimization for code readability and modern Python standards rather than purely for performance in I/O-bound contexts.
