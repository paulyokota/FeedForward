"""
Phase 3 Integration Tests

End-to-end tests for Shortcut sync + analytics functionality.
Run with: pytest tests/test_phase3_integration.py -v
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.deps import get_db
from src.api.routers.sync import get_sync_service, get_shortcut_client
from src.api.routers.labels import get_label_service
from src.api.routers.analytics import get_analytics_service


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    db = Mock()
    cursor = MagicMock()
    db.cursor.return_value.__enter__ = Mock(return_value=cursor)
    db.cursor.return_value.__exit__ = Mock(return_value=False)
    return db, cursor


@pytest.fixture
def mock_services():
    """Create mock services for all dependencies."""
    return {
        "sync": Mock(),
        "label": Mock(),
        "analytics": Mock(),
        "shortcut": Mock(),
    }


@pytest.fixture
def client(mock_db, mock_services):
    """Create a test client with all dependencies mocked."""
    db, _ = mock_db

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_sync_service] = lambda: mock_services["sync"]
    app.dependency_overrides[get_label_service] = lambda: mock_services["label"]
    app.dependency_overrides[get_analytics_service] = lambda: mock_services["analytics"]
    app.dependency_overrides[get_shortcut_client] = lambda: mock_services["shortcut"]

    yield TestClient(app)

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# Integration Flow Tests
# -----------------------------------------------------------------------------


class TestSyncWorkflow:
    """Tests for the complete sync workflow."""

    def test_push_then_status_workflow(self, client, mock_services):
        """Test pushing a story then checking its sync status."""
        story_id = uuid4()
        now = datetime.now()

        # Configure mocks
        from story_tracking.models import SyncResult, SyncStatusResponse

        push_result = SyncResult(
            success=True,
            direction="push",
            story_id=story_id,
            shortcut_story_id="sc-12345",
            synced_at=now,
        )
        mock_services["sync"].push_to_shortcut.return_value = push_result

        status_response = SyncStatusResponse(
            story_id=story_id,
            shortcut_story_id="sc-12345",
            last_internal_update_at=now,
            last_external_update_at=now,
            last_synced_at=now,
            last_sync_status="success",
            last_sync_error=None,
            needs_sync=False,
            sync_direction_hint="none",
        )
        mock_services["sync"].get_sync_status.return_value = status_response

        # Step 1: Push to Shortcut
        push_response = client.post(
            "/api/sync/shortcut/push",
            json={
                "story_id": str(story_id),
                "snapshot": {
                    "title": "Test Story",
                    "description": "Description",
                    "labels": ["bug"],
                },
            },
        )
        assert push_response.status_code == 200
        assert push_response.json()["shortcut_story_id"] == "sc-12345"

        # Step 2: Check sync status
        status_response = client.get(f"/api/sync/shortcut/status/{story_id}")
        assert status_response.status_code == 200
        assert status_response.json()["needs_sync"] is False

    def test_webhook_then_pull_workflow(self, client, mock_services):
        """Test receiving a webhook then pulling updates."""
        story_id = uuid4()
        now = datetime.now()

        from story_tracking.models import SyncResult

        # Configure mocks
        webhook_result = SyncResult(
            success=True,
            direction="pull",
            story_id=story_id,
            shortcut_story_id="sc-12345",
            synced_at=now,
        )
        mock_services["sync"].handle_webhook.return_value = webhook_result

        # Step 1: Receive webhook
        webhook_response = client.post(
            "/api/sync/shortcut/webhook",
            json={
                "shortcut_story_id": "sc-12345",
                "event_type": "story.updated",
                "updated_at": now.isoformat(),
                "fields": {"name": "Updated Title"},
            },
        )
        assert webhook_response.status_code == 200
        assert webhook_response.json()["direction"] == "pull"


class TestLabelWorkflow:
    """Tests for the complete label workflow."""

    def test_import_then_list_workflow(self, client, mock_services):
        """Test importing labels then listing them."""
        from story_tracking.models import ImportResult, LabelListResponse, LabelRegistryEntry

        # Configure mocks
        import_result = ImportResult(
            imported_count=5,
            updated_count=3,
            skipped_count=0,
            errors=[],
        )
        mock_services["label"].import_from_shortcut.return_value = import_result

        now = datetime.now()
        label_list = LabelListResponse(
            labels=[
                LabelRegistryEntry(
                    label_name="bug",
                    source="shortcut",
                    category="type",
                    created_at=now,
                    last_seen_at=now,
                ),
                LabelRegistryEntry(
                    label_name="feature",
                    source="shortcut",
                    category="type",
                    created_at=now,
                    last_seen_at=now,
                ),
            ],
            total=2,
            shortcut_count=2,
            internal_count=0,
        )
        mock_services["label"].list_labels.return_value = label_list

        # Step 1: Import from Shortcut
        import_response = client.post("/api/labels/import")
        assert import_response.status_code == 200
        assert import_response.json()["imported_count"] == 5

        # Step 2: List labels
        list_response = client.get("/api/labels")
        assert list_response.status_code == 200
        assert len(list_response.json()["labels"]) == 2

    def test_create_then_ensure_workflow(self, client, mock_services):
        """Test creating an internal label then ensuring it exists in Shortcut."""
        from story_tracking.models import LabelRegistryEntry

        now = datetime.now()
        new_label = LabelRegistryEntry(
            label_name="internal-tracking",
            source="internal",
            category=None,
            created_at=now,
            last_seen_at=now,
        )

        # Configure mocks
        mock_services["label"].get_label.return_value = None  # Label doesn't exist
        mock_services["label"].create_label.return_value = new_label
        mock_services["label"].ensure_label_in_shortcut.return_value = True

        # Step 1: Create internal label
        create_response = client.post(
            "/api/labels",
            json={
                "label_name": "internal-tracking",
                "source": "internal",
            },
        )
        assert create_response.status_code == 200
        assert create_response.json()["source"] == "internal"

        # Step 2: Ensure it exists in Shortcut
        ensure_response = client.post("/api/labels/ensure/internal-tracking")
        assert ensure_response.status_code == 200
        assert ensure_response.json()["status"] == "ensured"


class TestAnalyticsWorkflow:
    """Tests for the analytics workflow."""

    def test_full_analytics_dashboard(self, client, mock_services):
        """Test fetching all analytics endpoints for a dashboard."""
        from story_tracking.services.analytics_service import (
            StoryMetrics,
            ThemeTrend,
            SourceDistribution,
            EvidenceSummary,
        )

        now = datetime.now()

        # Configure story metrics
        mock_services["analytics"].get_story_metrics.return_value = StoryMetrics(
            total_stories=50,
            by_status={"candidate": 20, "triaged": 15, "validated": 15},
            by_priority={"high": 10, "medium": 25, "none": 15},
            by_severity={"critical": 5, "major": 20, "none": 25},
            by_product_area={"billing": 20, "scheduler": 30},
            created_last_7_days=10,
            created_last_30_days=30,
            avg_confidence_score=85.5,
            total_evidence_count=150,
            total_conversation_count=500,
        )

        # Configure trending themes
        mock_services["analytics"].get_trending_themes.return_value = [
            ThemeTrend(
                theme_signature="Billing: Subscription issues",
                product_area="billing",
                occurrence_count=15,
                first_seen_at=now - timedelta(days=5),
                last_seen_at=now,
                trend_direction="rising",
                linked_story_count=3,
            ),
        ]

        # Configure source distribution
        mock_services["analytics"].get_source_distribution.return_value = [
            SourceDistribution(
                source="intercom",
                conversation_count=400,
                story_count=40,
                percentage=80.0,
            ),
        ]

        # Configure sync metrics
        mock_services["analytics"].get_sync_metrics.return_value = {
            "total_synced": 30,
            "success_count": 28,
            "error_count": 2,
            "push_count": 20,
            "pull_count": 10,
            "unsynced_count": 20,
        }

        # Fetch all analytics
        stories_response = client.get("/api/analytics/stories")
        assert stories_response.status_code == 200
        assert stories_response.json()["total_stories"] == 50

        themes_response = client.get("/api/analytics/themes/trending")
        assert themes_response.status_code == 200
        assert len(themes_response.json()) == 1

        sources_response = client.get("/api/analytics/sources")
        assert sources_response.status_code == 200
        assert sources_response.json()[0]["source"] == "intercom"

        sync_response = client.get("/api/analytics/sync")
        assert sync_response.status_code == 200
        assert sync_response.json()["total_synced"] == 30


# -----------------------------------------------------------------------------
# API Endpoint Discovery Tests
# -----------------------------------------------------------------------------


class TestAPIEndpointDiscovery:
    """Tests to verify all expected endpoints exist."""

    def test_sync_endpoints_exist(self, client, mock_services):
        """Verify all sync endpoints are registered."""
        from story_tracking.models import SyncResult

        # Configure sync service mocks
        mock_services["sync"].sync_all_pending.return_value = []

        # Test sync-all endpoint (the others require body validation)
        response = client.post("/api/sync/shortcut/sync-all")
        assert response.status_code == 200, f"sync-all endpoint returned {response.status_code}"

        # For endpoints that require body, just verify they don't return 404
        # POST with empty body will return 422 (validation error), which is fine
        push_response = client.post("/api/sync/shortcut/push", json={})
        assert push_response.status_code != 404, "push endpoint not found"

        pull_response = client.post("/api/sync/shortcut/pull", json={})
        assert pull_response.status_code != 404, "pull endpoint not found"

        webhook_response = client.post("/api/sync/shortcut/webhook", json={})
        assert webhook_response.status_code != 404, "webhook endpoint not found"

    def test_label_endpoints_exist(self, client, mock_services):
        """Verify all label endpoints are registered."""
        from story_tracking.models import LabelListResponse, ImportResult

        # Configure mocks for all label endpoints
        mock_services["label"].list_labels.return_value = LabelListResponse(
            labels=[], total=0, shortcut_count=0, internal_count=0
        )
        mock_services["label"].import_from_shortcut.return_value = ImportResult(
            imported_count=0, updated_count=0, skipped_count=0, errors=[]
        )
        mock_services["label"].get_label.return_value = None

        # Test list endpoint
        list_response = client.get("/api/labels")
        assert list_response.status_code == 200, f"labels list returned {list_response.status_code}"

        # Test import endpoint
        import_response = client.post("/api/labels/import")
        assert import_response.status_code == 200, f"labels import returned {import_response.status_code}"

        # Test create endpoint (will return 422 for missing body, but not 404)
        create_response = client.post("/api/labels", json={})
        assert create_response.status_code != 404, "labels create endpoint not found"

    def test_analytics_endpoints_exist(self, client, mock_services):
        """Verify all analytics endpoints are registered."""
        from story_tracking.services.analytics_service import StoryMetrics

        # Configure minimal mocks
        mock_services["analytics"].get_story_metrics.return_value = StoryMetrics(
            total_stories=0,
            by_status={},
            by_priority={},
            by_severity={},
            by_product_area={},
            created_last_7_days=0,
            created_last_30_days=0,
            avg_confidence_score=None,
            total_evidence_count=0,
            total_conversation_count=0,
        )
        mock_services["analytics"].get_trending_themes.return_value = []
        mock_services["analytics"].get_source_distribution.return_value = []
        mock_services["analytics"].get_sync_metrics.return_value = {
            "total_synced": 0,
            "success_count": 0,
            "error_count": 0,
            "push_count": 0,
            "pull_count": 0,
            "unsynced_count": 0,
        }

        endpoints = [
            "/api/analytics/stories",
            "/api/analytics/themes/trending",
            "/api/analytics/sources",
            "/api/analytics/sync",
        ]

        for path in endpoints:
            response = client.get(path)
            assert response.status_code != 404, f"Endpoint GET {path} not found"
            assert response.status_code == 200, f"Endpoint GET {path} returned {response.status_code}"
