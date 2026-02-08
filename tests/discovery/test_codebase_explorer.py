"""Tests for the Codebase Explorer agent.

Covers: explore flow, requery, checkpoint building, error handling,
batching, file formatting, truncation, partial batch failure,
coverage invariant, and confidence mapping.

Uses mock OpenAI client + mock CodebaseReader.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.codebase_explorer import (
    CodebaseExplorer,
    CodebaseExplorerConfig,
    ExplorerResult,
    _map_confidence,
)
from src.discovery.agents.codebase_data_access import CodebaseItem


# ============================================================================
# Helpers
# ============================================================================


def _make_codebase_item(**overrides) -> CodebaseItem:
    """Create a test CodebaseItem."""
    defaults = {
        "path": "src/api/main.py",
        "content": "from fastapi import FastAPI\n\napp = FastAPI()\n",
        "item_type": "source_file",
        "metadata": {
            "line_count": 3,
            "commit_count": 2,
            "last_modified": "2026-02-01T10:00:00+00:00",
            "authors": ["dev1"],
        },
    }
    defaults.update(overrides)
    return CodebaseItem(**defaults)


def _make_batch_response(findings=None):
    """Create a mock LLM response for batch analysis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "inconsistent_error_handling",
                "description": "Error handling varies across API endpoints",
                "evidence_file_paths": ["src/api/main.py"],
                "confidence": "high",
                "severity_assessment": "moderate impact on reliability",
                "affected_users_estimate": "~30% of codebase",
            }
        ]
    return _make_llm_response({"findings": findings, "batch_notes": ""})


def _make_synthesis_response(findings=None):
    """Create a mock LLM response for synthesis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "inconsistent_error_handling",
                "description": "Synthesized: error handling varies across endpoints",
                "evidence_file_paths": ["src/api/main.py", "src/api/routes.py"],
                "confidence": "high",
                "severity_assessment": "moderate",
                "affected_users_estimate": "~30% of codebase",
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


class MockCodebaseReader:
    """Mock CodebaseReader for testing."""

    def __init__(self, items=None, count=None):
        self._items = items or []
        self._count = count if count is not None else len(self._items)
        self._by_path = {item.path: item for item in self._items}

    def fetch_recently_changed(self, days, limit=None):
        result = self._items
        if limit:
            result = result[:limit]
        return result

    def fetch_file(self, path):
        return self._by_path.get(path)

    def get_item_count(self, days):
        return self._count


# ============================================================================
# Explore flow tests
# ============================================================================


class TestExplore:
    def test_basic_explore_returns_findings(self):
        items = [_make_codebase_item(path=f"src/module_{i}.py") for i in range(3)]
        reader = MockCodebaseReader(items=items, count=3)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CodebaseExplorer(
            reader=reader,
            openai_client=mock_client,
            config=CodebaseExplorerConfig(batch_size=20),
        )
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "inconsistent_error_handling"
        assert result.coverage["conversations_reviewed"] == 3
        assert result.coverage["items_type"] == "files"

    def test_empty_files_returns_empty_result(self):
        reader = MockCodebaseReader(items=[], count=0)
        mock_client = MagicMock()

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.findings == []
        assert result.coverage["conversations_reviewed"] == 0
        assert result.coverage["conversations_available"] == 0
        mock_client.chat.completions.create.assert_not_called()

    def test_multiple_batches(self):
        items = [_make_codebase_item(path=f"src/mod_{i}.py") for i in range(5)]
        reader = MockCodebaseReader(items=items, count=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_batch_response(findings=[{
                "pattern_name": "duplicated_logic",
                "description": "Same validation in two places",
                "evidence_file_paths": ["src/mod_3.py"],
                "confidence": "medium",
                "severity_assessment": "high",
                "affected_users_estimate": "~10%",
            }]),
            _make_synthesis_response(),
        ]

        explorer = CodebaseExplorer(
            reader=reader,
            openai_client=mock_client,
            config=CodebaseExplorerConfig(batch_size=3),
        )
        result = explorer.explore()

        # 2 batch calls + 1 synthesis call = 3 total
        assert mock_client.chat.completions.create.call_count == 3
        assert result.coverage["conversations_reviewed"] == 5

    def test_tracks_token_usage(self):
        items = [_make_codebase_item()]
        reader = MockCodebaseReader(items=items, count=1)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # 2 LLM calls * 150 tokens each
        assert result.token_usage["total_tokens"] == 300


# ============================================================================
# Partial failure / error handling
# ============================================================================


class TestErrorHandling:
    def test_batch_failure_skips_and_continues(self):
        items = [_make_codebase_item(path=f"src/mod_{i}.py") for i in range(6)]
        reader = MockCodebaseReader(items=items, count=6)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),      # batch 0 succeeds
            Exception("LLM timeout"),    # batch 1 fails
            _make_synthesis_response(),  # synthesis
        ]

        explorer = CodebaseExplorer(
            reader=reader,
            openai_client=mock_client,
            config=CodebaseExplorerConfig(batch_size=3),
        )
        result = explorer.explore()

        assert result.coverage["conversations_reviewed"] == 3
        assert result.coverage["conversations_skipped"] == 3
        assert len(result.batch_errors) == 1
        assert "Batch 1" in result.batch_errors[0]

    def test_synthesis_failure_falls_back_to_raw(self):
        items = [_make_codebase_item()]
        reader = MockCodebaseReader(items=items, count=1)

        raw_finding = {
            "pattern_name": "raw_finding",
            "description": "from batch",
            "evidence_file_paths": ["src/api/main.py"],
            "confidence": "medium",
            "severity_assessment": "low",
            "affected_users_estimate": "few",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(findings=[raw_finding]),
            Exception("Synthesis failed"),
        ]

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "raw_finding"
        assert "Synthesis" in result.batch_errors[0]

    def test_invalid_batch_json_raises(self):
        items = [_make_codebase_item()]
        reader = MockCodebaseReader(items=items, count=1)

        # Response without a findings list
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {"patterns": "wrong key"}
        )

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # Batch fails, 1 file skipped, synthesis not called
        assert result.coverage["conversations_skipped"] >= 1
        assert len(result.batch_errors) == 1


# ============================================================================
# Coverage invariant
# ============================================================================


class TestCoverageInvariant:
    def test_reviewed_plus_skipped_equals_available(self):
        """Coverage reconciliation: reviewed + skipped == available."""
        items = [_make_codebase_item(path=f"src/mod_{i}.py") for i in range(5)]
        reader = MockCodebaseReader(items=items, count=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_coverage_accounts_for_unfetched(self):
        """When available > fetched (due to limit), unfetched go to skipped."""
        items = [_make_codebase_item(path=f"src/mod_{i}.py") for i in range(3)]
        reader = MockCodebaseReader(items=items, count=10)  # 10 available, 3 fetched

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = CodebaseExplorer(
            reader=reader,
            openai_client=mock_client,
            config=CodebaseExplorerConfig(max_files=3),
        )
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] == 3
        assert cov["conversations_skipped"] == 7  # 10 - 3
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_no_files_fetched_but_available(self):
        """When fetch returns empty but count > 0, all go to skipped."""
        reader = MockCodebaseReader(items=[], count=15)
        mock_client = MagicMock()

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_available"] == 15
        assert cov["conversations_reviewed"] == 0
        assert cov["conversations_skipped"] == 15
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_coverage_with_partial_batch_failure(self):
        """Coverage invariant holds even when batches fail."""
        items = [_make_codebase_item(path=f"src/mod_{i}.py") for i in range(4)]
        reader = MockCodebaseReader(items=items, count=4)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("batch 0 failed"),  # batch 0 fails
            _make_batch_response(),        # batch 1 succeeds
            _make_synthesis_response(),    # synthesis
        ]

        explorer = CodebaseExplorer(
            reader=reader,
            openai_client=mock_client,
            config=CodebaseExplorerConfig(batch_size=2),
        )
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]


# ============================================================================
# File formatting and truncation
# ============================================================================


class TestFormatFile:
    def test_short_file_not_truncated(self):
        item = _make_codebase_item(
            content="def hello():\n    return 'world'\n"
        )
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_file(item)

        assert "src/api/main.py" in formatted
        assert "hello" in formatted
        assert "truncated" not in formatted

    def test_long_file_truncated(self):
        content = "x = 1\n" * 2000  # Very long file
        item = _make_codebase_item(content=content)
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(),
            openai_client=MagicMock(),
            config=CodebaseExplorerConfig(max_chars_per_file=500),
        )

        formatted = explorer._format_file(item)

        # Content portion should be capped near budget
        assert "truncated" in formatted

    def test_metadata_always_present(self):
        item = _make_codebase_item()
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_file(item)

        assert "src/api/main.py" in formatted
        assert "lines=3" in formatted
        assert "commits=2" in formatted

    def test_empty_file_handled(self):
        item = _make_codebase_item(content="")
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_file(item)

        assert "empty file" in formatted

    def test_whitespace_only_file_handled(self):
        item = _make_codebase_item(content="   \n  \n  ")
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_file(item)

        assert "empty file" in formatted

    def test_metadata_with_missing_fields(self):
        item = _make_codebase_item(metadata={})
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )

        formatted = explorer._format_file(item)

        assert "lines=?" in formatted
        assert "commits=?" in formatted
        assert "authors=unknown" in formatted

    def test_truncation_at_budget_boundary(self):
        """Content is truncated at exactly max_chars_per_file."""
        content = "a" * 100
        item = _make_codebase_item(content=content)
        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(),
            openai_client=MagicMock(),
            config=CodebaseExplorerConfig(max_chars_per_file=50),
        )

        formatted = explorer._format_file(item)

        # Meta line + 50 chars of content + truncation marker
        lines = formatted.split("\n", 1)
        content_part = lines[1] if len(lines) > 1 else ""
        # Content before truncation marker should be <= 50 chars
        assert "truncated" in content_part


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
                    "evidence_file_paths": ["src/api/main.py"],
                    "confidence": "high",
                    "severity_assessment": "moderate",
                    "affected_users_estimate": "~10%",
                }
            ],
            coverage={
                "time_window_days": 30,
                "conversations_available": 100,
                "conversations_reviewed": 95,
                "conversations_skipped": 5,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "files",
            },
        )

        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["schema_version"] == 1
        assert checkpoint["agent_name"] == "codebase"
        assert len(checkpoint["findings"]) == 1
        assert checkpoint["findings"][0]["pattern_name"] == "test_pattern"
        assert len(checkpoint["findings"][0]["evidence"]) == 1
        assert checkpoint["findings"][0]["evidence"][0]["source_type"] == "codebase"
        assert checkpoint["coverage"]["conversations_reviewed"] == 95

    def test_checkpoint_validates_against_model(self):
        """Checkpoint output should pass ExplorerCheckpoint validation."""
        from src.discovery.models.artifacts import ExplorerCheckpoint

        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "validated_pattern",
                    "description": "Should validate",
                    "evidence_file_paths": ["src/api/main.py"],
                    "confidence": "high",
                    "severity_assessment": "low",
                    "affected_users_estimate": "few",
                }
            ],
            coverage={
                "time_window_days": 30,
                "conversations_available": 50,
                "conversations_reviewed": 50,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "files",
            },
        )

        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Should not raise
        validated = ExplorerCheckpoint(**checkpoint)
        assert validated.agent_name == "codebase"
        assert len(validated.findings) == 1

    def test_empty_findings_checkpoint(self):
        result = ExplorerResult(
            findings=[],
            coverage={
                "time_window_days": 30,
                "conversations_available": 10,
                "conversations_reviewed": 10,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 0,
                "items_type": "files",
            },
        )

        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"] == []
        assert checkpoint["coverage"]["findings_count"] == 0

    def test_checkpoint_evidence_uses_codebase_source_type(self):
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "some_pattern",
                    "description": "desc",
                    "evidence_file_paths": ["src/foo.py", "src/bar.py"],
                    "confidence": "medium",
                    "severity_assessment": "low",
                    "affected_users_estimate": "few",
                }
            ],
            coverage={
                "time_window_days": 30,
                "conversations_available": 5,
                "conversations_reviewed": 5,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "files",
            },
        )

        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        for evidence in checkpoint["findings"][0]["evidence"]:
            assert evidence["source_type"] == "codebase"

    def test_finding_without_evidence_paths(self):
        """Finding with no evidence_file_paths should produce empty evidence."""
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "no_evidence_pattern",
                    "description": "pattern without file paths",
                    "confidence": "low",
                    "severity_assessment": "low",
                    "affected_users_estimate": "unknown",
                }
            ],
            coverage={
                "time_window_days": 30,
                "conversations_available": 5,
                "conversations_reviewed": 5,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "files",
            },
        )

        explorer = CodebaseExplorer(
            reader=MockCodebaseReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"][0]["evidence"] == []


# ============================================================================
# Requery
# ============================================================================


class TestRequery:
    def test_requery_returns_answer(self):
        items = [_make_codebase_item()]
        reader = MockCodebaseReader(items=items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "The error handling pattern is inconsistent in 3 files",
            "evidence_file_paths": ["src/api/main.py"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="How many files have inconsistent error handling?",
            previous_findings=[],
            file_paths=["src/api/main.py"],
        )

        assert result["answer"] == "The error handling pattern is inconsistent in 3 files"

    def test_requery_without_file_paths(self):
        reader = MockCodebaseReader()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "Based on previous findings...",
            "evidence_file_paths": [],
            "confidence": "medium",
            "additional_findings": [],
        })

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="Summarize patterns",
            previous_findings=[{"pattern_name": "test"}],
        )

        assert "Based on previous" in result["answer"]

    def test_requery_with_missing_file(self):
        """Requery for a file not in the reader should still work."""
        reader = MockCodebaseReader(items=[])  # No files

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "Could not access that file",
            "evidence_file_paths": [],
            "confidence": "low",
            "additional_findings": [],
        })

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="What about src/missing.py?",
            previous_findings=[],
            file_paths=["src/missing.py"],
        )

        assert "Could not access" in result["answer"]


# ============================================================================
# Confidence mapping
# ============================================================================


class TestConfidenceMapping:
    def test_maps_high(self):
        assert _map_confidence("high") == "high"

    def test_maps_medium(self):
        assert _map_confidence("medium") == "medium"

    def test_maps_low(self):
        assert _map_confidence("low") == "low"

    def test_unknown_defaults_to_medium(self):
        assert _map_confidence("uncertain") == "medium"

    def test_case_insensitive(self):
        assert _map_confidence("HIGH") == "high"

    def test_none_defaults_to_medium(self):
        assert _map_confidence(None) == "medium"

    def test_non_string_defaults_to_medium(self):
        assert _map_confidence(42) == "medium"
        assert _map_confidence({"level": "high"}) == "medium"
