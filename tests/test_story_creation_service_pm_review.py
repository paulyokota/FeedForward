"""
Story Creation Service PM Review Integration Tests

Tests for StoryCreationService with PM review integration.
Run with: pytest tests/test_story_creation_service_pm_review.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.models import (
    MIN_GROUP_SIZE,
    Orphan,
    OrphanCreate,
    Story,
    StoryCreate,
)
from story_tracking.services import (
    OrphanService,
    StoryCreationService,
    StoryService,
)
from story_tracking.services.story_creation_service import (
    ConversationData,
    ProcessingResult,
)
from story_tracking.services.pm_review_service import (
    PMReviewService,
    PMReviewResult,
    ReviewDecision,
    ConversationContext as PMConversationContext,
    SubGroupSuggestion,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_story_service():
    """Create a mock story service."""
    service = Mock(spec=StoryService)
    service.create.return_value = Story(
        id=uuid4(),
        title="Test Story",
        description="Test description",
        labels=[],
        priority=None,
        severity=None,
        product_area="publishing",
        technical_area="pinterest",
        status="candidate",
        confidence_score=None,
        evidence_count=0,
        conversation_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    return service


@pytest.fixture
def mock_orphan_service():
    """Create a mock orphan service."""
    service = Mock(spec=OrphanService)
    service.get_by_signature.return_value = None  # No existing orphan
    service.create.return_value = Orphan(
        id=uuid4(),
        signature="test_sig",
        original_signature=None,
        conversation_ids=["conv_1"],
        theme_data={},
        first_seen_at=datetime.now(),
        last_updated_at=datetime.now(),
    )
    return service


@pytest.fixture
def mock_pm_review_service():
    """Create a mock PM review service."""
    service = Mock(spec=PMReviewService)
    return service


@pytest.fixture
def sample_theme_groups():
    """Create sample theme groups for testing."""
    return {
        "pinterest_duplicate_pins": [
            {
                "id": "conv_1",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Pins are duplicated",
                "symptoms": ["duplicate pins"],
                "affected_flow": "publishing",
                "excerpt": "My pins show up twice",
            },
            {
                "id": "conv_2",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Double pins appearing",
                "symptoms": ["duplicate pins"],
                "affected_flow": "publishing",
                "excerpt": "Pins appear twice",
            },
            {
                "id": "conv_3",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Duplicate content",
                "symptoms": ["duplicate pins"],
                "affected_flow": "publishing",
                "excerpt": "Duplicate pins issue",
            },
        ],
    }


@pytest.fixture
def mixed_theme_groups():
    """Create theme groups with mixed symptoms (should trigger split)."""
    return {
        "pinterest_publishing_failure": [
            {
                "id": "conv_1",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Pins are duplicated",
                "symptoms": ["duplicate pins"],
                "affected_flow": "publishing",
                "excerpt": "My pins show up twice",
            },
            {
                "id": "conv_2",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Double pins",
                "symptoms": ["duplicate pins"],
                "affected_flow": "publishing",
                "excerpt": "Pins appear twice",
            },
            {
                "id": "conv_3",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Duplicate content",
                "symptoms": ["duplicate pins"],
                "affected_flow": "publishing",
                "excerpt": "Duplicate pins issue",
            },
            {
                "id": "conv_4",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Pins are missing",
                "symptoms": ["missing pins"],
                "affected_flow": "publishing",
                "excerpt": "My pins disappeared",
            },
            {
                "id": "conv_5",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Pins vanished",
                "symptoms": ["missing pins"],
                "affected_flow": "publishing",
                "excerpt": "Pins are gone",
            },
            {
                "id": "conv_6",
                "product_area": "publishing",
                "component": "pinterest",
                "user_intent": "Lost pins",
                "symptoms": ["missing pins"],
                "affected_flow": "publishing",
                "excerpt": "Cannot find my pins",
            },
        ],
    }


# -----------------------------------------------------------------------------
# Test PM Review Disabled
# -----------------------------------------------------------------------------


class TestPMReviewDisabled:
    """Test behavior when PM review is disabled."""

    def test_pm_review_skipped_when_disabled(
        self, mock_story_service, mock_orphan_service, sample_theme_groups
    ):
        """Test that PM review is skipped when disabled."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_enabled=False,  # Disabled
        )

        result = service.process_theme_groups(sample_theme_groups)

        assert result.pm_review_skipped == 1
        assert result.pm_review_kept == 0
        assert result.pm_review_splits == 0
        assert result.stories_created == 1

    def test_pm_review_skipped_when_service_none(
        self, mock_story_service, mock_orphan_service, sample_theme_groups
    ):
        """Test that PM review is skipped when service is None."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=None,
            pm_review_enabled=True,  # Enabled but no service
        )

        result = service.process_theme_groups(sample_theme_groups)

        # Should be skipped because pm_review_enabled was set to False in __init__
        # when service is not available
        assert result.stories_created == 1


# -----------------------------------------------------------------------------
# Test PM Review Enabled - Keep Together
# -----------------------------------------------------------------------------


class TestPMReviewKeepTogether:
    """Test PM review keep_together decisions."""

    def test_pm_review_keep_together(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        sample_theme_groups,
    ):
        """Test that keep_together decision creates story normally."""
        # Configure mock PM review to return keep_together
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="pinterest_duplicate_pins",
            conversation_count=3,
            decision=ReviewDecision.KEEP_TOGETHER,
            reasoning="All conversations about duplicate pins",
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(sample_theme_groups)

        assert result.pm_review_kept == 1
        assert result.pm_review_splits == 0
        assert result.stories_created == 1
        mock_pm_review_service.review_group.assert_called_once()


# -----------------------------------------------------------------------------
# Test PM Review Enabled - Split
# -----------------------------------------------------------------------------


class TestPMReviewSplit:
    """Test PM review split decisions."""

    def test_pm_review_split_creates_subgroup_stories(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        mixed_theme_groups,
    ):
        """Test that split decision creates stories for valid sub-groups."""
        # Configure mock PM review to return split with two valid sub-groups
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="pinterest_publishing_failure",
            conversation_count=6,
            decision=ReviewDecision.SPLIT,
            reasoning="Conversations have different symptoms",
            sub_groups=[
                SubGroupSuggestion(
                    suggested_signature="pinterest_duplicate_pins",
                    conversation_ids=["conv_1", "conv_2", "conv_3"],
                    rationale="All about duplicate pins",
                ),
                SubGroupSuggestion(
                    suggested_signature="pinterest_missing_pins",
                    conversation_ids=["conv_4", "conv_5", "conv_6"],
                    rationale="All about missing pins",
                ),
            ],
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(mixed_theme_groups)

        assert result.pm_review_splits == 1
        assert result.pm_review_kept == 0
        # Two sub-groups, both with >= MIN_GROUP_SIZE should create 2 stories
        assert result.stories_created == 2
        assert mock_story_service.create.call_count == 2

    def test_pm_review_split_small_subgroups_become_orphans(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        mixed_theme_groups,
    ):
        """Test that small sub-groups become orphans."""
        # Configure mock PM review to return split with one small sub-group
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="pinterest_publishing_failure",
            conversation_count=6,
            decision=ReviewDecision.SPLIT,
            reasoning="Conversations have different symptoms",
            sub_groups=[
                SubGroupSuggestion(
                    suggested_signature="pinterest_duplicate_pins",
                    conversation_ids=["conv_1", "conv_2", "conv_3"],
                    rationale="All about duplicate pins",
                ),
                SubGroupSuggestion(
                    suggested_signature="pinterest_missing_pins",
                    conversation_ids=["conv_4", "conv_5"],  # Only 2 - below MIN_GROUP_SIZE
                    rationale="About missing pins",
                ),
            ],
            orphan_conversation_ids=["conv_6"],  # One orphan
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(mixed_theme_groups)

        assert result.pm_review_splits == 1
        # One valid sub-group creates 1 story
        assert result.stories_created == 1
        # Small sub-group (2 convs) + orphan (1 conv) -> orphan creation
        assert result.orphans_created >= 1

    def test_pm_review_split_with_orphan_conversations(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        mixed_theme_groups,
    ):
        """Test handling of orphan conversations from PM split."""
        # Configure mock PM review to return split with orphans
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="pinterest_publishing_failure",
            conversation_count=6,
            decision=ReviewDecision.SPLIT,
            reasoning="Conversations have different symptoms",
            sub_groups=[
                SubGroupSuggestion(
                    suggested_signature="pinterest_duplicate_pins",
                    conversation_ids=["conv_1", "conv_2", "conv_3"],
                    rationale="All about duplicate pins",
                ),
            ],
            orphan_conversation_ids=["conv_4", "conv_5", "conv_6"],
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(mixed_theme_groups)

        assert result.pm_review_splits == 1
        assert result.stories_created == 1
        # Orphans should be created
        assert result.orphans_created >= 1


# -----------------------------------------------------------------------------
# Test PM Review Enabled - Reject
# -----------------------------------------------------------------------------


class TestPMReviewReject:
    """Test PM review reject decisions."""

    def test_pm_review_reject_routes_all_to_orphans(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        sample_theme_groups,
    ):
        """Test that reject decision routes all conversations to orphans."""
        # Configure mock PM review to return reject
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="pinterest_duplicate_pins",
            conversation_count=3,
            decision=ReviewDecision.REJECT,
            reasoning="All conversations are about different issues",
            orphan_conversation_ids=["conv_1", "conv_2", "conv_3"],
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(sample_theme_groups)

        assert result.pm_review_rejects == 1  # REJECT increments rejects counter
        assert result.stories_created == 0  # No stories
        assert result.orphans_created >= 1 or result.orphans_updated >= 1


# -----------------------------------------------------------------------------
# Test PM Review Error Handling
# -----------------------------------------------------------------------------


class TestPMReviewErrorHandling:
    """Test PM review error handling."""

    def test_pm_review_error_defaults_to_keep_together(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        sample_theme_groups,
    ):
        """Test that PM review errors default to keep_together."""
        # Configure mock PM review to raise an exception
        mock_pm_review_service.review_group.side_effect = Exception("API timeout")

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        # The _run_pm_review method catches exceptions and returns keep_together
        result = service.process_theme_groups(sample_theme_groups)

        # Should still create a story (defaulting to keep_together)
        assert result.stories_created == 1


# -----------------------------------------------------------------------------
# Test ProcessingResult PM Review Metrics
# -----------------------------------------------------------------------------


class TestProcessingResultPMMetrics:
    """Test ProcessingResult PM review metrics."""

    def test_processing_result_has_pm_metrics(self):
        """Test that ProcessingResult has PM review metric fields."""
        result = ProcessingResult()

        assert hasattr(result, "pm_review_splits")
        assert hasattr(result, "pm_review_kept")
        assert hasattr(result, "pm_review_skipped")
        assert result.pm_review_splits == 0
        assert result.pm_review_kept == 0
        assert result.pm_review_skipped == 0

    def test_processing_result_metrics_accumulate(
        self, mock_story_service, mock_orphan_service, mock_pm_review_service
    ):
        """Test that PM review metrics accumulate across groups."""
        # Create multiple theme groups
        theme_groups = {
            "sig_1": [
                {"id": "conv_1", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
                {"id": "conv_2", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
                {"id": "conv_3", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
            ],
            "sig_2": [
                {"id": "conv_4", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
                {"id": "conv_5", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
                {"id": "conv_6", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
            ],
        }

        # Configure mock PM review to return keep_together for both
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="test",
            conversation_count=3,
            decision=ReviewDecision.KEEP_TOGETHER,
            reasoning="All same",
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(theme_groups)

        assert result.pm_review_kept == 2  # Both groups kept
        assert result.stories_created == 2


# -----------------------------------------------------------------------------
# Test Integration with Quality Gates
# -----------------------------------------------------------------------------


class TestPMReviewWithQualityGates:
    """Test PM review integration with quality gates."""

    def test_pm_review_runs_after_quality_gates_pass(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
        sample_theme_groups,
    ):
        """Test that PM review only runs for groups that pass quality gates."""
        mock_pm_review_service.review_group.return_value = PMReviewResult(
            original_signature="pinterest_duplicate_pins",
            conversation_count=3,
            decision=ReviewDecision.KEEP_TOGETHER,
            reasoning="All same",
        )

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(sample_theme_groups)

        # PM review should be called (quality gates pass for valid groups)
        mock_pm_review_service.review_group.assert_called_once()

    def test_pm_review_not_called_for_small_groups(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_pm_review_service,
    ):
        """Test that PM review is not called for groups below MIN_GROUP_SIZE."""
        small_group = {
            "small_sig": [
                {"id": "conv_1", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
                {"id": "conv_2", "product_area": "a", "component": "b", "user_intent": "u", "symptoms": [], "affected_flow": "f", "excerpt": "e"},
            ],
        }

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_service=mock_pm_review_service,
            pm_review_enabled=True,
        )

        result = service.process_theme_groups(small_group)

        # PM review should not be called (group fails quality gate)
        mock_pm_review_service.review_group.assert_not_called()
        assert result.quality_gate_rejections == 1
