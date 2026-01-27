"""
Tests for the customer digest extractor module.

Issue #139: Use customer-only digest for embeddings/facets/themes
"""

import pytest
from src.digest_extractor import (
    extract_customer_messages,
    score_message_specificity,
    build_customer_digest,
    _strip_html,
    _messages_are_similar,
)


class TestExtractCustomerMessages:
    """Tests for extract_customer_messages function."""

    def test_extracts_user_messages(self):
        """Should extract messages from user author type."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "I have an issue with my pins",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "Let me help you with that",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "The error says 'Failed to post'",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 2
        assert "I have an issue with my pins" in result[0]
        assert "Failed to post" in result[1]

    def test_extracts_lead_messages(self):
        """Should extract messages from lead author type."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "lead"},
                        "body": "Hello, I need help",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 1
        assert "Hello, I need help" in result[0]

    def test_extracts_contact_messages(self):
        """Should extract messages from contact author type."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "contact"},
                        "body": "Question about scheduling",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 1
        assert "Question about scheduling" in result[0]

    def test_excludes_admin_messages(self):
        """Should not include admin messages."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "Thanks for reaching out",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 0

    def test_excludes_bot_messages(self):
        """Should not include bot messages."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "bot"},
                        "body": "Auto-reply message",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 0

    def test_excludes_non_comment_parts(self):
        """Should only include comment part types."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "assignment",
                        "author": {"type": "user"},
                        "body": "This should not appear",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "This should appear",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 1
        assert "This should appear" in result[0]

    def test_handles_empty_conversation_parts(self):
        """Should handle conversations with no parts."""
        raw_conversation = {"conversation_parts": {}}

        result = extract_customer_messages(raw_conversation)

        assert result == []

    def test_handles_missing_conversation_parts(self):
        """Should handle conversations without conversation_parts key."""
        raw_conversation = {}

        result = extract_customer_messages(raw_conversation)

        assert result == []

    def test_strips_html_from_messages(self):
        """Should strip HTML tags from message bodies."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "<p>Hello <b>world</b></p>",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 1
        assert "<p>" not in result[0]
        assert "<b>" not in result[0]
        assert "Hello" in result[0]
        assert "world" in result[0]

    def test_skips_empty_bodies(self):
        """Should skip messages with empty bodies."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "Actual message",
                    },
                ]
            }
        }

        result = extract_customer_messages(raw_conversation)

        assert len(result) == 1
        assert "Actual message" in result[0]


class TestScoreMessageSpecificity:
    """Tests for score_message_specificity function."""

    def test_quoted_error_text_scores_plus_3(self):
        """Quoted error text should score +3."""
        message = 'The error message says "Failed to connect to Pinterest API"'

        score = score_message_specificity(message)

        # +3 for quoted text, +2 for error keyword
        assert score >= 3

    def test_error_keywords_score_plus_2(self):
        """Error keywords should score +2."""
        test_cases = [
            "I got an error when posting",
            "The scheduler failed to work",
            "I cannot upload images",
            "My pins doesn't work anymore",
            "The feature is broken",
        ]

        for message in test_cases:
            score = score_message_specificity(message)
            assert score >= 2, f"Message '{message}' should score >= 2"

    def test_error_codes_score_plus_2(self):
        """Error codes should score +2."""
        test_cases = [
            "I'm seeing error 500",
            "Got ERR_CONNECTION_REFUSED",
            "Error code E1234",
        ]

        for message in test_cases:
            score = score_message_specificity(message)
            assert score >= 2, f"Message '{message}' should score >= 2"

    def test_feature_nouns_score_plus_1(self):
        """Feature nouns should score +1."""
        test_cases = [
            "My drafts are not saving",
            "The scheduler is acting up",
            "I need to upload a video",
            "My pins are duplicating",
        ]

        for message in test_cases:
            score = score_message_specificity(message)
            assert score >= 1, f"Message '{message}' should score >= 1"

    def test_url_scores_plus_1(self):
        """URLs should score +1."""
        message = "Here's the link: https://example.com/error"

        score = score_message_specificity(message)

        assert score >= 1

    def test_screenshot_marker_scores_plus_1(self):
        """Screenshot markers should score +1."""
        test_cases = [
            "I've attached a screenshot",
            "See the attachment below",
        ]

        for message in test_cases:
            score = score_message_specificity(message)
            assert score >= 1, f"Message '{message}' should score >= 1"

    def test_very_short_message_scores_minus_2(self):
        """Very short messages should score -2."""
        message = "ok"

        score = score_message_specificity(message)

        assert score <= -2

    def test_generic_message_scores_minus_2(self):
        """Generic messages should score -2."""
        test_cases = [
            "thanks",
            "ok got it",
            "hello",
        ]

        for message in test_cases:
            score = score_message_specificity(message)
            assert score <= -2, f"Message '{message}' should score <= -2"

    def test_empty_message_scores_minus_2(self):
        """Empty messages should score -2."""
        score = score_message_specificity("")

        assert score == -2

    def test_combined_scoring(self):
        """Test combined scoring rules."""
        # High specificity message with multiple signals
        high_specificity = 'Error "ERR_TIMEOUT" when using the scheduler to upload pins'
        # +3 (quoted), +2 (error keyword), +2 (error code), +1 (scheduler), +1 (pins)
        high_score = score_message_specificity(high_specificity)
        assert high_score >= 5

        # Low specificity message
        low_specificity = "thanks"
        low_score = score_message_specificity(low_specificity)
        assert low_score < 0

        assert high_score > low_score


class TestBuildCustomerDigest:
    """Tests for build_customer_digest function."""

    def test_returns_source_body_when_no_customer_messages(self):
        """Should return source_body when there are no additional customer messages."""
        source_body = "Initial customer message"
        customer_messages = []

        result = build_customer_digest(source_body, customer_messages)

        assert result == source_body

    def test_uses_most_specific_message(self):
        """Should include the most specific message in digest."""
        source_body = "Hi there"
        customer_messages = [
            "thanks",
            'Error "Failed to post" when using the scheduler',
            "ok",
        ]

        result = build_customer_digest(source_body, customer_messages)

        # Should include the high-specificity message
        assert "Failed to post" in result
        # Should also include source_body
        assert "Hi there" in result

    def test_returns_source_body_when_its_most_specific(self):
        """Should only return source_body when it's the most specific."""
        source_body = 'Error "Connection failed" when posting to Pinterest'
        customer_messages = [
            "thanks",
            "ok got it",
        ]

        result = build_customer_digest(source_body, customer_messages)

        # Source body is most specific, should not duplicate
        assert result == source_body

    def test_dedupes_when_best_message_matches_source(self):
        """Should not duplicate if best message is same as source_body."""
        source_body = "The scheduler is broken"
        customer_messages = [
            "The scheduler is broken",  # Same as source
        ]

        result = build_customer_digest(source_body, customer_messages)

        # Should not have duplicate content
        assert result.count("scheduler is broken") == 1

    def test_respects_max_length(self):
        """Should truncate to max_length."""
        source_body = "A" * 1000
        customer_messages = ["B" * 1000]

        result = build_customer_digest(source_body, customer_messages, max_length=500)

        assert len(result) <= 500

    def test_uses_separator_between_messages(self):
        """Should use separator between source_body and best message."""
        source_body = "Initial message"
        customer_messages = [
            'Error "Timeout" when saving draft',  # More specific
        ]

        result = build_customer_digest(source_body, customer_messages)

        assert "---" in result

    def test_handles_empty_source_body(self):
        """Should handle empty source_body."""
        source_body = ""
        customer_messages = ["Actual issue description"]

        result = build_customer_digest(source_body, customer_messages)

        # Should still return something
        assert result is not None


class TestStripHtml:
    """Tests for _strip_html helper function."""

    def test_removes_html_tags(self):
        """Should remove HTML tags."""
        html = "<p>Hello <b>world</b></p>"

        result = _strip_html(html)

        assert "<p>" not in result
        assert "<b>" not in result
        assert "Hello" in result
        assert "world" in result

    def test_normalizes_whitespace(self):
        """Should normalize multiple spaces to single space."""
        html = "<p>Hello</p>  <p>world</p>"

        result = _strip_html(html)

        assert "  " not in result

    def test_handles_plain_text(self):
        """Should handle plain text without tags."""
        text = "Plain text message"

        result = _strip_html(text)

        assert result == "Plain text message"


class TestMessagesAreSimilar:
    """Tests for _messages_are_similar helper function."""

    def test_exact_match_is_similar(self):
        """Exact matches should be similar."""
        assert _messages_are_similar("hello world", "hello world") is True

    def test_case_insensitive_match(self):
        """Should be case insensitive."""
        assert _messages_are_similar("Hello World", "hello world") is True

    def test_one_contains_other(self):
        """Should detect when one message contains the other."""
        assert _messages_are_similar(
            "short",
            "this is a short message"
        ) is True

    def test_different_messages_not_similar(self):
        """Different messages should not be similar."""
        assert _messages_are_similar(
            "The scheduler is broken",
            "I love using this product"
        ) is False

    def test_handles_empty_strings(self):
        """Should handle empty strings."""
        assert _messages_are_similar("", "") is False
        assert _messages_are_similar("hello", "") is False


class TestIntegration:
    """Integration tests for the full digest workflow."""

    def test_full_workflow_with_realistic_conversation(self):
        """Test full workflow with a realistic conversation."""
        # Simulate a real Intercom conversation structure
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "I'm having trouble with my pins",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "Can you tell me more about the issue?",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": 'I get error "ERR_PINTEREST_API_500" when trying to schedule pins. Screenshot attached.',
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "Thanks, let me look into this.",
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "thanks",
                    },
                ]
            }
        }

        source_body = "I'm having trouble with my pins"

        # Extract customer messages
        customer_messages = extract_customer_messages(raw_conversation)
        assert len(customer_messages) == 3

        # Build digest
        digest = build_customer_digest(source_body, customer_messages)

        # Should include both the initial message and the specific error details
        assert "trouble with my pins" in digest
        assert "ERR_PINTEREST_API_500" in digest

        # Should NOT include "thanks" (low specificity)
        # The digest should prioritize the error message

    def test_digest_improves_on_source_body_alone(self):
        """Verify digest captures error details not in source_body."""
        source_body = "Help please"

        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": 'The scheduler shows "Error 429: Rate limit exceeded" when I try to post',
                    },
                ]
            }
        }

        customer_messages = extract_customer_messages(raw_conversation)
        digest = build_customer_digest(source_body, customer_messages)

        # source_body alone would miss the error details
        assert "Error 429" in digest or "Rate limit" in digest
