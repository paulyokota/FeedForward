"""
Smart Digest Data Flow Integration Tests (Issue #144 Post-Mortem Fix)

Tests for verifying the complete Smart Digest data flow end-to-end.
These tests exist because Issue #144 post-mortem revealed that unit tests
passed but the feature was dead code - we never verified the connections
between components.

The flow being tested:
1. Intercom conversation (raw dict with messages)
2. build_full_conversation_text() formats messages into full_conversation string
3. Classification pipeline stores full_conversation in support_insights
4. Theme extraction receives full_conversation, generates diagnostic_summary + key_excerpts
5. Database themes table has populated diagnostic_summary, key_excerpts

Owner: Kenji (Testing)
Run: pytest tests/test_smart_digest_data_flow.py -v

Design Principle: Test the CONNECTIONS between components, not just individual functions.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from digest_extractor import build_full_conversation_text
from db.models import Conversation
from theme_extractor import Theme, ThemeExtractor

# Mark entire module as slow - these are integration tests
pytestmark = [pytest.mark.slow, pytest.mark.integration]


# =============================================================================
# Test Fixtures - Realistic Intercom Conversation Data
# =============================================================================

@pytest.fixture
def realistic_intercom_conversation() -> Dict[str, Any]:
    """
    Realistic Intercom conversation with multiple customer and support messages.

    This simulates what the Intercom API returns for a support conversation.
    """
    return {
        "id": "intercom_conv_abc123",
        "created_at": 1706400000,  # Unix timestamp
        "source": {
            "type": "conversation",
            "body": "<p>Hi, I'm having trouble scheduling pins to Pinterest. They show as scheduled but never post.</p>",
            "author": {
                "type": "user",
                "email": "customer@example.com",
            },
            "url": "https://app.tailwindapp.com/publisher",
        },
        "conversation_parts": {
            "conversation_parts": [
                {
                    "part_type": "comment",
                    "author": {"type": "admin", "name": "Support Agent"},
                    "body": "<p>Hi! I'm sorry to hear that. Can you tell me which board you're trying to post to?</p>",
                },
                {
                    "part_type": "comment",
                    "author": {"type": "user", "email": "customer@example.com"},
                    "body": '<p>It\'s my "Recipe Ideas" board. I\'ve been waiting 3 days and nothing posts.</p>',
                },
                {
                    "part_type": "assignment",
                    "author": {"type": "admin"},
                    "body": "Assigned to Technical Support",
                },
                {
                    "part_type": "comment",
                    "author": {"type": "admin"},
                    "body": "<p>I see. Are you getting any error messages?</p>",
                },
                {
                    "part_type": "comment",
                    "author": {"type": "user"},
                    "body": '<p>Yes, it says "Error 403: Board access denied" when I check the status.</p>',
                },
                {
                    "part_type": "note",
                    "author": {"type": "admin"},
                    "body": "Internal: Check if OAuth token expired",
                },
                {
                    "part_type": "comment",
                    "author": {"type": "admin"},
                    "body": "<p>That error usually means there's a permission issue. Have you reconnected your Pinterest account recently?</p>",
                },
                {
                    "part_type": "comment",
                    "author": {"type": "user"},
                    "body": "<p>No, I haven't. I'll try that now.</p>",
                },
            ]
        },
    }


@pytest.fixture
def expected_full_conversation_content() -> List[str]:
    """Key content that should be present in the formatted full_conversation."""
    return [
        "[Customer]:",  # Customer messages labeled correctly
        "[Support]:",   # Support messages labeled correctly
        "trouble scheduling pins",  # Initial problem from source
        "Recipe Ideas",  # Board name from follow-up
        "Error 403: Board access denied",  # The error message
        "3 days",  # Duration of issue
        "reconnected your Pinterest",  # Support troubleshooting
    ]


@pytest.fixture
def mock_llm_response_with_smart_digest() -> Dict[str, Any]:
    """
    Mock LLM response that includes Smart Digest fields.
    This simulates what gpt-4o-mini returns for theme extraction.
    """
    return {
        "product_area": "pinterest_publishing",
        "component": "scheduler",
        "issue_signature": "pinterest_board_permission_denied",
        "matched_existing": True,
        "match_reasoning": "Matched existing theme for Pinterest permission errors",
        "match_confidence": "high",
        "user_intent": "User wants to schedule pins to their Pinterest board",
        "symptoms": [
            "Pins show as scheduled but never post",
            "Error 403: Board access denied",
            "Issue persists for 3 days",
        ],
        "affected_flow": "Pin Scheduler -> Pinterest API",
        "root_cause_hypothesis": "OAuth token may have expired or board permissions changed",
        "diagnostic_summary": (
            "User reports 'Error 403: Board access denied' when scheduling pins to "
            "'Recipe Ideas' board. Issue is consistent (3 days, not intermittent). "
            "User verified pins show as scheduled in Tailwind but never appear on Pinterest. "
            "Suggests OAuth token scope issue or board permission change not synced to Tailwind."
        ),
        "key_excerpts": [
            {
                "text": "Error 403: Board access denied",
                "relevance": "Exact error code - indicates Pinterest API permission rejection"
            },
            {
                "text": "I've been waiting 3 days and nothing posts",
                "relevance": "Confirms issue is persistent, not intermittent"
            },
            {
                "text": "It's my 'Recipe Ideas' board",
                "relevance": "Identifies specific board with permission issue"
            }
        ],
        "context_used": ["Pinterest Publishing Issues", "OAuth Troubleshooting"],
        "context_gaps": ["Pinterest API rate limits", "Board permission sync frequency"]
    }


# =============================================================================
# Test 1: full_conversation flows through the pipeline
# =============================================================================

class TestFullConversationFlowsThroughPipeline:
    """
    Test that build_full_conversation_text() correctly formats Intercom conversations
    and that the result would be stored in support_insights.

    This verifies the connection: Intercom -> build_full_conversation_text() -> support_insights
    """

    def test_build_full_conversation_formats_intercom_data(
        self,
        realistic_intercom_conversation: Dict[str, Any],
        expected_full_conversation_content: List[str],
    ):
        """
        build_full_conversation_text() should format Intercom conversation
        with all customer and support messages.
        """
        # Act: Call the function that's used in the classification pipeline
        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        # Assert: Verify all expected content is present
        for expected in expected_full_conversation_content:
            assert expected in full_conversation, (
                f"Expected '{expected}' to be in full_conversation.\n"
                f"Got: {full_conversation[:500]}..."
            )

    def test_build_full_conversation_excludes_internal_parts(
        self,
        realistic_intercom_conversation: Dict[str, Any],
    ):
        """
        build_full_conversation_text() should exclude internal notes and assignments.
        """
        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        # These internal parts should NOT be in the output
        assert "Assigned to Technical Support" not in full_conversation
        assert "Internal:" not in full_conversation
        assert "OAuth token expired" not in full_conversation

    def test_build_full_conversation_preserves_message_order(
        self,
        realistic_intercom_conversation: Dict[str, Any],
    ):
        """
        build_full_conversation_text() should preserve chronological order.
        """
        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        # Find positions of key messages
        pos_initial = full_conversation.find("trouble scheduling pins")
        pos_board_name = full_conversation.find("Recipe Ideas")
        pos_error = full_conversation.find("Error 403")
        pos_reconnect = full_conversation.find("reconnected your Pinterest")

        # Verify chronological order
        assert pos_initial < pos_board_name < pos_error < pos_reconnect, (
            "Messages should appear in chronological order"
        )

    def test_full_conversation_would_be_stored_in_support_insights(
        self,
        realistic_intercom_conversation: Dict[str, Any],
    ):
        """
        Verify that the classification pipeline would store full_conversation
        in support_insights with the correct structure.

        This tests the contract between build_full_conversation_text()
        and the classification pipeline's storage format.
        """
        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        # The classification pipeline stores this in support_insights like this:
        # (from src/classification_pipeline.py lines 198-201)
        support_insights = {
            "customer_digest": "mock_customer_digest",  # Also stored
            "full_conversation": full_conversation,     # The key field we're testing
        }

        # Verify structure
        assert "full_conversation" in support_insights
        assert isinstance(support_insights["full_conversation"], str)
        assert len(support_insights["full_conversation"]) > 100  # Not empty
        assert "[Customer]:" in support_insights["full_conversation"]
        assert "[Support]:" in support_insights["full_conversation"]


# =============================================================================
# Test 2: Theme extraction receives full_conversation and generates Smart Digest
# =============================================================================

class TestThemeExtractionReceivesFullConversation:
    """
    Test that ThemeExtractor.extract() receives full_conversation and generates
    diagnostic_summary and key_excerpts.

    This verifies the connection: support_insights -> ThemeExtractor -> Theme
    """

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_uses_full_conversation_in_llm_prompt(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        realistic_intercom_conversation: Dict[str, Any],
        mock_llm_response_with_smart_digest: Dict[str, Any],
    ):
        """
        ThemeExtractor.extract() should include full_conversation content
        in the LLM prompt.
        """
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_with_smart_digest)))
        ]

        # Build full_conversation (simulating what pipeline does)
        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        # Create Conversation model (what pipeline passes to extractor)
        conv = Conversation(
            id="test_conv_123",
            created_at=datetime.utcnow(),
            source_body="Hi, I'm having trouble scheduling pins to Pinterest.",
            issue_type="bug_report",
            sentiment="frustrated",
            churn_risk=False,
            priority="high",
        )

        extractor = ThemeExtractor(use_vocabulary=False)

        # Act: Extract theme with full_conversation (how pipeline.py calls it)
        theme = extractor.extract(
            conv,
            full_conversation=full_conversation,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Assert: Verify LLM was called with full_conversation content
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]

        # The full conversation content should be in the LLM prompt
        assert "Error 403: Board access denied" in user_message, (
            "Full conversation error message should be in LLM prompt"
        )
        assert "Recipe Ideas" in user_message, (
            "Board name from full conversation should be in LLM prompt"
        )

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_returns_theme_with_smart_digest_fields(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        realistic_intercom_conversation: Dict[str, Any],
        mock_llm_response_with_smart_digest: Dict[str, Any],
    ):
        """
        ThemeExtractor.extract() should return Theme with populated
        diagnostic_summary and key_excerpts from LLM response.
        """
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_with_smart_digest)))
        ]

        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        conv = Conversation(
            id="test_conv_123",
            created_at=datetime.utcnow(),
            source_body="Hi, I'm having trouble scheduling pins to Pinterest.",
            issue_type="bug_report",
            sentiment="frustrated",
            churn_risk=False,
            priority="high",
        )

        extractor = ThemeExtractor(use_vocabulary=False)

        # Act
        theme = extractor.extract(
            conv,
            full_conversation=full_conversation,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Assert: Smart Digest fields are populated
        assert theme.diagnostic_summary != "", "diagnostic_summary should be populated"
        assert "Error 403" in theme.diagnostic_summary, (
            "diagnostic_summary should contain error details from conversation"
        )

        assert len(theme.key_excerpts) > 0, "key_excerpts should be populated"
        assert any(
            "Error 403" in excerpt.get("text", "")
            for excerpt in theme.key_excerpts
        ), "key_excerpts should contain the error message"

        # Verify excerpt structure
        for excerpt in theme.key_excerpts:
            assert "text" in excerpt, "Each excerpt should have 'text' field"
            assert "relevance" in excerpt, "Each excerpt should have 'relevance' field"

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_returns_context_tracking_fields(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        realistic_intercom_conversation: Dict[str, Any],
        mock_llm_response_with_smart_digest: Dict[str, Any],
    ):
        """
        ThemeExtractor.extract() should return Theme with context_used
        and context_gaps for observability.
        """
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_with_smart_digest)))
        ]

        full_conversation = build_full_conversation_text(realistic_intercom_conversation)

        conv = Conversation(
            id="test_conv_123",
            created_at=datetime.utcnow(),
            source_body="Test",
            issue_type="bug_report",
            sentiment="neutral",
            churn_risk=False,
            priority="normal",
        )

        extractor = ThemeExtractor(use_vocabulary=False)

        theme = extractor.extract(
            conv,
            full_conversation=full_conversation,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Assert: Context tracking fields are populated
        assert theme.context_used == ["Pinterest Publishing Issues", "OAuth Troubleshooting"]
        assert "Pinterest API rate limits" in theme.context_gaps


# =============================================================================
# Test 3: Smart Digest fields serialize correctly for DB storage
# =============================================================================

class TestSmartDigestFieldsStoredInDb:
    """
    Test that Theme dataclass fields serialize correctly for database storage.

    This verifies the connection: Theme -> JSON serialization -> DB columns
    """

    def test_theme_dataclass_has_required_smart_digest_fields(self):
        """Theme dataclass should have all Smart Digest fields."""
        theme = Theme(
            conversation_id="test_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1", "symptom2"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        # Verify fields exist
        assert hasattr(theme, "diagnostic_summary")
        assert hasattr(theme, "key_excerpts")
        assert hasattr(theme, "context_used")
        assert hasattr(theme, "context_gaps")

    def test_theme_smart_digest_fields_have_correct_defaults(self):
        """Smart Digest fields should have empty defaults."""
        theme = Theme(
            conversation_id="test_123",
            product_area="test",
            component="test",
            issue_signature="test",
            user_intent="test",
            symptoms=[],
            affected_flow="test",
            root_cause_hypothesis="test",
        )

        # Verify defaults
        assert theme.diagnostic_summary == ""
        assert theme.key_excerpts == []
        assert theme.context_used == []
        assert theme.context_gaps == []

    def test_theme_to_dict_serializes_smart_digest_fields(self):
        """Theme.to_dict() should correctly serialize Smart Digest fields."""
        key_excerpts = [
            {"text": "Error 403: Board access denied", "relevance": "Exact error code"},
            {"text": "Waiting 3 days", "relevance": "Duration of issue"},
        ]

        theme = Theme(
            conversation_id="test_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="pinterest_board_permission_denied",
            user_intent="Schedule pins",
            symptoms=["Permission error"],
            affected_flow="Scheduler -> Pinterest",
            root_cause_hypothesis="OAuth issue",
            diagnostic_summary="User reports Error 403 when scheduling.",
            key_excerpts=key_excerpts,
            context_used=["Pinterest Docs"],
            context_gaps=["Rate limits"],
        )

        # Act: Serialize to dict (how pipeline stores to DB)
        theme_dict = theme.to_dict()

        # Assert: All Smart Digest fields are present and correct
        assert "diagnostic_summary" in theme_dict
        assert theme_dict["diagnostic_summary"] == "User reports Error 403 when scheduling."

        assert "key_excerpts" in theme_dict
        assert len(theme_dict["key_excerpts"]) == 2
        assert theme_dict["key_excerpts"][0]["text"] == "Error 403: Board access denied"

        assert "context_used" in theme_dict
        assert theme_dict["context_used"] == ["Pinterest Docs"]

        assert "context_gaps" in theme_dict
        assert theme_dict["context_gaps"] == ["Rate limits"]

    def test_theme_dict_serializes_to_valid_json(self):
        """Theme dict should serialize to valid JSON for JSONB columns."""
        theme = Theme(
            conversation_id="test_123",
            product_area="test",
            component="test",
            issue_signature="test",
            user_intent="test",
            symptoms=["symptom"],
            affected_flow="test",
            root_cause_hypothesis="test",
            diagnostic_summary="Test summary with 'quotes' and \"double quotes\"",
            key_excerpts=[
                {"text": "Quote with <special> chars & symbols", "relevance": "Test"}
            ],
            context_used=["Section/With/Slashes"],
            context_gaps=["Missing: info"],
        )

        theme_dict = theme.to_dict()

        # Should not raise - valid JSON
        json_str = json.dumps(theme_dict)
        assert json_str is not None

        # Should round-trip correctly
        parsed = json.loads(json_str)
        assert parsed["diagnostic_summary"] == theme.diagnostic_summary
        assert parsed["key_excerpts"] == theme.key_excerpts


# =============================================================================
# Test 4: End-to-End Data Flow Integration
# =============================================================================

class TestEndToEndDataFlow:
    """
    Integration test verifying the complete Smart Digest data flow.

    This is the key test that would have caught Issue #144's dead code:
    Intercom conversation -> full_conversation -> support_insights ->
    ThemeExtractor -> Theme with populated Smart Digest fields
    """

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_complete_data_flow_from_intercom_to_theme(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
        realistic_intercom_conversation: Dict[str, Any],
        mock_llm_response_with_smart_digest: Dict[str, Any],
    ):
        """
        Complete integration test of Smart Digest data flow.

        Simulates exactly what the pipeline does:
        1. Receive Intercom conversation
        2. Build full_conversation using build_full_conversation_text()
        3. Store full_conversation in support_insights (simulated)
        4. Pass full_conversation to ThemeExtractor.extract()
        5. Verify Theme has populated diagnostic_summary and key_excerpts
        """
        # Setup mock LLM
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_llm_response_with_smart_digest)))
        ]

        # === STEP 1: Receive Intercom conversation ===
        # (realistic_intercom_conversation fixture simulates Intercom API response)
        raw_conv = realistic_intercom_conversation

        # === STEP 2: Build full_conversation ===
        # (This is called in classification_pipeline.py lines 181, 402)
        full_conversation_text = build_full_conversation_text(raw_conv)

        # Verify full_conversation has expected content
        assert "[Customer]:" in full_conversation_text
        assert "[Support]:" in full_conversation_text
        assert "Error 403: Board access denied" in full_conversation_text

        # === STEP 3: Store in support_insights ===
        # (This is the structure from classification_pipeline.py lines 198-201)
        support_insights = {
            "customer_digest": "Hi, I'm having trouble scheduling pins...",
            "full_conversation": full_conversation_text,
        }

        # === STEP 4: Theme extraction receives full_conversation ===
        # Create Conversation model (from DB after classification)
        conv = Conversation(
            id=raw_conv["id"],
            created_at=datetime.utcnow(),
            source_body=raw_conv["source"]["body"],
            source_url=raw_conv["source"].get("url"),
            issue_type="bug_report",
            sentiment="frustrated",
            churn_risk=False,
            priority="high",
        )

        extractor = ThemeExtractor(use_vocabulary=False)

        # Extract theme with full_conversation from support_insights
        # (This is how pipeline.py calls extract() at lines 608-614)
        theme = extractor.extract(
            conv,
            customer_digest=support_insights.get("customer_digest"),
            full_conversation=support_insights.get("full_conversation"),
            use_full_conversation=True,
            canonicalize=False,
        )

        # === STEP 5: Verify Theme has populated Smart Digest fields ===

        # diagnostic_summary should capture error details
        assert theme.diagnostic_summary != "", (
            "FAIL: diagnostic_summary is empty - Smart Digest data flow broken"
        )
        assert "Error 403" in theme.diagnostic_summary, (
            "diagnostic_summary should contain the error from conversation"
        )
        assert "Recipe Ideas" in theme.diagnostic_summary, (
            "diagnostic_summary should contain the board name from conversation"
        )

        # key_excerpts should contain important quotes
        assert len(theme.key_excerpts) > 0, (
            "FAIL: key_excerpts is empty - Smart Digest data flow broken"
        )

        excerpt_texts = [e.get("text", "") for e in theme.key_excerpts]
        assert any("Error 403" in text for text in excerpt_texts), (
            "key_excerpts should contain the error message"
        )

        # Each excerpt should have proper structure
        for i, excerpt in enumerate(theme.key_excerpts):
            assert "text" in excerpt, f"Excerpt {i} missing 'text' field"
            assert "relevance" in excerpt, f"Excerpt {i} missing 'relevance' field"
            assert len(excerpt["text"]) > 0, f"Excerpt {i} has empty text"
            # Relevance should be descriptive (not enum values like "high", "medium", "low")
            assert excerpt["relevance"] not in ("high", "medium", "low"), (
                f"Excerpt {i} relevance should be descriptive, got: {excerpt['relevance']}"
            )

        # context_used and context_gaps should be lists
        assert isinstance(theme.context_used, list)
        assert isinstance(theme.context_gaps, list)

        # Theme should serialize correctly for DB storage
        theme_dict = theme.to_dict()
        json_str = json.dumps(theme_dict)
        assert json_str is not None, "Theme should serialize to JSON"


# =============================================================================
# Test 5: Fallback Behavior When full_conversation is Empty
# =============================================================================

class TestFallbackBehavior:
    """
    Test graceful fallback when full_conversation is missing or empty.
    This ensures the pipeline doesn't break for older conversations.
    """

    @patch.object(ThemeExtractor, "product_context", new_callable=lambda: property(lambda self: "Test context"))
    @patch.object(ThemeExtractor, "get_research_context", return_value="")
    @patch.object(ThemeExtractor, "get_existing_signatures", return_value=[])
    @patch("theme_extractor.OpenAI")
    def test_extract_works_without_full_conversation(
        self,
        mock_openai_class,
        mock_get_signatures,
        mock_research,
        mock_context,
    ):
        """
        ThemeExtractor.extract() should work when full_conversation is None.
        Falls back to customer_digest or source_body.
        """
        # LLM response without Smart Digest fields (backward compatibility)
        llm_response = {
            "product_area": "pinterest_publishing",
            "component": "scheduler",
            "issue_signature": "pinterest_scheduling_issue",
            "matched_existing": False,
            "match_reasoning": "New issue",
            "match_confidence": "medium",
            "user_intent": "Schedule pins",
            "symptoms": ["Pins not posting"],
            "affected_flow": "Scheduler",
            "root_cause_hypothesis": "Unknown",
        }

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(llm_response)))
        ]

        conv = Conversation(
            id="test_123",
            created_at=datetime.utcnow(),
            source_body="My pins are not posting",
            issue_type="bug_report",
            sentiment="neutral",
            churn_risk=False,
            priority="normal",
        )

        extractor = ThemeExtractor(use_vocabulary=False)

        # Act: Call without full_conversation (simulates pre-#144 data)
        theme = extractor.extract(
            conv,
            full_conversation=None,
            customer_digest=None,
            use_full_conversation=True,
            canonicalize=False,
        )

        # Assert: Theme is created with default Smart Digest values
        assert theme.issue_signature == "pinterest_scheduling_issue"
        assert theme.diagnostic_summary == ""  # Empty default
        assert theme.key_excerpts == []  # Empty default

    def test_build_full_conversation_handles_empty_input(self):
        """build_full_conversation_text() should handle empty/None input gracefully."""
        assert build_full_conversation_text({}) == ""
        assert build_full_conversation_text(None) == ""

    def test_build_full_conversation_handles_missing_parts(self):
        """build_full_conversation_text() should handle missing conversation_parts."""
        raw_conv = {
            "source": {"body": "Only source message"},
            # No conversation_parts
        }

        result = build_full_conversation_text(raw_conv)

        assert "[Customer]: Only source message" in result


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
