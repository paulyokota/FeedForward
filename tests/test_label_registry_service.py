"""
Label Registry Service Tests

Tests for LabelRegistryService - label taxonomy management.
Run with: pytest tests/test_label_registry_service.py -v
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.models import (
    ImportResult,
    LabelCreate,
    LabelListResponse,
    LabelRegistryEntry,
    LabelUpdate,
)
from story_tracking.services import LabelRegistryService


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
def mock_shortcut_client():
    """Create a mock Shortcut client."""
    client = Mock()
    client._get.return_value = [
        {"name": "bug", "category": "type"},
        {"name": "feature", "category": "type"},
        {"name": "billing", "category": "product_area"},
    ]
    client._post.return_value = {"name": "new-label"}
    return client


@pytest.fixture
def sample_label_row():
    """Sample label row from database."""
    return {
        "label_name": "bug",
        "source": "shortcut",
        "category": "type",
        "created_at": datetime.now(),
        "last_seen_at": datetime.now(),
    }


@pytest.fixture
def internal_label_row():
    """Sample internal label row."""
    return {
        "label_name": "internal-tracking",
        "source": "internal",
        "category": None,
        "created_at": datetime.now(),
        "last_seen_at": datetime.now(),
    }


@pytest.fixture
def label_service(mock_db, mock_shortcut_client):
    """Create a LabelRegistryService with mock dependencies."""
    db, _ = mock_db
    return LabelRegistryService(db, mock_shortcut_client)


@pytest.fixture
def label_service_no_shortcut(mock_db):
    """Create a LabelRegistryService without Shortcut client."""
    db, _ = mock_db
    return LabelRegistryService(db, shortcut_client=None)


# -----------------------------------------------------------------------------
# CRUD Tests
# -----------------------------------------------------------------------------


class TestLabelCRUD:
    """Tests for label CRUD operations."""

    def test_list_labels_all(self, mock_db, label_service, sample_label_row):
        """Test listing all labels."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [sample_label_row]
        cursor.fetchone.side_effect = [
            {"count": 5},  # total
            {"count": 3},  # shortcut_count
            {"count": 2},  # internal_count
        ]

        result = label_service.list_labels()

        assert isinstance(result, LabelListResponse)
        assert result.total == 5
        assert result.shortcut_count == 3
        assert result.internal_count == 2
        assert len(result.labels) == 1

    def test_list_labels_filtered_by_source(self, mock_db, label_service, sample_label_row):
        """Test listing labels filtered by source."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [sample_label_row]
        cursor.fetchone.side_effect = [
            {"count": 5},
            {"count": 3},
            {"count": 2},
        ]

        result = label_service.list_labels(source="shortcut")

        assert len(result.labels) == 1
        # Verify the query included source filter
        call_args = cursor.execute.call_args_list[0]
        assert "WHERE source = %s" in call_args[0][0]

    def test_get_label_found(self, mock_db, label_service, sample_label_row):
        """Test getting a label that exists."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_label_row

        result = label_service.get_label("bug")

        assert result is not None
        assert result.label_name == "bug"
        assert result.source == "shortcut"

    def test_get_label_not_found(self, mock_db, label_service):
        """Test getting a label that doesn't exist."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        result = label_service.get_label("nonexistent")

        assert result is None

    def test_create_label(self, mock_db, label_service):
        """Test creating a new label."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {
            "label_name": "new-label",
            "source": "internal",
            "category": None,
            "created_at": datetime.now(),
            "last_seen_at": datetime.now(),
        }

        result = label_service.create_label(
            LabelCreate(label_name="new-label", source="internal")
        )

        assert result.label_name == "new-label"
        assert result.source == "internal"
        cursor.execute.assert_called()

    def test_create_label_with_category(self, mock_db, label_service):
        """Test creating a label with category."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {
            "label_name": "billing",
            "source": "shortcut",
            "category": "product_area",
            "created_at": datetime.now(),
            "last_seen_at": datetime.now(),
        }

        result = label_service.create_label(
            LabelCreate(label_name="billing", source="shortcut", category="product_area")
        )

        assert result.label_name == "billing"
        assert result.category == "product_area"

    def test_update_label(self, mock_db, label_service, sample_label_row):
        """Test updating a label."""
        db, cursor = mock_db
        updated_row = {**sample_label_row, "category": "updated-category"}
        cursor.fetchone.return_value = updated_row

        result = label_service.update_label(
            "bug", LabelUpdate(category="updated-category")
        )

        assert result is not None
        assert result.category == "updated-category"

    def test_update_last_seen(self, mock_db, label_service, sample_label_row):
        """Test updating last_seen_at timestamp."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_label_row

        result = label_service.update_last_seen("bug")

        assert result is not None
        cursor.execute.assert_called()

    def test_delete_label_success(self, mock_db, label_service):
        """Test deleting a label successfully."""
        db, cursor = mock_db
        cursor.rowcount = 1

        result = label_service.delete_label("bug")

        assert result is True

    def test_delete_label_not_found(self, mock_db, label_service):
        """Test deleting a label that doesn't exist."""
        db, cursor = mock_db
        cursor.rowcount = 0

        result = label_service.delete_label("nonexistent")

        assert result is False


# -----------------------------------------------------------------------------
# Shortcut Integration Tests
# -----------------------------------------------------------------------------


class TestShortcutIntegration:
    """Tests for Shortcut label integration."""

    def test_import_from_shortcut_success(
        self, mock_db, label_service, mock_shortcut_client
    ):
        """Test importing labels from Shortcut."""
        db, cursor = mock_db

        # First fetchone for get_label, returns None (new label)
        # Then fetchone for create_label, returns the created row
        cursor.fetchone.side_effect = [
            None,  # get_label("bug") - not found
            {  # create_label returns
                "label_name": "bug",
                "source": "shortcut",
                "category": "type",
                "created_at": datetime.now(),
                "last_seen_at": datetime.now(),
            },
            None,  # get_label("feature")
            {
                "label_name": "feature",
                "source": "shortcut",
                "category": "type",
                "created_at": datetime.now(),
                "last_seen_at": datetime.now(),
            },
            None,  # get_label("billing")
            {
                "label_name": "billing",
                "source": "shortcut",
                "category": "product_area",
                "created_at": datetime.now(),
                "last_seen_at": datetime.now(),
            },
        ]

        result = label_service.import_from_shortcut()

        assert isinstance(result, ImportResult)
        assert result.imported_count == 3
        assert result.errors == []
        mock_shortcut_client._get.assert_called_with("/labels")

    def test_import_from_shortcut_updates_existing(
        self, mock_db, label_service, mock_shortcut_client, sample_label_row
    ):
        """Test import updates existing labels' last_seen_at."""
        db, cursor = mock_db

        # All labels already exist
        cursor.fetchone.side_effect = [
            sample_label_row,  # get_label("bug") - found
            sample_label_row,  # update_last_seen
            sample_label_row,  # get_label("feature") - found
            sample_label_row,
            sample_label_row,  # get_label("billing") - found
            sample_label_row,
        ]

        result = label_service.import_from_shortcut()

        assert result.imported_count == 0
        assert result.updated_count == 3

    def test_import_without_shortcut_client(self, label_service_no_shortcut):
        """Test import fails gracefully without Shortcut client."""
        result = label_service_no_shortcut.import_from_shortcut()

        assert result.imported_count == 0
        assert len(result.errors) > 0
        assert "No Shortcut client" in result.errors[0]

    def test_ensure_label_in_shortcut_already_exists(
        self, mock_db, label_service, sample_label_row
    ):
        """Test ensure_label for label already in Shortcut."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_label_row

        result = label_service.ensure_label_in_shortcut("bug")

        assert result is True
        # Should not call _post since it's already a Shortcut label

    def test_ensure_label_in_shortcut_creates_new(
        self, mock_db, label_service, mock_shortcut_client, internal_label_row
    ):
        """Test ensure_label creates internal label in Shortcut."""
        db, cursor = mock_db
        cursor.fetchone.side_effect = [
            internal_label_row,  # get_label - found, but internal
            internal_label_row,  # update_last_seen
        ]

        result = label_service.ensure_label_in_shortcut("internal-tracking")

        assert result is True
        mock_shortcut_client._post.assert_called_with(
            "/labels", {"name": "internal-tracking"}
        )

    def test_ensure_label_without_shortcut_client(self, label_service_no_shortcut):
        """Test ensure_label fails gracefully without Shortcut client."""
        result = label_service_no_shortcut.ensure_label_in_shortcut("any-label")

        assert result is False


# -----------------------------------------------------------------------------
# Utility Tests
# -----------------------------------------------------------------------------


class TestLabelUtilities:
    """Tests for label utility methods."""

    def test_get_labels_for_story(self, mock_db, label_service, sample_label_row):
        """Test getting registry entries for story labels (uses batch query)."""
        db, cursor = mock_db
        # The new implementation uses a single batch query with fetchall()
        # Returns only labels that exist in the registry
        cursor.fetchall.return_value = [sample_label_row]  # Only "bug" found

        labels = ["bug", "unknown"]
        result = label_service.get_labels_for_story(labels)

        assert len(result) == 1
        assert result[0].label_name == "bug"
        # Verify batch query was used (2 execute calls: SELECT + UPDATE)
        assert cursor.execute.call_count == 2

    def test_row_to_label_conversion(self, label_service, sample_label_row):
        """Test database row to model conversion."""
        result = label_service._row_to_label(sample_label_row)

        assert isinstance(result, LabelRegistryEntry)
        assert result.label_name == sample_label_row["label_name"]
        assert result.source == sample_label_row["source"]
        assert result.category == sample_label_row["category"]
