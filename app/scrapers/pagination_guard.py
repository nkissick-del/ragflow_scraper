"""Reusable pagination termination guard for scrapers with while-True loops.

Detects three conditions that indicate pagination should stop:
1. **Empty pages** — zero items found on a page
2. **Duplicate pages** — exact same set of item URLs as a previous page
3. **No new items** — all items on the page were already seen on earlier pages
"""

from __future__ import annotations


class PaginationGuard:
    """Tracks page content across pagination to detect loops and dead ends.

    Usage::

        guard = PaginationGuard()
        while True:
            articles = parse_page(...)
            urls = [a.url for a in articles]
            should_stop, reason = guard.check_page(urls)
            if should_stop:
                logger.info(f"Stopping: {reason}")
                break
    """

    def __init__(
        self,
        max_duplicate_pages: int = 2,
        max_empty_pages: int = 2,
        max_no_new_items_pages: int = 3,
    ) -> None:
        self.max_duplicate_pages = max_duplicate_pages
        self.max_empty_pages = max_empty_pages
        self.max_no_new_items_pages = max_no_new_items_pages

        self._seen_urls: set[str] = set()
        self._seen_page_fingerprints: set[frozenset[str]] = set()

        self._consecutive_empty: int = 0
        self._consecutive_duplicate: int = 0
        self._consecutive_no_new: int = 0

    def check_page(self, item_urls: list[str]) -> tuple[bool, str]:
        """Evaluate a page's item URLs and return whether to stop.

        Args:
            item_urls: URLs of items found on the current page.

        Returns:
            ``(should_stop, reason)`` — *reason* is a human-readable string
            explaining why pagination should stop, or ``""`` if it should
            continue.
        """
        # --- empty page ---
        if not item_urls:
            self._consecutive_empty += 1
            # Reset other counters (page had no items to evaluate)
            self._consecutive_duplicate = 0
            self._consecutive_no_new = 0
            if self._consecutive_empty >= self.max_empty_pages:
                return True, (
                    f"{self._consecutive_empty} consecutive empty pages"
                )
            return False, ""

        # Non-empty page resets the empty counter
        self._consecutive_empty = 0

        fingerprint = frozenset(item_urls)

        # --- duplicate page (exact same URL set seen before) ---
        if fingerprint in self._seen_page_fingerprints:
            self._consecutive_duplicate += 1
            # Also counts as no-new since all URLs already seen
            self._consecutive_no_new += 1
            if self._consecutive_duplicate >= self.max_duplicate_pages:
                return True, (
                    f"{self._consecutive_duplicate} consecutive duplicate pages"
                )
            if self._consecutive_no_new >= self.max_no_new_items_pages:
                return True, (
                    f"{self._consecutive_no_new} consecutive pages with no new items"
                )
            return False, ""

        self._consecutive_duplicate = 0
        self._seen_page_fingerprints.add(fingerprint)

        # --- no new items (all URLs already encountered individually) ---
        new_urls = [u for u in item_urls if u not in self._seen_urls]
        if not new_urls:
            self._consecutive_no_new += 1
            if self._consecutive_no_new >= self.max_no_new_items_pages:
                return True, (
                    f"{self._consecutive_no_new} consecutive pages with no new items"
                )
        else:
            self._consecutive_no_new = 0

        # Record all URLs from this page
        self._seen_urls.update(item_urls)

        return False, ""
