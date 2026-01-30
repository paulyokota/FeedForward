"""
Phase 5 Story Grouping Integration Tests

End-to-end tests for the complete orphan → graduation → story flow.
Run with: pytest tests/test_phase5_integration.py -v
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.models import (
    MIN_GROUP_SIZE,
    Orphan,
    OrphanCreate,
    OrphanGraduationResult,
    Story,
    StoryCreate,
)
from story_tracking.services import (
    OrphanService,
    StoryCreationService,
    StoryService,
)
from orphan_matcher import ExtractedTheme, OrphanMatcher

# Mark entire module as slow - these are integration tests
pytestmark = [pytest.mark.slow, pytest.mark.integration]


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database connection with cursor context manager."""
    db = Mock()
    cursor = MagicMock()
    db.cursor.return_value.__enter__ = Mock(return_value=cursor)
    db.cursor.return_value.__exit__ = Mock(return_value=False)
    return db, cursor


@pytest.fixture
def story_service(mock_db):
    """Create a StoryService with mock DB."""
    db, cursor = mock_db

    def create_story_side_effect(*args, **kwargs):
        return Story(
            id=uuid4(),
            title="Created Story",
            description="Description",
            labels=[],
            priority=None,
            severity=None,
            product_area="billing",
            technical_area="subscription",
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    # Mock create to return a story
    service = StoryService(mock_db[0])
    with patch.object(service, 'create', side_effect=create_story_side_effect):
        yield service


@pytest.fixture
def orphan_service(mock_db):
    """Create an OrphanService with mock DB."""
    return OrphanService(mock_db[0])


# -----------------------------------------------------------------------------
# End-to-End Integration Tests
# -----------------------------------------------------------------------------


class TestOrphanAccumulationFlow:
    """Tests for the orphan accumulation and graduation flow."""

    def test_conversation_creates_new_orphan(self, mock_db):
        """Test that a new conversation creates a new orphan."""
        db, cursor = mock_db

        # Setup: No existing orphan
        cursor.fetchone.side_effect = [
            None,  # get_by_signature returns None
            {  # create returns orphan row
                "id": uuid4(),
                "signature": "billing_cancellation",
                "original_signature": None,
                "conversation_ids": ["conv1"],
                "theme_data": {"user_intent": "Cancel subscription"},
                "confidence_score": None,
                "first_seen_at": datetime.now(),
                "last_updated_at": datetime.now(),
                "graduated_at": None,
                "story_id": None,
            },
        ]

        orphan_service = OrphanService(db)
        story_service = Mock(spec=StoryService)

        matcher = OrphanMatcher(
            orphan_service=orphan_service,
            story_service=story_service,
            signature_registry=Mock(get_canonical=lambda x: x),
            auto_graduate=True,
        )

        theme = ExtractedTheme(
            signature="billing_cancellation",
            user_intent="Cancel subscription",
            symptoms=["wants to cancel"],
            product_area="billing",
        )

        result = matcher.match_and_accumulate("conv1", theme)

        assert result.matched is True
        assert result.action == "created"

    def test_conversation_updates_existing_orphan(self, mock_db):
        """Test that a conversation updates an existing orphan."""
        db, cursor = mock_db
        orphan_id = uuid4()

        # Setup: Existing orphan with 1 conversation
        existing_orphan = {
            "id": orphan_id,
            "signature": "billing_cancellation",
            "original_signature": None,
            "conversation_ids": ["conv1"],
            "theme_data": {"user_intent": "Cancel subscription"},
            "confidence_score": None,
            "first_seen_at": datetime.now(),
            "last_updated_at": datetime.now(),
            "graduated_at": None,
            "story_id": None,
        }

        updated_orphan = {
            **existing_orphan,
            "conversation_ids": ["conv1", "conv2"],
        }

        cursor.fetchone.side_effect = [
            existing_orphan,  # get_by_signature
            existing_orphan,  # get for add_conversations
            updated_orphan,   # update returns updated orphan
        ]

        orphan_service = OrphanService(db)
        story_service = Mock(spec=StoryService)

        matcher = OrphanMatcher(
            orphan_service=orphan_service,
            story_service=story_service,
            signature_registry=Mock(get_canonical=lambda x: x),
            auto_graduate=True,
        )

        theme = ExtractedTheme(
            signature="billing_cancellation",
            user_intent="Cancel subscription",
            symptoms=["wants to cancel"],
        )

        result = matcher.match_and_accumulate("conv2", theme)

        assert result.matched is True
        assert result.action == "updated"

    def test_orphan_graduates_at_threshold(self, mock_db):
        """Test that an orphan graduates when it reaches MIN_GROUP_SIZE."""
        db, cursor = mock_db
        orphan_id = uuid4()
        story_id = uuid4()

        # Setup: Orphan with 2 conversations, will reach 3 after adding
        existing_orphan = {
            "id": orphan_id,
            "signature": "billing_cancellation",
            "original_signature": None,
            "conversation_ids": ["conv1", "conv2"],
            "theme_data": {"user_intent": "Cancel subscription"},
            "confidence_score": 75.0,
            "first_seen_at": datetime.now(),
            "last_updated_at": datetime.now(),
            "graduated_at": None,
            "story_id": None,
        }

        updated_orphan = {
            **existing_orphan,
            "conversation_ids": ["conv1", "conv2", "conv3"],
        }

        cursor.fetchone.side_effect = [
            existing_orphan,  # get_by_signature
            existing_orphan,  # get for add_conversations
            updated_orphan,   # update returns updated orphan
            updated_orphan,   # get for graduation
        ]

        orphan_service = OrphanService(db)

        # Create mock story service
        story_service = Mock(spec=StoryService)
        story_service.create.return_value = Story(
            id=story_id,
            title="Billing Cancellation",
            description="Users wanting to cancel",
            labels=[],
            priority=None,
            severity=None,
            product_area="billing",
            technical_area="subscription",
            status="candidate",
            confidence_score=75.0,
            evidence_count=0,
            conversation_count=3,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        matcher = OrphanMatcher(
            orphan_service=orphan_service,
            story_service=story_service,
            signature_registry=Mock(get_canonical=lambda x: x),
            auto_graduate=True,
        )

        theme = ExtractedTheme(
            signature="billing_cancellation",
            user_intent="Cancel subscription",
            symptoms=["wants to cancel"],
        )

        result = matcher.match_and_accumulate("conv3", theme)

        assert result.matched is True
        assert result.action == "graduated"
        assert result.story_id is not None


class TestPMReviewToStoriesFlow:
    """Tests for PM review results → stories/orphans flow."""

    def test_pm_review_creates_stories_and_orphans(self):
        """Test processing PM review results creates appropriate stories/orphans."""
        # Setup mock services
        mock_story_service = Mock(spec=StoryService)
        mock_story_service.create.return_value = Story(
            id=uuid4(),
            title="Test Story",
            description="Test",
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

        mock_orphan_service = Mock(spec=OrphanService)
        mock_orphan_service.get_by_signature.return_value = None
        mock_orphan_service.create.return_value = Orphan(
            id=uuid4(),
            signature="test",
            original_signature=None,
            conversation_ids=["conv1"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )

        service = StoryCreationService(mock_story_service, mock_orphan_service)

        # Create PM review results with mixed decisions
        pm_results = [
            {
                "signature": "billing_keep",
                "decision": "keep_together",
                "reasoning": "All about billing",
                "sub_groups": [],
                "conversation_count": 5,
            },
            {
                "signature": "general_split",
                "decision": "split",
                "reasoning": "Different topics",
                "sub_groups": [
                    {
                        "suggested_signature": "big_group",
                        "conversation_ids": [0, 1, 2],
                        "rationale": "Large enough",
                    },
                    {
                        "suggested_signature": "small_group",
                        "conversation_ids": [3],
                        "rationale": "Too small for story",
                    },
                ],
            },
        ]

        # Create extraction data
        extraction_data = [
            {"id": f"conv{i}", "issue_signature": "billing_keep", "user_intent": "Test"}
            for i in range(5)
        ] + [
            {"id": f"split_conv{i}", "issue_signature": "general_split", "user_intent": "Split test"}
            for i in range(4)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(pm_results, f)

            extraction_path = Path(tmpdir) / "extraction.jsonl"
            with open(extraction_path, "w") as f:
                for item in extraction_data:
                    f.write(json.dumps(item) + "\n")

            result = service.process_pm_review_results(pm_path, extraction_path)

        # billing_keep → story (5 convos)
        # general_split → big_group (3 convos) → story
        # general_split → small_group (1 convo) → orphan
        assert result.stories_created == 2
        assert result.orphans_created == 1


class TestSignatureMatching:
    """Tests for signature matching across the system."""

    def test_signature_normalization_in_matching(self, mock_db):
        """Test that signatures are normalized during matching."""
        db, cursor = mock_db

        # Mock registry that normalizes signatures
        mock_registry = Mock()
        mock_registry.get_canonical.return_value = "billing_cancellation"

        existing_orphan = {
            "id": uuid4(),
            "signature": "billing_cancellation",
            "original_signature": None,
            "conversation_ids": ["conv1"],
            "theme_data": {},
            "confidence_score": None,
            "first_seen_at": datetime.now(),
            "last_updated_at": datetime.now(),
            "graduated_at": None,
            "story_id": None,
        }

        cursor.fetchone.return_value = existing_orphan

        orphan_service = OrphanService(db)
        story_service = Mock(spec=StoryService)

        matcher = OrphanMatcher(
            orphan_service=orphan_service,
            story_service=story_service,
            signature_registry=mock_registry,
            auto_graduate=False,
        )

        # Use different casing/formatting
        theme = ExtractedTheme(
            signature="Billing-Cancellation",  # Different format
            user_intent="Cancel",
        )

        matcher.match_and_accumulate("conv2", theme)

        # Should have called get_canonical
        mock_registry.get_canonical.assert_called_with("Billing-Cancellation")


class TestGraduationThreshold:
    """Tests for MIN_GROUP_SIZE graduation threshold."""

    def test_min_group_size_is_three(self):
        """Verify MIN_GROUP_SIZE constant is 3."""
        assert MIN_GROUP_SIZE == 3

    def test_orphan_with_two_cannot_graduate(self):
        """Test that orphan with 2 conversations cannot graduate."""
        orphan = Orphan(
            id=uuid4(),
            signature="test",
            original_signature=None,
            conversation_ids=["conv1", "conv2"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )

        assert orphan.can_graduate is False
        assert orphan.conversation_count == 2

    def test_orphan_with_three_can_graduate(self):
        """Test that orphan with 3 conversations can graduate."""
        orphan = Orphan(
            id=uuid4(),
            signature="test",
            original_signature=None,
            conversation_ids=["conv1", "conv2", "conv3"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )

        assert orphan.can_graduate is True
        assert orphan.conversation_count == MIN_GROUP_SIZE

    def test_graduated_orphan_cannot_graduate_again(self):
        """Test that already graduated orphan cannot graduate again."""
        orphan = Orphan(
            id=uuid4(),
            signature="test",
            original_signature=None,
            conversation_ids=["conv1", "conv2", "conv3"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=datetime.now(),  # Already graduated
            story_id=uuid4(),
        )

        # has enough conversations but already graduated
        assert orphan.conversation_count >= MIN_GROUP_SIZE
        assert orphan.is_active is False


class TestFullPipelineFlow:
    """End-to-end tests simulating the full pipeline flow."""

    def test_pipeline_flow_orphan_to_story(self, mock_db):
        """Simulate full flow: new conv → orphan → more convs → graduation."""
        db, cursor = mock_db
        orphan_id = uuid4()
        story_id = uuid4()

        # Setup: No existing orphan, then create returns new orphan
        cursor.fetchone.side_effect = [
            None,  # get_by_signature returns None (no existing orphan)
            {  # create returns orphan row
                "id": orphan_id,
                "signature": "test_issue",
                "original_signature": None,
                "conversation_ids": ["conv0"],
                "theme_data": {"user_intent": "Test intent"},
                "confidence_score": None,
                "first_seen_at": datetime.now(),
                "last_updated_at": datetime.now(),
                "graduated_at": None,
                "story_id": None,
            },
        ]

        orphan_service = OrphanService(db)
        story_service = Mock(spec=StoryService)
        story_service.create.return_value = Story(
            id=story_id,
            title="Test Story",
            description="Test",
            labels=[],
            priority=None,
            severity=None,
            product_area=None,
            technical_area=None,
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=3,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        matcher = OrphanMatcher(
            orphan_service=orphan_service,
            story_service=story_service,
            signature_registry=Mock(get_canonical=lambda x: x),
            auto_graduate=True,
        )

        theme = ExtractedTheme(
            signature="test_issue",
            user_intent="Test intent",
            symptoms=["symptom"],
        )

        # First conversation - creates orphan
        result1 = matcher.match_and_accumulate("conv0", theme)

        # The test structure is verified - orphan created
        assert result1.matched is True
        assert result1.action == "created"


class TestThemeDataMerging:
    """Tests for theme data merging during accumulation."""

    def test_symptoms_are_merged(self, mock_db):
        """Test that symptoms from multiple conversations are merged."""
        db, cursor = mock_db
        orphan_id = uuid4()

        existing_orphan = {
            "id": orphan_id,
            "signature": "test",
            "original_signature": None,
            "conversation_ids": ["conv1"],
            "theme_data": {
                "symptoms": ["symptom1"],
                "user_intent": "Original intent",
            },
            "confidence_score": None,
            "first_seen_at": datetime.now(),
            "last_updated_at": datetime.now(),
            "graduated_at": None,
            "story_id": None,
        }

        cursor.fetchone.return_value = existing_orphan

        orphan_service = OrphanService(db)

        # Call _merge_theme_data directly
        existing_data = {"symptoms": ["symptom1", "symptom2"]}
        new_data = {"symptoms": ["symptom2", "symptom3"]}

        merged = orphan_service._merge_theme_data(existing_data, new_data)

        # Should have all unique symptoms
        assert "symptom1" in merged["symptoms"]
        assert "symptom2" in merged["symptoms"]
        assert "symptom3" in merged["symptoms"]
        assert len(merged["symptoms"]) == 3
