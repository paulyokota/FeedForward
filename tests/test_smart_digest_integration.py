"""
Smart Digest Integration Tests (Phase 3+4)

Tests for Smart Digest fields integration in PM Review and Context Gap Analysis.
Run with: pytest tests/test_smart_digest_integration.py -v

Phase 3: PM Review uses Smart Digest
- _format_key_excerpts() function
- format_conversations_for_review() with Smart Digest
- ConversationContext dataclass with diagnostic_summary and key_excerpts
- ConversationData dataclass with diagnostic_summary and key_excerpts

Phase 4: Context Gap Analysis
- ContextGapItem, ContextGapsByArea, ContextGapsResponse schemas
- /api/analytics/context-gaps endpoint

Owner: Kenji (Testing)
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List
from unittest.mock import Mock, MagicMock

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Phase 3 imports
from prompts.pm_review import (
    _format_key_excerpts,
    format_conversations_for_review,
    SMART_DIGEST_TEMPLATE,
    EXCERPT_TEMPLATE,
)
from story_tracking.services.pm_review_service import ConversationContext
from story_tracking.services.story_creation_service import ConversationData

# Phase 4 imports
from api.schemas.analytics import (
    ContextGapItem,
    ContextGapsByArea,
    ContextGapsResponse,
)


# =============================================================================
# Phase 3: PM Review uses Smart Digest
# =============================================================================


class TestFormatKeyExcerpts:
    """Tests for _format_key_excerpts() function."""

    def test_empty_list_returns_none(self):
        """Test that empty list returns None (caller omits Key Excerpts section)."""
        result = _format_key_excerpts([])
        assert result is None

    def test_none_signals_caller_to_omit_section(self):
        """Test that None return signals caller to omit Key Excerpts section entirely."""
        # When no key_excerpts exist, returning None lets the caller
        # omit the "Key Excerpts" section entirely, avoiding LLM confusion
        result = _format_key_excerpts([])
        assert result is None

    def test_single_excerpt_with_relevance(self):
        """Test formatting single excerpt with relevance."""
        excerpts = [{"text": "User reported pin duplication", "relevance": "Shows symptom"}]
        result = _format_key_excerpts(excerpts)

        assert "1." in result
        assert "User reported pin duplication" in result
        assert "*Shows symptom*" in result

    def test_single_excerpt_without_relevance(self):
        """Test formatting single excerpt without relevance."""
        excerpts = [{"text": "User reported pin duplication", "relevance": ""}]
        result = _format_key_excerpts(excerpts)

        assert "1." in result
        assert "User reported pin duplication" in result
        # No asterisks for relevance when empty
        assert result.count("*") == 0

    def test_multiple_excerpts_numbered_correctly(self):
        """Test that multiple excerpts are numbered 1, 2, 3, etc."""
        excerpts = [
            {"text": "First excerpt", "relevance": "Reason 1"},
            {"text": "Second excerpt", "relevance": "Reason 2"},
            {"text": "Third excerpt", "relevance": "Reason 3"},
        ]
        result = _format_key_excerpts(excerpts)

        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "1." in lines[0]
        assert "2." in lines[1]
        assert "3." in lines[2]

    def test_limits_to_five_excerpts(self):
        """Test that only first 5 excerpts are included."""
        excerpts = [
            {"text": f"Excerpt {i}", "relevance": f"Reason {i}"}
            for i in range(1, 8)  # 7 excerpts
        ]
        result = _format_key_excerpts(excerpts)

        lines = result.strip().split("\n")
        assert len(lines) == 5
        assert "Excerpt 6" not in result
        assert "Excerpt 7" not in result

    def test_truncates_long_text_at_500_chars(self):
        """Test that long excerpt text is truncated at MAX_EXCERPT_TEXT_LENGTH (500) characters."""
        long_text = "A" * 600
        excerpts = [{"text": long_text, "relevance": "Test"}]
        result = _format_key_excerpts(excerpts)

        # Should not contain full 600 chars
        assert long_text not in result
        # Should contain truncated version (500 chars)
        assert "A" * 500 in result

    def test_handles_missing_text_field(self):
        """Test handling of excerpt missing 'text' field."""
        excerpts = [{"relevance": "Some relevance but no text"}]
        result = _format_key_excerpts(excerpts)

        # Should not crash, should show empty text
        assert "1." in result

    def test_handles_missing_relevance_field(self):
        """Test handling of excerpt missing 'relevance' field."""
        excerpts = [{"text": "Some text but no relevance"}]
        result = _format_key_excerpts(excerpts)

        assert "Some text but no relevance" in result
        # No relevance asterisks
        assert "*" not in result or result.count("*") == 0


class TestFormatConversationsForReview:
    """Tests for format_conversations_for_review() function."""

    def test_uses_smart_digest_when_diagnostic_summary_present(self):
        """Test that Smart Digest fields are used when diagnostic_summary is present."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Unable to publish pins",
                "symptoms": ["duplicate pins", "failed posts"],
                "affected_flow": "Pinterest publishing",
                "product_area": "publishing",
                "component": "pinterest",
                "diagnostic_summary": "User experiencing duplicate pins when scheduling to Pinterest",
                "key_excerpts": [
                    {"text": "Every pin appears twice", "relevance": "Core symptom"},
                ],
            }
        ]

        result = format_conversations_for_review(conversations)

        assert "**Diagnostic Summary**" in result
        assert "User experiencing duplicate pins" in result
        assert "**Key Excerpts**" in result
        assert "Every pin appears twice" in result
        # Should NOT contain excerpt fallback
        assert '**Excerpt**:' not in result

    def test_falls_back_to_excerpt_when_no_diagnostic_summary(self):
        """Test fallback to excerpt when diagnostic_summary is not present."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Unable to publish pins",
                "symptoms": ["duplicate pins"],
                "affected_flow": "Pinterest publishing",
                "product_area": "publishing",
                "component": "pinterest",
                "excerpt": "My pins are showing up twice on my board",
            }
        ]

        result = format_conversations_for_review(conversations)

        assert "**Excerpt**" in result
        assert "My pins are showing up twice" in result
        # Should NOT contain Smart Digest fields
        assert "**Diagnostic Summary**" not in result

    def test_falls_back_when_diagnostic_summary_is_empty_string(self):
        """Test fallback when diagnostic_summary is empty string."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Test intent",
                "symptoms": [],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "diagnostic_summary": "",  # Empty string
                "key_excerpts": [],
                "excerpt": "Fallback excerpt text",
            }
        ]

        result = format_conversations_for_review(conversations)

        assert "**Excerpt**" in result
        assert "Fallback excerpt text" in result

    def test_formats_multiple_conversations(self):
        """Test formatting multiple conversations with mixed formats."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Intent 1",
                "symptoms": ["symptom1"],
                "affected_flow": "flow1",
                "product_area": "area1",
                "component": "comp1",
                "diagnostic_summary": "Smart digest for conv 1",
                "key_excerpts": [{"text": "Excerpt 1", "relevance": "Rel 1"}],
            },
            {
                "conversation_id": "conv_2",
                "user_intent": "Intent 2",
                "symptoms": ["symptom2"],
                "affected_flow": "flow2",
                "product_area": "area2",
                "component": "comp2",
                "excerpt": "Old format excerpt for conv 2",
            },
        ]

        result = format_conversations_for_review(conversations)

        # First conversation uses Smart Digest
        assert "conv_1" in result
        assert "Smart digest for conv 1" in result

        # Second conversation uses excerpt fallback
        assert "conv_2" in result
        assert "Old format excerpt for conv 2" in result

    def test_symptoms_formatted_as_comma_separated(self):
        """Test that symptoms list is formatted as comma-separated string."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Test",
                "symptoms": ["duplicate pins", "failed posts", "timeout"],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "excerpt": "test",
            }
        ]

        result = format_conversations_for_review(conversations)

        assert "duplicate pins, failed posts, timeout" in result

    def test_handles_empty_symptoms_list(self):
        """Test handling of empty symptoms list."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Test",
                "symptoms": [],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "excerpt": "test",
            }
        ]

        result = format_conversations_for_review(conversations)

        assert "**Symptoms**: N/A" in result

    def test_handles_none_symptoms(self):
        """Test handling when symptoms is None."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Test",
                "symptoms": None,
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "excerpt": "test",
            }
        ]

        result = format_conversations_for_review(conversations)

        assert "**Symptoms**: N/A" in result

    def test_truncates_long_excerpt_at_500_chars(self):
        """Test that fallback excerpt is truncated at MAX_EXCERPT_TEXT_LENGTH (500) characters."""
        long_excerpt = "A" * 600
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Test",
                "symptoms": [],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "excerpt": long_excerpt,
            }
        ]

        result = format_conversations_for_review(conversations)

        # Full 600-char excerpt should not appear
        assert long_excerpt not in result
        # Should contain truncated version (500 chars)
        assert "A" * 500 in result

    def test_conversation_index_starts_at_1(self):
        """Test that conversation indices start at 1, not 0."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "First",
                "symptoms": [],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "excerpt": "test",
            },
            {
                "conversation_id": "conv_2",
                "user_intent": "Second",
                "symptoms": [],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "excerpt": "test",
            },
        ]

        result = format_conversations_for_review(conversations)

        assert "### Conversation 1" in result
        assert "### Conversation 2" in result
        assert "### Conversation 0" not in result


class TestConversationContextDataclass:
    """Tests for ConversationContext dataclass with Smart Digest fields."""

    def test_basic_initialization_without_smart_digest(self):
        """Test basic initialization without Smart Digest fields."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="flow",
            excerpt="test excerpt",
            product_area="area",
            component="comp",
        )

        assert ctx.conversation_id == "conv_1"
        assert ctx.diagnostic_summary == ""  # Default empty string
        assert ctx.key_excerpts == []  # Default empty list

    def test_initialization_with_smart_digest_fields(self):
        """Test initialization with diagnostic_summary and key_excerpts."""
        key_excerpts = [
            {"text": "User said X", "relevance": "Shows Y"},
            {"text": "User said Z", "relevance": "Shows W"},
        ]

        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="flow",
            excerpt="test excerpt",
            product_area="area",
            component="comp",
            diagnostic_summary="User is experiencing duplicate pins",
            key_excerpts=key_excerpts,
        )

        assert ctx.diagnostic_summary == "User is experiencing duplicate pins"
        assert len(ctx.key_excerpts) == 2
        assert ctx.key_excerpts[0]["text"] == "User said X"

    def test_post_init_converts_none_key_excerpts_to_empty_list(self):
        """Test that __post_init__ converts None key_excerpts to empty list."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="flow",
            excerpt="test excerpt",
            product_area="area",
            component="comp",
            key_excerpts=None,
        )

        assert ctx.key_excerpts == []
        assert isinstance(ctx.key_excerpts, list)


class TestConversationDataDataclass:
    """Tests for ConversationData dataclass with Smart Digest fields."""

    def test_basic_initialization_without_smart_digest(self):
        """Test basic initialization without Smart Digest fields."""
        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
        )

        assert data.id == "conv_1"
        assert data.diagnostic_summary is None
        assert data.key_excerpts == []

    def test_initialization_with_smart_digest_fields(self):
        """Test initialization with diagnostic_summary and key_excerpts."""
        key_excerpts = [
            {"text": "Excerpt 1", "relevance": "Why it matters"},
        ]

        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
            product_area="publishing",
            component="pinterest",
            user_intent="User wants to publish",
            symptoms=["duplicate pins"],
            affected_flow="Pinterest publishing",
            excerpt="Original excerpt",
            diagnostic_summary="User experiencing duplicate pins when scheduling",
            key_excerpts=key_excerpts,
        )

        assert data.diagnostic_summary == "User experiencing duplicate pins when scheduling"
        assert len(data.key_excerpts) == 1
        assert data.key_excerpts[0]["text"] == "Excerpt 1"

    def test_default_key_excerpts_is_empty_list(self):
        """Test that default key_excerpts is empty list, not None."""
        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
        )

        # Should be empty list, not None (due to field(default_factory=list))
        assert data.key_excerpts == []
        assert isinstance(data.key_excerpts, list)


# =============================================================================
# Phase 4: Context Gap Analysis
# =============================================================================


class TestContextGapItemSchema:
    """Tests for ContextGapItem Pydantic schema."""

    def test_basic_initialization(self):
        """Test basic ContextGapItem initialization."""
        item = ContextGapItem(text="Missing Pinterest API docs", count=15)

        assert item.text == "Missing Pinterest API docs"
        assert item.count == 15

    def test_serialization_to_dict(self):
        """Test serialization to dictionary."""
        item = ContextGapItem(text="Test gap", count=10)
        data = item.model_dump()

        assert data == {"text": "Test gap", "count": 10}

    def test_validation_requires_text(self):
        """Test that text field is required."""
        with pytest.raises(Exception):  # ValidationError
            ContextGapItem(count=10)

    def test_validation_requires_count(self):
        """Test that count field is required."""
        with pytest.raises(Exception):  # ValidationError
            ContextGapItem(text="Test")


class TestContextGapsByAreaSchema:
    """Tests for ContextGapsByArea Pydantic schema."""

    def test_basic_initialization(self):
        """Test basic ContextGapsByArea initialization."""
        gaps = [
            ContextGapItem(text="Gap 1", count=10),
            ContextGapItem(text="Gap 2", count=5),
        ]
        area = ContextGapsByArea(product_area="publishing", gaps=gaps)

        assert area.product_area == "publishing"
        assert len(area.gaps) == 2

    def test_empty_gaps_list(self):
        """Test with empty gaps list."""
        area = ContextGapsByArea(product_area="billing", gaps=[])

        assert area.product_area == "billing"
        assert area.gaps == []

    def test_default_gaps_is_empty_list(self):
        """Test that gaps defaults to empty list."""
        area = ContextGapsByArea(product_area="test")

        assert area.gaps == []


class TestContextGapsResponseSchema:
    """Tests for ContextGapsResponse Pydantic schema."""

    def test_minimal_initialization(self):
        """Test minimal initialization with required fields."""
        now = datetime.now(timezone.utc)
        response = ContextGapsResponse(
            period_start=now - timedelta(days=7),
            period_end=now,
        )

        assert response.total_extractions == 0
        assert response.extractions_with_gaps == 0
        assert response.top_gaps == []
        assert response.top_used == []
        assert response.recommendation is None

    def test_full_initialization(self):
        """Test full initialization with all fields."""
        now = datetime.now(timezone.utc)
        top_gaps = [
            ContextGapItem(text="Pinterest API rate limits", count=25),
            ContextGapItem(text="Scheduling timezone handling", count=15),
        ]
        top_used = [
            ContextGapItem(text="Tailwind codebase map", count=100),
        ]
        gaps_by_area = [
            ContextGapsByArea(
                product_area="publishing",
                gaps=[ContextGapItem(text="Pinterest limits", count=20)],
            ),
        ]

        response = ContextGapsResponse(
            period_start=now - timedelta(days=7),
            period_end=now,
            pipeline_run_id=123,
            total_extractions=500,
            extractions_with_gaps=150,
            extractions_with_context=400,
            top_gaps=top_gaps,
            top_used=top_used,
            gaps_by_product_area=gaps_by_area,
            recommendation='Add documentation for "Pinterest API rate limits" (25 occurrences)',
        )

        assert response.pipeline_run_id == 123
        assert response.total_extractions == 500
        assert response.extractions_with_gaps == 150
        assert len(response.top_gaps) == 2
        assert response.top_gaps[0].text == "Pinterest API rate limits"
        assert response.recommendation is not None

    def test_serialization_to_dict(self):
        """Test full serialization to dictionary."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)

        response = ContextGapsResponse(
            period_start=start,
            period_end=now,
            total_extractions=100,
            top_gaps=[ContextGapItem(text="Test gap", count=10)],
        )

        data = response.model_dump()

        assert "period_start" in data
        assert "period_end" in data
        assert data["total_extractions"] == 100
        assert len(data["top_gaps"]) == 1

    def test_optional_pipeline_run_id(self):
        """Test that pipeline_run_id is optional."""
        now = datetime.now(timezone.utc)
        response = ContextGapsResponse(
            period_start=now - timedelta(days=7),
            period_end=now,
        )

        assert response.pipeline_run_id is None


# =============================================================================
# Integration Tests - PM Review Service with Smart Digest
# =============================================================================


class TestPMReviewServiceSmartDigestIntegration:
    """Integration tests for PM Review Service using Smart Digest fields."""

    def test_format_conversations_uses_smart_digest_in_service(self):
        """Test that PMReviewService._format_conversations uses Smart Digest."""
        from story_tracking.services.pm_review_service import PMReviewService

        service = PMReviewService()

        conversations = [
            ConversationContext(
                conversation_id="conv_1",
                user_intent="Pins duplicating",
                symptoms=["duplicate pins"],
                affected_flow="Pinterest publishing",
                excerpt="Old excerpt that should not be used",
                product_area="publishing",
                component="pinterest",
                diagnostic_summary="User sees each pin appear twice after scheduling",
                key_excerpts=[
                    {"text": "Pin shows up twice", "relevance": "Core symptom"},
                ],
            ),
        ]

        formatted = service._format_conversations(conversations)

        # Should use Smart Digest
        assert "User sees each pin appear twice" in formatted
        assert "Pin shows up twice" in formatted
        # Should NOT use old excerpt
        assert "Old excerpt that should not be used" not in formatted

    def test_format_conversations_falls_back_to_excerpt(self):
        """Test that PMReviewService._format_conversations falls back to excerpt."""
        from story_tracking.services.pm_review_service import PMReviewService

        service = PMReviewService()

        conversations = [
            ConversationContext(
                conversation_id="conv_1",
                user_intent="Pins duplicating",
                symptoms=["duplicate pins"],
                affected_flow="Pinterest publishing",
                excerpt="This fallback excerpt should be used",
                product_area="publishing",
                component="pinterest",
                # No diagnostic_summary
            ),
        ]

        formatted = service._format_conversations(conversations)

        # Should use excerpt fallback
        assert "This fallback excerpt should be used" in formatted


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests for Smart Digest integration."""

    def test_key_excerpts_with_special_characters(self):
        """Test key_excerpts containing special characters."""
        excerpts = [
            {"text": 'User said: "This is broken!" & I agree', "relevance": "Quote with < > symbols"},
        ]
        result = _format_key_excerpts(excerpts)

        # Should handle special chars without crashing
        assert 'This is broken!' in result
        assert '&' in result

    def test_diagnostic_summary_with_newlines(self):
        """Test diagnostic_summary containing newlines."""
        conversations = [
            {
                "conversation_id": "conv_1",
                "user_intent": "Test",
                "symptoms": [],
                "affected_flow": "flow",
                "product_area": "area",
                "component": "comp",
                "diagnostic_summary": "Line 1\nLine 2\nLine 3",
                "key_excerpts": [],
            }
        ]

        result = format_conversations_for_review(conversations)

        # Should handle newlines
        assert "Line 1" in result

    def test_empty_conversations_list(self):
        """Test format_conversations_for_review with empty list."""
        result = format_conversations_for_review([])

        assert result == ""

    def test_conversation_with_all_fields_missing(self):
        """Test conversation dict with minimal fields."""
        conversations = [
            {
                "conversation_id": "conv_1",
            }
        ]

        # Should not crash - uses defaults
        result = format_conversations_for_review(conversations)

        assert "conv_1" in result
        assert "N/A" in result  # Default for missing fields

    def test_key_excerpts_empty_dict(self):
        """Test key_excerpts containing empty dict."""
        excerpts = [{}]
        result = _format_key_excerpts(excerpts)

        # Should handle gracefully
        assert "1." in result
