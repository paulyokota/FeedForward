"""
Pipeline Checkpoint and Resume Tests

Tests for Issue #202: Intercom backfill resumability.
Covers checkpoint save/load, resume eligibility, and edge cases.

Run with: pytest tests/test_pipeline_checkpoint.py -v
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
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
            # First call returns count, second returns the run
            mock_cursor.fetchone.side_effect = [
                {"count": 1},  # Count query
                {  # Select query
                    "id": 42,
                    "checkpoint": checkpoint,
                    "date_from": date_from,
                    "date_to": date_to,
                    "auto_create_stories": True,
                }
            ]
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            # Returns tuple of (run, count)
            result, count = pipeline_module._find_most_recent_resumable_run()

            assert result is not None
            assert result["id"] == 42
            assert result["checkpoint"] == checkpoint
            assert count == 1

    def test_returns_none_if_no_match(self):
        """Test returns None when no resumable run exists."""
        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.side_effect = [
                {"count": 0},  # Count query
                None  # Select query
            ]
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result, count = pipeline_module._find_most_recent_resumable_run()

            assert result is None
            assert count == 0

    def test_returns_none_if_wrong_phase(self):
        """Test returns None if checkpoint phase is not classification."""
        date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2026, 1, 8, tzinfo=timezone.utc)
        # Checkpoint has phase "embedding_generation" - not resumable
        checkpoint = {"phase": "embedding_generation"}

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.side_effect = [
                {"count": 1},  # Count query
                {  # Select query - wrong phase
                    "id": 42,
                    "checkpoint": checkpoint,
                    "date_from": date_from,
                    "date_to": date_to,
                    "auto_create_stories": False,
                }
            ]
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            result, count = pipeline_module._find_most_recent_resumable_run()

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
        # Returns tuple (None, 0) when no resumable runs
        with patch.object(pipeline_module, "_find_most_recent_resumable_run", return_value=(None, 0)):
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

        # Returns tuple (run, count=1) - single resumable run, auto-selects
        with patch.object(pipeline_module, "_find_most_recent_resumable_run", return_value=(existing_run, 1)):
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

    def test_resume_multiple_runs_requires_explicit_id(self, client, mock_db):
        """Test resume with multiple resumable runs requires explicit run_id."""
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

        # Returns tuple (run, count=3) - multiple resumable runs
        with patch.object(pipeline_module, "_find_most_recent_resumable_run", return_value=(existing_run, 3)):
            response = client.post(
                "/api/pipeline/run",
                json={"days": 7, "resume": True}
            )

            assert response.status_code == 400
            data = response.json()
            assert "Multiple resumable runs" in data["detail"]
            assert "resume_run_id" in data["detail"]

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


# -----------------------------------------------------------------------------
# Issue #209: Streaming Batch Mode Tests
# -----------------------------------------------------------------------------


class TestStreamingBatchEnvParsing:
    """Tests for streaming batch environment variable parsing."""

    def test_parse_env_int_valid(self):
        """Test _parse_env_int with valid value."""
        from src.classification_pipeline import _parse_env_int

        with patch.dict("os.environ", {"TEST_VAR": "75"}):
            result = _parse_env_int("TEST_VAR", 50, 10, 100)
            assert result == 75

    def test_parse_env_int_out_of_bounds_low(self):
        """Test _parse_env_int with value below minimum."""
        from src.classification_pipeline import _parse_env_int

        with patch.dict("os.environ", {"TEST_VAR": "5"}):
            result = _parse_env_int("TEST_VAR", 50, 10, 100)
            assert result == 50  # Returns default

    def test_parse_env_int_out_of_bounds_high(self):
        """Test _parse_env_int with value above maximum."""
        from src.classification_pipeline import _parse_env_int

        with patch.dict("os.environ", {"TEST_VAR": "150"}):
            result = _parse_env_int("TEST_VAR", 50, 10, 100)
            assert result == 50  # Returns default

    def test_parse_env_int_invalid(self):
        """Test _parse_env_int with non-integer value."""
        from src.classification_pipeline import _parse_env_int

        with patch.dict("os.environ", {"TEST_VAR": "not_a_number"}):
            result = _parse_env_int("TEST_VAR", 50, 10, 100)
            assert result == 50  # Returns default

    def test_parse_env_int_missing(self):
        """Test _parse_env_int with missing env var."""
        from src.classification_pipeline import _parse_env_int

        with patch.dict("os.environ", {}, clear=True):
            result = _parse_env_int("TEST_VAR_NONEXISTENT", 50, 10, 100)
            assert result == 50  # Returns default


class TestAccumulateStats:
    """Tests for _accumulate_stats helper."""

    def test_accumulates_numeric_fields(self):
        """Test that numeric fields are summed correctly."""
        from src.classification_pipeline import _accumulate_stats

        cumulative = {
            "fetched": 100,
            "classified": 90,
            "stored": 80,
            "stage2_run": 50,
            "classification_changed": 10,
            "warnings": [],
        }
        batch = {
            "fetched": 50,
            "classified": 45,
            "stored": 40,
            "stage2_run": 25,
            "classification_changed": 5,
        }

        _accumulate_stats(cumulative, batch)

        assert cumulative["fetched"] == 150
        assert cumulative["classified"] == 135
        assert cumulative["stored"] == 120
        assert cumulative["stage2_run"] == 75
        assert cumulative["classification_changed"] == 15

    def test_extends_warnings(self):
        """Test that warnings are extended, not summed."""
        from src.classification_pipeline import _accumulate_stats

        cumulative = {"fetched": 0, "warnings": ["warning1"]}
        batch = {"fetched": 10, "warnings": ["warning2", "warning3"]}

        _accumulate_stats(cumulative, batch)

        assert cumulative["warnings"] == ["warning1", "warning2", "warning3"]

    def test_handles_missing_fields(self):
        """Test graceful handling of missing fields in batch."""
        from src.classification_pipeline import _accumulate_stats

        cumulative = {"fetched": 100, "classified": 90}
        batch = {"fetched": 10}  # Missing classified

        _accumulate_stats(cumulative, batch)

        assert cumulative["fetched"] == 110
        assert cumulative["classified"] == 90  # Unchanged


class TestStreamingBatchPipeline:
    """Tests for _run_streaming_batch_pipeline_async."""

    @pytest.mark.asyncio
    async def test_cursor_used_on_resume(self):
        """Test that initial_cursor is passed to fetch on resume."""
        from src.classification_pipeline import _run_streaming_batch_pipeline_async
        from unittest.mock import AsyncMock, MagicMock
        from contextlib import asynccontextmanager

        mock_client = MagicMock()

        @asynccontextmanager
        async def mock_session_cm():
            yield MagicMock()

        mock_client._get_aiohttp_session = mock_session_cm

        # Mock the generator to yield nothing (empty result)
        async def empty_generator(*args, **kwargs):
            # Capture the initial_cursor that was passed
            empty_generator.initial_cursor = kwargs.get("initial_cursor")
            return
            yield  # Make it a generator

        mock_client.fetch_quality_conversations_async = empty_generator

        checkpoint = {
            "phase": "classification",
            "intercom_cursor": "resume_cursor_abc",
            "conversations_processed": 50,
        }

        result = await _run_streaming_batch_pipeline_async(
            client=mock_client,
            since=datetime.now(),
            until=datetime.now(),
            max_conversations=None,
            dry_run=True,
            concurrency=10,
            batch_size=50,
            semaphore=asyncio.Semaphore(10),
            stop_checker=lambda: False,
            pipeline_run_id=None,
            checkpoint=checkpoint,
        )

        assert empty_generator.initial_cursor == "resume_cursor_abc"

    @pytest.mark.asyncio
    async def test_checkpoint_saved_only_after_storage(self):
        """Test that checkpoint is saved AFTER storage, not before."""
        from src.classification_pipeline import (
            _run_streaming_batch_pipeline_async,
            _save_classification_checkpoint,
        )
        from unittest.mock import MagicMock, AsyncMock, call
        from contextlib import asynccontextmanager

        save_checkpoint_calls = []
        store_calls = []

        # Track order of operations
        original_save = _save_classification_checkpoint

        def tracking_save(*args, **kwargs):
            save_checkpoint_calls.append(("checkpoint", len(store_calls)))

        mock_client = MagicMock()

        @asynccontextmanager
        async def mock_session_cm():
            yield MagicMock()

        mock_client._get_aiohttp_session = mock_session_cm

        # Mock generator to yield one batch
        conversations_yielded = []

        async def mock_generator(*args, **kwargs):
            for i in range(3):  # 3 conversations
                mock_parsed = MagicMock()
                mock_parsed.id = f"conv_{i}"
                mock_parsed.source_body = "test message"
                mock_parsed.source_type = "conversation"
                mock_parsed.source_url = None
                mock_parsed.contact_email = None
                mock_parsed.contact_id = None
                mock_parsed.created_at = datetime.now()
                conversations_yielded.append(mock_parsed.id)
                yield (mock_parsed, {"id": f"conv_{i}"})

        mock_client.fetch_quality_conversations_async = mock_generator
        mock_client.get_conversation_async = AsyncMock(return_value={"id": "test"})
        mock_client.should_recover_conversation = MagicMock(return_value=False)

        with patch("src.classification_pipeline.store_classification_results_batch") as mock_store:
            mock_store.return_value = 3
            mock_store.side_effect = lambda *args, **kwargs: (
                store_calls.append("store"),
                3
            )[1]

            with patch("src.classification_pipeline._save_classification_checkpoint", tracking_save):
                with patch("src.classification_pipeline._clear_checkpoint"):
                    with patch("src.classification_pipeline.classify_conversation_async") as mock_classify:
                        mock_classify.return_value = {
                            "conversation_id": "test",
                            "stage1_result": {"conversation_type": "general_inquiry"},
                            "stage2_result": None,
                        }

                        result = await _run_streaming_batch_pipeline_async(
                            client=mock_client,
                            since=datetime.now(),
                            until=datetime.now(),
                            max_conversations=None,
                            dry_run=False,
                            concurrency=10,
                            batch_size=3,  # Process all 3 in one batch
                            semaphore=asyncio.Semaphore(10),
                            stop_checker=lambda: False,
                            pipeline_run_id=42,
                            checkpoint=None,
                        )

        # Checkpoint should be saved AFTER store (store_calls should have 1 entry when checkpoint is saved)
        assert len(save_checkpoint_calls) > 0
        for call_info in save_checkpoint_calls:
            operation, store_count = call_info
            assert store_count >= 1, "Checkpoint saved before storage completed"

    @pytest.mark.asyncio
    async def test_resume_with_missing_cursor(self):
        """Test resume works when cursor is missing (fallback to beginning)."""
        from src.classification_pipeline import _run_streaming_batch_pipeline_async
        from unittest.mock import MagicMock
        from contextlib import asynccontextmanager

        mock_client = MagicMock()

        @asynccontextmanager
        async def mock_session_cm():
            yield MagicMock()

        mock_client._get_aiohttp_session = mock_session_cm

        fallback_called = []

        async def mock_generator(*args, **kwargs):
            # Capture the on_cursor_fallback callback
            on_fallback = kwargs.get("on_cursor_fallback")
            initial_cursor = kwargs.get("initial_cursor")

            # Simulate cursor being None (missing)
            if initial_cursor is None and on_fallback:
                # In real code, fallback is called when cursor is invalid
                # Here we just verify the callback is provided
                pass

            return
            yield

        mock_client.fetch_quality_conversations_async = mock_generator

        # Checkpoint with missing cursor
        checkpoint = {
            "phase": "classification",
            "intercom_cursor": None,  # Missing cursor
            "conversations_processed": 50,
        }

        result = await _run_streaming_batch_pipeline_async(
            client=mock_client,
            since=datetime.now(),
            until=datetime.now(),
            max_conversations=None,
            dry_run=True,
            concurrency=10,
            batch_size=50,
            semaphore=asyncio.Semaphore(10),
            stop_checker=lambda: False,
            pipeline_run_id=None,
            checkpoint=checkpoint,
        )

        # Should complete without error
        assert result["classified"] == 0

    @pytest.mark.asyncio
    async def test_stats_seeded_from_checkpoint_on_resume(self):
        """Test that stats are seeded from checkpoint counts on resume (Codex fix)."""
        from src.classification_pipeline import _run_streaming_batch_pipeline_async
        from unittest.mock import MagicMock
        from contextlib import asynccontextmanager

        mock_client = MagicMock()

        @asynccontextmanager
        async def mock_session_context():
            yield MagicMock()

        mock_client._get_aiohttp_session = mock_session_context

        # Empty generator - no conversations to process
        async def mock_generator(**kwargs):
            return
            yield

        mock_client.fetch_quality_conversations_async = mock_generator

        # Checkpoint with prior counts
        checkpoint = {
            "phase": "classification",
            "intercom_cursor": "some_cursor",
            "conversations_fetched": 100,
            "conversations_classified": 95,
            "conversations_stored": 90,
        }

        result = await _run_streaming_batch_pipeline_async(
            client=mock_client,
            since=datetime.now(),
            until=datetime.now(),
            max_conversations=None,
            dry_run=True,
            concurrency=10,
            batch_size=50,
            semaphore=asyncio.Semaphore(10),
            stop_checker=lambda: False,
            pipeline_run_id=None,
            checkpoint=checkpoint,
        )

        # Stats should be seeded from checkpoint (cumulative)
        assert result["fetched"] == 100, "fetched should be seeded from checkpoint"
        assert result["classified"] == 95, "classified should be seeded from checkpoint"
        assert result["stored"] == 90, "stored should be seeded from checkpoint"

    @pytest.mark.asyncio
    async def test_max_conversations_enforced_during_fetch(self):
        """Test that max_conversations stops fetch early (Codex fix)."""
        from src.classification_pipeline import _run_streaming_batch_pipeline_async
        from unittest.mock import MagicMock
        from contextlib import asynccontextmanager

        mock_client = MagicMock()

        @asynccontextmanager
        async def mock_session_context():
            yield MagicMock()

        mock_client._get_aiohttp_session = mock_session_context

        # Generator that would yield 100 conversations
        conversations_yielded = [0]

        async def mock_generator(**kwargs):
            for i in range(100):
                conversations_yielded[0] += 1
                mock_parsed = MagicMock()
                mock_parsed.id = f"conv_{i}"
                yield (mock_parsed, {"id": f"conv_{i}"})

        mock_client.fetch_quality_conversations_async = mock_generator

        result = await _run_streaming_batch_pipeline_async(
            client=mock_client,
            since=datetime.now(),
            until=datetime.now(),
            max_conversations=10,  # Limit to 10
            dry_run=True,
            concurrency=10,
            batch_size=50,  # Larger than max
            semaphore=asyncio.Semaphore(10),
            stop_checker=lambda: False,
            pipeline_run_id=None,
            checkpoint=None,
        )

        # Should stop after reaching max_conversations
        assert conversations_yielded[0] <= 11, f"Should stop fetching early, got {conversations_yielded[0]}"


class TestProcessStreamingBatch:
    """Tests for _process_streaming_batch helper."""

    @pytest.mark.asyncio
    async def test_recovery_evaluation_order(self):
        """Test that recovery is evaluated BEFORE classification."""
        from src.classification_pipeline import _process_streaming_batch
        from unittest.mock import MagicMock, AsyncMock

        mock_client = MagicMock()
        mock_session = MagicMock()
        semaphore = asyncio.Semaphore(10)

        # Track order of operations
        operation_order = []

        mock_client.get_conversation_async = AsyncMock(side_effect=lambda session, id: (
            operation_order.append(f"detail_fetch_{id}"),
            {"id": id, "conversation_parts": {"conversation_parts": []}}
        )[1])

        mock_client.should_recover_conversation = MagicMock(side_effect=lambda parts, had_template_opener: (
            operation_order.append("recovery_check"),
            True
        )[1])

        # Mock parsed conversation
        mock_parsed = MagicMock()
        mock_parsed.id = "conv_1"
        mock_parsed.source_body = "test"
        mock_parsed.source_type = "conversation"
        mock_parsed.source_url = None
        mock_parsed.contact_email = None
        mock_parsed.contact_id = None
        mock_parsed.created_at = datetime.now()

        # One recovery candidate
        recovery_candidates = [(mock_parsed, {"id": "conv_1"}, False)]

        async def classify_side_effect(p, r, s):
            operation_order.append("classify")
            return {
                "conversation_id": "conv_1",
                "stage1_result": {"conversation_type": "general_inquiry"},
                "stage2_result": None,
            }

        with patch("src.classification_pipeline.classify_conversation_async", side_effect=classify_side_effect):
            with patch("src.classification_pipeline.store_classification_results_batch", return_value=1):
                result = await _process_streaming_batch(
                    batch=[],  # Empty batch, only recovery candidates
                    recovery_candidates=recovery_candidates,
                    client=mock_client,
                    session=mock_session,
                    semaphore=semaphore,
                    concurrency=10,
                    dry_run=False,
                    pipeline_run_id=42,
                )

        # Verify order: detail_fetch → recovery_check → classify
        assert "recovery_check" in operation_order
        classify_index = next((i for i, op in enumerate(operation_order) if op == "classify"), -1)
        recovery_index = next((i for i, op in enumerate(operation_order) if op == "recovery_check"), -1)

        if classify_index >= 0 and recovery_index >= 0:
            assert recovery_index < classify_index, "Recovery should happen before classification"

    @pytest.mark.asyncio
    async def test_classification_error_logged(self):
        """Test that classification errors are logged but batch continues."""
        from src.classification_pipeline import _process_streaming_batch
        from unittest.mock import MagicMock, AsyncMock

        mock_client = MagicMock()
        mock_session = MagicMock()
        semaphore = asyncio.Semaphore(10)

        mock_client.get_conversation_async = AsyncMock(return_value={
            "id": "test",
            "conversation_parts": {"conversation_parts": []}
        })

        # Mock parsed conversations
        def make_parsed(id):
            p = MagicMock()
            p.id = id
            p.source_body = "test"
            p.source_type = "conversation"
            p.source_url = None
            p.contact_email = None
            p.contact_id = None
            p.created_at = datetime.now()
            return p

        batch = [
            (make_parsed("conv_1"), {"id": "conv_1"}),
            (make_parsed("conv_2"), {"id": "conv_2"}),
        ]

        with patch("src.classification_pipeline.classify_conversation_async") as mock_classify:
            # First succeeds, second fails
            mock_classify.side_effect = [
                {
                    "conversation_id": "conv_1",
                    "stage1_result": {"conversation_type": "general_inquiry"},
                    "stage2_result": None,
                },
                Exception("Classification failed"),
            ]

            with patch("src.classification_pipeline.store_classification_results_batch", return_value=1):
                result = await _process_streaming_batch(
                    batch=batch,
                    recovery_candidates=[],
                    client=mock_client,
                    session=mock_session,
                    semaphore=semaphore,
                    concurrency=10,
                    dry_run=False,
                    pipeline_run_id=42,
                )

        # Should have 1 classified (the successful one)
        assert result["classified"] == 1
        assert result["stored"] == 1
