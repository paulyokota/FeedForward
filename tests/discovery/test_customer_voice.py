"""Tests for the Customer Voice Explorer agent.

Covers: explore flow, requery, checkpoint building, error handling,
batching, conversation formatting, truncation, partial batch failure,
and coverage invariant.

Uses mock OpenAI client + mock ConversationReader.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.discovery.agents.base import ExplorerResult
from src.discovery.agents.customer_voice import (
    CustomerVoiceExplorer,
    ExplorerConfig,
    _split_messages,
)
from src.discovery.models.enums import ConfidenceLevel
from src.discovery.agents.data_access import RawConversation


# ============================================================================
# Helpers
# ============================================================================


def _make_conversation(**overrides) -> RawConversation:
    """Create a test RawConversation."""
    defaults = {
        "conversation_id": "conv_001",
        "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "source_body": "I can't schedule posts",
        "full_conversation": "Customer: I can't schedule posts\nAgent: Can you describe the issue?",
        "source_url": "https://app.example.com/scheduler",
        "used_fallback": False,
    }
    defaults.update(overrides)
    return RawConversation(**defaults)


def _make_batch_response(findings=None):
    """Create a mock LLM response for batch analysis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "scheduling_confusion",
                "description": "Users confused by scheduling UI",
                "evidence_conversation_ids": ["conv_001"],
                "confidence": "high",
                "severity_assessment": "moderate impact on daily workflow",
                "affected_users_estimate": "~20% of active users",
            }
        ]
    return _make_llm_response({"findings": findings, "batch_notes": ""})


def _make_synthesis_response(findings=None):
    """Create a mock LLM response for synthesis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "scheduling_confusion",
                "description": "Synthesized: Users confused by scheduling UI",
                "evidence_conversation_ids": ["conv_001", "conv_002"],
                "confidence": "high",
                "severity_assessment": "moderate",
                "affected_users_estimate": "~20%",
                "batch_sources": [0],
            }
        ]
    return _make_llm_response(
        {"findings": findings, "synthesis_notes": "merged findings"}
    )


def _make_llm_response(content_dict):
    """Create a mock OpenAI ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    return mock_response


class MockReader:
    """Mock ConversationReader for testing."""

    def __init__(self, conversations=None, count=None):
        self._conversations = conversations or []
        self._count = count if count is not None else len(self._conversations)
        self._by_id = {c.conversation_id: c for c in self._conversations}

    def fetch_conversations(self, days, limit=None):
        result = self._conversations
        if limit:
            result = result[:limit]
        return result

    def fetch_conversation_by_id(self, conversation_id):
        return self._by_id.get(conversation_id)

    def get_conversation_count(self, days):
        return self._count


# ============================================================================
# Explore flow tests
# ============================================================================


class TestExplore:
    def test_basic_explore_returns_findings(self):
        convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(3)]
        reader = MockReader(conversations=convos, count=3)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),  # batch analysis
            _make_synthesis_response(),  # synthesis
        ]

        explorer = CustomerVoiceExplorer(
            reader=reader,
            openai_client=mock_client,
            config=ExplorerConfig(batch_size=20),
        )
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "scheduling_confusion"
        assert result.coverage["conversations_reviewed"] == 3

    def test_empty_conversations_returns_empty_result(self):
        reader = MockReader(conversations=[], count=0)
        mock_client = MagicMock()

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.findings == []
        assert result.coverage["conversations_reviewed"] == 0
        assert result.coverage["conversations_available"] == 0
        mock_client.chat.completions.create.assert_not_called()

    def test_multiple_batches(self):
        convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(5)]
        reader = MockReader(conversations=convos, count=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),  # batch 0 (3 convos)
            _make_batch_response(findings=[{
                "pattern_name": "billing_issue",
                "description": "Billing confusion",
                "evidence_conversation_ids": ["conv_003"],
                "confidence": "medium",
                "severity_assessment": "high",
                "affected_users_estimate": "~5%",
            }]),  # batch 1 (2 convos)
            _make_synthesis_response(),  # synthesis
        ]

        explorer = CustomerVoiceExplorer(
            reader=reader,
            openai_client=mock_client,
            config=ExplorerConfig(batch_size=3),
        )
        result = explorer.explore()

        # 2 batch calls + 1 synthesis call = 3 total
        assert mock_client.chat.completions.create.call_count == 3
        assert result.coverage["conversations_reviewed"] == 5

    def test_tracks_token_usage(self):
        convos = [_make_conversation()]
        reader = MockReader(conversations=convos, count=1)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # 2 LLM calls * 150 tokens each
        assert result.token_usage["total_tokens"] == 300


# ============================================================================
# Partial failure / error handling
# ============================================================================


class TestErrorHandling:
    def test_batch_failure_skips_and_continues(self):
        convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(6)]
        reader = MockReader(conversations=convos, count=6)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),  # batch 0 succeeds
            Exception("LLM timeout"),  # batch 1 fails
            _make_synthesis_response(),  # synthesis
        ]

        explorer = CustomerVoiceExplorer(
            reader=reader,
            openai_client=mock_client,
            config=ExplorerConfig(batch_size=3),
        )
        result = explorer.explore()

        assert result.coverage["conversations_reviewed"] == 3
        assert result.coverage["conversations_skipped"] == 3
        assert len(result.batch_errors) == 1
        assert "Batch 1" in result.batch_errors[0]

    def test_synthesis_failure_falls_back_to_raw(self):
        convos = [_make_conversation()]
        reader = MockReader(conversations=convos, count=1)

        raw_finding = {
            "pattern_name": "raw_finding",
            "description": "from batch",
            "evidence_conversation_ids": ["conv_001"],
            "confidence": "medium",
            "severity_assessment": "low",
            "affected_users_estimate": "few",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(findings=[raw_finding]),
            Exception("Synthesis failed"),
        ]

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "raw_finding"
        assert "Synthesis" in result.batch_errors[0]

    def test_invalid_batch_json_raises(self):
        convos = [_make_conversation()]
        reader = MockReader(conversations=convos, count=1)

        # Response without a findings list
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {"patterns": "wrong key"}
        )

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # Batch fails, 1 conversation skipped, synthesis not called
        assert result.coverage["conversations_skipped"] >= 1
        assert len(result.batch_errors) == 1


# ============================================================================
# Coverage invariant
# ============================================================================


class TestCoverageInvariant:
    def test_reviewed_plus_skipped_equals_available(self):
        """Coverage reconciliation: reviewed + skipped == available."""
        convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(5)]
        reader = MockReader(conversations=convos, count=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_coverage_accounts_for_unfetched(self):
        """When available > fetched (due to limit), unfetched go to skipped."""
        convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(3)]
        reader = MockReader(conversations=convos, count=10)  # 10 available, 3 fetched

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CustomerVoiceExplorer(
            reader=reader,
            openai_client=mock_client,
            config=ExplorerConfig(max_conversations=3),
        )
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] == 3
        assert cov["conversations_skipped"] == 7  # 10 - 3
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_no_conversations_fetched_but_available(self):
        """When fetch returns empty but count > 0, all go to skipped."""
        reader = MockReader(conversations=[], count=15)  # 15 available, 0 fetched
        mock_client = MagicMock()

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_available"] == 15
        assert cov["conversations_reviewed"] == 0
        assert cov["conversations_skipped"] == 15
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]


# ============================================================================
# Conversation formatting and truncation (MF2)
# ============================================================================


class TestFormatConversation:
    def test_short_conversation_not_truncated(self):
        conv = _make_conversation(
            full_conversation="Customer: Help\nAgent: Sure, what's up?"
        )
        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_conversation(conv)

        assert "conv_001" in formatted
        assert "Help" in formatted
        assert "omitted" not in formatted

    def test_long_conversation_truncated(self):
        messages = ["Customer: First complaint is very important"]
        for i in range(10):
            speaker = "Agent" if i % 2 == 0 else "Customer"
            messages.append(f"{speaker}: Message {i}")
        messages.append("Agent: Final response")
        messages.append("Customer: Thanks")
        messages.append("Agent: You're welcome")

        conv = _make_conversation(full_conversation="\n".join(messages))
        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_conversation(conv)

        # Should contain first message and last 3
        assert "First complaint" in formatted
        assert "omitted" in formatted
        assert "You're welcome" in formatted

    def test_metadata_always_present(self):
        conv = _make_conversation()
        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_conversation(conv)

        assert "conv_001" in formatted
        assert "2026-02-01" in formatted

    def test_empty_conversation_handled(self):
        conv = _make_conversation(full_conversation="", source_body="")
        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_conversation(conv)

        assert "no conversation text" in formatted

    def test_untagged_text_fallback(self):
        """Text without speaker tags is treated as single block."""
        conv = _make_conversation(
            full_conversation="This is just plain text without any speaker tags at all."
        )
        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_conversation(conv)

        assert "plain text" in formatted
        assert "omitted" not in formatted

    def test_character_budget_enforced(self):
        # Create a very long conversation
        long_text = "Customer: " + "x" * 5000
        conv = _make_conversation(full_conversation=long_text)
        explorer = CustomerVoiceExplorer(
            reader=MockReader(),
            openai_client=MagicMock(),
            config=ExplorerConfig(max_chars_per_conversation=500),
        )

        formatted = explorer._format_conversation(conv)

        # Metadata + text should be within reasonable bounds
        # (meta line adds some chars, but total text portion should be ~500)
        text_portion = formatted.split("\n", 1)[1] if "\n" in formatted else formatted
        assert len(text_portion) <= 600  # budget + truncation marker


# ============================================================================
# Message splitting
# ============================================================================


class TestSplitMessages:
    def test_splits_on_speaker_tags(self):
        text = "Customer: Hello\nAgent: Hi there\nCustomer: Thanks"
        messages = _split_messages(text)
        assert len(messages) == 3

    def test_no_tags_returns_single_block(self):
        text = "Just plain text with no speaker tags"
        messages = _split_messages(text)
        assert len(messages) == 1
        assert messages[0] == text

    def test_handles_multiline_messages(self):
        text = "Customer: Hello\nI have a problem\nWith multiple lines\nAgent: Let me help"
        messages = _split_messages(text)
        assert len(messages) == 2
        assert "multiple lines" in messages[0]


# ============================================================================
# Checkpoint building
# ============================================================================


class TestBuildCheckpoint:
    def test_builds_valid_checkpoint(self):
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "test_pattern",
                    "description": "A test",
                    "evidence_conversation_ids": ["conv_001"],
                    "confidence": "high",
                    "severity_assessment": "moderate",
                    "affected_users_estimate": "~10%",
                }
            ],
            coverage={
                "time_window_days": 14,
                "conversations_available": 100,
                "conversations_reviewed": 95,
                "conversations_skipped": 5,
                "model": "gpt-4o-mini",
                "findings_count": 1,
            },
        )

        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["schema_version"] == 1
        assert checkpoint["agent_name"] == "customer_voice"
        assert len(checkpoint["findings"]) == 1
        assert checkpoint["findings"][0]["pattern_name"] == "test_pattern"
        assert len(checkpoint["findings"][0]["evidence"]) == 1
        assert checkpoint["coverage"]["conversations_reviewed"] == 95

    def test_checkpoint_validates_against_model(self):
        """Checkpoint output should pass ExplorerCheckpoint validation."""
        from src.discovery.models.artifacts import ExplorerCheckpoint

        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "validated_pattern",
                    "description": "Should validate",
                    "evidence_conversation_ids": ["conv_001"],
                    "confidence": "high",
                    "severity_assessment": "low",
                    "affected_users_estimate": "few",
                }
            ],
            coverage={
                "time_window_days": 14,
                "conversations_available": 50,
                "conversations_reviewed": 50,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
            },
        )

        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Should not raise
        validated = ExplorerCheckpoint(**checkpoint)
        assert validated.agent_name == "customer_voice"
        assert len(validated.findings) == 1

    def test_empty_findings_checkpoint(self):
        result = ExplorerResult(
            findings=[],
            coverage={
                "time_window_days": 7,
                "conversations_available": 10,
                "conversations_reviewed": 10,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 0,
            },
        )

        explorer = CustomerVoiceExplorer(
            reader=MockReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"] == []
        assert checkpoint["coverage"]["findings_count"] == 0


# ============================================================================
# Requery
# ============================================================================


class TestRequery:
    def test_requery_returns_answer(self):
        reader = MockReader(conversations=[_make_conversation()])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "There were 3 billing complaints",
            "evidence_conversation_ids": ["conv_001"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="How many billing complaints?",
            previous_findings=[],
            conversation_ids=["conv_001"],
        )

        assert result["answer"] == "There were 3 billing complaints"

    def test_requery_without_conversation_ids(self):
        reader = MockReader()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "Based on previous findings...",
            "evidence_conversation_ids": [],
            "confidence": "medium",
            "additional_findings": [],
        })

        explorer = CustomerVoiceExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="Summarize patterns",
            previous_findings=[{"pattern_name": "test"}],
        )

        assert "Based on previous" in result["answer"]


# ============================================================================
# Confidence mapping
# ============================================================================


class TestConfidenceMapping:
    def test_maps_high(self):
        assert ConfidenceLevel.from_raw("high") == "high"

    def test_maps_medium(self):
        assert ConfidenceLevel.from_raw("medium") == "medium"

    def test_maps_low(self):
        assert ConfidenceLevel.from_raw("low") == "low"

    def test_unknown_defaults_to_medium(self):
        assert ConfidenceLevel.from_raw("uncertain") == "medium"

    def test_case_insensitive(self):
        assert ConfidenceLevel.from_raw("HIGH") == "high"

    def test_none_defaults_to_medium(self):
        assert ConfidenceLevel.from_raw(None) == "medium"

    def test_non_string_defaults_to_medium(self):
        assert ConfidenceLevel.from_raw(42) == "medium"
        assert ConfidenceLevel.from_raw({"level": "high"}) == "medium"
