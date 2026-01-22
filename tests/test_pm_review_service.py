"""
PM Review Service Tests

Tests for PMReviewService - Theme group coherence evaluation.
Run with: pytest tests/test_pm_review_service.py -v
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.services.pm_review_service import (
    PMReviewService,
    PMReviewResult,
    ReviewDecision,
    ConversationContext,
    SubGroupSuggestion,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def pm_review_service():
    """Create a PMReviewService with mocked OpenAI client."""
    service = PMReviewService(model="gpt-4o-mini", temperature=0.3)
    return service


@pytest.fixture
def sample_conversations():
    """Create sample conversations for testing."""
    return [
        ConversationContext(
            conversation_id="conv_1",
            user_intent="Pins are being posted twice",
            symptoms=["duplicate pins", "double posting"],
            affected_flow="Pinterest publishing",
            excerpt="My pins are showing up twice on my Pinterest board",
            product_area="publishing",
            component="pinterest",
        ),
        ConversationContext(
            conversation_id="conv_2",
            user_intent="Pins appear multiple times",
            symptoms=["duplicate content", "repeated posts"],
            affected_flow="Pinterest sync",
            excerpt="Every time I publish, the pin appears twice",
            product_area="publishing",
            component="pinterest",
        ),
        ConversationContext(
            conversation_id="conv_3",
            user_intent="Duplicate pins on Pinterest",
            symptoms=["duplicate pins"],
            affected_flow="Pinterest publishing",
            excerpt="I'm seeing duplicate pins after scheduling",
            product_area="publishing",
            component="pinterest",
        ),
    ]


@pytest.fixture
def mixed_symptom_conversations():
    """Create conversations with different symptoms (should trigger split)."""
    return [
        ConversationContext(
            conversation_id="conv_1",
            user_intent="Pins are being posted twice",
            symptoms=["duplicate pins"],
            affected_flow="Pinterest publishing",
            excerpt="My pins are showing up twice",
            product_area="publishing",
            component="pinterest",
        ),
        ConversationContext(
            conversation_id="conv_2",
            user_intent="Pins are being posted twice",
            symptoms=["duplicate pins"],
            affected_flow="Pinterest publishing",
            excerpt="Double pins appearing",
            product_area="publishing",
            component="pinterest",
        ),
        ConversationContext(
            conversation_id="conv_3",
            user_intent="Pins are missing",
            symptoms=["missing pins", "pins vanished"],
            affected_flow="Pinterest sync",
            excerpt="My pins have disappeared from my board",
            product_area="publishing",
            component="pinterest",
        ),
        ConversationContext(
            conversation_id="conv_4",
            user_intent="Pins not showing",
            symptoms=["missing pins"],
            affected_flow="Pinterest sync",
            excerpt="Several of my pins are gone",
            product_area="publishing",
            component="pinterest",
        ),
    ]


# -----------------------------------------------------------------------------
# Unit Tests - Basic Functionality
# -----------------------------------------------------------------------------


class TestPMReviewServiceInit:
    """Test PMReviewService initialization."""

    def test_default_initialization(self):
        """Test service initializes with default values."""
        service = PMReviewService()
        assert service.model == "gpt-4o-mini"
        assert service.temperature == 0.3
        assert service._client is None  # Lazy initialization

    def test_custom_initialization(self):
        """Test service initializes with custom values."""
        service = PMReviewService(model="gpt-4", temperature=0.5, timeout=60.0)
        assert service.model == "gpt-4"
        assert service.temperature == 0.5
        assert service.timeout == 60.0


class TestReviewDecisionEnum:
    """Test ReviewDecision enum values."""

    def test_enum_values(self):
        """Test enum has expected values."""
        assert ReviewDecision.KEEP_TOGETHER.value == "keep_together"
        assert ReviewDecision.SPLIT.value == "split"
        assert ReviewDecision.REJECT.value == "reject"

    def test_string_conversion(self):
        """Test enum string representation."""
        assert str(ReviewDecision.KEEP_TOGETHER) == "ReviewDecision.KEEP_TOGETHER"


class TestPMReviewResult:
    """Test PMReviewResult dataclass."""

    def test_passed_property_keep_together(self):
        """Test passed property returns True for keep_together."""
        result = PMReviewResult(
            original_signature="test_sig",
            conversation_count=3,
            decision=ReviewDecision.KEEP_TOGETHER,
            reasoning="All same issue",
        )
        assert result.passed is True

    def test_passed_property_split(self):
        """Test passed property returns False for split."""
        result = PMReviewResult(
            original_signature="test_sig",
            conversation_count=3,
            decision=ReviewDecision.SPLIT,
            reasoning="Different symptoms",
            sub_groups=[
                SubGroupSuggestion(
                    suggested_signature="test_sub_1",
                    conversation_ids=["conv_1", "conv_2"],
                    rationale="Same symptom",
                )
            ],
        )
        assert result.passed is False

    def test_passed_property_reject(self):
        """Test passed property returns False for reject."""
        result = PMReviewResult(
            original_signature="test_sig",
            conversation_count=3,
            decision=ReviewDecision.REJECT,
            reasoning="All different",
            orphan_conversation_ids=["conv_1", "conv_2", "conv_3"],
        )
        assert result.passed is False


# -----------------------------------------------------------------------------
# Unit Tests - Review Logic
# -----------------------------------------------------------------------------


class TestReviewGroup:
    """Test review_group method."""

    def test_single_conversation_skips_review(self, pm_review_service):
        """Test that single-conversation groups skip PM review."""
        single_conv = [
            ConversationContext(
                conversation_id="conv_1",
                user_intent="Test intent",
                symptoms=["symptom"],
                affected_flow="flow",
                excerpt="excerpt",
                product_area="area",
                component="comp",
            )
        ]

        result = pm_review_service.review_group("test_sig", single_conv)

        assert result.decision == ReviewDecision.KEEP_TOGETHER
        assert result.conversation_count == 1
        assert "skipped" in result.reasoning.lower()
        assert result.model_used == ""
        assert result.review_duration_ms == 0

    def test_empty_conversation_list(self, pm_review_service):
        """Test handling of empty conversation list."""
        result = pm_review_service.review_group("test_sig", [])

        assert result.decision == ReviewDecision.KEEP_TOGETHER
        assert result.conversation_count == 0

    def test_keep_together_response(self, pm_review_service, sample_conversations):
        """Test parsing of keep_together LLM response."""
        # Mock the OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "decision": "keep_together",
            "reasoning": "All conversations are about duplicate pins",
            "same_fix_confidence": 0.95,
            "sub_groups": [],
            "orphans": [],
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        pm_review_service._client = mock_client

        result = pm_review_service.review_group("pinterest_duplicate_pins", sample_conversations)

        assert result.decision == ReviewDecision.KEEP_TOGETHER
        assert "duplicate" in result.reasoning.lower()
        assert result.sub_groups == []
        assert result.orphan_conversation_ids == []

    def test_split_response(self, pm_review_service, mixed_symptom_conversations):
        """Test parsing of split LLM response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "decision": "split",
            "reasoning": "Conversations have different symptoms: duplicates vs missing",
            "same_fix_confidence": 0.3,
            "sub_groups": [
                {
                    "suggested_signature": "pinterest_duplicate_pins",
                    "conversation_ids": ["conv_1", "conv_2"],
                    "rationale": "Both about duplicate pins",
                    "symptom": "duplicate pins",
                },
                {
                    "suggested_signature": "pinterest_missing_pins",
                    "conversation_ids": ["conv_3", "conv_4"],
                    "rationale": "Both about missing pins",
                    "symptom": "missing pins",
                },
            ],
            "orphans": [],
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        pm_review_service._client = mock_client

        result = pm_review_service.review_group(
            "pinterest_publishing_failure", mixed_symptom_conversations
        )

        assert result.decision == ReviewDecision.SPLIT
        assert len(result.sub_groups) == 2
        assert result.sub_groups[0].suggested_signature == "pinterest_duplicate_pins"
        assert result.sub_groups[1].suggested_signature == "pinterest_missing_pins"

    def test_llm_error_defaults_to_keep_together(self, pm_review_service, sample_conversations):
        """Test that LLM errors default to keep_together decision."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API timeout")
        pm_review_service._client = mock_client

        result = pm_review_service.review_group("test_sig", sample_conversations)

        assert result.decision == ReviewDecision.KEEP_TOGETHER
        assert "error" in result.reasoning.lower()

    def test_invalid_json_defaults_to_keep_together(self, pm_review_service, sample_conversations):
        """Test that invalid JSON response defaults to keep_together."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not valid JSON"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        pm_review_service._client = mock_client

        result = pm_review_service.review_group("test_sig", sample_conversations)

        assert result.decision == ReviewDecision.KEEP_TOGETHER
        assert "parse error" in result.reasoning.lower() or "json" in result.reasoning.lower()

    def test_split_with_orphans(self, pm_review_service, mixed_symptom_conversations):
        """Test split response with orphan conversations."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "decision": "split",
            "reasoning": "Conversations have different issues",
            "same_fix_confidence": 0.2,
            "sub_groups": [
                {
                    "suggested_signature": "pinterest_duplicate_pins",
                    "conversation_ids": ["conv_1", "conv_2"],
                    "rationale": "Both about duplicate pins",
                },
            ],
            "orphans": [
                {"conversation_id": "conv_3", "reason": "Unique issue"},
                {"conversation_id": "conv_4", "reason": "Different problem"},
            ],
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        pm_review_service._client = mock_client

        result = pm_review_service.review_group(
            "pinterest_publishing_failure", mixed_symptom_conversations
        )

        assert result.decision == ReviewDecision.SPLIT
        assert len(result.orphan_conversation_ids) == 2
        assert "conv_3" in result.orphan_conversation_ids
        assert "conv_4" in result.orphan_conversation_ids

    def test_split_no_valid_subgroups_becomes_reject(self, pm_review_service, sample_conversations):
        """Test that split with no valid sub-groups becomes reject."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "decision": "split",
            "reasoning": "All conversations are different",
            "same_fix_confidence": 0.1,
            "sub_groups": [],  # No valid sub-groups
            "orphans": [],
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        pm_review_service._client = mock_client

        result = pm_review_service.review_group("test_sig", sample_conversations)

        assert result.decision == ReviewDecision.REJECT
        # All original conversations become orphans
        assert len(result.orphan_conversation_ids) == len(sample_conversations)


class TestReviewGroupsBatch:
    """Test review_groups_batch method."""

    @patch.object(PMReviewService, "review_group")
    def test_batch_processes_all_groups(self, mock_review_group, pm_review_service, sample_conversations):
        """Test that batch processes all groups."""
        mock_review_group.return_value = PMReviewResult(
            original_signature="test_sig",
            conversation_count=3,
            decision=ReviewDecision.KEEP_TOGETHER,
            reasoning="Test",
        )

        groups = {
            "sig_1": sample_conversations,
            "sig_2": sample_conversations[:2],
        }

        results = pm_review_service.review_groups_batch(groups)

        assert len(results) == 2
        assert "sig_1" in results
        assert "sig_2" in results
        assert mock_review_group.call_count == 2

    @patch.object(PMReviewService, "review_group")
    def test_batch_handles_individual_errors(self, mock_review_group, pm_review_service, sample_conversations):
        """Test that batch continues processing after individual errors."""
        # First call succeeds, second fails
        mock_review_group.side_effect = [
            PMReviewResult(
                original_signature="sig_1",
                conversation_count=3,
                decision=ReviewDecision.KEEP_TOGETHER,
                reasoning="Test",
            ),
            Exception("API error"),
        ]

        groups = {
            "sig_1": sample_conversations,
            "sig_2": sample_conversations[:2],
        }

        results = pm_review_service.review_groups_batch(groups)

        assert len(results) == 2
        assert results["sig_1"].decision == ReviewDecision.KEEP_TOGETHER
        # Error group defaults to keep_together
        assert results["sig_2"].decision == ReviewDecision.KEEP_TOGETHER
        assert "error" in results["sig_2"].reasoning.lower()


class TestFormatConversations:
    """Test _format_conversations helper method."""

    def test_formats_all_conversations(self, pm_review_service, sample_conversations):
        """Test that all conversations are formatted."""
        formatted = pm_review_service._format_conversations(sample_conversations)

        assert "conv_1" in formatted
        assert "conv_2" in formatted
        assert "conv_3" in formatted
        assert "Pins are being posted twice" in formatted

    def test_truncates_long_excerpts(self, pm_review_service):
        """Test that long excerpts are truncated."""
        long_excerpt = "A" * 1000
        conv = ConversationContext(
            conversation_id="conv_1",
            user_intent="Test",
            symptoms=["symptom"],
            affected_flow="flow",
            excerpt=long_excerpt,
            product_area="area",
            component="comp",
        )

        formatted = pm_review_service._format_conversations([conv])

        # Excerpt should be truncated to 500 chars
        assert len(long_excerpt) > 500
        assert long_excerpt not in formatted  # Full excerpt shouldn't appear


class TestParseResponse:
    """Test _parse_response method."""

    def test_handles_markdown_code_blocks(self, pm_review_service, sample_conversations):
        """Test parsing JSON wrapped in markdown code blocks."""
        response_with_blocks = """```json
        {
            "decision": "keep_together",
            "reasoning": "All same issue"
        }
        ```"""

        result = pm_review_service._parse_response(
            response_with_blocks, "test_sig", sample_conversations
        )

        assert result.decision == ReviewDecision.KEEP_TOGETHER

    def test_handles_plain_code_blocks(self, pm_review_service, sample_conversations):
        """Test parsing JSON wrapped in plain code blocks."""
        response_with_blocks = """```
        {
            "decision": "split",
            "reasoning": "Different symptoms",
            "sub_groups": [
                {"suggested_signature": "sig_1", "conversation_ids": ["conv_1"], "rationale": "test"}
            ]
        }
        ```"""

        result = pm_review_service._parse_response(
            response_with_blocks, "test_sig", sample_conversations
        )

        assert result.decision == ReviewDecision.SPLIT

    def test_handles_unknown_decision(self, pm_review_service, sample_conversations):
        """Test that unknown decision defaults to keep_together."""
        response = json.dumps({
            "decision": "unknown_decision",
            "reasoning": "Test",
        })

        result = pm_review_service._parse_response(
            response, "test_sig", sample_conversations
        )

        assert result.decision == ReviewDecision.KEEP_TOGETHER


# -----------------------------------------------------------------------------
# Integration Tests (with actual OpenAI - skip in CI)
# -----------------------------------------------------------------------------


@pytest.mark.skip(reason="Requires OpenAI API key - run manually")
class TestPMReviewServiceIntegration:
    """Integration tests that call actual OpenAI API."""

    def test_real_keep_together(self, sample_conversations):
        """Test real API call for coherent group."""
        service = PMReviewService()
        result = service.review_group("pinterest_duplicate_pins", sample_conversations)

        assert result.decision in [ReviewDecision.KEEP_TOGETHER, ReviewDecision.SPLIT]
        assert result.model_used == "gpt-4o-mini"
        assert result.review_duration_ms > 0

    def test_real_split(self, mixed_symptom_conversations):
        """Test real API call for incoherent group."""
        service = PMReviewService()
        result = service.review_group(
            "pinterest_publishing_failure", mixed_symptom_conversations
        )

        # This should ideally trigger a split
        assert result.decision in [ReviewDecision.KEEP_TOGETHER, ReviewDecision.SPLIT]
        assert result.review_duration_ms > 0
