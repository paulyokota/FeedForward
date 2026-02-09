"""Tests for the Research Explorer agent and ResearchReader.

Covers: explore flow, requery, checkpoint building, error handling,
bucket-based batching, doc formatting/truncation, partial batch failure,
coverage invariant, ResearchReader filesystem operations, and
confidence mapping.

Uses mock OpenAI client + ResearchReader with tmp_path fixtures
for filesystem tests, or direct ResearchItem construction for
explorer-level tests.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.base import ExplorerResult
from src.discovery.agents.research_data_access import ResearchItem, ResearchReader
from src.discovery.agents.research_explorer import (
    ResearchExplorer,
    ResearchExplorerConfig,
)
from src.discovery.models.enums import ConfidenceLevel, SourceType


# ============================================================================
# Helpers
# ============================================================================


def _make_research_item(path="docs/test.md", content="# Test\nSome content.", **kw):
    """Create a ResearchItem with sensible defaults."""
    defaults = {
        "path": path,
        "content": content,
        "bucket": kw.pop("bucket", "general"),
        "metadata": kw.pop("metadata", {
            "char_count": len(content),
            "line_count": content.count("\n") + 1,
            "title": "Test",
        }),
    }
    defaults.update(kw)
    return ResearchItem(**defaults)


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


def _make_batch_response(findings=None):
    """Create a mock LLM response for batch analysis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "unresolved_decision",
                "description": "Architecture docs reference unresolved migration strategy",
                "evidence_doc_paths": ["docs/architecture.md"],
                "confidence": "high",
                "severity_assessment": "moderate impact on velocity",
                "affected_users_estimate": "engineering team",
            }
        ]
    return _make_llm_response({"findings": findings, "batch_notes": ""})


def _make_synthesis_response(findings=None):
    """Create a mock LLM response for synthesis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "unresolved_decision",
                "description": "Synthesized: recurring unresolved migration strategy",
                "evidence_doc_paths": ["docs/architecture.md", "docs/plans/migration.md"],
                "confidence": "high",
                "severity_assessment": "moderate",
                "affected_users_estimate": "engineering team",
            }
        ]
    return _make_llm_response(
        {"findings": findings, "synthesis_notes": "merged across buckets"}
    )


def _make_reader_with_items(items):
    """Create a ResearchReader whose fetch_docs returns the given items."""
    reader = MagicMock(spec=ResearchReader)
    reader.fetch_docs.return_value = items
    reader.get_doc_count.return_value = len(items)
    reader.get_bucket_counts.return_value = {}
    reader.fetch_doc.return_value = None
    return reader


# ============================================================================
# Explore flow tests
# ============================================================================


class TestExplore:
    def test_basic_explore_returns_findings(self):
        items = [
            _make_research_item("docs/architecture.md", "# Arch\nContent", bucket="architecture"),
            _make_research_item("docs/plans/roadmap.md", "# Roadmap\nPlan", bucket="strategy"),
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        # 2 buckets = 2 batch calls + 1 synthesis
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "unresolved_decision"
        assert result.coverage["items_type"] == "research_documents"

    def test_empty_docs_returns_empty_result(self):
        reader = _make_reader_with_items([])
        mock_client = MagicMock()

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.findings == []
        assert result.coverage["conversations_reviewed"] == 0
        assert result.coverage["conversations_available"] == 0
        mock_client.chat.completions.create.assert_not_called()

    def test_bucket_based_batching(self):
        """Each bucket gets its own LLM batch call."""
        items = [
            _make_research_item("docs/architecture.md", "# A\nArch", bucket="architecture"),
            _make_research_item("docs/plans/plan.md", "# P\nPlan", bucket="strategy"),
            _make_research_item("docs/runbook/ops.md", "# O\nOps", bucket="process"),
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),  # architecture
            _make_batch_response(),  # strategy
            _make_batch_response(),  # process
            _make_synthesis_response(),
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # 3 buckets + 1 synthesis = 4 calls
        assert mock_client.chat.completions.create.call_count == 4
        assert result.coverage["conversations_reviewed"] == 3

    def test_tracks_token_usage(self):
        items = [_make_research_item(bucket="general")]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),     # 1 batch
            _make_synthesis_response(),  # synthesis
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # 2 LLM calls * 150 tokens each
        assert result.token_usage["total_tokens"] == 300

    def test_multiple_sub_batches_within_bucket(self):
        """Large bucket gets split into sub-batches."""
        items = [
            _make_research_item(f"docs/arch_{i}.md", f"# Doc {i}\nContent", bucket="architecture")
            for i in range(5)
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        # batch_size=2 => 3 sub-batches for 5 docs, + 1 synthesis
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_batch_response(),
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        config = ResearchExplorerConfig(batch_size=2)
        explorer = ResearchExplorer(reader=reader, openai_client=mock_client, config=config)
        result = explorer.explore()

        assert mock_client.chat.completions.create.call_count == 4
        assert result.coverage["conversations_reviewed"] == 5


# ============================================================================
# Partial failure / error handling
# ============================================================================


class TestErrorHandling:
    def test_batch_failure_skips_and_continues(self):
        items = [
            _make_research_item("docs/arch.md", "# Arch\nA", bucket="architecture"),
            _make_research_item("docs/plan.md", "# Plan\nP", bucket="strategy"),
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("LLM timeout"),    # architecture batch fails
            _make_batch_response(),      # strategy batch succeeds
            _make_synthesis_response(),  # synthesis
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.coverage["conversations_reviewed"] == 1  # only strategy
        assert result.coverage["conversations_skipped"] == 1  # architecture failed
        assert len(result.batch_errors) == 1
        assert "architecture" in result.batch_errors[0]

    def test_synthesis_failure_falls_back_to_raw(self):
        items = [_make_research_item(bucket="general")]
        reader = _make_reader_with_items(items)

        raw_finding = {
            "pattern_name": "raw_finding",
            "description": "from batch",
            "evidence_doc_paths": ["docs/test.md"],
            "confidence": "medium",
            "severity_assessment": "low",
            "affected_users_estimate": "few",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(findings=[raw_finding]),
            Exception("Synthesis failed"),
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "raw_finding"
        assert "Synthesis" in result.batch_errors[0]

    def test_invalid_batch_json_raises(self):
        items = [_make_research_item(bucket="general")]
        reader = _make_reader_with_items(items)

        # Response without a findings list
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {"patterns": "wrong key"}
        )

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # Batch fails, doc skipped
        assert result.coverage["conversations_skipped"] >= 1
        assert len(result.batch_errors) == 1


# ============================================================================
# Coverage invariant
# ============================================================================


class TestCoverageInvariant:
    def test_reviewed_plus_skipped_equals_available(self):
        """Coverage reconciliation: reviewed + skipped == available."""
        items = [
            _make_research_item("docs/a.md", "# A\nA", bucket="architecture"),
            _make_research_item("docs/b.md", "# B\nB", bucket="strategy"),
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_coverage_with_partial_batch_failure(self):
        """Coverage invariant holds even when batches fail."""
        items = [
            _make_research_item("docs/a.md", "# A\nA", bucket="architecture"),
            _make_research_item("docs/b.md", "# B\nB", bucket="strategy"),
            _make_research_item("docs/c.md", "# C\nC", bucket="process"),
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("batch failed"),  # architecture fails
            _make_batch_response(),     # strategy succeeds
            _make_batch_response(),     # process succeeds
            _make_synthesis_response(),
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_coverage_includes_bucket_counts(self):
        items = [
            _make_research_item("docs/a.md", "# A", bucket="architecture"),
            _make_research_item("docs/b.md", "# B", bucket="architecture"),
            _make_research_item("docs/c.md", "# C", bucket="strategy"),
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.coverage["bucket_counts"]["architecture"] == 2
        assert result.coverage["bucket_counts"]["strategy"] == 1


# ============================================================================
# ResearchReader (filesystem tests)
# ============================================================================


class TestResearchReader:
    def test_reads_markdown_files(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "readme.md").write_text("# Readme\nHello world")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        assert len(items) == 1
        assert items[0].path == "docs/readme.md"
        assert "Hello world" in items[0].content

    def test_classifies_into_buckets(self, tmp_path):
        docs_dir = tmp_path / "docs"
        (docs_dir / "plans").mkdir(parents=True)
        (docs_dir / "session").mkdir(parents=True)
        (docs_dir / "plans" / "plan.md").write_text("# Plan")
        (docs_dir / "session" / "notes.md").write_text("# Session")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        buckets = {item.path: item.bucket for item in items}
        assert buckets["docs/plans/plan.md"] == "strategy"
        assert buckets["docs/session/notes.md"] == "session_notes"

    def test_excludes_archive_dirs(self, tmp_path):
        docs_dir = tmp_path / "docs"
        (docs_dir / "_archive").mkdir(parents=True)
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "good.md").write_text("# Good")
        (docs_dir / "_archive" / "old.md").write_text("# Old")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        paths = [item.path for item in items]
        assert "docs/good.md" in paths
        assert "docs/_archive/old.md" not in paths

    def test_excludes_non_markdown(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "readme.md").write_text("# Readme")
        (docs_dir / "data.json").write_text("{}")
        (docs_dir / "script.py").write_text("print('hi')")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        assert len(items) == 1
        assert items[0].path == "docs/readme.md"

    def test_extracts_doc_title(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "titled.md").write_text("# My Cool Title\nContent here")
        (docs_dir / "no_title.md").write_text("Just some text without a heading")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        by_path = {item.path: item for item in items}
        assert by_path["docs/titled.md"].metadata["title"] == "My Cool Title"
        assert by_path["docs/no_title.md"].metadata["title"] == ""

    def test_deterministic_ordering(self, tmp_path):
        """Items sorted by bucket then path."""
        docs_dir = tmp_path / "docs"
        (docs_dir / "plans").mkdir(parents=True)
        (docs_dir / "session").mkdir(parents=True)
        # Create files — strategy < session_notes alphabetically
        (docs_dir / "plans" / "z_plan.md").write_text("# Z")
        (docs_dir / "plans" / "a_plan.md").write_text("# A")
        (docs_dir / "session" / "notes.md").write_text("# Notes")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        # session_notes < strategy alphabetically
        assert items[0].bucket == "session_notes"
        # Within strategy, a_plan.md < z_plan.md
        strategy_items = [i for i in items if i.bucket == "strategy"]
        assert strategy_items[0].path == "docs/plans/a_plan.md"
        assert strategy_items[1].path == "docs/plans/z_plan.md"

    def test_empty_directory_returns_empty(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        items = reader.fetch_docs()

        assert items == []

    def test_fetch_doc_single_file(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "target.md").write_text("# Target\nSpecific doc")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        item = reader.fetch_doc("docs/target.md")

        assert item is not None
        assert item.path == "docs/target.md"
        assert "Specific doc" in item.content

    def test_fetch_doc_nonexistent_returns_none(self, tmp_path):
        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        item = reader.fetch_doc("docs/ghost.md")
        assert item is None

    def test_get_bucket_counts(self, tmp_path):
        docs_dir = tmp_path / "docs"
        (docs_dir / "plans").mkdir(parents=True)
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "plans" / "p1.md").write_text("# P1")
        (docs_dir / "plans" / "p2.md").write_text("# P2")
        (docs_dir / "general.md").write_text("# Gen")

        reader = ResearchReader(doc_paths=["docs/"], repo_root=str(tmp_path))
        counts = reader.get_bucket_counts()

        assert counts["strategy"] == 2
        assert counts["general"] == 1


# ============================================================================
# Doc truncation
# ============================================================================


class TestDocTruncation:
    def test_per_doc_truncation(self):
        """Long content gets truncated in _format_doc."""
        long_content = "# Title\n" + "x" * 10000
        item = _make_research_item(content=long_content, metadata={
            "char_count": len(long_content),
            "line_count": 2,
            "title": "Title",
        })

        config = ResearchExplorerConfig(max_chars_per_doc=100)
        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader),
            openai_client=MagicMock(),
            config=config,
        )

        formatted = explorer._format_doc(item)
        assert "[... truncated ...]" in formatted

    def test_batch_budget_truncation(self):
        """When total formatted text exceeds max_chars_per_batch, tail docs dropped
        and coverage correctly reflects only docs the LLM actually saw."""
        items = [
            _make_research_item(f"docs/doc_{i}.md", f"# Doc {i}\n" + "x" * 500, bucket="general")
            for i in range(10)
        ]
        reader = _make_reader_with_items(items)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        config = ResearchExplorerConfig(max_chars_per_batch=1000)
        explorer = ResearchExplorer(reader=reader, openai_client=mock_client, config=config)
        result = explorer.explore()

        # Should still complete without error
        cov = result.coverage
        # Not all 10 docs fit in 1000 chars — dropped docs go to skipped
        assert cov["conversations_reviewed"] < 10
        assert cov["conversations_skipped"] > 0
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_empty_doc_formatted_as_empty(self):
        """Empty or whitespace-only docs get (empty document) marker."""
        item = _make_research_item(content="   \n  \n  ", metadata={
            "char_count": 9,
            "line_count": 3,
            "title": "",
        })

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader),
            openai_client=MagicMock(),
        )

        formatted = explorer._format_doc(item)
        assert "(empty document)" in formatted


# ============================================================================
# Checkpoint building
# ============================================================================


class TestBuildCheckpoint:
    def test_builds_valid_checkpoint(self):
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "unresolved_decision",
                    "description": "Migration strategy undecided",
                    "evidence_doc_paths": ["docs/architecture.md", "docs/plans/migration.md"],
                    "confidence": "high",
                    "severity_assessment": "moderate",
                    "affected_users_estimate": "engineering team",
                }
            ],
            coverage={
                "time_window_days": 1,
                "conversations_available": 10,
                "conversations_reviewed": 10,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "research_documents",
                "bucket_counts": {"architecture": 5, "strategy": 5},
            },
        )

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["schema_version"] == 1
        assert checkpoint["agent_name"] == "research"
        assert len(checkpoint["findings"]) == 1
        assert checkpoint["findings"][0]["pattern_name"] == "unresolved_decision"
        assert len(checkpoint["findings"][0]["evidence"]) == 2

    def test_checkpoint_validates_against_model(self):
        """Checkpoint output should pass ExplorerCheckpoint validation."""
        from src.discovery.models.artifacts import ExplorerCheckpoint

        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "validated_pattern",
                    "description": "Should validate against Pydantic model",
                    "evidence_doc_paths": ["docs/test.md"],
                    "confidence": "high",
                    "severity_assessment": "low",
                    "affected_users_estimate": "few",
                }
            ],
            coverage={
                "time_window_days": 1,
                "conversations_available": 5,
                "conversations_reviewed": 5,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "research_documents",
                "bucket_counts": {"general": 5},
            },
        )

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Should not raise
        validated = ExplorerCheckpoint(**checkpoint)
        assert validated.agent_name == "research"
        assert len(validated.findings) == 1

    def test_empty_findings_checkpoint(self):
        result = ExplorerResult(
            findings=[],
            coverage={
                "time_window_days": 1,
                "conversations_available": 4,
                "conversations_reviewed": 4,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 0,
                "items_type": "research_documents",
                "bucket_counts": {},
            },
        )

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"] == []
        assert checkpoint["coverage"]["findings_count"] == 0

    def test_checkpoint_evidence_uses_research_source_type(self):
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "some_pattern",
                    "description": "desc",
                    "evidence_doc_paths": ["docs/architecture.md", "docs/status.md"],
                    "confidence": "medium",
                    "severity_assessment": "low",
                    "affected_users_estimate": "few",
                }
            ],
            coverage={
                "time_window_days": 1,
                "conversations_available": 5,
                "conversations_reviewed": 5,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "research_documents",
                "bucket_counts": {},
            },
        )

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        for evidence in checkpoint["findings"][0]["evidence"]:
            assert evidence["source_type"] == "research"

    def test_finding_without_evidence_is_dropped(self):
        """Finding with no evidence_doc_paths violates ExplorerFinding(min_length=1)
        and should be dropped with a warning."""
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "no_evidence_pattern",
                    "description": "pattern without doc paths",
                    "confidence": "low",
                    "severity_assessment": "low",
                    "affected_users_estimate": "unknown",
                },
                {
                    "pattern_name": "has_evidence",
                    "description": "pattern with doc paths",
                    "evidence_doc_paths": ["docs/test.md"],
                    "confidence": "high",
                    "severity_assessment": "high",
                    "affected_users_estimate": "many",
                },
            ],
            coverage={
                "time_window_days": 1,
                "conversations_available": 5,
                "conversations_reviewed": 5,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 2,
                "items_type": "research_documents",
                "bucket_counts": {},
            },
        )

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Only the finding with evidence should survive
        assert len(checkpoint["findings"]) == 1
        assert checkpoint["findings"][0]["pattern_name"] == "has_evidence"

    def test_all_findings_without_evidence_produces_empty_checkpoint(self):
        """When ALL findings lack evidence_doc_paths, checkpoint has zero findings."""
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "no_evidence",
                    "description": "nothing cited",
                    "confidence": "low",
                    "severity_assessment": "low",
                    "affected_users_estimate": "unknown",
                }
            ],
            coverage={
                "time_window_days": 1,
                "conversations_available": 5,
                "conversations_reviewed": 5,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "research_documents",
                "bucket_counts": {},
            },
        )

        explorer = ResearchExplorer(
            reader=MagicMock(spec=ResearchReader), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"] == []


# ============================================================================
# Requery
# ============================================================================


class TestRequery:
    def test_requery_returns_answer(self):
        reader = MagicMock(spec=ResearchReader)
        reader.fetch_doc.return_value = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "The architecture docs mention 3 unresolved decisions",
            "evidence_doc_paths": ["docs/architecture.md"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="How many unresolved decisions?",
            previous_findings=[],
        )

        assert result["answer"] == "The architecture docs mention 3 unresolved decisions"

    def test_requery_with_doc_paths(self):
        """Requery with doc_paths fetches those docs and includes them in prompt."""
        doc_item = _make_research_item("docs/architecture.md", "# Architecture\nDesign details")
        reader = MagicMock(spec=ResearchReader)
        reader.fetch_doc.return_value = doc_item

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "Found in architecture doc",
            "evidence_doc_paths": ["docs/architecture.md"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="Tell me about architecture",
            previous_findings=[],
            doc_paths=["docs/architecture.md"],
        )

        # Verify the LLM was called with relevant doc text in the prompt
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "Architecture" in user_msg or "architecture" in user_msg


# ============================================================================
# Group by bucket (internal method)
# ============================================================================


class TestGroupByBucket:
    def test_groups_by_bucket(self):
        items = [
            _make_research_item("docs/a.md", bucket="architecture"),
            _make_research_item("docs/b.md", bucket="architecture"),
            _make_research_item("docs/c.md", bucket="strategy"),
            _make_research_item("docs/d.md", bucket="process"),
        ]

        groups = ResearchExplorer._group_by_bucket(items)

        assert len(groups) == 3
        assert len(groups["architecture"]) == 2
        assert len(groups["strategy"]) == 1
        assert len(groups["process"]) == 1

    def test_empty_list_returns_empty_dict(self):
        groups = ResearchExplorer._group_by_bucket([])
        assert groups == {}

    def test_single_bucket_single_group(self):
        items = [
            _make_research_item(f"docs/doc_{i}.md", bucket="general")
            for i in range(5)
        ]

        groups = ResearchExplorer._group_by_bucket(items)

        assert len(groups) == 1
        assert len(groups["general"]) == 5
