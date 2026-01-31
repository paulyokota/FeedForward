"""
Sync API Router Tests

Tests for sync API endpoints.
Run with: pytest tests/test_sync_router.py -v
"""

import pytest

# Mark entire module as medium - uses TestClient with mocked dependencies
pytestmark = pytest.mark.medium
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers.sync import get_sync_service, get_shortcut_client
from src.api.deps import get_db
from story_tracking.models import (
    SyncMetadata,
    SyncResult,
    SyncStatusResponse,
    StorySnapshot,
)
from story_tracking.services import StoryService


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    return Mock()


@pytest.fixture
def mock_shortcut_client():
    """Create a mock Shortcut client."""
    return Mock()


@pytest.fixture
def mock_sync_service():
    """Create a mock sync service."""
    return Mock()


@pytest.fixture
def client(mock_db, mock_shortcut_client, mock_sync_service):
    """Create a test client with overridden dependencies."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_shortcut_client] = lambda: mock_shortcut_client
    app.dependency_overrides[get_sync_service] = lambda: mock_sync_service

    yield TestClient(app)

    # Clean up overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def sample_story_id():
    """Generate a sample story ID."""
    return uuid4()


@pytest.fixture
def sample_sync_result(sample_story_id):
    """Create sample sync result."""
    return SyncResult(
        success=True,
        direction="push",
        story_id=sample_story_id,
        shortcut_story_id="sc-12345",
        synced_at=datetime.now(),
        error=None,
    )


@pytest.fixture
def sample_sync_status(sample_story_id):
    """Create sample sync status response."""
    return SyncStatusResponse(
        story_id=sample_story_id,
        shortcut_story_id="sc-12345",
        last_internal_update_at=datetime.now(),
        last_external_update_at=datetime.now(),
        last_synced_at=datetime.now(),
        last_sync_status="success",
        last_sync_error=None,
        needs_sync=False,
        sync_direction_hint="none",
    )


# -----------------------------------------------------------------------------
# Push Endpoint Tests
# -----------------------------------------------------------------------------


class TestPushEndpoint:
    """Tests for POST /api/sync/shortcut/push endpoint."""

    def test_push_success(self, client, mock_sync_service, sample_story_id, sample_sync_result):
        """Test successful push to Shortcut."""
        mock_sync_service.push_to_shortcut.return_value = sample_sync_result

        response = client.post(
            "/api/sync/shortcut/push",
            json={
                "story_id": str(sample_story_id),
                "snapshot": {
                    "title": "Test Story",
                    "description": "Test description",
                    "labels": ["bug"],
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["shortcut_story_id"] == "sc-12345"
        assert data["sync_status"] == "success"

    def test_push_failure(self, client, mock_sync_service, sample_story_id):
        """Test push failure returns error."""
        mock_sync_service.push_to_shortcut.return_value = SyncResult(
            success=False,
            direction="push",
            story_id=sample_story_id,
            error="Story not found",
        )

        response = client.post(
            "/api/sync/shortcut/push",
            json={
                "story_id": str(sample_story_id),
                "snapshot": {"title": "Test"},
            },
        )

        assert response.status_code == 500
        assert "Story not found" in response.json()["detail"]


# -----------------------------------------------------------------------------
# Pull Endpoint Tests
# -----------------------------------------------------------------------------


class TestPullEndpoint:
    """Tests for POST /api/sync/shortcut/pull endpoint."""

    def test_pull_by_story_id(self, client, mock_sync_service, mock_db, sample_story_id, sample_sync_result):
        """Test pull using story_id."""
        mock_sync_service.pull_from_shortcut.return_value = sample_sync_result

        # Mock the StoryService.get call made in the endpoint
        mock_story = Mock()
        mock_story.title = "Test Story"
        mock_story.description = "Test description"
        mock_story.labels = ["bug"]
        mock_story.priority = None
        mock_story.severity = None
        mock_story.product_area = "billing"
        mock_story.technical_area = None

        # We need to patch StoryService since it's instantiated in the endpoint
        from unittest.mock import patch
        with patch("src.api.routers.sync.StoryService") as MockStoryService:
            MockStoryService.return_value.get.return_value = mock_story

            response = client.post(
                "/api/sync/shortcut/pull",
                json={
                    "story_id": str(sample_story_id),
                    "shortcut_story_id": "sc-12345",  # Required field
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["story_id"] == str(sample_story_id)
            assert data["sync_status"] == "success"

    def test_pull_by_shortcut_id_only(self, client, mock_sync_service, sample_story_id, sample_sync_result):
        """Test pull using shortcut_story_id only."""
        mock_sync_service.find_story_by_shortcut_id.return_value = Mock(
            story_id=sample_story_id
        )
        mock_sync_service.pull_from_shortcut.return_value = sample_sync_result

        from unittest.mock import patch
        with patch("src.api.routers.sync.StoryService") as MockStoryService:
            mock_story = Mock()
            mock_story.title = "Test Story"
            mock_story.description = "Test description"
            mock_story.labels = []
            mock_story.priority = None
            mock_story.severity = None
            mock_story.product_area = None
            mock_story.technical_area = None
            MockStoryService.return_value.get.return_value = mock_story

            response = client.post(
                "/api/sync/shortcut/pull",
                json={"shortcut_story_id": "sc-12345"},
            )

            assert response.status_code == 200

    def test_pull_not_linked(self, client, mock_sync_service):
        """Test pull fails when no story linked."""
        mock_sync_service.find_story_by_shortcut_id.return_value = None

        response = client.post(
            "/api/sync/shortcut/pull",
            json={"shortcut_story_id": "sc-unknown"},
        )

        assert response.status_code == 404


# -----------------------------------------------------------------------------
# Webhook Endpoint Tests
# -----------------------------------------------------------------------------


class TestWebhookEndpoint:
    """Tests for POST /api/sync/shortcut/webhook endpoint."""

    def test_webhook_story_updated(self, client, mock_sync_service, sample_story_id, sample_sync_result):
        """Test webhook handles story.updated event."""
        mock_sync_service.handle_webhook.return_value = sample_sync_result

        response = client.post(
            "/api/sync/shortcut/webhook",
            json={
                "shortcut_story_id": "sc-12345",
                "event_type": "story.updated",
                "updated_at": datetime.now().isoformat(),
                "fields": {"name": "Updated Title"},
            },
        )

        assert response.status_code == 200
        mock_sync_service.handle_webhook.assert_called_once()

    def test_webhook_story_deleted(self, client, mock_sync_service, sample_story_id):
        """Test webhook handles story.deleted event."""
        mock_sync_service.handle_webhook.return_value = SyncResult(
            success=True,
            direction="none",
            story_id=sample_story_id,
        )

        response = client.post(
            "/api/sync/shortcut/webhook",
            json={
                "shortcut_story_id": "sc-12345",
                "event_type": "story.deleted",
                "updated_at": datetime.now().isoformat(),
                "fields": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["direction"] == "none"


# -----------------------------------------------------------------------------
# Status Endpoint Tests
# -----------------------------------------------------------------------------


class TestStatusEndpoint:
    """Tests for GET /api/sync/shortcut/status/{story_id} endpoint."""

    def test_get_sync_status(self, client, mock_sync_service, sample_story_id, sample_sync_status):
        """Test getting sync status."""
        mock_sync_service.get_sync_status.return_value = sample_sync_status

        response = client.get(f"/api/sync/shortcut/status/{sample_story_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["shortcut_story_id"] == "sc-12345"
        assert data["needs_sync"] is False


# -----------------------------------------------------------------------------
# Sync Story Endpoint Tests
# -----------------------------------------------------------------------------


class TestSyncStoryEndpoint:
    """Tests for POST /api/sync/shortcut/sync/{story_id} endpoint."""

    def test_sync_story(self, client, mock_sync_service, sample_story_id, sample_sync_result):
        """Test auto-sync a story."""
        mock_sync_service.sync_story.return_value = sample_sync_result

        response = client.post(f"/api/sync/shortcut/sync/{sample_story_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["direction"] == "push"


# -----------------------------------------------------------------------------
# Sync All Endpoint Tests
# -----------------------------------------------------------------------------


class TestSyncAllEndpoint:
    """Tests for POST /api/sync/shortcut/sync-all endpoint."""

    def test_sync_all_pending(self, client, mock_sync_service, sample_sync_result):
        """Test sync all pending stories."""
        mock_sync_service.sync_all_pending.return_value = [sample_sync_result]

        response = client.post("/api/sync/shortcut/sync-all")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["success"] is True

    def test_sync_all_empty(self, client, mock_sync_service):
        """Test sync all when no stories need syncing."""
        mock_sync_service.sync_all_pending.return_value = []

        response = client.post("/api/sync/shortcut/sync-all")

        assert response.status_code == 200
        data = response.json()
        assert data == []
