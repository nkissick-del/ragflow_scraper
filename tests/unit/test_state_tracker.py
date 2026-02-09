
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
