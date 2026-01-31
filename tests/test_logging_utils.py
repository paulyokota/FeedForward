"""Tests for logging utilities (Issue #185)."""
import io
import logging
import pytest

from src.logging_utils import SafeStreamHandler, configure_safe_logging


class TestSafeStreamHandler:
    """Tests for SafeStreamHandler exception handling."""

    def test_catches_broken_pipe_error(self):
        """SafeStreamHandler should silently ignore BrokenPipeError."""
        handler = SafeStreamHandler(stream=io.StringIO())

        # Override emit to raise BrokenPipeError
        original_emit = logging.StreamHandler.emit

        def broken_emit(self, record):
            raise BrokenPipeError("stdout closed")

        logging.StreamHandler.emit = broken_emit
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test message",
                args=(),
                exc_info=None,
            )
            # Should not raise
            handler.emit(record)
        finally:
            logging.StreamHandler.emit = original_emit

    def test_catches_value_error_closed_file(self):
        """SafeStreamHandler should silently ignore ValueError (closed file)."""
        handler = SafeStreamHandler(stream=io.StringIO())

        original_emit = logging.StreamHandler.emit

        def closed_emit(self, record):
            raise ValueError("I/O operation on closed file")

        logging.StreamHandler.emit = closed_emit
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test message",
                args=(),
                exc_info=None,
            )
            # Should not raise
            handler.emit(record)
        finally:
            logging.StreamHandler.emit = original_emit

    def test_reraises_other_exceptions(self):
        """SafeStreamHandler should re-raise non-pipe/file errors."""
        handler = SafeStreamHandler(stream=io.StringIO())

        original_emit = logging.StreamHandler.emit

        def bad_emit(self, record):
            raise RuntimeError("unexpected error")

        logging.StreamHandler.emit = bad_emit
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test message",
                args=(),
                exc_info=None,
            )
            with pytest.raises(RuntimeError, match="unexpected error"):
                handler.emit(record)
        finally:
            logging.StreamHandler.emit = original_emit

    def test_normal_logging_works(self):
        """SafeStreamHandler should work normally when no errors."""
        stream = io.StringIO()
        handler = SafeStreamHandler(stream=stream)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        assert "hello world" in stream.getvalue()


class TestConfigureSafeLogging:
    """Tests for configure_safe_logging function."""

    def setup_method(self):
        """Clean up root logger before each test."""
        root = logging.getLogger()
        # Remove all handlers
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        # Reset level
        root.setLevel(logging.WARNING)

    def teardown_method(self):
        """Clean up root logger after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            if isinstance(handler, SafeStreamHandler):
                root.removeHandler(handler)

    def test_adds_safe_stream_handler(self):
        """configure_safe_logging should add a SafeStreamHandler."""
        root = logging.getLogger()
        assert not any(isinstance(h, SafeStreamHandler) for h in root.handlers)

        configure_safe_logging()

        assert any(isinstance(h, SafeStreamHandler) for h in root.handlers)

    def test_prevents_duplicate_handlers(self):
        """configure_safe_logging should not add duplicate handlers."""
        root = logging.getLogger()

        configure_safe_logging()
        configure_safe_logging()
        configure_safe_logging()

        safe_handlers = [h for h in root.handlers if isinstance(h, SafeStreamHandler)]
        assert len(safe_handlers) == 1

    def test_sets_log_level_to_info(self):
        """configure_safe_logging should set level to INFO."""
        root = logging.getLogger()
        root.setLevel(logging.WARNING)  # Start with WARNING

        configure_safe_logging()

        assert root.level == logging.INFO

    def test_respects_more_permissive_level(self):
        """configure_safe_logging should not override DEBUG level."""
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)  # More permissive than INFO

        configure_safe_logging()

        # Should not override since DEBUG is more permissive than INFO
        assert root.level == logging.DEBUG

    def test_accepts_custom_level(self):
        """configure_safe_logging should accept custom log level."""
        root = logging.getLogger()
        root.setLevel(logging.WARNING)

        configure_safe_logging(level=logging.DEBUG)

        assert root.level == logging.DEBUG
