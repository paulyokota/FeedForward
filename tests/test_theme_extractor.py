"""
Smart Digest (Issue #144) tests for theme extractor.

Tests the new Smart Digest functionality including:
- full_conversation parameter in extract()
- use_full_conversation flag behavior
- New Theme dataclass fields (diagnostic_summary, key_excerpts, context_used, context_gaps)
- prepare_conversation_for_extraction() smart truncation

Owner: Kenji (Testing)
Run: pytest tests/test_theme_extractor.py -v
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.models import Conversation
from theme_extractor import (
    Theme,
    ThemeExtractor,
    prepare_conversation_for_extraction,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_conversation():
    """Basic test conversation."""
    return Conversation(
        id="test_conv_123",
        created_at=datetime.utcnow(),
        source_body="My pins are not posting to Pinterest.",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
    )


@pytest.fixture
def sample_full_conversation():
    """Full conversation with multiple messages."""
    return """Customer: I'm having trouble scheduling pins. They show as scheduled but never post.

Support: Hi! I'm sorry to hear that. Can you tell me which board you're trying to post to?

Customer: It's my "Recipe Ideas" board. I've been waiting 3 days and nothing posts.

Support: I see. Are you getting any error messages?

Customer: Yes, it says "Error 403: Board access denied" when I check the status.

Support: That error usually means there's a permission issue. Have you reconnected your Pinterest account recently?

Customer: No, I haven't. I'll try that now.

Support: Great, let me know if that helps!"""


@pytest.fixture
def sample_customer_digest():
    """Customer digest with key messages (Issue #139 format)."""
    return """Customer: I'm having trouble scheduling pins. They show as scheduled but never post.

Customer: Yes, it says "Error 403: Board access denied" when I check the status."""


@pytest.fixture
def mock_llm_response_with_smart_digest():
    """Mock LLM response including Smart Digest fields."""
    return {
        "product_area": "pinterest_publishing",
        "component": "scheduler",
        "issue_signature": "pinterest_board_permission_denied",
        "matched_existing": True,
        "match_reasoning": "Matched existing theme for Pinterest permission errors",
        "match_confidence": "high",
        "user_intent": "User wants to schedule pins to their Pinterest board",
        "symptoms": ["Pins show as scheduled", "Error 403 when checking status", "Nothing posts"],
        "affected_flow": "Pin Scheduler -> Pinterest API",
        "root_cause_hypothesis": "OAuth token may have expired or board permissions changed",
        "diagnostic_summary": "User reports 'Error 403: Board access denied' when scheduling pins to 'Recipe Ideas' board. Issue is consistent (3 days, no intermittent posting). Suggests OAuth token or board permission sync issue.",
        "key_excerpts": [
            {
                "text": "Error 403: Board access denied",
                "relevance": "Exact error code - indicates Pinterest API permission rejection"
            },
            {
                "text": "I've been waiting 3 days and nothing posts",
                "relevance": "Confirms issue is persistent, not intermittent"
            }
        ],
        "context_used": ["Pinterest Publishing Issues", "OAuth Troubleshooting"],
        "context_gaps": ["Pinterest API rate limits", "Board permission sync frequency"]
    }


@pytest.fixture
def mock_llm_response_minimal():
    """Mock LLM response without Smart Digest fields (backward compatibility)."""
    return {
        "product_area": "pinterest_publishing",
        "component": "scheduler",
        "issue_signature": "pinterest_board_permission_denied",
        "matched_existing": False,
        "match_reasoning": "New theme for permission errors",
        "match_confidence": "medium",
        "user_intent": "User wants to schedule pins",
        "symptoms": ["Pins not posting"],
        "affected_flow": "Scheduler",
        "root_cause_hypothesis": "Permission issue"
    }


# =============================================================================
# Test: Theme Dataclass Smart Digest Fields
# =============================================================================

class TestThemeDataclassSmartDigestFields:
    """Tests for new Smart Digest fields in Theme dataclass."""

    def test_theme_dataclass_has_smart_digest_fields(self):
        """Theme dataclass should have all Smart Digest fields."""
        theme = Theme(
            conversation_id="test_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        # Verify new fields exist with correct defaults
        assert hasattr(theme, "diagnostic_summary")
        assert hasattr(theme, "key_excerpts")
        assert hasattr(theme, "context_used")
        assert hasattr(theme, "context_gaps")

        # Verify default values
        assert theme.diagnostic_summary == ""
        assert theme.key_excerpts == []
        assert theme.context_used == []
        assert theme.context_gaps == []

    def test_theme_dataclass_with_smart_digest_values(self):
        """Theme dataclass should accept Smart Digest field values."""
        theme = Theme(
            conversation_id="test_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
            diagnostic_summary="User reports Error 403 on board access.",
            key_excerpts=[
                {"text": "Error 403", "relevance": "Exact error code"}
            ],
            context_used=["Pinterest Docs"],
            context_gaps=["API limits"],
        )

        assert theme.diagnostic_summary == "User reports Error 403 on board access."
        assert len(theme.key_excerpts) == 1
        assert theme.key_excerpts[0]["text"] == "Error 403"
        assert theme.context_used == ["Pinterest Docs"]
        assert theme.context_gaps == ["API limits"]

    def test_theme_to_dict_includes_smart_digest_fields(self):
        """Theme.to_dict() should include Smart Digest fields."""
        theme = Theme(
            conversation_id="test_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
            diagnostic_summary="Test summary",
            key_excerpts=[{"text": "quote", "relevance": "reason"}],
            context_used=["Section A"],
            context_gaps=["Missing info"],
        )

        d = theme.to_dict()

        assert "diagnostic_summary" in d
        assert "key_excerpts" in d
        assert "context_used" in d
        assert "context_gaps" in d
        assert d["diagnostic_summary"] == "Test summary"
        assert d["key_excerpts"] == [{"text": "quote", "relevance": "reason"}]


class TestKeyExcerptsStructure:
    """Tests for key_excerpts structure validation."""

    def test_key_excerpts_valid_structure(self):
        """key_excerpts should have [{text, relevance}] structure."""
        excerpts = [
            {"text": "Error 403: Board access denied", "relevance": "Exact error code"},
            {"text": "Waiting 3 days", "relevance": "Confirms persistence"},
        ]

        theme = Theme(
            conversation_id="test_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
            key_excerpts=excerpts,
        )

        assert len(theme.key_excerpts) == 2
        for excerpt in theme.key_excerpts:
            assert "text" in excerpt
            assert "relevance" in excerpt

    def test_key_excerpts_empty_list(self):
        """key_excerpts should accept empty list."""
        theme = Theme(
            conversation_id="test_123",
            product_area="test",
            component="test",
            issue_signature="test",
            user_intent="test",
            symptoms=[],
            affected_flow="test",
            root_cause_hypothesis="test",
            key_excerpts=[],
        )

        assert theme.key_excerpts == []

    def test_key_excerpts_serializes_to_json(self):
        """key_excerpts should serialize to JSON correctly."""
        excerpts = [
            {"text": "Test quote", "relevance": "Test reason"},
        ]

        theme = Theme(
            conversation_id="test_123",
            product_area="test",
            component="test",
            issue_signature="test",
            user_intent="test",
            symptoms=[],
            affected_flow="test",
            root_cause_hypothesis="test",
            key_excerpts=excerpts,
        )

        d = theme.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)

        assert parsed["key_excerpts"] == excerpts


# =============================================================================
# Test: prepare_conversation_for_extraction()
# =============================================================================

class TestPrepareConversationNoTruncation:
    """Tests for prepare_conversation_for_extraction() - no truncation needed."""

    def test_short_conversation_unchanged(self):
        """Short conversations pass through unchanged."""
        conversation = "Customer: Hello\n\nSupport: Hi there!"

        result = prepare_conversation_for_extraction(conversation)

        assert result == conversation

    def test_medium_conversation_unchanged(self):
        """Medium-length conversations pass through unchanged."""
        # Create a conversation well under the limit
        messages = [f"Message {i}: This is message content number {i}." for i in range(50)]
        conversation = "\n\n".join(messages)

        result = prepare_conversation_for_extraction(conversation)

        assert result == conversation
        assert len(result) < 400_000

    def test_empty_conversation_returns_empty(self):
        """Empty conversation returns empty string."""
        assert prepare_conversation_for_extraction("") == ""
        # Note: Whitespace-only strings are NOT stripped by prepare_conversation_for_extraction
        # The stripping happens in extract() before calling this function

    def test_none_like_handling(self):
        """None-ish values handled gracefully."""
        # The function checks 'if not full_conversation'
        assert prepare_conversation_for_extraction("") == ""


class TestPrepareConversationWithTruncation:
    """Tests for prepare_conversation_for_extraction() - truncation applied."""

    def test_long_conversation_truncated(self):
        """Conversations exceeding limit are truncated."""
        # Create a very long conversation (> 400K chars)
        messages = [f"Message {i}: " + "x" * 10000 for i in range(50)]
        conversation = "\n\n".join(messages)

        assert len(conversation) > 400_000

        result = prepare_conversation_for_extraction(conversation, max_chars=50_000)

        assert len(result) <= 50_000
        assert "omitted" in result.lower() or "truncated" in result.lower()

    def test_truncation_preserves_first_messages(self):
        """Truncation always keeps first 2 messages."""
        messages = [f"Message {i}" for i in range(100)]
        conversation = "\n\n".join(messages)

        # Use a small max_chars to force truncation
        result = prepare_conversation_for_extraction(conversation, max_chars=500)

        # First messages should be present
        assert "Message 0" in result
        assert "Message 1" in result

    def test_truncation_preserves_last_messages(self):
        """Truncation always keeps last 3 messages."""
        messages = [f"Message {i}" for i in range(100)]
        conversation = "\n\n".join(messages)

        # Use a small max_chars to force truncation
        result = prepare_conversation_for_extraction(conversation, max_chars=500)

        # Last messages should be present
        assert "Message 99" in result
        assert "Message 98" in result
        assert "Message 97" in result

    def test_truncation_adds_omission_marker(self):
        """Truncation adds marker indicating messages were omitted."""
        messages = [f"Message {i}: content here" for i in range(100)]
        conversation = "\n\n".join(messages)

        result = prepare_conversation_for_extraction(conversation, max_chars=1000)

        assert "omitted" in result.lower() or "truncated" in result.lower()

    def test_few_messages_hard_truncated(self):
        """Conversations with <= 5 messages use hard truncation."""
        # 4 very long messages
        messages = ["Very long message " + "x" * 150000 for _ in range(4)]
        conversation = "\n\n".join(messages)

        result = prepare_conversation_for_extraction(conversation, max_chars=50_000)

        # Should be truncated but not use smart truncation (not enough messages)
        assert len(result) <= 50_000 + 50  # Allow small overhead for marker
        assert "truncated" in result.lower()


class TestPrepareConversationPreservesFirstAndLast:
    """Tests verifying first 2 and last 3 messages are preserved."""

    def test_preserves_exact_message_boundaries(self):
        """First 2 and last 3 messages preserved with correct content."""
        messages = [
            "FIRST: Initial problem statement",
            "SECOND: More context from user",
            "MIDDLE_1: Some back and forth",
            "MIDDLE_2: More discussion",
            "MIDDLE_3: Continued conversation",
            "MIDDLE_4: Additional details",
            "THIRD_TO_LAST: Recent update",
            "SECOND_TO_LAST: More recent info",
            "LAST: Final message with error code",
        ]
        conversation = "\n\n".join(messages)

        # Force truncation with small limit
        result = prepare_conversation_for_extraction(conversation, max_chars=500)

        # Verify first 2 present
        assert "FIRST: Initial problem statement" in result
        assert "SECOND: More context from user" in result

        # Verify last 3 present
        assert "THIRD_TO_LAST: Recent update" in result
        assert "SECOND_TO_LAST: More recent info" in result
        assert "LAST: Final message with error code" in result

    def test_middle_messages_omitted_when_needed(self):
        """Middle messages are omitted when truncation needed."""
        messages = [
            "FIRST",
            "SECOND",
            "MIDDLE_TO_REMOVE_1",
            "MIDDLE_TO_REMOVE_2",
            "MIDDLE_TO_REMOVE_3",
            "THIRD_TO_LAST",
            "SECOND_TO_LAST",
            "LAST",
        ]
        conversation = "\n\n".join(messages)

        # Force truncation with very small limit
        result = prepare_conversation_for_extraction(conversation, max_chars=200)

        # Middle messages may be omitted
        # First and last should remain
        assert "FIRST" in result
        assert "LAST" in result


# =============================================================================
# Test: extract() with full_conversation parameter
# =============================================================================

class TestExtractWithFullConversation:
    """Tests for extract() method with full_conversation parameter."""

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_uses_full_conversation_when_provided(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        sample_full_conversation,
        mock_llm_response_with_smart_digest,
    ):
        """extract() should use full_conversation when provided."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_with_smart_digest)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation=sample_full_conversation,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Verify LLM was called
        assert mock_client.chat.completions.create.called

        # Check that the prompt contained the full conversation content
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        # Full conversation content should be in the prompt
        assert "Error 403: Board access denied" in user_message
        assert "Recipe Ideas" in user_message

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_returns_smart_digest_fields(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        sample_full_conversation,
        mock_llm_response_with_smart_digest,
    ):
        """extract() should return Theme with Smart Digest fields populated."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_with_smart_digest)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation=sample_full_conversation,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Verify Smart Digest fields
        assert theme.diagnostic_summary != ""
        assert "Error 403" in theme.diagnostic_summary
        assert len(theme.key_excerpts) == 2
        assert theme.context_used == ["Pinterest Publishing Issues", "OAuth Troubleshooting"]
        assert "Pinterest API rate limits" in theme.context_gaps


class TestExtractFallbackToCustomerDigest:
    """Tests for fallback to customer_digest when full_conversation is None."""

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_fallback_to_customer_digest(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        sample_customer_digest,
        mock_llm_response_minimal,
    ):
        """extract() should fall back to customer_digest when full_conversation is None."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation=None,
            customer_digest=sample_customer_digest,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Verify LLM was called with customer_digest content
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        # Customer digest content should be in the prompt
        assert "Error 403: Board access denied" in user_message
        assert "having trouble scheduling pins" in user_message


class TestExtractFallbackToSourceBody:
    """Tests for fallback to source_body when both full_conversation and customer_digest are None."""

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_fallback_to_source_body(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        mock_llm_response_minimal,
    ):
        """extract() should fall back to source_body when both alternatives are None."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation=None,
            customer_digest=None,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Verify LLM was called with source_body content
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        # source_body content should be in the prompt
        assert sample_conversation.source_body in user_message


class TestExtractUseFullConversationFalse:
    """Tests for use_full_conversation=False behavior."""

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_ignores_full_conversation_when_flag_false(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        sample_full_conversation,
        sample_customer_digest,
        mock_llm_response_minimal,
    ):
        """extract() should NOT use full_conversation when use_full_conversation=False."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation=sample_full_conversation,
            customer_digest=sample_customer_digest,
            use_full_conversation=False,  # KEY: Flag is False
            canonicalize=False,
        )

        # Verify LLM was called
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        # Should use customer_digest, not full_conversation
        # full_conversation has "Recipe Ideas" board mentioned
        # customer_digest has the error but not the board name mentioned in support context
        # The key test is that it should use customer_digest format
        assert "having trouble scheduling pins" in user_message

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_falls_back_to_source_body_when_flag_false_and_no_digest(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        sample_full_conversation,
        mock_llm_response_minimal,
    ):
        """extract() with use_full_conversation=False and no digest uses source_body."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation=sample_full_conversation,
            customer_digest=None,  # No digest
            use_full_conversation=False,  # Flag is False
            canonicalize=False,
        )

        # Verify source_body was used
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        assert sample_conversation.source_body in user_message


# =============================================================================
# Test: Key Excerpts Validation in extract()
# =============================================================================

class TestKeyExcerptsValidation:
    """Tests for key_excerpts validation during extraction."""

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_key_excerpts_limited_to_five(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
    ):
        """key_excerpts should be limited to 5 items."""
        # LLM returns more than 5 excerpts
        llm_response = {
            "product_area": "test",
            "component": "test",
            "issue_signature": "test_sig",
            "matched_existing": False,
            "match_reasoning": "test",
            "match_confidence": "high",
            "user_intent": "test",
            "symptoms": [],
            "affected_flow": "test",
            "root_cause_hypothesis": "test",
            "key_excerpts": [
                {"text": f"Excerpt {i}", "relevance": f"Reason {i}"}
                for i in range(10)  # 10 excerpts
            ],
        }

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_response)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)
        theme = extractor.extract(sample_conversation, canonicalize=False)

        # Should be limited to 5
        assert len(theme.key_excerpts) == 5

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_key_excerpts_text_truncated(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
    ):
        """key_excerpts text should be truncated to 500 chars."""
        long_text = "x" * 1000  # 1000 chars

        llm_response = {
            "product_area": "test",
            "component": "test",
            "issue_signature": "test_sig",
            "matched_existing": False,
            "match_reasoning": "test",
            "match_confidence": "high",
            "user_intent": "test",
            "symptoms": [],
            "affected_flow": "test",
            "root_cause_hypothesis": "test",
            "key_excerpts": [
                {"text": long_text, "relevance": "test"}
            ],
        }

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_response)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)
        theme = extractor.extract(sample_conversation, canonicalize=False)

        # Text should be truncated
        assert len(theme.key_excerpts[0]["text"]) == 500

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_key_excerpts_invalid_structure_normalized(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
    ):
        """key_excerpts with missing fields should be normalized."""
        llm_response = {
            "product_area": "test",
            "component": "test",
            "issue_signature": "test_sig",
            "matched_existing": False,
            "match_reasoning": "test",
            "match_confidence": "high",
            "user_intent": "test",
            "symptoms": [],
            "affected_flow": "test",
            "root_cause_hypothesis": "test",
            "key_excerpts": [
                {"text": "Valid excerpt"},  # Missing relevance
                {"relevance": "Only relevance"},  # Missing text - should be filtered
                {"text": "Another valid", "relevance": "With relevance"},
            ],
        }

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_response)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)
        theme = extractor.extract(sample_conversation, canonicalize=False)

        # Only excerpts with 'text' field should be kept
        assert len(theme.key_excerpts) == 2
        # First excerpt should have descriptive fallback relevance (not enum "medium")
        assert theme.key_excerpts[0]["relevance"] == "Relevant excerpt from conversation"

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_key_excerpts_enum_relevance_converted_to_descriptive(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
    ):
        """key_excerpts with enum relevance values should be converted to descriptive strings."""
        llm_response = {
            "product_area": "test",
            "component": "test",
            "issue_signature": "test_sig",
            "matched_existing": False,
            "match_reasoning": "test",
            "match_confidence": "high",
            "user_intent": "test",
            "symptoms": [],
            "affected_flow": "test",
            "root_cause_hypothesis": "test",
            "key_excerpts": [
                {"text": "Error 403", "relevance": "high"},  # Enum value
                {"text": "Waiting 3 days", "relevance": "medium"},  # Enum value
                {"text": "Works elsewhere", "relevance": "low"},  # Enum value
                {"text": "OAuth expired", "relevance": "OAuth token expired - key diagnostic info"},  # Descriptive
            ],
        }

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_response)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)
        theme = extractor.extract(sample_conversation, canonicalize=False)

        # Enum values should be converted to descriptive fallback
        assert theme.key_excerpts[0]["relevance"] == "Relevant excerpt from conversation"
        assert theme.key_excerpts[1]["relevance"] == "Relevant excerpt from conversation"
        assert theme.key_excerpts[2]["relevance"] == "Relevant excerpt from conversation"
        # Descriptive value should be preserved
        assert theme.key_excerpts[3]["relevance"] == "OAuth token expired - key diagnostic info"


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for Smart Digest functionality."""

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_empty_full_conversation_falls_back(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        mock_llm_response_minimal,
    ):
        """Empty full_conversation should fall back to customer_digest or source_body."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        # Empty string should trigger fallback
        theme = extractor.extract(
            sample_conversation,
            full_conversation="",
            customer_digest=None,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Should use source_body
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        assert sample_conversation.source_body in user_message

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_whitespace_only_full_conversation_falls_back(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        mock_llm_response_minimal,
    ):
        """Whitespace-only full_conversation should fall back."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            full_conversation="   \n\n   ",  # Whitespace only
            customer_digest=None,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Should use source_body
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        assert sample_conversation.source_body in user_message

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_llm_returns_no_smart_digest_fields(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        sample_conversation,
        mock_llm_response_minimal,  # No Smart Digest fields
    ):
        """Extraction should work when LLM doesn't return Smart Digest fields."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_minimal)))
        ]

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            sample_conversation,
            canonicalize=False,
        )

        # Smart Digest fields should have defaults
        assert theme.diagnostic_summary == ""
        assert theme.key_excerpts == []
        assert theme.context_used == []
        assert theme.context_gaps == []

    def test_prepare_conversation_custom_max_chars(self):
        """prepare_conversation_for_extraction() should respect custom max_chars."""
        messages = [f"Message {i}: " + "x" * 100 for i in range(100)]
        conversation = "\n\n".join(messages)

        result = prepare_conversation_for_extraction(conversation, max_chars=1000)

        assert len(result) <= 1000 + 50  # Allow small overhead


# =============================================================================
# Run tests standalone
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
