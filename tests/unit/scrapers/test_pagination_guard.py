"""Unit tests for PaginationGuard."""

from __future__ import annotations

from app.scrapers.pagination_guard import PaginationGuard


class TestEmptyPages:
    """Stop after N consecutive empty pages."""

    def test_stops_after_default_empty_threshold(self):
        guard = PaginationGuard()
        stop, _ = guard.check_page([])
        assert stop is False
        stop, reason = guard.check_page([])
        assert stop is True
        assert "empty" in reason

    def test_custom_empty_threshold(self):
        guard = PaginationGuard(max_empty_pages=3)
        for _ in range(2):
            stop, _ = guard.check_page([])
            assert stop is False
        stop, reason = guard.check_page([])
        assert stop is True
        assert "3" in reason

    def test_non_empty_page_resets_empty_counter(self):
        guard = PaginationGuard()
        guard.check_page([])  # 1 empty
        guard.check_page(["http://a.com/1"])  # resets
        stop, _ = guard.check_page([])  # 1 empty again
        assert stop is False


class TestDuplicatePages:
    """Stop after N consecutive duplicate pages (same URL set)."""

    def test_stops_after_default_duplicate_threshold(self):
        guard = PaginationGuard()
        urls = ["http://a.com/1", "http://a.com/2"]
        guard.check_page(urls)  # first time — recorded
        stop, _ = guard.check_page(urls)  # dup 1
        assert stop is False
        stop, reason = guard.check_page(urls)  # dup 2
        assert stop is True
        assert "duplicate" in reason

    def test_order_independent_fingerprint(self):
        """Same URLs in different order count as duplicate."""
        guard = PaginationGuard()
        guard.check_page(["http://a.com/1", "http://a.com/2"])
        stop, _ = guard.check_page(["http://a.com/2", "http://a.com/1"])
        # First duplicate, not yet at threshold
        assert stop is False

    def test_different_page_resets_duplicate_counter(self):
        guard = PaginationGuard()
        urls_a = ["http://a.com/1"]
        urls_b = ["http://a.com/2"]
        guard.check_page(urls_a)
        guard.check_page(urls_a)  # dup 1
        guard.check_page(urls_b)  # different — resets
        stop, _ = guard.check_page(urls_b)  # dup 1 of urls_b
        assert stop is False

    def test_custom_duplicate_threshold(self):
        guard = PaginationGuard(max_duplicate_pages=1)
        urls = ["http://a.com/1"]
        guard.check_page(urls)
        stop, reason = guard.check_page(urls)  # dup 1 — hits threshold
        assert stop is True
        assert "duplicate" in reason


class TestNoNewItems:
    """Stop after N consecutive pages with no new URLs."""

    def test_stops_after_default_no_new_threshold(self):
        guard = PaginationGuard()
        # First page: all new
        guard.check_page(["http://a.com/1", "http://a.com/2"])
        # Pages with overlapping but not identical subsets (different fingerprints)
        guard.check_page(["http://a.com/1"])  # no new — 1
        guard.check_page(["http://a.com/2"])  # no new — 2
        stop, reason = guard.check_page(["http://a.com/1", "http://a.com/2"])
        # This is a duplicate page fingerprint AND no-new
        assert stop is True
        assert "no new items" in reason

    def test_new_url_resets_no_new_counter(self):
        guard = PaginationGuard()
        guard.check_page(["http://a.com/1"])
        guard.check_page(["http://a.com/1"])  # dup → no-new 1
        # Fresh URL resets
        guard.check_page(["http://a.com/2"])
        stop, _ = guard.check_page(["http://a.com/2"])
        # only 1 no-new after reset
        assert stop is False

    def test_custom_no_new_threshold(self):
        guard = PaginationGuard(max_no_new_items_pages=1)
        guard.check_page(["http://a.com/1"])
        stop, reason = guard.check_page(["http://a.com/1"])
        assert stop is True


class TestEdgeCases:
    """Edge cases and mixed scenarios."""

    def test_single_item_pages(self):
        guard = PaginationGuard()
        guard.check_page(["http://a.com/1"])
        guard.check_page(["http://a.com/2"])
        guard.check_page(["http://a.com/3"])
        # All unique — no stop
        stop, _ = guard.check_page(["http://a.com/4"])
        assert stop is False

    def test_overlapping_but_not_identical_sets(self):
        """Pages that share some URLs but have different fingerprints."""
        guard = PaginationGuard()
        guard.check_page(["http://a.com/1", "http://a.com/2"])
        # Overlapping: /2 is old, /3 is new — different fingerprint, has new URL
        stop, _ = guard.check_page(["http://a.com/2", "http://a.com/3"])
        assert stop is False

    def test_empty_between_non_empty_pages(self):
        """Empty page sandwiched between non-empty pages."""
        guard = PaginationGuard()
        guard.check_page(["http://a.com/1"])
        guard.check_page([])  # empty 1
        guard.check_page(["http://a.com/2"])  # non-empty resets
        stop, _ = guard.check_page([])  # empty 1 again
        assert stop is False

    def test_fresh_guard_first_page_not_stopped(self):
        guard = PaginationGuard()
        stop, _ = guard.check_page(["http://a.com/1"])
        assert stop is False

    def test_counters_interact_correctly(self):
        """Duplicate pages also increment no-new counter."""
        guard = PaginationGuard(max_duplicate_pages=5, max_no_new_items_pages=3)
        urls = ["http://a.com/1"]
        guard.check_page(urls)
        guard.check_page(urls)  # dup 1, no-new 1
        guard.check_page(urls)  # dup 2, no-new 2
        stop, reason = guard.check_page(urls)  # dup 3, no-new 3
        assert stop is True
        assert "no new items" in reason
