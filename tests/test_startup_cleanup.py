"""
Startup Cleanup Tests

Tests for the startup cleanup hook that marks stale 'running' pipeline runs as 'failed'.
Run with: pytest tests/test_startup_cleanup.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.api.main import cleanup_stale_pipeline_runs


class TestCleanupStalePipelineRuns:
    """Tests for cleanup_stale_pipeline_runs function."""

    def test_cleans_up_stale_runs(self):
        """Test that stale 'running' runs are marked as 'failed'."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1,), (2,), (3,)]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("src.api.main.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = cleanup_stale_pipeline_runs()

        assert result == 3
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

        # Verify the SQL updates status to 'failed'
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "status = 'failed'" in sql_call
        assert "WHERE status = 'running'" in sql_call

    def test_returns_zero_when_no_stale_runs(self):
        """Test that zero is returned when no stale runs exist."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("src.api.main.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = cleanup_stale_pipeline_runs()

        assert result == 0

    def test_handles_database_error_gracefully(self):
        """Test that database errors are caught and logged."""
        with patch("src.api.main.get_connection") as mock_get_conn:
            mock_get_conn.side_effect = Exception("Database connection failed")

            result = cleanup_stale_pipeline_runs()

        assert result == 0

    def test_sets_error_message_on_stale_runs(self):
        """Test that stale runs get an appropriate error message."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(5,)]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("src.api.main.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            cleanup_stale_pipeline_runs()

        sql_call = mock_cursor.execute.call_args[0][0]
        assert "error_message = 'Process terminated unexpectedly" in sql_call

    def test_sets_completed_at_timestamp(self):
        """Test that stale runs get a completed_at timestamp."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(7,)]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("src.api.main.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            cleanup_stale_pipeline_runs()

        sql_call = mock_cursor.execute.call_args[0][0]
        assert "completed_at = NOW()" in sql_call
