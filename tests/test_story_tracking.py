"""
Story Tracking Service Tests

Tests for StoryService and EvidenceService.
Run with: pytest tests/test_story_tracking.py -v
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
    Story,
    StoryCreate,
    StoryUpdate,
    StoryWithEvidence,
    StoryListResponse,
    StoryEvidence,
    EvidenceExcerpt,
)
from story_tracking.services import StoryService, EvidenceService


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
def sample_story_row():
    """Sample story row from database."""
    return {
        "id": uuid4(),
        "title": "Test Story",
        "description": "Test description",
        "labels": ["bug", "scheduler"],
        "priority": "high",
        "severity": "major",
        "product_area": "Scheduler",
        "technical_area": "Backend",
        "status": "candidate",
        "confidence_score": 85.5,
        "evidence_count": 3,
        "conversation_count": 5,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


@pytest.fixture
def sample_evidence_row():
    """Sample evidence row from database."""
    return {
        "id": uuid4(),
        "story_id": uuid4(),
        "conversation_ids": ["conv1", "conv2", "conv3"],
        "theme_signatures": ["Scheduler: Pin scheduling fails"],
        "source_stats": {"intercom": 3, "coda": 1},
        "excerpts": [
            {"text": "My pin didn't post", "source": "intercom", "conversation_id": "conv1"},
        ],
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


# -----------------------------------------------------------------------------
# StoryService Tests
# -----------------------------------------------------------------------------

class TestStoryService:
    """Tests for StoryService."""

    def test_create_story(self, mock_db, sample_story_row):
        """Test creating a new story."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_story_row

        service = StoryService(db)
        story_create = StoryCreate(
            title="Test Story",
            description="Test description",
            product_area="Scheduler",
            status="candidate",
        )

        result = service.create(story_create)

        assert result.title == "Test Story"
        assert result.status == "candidate"
        cursor.execute.assert_called_once()

    def test_get_story_with_evidence(self, mock_db, sample_story_row, sample_evidence_row):
        """Test getting a story with full details."""
        db, cursor = mock_db

        # Mock multiple fetchone calls
        cursor.fetchone.side_effect = [
            sample_story_row,  # Story
            sample_evidence_row,  # Evidence
            None,  # Sync metadata
        ]
        cursor.fetchall.return_value = []  # Comments

        service = StoryService(db)
        result = service.get(sample_story_row["id"])

        assert result is not None
        assert result.title == "Test Story"
        assert result.evidence is not None
        assert len(result.evidence.conversation_ids) == 3

    def test_get_story_not_found(self, mock_db):
        """Test getting a non-existent story."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        service = StoryService(db)
        result = service.get(uuid4())

        assert result is None

    def test_update_story(self, mock_db, sample_story_row):
        """Test updating story fields."""
        db, cursor = mock_db
        updated_row = {**sample_story_row, "status": "triaged"}
        cursor.fetchone.return_value = updated_row

        service = StoryService(db)
        updates = StoryUpdate(status="triaged")
        result = service.update(sample_story_row["id"], updates)

        assert result.status == "triaged"

    def test_list_stories(self, mock_db, sample_story_row):
        """Test listing stories."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"count": 1}
        cursor.fetchall.return_value = [sample_story_row]

        service = StoryService(db)
        result = service.list(status="candidate", limit=10)

        assert isinstance(result, StoryListResponse)
        assert result.total == 1
        assert len(result.stories) == 1

    def test_get_by_status(self, mock_db, sample_story_row):
        """Test getting stories by status."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [sample_story_row]

        service = StoryService(db)
        result = service.get_by_status("candidate")

        assert len(result) == 1
        assert result[0].status == "candidate"

    def test_get_board_view(self, mock_db, sample_story_row):
        """Test getting board view grouped by status."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [
            sample_story_row,
            {**sample_story_row, "id": uuid4(), "status": "triaged"},
        ]

        service = StoryService(db)
        result = service.get_board_view()

        assert "candidate" in result
        assert "triaged" in result

    def test_search_stories(self, mock_db, sample_story_row):
        """Test searching stories."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [sample_story_row]

        service = StoryService(db)
        result = service.search("Test")

        assert len(result) == 1
        assert "Test" in result[0].title

    def test_delete_story(self, mock_db):
        """Test deleting a story."""
        db, cursor = mock_db
        cursor.rowcount = 1

        service = StoryService(db)
        result = service.delete(uuid4())

        assert result is True


# -----------------------------------------------------------------------------
# EvidenceService Tests
# -----------------------------------------------------------------------------

class TestEvidenceService:
    """Tests for EvidenceService."""

    def test_get_for_story(self, mock_db, sample_evidence_row):
        """Test getting evidence for a story."""
        db, cursor = mock_db
        cursor.fetchone.return_value = sample_evidence_row

        service = EvidenceService(db)
        result = service.get_for_story(sample_evidence_row["story_id"])

        assert result is not None
        assert len(result.conversation_ids) == 3
        assert result.source_stats["intercom"] == 3

    def test_get_for_story_not_found(self, mock_db):
        """Test getting evidence for story without evidence."""
        db, cursor = mock_db
        cursor.fetchone.return_value = None

        service = EvidenceService(db)
        result = service.get_for_story(uuid4())

        assert result is None

    def test_create_or_update_new(self, mock_db, sample_evidence_row):
        """Test creating new evidence."""
        db, cursor = mock_db
        cursor.fetchone.side_effect = [None, sample_evidence_row]

        service = EvidenceService(db)
        result = service.create_or_update(
            story_id=sample_evidence_row["story_id"],
            conversation_ids=["conv1", "conv2"],
            theme_signatures=["Theme 1"],
            source_stats={"intercom": 2},
            excerpts=[EvidenceExcerpt(text="test", source="intercom")],
        )

        assert result is not None
        assert len(result.conversation_ids) == 3  # From mock

    def test_add_conversation(self, mock_db, sample_evidence_row):
        """Test adding a conversation to evidence."""
        db, cursor = mock_db
        # First call returns existing evidence, second returns updated
        cursor.fetchone.side_effect = [
            {
                "id": sample_evidence_row["id"],
                "conversation_ids": ["conv1"],
                "source_stats": {"intercom": 1},
                "excerpts": [],
            },
            sample_evidence_row,
        ]

        service = EvidenceService(db)
        result = service.add_conversation(
            story_id=sample_evidence_row["story_id"],
            conversation_id="conv2",
            source="intercom",
            excerpt="User reported issue",
        )

        assert result is not None

    def test_add_theme(self, mock_db, sample_evidence_row):
        """Test adding a theme to evidence."""
        db, cursor = mock_db
        cursor.fetchone.side_effect = [
            {"id": sample_evidence_row["id"], "theme_signatures": ["Theme 1"]},
            sample_evidence_row,
        ]

        service = EvidenceService(db)
        result = service.add_theme(
            story_id=sample_evidence_row["story_id"],
            theme_signature="Theme 2",
        )

        assert result is not None

    def test_get_by_conversation(self, mock_db, sample_evidence_row):
        """Test finding evidence by conversation ID."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [sample_evidence_row]

        service = EvidenceService(db)
        result = service.get_by_conversation("conv1")

        assert len(result) == 1
        assert "conv1" in result[0].conversation_ids

    def test_get_by_theme(self, mock_db, sample_evidence_row):
        """Test finding evidence by theme signature."""
        db, cursor = mock_db
        cursor.fetchall.return_value = [sample_evidence_row]

        service = EvidenceService(db)
        result = service.get_by_theme("Scheduler: Pin scheduling fails")

        assert len(result) == 1


# -----------------------------------------------------------------------------
# Model Tests
# -----------------------------------------------------------------------------

class TestModels:
    """Tests for Pydantic models."""

    def test_story_create(self):
        """Test StoryCreate model."""
        story = StoryCreate(
            title="Test",
            description="Description",
            product_area="Scheduler",
        )
        assert story.title == "Test"
        assert story.status == "candidate"  # Default

    def test_story_update_partial(self):
        """Test StoryUpdate with partial fields."""
        update = StoryUpdate(status="triaged")
        assert update.status == "triaged"
        assert update.title is None

    def test_evidence_excerpt(self):
        """Test EvidenceExcerpt model."""
        excerpt = EvidenceExcerpt(
            text="User said this",
            source="intercom",
            conversation_id="123",
        )
        assert excerpt.text == "User said this"
        assert excerpt.source == "intercom"

    def test_story_list_response(self):
        """Test StoryListResponse model."""
        response = StoryListResponse(
            stories=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert response.total == 0
        assert response.limit == 50
