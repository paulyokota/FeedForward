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
    CodeContext,
    CodeContextClassification,
    CodeContextFile,
    CodeContextSnippet,
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
        "code_context": None,  # No code context by default
        "evidence_count": 3,
        "conversation_count": 5,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


@pytest.fixture
def sample_code_context():
    """Sample code_context JSONB data."""
    return {
        "classification": {
            "category": "scheduling",
            "confidence": "high",
            "reasoning": "Issue mentions scheduled pins",
            "keywords_matched": ["schedule", "pin"],
        },
        "relevant_files": [
            {
                "path": "packages/scheduler/pin_scheduler.ts",
                "line_start": 142,
                "line_end": None,
                "relevance": "5 matches: schedule, pin",
            },
        ],
        "code_snippets": [
            {
                "file_path": "packages/scheduler/pin_scheduler.ts",
                "line_start": 140,
                "line_end": 160,
                "content": "async function schedulePin() { }",
                "language": "typescript",
                "context": "Main scheduling function",
            },
        ],
        "exploration_duration_ms": 350,
        "classification_duration_ms": 180,
        "explored_at": "2025-01-20T12:00:00+00:00",
        "success": True,
        "error": None,
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


# -----------------------------------------------------------------------------
# Code Context Tests (Issue #44)
# -----------------------------------------------------------------------------

class TestCodeContextModels:
    """Tests for CodeContext Pydantic models."""

    def test_code_context_classification_model(self):
        """Test CodeContextClassification model."""
        classification = CodeContextClassification(
            category="scheduling",
            confidence="high",
            reasoning="Issue mentions scheduled pins",
            keywords_matched=["schedule", "pin"],
        )
        assert classification.category == "scheduling"
        assert classification.confidence == "high"
        assert len(classification.keywords_matched) == 2

    def test_code_context_file_model(self):
        """Test CodeContextFile model."""
        file_ref = CodeContextFile(
            path="packages/scheduler/service.ts",
            line_start=100,
            line_end=150,
            relevance="5 matches: schedule",
        )
        assert file_ref.path == "packages/scheduler/service.ts"
        assert file_ref.line_start == 100

    def test_code_context_snippet_model(self):
        """Test CodeContextSnippet model."""
        snippet = CodeContextSnippet(
            file_path="service.py",
            line_start=50,
            line_end=60,
            content="def process(): pass",
            language="python",
            context="Processing function",
        )
        assert snippet.language == "python"
        assert snippet.content == "def process(): pass"

    def test_code_context_model(self, sample_code_context):
        """Test CodeContext model with full data."""
        code_context = CodeContext(
            classification=CodeContextClassification(
                **sample_code_context["classification"]
            ),
            relevant_files=[
                CodeContextFile(**f) for f in sample_code_context["relevant_files"]
            ],
            code_snippets=[
                CodeContextSnippet(**s) for s in sample_code_context["code_snippets"]
            ],
            exploration_duration_ms=350,
            classification_duration_ms=180,
            success=True,
        )
        assert code_context.classification.category == "scheduling"
        assert len(code_context.relevant_files) == 1
        assert len(code_context.code_snippets) == 1
        assert code_context.success is True

    def test_story_create_with_code_context(self, sample_code_context):
        """Test StoryCreate model with code_context."""
        story = StoryCreate(
            title="Test Story with Code Context",
            description="Description",
            product_area="Scheduler",
            code_context=sample_code_context,
        )
        assert story.code_context is not None
        assert story.code_context["classification"]["category"] == "scheduling"

    def test_story_update_with_code_context(self, sample_code_context):
        """Test StoryUpdate model with code_context."""
        update = StoryUpdate(code_context=sample_code_context)
        assert update.code_context is not None
        assert update.code_context["success"] is True


class TestCodeContextPersistence:
    """Tests for code_context persistence in StoryService."""

    def test_create_story_with_code_context(self, mock_db, sample_story_row, sample_code_context):
        """Test creating a story with code_context."""
        db, cursor = mock_db
        # Return row with code_context
        row_with_context = {**sample_story_row, "code_context": sample_code_context}
        cursor.fetchone.return_value = row_with_context

        service = StoryService(db)
        story_create = StoryCreate(
            title="Story with Code",
            description="Description",
            product_area="Scheduler",
            code_context=sample_code_context,
        )

        result = service.create(story_create)

        assert result.code_context is not None
        assert result.code_context.classification.category == "scheduling"
        assert len(result.code_context.relevant_files) == 1

    def test_get_story_with_code_context(self, mock_db, sample_story_row, sample_code_context, sample_evidence_row):
        """Test getting a story with code_context."""
        db, cursor = mock_db

        # Return row with code_context
        row_with_context = {**sample_story_row, "code_context": sample_code_context}
        cursor.fetchone.side_effect = [
            row_with_context,  # Story
            sample_evidence_row,  # Evidence
            None,  # Sync metadata
        ]
        cursor.fetchall.return_value = []  # Comments

        service = StoryService(db)
        result = service.get(sample_story_row["id"])

        assert result is not None
        assert result.code_context is not None
        assert result.code_context.classification.confidence == "high"
        assert result.code_context.exploration_duration_ms == 350

    def test_parse_code_context_from_dict(self, mock_db, sample_code_context):
        """Test _parse_code_context with dict input."""
        db, _ = mock_db
        service = StoryService(db)

        result = service._parse_code_context(sample_code_context)

        assert result is not None
        assert result.classification.category == "scheduling"
        assert len(result.relevant_files) == 1
        assert result.relevant_files[0].path == "packages/scheduler/pin_scheduler.ts"
        assert len(result.code_snippets) == 1
        assert result.code_snippets[0].language == "typescript"

    def test_parse_code_context_from_json_string(self, mock_db, sample_code_context):
        """Test _parse_code_context with JSON string input."""
        import json
        db, _ = mock_db
        service = StoryService(db)

        json_string = json.dumps(sample_code_context)
        result = service._parse_code_context(json_string)

        assert result is not None
        assert result.classification.category == "scheduling"

    def test_parse_code_context_with_none(self, mock_db):
        """Test _parse_code_context with None input."""
        db, _ = mock_db
        service = StoryService(db)

        result = service._parse_code_context(None)

        assert result is None

    def test_parse_code_context_without_classification(self, mock_db):
        """Test _parse_code_context when classification is missing."""
        db, _ = mock_db
        service = StoryService(db)

        data_without_classification = {
            "classification": None,
            "relevant_files": [],
            "code_snippets": [],
            "success": False,
            "error": "Classification failed",
        }

        result = service._parse_code_context(data_without_classification)

        assert result is not None
        assert result.classification is None
        assert result.success is False
        assert result.error == "Classification failed"

    def test_parse_code_context_with_invalid_json(self, mock_db):
        """Test _parse_code_context handles invalid JSON gracefully."""
        db, _ = mock_db
        service = StoryService(db)

        result = service._parse_code_context("not valid json {")

        assert result is None

    def test_update_story_with_code_context(self, mock_db, sample_story_row, sample_code_context):
        """Test updating a story's code_context."""
        db, cursor = mock_db
        row_with_context = {**sample_story_row, "code_context": sample_code_context}
        cursor.fetchone.return_value = row_with_context

        service = StoryService(db)
        updates = StoryUpdate(code_context=sample_code_context)
        result = service.update(sample_story_row["id"], updates)

        assert result.code_context is not None
        # Verify JSON was serialized in the SQL call
        call_args = cursor.execute.call_args
        assert "code_context" in call_args[0][0]

    def test_list_stories_with_code_context(self, mock_db, sample_story_row, sample_code_context):
        """Test listing stories includes code_context."""
        db, cursor = mock_db
        row_with_context = {**sample_story_row, "code_context": sample_code_context}
        cursor.fetchone.return_value = {"count": 1}
        cursor.fetchall.return_value = [row_with_context]

        service = StoryService(db)
        result = service.list(limit=10)

        assert len(result.stories) == 1
        assert result.stories[0].code_context is not None
        assert result.stories[0].code_context.classification.category == "scheduling"


# -----------------------------------------------------------------------------
# Created Since Filter Tests (Issue #54)
# -----------------------------------------------------------------------------

class TestCreatedSinceFilter:
    """Tests for created_since filtering in StoryService."""

    def test_list_stories_with_created_since(self, mock_db, sample_story_row):
        """Test filtering stories by created_since timestamp."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"count": 1}
        cursor.fetchall.return_value = [sample_story_row]

        service = StoryService(db)
        result = service.list(created_since="2025-01-15T10:30:00Z", limit=10)

        assert isinstance(result, StoryListResponse)
        assert result.total == 1
        # Verify the SQL includes created_at filter
        call_args = cursor.execute.call_args_list
        # Second call is the SELECT for stories
        select_call = call_args[1][0][0]
        assert "created_at >=" in select_call
        # Check the timestamp value was passed
        values = call_args[1][0][1]
        assert "2025-01-15T10:30:00Z" in values

    def test_list_stories_with_created_since_and_status(self, mock_db, sample_story_row):
        """Test combining created_since with status filter."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"count": 1}
        cursor.fetchall.return_value = [sample_story_row]

        service = StoryService(db)
        result = service.list(
            status="candidate",
            created_since="2025-01-15T10:30:00Z",
            limit=10,
        )

        assert result.total == 1
        # Verify both filters in SQL
        call_args = cursor.execute.call_args_list
        select_call = call_args[1][0][0]
        assert "status = %s" in select_call
        assert "created_at >=" in select_call

    def test_list_stories_without_created_since(self, mock_db, sample_story_row):
        """Test that created_since is optional (None by default)."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"count": 5}
        cursor.fetchall.return_value = [sample_story_row] * 5

        service = StoryService(db)
        result = service.list(limit=10)

        assert result.total == 5
        # Verify no created_at filter in SQL
        call_args = cursor.execute.call_args_list
        select_call = call_args[1][0][0]
        assert "created_at >=" not in select_call
