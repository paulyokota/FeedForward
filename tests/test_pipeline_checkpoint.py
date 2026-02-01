"""
Pipeline Checkpoint and Resume Tests

Tests for Issue #202: Intercom backfill resumability.
Covers checkpoint save/load, resume eligibility, and edge cases.

Run with: pytest tests/test_pipeline_checkpoint.py -v
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.deps import get_db
import src.api.routers.pipeline as pipeline_module


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    return mock_conn


@pytest.fixture
def client(mock_db):
    """Create a test client with overridden dependencies."""
    app.dependency_overrides[get_db] = lambda: mock_db

    # Clear module state
    pipeline_module._active_runs.clear()
    pipeline_module._active_checkpoints.clear()

    yield TestClient(app)

    # Clean up
    app.dependency_overrides.clear()
    pipeline_module._active_runs.clear()
    pipeline_module._active_checkpoints.clear()


# -----------------------------------------------------------------------------
# _save_checkpoint Unit Tests
# -----------------------------------------------------------------------------


class TestSaveCheckpoint:
    """Tests for _save_checkpoint helper function."""

    def test_save_checkpoint_with_counts(self):
        """Test saving checkpoint persists counts with GREATEST."""
        run_id = 42
        checkpoint = {
            "phase": "classification",
            "intercom_cursor": "abc123",
            "counts": {
                "fetched": 100,
                "classified": 95,
                "stored": 90,
            }
        }

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            pipeline_module._save_checkpoint(run_id, checkpoint)

            # Verify SQL uses GREATEST for monotonic updates
            call_args = mock_cursor.execute.call_args
            sql = call_args[0][0]
            assert "GREATEST" in sql
            assert "conversations_fetched" in sql
            assert "conversations_classified" in sql
            assert "conversations_stored" in sql

    def test_save_checkpoint_empty_clears(self):
        """Test saving empty checkpoint clears the checkpoint."""
        run_id = 42
        checkpoint = {}

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            pipeline_module._save_checkpoint(run_id, checkpoint)

            # Should still execute update with empty checkpoint
            mock_cursor.execute.assert_called_once()


class TestSaveCheckpointBestEffort:
    """Tests for _save_checkpoint_best_effort helper."""

    def test_saves_from_active_checkpoints(self):
        """Test best-effort save uses in-memory checkpoint."""
        run_id = 42
        checkpoint = {"phase": "classification", "intercom_cursor": "xyz"}
        pipeline_module._active_checkpoints[run_id] = checkpoint

        with patch.object(pipeline_module, "_save_checkpoint") as mock_save:
            pipeline_module._save_checkpoint_best_effort(run_id)

            mock_save.assert_called_once_with(run_id, checkpoint)
            # Should be removed from active checkpoints
            assert run_id not in pipeline_module._active_checkpoints

    def test_does_nothing_if_no_checkpoint(self):
        """Test best-effort save is no-op if no checkpoint exists."""
        run_id = 42
        # No checkpoint in _active_checkpoints

        with patch.object(pipeline_module, "_save_checkpoint") as mock_save:
            pipeline_module._save_checkpoint_best_effort(run_id)

            mock_save.assert_not_called()

    def test_handles_save_error_gracefully(self):
        """Test best-effort save doesn't raise on error."""
        run_id = 42
        pipeline_module._active_checkpoints[run_id] = {"phase": "classification"}

        with patch.object(pipeline_module, "_save_checkpoint", side_effect=Exception("DB error")):
            # Should not raise
            pipeline_module._save_checkpoint_best_effort(run_id)

            # Should still clean up
            assert run_id not in pipeline_module._active_checkpoints


# -----------------------------------------------------------------------------
# _find_most_recent_resumable_run Unit Tests
# -----------------------------------------------------------------------------


class TestFindResumableRun:
    """Tests for _find_most_recent_resumable_run helper function."""

    def test_finds_matching_run(self):
        """Test finding the most recent resumable run."""
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 8, tzinfo=timezone.utc)
        checkpoint = {"phase": "classification", "intercom_cursor": "abc"}

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                "id": 42,
                "checkpoint": checkpoint,
                "date_from": date_from,
                "date_to": date_to,
                "auto_create_stories": True,
            }
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            # No date parameters - finds most recent resumable run
            result = pipeline_module._find_most_recent_resumable_run()

            assert result is not None
            assert result["id"] == 42
            assert result["checkpoint"] == checkpoint

    def test_returns_none_if_no_match(self):
        """Test returns None when no resumable run exists."""
        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = pipeline_module._find_most_recent_resumable_run()

            assert result is None

    def test_returns_none_if_wrong_phase(self):
        """Test returns None if checkpoint phase is not classification."""
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 8, tzinfo=timezone.utc)
        # Checkpoint has phase "embedding_generation" - not resumable
        checkpoint = {"phase": "embedding_generation"}

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                "id": 42,
                "checkpoint": checkpoint,
                "date_from": date_from,
                "date_to": date_to,
                "auto_create_stories": False,
            }
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = pipeline_module._find_most_recent_resumable_run()

            assert result is None


# -----------------------------------------------------------------------------
# _find_resumable_run_by_id Unit Tests
# -----------------------------------------------------------------------------


class TestFindResumableRunById:
    """Tests for _find_resumable_run_by_id helper function."""

    def test_finds_run_by_id(self):
        """Test finding a run by explicit ID."""
        checkpoint = {"phase": "classification", "intercom_cursor": "abc"}

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                "id": 42,
                "checkpoint": checkpoint,
                "date_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "date_to": datetime(2026, 1, 8, tzinfo=timezone.utc),
                "auto_create_stories": True,
            }
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = pipeline_module._find_resumable_run_by_id(42)

            assert result is not None
            assert result["id"] == 42

    def test_returns_none_for_nonexistent_id(self):
        """Test returns None when run ID doesn't exist."""
        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = pipeline_module._find_resumable_run_by_id(999)

            assert result is None

    def test_returns_none_if_wrong_phase(self):
        """Test returns None when checkpoint phase is not classification."""
        checkpoint = {"phase": "theme_extraction", "intercom_cursor": "abc"}

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {
                "id": 42,
                "checkpoint": checkpoint,
                "date_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "date_to": datetime(2026, 1, 8, tzinfo=timezone.utc),
                "auto_create_stories": False,
            }
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result = pipeline_module._find_resumable_run_by_id(42)

            assert result is None


# -----------------------------------------------------------------------------
# Resume Endpoint Tests
# -----------------------------------------------------------------------------


class TestResumeEndpoint:
    """Tests for POST /api/pipeline/run with resume=true."""

    def test_resume_no_eligible_run_returns_400(self, client, mock_db):
        """Test resume with no eligible run returns 400."""
        with patch.object(pipeline_module, "_find_most_recent_resumable_run", return_value=None):
            response = client.post(
                "/api/pipeline/run",
                json={"days": 7, "resume": True}
            )

            assert response.status_code == 400
            data = response.json()
            assert "No resumable run found" in data["detail"]

    def test_resume_with_valid_run(self, client, mock_db):
        """Test resume with valid run succeeds."""
        date_from = datetime.now(timezone.utc) - timedelta(days=7)
        date_to = datetime.now(timezone.utc)
        checkpoint = {"phase": "classification", "intercom_cursor": "abc123"}

        existing_run = {
            "id": 42,
            "checkpoint": checkpoint,
            "date_from": date_from,
            "date_to": date_to,
            "auto_create_stories": True,
        }

        # Mock cursor for the UPDATE query
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch.object(pipeline_module, "_find_most_recent_resumable_run", return_value=existing_run):
            with patch.object(pipeline_module, "_cleanup_terminal_runs"):
                with patch.object(pipeline_module, "_run_pipeline_async"):
                    response = client.post(
                        "/api/pipeline/run",
                        json={"days": 7, "resume": True}
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["run_id"] == 42
                    assert "resumed" in data["message"].lower()

    def test_resume_with_active_run_returns_409(self, client, mock_db):
        """Test resume fails if another run is active."""
        pipeline_module._active_runs[99] = "running"

        response = client.post(
            "/api/pipeline/run",
            json={"days": 7, "resume": True}
        )

        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]

    def test_resume_with_explicit_run_id(self, client, mock_db):
        """Test resume with explicit resume_run_id bypasses date matching."""
        date_from = datetime.now(timezone.utc) - timedelta(days=30)  # Different from request
        date_to = datetime.now(timezone.utc) - timedelta(days=23)
        checkpoint = {"phase": "classification", "intercom_cursor": "xyz789"}

        existing_run = {
            "id": 100,
            "checkpoint": checkpoint,
            "date_from": date_from,
            "date_to": date_to,
            "auto_create_stories": False,
        }

        # Mock cursor for the UPDATE query
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch.object(pipeline_module, "_find_resumable_run_by_id", return_value=existing_run) as mock_by_id:
            with patch.object(pipeline_module, "_find_most_recent_resumable_run") as mock_most_recent:
                with patch.object(pipeline_module, "_cleanup_terminal_runs"):
                    with patch.object(pipeline_module, "_run_pipeline_async"):
                        response = client.post(
                            "/api/pipeline/run",
                            json={"days": 7, "resume": True, "resume_run_id": 100}
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["run_id"] == 100
                        # Should use by-ID lookup, not most-recent lookup
                        mock_by_id.assert_called_once_with(100)
                        mock_most_recent.assert_not_called()

    def test_resume_run_id_not_found_returns_400(self, client, mock_db):
        """Test resume with invalid resume_run_id returns 400."""
        with patch.object(pipeline_module, "_find_resumable_run_by_id", return_value=None):
            with patch.object(pipeline_module, "_cleanup_terminal_runs"):
                response = client.post(
                    "/api/pipeline/run",
                    json={"days": 7, "resume": True, "resume_run_id": 999}
                )

                assert response.status_code == 400
                assert "999" in response.json()["detail"]
                assert "not resumable" in response.json()["detail"]


# -----------------------------------------------------------------------------
# Fresh Run Tests (non-resume)
# -----------------------------------------------------------------------------


class TestFreshRunEndpoint:
    """Tests for POST /api/pipeline/run without resume."""

    def test_fresh_run_creates_new_record(self, client, mock_db):
        """Test fresh run creates new pipeline_runs record."""
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = {"id": 123}
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch.object(pipeline_module, "_cleanup_terminal_runs"):
            with patch.object(pipeline_module, "_run_pipeline_async"):
                response = client.post(
                    "/api/pipeline/run",
                    json={"days": 7, "resume": False}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["run_id"] == 123
                assert data["status"] == "started"

                # Verify INSERT was called
                calls = mock_cursor.execute.call_args_list
                insert_call = [c for c in calls if "INSERT" in str(c)]
                assert len(insert_call) > 0


# -----------------------------------------------------------------------------
# Intercom Client Cursor Tests
# -----------------------------------------------------------------------------


class TestIntercomClientCursor:
    """Tests for initial_cursor parameter in IntercomClient."""

    @pytest.mark.asyncio
    async def test_initial_cursor_used_on_first_request(self):
        """Test that initial_cursor is used on the first API request."""
        from src.intercom_client import IntercomClient
        from unittest.mock import AsyncMock
        from contextlib import asynccontextmanager

        client = IntercomClient()
        initial_cursor = "test_cursor_abc"
        cursors_seen = []

        def cursor_callback(cursor):
            cursors_seen.append(cursor)

        # Create a proper async context manager mock
        @asynccontextmanager
        async def mock_session_cm():
            yield MagicMock()

        with patch.object(client, "_get_aiohttp_session", mock_session_cm):
            mock_request = AsyncMock(return_value={
                "conversations": [],
                "pages": {}
            })
            with patch.object(client, "_request_with_retry_async", mock_request):
                # Consume the async generator
                results = []
                async for conv in client.search_by_date_range_async(
                    start_timestamp=1000,
                    end_timestamp=2000,
                    initial_cursor=initial_cursor,
                    cursor_callback=cursor_callback,
                ):
                    results.append(conv)

                # Verify request was called
                mock_request.assert_called()
                call_args = mock_request.call_args
                json_data = call_args[1].get("json_data") or call_args[0][2]

                # The initial cursor should be in pagination
                assert json_data["pagination"]["starting_after"] == initial_cursor

    @pytest.mark.asyncio
    async def test_cursor_callback_called_after_each_page(self):
        """Test that cursor_callback is called with new cursor after each page."""
        from src.intercom_client import IntercomClient
        from unittest.mock import AsyncMock
        from contextlib import asynccontextmanager

        client = IntercomClient()
        cursors_received = []

        def cursor_callback(cursor):
            cursors_received.append(cursor)

        @asynccontextmanager
        async def mock_session_cm():
            yield MagicMock()

        with patch.object(client, "_get_aiohttp_session", mock_session_cm):
            # First call returns conversations with next cursor
            # Second call returns empty
            mock_request = AsyncMock(side_effect=[
                {
                    "conversations": [{"id": "1"}],
                    "pages": {"next": {"starting_after": "cursor_page_2"}}
                },
                {
                    "conversations": [],
                    "pages": {}
                },
            ])
            with patch.object(client, "_request_with_retry_async", mock_request):
                results = []
                async for conv in client.search_by_date_range_async(
                    start_timestamp=1000,
                    end_timestamp=2000,
                    cursor_callback=cursor_callback,
                ):
                    results.append(conv)

                # Should have received cursor_page_2 from first response
                assert "cursor_page_2" in cursors_received


# -----------------------------------------------------------------------------
# Classification Pipeline Checkpoint Tests
# -----------------------------------------------------------------------------


class TestClassificationPipelineCheckpoint:
    """Tests for checkpoint logic in classification_pipeline.py."""

    def test_save_classification_checkpoint(self):
        """Test _save_classification_checkpoint helper."""
        from src.classification_pipeline import _save_classification_checkpoint

        run_id = 42
        cursor = "test_cursor"
        fetched = 100

        # Patch at the source module since import happens inside function
        with patch("src.api.routers.pipeline._save_checkpoint") as mock_save:
            with patch.dict("src.api.routers.pipeline._active_checkpoints", {}, clear=True):
                _save_classification_checkpoint(run_id, cursor, fetched)

                mock_save.assert_called_once()
                call_args = mock_save.call_args
                assert call_args[0][0] == run_id
                checkpoint = call_args[0][1]
                assert checkpoint["phase"] == "classification"
                assert checkpoint["intercom_cursor"] == cursor
                assert checkpoint["counts"]["fetched"] == fetched

    def test_clear_checkpoint(self):
        """Test _clear_checkpoint helper."""
        from src.classification_pipeline import _clear_checkpoint

        run_id = 42

        # Patch at the source module since import happens inside function
        with patch("src.api.routers.pipeline._save_checkpoint") as mock_save:
            with patch.dict("src.api.routers.pipeline._active_checkpoints", {run_id: {"test": 1}}):
                _clear_checkpoint(run_id)

                # Should save empty checkpoint
                mock_save.assert_called_once_with(run_id, {})
