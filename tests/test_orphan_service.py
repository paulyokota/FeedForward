"""
Orphan Service Tests

Tests for OrphanService - Phase 5 Story Grouping.
Run with: pytest tests/test_orphan_service.py -v
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
    MIN_GROUP_SIZE,
    Orphan,
    OrphanCreate,
    OrphanGraduationResult,
    OrphanListResponse,
    OrphanUpdate,
    Story,
)
from story_tracking.services import OrphanService, StoryService


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
def sample_orphan_row():
    """Sample orphan row from database."""
    return {
        "id": uuid4(),
        "signature": "Scheduler: Pin fails to post",
        "original_signature": None,
        "conversation_ids": ["conv1", "conv2"],
        "theme_data": {
            "user_intent": "Schedule a pin to post at a specific time",
            "symptoms": ["pin not posting", "scheduling error"],
            "product_area": "Scheduler",
            "component": "Pin Queue",
        },
        "confidence_score": 75.5,
        "first_seen_at": datetime.now(),
        "last_updated_at": datetime.now(),
        "graduated_at": None,
        "story_id": None,
    }


@pytest.fixture
def graduated_orphan_row(sample_orphan_row):
    """Sample graduated orphan row."""
    story_id = uuid4()
    return {
        **sample_orphan_row,
        "conversation_ids": ["conv1", "conv2", "conv3"],
        "graduated_at": datetime.now(),
        "story_id": story_id,
    }


@pytest.fixture
def ready_to_graduate_orphan_row(sample_orphan_row):
    """Sample orphan that has enough conversations to graduate."""
    return {
        **sample_orphan_row,
        "conversation_ids": ["conv1", "conv2", "conv3"],  # MIN_GROUP_SIZE
    }


@pytest.fixture
def sample_story_row():
    """Sample story row for graduation tests."""
    return {
        "id": uuid4(),
        "title": "Test Story",
        "description": "Test description",
        "labels": [],
        "priority": None,
        "severity": None,
        "product_area": "Scheduler",
        "technical_area": "Pin Queue",
        "status": "candidate",
        "confidence_score": 75.5,
        "evidence_count": 0,
        "conversation_count": 0,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


# -----------------------------------------------------------------------------
# OrphanService Tests
# -----------------------------------------------------------------------------


class TestOrphanService:
    """Tests for OrphanService."""

    def test_create_orphan(self, mock_db, sample_orphan_row):
        """Test creating a new orphan."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_orphan_row

        service = OrphanService(db)
        orphan_create = OrphanCreate(
            signature="Scheduler: Pin fails to post",
            conversation_ids=["conv1", "conv2"],
            theme_data={"user_intent": "Schedule a pin"},
        )

        result = service.create(orphan_create)

        assert result.signature == "Scheduler: Pin fails to post"
        assert len(result.conversation_ids) == 2
        cursor.execute.assert_called_once()

    def test_get_orphan(self, mock_db, sample_orphan_row):
        """Test getting an orphan by ID."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_orphan_row

        service = OrphanService(db)
        result = service.get(sample_orphan_row["id"])

        assert result is not None
        assert result.signature == "Scheduler: Pin fails to post"
        assert result.is_active is True

    def test_get_orphan_not_found(self, mock_db):
        """Test getting a non-existent orphan."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        service = OrphanService(db)
        result = service.get(uuid4())

        assert result is None

    def test_get_by_signature(self, mock_db, sample_orphan_row):
        """Test finding an active orphan by signature."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_orphan_row

        service = OrphanService(db)
        result = service.get_by_signature("Scheduler: Pin fails to post")

        assert result is not None
        assert result.signature == "Scheduler: Pin fails to post"

    def test_get_by_signature_not_found(self, mock_db):
        """Test finding orphan by signature when not found."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        service = OrphanService(db)
        result = service.get_by_signature("nonexistent")

        assert result is None

    def test_list_active_orphans(self, mock_db, sample_orphan_row):
        """Test listing active orphans."""
        db, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"count": 5},  # total
            {"count": 3},  # active
        ]
        cursor.fetchall.return_value = [sample_orphan_row]

        service = OrphanService(db)
        result = service.list_active(limit=10)

        assert isinstance(result, OrphanListResponse)
        assert result.total == 5
        assert result.active_count == 3
        assert len(result.orphans) == 1

    def test_update_orphan(self, mock_db, sample_orphan_row):
        """Test updating orphan fields."""
        db, cursor = mock_db
        updated_row = {
            **sample_orphan_row,
            "confidence_score": 85.0,
        }
        cursor.fetchone.return_value = updated_row

        service = OrphanService(db)
        updates = OrphanUpdate(confidence_score=85.0)
        result = service.update(sample_orphan_row["id"], updates)

        assert result.confidence_score == 85.0

    def test_add_conversations(self, mock_db, sample_orphan_row):
        """Test adding conversations to an orphan."""
        db, cursor = mock_db
        # First call for get(), second for update()
        updated_row = {
            **sample_orphan_row,
            "conversation_ids": ["conv1", "conv2", "conv3"],
        }
        cursor.fetchone.side_effect = [sample_orphan_row, updated_row]

        service = OrphanService(db)
        result = service.add_conversations(
            sample_orphan_row["id"],
            conversation_ids=["conv3"],
            theme_data={"symptoms": ["new symptom"]},
        )

        assert result is not None
        assert "conv3" in result.conversation_ids

    def test_add_conversations_no_duplicates(self, mock_db, sample_orphan_row):
        """Test that duplicate conversations are not added."""
        db, cursor = mock_db
        # Conversation list stays the same because conv1 already exists
        cursor.fetchone.side_effect = [sample_orphan_row, sample_orphan_row]

        service = OrphanService(db)
        result = service.add_conversations(
            sample_orphan_row["id"],
            conversation_ids=["conv1"],  # Already exists
        )

        assert result is not None
        # Should still have only 2 conversations
        assert len(result.conversation_ids) == 2

    def test_delete_orphan(self, mock_db):
        """Test deleting an orphan."""
        db, cursor = mock_db
        cursor.rowcount = 1

        service = OrphanService(db)
        result = service.delete(uuid4())

        assert result is True

    def test_delete_orphan_not_found(self, mock_db):
        """Test deleting a non-existent orphan."""
        db, cursor = mock_db
        cursor.rowcount = 0

        service = OrphanService(db)
        result = service.delete(uuid4())

        assert result is False


class TestOrphanGraduation:
    """Tests for orphan graduation to stories."""

    def test_orphan_can_graduate(self, mock_db, ready_to_graduate_orphan_row):
        """Test that orphan with MIN_GROUP_SIZE conversations can graduate."""
        db, cursor = mock_db
        cursor.fetchone.return_value = ready_to_graduate_orphan_row

        service = OrphanService(db)
        orphan = service.get(ready_to_graduate_orphan_row["id"])

        assert orphan.can_graduate is True
        assert orphan.conversation_count == MIN_GROUP_SIZE

    def test_orphan_cannot_graduate_insufficient(self, mock_db, sample_orphan_row):
        """Test that orphan with <MIN_GROUP_SIZE cannot graduate."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_orphan_row

        service = OrphanService(db)
        orphan = service.get(sample_orphan_row["id"])

        assert orphan.can_graduate is False
        assert orphan.conversation_count < MIN_GROUP_SIZE

    def test_graduate_orphan(
        self, mock_db, ready_to_graduate_orphan_row, sample_story_row
    ):
        """Test graduating an orphan to a story."""
        db, cursor = mock_db
        orphan_id = ready_to_graduate_orphan_row["id"]

        # Mock story service
        mock_story_service = Mock(spec=StoryService)
        mock_story = Story(**sample_story_row)
        mock_story_service.create.return_value = mock_story

        cursor.fetchone.return_value = ready_to_graduate_orphan_row

        service = OrphanService(db)
        result = service.graduate(orphan_id, mock_story_service)

        assert result is not None
        assert isinstance(result, OrphanGraduationResult)
        assert result.orphan_id == orphan_id
        assert result.story_id == mock_story.id
        assert result.conversation_count == MIN_GROUP_SIZE

        # Verify story was created
        mock_story_service.create.assert_called_once()

    def test_graduate_orphan_not_found(self, mock_db):
        """Test graduation fails for non-existent orphan."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        mock_story_service = Mock(spec=StoryService)

        service = OrphanService(db)
        result = service.graduate(uuid4(), mock_story_service)

        assert result is None
        mock_story_service.create.assert_not_called()

    def test_graduate_orphan_insufficient_conversations(
        self, mock_db, sample_orphan_row
    ):
        """Test graduation fails for orphan with too few conversations."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_orphan_row  # Only 2 conversations

        mock_story_service = Mock(spec=StoryService)

        service = OrphanService(db)
        result = service.graduate(sample_orphan_row["id"], mock_story_service)

        assert result is None
        mock_story_service.create.assert_not_called()

    def test_graduate_already_graduated(self, mock_db, graduated_orphan_row):
        """Test graduation fails for already graduated orphan."""
        db, cursor = mock_db
        cursor.fetchone.return_value = graduated_orphan_row

        mock_story_service = Mock(spec=StoryService)

        service = OrphanService(db)
        result = service.graduate(graduated_orphan_row["id"], mock_story_service)

        assert result is None
        mock_story_service.create.assert_not_called()

    def test_check_and_graduate_ready(
        self, mock_db, ready_to_graduate_orphan_row, sample_story_row
    ):
        """Test batch graduation of ready orphans."""
        db, cursor = mock_db

        # Mock list_active to return one ready orphan
        cursor.fetchone.side_effect = [
            {"count": 1},  # total
            {"count": 1},  # active
            ready_to_graduate_orphan_row,  # for graduate() -> get()
        ]
        cursor.fetchall.return_value = [ready_to_graduate_orphan_row]

        mock_story_service = Mock(spec=StoryService)
        mock_story = Story(**sample_story_row)
        mock_story_service.create.return_value = mock_story

        service = OrphanService(db)
        results = service.check_and_graduate_ready(mock_story_service)

        assert len(results) == 1
        assert results[0].story_id == mock_story.id


class TestOrphanModels:
    """Tests for orphan-related Pydantic models."""

    def test_orphan_create(self):
        """Test OrphanCreate model."""
        orphan = OrphanCreate(
            signature="Test signature",
            conversation_ids=["conv1"],
            theme_data={"user_intent": "Test intent"},
        )
        assert orphan.signature == "Test signature"
        assert len(orphan.conversation_ids) == 1

    def test_orphan_update_partial(self):
        """Test OrphanUpdate with partial fields."""
        update = OrphanUpdate(confidence_score=90.0)
        assert update.confidence_score == 90.0
        assert update.conversation_ids is None

    def test_orphan_list_response(self):
        """Test OrphanListResponse model."""
        response = OrphanListResponse(
            orphans=[],
            total=0,
            active_count=0,
        )
        assert response.total == 0
        assert response.active_count == 0

    def test_orphan_graduation_result(self):
        """Test OrphanGraduationResult model."""
        result = OrphanGraduationResult(
            orphan_id=uuid4(),
            story_id=uuid4(),
            signature="Test signature",
            conversation_count=3,
            graduated_at=datetime.now(),
        )
        assert result.conversation_count == MIN_GROUP_SIZE

    def test_min_group_size_constant(self):
        """Test MIN_GROUP_SIZE constant is 3."""
        assert MIN_GROUP_SIZE == 3


class TestThemeDataMerging:
    """Tests for theme data merging logic."""

    def test_merge_new_keys(self, mock_db, sample_orphan_row):
        """Test merging adds new keys."""
        db, cursor = mock_db
        updated_row = {
            **sample_orphan_row,
            "theme_data": {
                **sample_orphan_row["theme_data"],
                "new_key": "new_value",
            },
        }
        cursor.fetchone.side_effect = [sample_orphan_row, updated_row]

        service = OrphanService(db)
        result = service.add_conversations(
            sample_orphan_row["id"],
            conversation_ids=["conv3"],
            theme_data={"new_key": "new_value"},
        )

        assert result is not None

    def test_merge_lists_deduplicates(self, mock_db):
        """Test that list merging avoids duplicates."""
        db, _ = mock_db
        service = OrphanService(db)

        existing = {"symptoms": ["symptom1", "symptom2"]}
        new = {"symptoms": ["symptom2", "symptom3"]}

        merged = service._merge_theme_data(existing, new)

        assert len(merged["symptoms"]) == 3
        assert "symptom1" in merged["symptoms"]
        assert "symptom2" in merged["symptoms"]
        assert "symptom3" in merged["symptoms"]

    def test_merge_nested_dicts(self, mock_db):
        """Test recursive dict merging."""
        db, _ = mock_db
        service = OrphanService(db)

        existing = {"nested": {"key1": "val1"}}
        new = {"nested": {"key2": "val2"}}

        merged = service._merge_theme_data(existing, new)

        assert merged["nested"]["key1"] == "val1"
        assert merged["nested"]["key2"] == "val2"
