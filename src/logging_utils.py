"""Shared logging utilities (Issue #185).

This module provides a SafeStreamHandler that gracefully handles broken pipes
and closed file descriptors, which can occur when running as a background task
(e.g., when uvicorn reloads during a pipeline run).
"""
import logging


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that ignores broken pipe and closed file errors.

    When running as a background task, stdout can be closed (e.g., uvicorn reload).
    Standard StreamHandler raises BrokenPipeError or ValueError in this case.
    This handler silently ignores these errors while still logging to file handlers.
    """

    def emit(self, record):
        try:
            super().emit(record)
        except BrokenPipeError:
            pass  # stdout closed, ignore silently
        except ValueError:
            pass  # I/O operation on closed file


def configure_safe_logging(level=logging.INFO):
    """Configure root logger with SafeStreamHandler.

    Call this in standalone scripts that might run with closed stdout.
    Safe to call multiple times (guards against duplicate handlers).

    Args:
        level: Logging level to set (default: INFO)
    """
    logger = logging.getLogger()
    # Avoid duplicate handlers (e.g., uvicorn reload loops)
    if not any(isinstance(h, SafeStreamHandler) for h in logger.handlers):
        handler = SafeStreamHandler()  # Defaults to sys.stdout
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handler.setLevel(level)
        logger.addHandler(handler)
        # For CLI scripts, ensure we can see our output.
        # Some libraries (e.g., OpenAI) set root logger to WARNING during import.
        # We override if level is more restrictive than requested.
        if logger.level == logging.NOTSET or logger.level > level:
            logger.setLevel(level)
