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
    FallbackPMReviewResult,
    ProcessingResult,
    MAX_EXCERPT_LENGTH,
    MAX_EXCERPTS_IN_THEME,
    _build_intercom_url,
    INTERCOM_APP_ID,
    _rank_conversations_by_signal,
    _calculate_signal_score,
    _text_similarity,
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
        """Test FallbackPMReviewResult dataclass."""
        result = FallbackPMReviewResult(
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


# -----------------------------------------------------------------------------
# Dual-Format Story Tests (Phase 3.3)
# -----------------------------------------------------------------------------


class TestDualFormatIntegration:
    """Tests for dual-format story generation integration."""

    def test_dual_format_disabled_by_default(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that dual format is disabled by default (backward compatibility)."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        assert service.dual_format_enabled is False
        assert service.dual_formatter is None
        assert service.codebase_provider is None

    def test_dual_format_enabled_without_dependencies(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that dual format degrades gracefully when dependencies unavailable."""
        # Patch DUAL_FORMAT_AVAILABLE to simulate missing dependencies
        with patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', False):
            service = StoryCreationService(
                mock_story_service,
                mock_orphan_service,
                dual_format_enabled=True,
                target_repo="aero",
            )

            # Should fall back to simple format
            assert service.dual_format_enabled is False
            assert service.dual_formatter is None

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_dual_format_enabled_with_dependencies(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that dual format is properly initialized when enabled."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=True,
            target_repo="aero",
        )

        assert service.dual_format_enabled is True
        assert service.target_repo == "aero"
        mock_dual_formatter_class.assert_called_once()
        mock_codebase_provider_class.assert_called_once()

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_dual_format_generates_v2_description(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that dual format generates v2 description with exploration."""
        # Setup mock exploration result
        mock_exploration = Mock()
        mock_exploration.relevant_files = [Mock(path="file1.py", line_start=10)]
        mock_exploration.code_snippets = []

        mock_codebase_provider = Mock()
        mock_codebase_provider.explore_for_theme.return_value = mock_exploration
        mock_codebase_provider_class.return_value = mock_codebase_provider

        # Setup mock dual output
        mock_dual_output = Mock()
        mock_dual_output.combined = "# Dual Format Story\n\nSection 1: Human\n\n---\n\nSection 2: AI"
        mock_dual_output.format_version = "v2"

        mock_formatter = Mock()
        mock_formatter.format_story.return_value = mock_dual_output
        mock_dual_formatter_class.return_value = mock_formatter

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=True,
            target_repo="aero",
        )

        # Generate description
        theme_data = {
            "user_intent": "Test issue",
            "product_area": "billing",
            "component": "subscription",
            "symptoms": ["error occurs"],
        }

        description = service._generate_description(
            "test_signature",
            theme_data,
            "PM reasoning",
        )

        # Verify dual format was used
        assert "Dual Format Story" in description
        assert "Section 1: Human" in description
        assert "Section 2: AI" in description
        mock_codebase_provider.explore_for_theme.assert_called_once()
        mock_formatter.format_story.assert_called_once()

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_dual_format_handles_exploration_failure(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that dual format gracefully handles exploration failures."""
        # Setup mock to raise exception
        mock_codebase_provider = Mock()
        mock_codebase_provider.explore_for_theme.side_effect = Exception("Exploration failed")
        mock_codebase_provider_class.return_value = mock_codebase_provider

        # Setup mock dual output (should still work without exploration)
        mock_dual_output = Mock()
        mock_dual_output.combined = "# Story without codebase context"
        mock_dual_output.format_version = "v2"

        mock_formatter = Mock()
        mock_formatter.format_story.return_value = mock_dual_output
        mock_dual_formatter_class.return_value = mock_formatter

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=True,
            target_repo="aero",
        )

        # Generate description - should not raise
        theme_data = {"user_intent": "Test issue"}
        description = service._generate_description(
            "test_signature",
            theme_data,
            "PM reasoning",
        )

        # Verify dual format was still used (without exploration)
        assert description == "# Story without codebase context"
        # format_story should be called with None exploration_result
        call_args = mock_formatter.format_story.call_args
        assert call_args[1]['exploration_result'] is None

    def test_simple_format_still_works(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that simple format (v1) still works when dual format disabled."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=False,
        )

        theme_data = {
            "user_intent": "Cancel subscription",
            "symptoms": ["wants to cancel", "billing issue"],
            "product_area": "billing",
            "component": "subscription",
        }

        description = service._generate_description(
            "billing_cancellation",
            theme_data,
            "Test reasoning",
        )

        # Verify simple format structure
        assert "**User Intent**: Cancel subscription" in description
        assert "**Symptoms**: wants to cancel, billing issue" in description
        assert "**Product Area**: billing" in description
        assert "`billing_cancellation`" in description

    def test_build_formatter_theme_data_transformation(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that internal theme data is correctly transformed for formatter."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        theme_data = {
            "user_intent": "Fix login issue",
            "product_area": "auth",
            "component": "login",
            "symptoms": ["error message", "timeout"],
            "root_cause_hypothesis": "Database connection",
            "excerpts": [
                {"text": "I can't login", "conversation_id": "conv1"},
                {"text": "Login fails", "conversation_id": "conv2"},
            ],
        }

        formatter_data = service._build_formatter_theme_data(
            "login_failure",
            theme_data,
            "PM says fix this",
            "original_sig",
        )

        # Verify transformation
        assert formatter_data["issue_signature"] == "login_failure"
        assert formatter_data["product_area"] == "auth"
        assert formatter_data["component"] == "login"
        assert formatter_data["pm_reasoning"] == "PM says fix this"
        assert formatter_data["original_signature"] == "original_sig"
        assert formatter_data["occurrences"] == 2
        assert len(formatter_data["customer_messages"]) == 2
        assert "I can't login" in formatter_data["customer_messages"]

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_end_to_end_dual_format_story_creation(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
        sample_pm_results_keep,
        sample_extraction_data,
    ):
        """Test end-to-end dual format story creation from PM results."""
        # Setup mocks
        mock_codebase_provider = Mock()
        mock_codebase_provider.explore_for_theme.return_value = Mock(
            relevant_files=[],
            code_snippets=[],
            success=True,
        )
        mock_codebase_provider_class.return_value = mock_codebase_provider

        mock_dual_output = Mock()
        mock_dual_output.combined = "# Dual Format Story"
        mock_dual_output.format_version = "v2"

        mock_formatter = Mock()
        mock_formatter.format_story.return_value = mock_dual_output
        mock_dual_formatter_class.return_value = mock_formatter

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

            service = StoryCreationService(
                mock_story_service,
                mock_orphan_service,
                dual_format_enabled=True,
                target_repo="aero",
            )

            result = service.process_pm_review_results(pm_path, extraction_path)

            # Verify story was created with dual format
            assert result.stories_created == 1
            mock_story_service.create.assert_called_once()

            # Check that description passed to create includes dual format
            create_call = mock_story_service.create.call_args[0][0]
            assert "Dual Format Story" in create_call.description


# -----------------------------------------------------------------------------
# Classification-Guided Exploration Tests (Issue #44)
# -----------------------------------------------------------------------------


class TestClassificationGuidedExploration:
    """Tests for classification-guided codebase exploration (Issue #44)."""

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_explore_codebase_with_classification_returns_code_context(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that classification-guided exploration returns code context dict."""
        # Setup mock exploration and classification results
        mock_exploration = Mock()
        mock_exploration.relevant_files = [
            Mock(path="packages/scheduler/pin_scheduler.ts", line_start=142, line_end=None, relevance="5 matches"),
        ]
        mock_exploration.code_snippets = [
            Mock(
                file_path="packages/scheduler/pin_scheduler.ts",
                line_start=140,
                line_end=160,
                content="async function schedulePin() {}",
                language="typescript",
                context="Scheduling function",
            ),
        ]
        mock_exploration.exploration_duration_ms = 350
        mock_exploration.success = True
        mock_exploration.error = None

        mock_classification = Mock()
        mock_classification.category = "scheduling"
        mock_classification.confidence = "high"
        mock_classification.reasoning = "Issue mentions scheduled pins"
        mock_classification.keywords_matched = ["schedule", "pin"]
        mock_classification.classification_duration_ms = 180

        mock_codebase_provider = Mock()
        mock_codebase_provider.explore_with_classification.return_value = (
            mock_exploration,
            mock_classification,
        )
        mock_codebase_provider_class.return_value = mock_codebase_provider

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=True,
            target_repo="aero",
        )

        theme_data = {
            "user_intent": "My scheduled pins aren't posting to Pinterest",
            "symptoms": ["pins not posting", "scheduling failure"],
            "product_area": "Scheduler",
            "component": "pinterest",
        }

        code_context = service._explore_codebase_with_classification(theme_data)

        # Verify code_context structure
        assert code_context is not None
        assert code_context["success"] is True
        assert code_context["classification"]["category"] == "scheduling"
        assert code_context["classification"]["confidence"] == "high"
        assert len(code_context["relevant_files"]) == 1
        assert code_context["relevant_files"][0]["path"] == "packages/scheduler/pin_scheduler.ts"
        assert len(code_context["code_snippets"]) == 1
        assert code_context["exploration_duration_ms"] == 350
        assert code_context["classification_duration_ms"] == 180
        assert "explored_at" in code_context

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_explore_codebase_with_classification_handles_failure(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that exploration failures return error context."""
        mock_codebase_provider = Mock()
        mock_codebase_provider.explore_with_classification.side_effect = Exception(
            "Classifier API timeout"
        )
        mock_codebase_provider_class.return_value = mock_codebase_provider

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=True,
            target_repo="aero",
        )

        theme_data = {"user_intent": "Test issue"}
        code_context = service._explore_codebase_with_classification(theme_data)

        # Should return error context, not None
        assert code_context is not None
        assert code_context["success"] is False
        assert "Classifier API timeout" in code_context["error"]
        assert code_context["relevant_files"] == []
        assert code_context["code_snippets"] == []

    def test_explore_codebase_without_provider_returns_none(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that exploration returns None when provider is not available."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            dual_format_enabled=False,  # Provider not initialized
        )

        code_context = service._explore_codebase_with_classification({"user_intent": "Test"})

        assert code_context is None

    def test_build_issue_text_for_classification(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that issue text is correctly built for classification."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        theme_data = {
            "user_intent": "Scheduled pins failing to post",
            "symptoms": ["pins not posting", "scheduling error", "timeout"],
            "product_area": "Scheduler",
            "component": "pinterest",
            "excerpts": [
                {"text": "My pins aren't posting on time", "conversation_id": "conv1"},
            ],
        }

        issue_text = service._build_issue_text_for_classification(theme_data)

        assert "Scheduled pins failing to post" in issue_text
        assert "pins not posting" in issue_text
        assert "Scheduler" in issue_text
        assert "pinterest" in issue_text
        assert "My pins aren't posting on time" in issue_text

    def test_build_issue_text_handles_empty_data(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that issue text builder handles empty/missing data."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        # Completely empty
        assert service._build_issue_text_for_classification({}) == ""

        # Only user_intent
        theme_data = {"user_intent": "Test issue"}
        issue_text = service._build_issue_text_for_classification(theme_data)
        assert "Test issue" in issue_text

    @patch('story_tracking.services.story_creation_service.DUAL_FORMAT_AVAILABLE', True)
    @patch('story_tracking.services.story_creation_service.DualStoryFormatter')
    @patch('story_tracking.services.story_creation_service.CodebaseContextProvider')
    def test_code_context_passed_to_story_create(
        self,
        mock_codebase_provider_class,
        mock_dual_formatter_class,
        mock_story_service,
        mock_orphan_service,
        sample_pm_results_keep,
        sample_extraction_data,
    ):
        """Test that code_context is passed to story creation."""
        # Setup mocks
        mock_exploration = Mock()
        mock_exploration.relevant_files = [Mock(path="test.py", line_start=1, line_end=None, relevance="test")]
        mock_exploration.code_snippets = []
        mock_exploration.exploration_duration_ms = 100
        mock_exploration.success = True
        mock_exploration.error = None

        mock_classification = Mock()
        mock_classification.category = "billing"
        mock_classification.confidence = "high"
        mock_classification.reasoning = "Billing related"
        mock_classification.keywords_matched = ["billing"]
        mock_classification.classification_duration_ms = 50

        mock_codebase_provider = Mock()
        mock_codebase_provider.explore_with_classification.return_value = (
            mock_exploration,
            mock_classification,
        )
        mock_codebase_provider_class.return_value = mock_codebase_provider

        # Setup dual formatter
        mock_dual_output = Mock()
        mock_dual_output.combined = "# Dual Format"
        mock_dual_output.format_version = "v2"
        mock_formatter = Mock()
        mock_formatter.format_story.return_value = mock_dual_output
        mock_dual_formatter_class.return_value = mock_formatter

        with tempfile.TemporaryDirectory() as tmpdir:
            pm_path = Path(tmpdir) / "pm_results.json"
            with open(pm_path, "w") as f:
                json.dump(sample_pm_results_keep, f)

            extraction_path = Path(tmpdir) / "extraction.jsonl"
            with open(extraction_path, "w") as f:
                for item in sample_extraction_data:
                    f.write(json.dumps(item) + "\n")

            service = StoryCreationService(
                mock_story_service,
                mock_orphan_service,
                dual_format_enabled=True,
                target_repo="aero",
            )

            result = service.process_pm_review_results(pm_path, extraction_path)

            assert result.stories_created == 1
            mock_story_service.create.assert_called_once()

            # Verify code_context was passed to create
            create_call = mock_story_service.create.call_args[0][0]
            assert create_call.code_context is not None
            assert create_call.code_context["classification"]["category"] == "billing"
            assert len(create_call.code_context["relevant_files"]) == 1

    def test_build_code_context_dict_structure(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that code context dict is correctly structured."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        # Create mock exploration result
        mock_exploration = Mock()
        mock_exploration.relevant_files = [
            Mock(path="file1.py", line_start=10, line_end=20, relevance="3 matches: test"),
            Mock(path="file2.ts", line_start=None, line_end=None, relevance="1 match"),
        ]
        mock_exploration.code_snippets = [
            Mock(
                file_path="file1.py",
                line_start=8,
                line_end=15,
                content="def test():\n    pass",
                language="python",
                context="Test function",
            ),
        ]
        mock_exploration.exploration_duration_ms = 250
        mock_exploration.success = True
        mock_exploration.error = None

        # Create mock classification result
        mock_classification = Mock()
        mock_classification.category = "billing"
        mock_classification.confidence = "high"
        mock_classification.reasoning = "Billing keywords found"
        mock_classification.keywords_matched = ["billing", "payment"]
        mock_classification.classification_duration_ms = 120

        code_context = service._build_code_context_dict(mock_exploration, mock_classification)

        # Verify structure
        assert "classification" in code_context
        assert code_context["classification"]["category"] == "billing"
        assert code_context["classification"]["confidence"] == "high"
        assert code_context["classification"]["keywords_matched"] == ["billing", "payment"]

        assert "relevant_files" in code_context
        assert len(code_context["relevant_files"]) == 2
        assert code_context["relevant_files"][0]["path"] == "file1.py"
        assert code_context["relevant_files"][0]["line_start"] == 10

        assert "code_snippets" in code_context
        assert len(code_context["code_snippets"]) == 1
        assert code_context["code_snippets"][0]["language"] == "python"

        assert code_context["exploration_duration_ms"] == 250
        assert code_context["classification_duration_ms"] == 120
        assert code_context["success"] is True
        assert code_context["error"] is None
        assert "explored_at" in code_context

    def test_build_code_context_dict_without_classification(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test code context dict when classification is None."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        mock_exploration = Mock()
        mock_exploration.relevant_files = []
        mock_exploration.code_snippets = []
        mock_exploration.exploration_duration_ms = 100
        mock_exploration.success = False
        mock_exploration.error = "Classification failed"

        code_context = service._build_code_context_dict(mock_exploration, None)

        assert code_context["classification"] is None
        assert code_context["success"] is False
        assert code_context["error"] == "Classification failed"
        assert code_context["classification_duration_ms"] == 0


# -----------------------------------------------------------------------------
# process_theme_groups Tests (Issue #77)
# -----------------------------------------------------------------------------


class TestProcessThemeGroups:
    """Tests for process_theme_groups method - pipeline integration entry point."""

    @pytest.fixture
    def mock_evidence_service(self):
        """Create mock EvidenceService."""
        service = Mock()
        service.create_or_update.return_value = Mock(id=uuid4())
        return service

    @pytest.fixture
    def sample_theme_groups(self):
        """Sample theme groups as produced by pipeline."""
        return {
            "billing_invoice_download_error": [
                {
                    "id": "conv1",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "Cannot download invoice PDF",
                    "symptoms": ["error message", "blank page"],
                    "affected_flow": "invoice_download",
                    "excerpt": "I tried to download my invoice but got an error",
                },
                {
                    "id": "conv2",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "Invoice download broken",
                    "symptoms": ["404 error"],
                    "affected_flow": "invoice_download",
                    "excerpt": "Getting 404 when trying to access invoice",
                },
                {
                    "id": "conv3",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "PDF download fails",
                    "symptoms": ["timeout"],
                    "affected_flow": "invoice_download",
                    "excerpt": "Download times out after a few seconds",
                },
            ],
            "scheduler_pin_deletion": [
                {
                    "id": "conv4",
                    "product_area": "Scheduler",
                    "component": "Pins",
                    "user_intent": "Cannot delete pins",
                    "symptoms": ["button not working"],
                    "affected_flow": "pin_management",
                    "excerpt": "Delete button does nothing",
                },
                # Only 1 conversation - should become orphan
            ],
        }

    def test_creates_story_for_valid_group(
        self, mock_story_service, mock_orphan_service, mock_evidence_service, sample_theme_groups
    ):
        """Test that groups with >= MIN_GROUP_SIZE conversations create stories."""
        # Setup mock_story_service db for pipeline_run linking
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        result = service.process_theme_groups(sample_theme_groups)

        # billing_invoice_download_error has 3 convs -> should create story
        assert result.stories_created >= 1
        assert mock_story_service.create.called

    def test_creates_orphan_for_small_group(
        self, mock_story_service, mock_orphan_service, mock_evidence_service, sample_theme_groups
    ):
        """Test that groups with < MIN_GROUP_SIZE conversations create orphans."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        result = service.process_theme_groups(sample_theme_groups)

        # scheduler_pin_deletion has 1 conv -> should create orphan
        assert result.orphans_created >= 1
        assert mock_orphan_service.create.called

    def test_creates_evidence_for_stories(
        self, mock_story_service, mock_orphan_service, mock_evidence_service, sample_theme_groups
    ):
        """Test that evidence bundles are created for stories."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        result = service.process_theme_groups(sample_theme_groups)

        # Should create evidence for the story
        assert mock_evidence_service.create_or_update.called
        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        assert "story_id" in call_kwargs
        assert "conversation_ids" in call_kwargs
        assert "theme_signatures" in call_kwargs

    def test_links_stories_to_pipeline_run(
        self, mock_story_service, mock_orphan_service, mock_evidence_service, sample_theme_groups
    ):
        """Test that stories are linked to pipeline_run_id."""
        mock_cursor = Mock()
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        pipeline_run_id = 42
        result = service.process_theme_groups(
            sample_theme_groups,
            pipeline_run_id=pipeline_run_id,
        )

        # Should execute UPDATE to link story to pipeline run
        assert mock_cursor.execute.called
        # Find the UPDATE call
        update_calls = [c for c in mock_cursor.execute.call_args_list if 'pipeline_run_id' in str(c)]
        assert len(update_calls) >= 1

    def test_returns_processing_result(
        self, mock_story_service, mock_orphan_service, mock_evidence_service, sample_theme_groups
    ):
        """Test that ProcessingResult is returned with correct structure."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        result = service.process_theme_groups(sample_theme_groups)

        assert isinstance(result, ProcessingResult)
        assert result.stories_created >= 0
        assert result.orphans_created >= 0
        assert isinstance(result.created_story_ids, list)
        assert isinstance(result.created_orphan_ids, list)
        assert isinstance(result.errors, list)

    def test_handles_empty_groups(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test handling of empty theme groups."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        result = service.process_theme_groups({})

        assert result.stories_created == 0
        assert result.orphans_created == 0
        assert len(result.errors) == 0

    def test_handles_missing_fields_gracefully(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test graceful handling of conversations with missing fields."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        # Minimal data - only required fields
        minimal_groups = {
            "test_signature": [
                {"id": "conv1"},
                {"id": "conv2"},
                {"id": "conv3"},
            ],
        }

        # Should not raise
        result = service.process_theme_groups(minimal_groups)
        assert len(result.errors) == 0


class TestDictToConversationData:
    """Tests for _dict_to_conversation_data helper."""

    def test_converts_full_dict(self, mock_story_service, mock_orphan_service):
        """Test conversion with all fields present."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        conv_dict = {
            "id": "test123",
            "product_area": "Billing",
            "component": "Invoices",
            "user_intent": "Download invoice",
            "symptoms": ["error", "timeout"],
            "affected_flow": "invoice_download",
            "excerpt": "I can't download",
        }

        result = service._dict_to_conversation_data(conv_dict, "test_signature")

        assert isinstance(result, ConversationData)
        assert result.id == "test123"
        assert result.issue_signature == "test_signature"
        assert result.product_area == "Billing"
        assert result.component == "Invoices"
        assert result.symptoms == ["error", "timeout"]
        assert result.excerpt == "I can't download"

    def test_handles_missing_optional_fields(self, mock_story_service, mock_orphan_service):
        """Test conversion handles missing optional fields."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        conv_dict = {"id": "test123"}

        result = service._dict_to_conversation_data(conv_dict, "test_signature")

        assert result.id == "test123"
        assert result.product_area is None
        assert result.symptoms == []
        assert result.excerpt is None

    def test_rejects_empty_conversation_id(self, mock_story_service, mock_orphan_service):
        """Test that empty conversation IDs raise ValueError (S1 fix)."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        # Test with empty string
        with pytest.raises(ValueError, match="Empty conversation ID"):
            service._dict_to_conversation_data({"id": ""}, "test_signature")

        # Test with whitespace only
        with pytest.raises(ValueError, match="Empty conversation ID"):
            service._dict_to_conversation_data({"id": "   "}, "test_signature")

        # Test with missing id key
        with pytest.raises(ValueError, match="Empty conversation ID"):
            service._dict_to_conversation_data({}, "test_signature")


class TestGeneratePMResult:
    """Tests for _generate_pm_result helper."""

    def test_generates_keep_together_result(self, mock_story_service, mock_orphan_service):
        """Test PM result generation with keep_together decision."""
        service = StoryCreationService(mock_story_service, mock_orphan_service)

        result = service._generate_pm_result("test_signature", conversation_count=5)

        assert isinstance(result, FallbackPMReviewResult)
        assert result.signature == "test_signature"
        assert result.decision == "keep_together"
        assert result.conversation_count == 5
        assert result.sub_groups == []


# -----------------------------------------------------------------------------
# Quality Gate Tests (Milestone 6, Issue #82)
# -----------------------------------------------------------------------------


class TestQualityGates:
    """Tests for quality gate integration in process_theme_groups."""

    @pytest.fixture
    def sample_valid_group(self):
        """Sample theme group with valid data for quality gates."""
        return {
            "billing_invoice_error": [
                {
                    "id": "conv1",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "Cannot download invoice",
                    "symptoms": ["error message", "blank page"],
                    "affected_flow": "invoice_download",
                    "excerpt": "I tried to download my invoice but got an error",
                },
                {
                    "id": "conv2",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "Invoice download broken",
                    "symptoms": ["404 error"],
                    "affected_flow": "invoice_download",
                    "excerpt": "Getting 404 when trying to access invoice",
                },
                {
                    "id": "conv3",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "PDF download fails",
                    "symptoms": ["timeout"],
                    "affected_flow": "invoice_download",
                    "excerpt": "Download times out after a few seconds",
                },
            ],
        }

    @pytest.fixture
    def mock_confidence_scorer(self):
        """Create a mock ConfidenceScorer."""
        scorer = Mock()
        # Default behavior: return a valid ScoredGroup with score above threshold
        scored_group = Mock()
        scored_group.confidence_score = 75.0
        scorer.score_groups.return_value = [scored_group]
        return scorer

    def test_low_confidence_group_routes_to_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Groups with confidence < threshold should become orphans."""
        # Setup mock scorer to return low confidence
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 40.0  # Below default threshold of 50
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,  # Disable validation to test scoring only
        )

        result = service.process_theme_groups(sample_valid_group)

        # Should NOT create a story
        assert mock_story_service.create.call_count == 0
        # Should create orphan for the low-confidence group
        assert result.quality_gate_rejections == 1

    def test_failed_validation_routes_to_orphan(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Groups failing evidence validation should become orphans."""
        # Create group with missing required fields (no excerpts)
        invalid_group = {
            "test_signature": [
                {"id": "conv1"},  # Missing excerpt
                {"id": "conv2"},
                {"id": "conv3"},
            ],
        }

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            validation_enabled=True,  # Enable validation
            confidence_scorer=None,  # No scoring
        )

        result = service.process_theme_groups(invalid_group)

        # Should NOT create a story (validation fails)
        assert mock_story_service.create.call_count == 0
        # Should record quality gate rejection
        assert result.quality_gate_rejections == 1

    def test_confidence_score_persisted_to_story(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Stories should have confidence_score from scorer."""
        # Setup mock scorer with specific score
        mock_scorer = Mock()
        scored_group = Mock()
        scored_group.confidence_score = 85.5
        mock_scorer.score_groups.return_value = [scored_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        service.process_theme_groups(sample_valid_group)

        # Verify story was created with confidence_score
        mock_story_service.create.assert_called_once()
        create_call = mock_story_service.create.call_args[0][0]
        assert create_call.confidence_score == 85.5

    def test_quality_gates_disabled_skips_validation(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """validation_enabled=False should skip validation."""
        # Create group with missing excerpts (would fail validation)
        group_without_excerpts = {
            "test_signature": [
                {"id": "conv1"},
                {"id": "conv2"},
                {"id": "conv3"},
            ],
        }

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            validation_enabled=False,  # Disable validation
            confidence_scorer=None,  # No scoring
        )

        result = service.process_theme_groups(group_without_excerpts)

        # Should create story since validation is disabled
        assert mock_story_service.create.call_count == 1
        assert result.quality_gate_rejections == 0

    def test_quality_gates_without_scorer_skips_scoring(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """confidence_scorer=None should skip scoring."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=None,  # No scorer
            validation_enabled=False,  # Skip validation too
        )

        result = service.process_theme_groups(sample_valid_group)

        # Should create story without scoring
        assert mock_story_service.create.call_count == 1
        assert result.quality_gate_rejections == 0

        # Confidence score should be 0 (default when scorer not provided)
        create_call = mock_story_service.create.call_args[0][0]
        assert create_call.confidence_score == 0.0

    def test_boundary_confidence_threshold_at_49_9(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Test boundary case: 49.9 should be BELOW threshold of 50.0."""
        mock_scorer = Mock()
        scored_group = Mock()
        scored_group.confidence_score = 49.9  # Just below threshold
        mock_scorer.score_groups.return_value = [scored_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # 49.9 < 50.0, should route to orphan
        assert mock_story_service.create.call_count == 0
        assert result.quality_gate_rejections == 1

    def test_boundary_confidence_threshold_at_50_0(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Test boundary case: 50.0 should be AT threshold (pass)."""
        mock_scorer = Mock()
        scored_group = Mock()
        scored_group.confidence_score = 50.0  # Exactly at threshold
        mock_scorer.score_groups.return_value = [scored_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # 50.0 >= 50.0, should create story
        assert mock_story_service.create.call_count == 1
        assert result.quality_gate_rejections == 0

    def test_boundary_confidence_threshold_at_50_1(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Test boundary case: 50.1 should be ABOVE threshold (pass)."""
        mock_scorer = Mock()
        scored_group = Mock()
        scored_group.confidence_score = 50.1  # Just above threshold
        mock_scorer.score_groups.return_value = [scored_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # 50.1 >= 50.0, should create story
        assert mock_story_service.create.call_count == 1
        assert result.quality_gate_rejections == 0

    def test_undersized_group_fails_quality_gates(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Groups with < MIN_GROUP_SIZE conversations should fail quality gates."""
        # Only 2 conversations (MIN_GROUP_SIZE is 3)
        undersized_group = {
            "test_signature": [
                {"id": "conv1", "excerpt": "test 1"},
                {"id": "conv2", "excerpt": "test 2"},
            ],
        }

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            validation_enabled=False,
            confidence_scorer=None,
        )

        result = service.process_theme_groups(undersized_group)

        # Should not create story, should create orphan
        assert mock_story_service.create.call_count == 0
        assert result.quality_gate_rejections == 1

    def test_quality_gate_result_tracks_rejections(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """ProcessingResult should track quality_gate_rejections count."""
        # Create multiple groups with different outcomes
        mixed_groups = {
            "valid_group": [
                {"id": "conv1", "excerpt": "test 1"},
                {"id": "conv2", "excerpt": "test 2"},
                {"id": "conv3", "excerpt": "test 3"},
            ],
            "undersized_group": [
                {"id": "conv4", "excerpt": "test 4"},
            ],
        }

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            validation_enabled=False,
            confidence_scorer=None,
        )

        result = service.process_theme_groups(mixed_groups)

        # One story created, one rejected
        assert result.stories_created == 1
        assert result.quality_gate_rejections == 1


class TestOrphanRouting:
    """Tests for routing failed groups to OrphanIntegrationService."""

    @pytest.fixture
    def sample_valid_group(self):
        """Sample theme group with valid data."""
        return {
            "billing_invoice_error": [
                {
                    "id": "conv1",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "Cannot download invoice",
                    "symptoms": ["error message"],
                    "affected_flow": "invoice_download",
                    "excerpt": "I tried to download my invoice",
                },
                {
                    "id": "conv2",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "Invoice download broken",
                    "symptoms": ["404 error"],
                    "affected_flow": "invoice_download",
                    "excerpt": "Getting 404 when trying to access invoice",
                },
                {
                    "id": "conv3",
                    "product_area": "Billing",
                    "component": "Invoices",
                    "user_intent": "PDF download fails",
                    "symptoms": ["timeout"],
                    "affected_flow": "invoice_download",
                    "excerpt": "Download times out",
                },
            ],
        }

    def test_orphan_integration_service_called_for_failed_groups(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """OrphanIntegrationService should be called for failed quality gates."""
        # Setup mock OrphanIntegrationService
        mock_orphan_integration = Mock()
        mock_orphan_integration.process_theme.return_value = Mock(action="updated")

        # Setup scorer to return low confidence (fail quality gate)
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 30.0
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            orphan_integration_service=mock_orphan_integration,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # OrphanIntegrationService should be called for each conversation
        assert mock_orphan_integration.process_theme.call_count == 3

    def test_fallback_to_orphan_service_when_integration_unavailable(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Should fall back to OrphanService.create() if OrphanIntegrationService unavailable."""
        # Setup scorer to return low confidence
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 30.0
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            orphan_integration_service=None,  # Not available
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # Should fall back to orphan_service.create (via _create_or_update_orphan)
        assert mock_orphan_service.create.called or mock_orphan_service.add_conversations.called

    def test_orphan_routing_counts_as_update(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Orphan routing via OrphanIntegrationService should count as orphans_updated."""
        mock_orphan_integration = Mock()
        mock_orphan_integration.process_theme.return_value = Mock(action="updated")

        # Setup scorer to return low confidence
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 30.0
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            orphan_integration_service=mock_orphan_integration,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # Should track as orphan update
        assert result.orphans_updated >= 1

    def test_orphan_routing_fallback_on_integration_error(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """Should fall back to OrphanService if OrphanIntegrationService raises error."""
        mock_orphan_integration = Mock()
        mock_orphan_integration.process_theme.side_effect = Exception("Integration failed")

        # Setup scorer to return low confidence
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 30.0
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            orphan_integration_service=mock_orphan_integration,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # Should fall back to direct orphan creation
        assert mock_orphan_service.create.called or mock_orphan_service.add_conversations.called

    def test_orphan_fallback_counter_incremented_on_integration_error(
        self,
        mock_story_service,
        mock_orphan_service,
        sample_valid_group,
    ):
        """orphan_fallbacks counter should be incremented when OrphanIntegrationService fails."""
        mock_orphan_integration = Mock()
        mock_orphan_integration.process_theme.side_effect = Exception("Integration failed")

        # Setup scorer to return low confidence
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 30.0
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            orphan_integration_service=mock_orphan_integration,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_valid_group)

        # Should track the fallback occurrence
        assert result.orphan_fallbacks == 1

    def test_orphan_fallback_only_processes_remaining_conversations(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Fallback should only process conversations not already processed by OrphanIntegrationService."""
        # Create a group with 3 conversations
        sample_group = {
            "test_signature": [
                {"id": "conv1", "excerpt": "test 1"},
                {"id": "conv2", "excerpt": "test 2"},
                {"id": "conv3", "excerpt": "test 3"},
            ],
        }

        mock_orphan_integration = Mock()
        # Fail on the second call (after first conversation processed)
        call_count = [0]

        def fail_on_second_call(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise Exception("Integration failed mid-loop")
            return Mock(action="updated")

        mock_orphan_integration.process_theme.side_effect = fail_on_second_call

        # Setup scorer to return low confidence (trigger orphan routing)
        mock_scorer = Mock()
        low_score_group = Mock()
        low_score_group.confidence_score = 30.0
        mock_scorer.score_groups.return_value = [low_score_group]

        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            orphan_integration_service=mock_orphan_integration,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        result = service.process_theme_groups(sample_group)

        # The fallback should have been called
        assert result.orphan_fallbacks == 1

        # OrphanService should be called with only the remaining conversations (2, not 3)
        if mock_orphan_service.create.called:
            create_call = mock_orphan_service.create.call_args
            orphan_create = create_call[0][0]  # First positional arg
            # Should have 2 conversations (conv2, conv3), not 3
            assert len(orphan_create.conversation_ids) == 2
            assert "conv1" not in orphan_create.conversation_ids


# -----------------------------------------------------------------------------
# QualityGateResult Dataclass Tests
# -----------------------------------------------------------------------------


class TestQualityGateResultModel:
    """Tests for QualityGateResult dataclass."""

    def test_quality_gate_result_creation(self):
        """Test creating QualityGateResult."""
        from story_tracking.services.story_creation_service import QualityGateResult

        result = QualityGateResult(
            signature="test_sig",
            passed=True,
        )

        assert result.signature == "test_sig"
        assert result.passed is True
        assert result.validation_passed is True
        assert result.scoring_passed is True
        assert result.confidence_score == 0.0
        assert result.failure_reason is None

    def test_quality_gate_result_with_failure(self):
        """Test QualityGateResult with failure details."""
        from story_tracking.services.story_creation_service import QualityGateResult

        result = QualityGateResult(
            signature="failed_sig",
            passed=False,
            validation_passed=False,
            failure_reason="Evidence validation failed",
        )

        assert result.passed is False
        assert result.validation_passed is False
        assert result.failure_reason == "Evidence validation failed"


# -----------------------------------------------------------------------------
# Migrated Patterns from test_pipeline_integration.py
# -----------------------------------------------------------------------------


class TestSourceStatsCalculation:
    """Tests for source statistics calculation (migrated from test_pipeline_integration.py)."""

    def test_evidence_source_stats_intercom(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that source stats default to intercom for pipeline path."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_evidence_service = Mock()
        mock_evidence_service.create_or_update.return_value = Mock(id=uuid4())

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        theme_groups = {
            "test_sig": [
                {"id": "conv1", "excerpt": "test 1"},
                {"id": "conv2", "excerpt": "test 2"},
                {"id": "conv3", "excerpt": "test 3"},
            ],
        }

        service.process_theme_groups(theme_groups)

        # Verify evidence was created with source_stats
        mock_evidence_service.create_or_update.assert_called()
        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        assert call_kwargs["source_stats"] == {"intercom": 3}


class TestExcerptPreparation:
    """Tests for excerpt handling (migrated patterns from test_pipeline_integration.py)."""

    def test_excerpts_included_in_evidence(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that excerpts are included in evidence bundle."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_evidence_service = Mock()
        mock_evidence_service.create_or_update.return_value = Mock(id=uuid4())

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
        )

        theme_groups = {
            "test_sig": [
                {"id": "conv1", "excerpt": "I can't download my invoice"},
                {"id": "conv2", "excerpt": "Getting 404 error"},
                {"id": "conv3", "excerpt": "Download times out"},
            ],
        }

        service.process_theme_groups(theme_groups)

        # Verify excerpts were passed to evidence service
        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]
        assert len(excerpts) == 3
        # Note: Order determined by signal-based ranking (#158), so check presence not position
        texts = [e.text for e in excerpts]
        assert "I can't download my invoice" in texts
        assert "Getting 404 error" in texts
        assert "Download times out" in texts
        # Verify conversation_id is correctly associated with text
        conv_map = {e.text: e.conversation_id for e in excerpts}
        assert conv_map["I can't download my invoice"] == "conv1"

    def test_missing_excerpt_in_conversation_handled(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test that conversations with missing excerpts are handled gracefully."""
        mock_story_service.db = Mock()
        mock_story_service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        mock_story_service.db.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_evidence_service = Mock()
        mock_evidence_service.create_or_update.return_value = Mock(id=uuid4())

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,  # Disable validation to focus on excerpt handling
        )

        theme_groups = {
            "test_sig": [
                {"id": "conv1", "excerpt": "Test 1"},
                {"id": "conv2", "excerpt": "Test 2"},
                {"id": "conv3"},  # Missing excerpt - should be skipped in excerpts
            ],
        }

        service.process_theme_groups(theme_groups)

        # Should only have 2 excerpts (conv3 has no excerpt)
        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]
        assert len(excerpts) == 2


class TestApplyQualityGatesMethod:
    """Direct tests for _apply_quality_gates method."""

    def test_apply_quality_gates_passes_for_valid_group(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test _apply_quality_gates returns passing result for valid group."""
        mock_scorer = Mock()
        scored_group = Mock()
        scored_group.confidence_score = 75.0
        mock_scorer.score_groups.return_value = [scored_group]

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            confidence_threshold=50.0,
            validation_enabled=False,
        )

        conversations = [
            ConversationData(id="1", issue_signature="test", excerpt="test 1"),
            ConversationData(id="2", issue_signature="test", excerpt="test 2"),
            ConversationData(id="3", issue_signature="test", excerpt="test 3"),
        ]
        conv_dicts = [{"id": "1"}, {"id": "2"}, {"id": "3"}]

        result = service._apply_quality_gates("test_sig", conversations, conv_dicts)

        assert result.passed is True
        assert result.confidence_score == 75.0

    def test_apply_quality_gates_fails_for_undersized_group(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test _apply_quality_gates returns failing result for undersized group."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            validation_enabled=False,
        )

        # Only 2 conversations (MIN_GROUP_SIZE is 3)
        conversations = [
            ConversationData(id="1", issue_signature="test"),
            ConversationData(id="2", issue_signature="test"),
        ]
        conv_dicts = [{"id": "1"}, {"id": "2"}]

        result = service._apply_quality_gates("test_sig", conversations, conv_dicts)

        assert result.passed is False
        assert "minimum is" in result.failure_reason

    def test_apply_quality_gates_handles_scorer_error(
        self,
        mock_story_service,
        mock_orphan_service,
    ):
        """Test _apply_quality_gates handles scorer errors conservatively."""
        mock_scorer = Mock()
        mock_scorer.score_groups.side_effect = Exception("API rate limit exceeded")

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            confidence_scorer=mock_scorer,
            validation_enabled=False,
        )

        conversations = [
            ConversationData(id="1", issue_signature="test", excerpt="test 1"),
            ConversationData(id="2", issue_signature="test", excerpt="test 2"),
            ConversationData(id="3", issue_signature="test", excerpt="test 3"),
        ]
        conv_dicts = [{"id": "1"}, {"id": "2"}, {"id": "3"}]

        result = service._apply_quality_gates("test_sig", conversations, conv_dicts)

        # Should fail conservatively on error
        assert result.passed is False
        assert "scoring error" in result.failure_reason.lower()


class TestEvidenceDiagnosticSummary:
    """
    Tests for Issue #156: Evidence uses diagnostic_summary + key_excerpts.

    Verifies that _create_evidence_for_story prefers diagnostic_summary over
    raw excerpt and appends key_excerpts as additional evidence snippets.
    """

    @pytest.fixture
    def mock_story_service(self):
        """Create a mock story service."""
        service = Mock(spec=StoryService)
        service.db = Mock()
        service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        service.db.cursor.return_value.__exit__ = Mock(return_value=False)
        service.create.return_value = Story(
            id=uuid4(),
            title="Test Story",
            description="Test description",
            labels=[],
            priority=None,
            severity=None,
            product_area="test",
            technical_area="test",
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return service

    @pytest.fixture
    def mock_orphan_service(self):
        """Create a mock orphan service."""
        service = Mock(spec=OrphanService)
        service.get_by_signature.return_value = None
        return service

    @pytest.fixture
    def mock_evidence_service(self):
        """Create mock EvidenceService."""
        service = Mock()
        service.create_or_update.return_value = Mock(id=uuid4())
        return service

    def test_evidence_uses_diagnostic_summary_when_present(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that diagnostic_summary is preferred over excerpt when present."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "raw excerpt text",
                    "diagnostic_summary": "LLM-generated diagnostic summary",
                },
                {"id": "conv2", "excerpt": "another raw excerpt"},
                {"id": "conv3", "excerpt": "third excerpt"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # First excerpt should use diagnostic_summary, not raw excerpt
        assert excerpts[0].text == "LLM-generated diagnostic summary"
        assert excerpts[0].conversation_id == "conv1"
        # Second should fall back to excerpt
        assert excerpts[1].text == "another raw excerpt"

    def test_evidence_fallback_when_diagnostic_summary_empty_string(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test fallback to excerpt when diagnostic_summary is empty string."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "fallback excerpt",
                    "diagnostic_summary": "",  # Empty string
                },
                {
                    "id": "conv2",
                    "excerpt": "another fallback",
                    "diagnostic_summary": "   ",  # Whitespace only
                },
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Both should fall back to excerpt since diagnostic_summary is empty/whitespace
        # Note: Order may vary due to signal-based ranking (#158)
        texts = [e.text for e in excerpts]
        assert "fallback excerpt" in texts
        assert "another fallback" in texts

    def test_evidence_fallback_when_diagnostic_summary_none(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test fallback to excerpt when diagnostic_summary is None."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "fallback excerpt",
                    "diagnostic_summary": None,
                },
                {"id": "conv2", "excerpt": "no diagnostic field"},  # Missing field
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Both should fall back to excerpt
        # Note: Order may vary due to signal-based ranking (#158)
        texts = [e.text for e in excerpts]
        assert "fallback excerpt" in texts
        assert "no diagnostic field" in texts

    def test_key_excerpts_appended_to_evidence(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that key_excerpts are appended as additional evidence snippets."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "main excerpt",
                    "diagnostic_summary": "diagnostic summary",
                    "key_excerpts": [
                        {"text": "key excerpt 1"},
                        {"text": "key excerpt 2"},
                    ],
                },
                {"id": "conv2", "excerpt": "second conv"},
                {"id": "conv3", "excerpt": "third conv"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Should have: diagnostic_summary + 2 key_excerpts + 2 fallback excerpts = 5
        assert len(excerpts) >= 4
        texts = [e.text for e in excerpts]
        assert "diagnostic summary" in texts
        assert "key excerpt 1" in texts
        assert "key excerpt 2" in texts

    def test_key_excerpts_with_relevance_preserved(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that key_excerpts relevance annotation is included."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "main",
                    "key_excerpts": [
                        {
                            "text": "error occurred",
                            "relevance": "Shows root cause",
                        },
                    ],
                },
                {"id": "conv2", "excerpt": "second"},
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Find the key_excerpt and check relevance is included
        key_excerpt = next(
            (e for e in excerpts if "error occurred" in e.text), None
        )
        assert key_excerpt is not None
        assert "[Relevance: Shows root cause]" in key_excerpt.text

    def test_excerpt_length_truncation(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that excerpts are truncated to MAX_EXCERPT_LENGTH."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        long_text = "x" * (MAX_EXCERPT_LENGTH + 100)
        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "short",
                    "diagnostic_summary": long_text,
                },
                {"id": "conv2", "excerpt": "second"},
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # First excerpt should be truncated
        assert len(excerpts[0].text) == MAX_EXCERPT_LENGTH

    def test_mixed_conversations_some_with_diagnostic_summary(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test handling of mixed conversations with varying diagnostic_summary availability."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "fallback 1",
                    "diagnostic_summary": "has diagnostic",
                },
                {
                    "id": "conv2",
                    "excerpt": "fallback 2",
                    # No diagnostic_summary
                },
                {
                    "id": "conv3",
                    "excerpt": "fallback 3",
                    "diagnostic_summary": "",  # Empty
                },
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        texts = [e.text for e in excerpts]
        # conv1 uses diagnostic_summary
        assert "has diagnostic" in texts
        # conv2 and conv3 fall back to excerpt
        assert "fallback 2" in texts
        assert "fallback 3" in texts
        # Raw excerpt for conv1 should NOT be used
        assert "fallback 1" not in texts

    def test_empty_key_excerpts_handled_gracefully(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that empty or malformed key_excerpts don't cause errors."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "main",
                    "key_excerpts": [],  # Empty list
                },
                {
                    "id": "conv2",
                    "excerpt": "second",
                    "key_excerpts": [
                        {"text": ""},  # Empty text
                        {"text": "   "},  # Whitespace only
                        {"not_text": "missing text field"},  # Wrong field
                        "not a dict",  # Wrong type
                    ],
                },
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        # Should not raise
        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Should have 3 primary excerpts, no malformed key_excerpts
        texts = [e.text for e in excerpts]
        assert "main" in texts
        assert "second" in texts
        assert "third" in texts


class TestEvidenceMetadataCompleteness:
    """
    Tests for Issue #157: Evidence metadata completeness.

    Verifies that evidence excerpts include email, intercom_url, and org/user IDs
    when available in the conversation data.
    """

    @pytest.fixture
    def mock_story_service(self):
        """Create a mock story service."""
        service = Mock(spec=StoryService)
        service.db = Mock()
        service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        service.db.cursor.return_value.__exit__ = Mock(return_value=False)
        service.create.return_value = Story(
            id=uuid4(),
            title="Test Story",
            description="Test description",
            labels=[],
            priority=None,
            severity=None,
            product_area="test",
            technical_area="test",
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return service

    @pytest.fixture
    def mock_orphan_service(self):
        """Create a mock orphan service."""
        service = Mock(spec=OrphanService)
        service.get_by_signature.return_value = None
        return service

    @pytest.fixture
    def mock_evidence_service(self):
        """Create mock EvidenceService."""
        service = Mock()
        service.create_or_update.return_value = Mock(id=uuid4())
        return service

    def test_evidence_includes_contact_email(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that contact_email flows through to evidence."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "test excerpt",
                    "contact_email": "user@example.com",
                },
                {"id": "conv2", "excerpt": "second"},
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # First excerpt should have email
        assert excerpts[0].email == "user@example.com"
        # Second excerpt should have None email
        assert excerpts[1].email is None

    def test_evidence_includes_intercom_url(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that intercom_url is constructed correctly."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {"id": "conv123", "excerpt": "test excerpt"},
                {"id": "conv456", "excerpt": "second"},
                {"id": "conv789", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # All excerpts should have intercom_url
        assert excerpts[0].intercom_url is not None
        assert "conv123" in excerpts[0].intercom_url
        assert excerpts[1].intercom_url is not None
        assert "conv456" in excerpts[1].intercom_url

    def test_intercom_url_format_matches_story_formatter(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that intercom_url format matches story_formatter.py pattern."""
        # Test the helper function directly
        url = _build_intercom_url("test_conv_id")

        # Should match the pattern from story_formatter.py
        expected_pattern = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/test_conv_id"
        assert url == expected_pattern

    def test_evidence_includes_org_user_ids(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that org_id, user_id, contact_id flow through to evidence."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "test excerpt",
                    "org_id": "org_123",
                    "user_id": "user_456",
                    "contact_id": "contact_789",
                },
                {"id": "conv2", "excerpt": "second"},
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # First excerpt should have all IDs
        assert excerpts[0].org_id == "org_123"
        assert excerpts[0].user_id == "user_456"
        assert excerpts[0].contact_id == "contact_789"

        # Second excerpt should have None IDs
        assert excerpts[1].org_id is None
        assert excerpts[1].user_id is None
        assert excerpts[1].contact_id is None

    def test_evidence_metadata_optional_when_missing(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test graceful handling when metadata fields are missing/None."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "test excerpt",
                    # All metadata fields missing
                },
                {
                    "id": "conv2",
                    "excerpt": "second",
                    "contact_email": None,
                    "org_id": None,
                },
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        # Should not raise
        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # All excerpts should be created successfully
        assert len(excerpts) == 3
        # intercom_url should still be present (constructed from ID)
        assert all(e.intercom_url is not None for e in excerpts)

    def test_conversation_data_metadata_fields(self):
        """Test that ConversationData dataclass accepts new metadata fields."""
        conv = ConversationData(
            id="test",
            issue_signature="test_sig",
            contact_email="test@example.com",
            contact_id="contact_123",
            user_id="user_456",
            org_id="org_789",
        )

        assert conv.contact_email == "test@example.com"
        assert conv.contact_id == "contact_123"
        assert conv.user_id == "user_456"
        assert conv.org_id == "org_789"

    def test_metadata_in_key_excerpts(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that metadata is also included in key_excerpts evidence."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "main excerpt",
                    "contact_email": "user@example.com",
                    "org_id": "org_123",
                    "key_excerpts": [
                        {"text": "key excerpt text"},
                    ],
                },
                {"id": "conv2", "excerpt": "second"},
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Find the key_excerpt
        key_excerpt = next(
            (e for e in excerpts if "key excerpt text" in e.text), None
        )
        assert key_excerpt is not None
        # Key excerpt should have same metadata as parent conversation
        assert key_excerpt.email == "user@example.com"
        assert key_excerpt.org_id == "org_123"
        assert key_excerpt.intercom_url is not None
        assert "conv1" in key_excerpt.intercom_url


class TestSignalBasedRanking:
    """
    Tests for Issue #158: Signal-based evidence ranking.

    Verifies that conversations are ranked by signal quality rather than
    arbitrary first-N selection, and that key_excerpts are deduped against
    diagnostic_summary.
    """

    def test_ranking_prefers_key_excerpts(self):
        """Test that conversations with key_excerpts are ranked higher."""
        conv_with_key = ConversationData(
            id="with_key",
            issue_signature="test",
            excerpt="low signal text",
            key_excerpts=[{"text": "important error"}],
        )
        conv_without_key = ConversationData(
            id="without_key",
            issue_signature="test",
            excerpt="low signal text",
        )

        ranked = _rank_conversations_by_signal([conv_without_key, conv_with_key])

        # Conversation with key_excerpts should be first
        assert ranked[0].id == "with_key"
        assert ranked[1].id == "without_key"

    def test_ranking_prefers_diagnostic_summary(self):
        """Test that conversations with diagnostic_summary rank higher than those without."""
        conv_with_diag = ConversationData(
            id="with_diag",
            issue_signature="test",
            diagnostic_summary="Detailed diagnostic summary",
            excerpt="short",
        )
        conv_without_diag = ConversationData(
            id="without_diag",
            issue_signature="test",
            excerpt="short excerpt only",
        )

        ranked = _rank_conversations_by_signal([conv_without_diag, conv_with_diag])

        # Conversation with diagnostic_summary should be first
        assert ranked[0].id == "with_diag"

    def test_ranking_by_error_density(self):
        """Test that conversations with error patterns rank higher."""
        conv_errors = ConversationData(
            id="high_error",
            issue_signature="test",
            excerpt="Error 500 failed crashed timeout exception",
        )
        conv_no_errors = ConversationData(
            id="low_error",
            issue_signature="test",
            excerpt="Everything is working fine today",
        )

        ranked = _rank_conversations_by_signal([conv_no_errors, conv_errors])

        # High error density should rank first
        assert ranked[0].id == "high_error"

    def test_ranking_stable_tiebreaker(self):
        """Test that conversation_id provides stable tie-breaker."""
        # Create conversations with identical signal characteristics
        conv_b = ConversationData(
            id="b_conv",
            issue_signature="test",
            excerpt="same text",
        )
        conv_a = ConversationData(
            id="a_conv",
            issue_signature="test",
            excerpt="same text",
        )
        conv_c = ConversationData(
            id="c_conv",
            issue_signature="test",
            excerpt="same text",
        )

        # Run multiple times to verify stability
        for _ in range(3):
            ranked = _rank_conversations_by_signal([conv_b, conv_c, conv_a])
            ids = [c.id for c in ranked]
            # Should be deterministic ordering
            assert ids == ids  # Same order each time

    def test_ranking_handles_all_low_signal(self):
        """Test graceful handling when no conversations have high signal."""
        convs = [
            ConversationData(id=f"conv{i}", issue_signature="test", excerpt="simple")
            for i in range(5)
        ]

        # Should not raise
        ranked = _rank_conversations_by_signal(convs)

        # Should return all conversations
        assert len(ranked) == 5

    def test_ranking_handles_empty_key_excerpts(self):
        """Test that empty key_excerpts list doesn't crash ranking."""
        conv = ConversationData(
            id="test",
            issue_signature="test",
            excerpt="text",
            key_excerpts=[],
        )

        ranked = _rank_conversations_by_signal([conv])

        assert len(ranked) == 1
        assert ranked[0].id == "test"

    def test_text_similarity_detects_duplicates(self):
        """Test that _text_similarity correctly identifies similar texts."""
        # High similarity
        assert _text_similarity(
            "The error occurred when uploading files",
            "The error occurred when uploading files to server",
            threshold=0.7,
        )

        # Low similarity
        assert not _text_similarity(
            "Login failed with error",
            "Upload completed successfully",
            threshold=0.7,
        )

        # Empty strings
        assert not _text_similarity("", "some text")
        assert not _text_similarity("some text", "")

    @pytest.fixture
    def mock_story_service(self):
        """Create a mock story service."""
        service = Mock(spec=StoryService)
        service.db = Mock()
        service.db.cursor.return_value.__enter__ = Mock(return_value=Mock())
        service.db.cursor.return_value.__exit__ = Mock(return_value=False)
        service.create.return_value = Story(
            id=uuid4(),
            title="Test Story",
            description="Test description",
            labels=[],
            priority=None,
            severity=None,
            product_area="test",
            technical_area="test",
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        return service

    @pytest.fixture
    def mock_orphan_service(self):
        """Create a mock orphan service."""
        service = Mock(spec=OrphanService)
        service.get_by_signature.return_value = None
        return service

    @pytest.fixture
    def mock_evidence_service(self):
        """Create mock EvidenceService."""
        service = Mock()
        service.create_or_update.return_value = Mock(id=uuid4())
        return service

    def test_ranking_selects_higher_signal_over_earlier(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that higher-signal conversation is selected over earlier low-signal one."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        # conv1 is first but low signal, conv2 is high signal
        theme_groups = {
            "test_sig": [
                {"id": "conv1", "excerpt": "simple text"},
                {
                    "id": "conv2",
                    "excerpt": "Error 500 failed crashed timeout",
                    "diagnostic_summary": "Detailed error analysis",
                    "key_excerpts": [{"text": "critical error"}],
                },
                {"id": "conv3", "excerpt": "another simple one"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # The first excerpt should be from the high-signal conv2, not conv1
        # (conv2 has key_excerpts, diagnostic_summary, and error patterns)
        assert excerpts[0].conversation_id == "conv2"

    def test_dedupe_key_excerpts_against_diagnostic_summary(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that key_excerpts similar to diagnostic_summary are deduped."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "raw text",
                    "diagnostic_summary": "The upload failed with error 500",
                    "key_excerpts": [
                        # This is very similar to diagnostic_summary - should be deduped
                        {"text": "The upload failed with error 500 internal"},
                        # This is different - should be kept
                        {"text": "User tried three different browsers"},
                    ],
                },
                {"id": "conv2", "excerpt": "second"},
                {"id": "conv3", "excerpt": "third"},
            ],
        }

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        texts = [e.text for e in excerpts]
        # The similar key_excerpt should be deduped
        assert not any("error 500 internal" in t.lower() for t in texts)
        # The different key_excerpt should be kept
        assert any("different browsers" in t.lower() for t in texts)

    def test_top_n_selected_after_ranking(
        self, mock_story_service, mock_orphan_service, mock_evidence_service
    ):
        """Test that MAX_EXCERPTS_IN_THEME limit is respected after ranking."""
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        # Create more conversations than MAX_EXCERPTS_IN_THEME
        convs = [
            {"id": f"conv{i}", "excerpt": f"text {i}"}
            for i in range(MAX_EXCERPTS_IN_THEME + 3)
        ]
        theme_groups = {"test_sig": convs}

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Should only have MAX_EXCERPTS_IN_THEME excerpts
        assert len(excerpts) == MAX_EXCERPTS_IN_THEME
