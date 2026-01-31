"""
Labels API Router Tests

Tests for labels API endpoints.
Run with: pytest tests/test_labels_router.py -v
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
from src.api.routers.labels import get_label_service, get_shortcut_client
from src.api.deps import get_db
from story_tracking.models import (
    ImportResult,
    LabelListResponse,
    LabelRegistryEntry,
)


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
def mock_label_service():
    """Create a mock label service."""
    return Mock()


@pytest.fixture
def client(mock_db, mock_shortcut_client, mock_label_service):
    """Create a test client with overridden dependencies."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_shortcut_client] = lambda: mock_shortcut_client
    app.dependency_overrides[get_label_service] = lambda: mock_label_service

    yield TestClient(app)

    # Clean up overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def sample_label():
    """Create a sample label entry."""
    return LabelRegistryEntry(
        label_name="bug",
        source="shortcut",
        category="type",
        created_at=datetime.now(),
        last_seen_at=datetime.now(),
    )


@pytest.fixture
def sample_internal_label():
    """Create a sample internal label entry."""
    return LabelRegistryEntry(
        label_name="needs-review",
        source="internal",
        category=None,
        created_at=datetime.now(),
        last_seen_at=datetime.now(),
    )


@pytest.fixture
def sample_label_list(sample_label, sample_internal_label):
    """Create a sample label list response."""
    return LabelListResponse(
        labels=[sample_label, sample_internal_label],
        total=2,
        shortcut_count=1,
        internal_count=1,
    )


@pytest.fixture
def sample_import_result():
    """Create a sample import result."""
    return ImportResult(
        imported_count=3,
        skipped_count=0,
        updated_count=2,
        errors=[],
    )


# -----------------------------------------------------------------------------
# List Labels Endpoint Tests
# -----------------------------------------------------------------------------


class TestListLabelsEndpoint:
    """Tests for GET /api/labels endpoint."""

    def test_list_all_labels(self, client, mock_label_service, sample_label_list):
        """Test listing all labels."""
        mock_label_service.list_labels.return_value = sample_label_list

        response = client.get("/api/labels")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["shortcut_count"] == 1
        assert data["internal_count"] == 1
        assert len(data["labels"]) == 2

    def test_list_labels_filtered_by_source(self, client, mock_label_service, sample_label):
        """Test listing labels filtered by source."""
        mock_label_service.list_labels.return_value = LabelListResponse(
            labels=[sample_label],
            total=1,
            shortcut_count=1,
            internal_count=0,
        )

        response = client.get("/api/labels?source=shortcut")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert all(l["source"] == "shortcut" for l in data["labels"])

    def test_list_labels_with_limit(self, client, mock_label_service, sample_label_list):
        """Test listing labels with custom limit."""
        mock_label_service.list_labels.return_value = sample_label_list

        response = client.get("/api/labels?limit=50")

        assert response.status_code == 200
        mock_label_service.list_labels.assert_called_with(source=None, limit=50)


# -----------------------------------------------------------------------------
# Get Label Endpoint Tests
# -----------------------------------------------------------------------------


class TestGetLabelEndpoint:
    """Tests for GET /api/labels/{label_name} endpoint."""

    def test_get_label_found(self, client, mock_label_service, sample_label):
        """Test getting an existing label."""
        mock_label_service.get_label.return_value = sample_label

        response = client.get("/api/labels/bug")

        assert response.status_code == 200
        data = response.json()
        assert data["label_name"] == "bug"
        assert data["source"] == "shortcut"

    def test_get_label_not_found(self, client, mock_label_service):
        """Test getting a non-existent label."""
        mock_label_service.get_label.return_value = None

        response = client.get("/api/labels/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# Create Label Endpoint Tests
# -----------------------------------------------------------------------------


class TestCreateLabelEndpoint:
    """Tests for POST /api/labels endpoint."""

    def test_create_label_success(self, client, mock_label_service, sample_internal_label):
        """Test creating a new label."""
        mock_label_service.get_label.return_value = None  # Label doesn't exist
        mock_label_service.create_label.return_value = sample_internal_label

        response = client.post(
            "/api/labels",
            json={
                "label_name": "needs-review",
                "source": "internal",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["label_name"] == "needs-review"
        assert data["source"] == "internal"

    def test_create_label_already_exists(self, client, mock_label_service, sample_label):
        """Test creating a label that already exists."""
        mock_label_service.get_label.return_value = sample_label  # Already exists

        response = client.post(
            "/api/labels",
            json={
                "label_name": "bug",
                "source": "internal",
            },
        )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_create_label_with_category(self, client, mock_label_service, sample_label):
        """Test creating a label with category."""
        mock_label_service.get_label.return_value = None
        mock_label_service.create_label.return_value = sample_label

        response = client.post(
            "/api/labels",
            json={
                "label_name": "bug",
                "source": "shortcut",
                "category": "type",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "type"


# -----------------------------------------------------------------------------
# Delete Label Endpoint Tests
# -----------------------------------------------------------------------------


class TestDeleteLabelEndpoint:
    """Tests for DELETE /api/labels/{label_name} endpoint."""

    def test_delete_label_success(self, client, mock_label_service):
        """Test deleting a label successfully."""
        mock_label_service.delete_label.return_value = True

        response = client.delete("/api/labels/bug")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["label_name"] == "bug"

    def test_delete_label_not_found(self, client, mock_label_service):
        """Test deleting a non-existent label."""
        mock_label_service.delete_label.return_value = False

        response = client.delete("/api/labels/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# Import Endpoint Tests
# -----------------------------------------------------------------------------


class TestImportEndpoint:
    """Tests for POST /api/labels/import endpoint."""

    def test_import_from_shortcut_success(self, client, mock_label_service, sample_import_result):
        """Test importing labels from Shortcut."""
        mock_label_service.import_from_shortcut.return_value = sample_import_result

        response = client.post("/api/labels/import")

        assert response.status_code == 200
        data = response.json()
        assert data["imported_count"] == 3
        assert data["updated_count"] == 2
        assert data["errors"] == []

    def test_import_with_errors(self, client, mock_label_service):
        """Test import with some errors."""
        mock_label_service.import_from_shortcut.return_value = ImportResult(
            imported_count=2,
            skipped_count=1,
            updated_count=0,
            errors=["Failed to import label 'special-chars!@#'"],
        )

        response = client.post("/api/labels/import")

        # Should return 200 even with partial errors
        assert response.status_code == 200
        data = response.json()
        assert len(data["errors"]) > 0


# -----------------------------------------------------------------------------
# Ensure Label Endpoint Tests
# -----------------------------------------------------------------------------


class TestEnsureLabelEndpoint:
    """Tests for POST /api/labels/ensure/{label_name} endpoint."""

    def test_ensure_label_success(self, client, mock_label_service):
        """Test ensuring a label exists in Shortcut."""
        mock_label_service.ensure_label_in_shortcut.return_value = True

        response = client.post("/api/labels/ensure/needs-review")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ensured"
        assert data["label_name"] == "needs-review"

    def test_ensure_label_failure(self, client, mock_label_service):
        """Test ensure label failure."""
        mock_label_service.ensure_label_in_shortcut.return_value = False

        response = client.post("/api/labels/ensure/bad-label")

        assert response.status_code == 500
        assert "Failed to ensure" in response.json()["detail"]
