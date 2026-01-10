"""
Story Creation Service Tests

Tests for StoryCreationService - PM Review → Stories/Orphans.
Run with: pytest tests/test_story_creation_service.py -v
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
    PMReviewResult,
    ProcessingResult,
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
        product_area="billing",
        technical_area="subscription",
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
    service.get_by_signature.return_value = None  # No existing orphan by default
    service.create.return_value = Orphan(
        id=uuid4(),
        signature="test_signature",
        original_signature=None,
        conversation_ids=["conv1"],
        theme_data={},
        confidence_score=None,
        first_seen_at=datetime.now(),
        last_updated_at=datetime.now(),
        graduated_at=None,
        story_id=None,
    )
    return service


@pytest.fixture
def sample_pm_results_keep():
    """Sample PM review results with keep_together decision."""
    return [
        {
            "signature": "billing_cancellation_request",
            "decision": "keep_together",
            "reasoning": "All conversations about billing cancellation",
            "sub_groups": [],
            "conversation_count": 5,
        }
    ]


@pytest.fixture
def sample_pm_results_split():
    """Sample PM review results with split decision."""
    return [
        {
            "signature": "general_product_question",
            "decision": "split",
            "reasoning": "Different types of questions",
            "sub_groups": [
                {
                    "suggested_signature": "promotions",
                    "conversation_ids": [0],
                    "rationale": "Promotional queries",
                },
                {
                    "suggested_signature": "customer_service",
                    "conversation_ids": [1, 2, 3],  # MIN_GROUP_SIZE
                    "rationale": "Customer service responses",
                },
            ],
            "conversation_count": 4,
        }
    ]


@pytest.fixture
def sample_extraction_data():
    """Sample theme extraction JSONL data."""
    return [
        {
            "id": "conv1",
            "issue_signature": "billing_cancellation_request",
            "product_area": "billing",
            "component": "subscription",
            "user_intent": "Cancel subscription",
            "symptoms": ["wants to cancel", "billing issue"],
            "affected_flow": "Billing → Cancellation",
            "root_cause_hypothesis": "User wants to cancel",
            "excerpt": "I want to cancel my subscription",
        },
        {
            "id": "conv2",
            "issue_signature": "billing_cancellation_request",
            "product_area": "billing",
            "component": "subscription",
            "user_intent": "Cancel account",
            "symptoms": ["account cancellation"],
            "affected_flow": "Billing → Cancellation",
            "root_cause_hypothesis": None,
            "excerpt": "Please cancel my account",
        },
        {
            "id": "conv3",
            "issue_signature": "billing_cancellation_request",
            "product_area": "billing",
            "component": "subscription",
            "user_intent": "Stop billing",
            "symptoms": ["stop charging"],
            "affected_flow": "Billing → Cancellation",
            "root_cause_hypothesis": None,
            "excerpt": "Stop charging my card",
        },
    ]


@pytest.fixture
def sample_extraction_data_for_split():
    """Sample extraction data matching the split PM results."""
    return [
        {
            "id": "conv0",
            "issue_signature": "general_product_question",
            "product_area": "marketing",
            "component": "promotions",
            "user_intent": "Ask about discount",
            "symptoms": ["discount inquiry"],
            "affected_flow": None,
            "excerpt": "Do you have any discounts?",
        },
        {
            "id": "conv1",
            "issue_signature": "general_product_question",
            "product_area": "support",
            "component": "customer_service",
            "user_intent": "Get help",
            "symptoms": ["needs assistance"],
            "affected_flow": "Support → Help",
            "excerpt": "I need help with my account",
        },
        {
            "id": "conv2",
            "issue_signature": "general_product_question",
            "product_area": "support",
            "component": "customer_service",
            "user_intent": "Contact support",
            "symptoms": ["support request"],
            "affected_flow": "Support → Help",
            "excerpt": "How do I contact support?",
        },
        {
            "id": "conv3",
            "issue_signature": "general_product_question",
            "product_area": "support",
            "component": "customer_service",
            "user_intent": "Follow up",
            "symptoms": ["follow up"],
            "affected_flow": "Support → Help",
            "excerpt": "Following up on my request",
        },
    ]


# -----------------------------------------------------------------------------
# StoryCreationService Tests
# -----------------------------------------------------------------------------


class TestStoryCreationService:
    """Tests for StoryCreationService."""

    def test_process_keep_together_creates_story(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_pm_results_keep,
        sample_extraction_data,
    ):
        """Test that keep_together decision creates a story."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write PM results
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(sample_pm_results_keep, f)

            # Write extraction data
            extraction_path = Path(tmpdir) / "extraction.jsonl"
            with open(extraction_path, "w") as f:
                for item in sample_extraction_data:
                    f.write(json.dumps(item) + "\n")

            service = StoryCreationService(mock_story_service, mock_orphan_service)
            result = service.process_pm_review_results(pm_path, extraction_path)

            assert result.stories_created == 1
            assert result.orphans_created == 0
            mock_story_service.create.assert_called_once()

    def test_process_split_creates_story_and_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_pm_results_split,
        sample_extraction_data_for_split,
    ):
        """Test that split decision creates stories for large groups, orphans for small."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(sample_pm_results_split, f)

            extraction_path = Path(tmpdir) / "extraction.jsonl"
            with open(extraction_path, "w") as f:
                for item in sample_extraction_data_for_split:
                    f.write(json.dumps(item) + "\n")

            service = StoryCreationService(mock_story_service, mock_orphan_service)
            result = service.process_pm_review_results(pm_path, extraction_path)

            # customer_service has 3 convos → story
            # promotions has 1 convo → orphan
            assert result.stories_created == 1
            assert result.orphans_created == 1

    def test_process_updates_existing_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_pm_results_split,
        sample_extraction_data_for_split,
    ):
        """Test that existing orphan gets updated instead of creating new."""
        # Set up existing orphan
        existing_orphan = Orphan(
            id=uuid4(),
            signature="promotions",
            original_signature=None,
            conversation_ids=["old_conv"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )
        mock_orphan_service.get_by_signature.side_effect = lambda sig: (
            existing_orphan if sig == "promotions" else None
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(sample_pm_results_split, f)

            extraction_path = Path(tmpdir) / "extraction.jsonl"
            with open(extraction_path, "w") as f:
                for item in sample_extraction_data_for_split:
                    f.write(json.dumps(item) + "\n")

            service = StoryCreationService(mock_story_service, mock_orphan_service)
            result = service.process_pm_review_results(pm_path, extraction_path)

            # Should update existing orphan, not create new
            assert result.orphans_updated == 1
            assert result.orphans_created == 0
            mock_orphan_service.add_conversations.assert_called_once()

    def test_process_handles_error_decision(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that error decisions are recorded in errors."""
        pm_results = [
            {
                "signature": "failed_review",
                "decision": "error",
                "reasoning": "API call failed",
                "sub_groups": [],
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(pm_results, f)

            service = StoryCreationService(mock_story_service, mock_orphan_service)
            result = service.process_pm_review_results(pm_path)

            assert len(result.errors) == 1
            assert "failed_review" in result.errors[0]

    def test_process_handles_missing_file(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test graceful handling of missing PM results file."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)
        result = service.process_pm_review_results(Path("/nonexistent/path.json"))

        assert len(result.errors) == 1
        assert "Failed to load" in result.errors[0]

    def test_keep_together_with_insufficient_convos_creates_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that keep_together with <MIN_GROUP_SIZE creates orphan."""
        pm_results = [
            {
                "signature": "small_group",
                "decision": "keep_together",
                "reasoning": "Keep together",
                "sub_groups": [],
                "conversation_count": 2,  # Less than MIN_GROUP_SIZE
            }
        ]

        # Extraction data with only 2 conversations
        extraction_data = [
            {
                "id": "conv1",
                "issue_signature": "small_group",
                "product_area": "test",
                "user_intent": "Test 1",
                "symptoms": [],
            },
            {
                "id": "conv2",
                "issue_signature": "small_group",
                "product_area": "test",
                "user_intent": "Test 2",
                "symptoms": [],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(pm_results, f)

            extraction_path = Path(tmpdir) / "extraction.jsonl"
            with open(extraction_path, "w") as f:
                for item in extraction_data:
                    f.write(json.dumps(item) + "\n")

            service = StoryCreationService(mock_story_service, mock_orphan_service)
            result = service.process_pm_review_results(pm_path, extraction_path)

            # Should create orphan, not story
            assert result.stories_created == 0
            assert result.orphans_created == 1


class TestThemeDataBuilding:
    """Tests for theme data building from conversations."""

    def test_build_theme_data_aggregates_symptoms(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that symptoms are aggregated from all conversations."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        conversations = [
            ConversationData(
                id="1",
                issue_signature="test",
                symptoms=["symptom1", "symptom2"],
            ),
            ConversationData(
                id="2",
                issue_signature="test",
                symptoms=["symptom2", "symptom3"],
            ),
        ]

        theme_data = service._build_theme_data(conversations)

        assert "symptom1" in theme_data["symptoms"]
        assert "symptom2" in theme_data["symptoms"]
        assert "symptom3" in theme_data["symptoms"]

    def test_build_theme_data_collects_excerpts(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that excerpts are collected with conversation IDs."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        conversations = [
            ConversationData(
                id="conv1",
                issue_signature="test",
                excerpt="First excerpt",
            ),
            ConversationData(
                id="conv2",
                issue_signature="test",
                excerpt="Second excerpt",
            ),
        ]

        theme_data = service._build_theme_data(conversations)

        assert len(theme_data["excerpts"]) == 2
        assert theme_data["excerpts"][0]["conversation_id"] == "conv1"

    def test_build_theme_data_empty_list(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that empty conversation list returns empty dict."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)
        theme_data = service._build_theme_data([])
        assert theme_data == {}


class TestTitleGeneration:
    """Tests for story title generation."""

    def test_generate_title_uses_user_intent(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that user_intent is used for title when available."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        theme_data = {"user_intent": "User wants to schedule pins"}
        title = service._generate_title("pin_scheduling", theme_data)

        assert title == "User wants to schedule pins"

    def test_generate_title_falls_back_to_signature(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test fallback to formatted signature when no user_intent."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        title = service._generate_title("pin_scheduling_fails", {})

        assert title == "Pin Scheduling Fails"

    def test_generate_title_truncates_long_intent(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that long user_intent is truncated."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        long_intent = "A" * 300
        theme_data = {"user_intent": long_intent}
        title = service._generate_title("test", theme_data)

        assert len(title) <= 200


class TestDescriptionGeneration:
    """Tests for story description generation."""

    def test_generate_description_includes_all_fields(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that description includes all available theme data."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        theme_data = {
            "user_intent": "Schedule pins",
            "symptoms": ["pins fail", "error message"],
            "product_area": "Scheduler",
            "component": "Pin Queue",
            "affected_flow": "Scheduling → Publishing",
            "root_cause_hypothesis": "Queue overflow",
        }

        description = service._generate_description(
            "pin_scheduling",
            theme_data,
            "PM reasoning here",
        )

        assert "Schedule pins" in description
        assert "pins fail" in description
        assert "Scheduler" in description
        assert "Pin Queue" in description
        assert "PM reasoning here" in description
        assert "`pin_scheduling`" in description

    def test_generate_description_includes_original_signature(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that split origin is included in description."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        description = service._generate_description(
            "specific_signature",
            {},
            "Split reasoning",
            original_signature="general_signature",
        )

        assert "`general_signature`" in description


class TestPMResultModels:
    """Tests for PM result data models."""

    def test_pm_review_result_dataclass(self):
        """Test PMReviewResult dataclass."""
        result = PMReviewResult(
            signature="test",
            decision="keep_together",
            reasoning="Test reasoning",
        )
        assert result.signature == "test"
        assert result.sub_groups == []

    def test_conversation_data_dataclass(self):
        """Test ConversationData dataclass."""
        conv = ConversationData(
            id="123",
            issue_signature="test_sig",
            user_intent="Test intent",
        )
        assert conv.id == "123"
        assert conv.symptoms == []

    def test_processing_result_dataclass(self):
        """Test ProcessingResult dataclass."""
        result = ProcessingResult()
        assert result.stories_created == 0
        assert result.orphans_created == 0
        assert result.errors == []
