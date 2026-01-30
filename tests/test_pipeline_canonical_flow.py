"""
Pipeline-critical tests for canonical flow (Issue #89).

Tests the end-to-end pipeline flow:
1. Classification → Theme extraction → Story creation
2. StoryCreationService behavior (MIN_GROUP_SIZE, orphan path, quality gates)
3. Confidence scoring and evidence validation
4. Run scoping isolation (no cross-contamination)

Run with: pytest tests/test_pipeline_canonical_flow.py -v
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys

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
    QualityGateResult,
    DEFAULT_CONFIDENCE_THRESHOLD,
)
from evidence_validator import validate_samples, EvidenceQuality

# Mark entire module as slow - these are integration tests
pytestmark = [pytest.mark.slow, pytest.mark.integration]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_story_service():
    """Create a mock story service that tracks created stories."""
    service = Mock(spec=StoryService)
    created_stories = []

    def create_story(story_create):
        story = Story(
            id=uuid4(),
            title=story_create.title,
            description=story_create.description,
            labels=story_create.labels,
            priority=None,
            severity=None,
            product_area=story_create.product_area,
            technical_area=story_create.technical_area,
            status=story_create.status,
            confidence_score=story_create.confidence_score,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        created_stories.append(story)
        return story

    service.create.side_effect = create_story
    service.created_stories = created_stories
    return service


@pytest.fixture
def mock_orphan_service():
    """Create a mock orphan service that tracks created orphans."""
    service = Mock(spec=OrphanService)
    created_orphans = []

    def create_orphan(orphan_create):
        now = datetime.now(timezone.utc)
        orphan = Orphan(
            id=uuid4(),
            signature=orphan_create.signature,
            original_signature=orphan_create.original_signature,
            conversation_ids=orphan_create.conversation_ids,
            theme_data=orphan_create.theme_data,
            first_seen_at=now,
            last_updated_at=now,
        )
        created_orphans.append(orphan)
        return orphan

    service.create.side_effect = create_orphan
    service.get_by_signature.return_value = None  # No existing orphans by default
    service.created_orphans = created_orphans
    return service


@pytest.fixture
def sample_conversations() -> List[Dict[str, Any]]:
    """Generate sample conversations for theme groups."""
    return [
        {
            "id": f"conv_{i}",
            "product_area": "scheduler",
            "component": "queue",
            "user_intent": "Schedule posts to Instagram",
            "symptoms": ["posts not going live", "scheduled but stuck"],
            "affected_flow": "posting",
            "excerpt": f"I scheduled a post but it's stuck in queue. Sample {i}.",
        }
        for i in range(5)
    ]


@pytest.fixture
def small_group_conversations() -> List[Dict[str, Any]]:
    """Generate under-sized group (< MIN_GROUP_SIZE)."""
    return [
        {
            "id": f"small_conv_{i}",
            "product_area": "analytics",
            "component": "reports",
            "user_intent": "View analytics data",
            "symptoms": ["dashboard not loading"],
            "affected_flow": "analytics",
            "excerpt": f"My analytics dashboard is blank. Sample {i}.",
        }
        for i in range(MIN_GROUP_SIZE - 1)  # One less than minimum
    ]


# =============================================================================
# Test Class: Pipeline Flow Integration
# =============================================================================


class TestPipelineFlowIntegration:
    """
    Tests for the canonical pipeline flow: classification → theme → story.

    These tests validate that the StoryCreationService correctly:
    - Creates stories for groups >= MIN_GROUP_SIZE
    - Creates orphans for groups < MIN_GROUP_SIZE
    - Tracks processing metrics accurately
    """

    def test_theme_groups_create_stories_when_large_enough(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_conversations,
    ):
        """Groups with >= MIN_GROUP_SIZE conversations should become stories."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,  # Skip validation for unit test
        )

        theme_groups = {
            "scheduler_queue_stuck": sample_conversations[:MIN_GROUP_SIZE],
        }

        result = service.process_theme_groups(theme_groups)

        assert result.stories_created == 1
        assert result.orphans_created == 0
        assert len(result.created_story_ids) == 1
        assert result.errors == []

    def test_theme_groups_create_orphans_when_too_small(
        self,
        mock_story_service,
        mock_orphan_service,
        small_group_conversations,
    ):
        """Groups with < MIN_GROUP_SIZE conversations should become orphans."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        theme_groups = {
            "analytics_dashboard_blank": small_group_conversations,
        }

        result = service.process_theme_groups(theme_groups)

        assert result.stories_created == 0
        assert result.orphans_created == 1
        assert len(result.created_orphan_ids) == 1
        assert result.quality_gate_rejections == 1  # Failed due to size

    def test_mixed_groups_processed_correctly(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_conversations,
        small_group_conversations,
    ):
        """Mix of large and small groups should create stories and orphans."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        theme_groups = {
            "large_group": sample_conversations[:MIN_GROUP_SIZE],
            "small_group": small_group_conversations,
        }

        result = service.process_theme_groups(theme_groups)

        assert result.stories_created == 1
        assert result.orphans_created == 1
        assert result.quality_gate_rejections == 1

    def test_processing_result_metrics_accurate(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_conversations,
    ):
        """ProcessingResult should accurately track all metrics."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # Create multiple theme groups
        theme_groups = {
            "group_a": sample_conversations[:MIN_GROUP_SIZE],
            "group_b": sample_conversations[:MIN_GROUP_SIZE],
            "group_c": sample_conversations[:MIN_GROUP_SIZE - 1],  # Too small
        }

        result = service.process_theme_groups(theme_groups)

        assert result.stories_created == 2
        assert result.orphans_created == 1
        assert len(result.created_story_ids) == 2
        assert len(result.created_orphan_ids) == 1
        assert result.quality_gate_rejections == 1
        assert result.errors == []


# =============================================================================
# Test Class: StoryCreationService Unit Tests
# =============================================================================


class TestStoryCreationServiceBehavior:
    """
    Unit tests for StoryCreationService behavior:
    - MIN_GROUP_SIZE enforcement
    - Orphan integration path
    - Error handling
    """

    def test_min_group_size_boundary_story(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Exactly MIN_GROUP_SIZE conversations should create a story."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # Exactly at the boundary
        convs = [
            {
                "id": f"boundary_{i}",
                "product_area": "test",
                "component": "test",
                "user_intent": "Test intent",
                "symptoms": ["symptom"],
                "excerpt": f"Test excerpt {i}",
            }
            for i in range(MIN_GROUP_SIZE)
        ]

        result = service.process_theme_groups({"boundary_test": convs})

        assert result.stories_created == 1
        assert result.orphans_created == 0

    def test_min_group_size_boundary_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """MIN_GROUP_SIZE - 1 conversations should create an orphan."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # One below boundary
        convs = [
            {
                "id": f"under_{i}",
                "product_area": "test",
                "component": "test",
                "user_intent": "Test intent",
                "symptoms": ["symptom"],
                "excerpt": f"Test excerpt {i}",
            }
            for i in range(MIN_GROUP_SIZE - 1)
        ]

        result = service.process_theme_groups({"under_boundary": convs})

        assert result.stories_created == 0
        assert result.orphans_created == 1

    def test_empty_conversation_id_rejected(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Conversations with empty IDs should be rejected."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # Include a conversation with empty ID
        convs = [
            {"id": "", "excerpt": "Empty ID"},  # Should fail
            {"id": "valid_1", "excerpt": "Valid"},
            {"id": "valid_2", "excerpt": "Valid"},
        ]

        result = service.process_theme_groups({"bad_ids": convs})

        # Should have an error for the empty ID
        assert len(result.errors) > 0
        assert any("empty" in err.lower() or "id" in err.lower() for err in result.errors)
        # Verify no story was created with bad data
        assert mock_story_service.create.call_count == 0

    def test_orphan_integration_used_when_available(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """OrphanIntegrationService should be used when provided."""
        mock_integration = Mock()

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            orphan_integration_service=mock_integration,
            validation_enabled=False,
        )

        # Small group that will be routed to orphan integration
        convs = [{"id": f"int_{i}", "excerpt": f"Test {i}"} for i in range(2)]

        service.process_theme_groups({"small_group": convs})

        # OrphanIntegrationService.process_theme should have been called
        assert mock_integration.process_theme.call_count >= 1

    def test_orphan_fallback_on_integration_failure(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Should fall back to direct orphan creation if integration fails."""
        mock_integration = Mock()
        mock_integration.process_theme.side_effect = Exception("Integration error")

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            orphan_integration_service=mock_integration,
            validation_enabled=False,
        )

        convs = [{"id": f"fb_{i}", "excerpt": f"Test {i}"} for i in range(2)]

        result = service.process_theme_groups({"fallback_group": convs})

        # Should have used fallback (integration failed)
        assert result.orphan_fallbacks == 1
        # And created orphan via fallback mechanism
        assert result.orphans_created == 1 or result.orphans_updated == 1


# =============================================================================
# Test Class: Quality Gate Regression Tests
# =============================================================================


class TestQualityGateRegression:
    """
    Regression tests for quality gates:
    - Confidence scoring stored and within expected range
    - Evidence validation failure → deterministic outcome
    """

    def test_confidence_score_stored_on_story(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Stories should have confidence_score from quality gates."""
        # Mock confidence scorer
        mock_scorer = Mock()
        mock_scored_group = Mock()
        mock_scored_group.confidence_score = 75.0
        mock_scorer.score_groups.return_value = [mock_scored_group]

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        convs = [
            {"id": f"scored_{i}", "excerpt": f"Test {i}", "product_area": "test"}
            for i in range(MIN_GROUP_SIZE)
        ]

        service.process_theme_groups({"scored_group": convs})

        # Verify story was created with confidence score
        assert len(mock_story_service.created_stories) == 1
        created_story = mock_story_service.created_stories[0]
        assert created_story.confidence_score == 75.0

    def test_confidence_below_threshold_creates_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Groups below confidence threshold should become orphans."""
        mock_scorer = Mock()
        mock_scored_group = Mock()
        mock_scored_group.confidence_score = 30.0  # Below default 50 threshold
        mock_scorer.score_groups.return_value = [mock_scored_group]

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
            validation_enabled=False,
        )

        convs = [
            {"id": f"low_conf_{i}", "excerpt": f"Test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]

        result = service.process_theme_groups({"low_confidence": convs})

        assert result.stories_created == 0
        assert result.quality_gate_rejections == 1

    def test_evidence_validation_failure_routes_to_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Evidence validation failure should route to orphan integration."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=True,  # Enable validation
        )

        # Conversations missing required 'id' or 'excerpt' fields
        convs = [
            {"id": f"bad_ev_{i}"}  # Missing excerpt - validation should fail
            for i in range(MIN_GROUP_SIZE)
        ]

        result = service.process_theme_groups({"bad_evidence": convs})

        # Should be rejected by quality gates and NOT create a story
        assert result.quality_gate_rejections == 1
        assert result.stories_created == 0
        # Orphan should be created via fallback/integration
        assert result.orphans_created == 1 or mock_orphan_service.create.called

    def test_quality_gate_result_captures_failure_reason(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """QualityGateResult should capture specific failure reason."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # Test the internal _apply_quality_gates method
        convs_data = [
            ConversationData(
                id=f"gate_{i}",
                issue_signature="test_sig",
                excerpt=f"Test {i}",
            )
            for i in range(MIN_GROUP_SIZE - 1)  # Under minimum
        ]

        conv_dicts = [{"id": c.id, "excerpt": c.excerpt} for c in convs_data]

        result = service._apply_quality_gates("test_sig", convs_data, conv_dicts)

        assert result.passed is False
        assert "minimum" in result.failure_reason.lower()


# =============================================================================
# Test Class: Evidence Validator Tests
# =============================================================================


class TestEvidenceValidator:
    """Tests for the evidence_validator module."""

    def test_valid_samples_pass(self):
        """Samples with required fields should pass validation."""
        samples = [
            {"id": "123", "excerpt": "A meaningful excerpt about the issue"},
            {"id": "124", "excerpt": "Another meaningful excerpt here"},
        ]

        quality = validate_samples(samples)

        assert quality.is_valid is True
        assert quality.sample_count == 2
        assert len(quality.errors) == 0

    def test_missing_id_fails(self):
        """Samples missing 'id' field should fail validation."""
        samples = [
            {"excerpt": "Has excerpt but no id"},
        ]

        quality = validate_samples(samples)

        assert quality.is_valid is False
        assert any("id" in err.lower() for err in quality.errors)

    def test_missing_excerpt_fails(self):
        """Samples missing 'excerpt' field should fail validation."""
        samples = [
            {"id": "123"},
        ]

        quality = validate_samples(samples)

        assert quality.is_valid is False
        assert any("excerpt" in err.lower() for err in quality.errors)

    def test_placeholder_excerpt_fails(self):
        """Placeholder excerpts should be detected and rejected."""
        samples = [
            {"id": "123", "excerpt": "Not captured during batch processing - search Intercom for more"},
        ]

        quality = validate_samples(samples)

        assert quality.is_valid is False
        assert any("placeholder" in err.lower() for err in quality.errors)

    def test_empty_samples_fails(self):
        """Empty sample list should fail validation."""
        quality = validate_samples([])

        assert quality.is_valid is False
        assert quality.sample_count == 0

    def test_coverage_calculated_correctly(self):
        """Field coverage should be calculated as percentage."""
        samples = [
            {"id": "1", "excerpt": "Test", "email": "a@test.com"},
            {"id": "2", "excerpt": "Test"},  # No email
        ]

        quality = validate_samples(samples)

        assert quality.coverage["id"] == 100.0
        assert quality.coverage["excerpt"] == 100.0
        assert quality.coverage["email"] == 50.0


# =============================================================================
# Test Class: Run Scoping Isolation Tests
# =============================================================================


class TestRunScopingIsolation:
    """
    Tests for run scoping isolation.

    Verifies that overlapping pipeline runs don't contaminate each other.
    These tests extend test_run_scoping.py with story-level isolation tests.
    """

    def test_stories_linked_to_pipeline_run_id(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Stories should be linkable to their pipeline_run_id."""
        # Mock DB connection with proper context manager pattern
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__.return_value = mock_cursor
        mock_cursor_ctx.__exit__.return_value = False
        mock_db.cursor.return_value = mock_cursor_ctx
        mock_story_service.db = mock_db

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        convs = [
            {"id": f"run_link_{i}", "excerpt": f"Test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]

        pipeline_run_id = 42

        result = service.process_theme_groups(
            {"run_linked": convs},
            pipeline_run_id=pipeline_run_id,
        )

        # Story should be created
        assert result.stories_created == 1

        # Link query should have been executed
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0]
        assert "UPDATE stories SET pipeline_run_id" in call_args[0]
        assert pipeline_run_id in call_args[1]

    def test_processing_result_tracks_story_ids(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """ProcessingResult.created_story_ids should track all created stories."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        convs = [
            {"id": f"track_{i}", "excerpt": f"Test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]

        result = service.process_theme_groups({"tracked": convs})

        assert len(result.created_story_ids) == 1
        assert result.created_story_ids[0] == mock_story_service.created_stories[0].id

    def test_separate_runs_create_separate_stories(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Different pipeline runs should create separate stories."""
        # Mock the DB with proper context manager pattern
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__.return_value = mock_cursor
        mock_cursor_ctx.__exit__.return_value = False
        mock_db.cursor.return_value = mock_cursor_ctx
        mock_story_service.db = mock_db

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # Run 1
        convs_1 = [
            {"id": f"run1_{i}", "excerpt": f"Run 1 test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]
        result_1 = service.process_theme_groups(
            {"run1_group": convs_1},
            pipeline_run_id=100,
        )

        # Run 2 (same signature but different run)
        convs_2 = [
            {"id": f"run2_{i}", "excerpt": f"Run 2 test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]
        result_2 = service.process_theme_groups(
            {"run2_group": convs_2},
            pipeline_run_id=200,
        )

        # Each run should create its own story
        assert result_1.stories_created == 1
        assert result_2.stories_created == 1
        assert len(mock_story_service.created_stories) == 2

        # Story IDs should be different
        assert result_1.created_story_ids[0] != result_2.created_story_ids[0]


# =============================================================================
# Test Class: PM Review Integration
# =============================================================================


class TestPMReviewMetrics:
    """Tests for PM review metrics in ProcessingResult."""

    def test_pm_review_skipped_when_disabled(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """PM review should be skipped when disabled."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            pm_review_enabled=False,
            validation_enabled=False,
        )

        convs = [
            {"id": f"pm_skip_{i}", "excerpt": f"Test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]

        result = service.process_theme_groups({"pm_test": convs})

        # Should be marked as skipped, not kept/split/rejected
        assert result.pm_review_skipped == 1
        assert result.pm_review_kept == 0
        assert result.pm_review_splits == 0
        assert result.pm_review_rejects == 0

    def test_pm_review_metrics_initialized(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """ProcessingResult should have all PM review metrics initialized."""
        result = ProcessingResult()

        assert hasattr(result, "pm_review_splits")
        assert hasattr(result, "pm_review_rejects")
        assert hasattr(result, "pm_review_kept")
        assert hasattr(result, "pm_review_skipped")
        assert result.pm_review_splits == 0
        assert result.pm_review_rejects == 0
        assert result.pm_review_kept == 0
        assert result.pm_review_skipped == 0


# =============================================================================
# Test Class: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in the pipeline flow."""

    def test_exception_in_one_group_doesnt_stop_others(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Exception processing one group should not stop processing others."""
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        # First group will fail due to exception
        # Mock _dict_to_conversation_data to throw for first group
        original_method = service._dict_to_conversation_data

        def failing_converter(conv_dict, signature):
            if signature == "failing_group":
                raise ValueError("Simulated failure")
            return original_method(conv_dict, signature)

        service._dict_to_conversation_data = failing_converter

        theme_groups = {
            "failing_group": [{"id": "fail_1", "excerpt": "Test"}] * MIN_GROUP_SIZE,
            "working_group": [
                {"id": f"work_{i}", "excerpt": f"Test {i}"}
                for i in range(MIN_GROUP_SIZE)
            ],
        }

        result = service.process_theme_groups(theme_groups)

        # Should have error for failing group
        assert len(result.errors) >= 1
        assert any("failing_group" in err for err in result.errors)

        # But working group should still be processed
        assert result.stories_created == 1

    def test_story_service_exception_captured(
        self,
        mock_orphan_service,
    ):
        """Exception from story_service.create should be captured in errors."""
        mock_story_service = Mock(spec=StoryService)
        mock_story_service.create.side_effect = Exception("DB connection failed")

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            validation_enabled=False,
        )

        convs = [
            {"id": f"db_fail_{i}", "excerpt": f"Test {i}"}
            for i in range(MIN_GROUP_SIZE)
        ]

        result = service.process_theme_groups({"db_test": convs})

        assert len(result.errors) >= 1


# =============================================================================
# Test Class: Constants and Configuration
# =============================================================================


class TestConstants:
    """Tests for pipeline constants and configuration."""

    def test_min_group_size_is_3(self):
        """MIN_GROUP_SIZE should be 3 per architecture doc."""
        assert MIN_GROUP_SIZE == 3

    def test_default_confidence_threshold_is_50(self):
        """Default confidence threshold should be 50.0."""
        assert DEFAULT_CONFIDENCE_THRESHOLD == 50.0

    def test_processing_result_has_quality_gate_metrics(self):
        """ProcessingResult should track quality gate rejections."""
        result = ProcessingResult()
        assert hasattr(result, "quality_gate_rejections")
        assert hasattr(result, "orphan_fallbacks")
        assert result.quality_gate_rejections == 0
        assert result.orphan_fallbacks == 0
