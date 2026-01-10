"""
Pipeline Integration Service Tests

Tests for PipelineIntegrationService that bridges theme extraction
to story creation.

Run with: pytest tests/test_pipeline_integration.py -v
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
    StoryWithEvidence,
    StoryEvidence,
    EvidenceExcerpt,
)
from story_tracking.services import (
    StoryService,
    EvidenceService,
    PipelineIntegrationService,
    ValidatedGroup,
)


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
def story_service(mock_db):
    """Create StoryService with mock DB."""
    db, cursor = mock_db
    return StoryService(db)


@pytest.fixture
def evidence_service(mock_db):
    """Create EvidenceService with mock DB."""
    db, cursor = mock_db
    return EvidenceService(db)


@pytest.fixture
def pipeline_service(story_service, evidence_service):
    """Create PipelineIntegrationService."""
    return PipelineIntegrationService(story_service, evidence_service)


@pytest.fixture
def sample_validated_group():
    """Sample validated group from PM review."""
    return ValidatedGroup(
        signature="pin_deletion_request",
        conversation_ids=["conv1", "conv2", "conv3"],
        theme_signatures=["Scheduler: Pin deletion request"],
        title="Users unable to delete multiple pins",
        description="Multiple users reporting they cannot delete scheduled pins in bulk",
        product_area="Scheduler",
        technical_area="Backend",
        confidence_score=0.85,
        excerpts=[
            {
                "text": "I can't delete my scheduled pins",
                "source": "intercom",
                "conversation_id": "conv1",
            },
            {
                "text": "Bulk delete feature not working",
                "source": "intercom",
                "conversation_id": "conv2",
            },
            {
                "text": "Need to delete multiple pins at once",
                "source": "coda",
                "conversation_id": "conv3",
            },
        ],
    )


@pytest.fixture
def sample_story_row():
    """Sample story row from database."""
    story_id = uuid4()
    return {
        "id": story_id,
        "title": "Users unable to delete multiple pins",
        "description": "Multiple users reporting they cannot delete scheduled pins in bulk",
        "labels": ["auto-generated", "scheduler"],
        "priority": None,
        "severity": None,
        "product_area": "Scheduler",
        "technical_area": "Backend",
        "status": "candidate",
        "confidence_score": 0.85,
        "evidence_count": 3,
        "conversation_count": 3,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


@pytest.fixture
def sample_evidence_row(sample_story_row):
    """Sample evidence row from database."""
    return {
        "id": uuid4(),
        "story_id": sample_story_row["id"],
        "conversation_ids": ["conv1", "conv2", "conv3"],
        "theme_signatures": ["Scheduler: Pin deletion request"],
        "source_stats": {"intercom": 2, "coda": 1},
        "excerpts": [
            {"text": "I can't delete my scheduled pins", "source": "intercom", "conversation_id": "conv1"},
            {"text": "Bulk delete feature not working", "source": "intercom", "conversation_id": "conv2"},
            {"text": "Need to delete multiple pins at once", "source": "coda", "conversation_id": "conv3"},
        ],
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


# -----------------------------------------------------------------------------
# PipelineIntegrationService Tests
# -----------------------------------------------------------------------------

class TestPipelineIntegrationService:
    """Tests for PipelineIntegrationService."""

    def test_create_candidate_story_success(
        self, pipeline_service, mock_db, sample_validated_group, sample_story_row, sample_evidence_row
    ):
        """Test creating a candidate story from validated group."""
        db, cursor = mock_db

        # Mock sequence:
        # 1. find_existing_story -> search() -> fetchall
        # 2. create() -> fetchone
        # 3. create_or_update evidence check -> fetchone
        # 4. create_or_update insert -> fetchone
        # 5. get() story -> fetchone
        # 6. get() evidence -> fetchone
        # 7. get() comments -> fetchall
        # 8. get() sync -> fetchone

        cursor.fetchall.side_effect = [
            [],  # search() returns no existing stories
            [],  # get() returns no comments
        ]
        cursor.fetchone.side_effect = [
            sample_story_row,  # create() returns story
            None,  # evidence create_or_update check (no existing)
            sample_evidence_row,  # evidence create_or_update insert
            sample_story_row,  # get() returns story
            sample_evidence_row,  # get() returns evidence
            None,  # get() returns no sync metadata
        ]

        # Create story
        result = pipeline_service.create_candidate_story(sample_validated_group)

        # Verify result
        assert result is not None
        assert result.title == sample_validated_group.title
        assert result.status == "candidate"
        assert "auto-generated" in result.labels
        assert result.product_area == sample_validated_group.product_area
        assert result.confidence_score == sample_validated_group.confidence_score

    def test_create_candidate_story_with_evidence(
        self, pipeline_service, mock_db, sample_validated_group, sample_story_row, sample_evidence_row
    ):
        """Test that evidence is created correctly."""
        db, cursor = mock_db

        # Mock responses
        cursor.fetchall.return_value = []  # No existing stories
        cursor.fetchone.side_effect = [
            sample_story_row,  # create() returns story
            None,  # evidence create_or_update check (no existing)
            sample_evidence_row,  # evidence create_or_update returns evidence
            sample_story_row,  # get() returns story
            sample_evidence_row,  # get() returns evidence
            None,  # get() returns no sync
        ]
        cursor.fetchall.side_effect = [
            [],  # search() returns no existing
            [],  # get() returns no comments
        ]

        result = pipeline_service.create_candidate_story(sample_validated_group)

        # Verify evidence was created
        assert result.evidence is not None
        assert len(result.evidence.conversation_ids) == 3
        assert len(result.evidence.theme_signatures) == 1
        assert result.evidence.source_stats["intercom"] == 2
        assert result.evidence.source_stats["coda"] == 1

    def test_create_candidate_story_duplicate_skip(
        self, pipeline_service, mock_db, sample_validated_group, sample_story_row, sample_evidence_row
    ):
        """Test that duplicate stories are skipped."""
        db, cursor = mock_db

        # Mock search finding existing story
        existing_story = {**sample_story_row, "labels": ["auto-generated", sample_validated_group.signature]}

        # Mock sequence:
        # 1. find_existing_story -> search() -> fetchall
        # 2. find_existing_story -> get() story -> fetchone
        # 3. find_existing_story -> get() evidence -> fetchone
        # 4. find_existing_story -> get() comments -> fetchall
        # 5. find_existing_story -> get() sync -> fetchone

        cursor.fetchall.side_effect = [
            [existing_story],  # search() finds existing
            [],  # get() returns no comments
        ]
        cursor.fetchone.side_effect = [
            existing_story,  # get() returns existing story
            sample_evidence_row,  # get() returns evidence
            None,  # get() returns no sync
        ]

        result = pipeline_service.create_candidate_story(sample_validated_group)

        # Should return existing story, not create new one
        assert result is not None
        assert result.id == sample_story_row["id"]

    def test_create_candidate_story_validation_errors(self, pipeline_service, sample_validated_group):
        """Test validation of required fields."""
        # Missing title
        group_no_title = ValidatedGroup(
            signature="test",
            conversation_ids=["conv1"],
            theme_signatures=["theme1"],
            title="",  # Empty title
            description="test",
        )

        with pytest.raises(ValueError, match="title is required"):
            pipeline_service.create_candidate_story(group_no_title)

        # Missing conversation_ids
        group_no_convs = ValidatedGroup(
            signature="test",
            conversation_ids=[],  # Empty
            theme_signatures=["theme1"],
            title="Test",
            description="test",
        )

        with pytest.raises(ValueError, match="conversation_id is required"):
            pipeline_service.create_candidate_story(group_no_convs)

    def test_bulk_create_candidates_success(
        self, pipeline_service, sample_validated_group
    ):
        """Test bulk creating multiple candidate stories."""
        from unittest.mock import patch, Mock

        # Mock create_candidate_story to avoid complex DB mocking
        mock_story1 = Mock(id=uuid4(), title="Story 1")
        mock_story2 = Mock(id=uuid4(), title="Story 2")

        with patch.object(pipeline_service, 'find_existing_story', side_effect=[None, None]), \
             patch.object(pipeline_service, 'create_candidate_story', side_effect=[mock_story1, mock_story2]):

            # Create multiple groups
            group1 = sample_validated_group
            group2 = ValidatedGroup(
                signature="billing_cancellation",
                conversation_ids=["conv4"],
                theme_signatures=["Billing: Cancellation issues"],
                title="Users unable to cancel subscription",
                description="Users reporting they cannot cancel their subscription",
                product_area="Billing",
            )

            groups = [group1, group2]
            results = pipeline_service.bulk_create_candidates(groups)

            assert len(results) == 2
            assert results[0].id == mock_story1.id
            assert results[1].id == mock_story2.id

    def test_bulk_create_candidates_skip_duplicates(
        self, pipeline_service, sample_validated_group
    ):
        """Test that bulk import skips duplicates."""
        from unittest.mock import patch, Mock

        # Mock: first group creates story, second is duplicate
        mock_story1 = Mock(id=uuid4(), title="Story 1")
        mock_existing = Mock(id=uuid4(), title="Existing Story")

        with patch.object(pipeline_service, 'find_existing_story', side_effect=[None, mock_existing]), \
             patch.object(pipeline_service, 'create_candidate_story', return_value=mock_story1) as mock_create:

            # Create groups with one duplicate
            group1 = sample_validated_group
            group2 = ValidatedGroup(
                signature="pin_deletion_request",  # Same as group1
                conversation_ids=["conv5"],
                theme_signatures=["Scheduler: Pin deletion request"],
                title="Duplicate story",
                description="Should be skipped",
            )

            groups = [group1, group2]
            results = pipeline_service.bulk_create_candidates(groups)

            # Only group1 should be created, group2 skipped
            assert len(results) == 1
            assert results[0].id == mock_story1.id

            # Verify create was only called once (for group1)
            assert mock_create.call_count == 1

    def test_bulk_create_candidates_error_handling(
        self, pipeline_service, mock_db, sample_validated_group, sample_story_row, sample_evidence_row
    ):
        """Test that bulk import handles errors gracefully."""
        db, cursor = mock_db

        # Create groups with one that will fail
        group1 = sample_validated_group
        group2 = ValidatedGroup(
            signature="bad_group",
            conversation_ids=[],  # Will fail validation
            theme_signatures=["theme"],
            title="Bad Group",
            description="Should fail",
        )

        groups = [group1, group2]

        # Mock sequence:
        # Group 1: successful creation
        # Group 2: will fail validation before any DB calls
        cursor.fetchall.side_effect = [
            [],  # search for group1
            [],  # get comments for group1
            [],  # search for group2 (even though it fails validation, find_existing_story is called first)
        ]
        cursor.fetchone.side_effect = [
            sample_story_row,  # create group1
            None,  # evidence check group1
            sample_evidence_row,  # create evidence group1
            sample_story_row,  # get group1 story
            sample_evidence_row,  # get group1 evidence
            None,  # get group1 sync
            # Group 2 fails validation, no more DB calls
        ]

        # Should continue despite error
        results = pipeline_service.bulk_create_candidates(groups)

        # Only successful story should be returned
        assert len(results) == 1
        assert results[0].title == group1.title

    def test_find_existing_story_found(
        self, pipeline_service, mock_db, sample_story_row, sample_evidence_row
    ):
        """Test finding an existing story by signature."""
        db, cursor = mock_db

        # Mock search finding story with signature in labels
        existing_story = {**sample_story_row, "labels": ["auto-generated", "pin_deletion_request"]}
        cursor.fetchall.return_value = [existing_story]
        cursor.fetchone.side_effect = [
            existing_story,  # get() returns story
            sample_evidence_row,  # get() returns evidence
            None,  # get() returns no sync
        ]
        cursor.fetchall.side_effect = [
            [existing_story],  # search() finds story
            [],  # get() returns no comments
        ]

        result = pipeline_service.find_existing_story("pin_deletion_request")

        assert result is not None
        assert "pin_deletion_request" in result.labels

    def test_find_existing_story_not_found(self, pipeline_service, mock_db):
        """Test finding non-existent story."""
        db, cursor = mock_db
        cursor.fetchall.return_value = []

        result = pipeline_service.find_existing_story("nonexistent_signature")

        assert result is None

    def test_prepare_excerpts(self, pipeline_service):
        """Test excerpt preparation."""
        excerpts_data = [
            {"text": "Test 1", "source": "intercom", "conversation_id": "conv1"},
            {"text": "Test 2", "source": "coda", "conversation_id": "conv2"},
            {"text": "Test 3", "source": "intercom"},  # Missing conversation_id
        ]

        excerpts = pipeline_service._prepare_excerpts(excerpts_data)

        assert len(excerpts) == 3
        assert all(isinstance(e, EvidenceExcerpt) for e in excerpts)
        assert excerpts[0].text == "Test 1"
        assert excerpts[0].source == "intercom"
        assert excerpts[2].conversation_id is None

    def test_calculate_source_stats(self, pipeline_service):
        """Test source statistics calculation."""
        excerpts_data = [
            {"source": "intercom"},
            {"source": "intercom"},
            {"source": "coda"},
            {"source": "intercom"},
        ]

        stats = pipeline_service._calculate_source_stats(excerpts_data)

        assert stats["intercom"] == 3
        assert stats["coda"] == 1

    def test_labels_include_product_area(
        self, pipeline_service, mock_db, sample_validated_group, sample_story_row, sample_evidence_row
    ):
        """Test that product area is added to labels."""
        db, cursor = mock_db

        cursor.fetchall.side_effect = [[], []]
        cursor.fetchone.side_effect = [
            sample_story_row,
            None,
            sample_evidence_row,
            sample_story_row,
            sample_evidence_row,
            None,
        ]

        result = pipeline_service.create_candidate_story(sample_validated_group)

        assert "auto-generated" in result.labels
        assert "scheduler" in result.labels  # product_area lowercased


# -----------------------------------------------------------------------------
# ValidatedGroup Tests
# -----------------------------------------------------------------------------

class TestValidatedGroup:
    """Tests for ValidatedGroup dataclass."""

    def test_validated_group_creation(self):
        """Test creating ValidatedGroup."""
        group = ValidatedGroup(
            signature="test_signature",
            conversation_ids=["conv1"],
            theme_signatures=["theme1"],
            title="Test Title",
            description="Test Description",
        )

        assert group.signature == "test_signature"
        assert group.title == "Test Title"
        assert group.product_area is None  # Optional field

    def test_validated_group_with_optional_fields(self):
        """Test ValidatedGroup with all fields."""
        group = ValidatedGroup(
            signature="test_signature",
            conversation_ids=["conv1"],
            theme_signatures=["theme1"],
            title="Test Title",
            description="Test Description",
            product_area="Scheduler",
            technical_area="Backend",
            confidence_score=0.95,
            excerpts=[{"text": "test", "source": "intercom"}],
        )

        assert group.product_area == "Scheduler"
        assert group.confidence_score == 0.95
        assert len(group.excerpts) == 1
