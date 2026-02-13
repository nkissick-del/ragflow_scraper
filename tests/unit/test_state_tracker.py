
import json
import threading

import pytest

from app.services.state_tracker import StateTracker


@pytest.fixture
def tracker():
    return StateTracker("test-scraper")


def test_mark_processed_creates_state_file(tracker):
    url = "https://example.com/doc.pdf"
    tracker.mark_processed(url)
    tracker.save()

    assert tracker.state_file.exists()
    content = tracker.state_file.read_text()
    assert url in content


def test_is_processed_true_after_mark(tracker):
    url = "https://example.com/doc.pdf"
    tracker.mark_processed(url)
    assert tracker.is_processed(url) is True


def test_is_processed_false_for_new_url(tracker):
    url = "https://example.com/new.pdf"
    assert tracker.is_processed(url) is False


def test_statistics_update(tracker):
    tracker.mark_processed("https://example.com/doc1.pdf", status="downloaded")
    tracker.mark_processed("https://example.com/doc2.pdf", status="skipped")
    tracker.mark_processed("https://example.com/doc3.pdf", status="failed")

    stats = tracker.get_statistics()
    assert stats["total_processed"] == 3
    assert stats["total_downloaded"] == 1
    assert stats["total_skipped"] == 1
    assert stats["total_failed"] == 1


def test_remove_url(tracker):
    url = "https://example.com/doc.pdf"
    tracker.mark_processed(url)
    assert tracker.remove_url(url) is True
    assert tracker.is_processed(url) is False


def test_last_run_info(tracker):
    tracker.mark_processed("https://example.com/doc.pdf")
    tracker.save()
    info = tracker.get_last_run_info()
    assert info["processed_count"] == 1
    assert "statistics" in info


def test_concurrent_mark_processed(tracker):
    """10 threads each marking a unique URL should all succeed."""
    errors: list[Exception] = []

    def mark(url: str):
        try:
            tracker.mark_processed(url)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=mark, args=(f"https://example.com/{i}.pdf",))
        for i in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    urls = tracker.get_processed_urls()
    assert len(urls) == 10
    for i in range(10):
        assert f"https://example.com/{i}.pdf" in urls


def test_concurrent_save(tracker):
    """5 threads each mark+save; state file should be valid JSON with all URLs."""
    errors: list[Exception] = []

    def mark_and_save(url: str):
        try:
            tracker.mark_processed(url)
            tracker.save()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=mark_and_save, args=(f"https://example.com/{i}.pdf",))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []

    # Verify state file is valid JSON
    with open(tracker.state_file, "r") as f:
        state = json.load(f)

    assert len(state["processed_urls"]) == 5


# ── Additional coverage tests ─────────────────────────────────────────


class TestMarkProcessedVariousMetadata:
    """Test mark_processed with various metadata and statuses."""

    def test_mark_with_metadata(self, tracker):
        """Should store metadata along with URL."""
        url = "https://example.com/doc.pdf"
        metadata = {"title": "Test Doc", "size": 1024}
        tracker.mark_processed(url, metadata=metadata, status="downloaded")

        info = tracker.get_url_info(url)
        assert info is not None
        assert info["metadata"] == metadata
        assert info["status"] == "downloaded"

    def test_mark_with_default_status(self, tracker):
        """Default status should be 'downloaded'."""
        tracker.mark_processed("https://example.com/doc.pdf")

        info = tracker.get_url_info("https://example.com/doc.pdf")
        assert info["status"] == "downloaded"

    def test_mark_with_skipped_status(self, tracker):
        """Should track skipped status."""
        tracker.mark_processed("https://example.com/doc.pdf", status="skipped")
        stats = tracker.get_statistics()
        assert stats["total_skipped"] == 1
        assert stats["total_downloaded"] == 0

    def test_mark_with_failed_status(self, tracker):
        """Should track failed status."""
        tracker.mark_processed("https://example.com/doc.pdf", status="failed")
        stats = tracker.get_statistics()
        assert stats["total_failed"] == 1

    def test_mark_with_unknown_status(self, tracker):
        """Unknown status increments total_processed but no category."""
        tracker.mark_processed("https://example.com/doc.pdf", status="custom")
        stats = tracker.get_statistics()
        assert stats["total_processed"] == 1
        assert stats["total_downloaded"] == 0
        assert stats["total_skipped"] == 0
        assert stats["total_failed"] == 0

    def test_mark_overwrites_existing_url(self, tracker):
        """Marking same URL twice should overwrite entry."""
        url = "https://example.com/doc.pdf"
        tracker.mark_processed(url, status="failed")
        tracker.mark_processed(url, status="downloaded")

        info = tracker.get_url_info(url)
        assert info["status"] == "downloaded"

        # Statistics count both marks
        stats = tracker.get_statistics()
        assert stats["total_processed"] == 2


class TestGetStatisticsCalculations:
    """Test get_statistics returns correct calculations."""

    def test_initial_statistics_are_zero(self, tracker):
        """Fresh tracker should have zero statistics."""
        stats = tracker.get_statistics()
        assert stats["total_processed"] == 0
        assert stats["total_downloaded"] == 0
        assert stats["total_skipped"] == 0
        assert stats["total_failed"] == 0

    def test_mixed_status_counts(self, tracker):
        """Should accurately count mixed statuses."""
        tracker.mark_processed("https://a.com/1.pdf", status="downloaded")
        tracker.mark_processed("https://a.com/2.pdf", status="downloaded")
        tracker.mark_processed("https://a.com/3.pdf", status="skipped")
        tracker.mark_processed("https://a.com/4.pdf", status="failed")
        tracker.mark_processed("https://a.com/5.pdf", status="downloaded")

        stats = tracker.get_statistics()
        assert stats["total_processed"] == 5
        assert stats["total_downloaded"] == 3
        assert stats["total_skipped"] == 1
        assert stats["total_failed"] == 1

    def test_statistics_are_deep_copy(self, tracker):
        """Returned statistics should be a deep copy."""
        tracker.mark_processed("https://example.com/1.pdf", status="downloaded")
        stats = tracker.get_statistics()
        stats["total_downloaded"] = 999

        # Original should be unmodified
        assert tracker.get_statistics()["total_downloaded"] == 1


class TestSaveLoadStateFileIO:
    """Test save/load state file I/O edge cases."""

    def test_save_creates_state_file(self, tracker):
        """Save should create the state file."""
        tracker.mark_processed("https://example.com/doc.pdf")
        tracker.save()

        assert tracker.state_file.exists()

    def test_save_updates_last_updated(self, tracker):
        """Save should update last_updated timestamp."""
        tracker.save()

        with open(tracker.state_file, "r") as f:
            state = json.load(f)

        assert state["last_updated"] is not None

    def test_load_corrupted_json(self, tmp_path):
        """Should start fresh when state file contains invalid JSON."""
        from app.config import Config

        state_file = Config.STATE_DIR / "corrupted_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{invalid json!!!")

        tracker = StateTracker("corrupted")
        tracker.state_file = state_file
        tracker._state = tracker._load_state()

        # Should have empty processed_urls
        assert tracker.get_processed_urls() == []

    def test_load_valid_state(self, tmp_path):
        """Should load valid state from file."""
        tracker = StateTracker("loadtest")
        tracker.mark_processed("https://example.com/doc.pdf")
        tracker.save()

        # Create new tracker to reload from file
        tracker2 = StateTracker("loadtest")
        assert tracker2.is_processed("https://example.com/doc.pdf")


class TestClearState:
    """Test clear() method."""

    def test_clear_removes_all_urls(self, tracker):
        """Clear should remove all processed URLs."""
        tracker.mark_processed("https://example.com/1.pdf")
        tracker.mark_processed("https://example.com/2.pdf")

        tracker.clear()

        assert tracker.get_processed_urls() == []
        stats = tracker.get_statistics()
        assert stats["total_processed"] == 0

    def test_clear_saves_state(self, tracker):
        """Clear should save the cleared state to file."""
        tracker.mark_processed("https://example.com/1.pdf")
        tracker.save()
        tracker.clear()

        # Reload and verify
        tracker2 = StateTracker(tracker.scraper_name)
        assert tracker2.get_processed_urls() == []


class TestRemoveUrl:
    """Test remove_url edge cases."""

    def test_remove_nonexistent_url(self, tracker):
        """Should return False for non-existent URL."""
        result = tracker.remove_url("https://nonexistent.com/doc.pdf")
        assert result is False

    def test_remove_existing_url(self, tracker):
        """Should return True and remove URL."""
        url = "https://example.com/doc.pdf"
        tracker.mark_processed(url)
        assert tracker.remove_url(url) is True
        assert tracker.is_processed(url) is False


class TestGetLastRunInfo:
    """Test get_last_run_info format."""

    def test_fresh_tracker_has_none_last_updated(self, tracker):
        """Fresh tracker should have None last_updated."""
        info = tracker.get_last_run_info()
        assert info["last_updated"] is None
        assert info["processed_count"] == 0

    def test_after_save_has_last_updated(self, tracker):
        """After save, last_updated should be set."""
        tracker.mark_processed("https://example.com/doc.pdf")
        tracker.save()

        info = tracker.get_last_run_info()
        assert info["last_updated"] is not None
        assert info["processed_count"] == 1
        assert info["statistics"]["total_processed"] == 1


class TestCustomValues:
    """Test set_value/get_value."""

    def test_set_and_get_custom_value(self, tracker):
        """Should store and retrieve custom values."""
        tracker.set_value("last_scrape_date", "2024-01-15")
        assert tracker.get_value("last_scrape_date") == "2024-01-15"

    def test_get_missing_value_returns_default(self, tracker):
        """Should return default for missing keys."""
        assert tracker.get_value("nonexistent", default="fallback") == "fallback"

    def test_get_value_returns_deep_copy(self, tracker):
        """Returned values should be deep copies."""
        tracker.set_value("nested", {"key": [1, 2, 3]})
        val = tracker.get_value("nested")
        val["key"].append(4)

        # Original should be unmodified
        assert tracker.get_value("nested")["key"] == [1, 2, 3]

    def test_get_state_returns_deep_copy(self, tracker):
        """get_state should return deep copy of full state."""
        tracker.mark_processed("https://example.com/doc.pdf")
        state = tracker.get_state()
        state["processed_urls"]["https://example.com/doc.pdf"]["status"] = "modified"

        # Original should be unmodified
        info = tracker.get_url_info("https://example.com/doc.pdf")
        assert info["status"] == "downloaded"

    def test_url_info_returns_none_for_unknown(self, tracker):
        """get_url_info should return None for unknown URL."""
        assert tracker.get_url_info("https://unknown.com") is None
