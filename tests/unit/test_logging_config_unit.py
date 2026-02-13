"""Tests for app.utils.logging_config — JSON formatter, setup, and helpers."""

import json
import logging
from unittest.mock import patch, MagicMock

import pytest

from app.config import Config
from app.utils.logging_config import (
    JsonFormatter,
    get_logger,
    log_event,
    log_exception,
    setup_logging,
)


# ===========================================================================
# TestJsonFormatter
# ===========================================================================
class TestJsonFormatter:
    def _make_record(self, msg="test message", level=logging.INFO, exc_info=None, extra=None):
        """Create a LogRecord for testing."""
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="test_file.py",
            lineno=42,
            msg=msg,
            args=(),
            exc_info=exc_info,
        )
        if extra is not None:
            record.extra = extra  # type: ignore[attr-defined]
        return record

    def test_basic_format(self):
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = self._make_record("hello world")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["filename"] == "test_file.py"
        assert parsed["lineno"] == 42

    def test_with_exception_info(self):
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = self._make_record("error occurred", exc_info=exc_info)
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]

    def test_with_extra_dict(self):
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = self._make_record("event happened", extra={"scraper": "aemo", "count": 5})
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["scraper"] == "aemo"
        assert parsed["count"] == 5

    def test_extra_dict_skips_reserved_keys(self):
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        # These reserved keys should not overwrite the log entry
        record = self._make_record(
            "event",
            extra={
                "timestamp": "should_be_ignored",
                "level": "should_be_ignored",
                "custom_field": "preserved",
            },
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        # Reserved keys should NOT be overwritten
        assert parsed["level"] == "INFO"  # not "should_be_ignored"
        # Non-reserved key should be added
        assert parsed["custom_field"] == "preserved"


# ===========================================================================
# TestSetupLogging
# ===========================================================================
class TestSetupLogging:
    @pytest.fixture(autouse=True)
    def _cleanup_loggers(self):
        """Clean up test loggers after each test."""
        yield
        for name in ["test_setup", "test_file_setup", "test_no_file", "test_skip_handlers"]:
            logger = logging.getLogger(name)
            logger.handlers.clear()

    def test_creates_console_handler(self):
        with patch.object(Config, "LOG_TO_FILE", False):
            logger = setup_logging(name="test_setup", level="DEBUG", log_to_file=False)
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        assert logger.level == logging.DEBUG

    def test_with_file_handler(self, tmp_path):
        with patch.object(Config, "LOG_TO_FILE", True), \
             patch.object(Config, "LOG_DIR", tmp_path), \
             patch.object(Config, "LOG_FILE_MAX_BYTES", 1024), \
             patch.object(Config, "LOG_FILE_BACKUP_COUNT", 2), \
             patch.object(Config, "LOG_JSON_FORMAT", False):
            logger = setup_logging(name="test_file_setup", level="INFO")
        assert len(logger.handlers) == 2
        # Second handler should be a file handler
        assert hasattr(logger.handlers[1], "baseFilename")

    def test_skips_file_when_log_to_file_false(self):
        with patch.object(Config, "LOG_TO_FILE", False):
            logger = setup_logging(name="test_no_file", level="INFO", log_to_file=True)
        # Only console handler — LOG_TO_FILE=False overrides log_to_file=True
        assert len(logger.handlers) == 1

    def test_skips_adding_handlers_when_already_present(self):
        with patch.object(Config, "LOG_TO_FILE", False):
            logger = setup_logging(name="test_skip_handlers", level="INFO", log_to_file=False)
            handler_count = len(logger.handlers)
            # Call again — should not add more handlers
            logger2 = setup_logging(name="test_skip_handlers", level="INFO", log_to_file=False)
            assert len(logger2.handlers) == handler_count


# ===========================================================================
# TestGetLogger
# ===========================================================================
class TestGetLogger:
    @pytest.fixture(autouse=True)
    def _cleanup_loggers(self):
        yield
        for name in ["scraper.mymodule", "scraper.already", "scraper"]:
            logger = logging.getLogger(name)
            logger.handlers.clear()

    def test_prefixes_with_scraper(self):
        logger = get_logger("mymodule")
        assert logger.name == "scraper.mymodule"

    def test_already_prefixed_not_doubled(self):
        logger = get_logger("scraper.already")
        assert logger.name == "scraper.already"

    def test_sets_up_logging_if_parent_has_no_handlers(self):
        # Ensure parent has no handlers
        parent = logging.getLogger("scraper")
        parent.handlers.clear()
        with patch("app.utils.logging_config.setup_logging") as mock_setup:
            mock_setup.return_value = parent
            get_logger("mymodule")
            mock_setup.assert_called_once()


# ===========================================================================
# TestLogException
# ===========================================================================
class TestLogException:
    def test_logs_with_context(self):
        mock_logger = MagicMock()
        exc = ValueError("test error")
        log_exception(mock_logger, exc, "something.failed", scraper="aemo", page=3)
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert args[0] == "something.failed"
        assert kwargs["exc_info"] is exc
        assert kwargs["extra"]["extra"]["scraper"] == "aemo"

    def test_logs_without_context(self):
        mock_logger = MagicMock()
        exc = RuntimeError("boom")
        log_exception(mock_logger, exc, "simple.error")
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert args[0] == "simple.error"
        assert kwargs["extra"] is None


# ===========================================================================
# TestLogEvent
# ===========================================================================
class TestLogEvent:
    def test_logs_at_specified_level(self):
        mock_logger = MagicMock()
        log_event(mock_logger, "warning", "something.happened", detail="info")
        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert args[0] == "something.happened"
        assert kwargs["extra"]["extra"]["detail"] == "info"

    def test_defaults_to_info_for_unknown_level(self):
        # MagicMock auto-creates attributes, so any getattr succeeds.
        # Use spec to restrict to only known attributes, forcing the fallback.
        mock_logger = MagicMock(spec=["info"])
        log_event(mock_logger, "nonexistent_level", "test.event")
        # Since "nonexistent_level" is not in spec, getattr falls back to logger.info
        mock_logger.info.assert_called_once()
