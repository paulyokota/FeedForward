"""
Tests for ResolutionAnalyzer and KnowledgeExtractor Integration.

Tests the integration of resolution analysis and knowledge extraction into
the two-stage classification pipeline.

Run with: pytest tests/test_pipeline_integration_insights.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from two_stage_pipeline import (
    detect_resolution_signal,
    get_full_resolution_analysis,
    extract_knowledge,
)


# -----------------------------------------------------------------------------
# Unit Tests for Helper Functions
# -----------------------------------------------------------------------------

class TestDetectResolutionSignal:
    """Test detect_resolution_signal backward compatibility."""

    def test_detect_resolution_signal_backward_compatible(self):
        """Verify simple format returned for backward compatibility."""
        support_messages = [
            "Thanks for reaching out!",
            "I've processed your refund and it should appear in 3-5 business days."
        ]

        result = detect_resolution_signal(support_messages)

        # Should return simple format: {"action": str, "signal": str}
        assert result is not None
        assert "action" in result
        assert "signal" in result
        assert isinstance(result["action"], str)
        assert isinstance(result["signal"], str)

    def test_detect_resolution_signal_empty_messages(self):
        """Verify None handling for empty messages."""
        assert detect_resolution_signal([]) is None
        assert detect_resolution_signal(None) is None

    def test_detect_resolution_signal_no_patterns(self):
        """Verify None returned when no resolution patterns found."""
        support_messages = [
            "Thanks for reaching out!",
            "Can you provide more details?"
        ]

        result = detect_resolution_signal(support_messages)
        assert result is None

    def test_detect_resolution_signal_multiple_patterns(self):
        """Verify all messages are analyzed for resolution patterns."""
        support_messages = [
            "I've created a ticket for engineering.",  # Has pattern
            "Can you provide more details?"  # No pattern
        ]

        result = detect_resolution_signal(support_messages)
        # Should detect ticket_created from first message
        assert result is not None
        assert result["action"] == "ticket_created"

    def test_detect_resolution_signal_various_phrases(self):
        """Test detection of various resolution phrases from resolution_patterns.json."""
        test_cases = [
            ("I've processed your refund", "refund_processed", "processed your refund"),
            ("I've created a ticket for engineering", "ticket_created", "created a ticket"),
            ("Here's the help doc", "docs_link_sent", "here's the help doc"),
            ("Not currently available", "feature_not_available", "not currently available"),
            ("I've reset your password", "password_reset", "reset your password"),
        ]

        for message, expected_action, expected_keyword in test_cases:
            result = detect_resolution_signal([message])
            assert result is not None, f"Expected to detect pattern in: {message}"
            assert result["action"] == expected_action
            assert expected_keyword in result["signal"].lower()


class TestGetFullResolutionAnalysis:
    """Test get_full_resolution_analysis format."""

    def test_get_full_resolution_analysis_format(self):
        """Verify full analysis structure."""
        support_messages = [
            "Thanks for reaching out!",
            "I've processed your refund and it should appear in 3-5 business days."
        ]

        with patch('two_stage_pipeline.get_resolution_analyzer') as mock_get_analyzer:
            # Mock the analyzer
            mock_analyzer = Mock()
            mock_analyzer.analyze_conversation.return_value = {
                "primary_action": {
                    "action": "refund_processed",
                    "category": "billing",
                    "conversation_type": "billing_question",
                    "action_category": "billing_resolution",
                    "matched_keyword": "refund"
                },
                "all_actions": [
                    {
                        "action": "refund_processed",
                        "category": "billing",
                        "matched_keyword": "refund"
                    }
                ],
                "action_count": 1,
                "categories": ["billing"],
                "suggested_type": "billing_question"
            }
            mock_get_analyzer.return_value = mock_analyzer

            result = get_full_resolution_analysis(support_messages)

            # Verify expected keys
            assert "primary_action" in result
            assert "action_category" in result
            assert "all_actions" in result
            assert "categories" in result
            assert "suggested_type" in result
            assert "matched_keywords" in result

            # Verify types
            assert result["primary_action"] == "refund_processed"
            assert result["action_category"] == "billing_resolution"
            assert isinstance(result["all_actions"], list)
            assert isinstance(result["categories"], list)
            assert result["suggested_type"] == "billing_question"
            assert isinstance(result["matched_keywords"], list)

    def test_get_full_resolution_analysis_no_actions(self):
        """Verify handling when no actions detected."""
        support_messages = ["Thanks for reaching out!"]

        with patch('two_stage_pipeline.get_resolution_analyzer') as mock_get_analyzer:
            mock_analyzer = Mock()
            mock_analyzer.analyze_conversation.return_value = {
                "primary_action": None,
                "all_actions": [],
                "action_count": 0,
                "categories": [],
                "suggested_type": None
            }
            mock_get_analyzer.return_value = mock_analyzer

            result = get_full_resolution_analysis(support_messages)

            assert result["primary_action"] is None
            assert result["action_category"] is None
            assert result["all_actions"] == []
            assert result["categories"] == []
            assert result["suggested_type"] is None
            assert result["matched_keywords"] == []

    def test_get_full_resolution_analysis_empty_messages(self):
        """Verify empty dict returned for empty messages."""
        assert get_full_resolution_analysis([]) == {}
        assert get_full_resolution_analysis(None) == {}


class TestExtractKnowledge:
    """Test extract_knowledge format."""

    def test_extract_knowledge_format(self):
        """Verify knowledge structure."""
        customer_message = "I can't cancel my subscription"
        support_messages = [
            "I'm sorry you're looking to cancel. Could you share why?",
            "I've gone ahead and initialized that cancellation for you."
        ]

        with patch('two_stage_pipeline.get_knowledge_extractor') as mock_get_extractor:
            mock_extractor = Mock()
            mock_extractor.extract_from_conversation.return_value = {
                "conversation_type": "billing_question",
                "root_cause": "Customer wants to cancel subscription",
                "solution_provided": "I've gone ahead and initialized that cancellation for you",
                "product_mentions": ["subscription"],
                "feature_mentions": ["billing"],
                "customer_terminology": ["cancel subscription"],
                "support_terminology": ["initialized cancellation"],
                "self_service_gap": True,
                "gap_evidence": "Support manually handled cancel - could be self-service"
            }
            mock_get_extractor.return_value = mock_extractor

            result = extract_knowledge(
                customer_message,
                support_messages,
                "billing_question"
            )

            # Verify expected keys (subset for storage)
            assert "root_cause" in result
            assert "solution_provided" in result
            assert "product_mentions" in result
            assert "feature_mentions" in result
            assert "self_service_gap" in result
            assert "gap_evidence" in result

            # Should NOT include verbose fields
            assert "customer_terminology" not in result
            assert "support_terminology" not in result

            # Verify values
            assert result["self_service_gap"] is True
            assert "cancel" in result["gap_evidence"]

    def test_extract_knowledge_empty_messages(self):
        """Verify empty dict returned for empty messages."""
        assert extract_knowledge("test", [], "billing_question") == {}
        assert extract_knowledge("test", None, "billing_question") == {}

    def test_extract_knowledge_no_self_service_gap(self):
        """Verify handling when no self-service gap detected."""
        customer_message = "How do I reset my password?"
        support_messages = [
            "You can reset your password by visiting the login page and clicking 'Forgot Password'."
        ]

        with patch('two_stage_pipeline.get_knowledge_extractor') as mock_get_extractor:
            mock_extractor = Mock()
            mock_extractor.extract_from_conversation.return_value = {
                "conversation_type": "how_to_question",
                "root_cause": None,
                "solution_provided": "You can reset your password by visiting the login page",
                "product_mentions": [],
                "feature_mentions": ["password"],
                "customer_terminology": ["reset password"],
                "support_terminology": ["forgot password"],
                "self_service_gap": False,
                "gap_evidence": None
            }
            mock_get_extractor.return_value = mock_extractor

            result = extract_knowledge(
                customer_message,
                support_messages,
                "how_to_question"
            )

            assert result["self_service_gap"] is False
            assert result["gap_evidence"] is None


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

class TestSupportInsightsIntegration:
    """Test support_insights structure in pipeline results."""

    def test_support_insights_structure_with_messages(self):
        """Verify support_insights structure when support messages exist."""
        from two_stage_pipeline import extract_support_messages

        # Test extract_support_messages helper
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "I'm sorry you're looking to cancel. Could you share why?"
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "I've gone ahead and processed your refund."
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},  # Should be filtered out
                        "body": "Thank you!"
                    }
                ]
            }
        }

        messages = extract_support_messages(raw_conversation)

        # Should only extract admin messages
        assert len(messages) == 2
        assert "cancel" in messages[0].lower()
        assert "refund" in messages[1].lower()

    def test_support_insights_structure_no_messages(self):
        """Verify support_insights handling when no support messages."""
        from two_stage_pipeline import extract_support_messages

        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": []
            }
        }

        messages = extract_support_messages(raw_conversation)
        assert messages == []

    def test_support_insights_backward_compatibility(self):
        """Verify resolution_signal format unchanged (backward compatibility)."""
        support_messages = [
            "I've created a ticket for engineering to investigate this issue."
        ]

        # Test the simple detect_resolution_signal
        result = detect_resolution_signal(support_messages)

        # Should return simple format: {"action": str, "signal": str}
        assert result is not None
        assert "action" in result
        assert "signal" in result
        assert result["action"] == "ticket_created"
        assert "created a ticket" in result["signal"].lower()

        # Test the full analysis
        full_result = get_full_resolution_analysis(support_messages)

        # Should have more detailed structure
        assert "primary_action" in full_result
        assert "action_category" in full_result
        assert "all_actions" in full_result
        assert full_result["primary_action"] == "ticket_created"
        assert full_result["action_category"] == "escalation"

    def test_integration_extract_support_messages_various_authors(self):
        """Test extract_support_messages with various author types."""
        raw_conversation = {
            "conversation_parts": {
                "conversation_parts": [
                    {
                        "part_type": "comment",
                        "author": {"type": "admin"},
                        "body": "Admin message 1"
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "bot"},
                        "body": "Bot message"
                    },
                    {
                        "part_type": "comment",
                        "author": {"type": "user"},
                        "body": "User message"
                    },
                    {
                        "part_type": "note",  # Not a comment
                        "author": {"type": "admin"},
                        "body": "Admin note"
                    }
                ]
            }
        }

        from two_stage_pipeline import extract_support_messages
        messages = extract_support_messages(raw_conversation)

        # Should only extract admin and bot comments (not notes, not user)
        assert len(messages) == 2
        assert "Admin message 1" in messages
        assert "Bot message" in messages


# -----------------------------------------------------------------------------
# Database Integration Tests
# -----------------------------------------------------------------------------

class TestSupportInsightsDBStorage:
    """Test support_insights stored in DB (integration with storage layer)."""

    def test_support_insights_stored_in_db(self):
        """Verify support_insights can be stored in classification_results table."""
        # This test verifies the data structure is compatible with DB storage
        # Actual DB test would require database fixture

        sample_support_insights = {
            "resolution_analysis": {
                "primary_action": "refund_processed",
                "action_category": "billing_resolution",
                "all_actions": ["refund_processed"],
                "categories": ["billing"],
                "suggested_type": "billing_question",
                "matched_keywords": ["refund"]
            },
            "knowledge": {
                "root_cause": "Customer wants refund",
                "solution_provided": "I've processed your refund",
                "product_mentions": ["subscription"],
                "feature_mentions": ["billing"],
                "self_service_gap": True,
                "gap_evidence": "Support manually handled refund"
            }
        }

        # Verify structure is JSON-serializable (required for JSONB storage)
        import json
        try:
            json_str = json.dumps(sample_support_insights)
            restored = json.loads(json_str)
            assert restored == sample_support_insights
        except (TypeError, ValueError) as e:
            pytest.fail(f"support_insights not JSON-serializable: {e}")

    def test_support_insights_empty_structure(self):
        """Verify empty support_insights is valid."""
        empty_insights = {
            "resolution_analysis": {},
            "knowledge": {}
        }

        import json
        json_str = json.dumps(empty_insights)
        restored = json.loads(json_str)
        assert restored == empty_insights

    def test_support_insights_null_values(self):
        """Verify support_insights with null values is valid."""
        null_insights = {
            "resolution_analysis": {
                "primary_action": None,
                "action_category": None,
                "all_actions": [],
                "categories": [],
                "suggested_type": None,
                "matched_keywords": []
            },
            "knowledge": {
                "root_cause": None,
                "solution_provided": None,
                "product_mentions": [],
                "feature_mentions": [],
                "self_service_gap": False,
                "gap_evidence": None
            }
        }

        import json
        json_str = json.dumps(null_insights)
        restored = json.loads(json_str)
        assert restored == null_insights


# -----------------------------------------------------------------------------
# Edge Case Tests
# -----------------------------------------------------------------------------

class TestHelperEdgeCases:
    """Test edge cases for helper functions."""

    def test_detect_resolution_signal_handles_special_chars(self):
        """Test handling of special characters in messages."""
        support_messages = [
            "I've processed your refund! 🎉"  # Use actual pattern from resolution_patterns.json
        ]
        result = detect_resolution_signal(support_messages)
        assert result is not None
        assert result["action"] == "refund_processed"

    def test_detect_resolution_signal_case_insensitive(self):
        """Test case-insensitive pattern matching."""
        support_messages = [
            "I've PROCESSED YOUR REFUND."  # Use actual pattern from resolution_patterns.json
        ]
        result = detect_resolution_signal(support_messages)
        assert result is not None
        assert result["action"] == "refund_processed"

    def test_get_full_resolution_analysis_with_multiple_actions(self):
        """Test handling of multiple detected actions."""
        support_messages = [
            "I've created a ticket for engineering and sent you the help doc."
        ]

        with patch('two_stage_pipeline.get_resolution_analyzer') as mock_get_analyzer:
            mock_analyzer = Mock()
            mock_analyzer.analyze_conversation.return_value = {
                "primary_action": {
                    "action": "ticket_created",
                    "category": "escalation",
                    "conversation_type": "product_issue",
                    "action_category": "escalation",
                    "matched_keyword": "ticket"
                },
                "all_actions": [
                    {
                        "action": "ticket_created",
                        "category": "escalation",
                        "matched_keyword": "ticket"
                    },
                    {
                        "action": "docs_link_sent",
                        "category": "guidance",
                        "matched_keyword": "help doc"
                    }
                ],
                "action_count": 2,
                "categories": ["escalation", "guidance"],
                "suggested_type": "product_issue"
            }
            mock_get_analyzer.return_value = mock_analyzer

            result = get_full_resolution_analysis(support_messages)

            assert len(result["all_actions"]) == 2
            assert "ticket_created" in result["all_actions"]
            assert "docs_link_sent" in result["all_actions"]
            assert len(result["categories"]) == 2
            assert len(result["matched_keywords"]) == 2
