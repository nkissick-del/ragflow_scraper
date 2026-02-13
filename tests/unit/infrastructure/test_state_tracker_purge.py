"""Tests for StateTracker.purge() method."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.state_tracker import StateTracker


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Create temporary state, download, and metadata directories."""
    state_dir = tmp_path / "state"
    download_dir = tmp_path / "downloads"
    metadata_dir = tmp_path / "metadata"
    state_dir.mkdir()
    download_dir.mkdir()
    metadata_dir.mkdir()
    return tmp_path


@pytest.fixture
def tracker(tmp_state_dir):
    """Create a StateTracker with mocked Config paths."""
    with patch("app.services.state_tracker.Config") as mock_config:
        mock_config.STATE_DIR = tmp_state_dir / "state"
        mock_config.DOWNLOAD_DIR = tmp_state_dir / "downloads"
        mock_config.METADATA_DIR = tmp_state_dir / "metadata"
        with patch("app.services.state_tracker.get_logger"):
            t = StateTracker("test-scraper")
        yield t, tmp_state_dir, mock_config


class TestPurge:
    def test_purge_empty_state(self, tracker):
        """Purge with no processed URLs and no files."""
        t, tmp_path, mock_config = tracker
        counts = t.purge()
        assert counts["urls_cleared"] == 0
        assert counts["files_deleted"] == 0
        assert counts["metadata_deleted"] == 0

    def test_purge_clears_urls(self, tracker):
        """Purge clears processed URLs."""
        t, tmp_path, mock_config = tracker
        t.mark_processed("http://example.com/a")
        t.mark_processed("http://example.com/b")
        assert len(t.get_processed_urls()) == 2

        counts = t.purge()
        assert counts["urls_cleared"] == 2
        assert len(t.get_processed_urls()) == 0

    def test_purge_resets_statistics(self, tracker):
        """Purge resets all statistics to zero."""
        t, tmp_path, mock_config = tracker
        t.mark_processed("http://example.com/a", status="downloaded")
        t.mark_processed("http://example.com/b", status="failed")
        stats = t.get_statistics()
        assert stats["total_processed"] == 2

        t.purge()
        stats = t.get_statistics()
        assert stats["total_processed"] == 0
        assert stats["total_downloaded"] == 0
        assert stats["total_failed"] == 0

    def test_purge_deletes_download_files(self, tracker):
        """Purge deletes files in the download directory."""
        t, tmp_path, mock_config = tracker
        dl_dir = tmp_path / "downloads" / "test-scraper"
        dl_dir.mkdir(parents=True)
        (dl_dir / "doc1.pdf").write_text("pdf content")
        (dl_dir / "doc2.pdf").write_text("pdf content")

        counts = t.purge()
        assert counts["files_deleted"] == 2
        assert not list(dl_dir.iterdir())

    def test_purge_deletes_metadata_files(self, tracker):
        """Purge deletes files in the metadata directory."""
        t, tmp_path, mock_config = tracker
        meta_dir = tmp_path / "metadata" / "test-scraper"
        meta_dir.mkdir(parents=True)
        (meta_dir / "doc1.json").write_text("{}")
        (meta_dir / "doc2.json").write_text("{}")
        (meta_dir / "doc3.json").write_text("{}")

        counts = t.purge()
        assert counts["metadata_deleted"] == 3

    def test_purge_handles_missing_directories(self, tracker):
        """Purge gracefully handles non-existent directories."""
        t, tmp_path, mock_config = tracker
        # Don't create scraper subdirectories
        counts = t.purge()
        assert counts["files_deleted"] == 0
        assert counts["metadata_deleted"] == 0

    def test_purge_deletes_subdirectories(self, tracker):
        """Purge removes subdirectories within download dir."""
        t, tmp_path, mock_config = tracker
        dl_dir = tmp_path / "downloads" / "test-scraper"
        dl_dir.mkdir(parents=True)
        sub_dir = dl_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "nested.pdf").write_text("pdf")
        (dl_dir / "top.pdf").write_text("pdf")

        counts = t.purge()
        assert counts["files_deleted"] == 2  # 1 file + 1 subdirectory


class TestDeleteDirectoryContents:
    def test_nonexistent_directory(self):
        """Returns 0 for non-existent directory."""
        count = StateTracker._delete_directory_contents(Path("/nonexistent"))
        assert count == 0

    def test_empty_directory(self, tmp_path):
        """Returns 0 for empty directory."""
        count = StateTracker._delete_directory_contents(tmp_path)
        assert count == 0

    def test_files_only(self, tmp_path):
        """Deletes files and returns count."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        count = StateTracker._delete_directory_contents(tmp_path)
        assert count == 2
        assert not list(tmp_path.iterdir())
