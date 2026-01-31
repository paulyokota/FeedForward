"""Test that pipeline background tasks have access to environment variables.

Issue #189: Pipeline API runs stuck at fetched=0 - environment variable not inherited
by thread pool workers spawned by anyio.to_thread.run_sync().
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestPipelineEnvLoading:
    """Tests for Issue #189: env var loading in background tasks."""

    def test_pipeline_task_fails_fast_without_token(self):
        """Pipeline should fail early if INTERCOM_ACCESS_TOKEN is missing.

        Prevents pipeline from appearing to start successfully then silently
        failing during fetch phase (stuck at fetched=0). Issue #189.
        """
        # Import inside test to ensure patches apply correctly
        from src.api.routers import pipeline

        # Clear the token from env
        with patch.dict(os.environ, {}, clear=True):
            # Mock database connection at the source module (where it's imported from)
            with patch("src.db.connection.get_connection") as mock_conn:
                mock_cursor = MagicMock()
                mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

                # Prevent actual .env file read (simulate missing token)
                with patch("dotenv.load_dotenv"):
                    # The fail-fast check happens before run_pipeline_async is called,
                    # so we don't need to patch it - function returns early
                    pipeline._run_pipeline_task(
                        run_id=999,
                        days=1,
                        max_conversations=1,
                        dry_run=True,
                        concurrency=1,
                    )

                # Should have executed the fail-fast database update
                mock_cursor.execute.assert_called_once()
                call_args = mock_cursor.execute.call_args
                sql = call_args[0][0]
                params = call_args[0][1]

                assert "status = 'failed'" in sql
                assert "INTERCOM_ACCESS_TOKEN not configured" in params

    def test_intercom_client_gets_token_after_load_dotenv(self):
        """Verify load_dotenv() makes token available for IntercomClient.

        This tests the fix mechanism: load_dotenv() reads .env file and
        populates os.environ, making INTERCOM_ACCESS_TOKEN available to
        IntercomClient when it initializes in the thread pool worker.
        """
        from dotenv import load_dotenv

        # Create temp .env file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("INTERCOM_ACCESS_TOKEN=test_token_12345\n")
            env_path = Path(f.name)

        try:
            # Clear env, then load from temp file
            with patch.dict(os.environ, {}, clear=True):
                assert os.getenv("INTERCOM_ACCESS_TOKEN") is None

                load_dotenv(env_path)

                # Now token should be available
                token = os.getenv("INTERCOM_ACCESS_TOKEN")
                assert token == "test_token_12345"
        finally:
            env_path.unlink()
