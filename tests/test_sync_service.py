"""
Sync Service Tests

Tests for SyncService - bidirectional Shortcut sync.
Run with: pytest tests/test_sync_service.py -v
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

pytestmark = pytest.mark.medium

from story_tracking.models import (
    ShortcutWebhookEvent,
    Story,
    StoryUpdate,
    SyncMetadata,
    SyncMetadataUpdate,
    SyncResult,
)
from story_tracking.services import SyncService, StoryService


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
    from dataclasses import dataclass

    @dataclass
    class MockShortcutStory:
        id: str = "sc-12345"
        name: str = "Test Story from Shortcut"
        description: str = "Description from Shortcut"
        story_type: str = "bug"

    client = Mock()
    client.create_story.return_value = "sc-12345"
    client.update_story.return_value = True
    client.get_story.return_value = MockShortcutStory()
    return client


@pytest.fixture
def mock_story_service():
    """Create a mock story service."""
    service = Mock(spec=StoryService)
    service.get.return_value = Story(
        id=uuid4(),
        title="Test Story",
        description="Test description",
        labels=[],
        priority=None,
        severity=None,
        product_area="billing",
        technical_area=None,
        status="candidate",
        confidence_score=None,
        evidence_count=0,
        conversation_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    service.update.return_value = service.get.return_value
    return service


@pytest.fixture
def sample_sync_metadata_row():
    """Sample sync metadata row from database."""
    return {
        "story_id": uuid4(),
        "shortcut_story_id": "sc-12345",
        "last_internal_update_at": datetime.now() - timedelta(hours=1),
        "last_external_update_at": datetime.now() - timedelta(hours=2),
        "last_synced_at": datetime.now() - timedelta(hours=1),
        "last_sync_status": "success",
        "last_sync_error": None,
        "last_sync_direction": "push",
    }


@pytest.fixture
def sync_service(mock_db, mock_shortcut_client, mock_story_service):
    """Create a SyncService with mock dependencies."""
    db, _ = mock_db
    return SyncService(db, mock_shortcut_client, mock_story_service)


# -----------------------------------------------------------------------------
# Sync Metadata CRUD Tests
# -----------------------------------------------------------------------------


class TestSyncMetadataCRUD:
    """Tests for sync metadata CRUD operations."""

    def test_get_sync_metadata_found(self, mock_db, sync_service, sample_sync_metadata_row):
        """Test getting sync metadata when it exists."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_sync_metadata_row

        result = sync_service.get_sync_metadata(sample_sync_metadata_row["story_id"])

        assert result is not None
        assert result.shortcut_story_id == "sc-12345"
        assert result.last_sync_status == "success"

    def test_get_sync_metadata_not_found(self, mock_db, sync_service):
        """Test getting sync metadata when it doesn't exist."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        result = sync_service.get_sync_metadata(uuid4())

        assert result is None

    def test_create_sync_metadata(self, mock_db, sync_service):
        """Test creating sync metadata."""
        db, cursor = mock_db
        story_id = uuid4()
        cursor.fetchone.return_value = {
            "story_id": story_id,
            "shortcut_story_id": "sc-99999",
            "last_internal_update_at": None,
            "last_external_update_at": None,
            "last_synced_at": datetime.now(),
            "last_sync_status": "created",
            "last_sync_error": None,
            "last_sync_direction": "push",
        }

        result = sync_service.create_sync_metadata(story_id, "sc-99999")

        assert result.shortcut_story_id == "sc-99999"
        assert result.last_sync_status == "created"
        cursor.execute.assert_called()

    def test_update_sync_metadata(self, mock_db, sync_service, sample_sync_metadata_row):
        """Test updating sync metadata."""
        db, cursor = mock_db
        updated_row = {**sample_sync_metadata_row, "last_sync_status": "success"}
        cursor.fetchone.return_value = updated_row

        result = sync_service.update_sync_metadata(
            sample_sync_metadata_row["story_id"],
            SyncMetadataUpdate(last_sync_status="success"),
        )

        assert result is not None
        assert result.last_sync_status == "success"


# -----------------------------------------------------------------------------
# Push to Shortcut Tests
# -----------------------------------------------------------------------------


class TestPushToShortcut:
    """Tests for pushing internal stories to Shortcut."""

    def test_push_creates_new_shortcut_story(
        self, mock_db, sync_service, mock_shortcut_client, mock_story_service
    ):
        """Test pushing a story that doesn't exist in Shortcut."""
        db, cursor = mock_db
        story_id = uuid4()

        # No existing sync metadata - empty shortcut_story_id means create new
        cursor.fetchone.side_effect = [
            None,  # get_sync_metadata returns None (first call)
            {  # create_sync_metadata returns new row with empty shortcut_id
                "story_id": story_id,
                "shortcut_story_id": "",  # Empty means no Shortcut story yet
                "last_internal_update_at": None,
                "last_external_update_at": None,
                "last_synced_at": datetime.now(),
                "last_sync_status": "created",
                "last_sync_error": None,
                "last_sync_direction": "push",
            },
            {  # update_sync_metadata after create_story - adds shortcut_id
                "story_id": story_id,
                "shortcut_story_id": "sc-12345",
                "last_internal_update_at": None,
                "last_external_update_at": None,
                "last_synced_at": datetime.now(),
                "last_sync_status": "created",
                "last_sync_error": None,
                "last_sync_direction": "push",
            },
            {  # get_sync_metadata for final result
                "story_id": story_id,
                "shortcut_story_id": "sc-12345",
                "last_internal_update_at": None,
                "last_external_update_at": None,
                "last_synced_at": datetime.now(),
                "last_sync_status": "created",
                "last_sync_error": None,
                "last_sync_direction": "push",
            },
            {  # update_sync_metadata for success
                "story_id": story_id,
                "shortcut_story_id": "sc-12345",
                "last_internal_update_at": datetime.now(),
                "last_external_update_at": None,
                "last_synced_at": datetime.now(),
                "last_sync_status": "success",
                "last_sync_error": None,
                "last_sync_direction": "push",
            },
        ]

        result = sync_service.push_to_shortcut(story_id)

        assert result.success is True
        assert result.direction == "push"
        mock_shortcut_client.create_story.assert_called_once()

    def test_push_updates_existing_shortcut_story(
        self, mock_db, sync_service, mock_shortcut_client, sample_sync_metadata_row
    ):
        """Test pushing updates to an existing Shortcut story."""
        db, cursor = mock_db
        story_id = sample_sync_metadata_row["story_id"]

        cursor.fetchone.side_effect = [
            sample_sync_metadata_row,  # get_sync_metadata
            {  # update_sync_metadata
                **sample_sync_metadata_row,
                "last_synced_at": datetime.now(),
                "last_sync_status": "success",
            },
        ]

        result = sync_service.push_to_shortcut(story_id)

        assert result.success is True
        assert result.direction == "push"
        mock_shortcut_client.update_story.assert_called_once()

    def test_push_fails_when_story_not_found(self, mock_db, sync_service, mock_story_service):
        """Test push fails gracefully when story doesn't exist."""
        mock_story_service.get.return_value = None

        result = sync_service.push_to_shortcut(uuid4())

        assert result.success is False
        assert "not found" in result.error.lower()


# -----------------------------------------------------------------------------
# Pull from Shortcut Tests
# -----------------------------------------------------------------------------


class TestPullFromShortcut:
    """Tests for pulling Shortcut stories to internal."""

    def test_pull_updates_internal_story(
        self, mock_db, sync_service, sample_sync_metadata_row, mock_story_service
    ):
        """Test pulling a Shortcut story updates internal."""
        db, cursor = mock_db
        story_id = sample_sync_metadata_row["story_id"]

        # Mock the story service to return a story with the same ID
        mock_story_service.get.return_value = Story(
            id=story_id,
            title="Test Story",
            description="Test description",
            labels=[],
            priority=None,
            severity=None,
            product_area="billing",
            technical_area=None,
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        cursor.fetchone.side_effect = [
            sample_sync_metadata_row,  # get_sync_metadata
            {  # update_sync_metadata for success
                **sample_sync_metadata_row,
                "last_synced_at": datetime.now(),
                "last_sync_status": "success",
                "last_sync_direction": "pull",
            },
        ]

        result = sync_service.pull_from_shortcut(story_id)

        assert result.success is True
        assert result.direction == "pull"
        mock_story_service.update.assert_called_once()

    def test_pull_fails_without_shortcut_link(self, mock_db, sync_service):
        """Test pull fails when no Shortcut story is linked."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None  # No sync metadata

        result = sync_service.pull_from_shortcut(uuid4())

        assert result.success is False
        assert "No Shortcut story linked" in result.error


# -----------------------------------------------------------------------------
# Auto Sync Tests
# -----------------------------------------------------------------------------


class TestAutoSync:
    """Tests for automatic sync direction determination."""

    def test_sync_chooses_push_when_internal_newer(
        self, mock_db, sync_service, mock_shortcut_client, mock_story_service
    ):
        """Test sync pushes when internal update is newer."""
        db, cursor = mock_db
        story_id = uuid4()

        # Internal is newer than external
        metadata_row = {
            "story_id": story_id,
            "shortcut_story_id": "sc-12345",
            "last_internal_update_at": datetime.now(),
            "last_external_update_at": datetime.now() - timedelta(hours=1),
            "last_synced_at": datetime.now() - timedelta(hours=2),
            "last_sync_status": "success",
            "last_sync_error": None,
            "last_sync_direction": "push",
        }

        cursor.fetchone.side_effect = [
            metadata_row,  # get_sync_metadata for sync_story
            metadata_row,  # get_sync_metadata for push
            {**metadata_row, "last_sync_status": "success"},  # update after push
        ]

        result = sync_service.sync_story(story_id)

        assert result.direction == "push"
        mock_shortcut_client.update_story.assert_called()

    def test_sync_chooses_pull_when_external_newer(
        self, mock_db, sync_service, mock_shortcut_client, mock_story_service
    ):
        """Test sync pulls when external update is newer."""
        db, cursor = mock_db
        story_id = uuid4()

        # External is newer than internal
        metadata_row = {
            "story_id": story_id,
            "shortcut_story_id": "sc-12345",
            "last_internal_update_at": datetime.now() - timedelta(hours=2),
            "last_external_update_at": datetime.now(),
            "last_synced_at": datetime.now() - timedelta(hours=2),
            "last_sync_status": "success",
            "last_sync_error": None,
            "last_sync_direction": "pull",
        }

        cursor.fetchone.side_effect = [
            metadata_row,  # get_sync_metadata for sync_story
            metadata_row,  # get_sync_metadata for pull
            {**metadata_row, "last_sync_status": "success"},  # update after pull
        ]

        result = sync_service.sync_story(story_id)

        assert result.direction == "pull"


# -----------------------------------------------------------------------------
# Webhook Handling Tests
# -----------------------------------------------------------------------------


class TestWebhookHandling:
    """Tests for Shortcut webhook handling."""

    def test_handle_webhook_updates_story(
        self, mock_db, sync_service, sample_sync_metadata_row, mock_story_service
    ):
        """Test webhook triggers pull from Shortcut."""
        db, cursor = mock_db
        story_id = sample_sync_metadata_row["story_id"]

        # Mock story_service to return a story with matching ID
        mock_story_service.get.return_value = Story(
            id=story_id,
            title="Test Story",
            description="Test description",
            labels=[],
            priority=None,
            severity=None,
            product_area="billing",
            technical_area=None,
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        cursor.fetchone.side_effect = [
            {"story_id": story_id},  # find_story_by_shortcut_id
            sample_sync_metadata_row,  # update_sync_metadata for timestamp
            sample_sync_metadata_row,  # get_sync_metadata for pull
            {**sample_sync_metadata_row, "last_sync_status": "success"},  # update after pull
        ]

        event = ShortcutWebhookEvent(
            shortcut_story_id="sc-12345",
            event_type="story.updated",
            updated_at=datetime.now(),
            fields={"name": "Updated Title"},
        )

        result = sync_service.handle_webhook(event)

        assert result.success is True

    def test_handle_webhook_unlinks_deleted_story(self, mock_db, sync_service):
        """Test webhook unlinks when Shortcut story is deleted."""
        db, cursor = mock_db
        story_id = uuid4()

        cursor.fetchone.side_effect = [
            {"story_id": story_id},  # find_story_by_shortcut_id
            None,  # update_sync_metadata returns (for timestamp update)
            None,  # update_sync_metadata (for unlink)
        ]

        event = ShortcutWebhookEvent(
            shortcut_story_id="sc-12345",
            event_type="story.deleted",
            updated_at=datetime.now(),
            fields={},
        )

        result = sync_service.handle_webhook(event)

        assert result.success is True
        assert result.direction == "none"

    def test_handle_webhook_unknown_story(self, mock_db, sync_service):
        """Test webhook for unknown Shortcut story."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None  # No matching story

        event = ShortcutWebhookEvent(
            shortcut_story_id="sc-unknown",
            event_type="story.updated",
            updated_at=datetime.now(),
            fields={},
        )

        result = sync_service.handle_webhook(event)

        assert result.success is False
        assert "No linked internal story" in result.error


# -----------------------------------------------------------------------------
# Sync Status Tests
# -----------------------------------------------------------------------------


class TestSyncStatus:
    """Tests for sync status queries."""

    def test_get_sync_status_needs_push(
        self, mock_db, sync_service, mock_story_service
    ):
        """Test status indicates push needed when internal is newer."""
        db, cursor = mock_db
        story_id = uuid4()

        # Story was updated after last sync
        story = mock_story_service.get.return_value
        story.updated_at = datetime.now()

        metadata_row = {
            "story_id": story_id,
            "shortcut_story_id": "sc-12345",
            "last_internal_update_at": datetime.now() - timedelta(hours=1),
            "last_external_update_at": datetime.now() - timedelta(hours=2),
            "last_synced_at": datetime.now() - timedelta(hours=1),
            "last_sync_status": "success",
            "last_sync_error": None,
            "last_sync_direction": "push",
        }

        cursor.fetchone.return_value = metadata_row

        status = sync_service.get_sync_status(story_id)

        assert status.needs_sync is True
        assert status.sync_direction_hint == "push"

    def test_get_sync_status_no_metadata(self, mock_db, sync_service):
        """Test status for story without sync metadata."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        status = sync_service.get_sync_status(uuid4())

        assert status.needs_sync is True
        assert status.sync_direction_hint == "push"


# -----------------------------------------------------------------------------
# Metadata Stripping Tests
# -----------------------------------------------------------------------------


class TestMetadataStripping:
    """Tests for _strip_feedforward_metadata helper method."""

    def test_strip_metadata_with_full_block(self, sync_service):
        """Test stripping a complete metadata block."""
        description = """This is the story description.

It has multiple paragraphs.

---
## Metadata

| Field | Value |
|-------|-------|
| Source | intercom |
| Product Area | billing |

*Generated by FeedForward pipeline*"""

        result = sync_service._strip_feedforward_metadata(description)

        assert result == "This is the story description.\n\nIt has multiple paragraphs."
        assert "## Metadata" not in result
        assert "Generated by FeedForward pipeline" not in result

    def test_strip_metadata_preserves_content_before(self, sync_service):
        """Test that content before metadata is preserved."""
        description = """# Bug Report

Users cannot submit payments.

## Steps to Reproduce
1. Go to checkout
2. Click pay

---
## Metadata

| Field | Value |
|-------|-------|
| Severity | high |

*Generated by FeedForward pipeline*"""

        result = sync_service._strip_feedforward_metadata(description)

        assert "# Bug Report" in result
        assert "Users cannot submit payments" in result
        assert "## Steps to Reproduce" in result
        assert "## Metadata" not in result

    def test_strip_metadata_no_metadata_block(self, sync_service):
        """Test description without metadata block is unchanged."""
        description = "Simple description without any metadata."

        result = sync_service._strip_feedforward_metadata(description)

        assert result == description

    def test_strip_metadata_empty_string(self, sync_service):
        """Test empty string returns empty string (falsy passthrough)."""
        result = sync_service._strip_feedforward_metadata("")

        assert result == ""

    def test_strip_metadata_none_input(self, sync_service):
        """Test None input returns None."""
        result = sync_service._strip_feedforward_metadata(None)

        assert result is None

    def test_strip_metadata_only_metadata_block(self, sync_service):
        """Test description that is only metadata returns None."""
        description = """---
## Metadata

| Field | Value |
|-------|-------|
| Source | coda |

*Generated by FeedForward pipeline*"""

        result = sync_service._strip_feedforward_metadata(description)

        assert result is None

    def test_strip_metadata_multiple_dashes(self, sync_service):
        """Test that other --- separators are preserved."""
        description = """# Story

---

Some content after first separator.

---
## Metadata

*Generated by FeedForward pipeline*"""

        result = sync_service._strip_feedforward_metadata(description)

        assert "# Story" in result
        assert "Some content after first separator" in result
        # First separator should be preserved
        assert result.count("---") == 1

    def test_strip_metadata_trailing_whitespace(self, sync_service):
        """Test metadata block with trailing whitespace."""
        description = """Description here.

---
## Metadata

*Generated by FeedForward pipeline*
"""

        result = sync_service._strip_feedforward_metadata(description)

        assert result == "Description here."
