"""
Pipeline API Router Tests

Tests for pipeline control endpoints including start, stop, status, and history.
Run with: pytest tests/test_pipeline_router.py -v
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

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

    # Clear the in-memory active runs state
    pipeline_module._active_runs.clear()

    yield TestClient(app)

    # Clean up overrides and state after test
    app.dependency_overrides.clear()
    pipeline_module._active_runs.clear()


# -----------------------------------------------------------------------------
# Stop Endpoint Tests
# -----------------------------------------------------------------------------


class TestStopPipelineEndpoint:
    """Tests for POST /api/pipeline/stop endpoint."""

    def test_stop_no_active_run(self, client):
        """Test stopping when no pipeline is running."""
        response = client.post("/api/pipeline/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_running"
        assert data["run_id"] == 0
        assert "No active pipeline run" in data["message"]

    def test_stop_active_run(self, client, mock_db):
        """Test stopping an active pipeline run."""
        # Setup: Mark a run as active
        run_id = 42
        pipeline_module._active_runs[run_id] = "running"

        # Setup mock cursor for database update
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        response = client.post("/api/pipeline/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopping"
        assert data["run_id"] == run_id
        assert "Stop signal sent" in data["message"]

        # Verify in-memory state updated
        assert pipeline_module._active_runs[run_id] == "stopping"

        # Verify database was updated
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "UPDATE pipeline_runs" in call_args[0][0]
        assert "stopping" in call_args[0][0]

    def test_stop_already_stopping(self, client, mock_db):
        """Test stopping when already in stopping state."""
        # Setup: Mark a run as stopping
        run_id = 42
        pipeline_module._active_runs[run_id] = "stopping"

        response = client.post("/api/pipeline/stop")

        # Should report no running pipeline (stopping doesn't count as running)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_running"

    def test_stop_completed_run_not_stoppable(self, client):
        """Test that completed runs are not considered active."""
        # Setup: Mark a run as completed
        run_id = 42
        pipeline_module._active_runs[run_id] = "completed"

        response = client.post("/api/pipeline/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_running"


# -----------------------------------------------------------------------------
# Active Endpoint Tests
# -----------------------------------------------------------------------------


class TestActiveEndpoint:
    """Tests for GET /api/pipeline/active endpoint."""

    def test_active_no_runs(self, client):
        """Test active check with no runs."""
        response = client.get("/api/pipeline/active")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False
        assert data["run_id"] is None

    def test_active_with_running_pipeline(self, client):
        """Test active check with running pipeline."""
        run_id = 42
        pipeline_module._active_runs[run_id] = "running"

        response = client.get("/api/pipeline/active")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["run_id"] == run_id

    def test_active_ignores_completed_runs(self, client):
        """Test that completed runs are not considered active."""
        pipeline_module._active_runs[41] = "completed"
        pipeline_module._active_runs[42] = "failed"
        pipeline_module._active_runs[43] = "stopped"

        response = client.get("/api/pipeline/active")

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False


# -----------------------------------------------------------------------------
# Stop Checker Tests
# -----------------------------------------------------------------------------


class TestStopChecker:
    """Tests for the _is_stopping helper function."""

    def test_is_stopping_true(self):
        """Test _is_stopping returns True when status is stopping."""
        run_id = 42
        pipeline_module._active_runs[run_id] = "stopping"

        assert pipeline_module._is_stopping(run_id) is True

    def test_is_stopping_false_running(self):
        """Test _is_stopping returns False when status is running."""
        run_id = 42
        pipeline_module._active_runs[run_id] = "running"

        assert pipeline_module._is_stopping(run_id) is False

    def test_is_stopping_false_not_found(self):
        """Test _is_stopping returns False when run not in dict."""
        assert pipeline_module._is_stopping(999) is False


# -----------------------------------------------------------------------------
# History Endpoint Tests
# -----------------------------------------------------------------------------


class TestHistoryEndpoint:
    """Tests for GET /api/pipeline/history endpoint."""

    def test_history_returns_list(self, client, mock_db):
        """Test history returns list of runs."""
        # Setup mock cursor to return sample history
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        now = datetime.now(timezone.utc)
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "started_at": now - timedelta(hours=2),
                "completed_at": now - timedelta(hours=1),
                "status": "completed",
                "current_phase": "completed",
                "conversations_fetched": 100,
                "conversations_classified": 100,
                "conversations_stored": 95,
                "themes_extracted": 50,
                "stories_created": 10,
                "stories_ready": True,
            },
            {
                "id": 2,
                "started_at": now - timedelta(hours=1),
                "completed_at": None,
                "status": "running",
                "current_phase": "classification",
                "conversations_fetched": 50,
                "conversations_classified": 30,
                "conversations_stored": 25,
                "themes_extracted": 0,
                "stories_created": 0,
                "stories_ready": False,
            },
        ]

        response = client.get("/api/pipeline/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["status"] == "completed"
        assert data[0]["current_phase"] == "completed"
        assert data[0]["themes_extracted"] == 50
        assert data[0]["stories_ready"] is True
        assert data[1]["id"] == 2
        assert data[1]["status"] == "running"
        assert data[1]["current_phase"] == "classification"

    def test_history_with_stopped_status(self, client, mock_db):
        """Test history includes stopped runs."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        now = datetime.now(timezone.utc)
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "started_at": now - timedelta(hours=1),
                "completed_at": now - timedelta(minutes=30),
                "status": "stopped",
                "current_phase": "theme_extraction",
                "conversations_fetched": 50,
                "conversations_classified": 25,
                "conversations_stored": 20,
                "themes_extracted": 10,
                "stories_created": 0,
                "stories_ready": True,
            },
        ]

        response = client.get("/api/pipeline/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "stopped"
        assert data[0]["stories_ready"] is True


# -----------------------------------------------------------------------------
# Status Endpoint Tests
# -----------------------------------------------------------------------------


class TestStatusEndpoint:
    """Tests for GET /api/pipeline/status/{run_id} endpoint."""

    def test_status_not_found(self, client, mock_db):
        """Test status for non-existent run."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)
        mock_cursor.fetchone.return_value = None

        response = client.get("/api/pipeline/status/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_status_returns_stopping(self, client, mock_db):
        """Test status returns stopping state."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        now = datetime.now(timezone.utc)
        mock_cursor.fetchone.return_value = {
            "id": 42,
            "started_at": now - timedelta(minutes=10),
            "completed_at": None,
            "date_from": now - timedelta(days=7),
            "date_to": now,
            "status": "stopping",
            "error_message": None,
            "current_phase": "classification",
            "auto_create_stories": False,
            "conversations_fetched": 100,
            "conversations_filtered": 80,
            "conversations_classified": 50,
            "conversations_stored": 45,
            "themes_extracted": 0,
            "themes_new": 0,
            "stories_created": 0,
            "orphans_created": 0,
            "stories_ready": False,
        }

        response = client.get("/api/pipeline/status/42")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["status"] == "stopping"
        assert data["current_phase"] == "classification"
        assert data["conversations_fetched"] == 100
        assert data["conversations_classified"] == 50
        assert data["stories_ready"] is False

    def test_status_returns_stopped(self, client, mock_db):
        """Test status returns stopped state."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        now = datetime.now(timezone.utc)
        mock_cursor.fetchone.return_value = {
            "id": 42,
            "started_at": now - timedelta(minutes=10),
            "completed_at": now - timedelta(minutes=5),
            "date_from": now - timedelta(days=7),
            "date_to": now,
            "status": "stopped",
            "error_message": None,
            "current_phase": "theme_extraction",
            "auto_create_stories": True,
            "conversations_fetched": 100,
            "conversations_filtered": 80,
            "conversations_classified": 50,
            "conversations_stored": 45,
            "themes_extracted": 30,
            "themes_new": 5,
            "stories_created": 0,
            "orphans_created": 0,
            "stories_ready": True,
        }

        response = client.get("/api/pipeline/status/42")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["completed_at"] is not None
        assert data["current_phase"] == "theme_extraction"
        assert data["themes_extracted"] == 30
        assert data["stories_ready"] is True
