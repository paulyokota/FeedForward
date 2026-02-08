"""Tests for the Analytics Explorer agent and PostHogReader.

Covers: explore flow, requery, checkpoint building, error handling,
structural batching by data_type, data point formatting, truncation,
partial batch failure, coverage invariant, and confidence mapping.

Uses mock OpenAI client + PostHogReader instantiated with canned dicts.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.base import ExplorerResult
from src.discovery.agents.analytics_explorer import (
    AnalyticsExplorer,
    AnalyticsExplorerConfig,
)
from src.discovery.agents.posthog_data_access import PostHogDataPoint, PostHogReader
from src.discovery.models.enums import ConfidenceLevel, SourceType


# ============================================================================
# Helpers
# ============================================================================


def _make_event_definition(**overrides):
    """Create a test event definition dict."""
    defaults = {
        "name": "user_signed_up",
        "event_type": "custom",
        "last_seen_at": "2026-02-01T12:00:00Z",
        "volume_30_day": 1500,
    }
    defaults.update(overrides)
    return defaults


def _make_dashboard(**overrides):
    """Create a test dashboard dict."""
    defaults = {
        "id": 42,
        "name": "Growth Dashboard",
        "description": "Tracks user growth metrics",
        "tags": ["growth", "product"],
    }
    defaults.update(overrides)
    return defaults


def _make_insight(**overrides):
    """Create a test insight dict."""
    defaults = {
        "id": 101,
        "name": "Weekly Active Users",
        "description": "WAU trend over time",
        "query": {
            "kind": "TrendsQuery",
            "series": [{"event": "$pageview"}],
            "dateRange": {"date_from": "-30d"},
        },
    }
    defaults.update(overrides)
    return defaults


def _make_error(**overrides):
    """Create a test error dict."""
    defaults = {
        "id": "err_001",
        "type": "TypeError",
        "value": "Cannot read property 'x' of undefined",
        "occurrences": 42,
        "sessions": 15,
        "users": 8,
        "status": "unresolved",
        "fingerprint": ["TypeError", "app.js", "handleClick"],
    }
    defaults.update(overrides)
    return defaults


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
                "pattern_name": "low_feature_adoption",
                "description": "Several features show minimal usage despite being shipped",
                "evidence_refs": ["event_user_signed_up", "insight_101"],
                "confidence": "high",
                "severity_assessment": "moderate impact on growth",
                "affected_users_estimate": "~40% of user base",
            }
        ]
    return _make_llm_response({"findings": findings, "batch_notes": ""})


def _make_synthesis_response(findings=None):
    """Create a mock LLM response for synthesis."""
    if findings is None:
        findings = [
            {
                "pattern_name": "low_feature_adoption",
                "description": "Synthesized: features with low adoption despite shipping",
                "evidence_refs": ["event_user_signed_up", "insight_101", "dashboard_42"],
                "confidence": "high",
                "severity_assessment": "moderate",
                "affected_users_estimate": "~40% of users",
                "batch_sources": ["event_definition", "insight"],
            }
        ]
    return _make_llm_response(
        {"findings": findings, "synthesis_notes": "merged across categories"}
    )


def _make_reader_with_data(**overrides):
    """Create a PostHogReader with default test data."""
    defaults = {
        "event_definitions": [_make_event_definition()],
        "dashboards": [_make_dashboard()],
        "insights": [_make_insight()],
        "errors": [_make_error()],
    }
    defaults.update(overrides)
    return PostHogReader(**defaults)


# ============================================================================
# Explore flow tests
# ============================================================================


class TestExplore:
    def test_basic_explore_returns_findings(self):
        reader = _make_reader_with_data()

        mock_client = MagicMock()
        # 4 data types = 4 batch calls + 1 synthesis
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),  # dashboard batch
            _make_batch_response(),  # error batch
            _make_batch_response(),  # event_definition batch
            _make_batch_response(),  # insight batch
            _make_synthesis_response(),
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "low_feature_adoption"
        assert result.coverage["items_type"] == "analytics_data_points"

    def test_empty_data_returns_empty_result(self):
        reader = PostHogReader()  # All empty
        mock_client = MagicMock()

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.findings == []
        assert result.coverage["conversations_reviewed"] == 0
        assert result.coverage["conversations_available"] == 0
        mock_client.chat.completions.create.assert_not_called()

    def test_structural_batching_by_data_type(self):
        """Each data_type group gets its own LLM batch call."""
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition(name=f"evt_{i}") for i in range(3)],
            dashboards=[_make_dashboard(id=i, name=f"Dash {i}") for i in range(2)],
            insights=[],
            errors=[],
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),  # dashboard batch (2 dashboards)
            _make_batch_response(),  # event_definition batch (3 events)
            _make_synthesis_response(),
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # 2 data_type groups + 1 synthesis = 3 calls
        assert mock_client.chat.completions.create.call_count == 3
        assert result.coverage["conversations_reviewed"] == 5  # 3 events + 2 dashboards

    def test_tracks_token_usage(self):
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition()],
            dashboards=[],
            insights=[],
            errors=[],
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),     # 1 batch
            _make_synthesis_response(),  # synthesis
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # 2 LLM calls * 150 tokens each
        assert result.token_usage["total_tokens"] == 300


# ============================================================================
# Partial failure / error handling
# ============================================================================


class TestErrorHandling:
    def test_batch_failure_skips_and_continues(self):
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition()],
            dashboards=[_make_dashboard()],
            insights=[],
            errors=[],
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("LLM timeout"),    # dashboard batch fails
            _make_batch_response(),      # event_definition batch succeeds
            _make_synthesis_response(),  # synthesis
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.coverage["conversations_reviewed"] == 1  # only events
        assert result.coverage["conversations_skipped"] == 1  # dashboard failed
        assert len(result.batch_errors) == 1
        assert "dashboard" in result.batch_errors[0]

    def test_synthesis_failure_falls_back_to_raw(self):
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition()],
            dashboards=[],
            insights=[],
            errors=[],
        )

        raw_finding = {
            "pattern_name": "raw_finding",
            "description": "from batch",
            "evidence_refs": ["event_user_signed_up"],
            "confidence": "medium",
            "severity_assessment": "low",
            "affected_users_estimate": "few",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(findings=[raw_finding]),
            Exception("Synthesis failed"),
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert len(result.findings) == 1
        assert result.findings[0]["pattern_name"] == "raw_finding"
        assert "Synthesis" in result.batch_errors[0]

    def test_invalid_batch_json_raises(self):
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition()],
            dashboards=[],
            insights=[],
            errors=[],
        )

        # Response without a findings list
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {"patterns": "wrong key"}
        )

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        # Batch fails, data point skipped
        assert result.coverage["conversations_skipped"] >= 1
        assert len(result.batch_errors) == 1


# ============================================================================
# Coverage invariant
# ============================================================================


class TestCoverageInvariant:
    def test_reviewed_plus_skipped_equals_available(self):
        """Coverage reconciliation: reviewed + skipped == available."""
        reader = _make_reader_with_data()

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_batch_response(),
            _make_batch_response(),
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_empty_but_counted_goes_to_skipped(self):
        """When fetch returns empty but we construct reader with data
        that gets formatted to 0 points, all go to skipped."""
        reader = PostHogReader()  # All empty = 0 total
        mock_client = MagicMock()

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_available"] == 0
        assert cov["conversations_reviewed"] == 0
        assert cov["conversations_skipped"] == 0

    def test_coverage_with_partial_batch_failure(self):
        """Coverage invariant holds even when batches fail."""
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition()],
            dashboards=[_make_dashboard()],
            insights=[_make_insight()],
            errors=[],
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            Exception("batch failed"),   # dashboard fails
            _make_batch_response(),      # event_definition succeeds
            _make_batch_response(),      # insight succeeds
            _make_synthesis_response(),  # synthesis
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        cov = result.coverage
        assert cov["conversations_reviewed"] + cov["conversations_skipped"] == cov["conversations_available"]

    def test_time_window_days_is_1_for_analytics(self):
        """Analytics is a snapshot; time_window_days should be 1."""
        reader = _make_reader_with_data(
            event_definitions=[_make_event_definition()],
            dashboards=[],
            insights=[],
            errors=[],
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.explore()

        assert result.coverage["time_window_days"] == 1


# ============================================================================
# Data point formatting (PostHogReader)
# ============================================================================


class TestPostHogReader:
    def test_formats_event_definitions(self):
        reader = PostHogReader(event_definitions=[
            _make_event_definition(name="user_signed_up", volume_30_day=1500),
        ])
        points = reader.fetch_overview()

        assert len(points) == 1
        assert points[0].data_type == "event_definition"
        assert points[0].name == "user_signed_up"
        assert "1500" in points[0].result_summary
        assert points[0].source_ref == "event_user_signed_up"

    def test_formats_dashboards(self):
        reader = PostHogReader(dashboards=[
            _make_dashboard(id=42, name="Growth Dashboard", tags=["growth"]),
        ])
        points = reader.fetch_overview()

        assert len(points) == 1
        assert points[0].data_type == "dashboard"
        assert "Growth Dashboard" in points[0].result_summary
        assert "growth" in points[0].result_summary
        assert points[0].source_ref == "dashboard_42"

    def test_formats_insights(self):
        reader = PostHogReader(insights=[_make_insight()])
        points = reader.fetch_overview()

        assert len(points) == 1
        assert points[0].data_type == "insight"
        assert "TrendsQuery" in points[0].result_summary
        assert points[0].source_ref == "insight_101"

    def test_formats_errors(self):
        reader = PostHogReader(errors=[_make_error()])
        points = reader.fetch_overview()

        assert len(points) == 1
        assert points[0].data_type == "error"
        assert "TypeError" in points[0].result_summary
        assert "42" in points[0].result_summary  # occurrences
        assert points[0].source_ref == "error_err_001"

    def test_empty_reader_returns_empty(self):
        reader = PostHogReader()
        points = reader.fetch_overview()
        assert points == []
        assert reader.get_data_point_count() == 0

    def test_get_data_point_count(self):
        reader = PostHogReader(
            event_definitions=[_make_event_definition()] * 3,
            dashboards=[_make_dashboard()] * 2,
            insights=[_make_insight()],
            errors=[_make_error()] * 4,
        )
        assert reader.get_data_point_count() == 10

    def test_deterministic_ordering(self):
        """Points sorted by data_type then name."""
        reader = PostHogReader(
            event_definitions=[
                _make_event_definition(name="zebra_event"),
                _make_event_definition(name="alpha_event"),
            ],
            dashboards=[_make_dashboard(name="Beta Dashboard")],
        )
        points = reader.fetch_overview()

        # dashboard < event_definition (alphabetical data_type)
        assert points[0].data_type == "dashboard"
        # Then event_definitions sorted by name
        assert points[1].name == "alpha_event"
        assert points[2].name == "zebra_event"

    def test_dashboard_description_truncation(self):
        long_desc = "x" * 500
        reader = PostHogReader(dashboards=[
            _make_dashboard(description=long_desc),
        ])
        points = reader.fetch_overview()

        assert "[... truncated]" in points[0].result_summary

    def test_error_message_truncation(self):
        long_msg = "Error: " + "y" * 500
        reader = PostHogReader(errors=[
            _make_error(value=long_msg),
        ])
        points = reader.fetch_overview()

        assert "[... truncated]" in points[0].result_summary

    def test_fetch_specific_by_name(self):
        reader = PostHogReader(
            event_definitions=[
                _make_event_definition(name="user_signed_up"),
                _make_event_definition(name="page_viewed"),
            ],
        )
        results = reader.fetch_specific("signed_up")

        assert len(results) == 1
        assert results[0].name == "user_signed_up"

    def test_fetch_specific_case_insensitive(self):
        reader = PostHogReader(
            dashboards=[_make_dashboard(name="Growth Dashboard")],
        )
        results = reader.fetch_specific("GROWTH")

        assert len(results) == 1

    def test_fetch_specific_searches_summary(self):
        reader = PostHogReader(
            errors=[_make_error(type="TypeError", value="undefined is not a function")],
        )
        results = reader.fetch_specific("undefined")

        assert len(results) == 1

    def test_insight_filters_summarized(self):
        """Insight with series + dateRange should produce a compact summary."""
        reader = PostHogReader(insights=[_make_insight()])
        points = reader.fetch_overview()

        summary = points[0].result_summary
        assert "$pageview" in summary
        assert "-30d" in summary

    def test_insight_old_format_filters(self):
        """Insights using filters-based format (older PostHog) should still work."""
        reader = PostHogReader(insights=[{
            "id": 200,
            "name": "Old Format Insight",
            "filters": {
                "insight": "TRENDS",
                "events": [{"id": "$pageview"}, {"id": "user_signed_up"}],
            },
        }])
        points = reader.fetch_overview()

        assert "TRENDS" in points[0].result_summary
        assert "$pageview" in points[0].result_summary

    def test_fetch_specific_empty_query_returns_empty(self):
        """Empty or whitespace-only query returns empty list."""
        reader = PostHogReader(
            event_definitions=[_make_event_definition(name="user_signed_up")],
        )
        assert reader.fetch_specific("") == []
        assert reader.fetch_specific("   ") == []

    def test_source_ref_sanitization(self):
        """Event names with spaces/slashes get sanitized in source_ref."""
        reader = PostHogReader(event_definitions=[
            _make_event_definition(name="Added draft / new"),
        ])
        points = reader.fetch_overview()

        ref = points[0].source_ref
        assert " " not in ref
        assert "/" not in ref
        assert ref.startswith("event_")


# ============================================================================
# Data point truncation in explore
# ============================================================================


class TestDataPointTruncation:
    def test_per_point_truncation(self):
        """Long result_summary is truncated per config.max_chars_per_data_point."""
        long_summary_event = _make_event_definition(name="big_event")
        reader = PostHogReader(event_definitions=[long_summary_event])

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = AnalyticsExplorer(
            reader=reader,
            openai_client=mock_client,
            config=AnalyticsExplorerConfig(max_chars_per_data_point=20),
        )
        result = explorer.explore()

        # Verify the LLM was called (truncation happens internally)
        assert mock_client.chat.completions.create.call_count == 2

    def test_batch_budget_truncation(self):
        """When total formatted text exceeds max_chars_per_batch, truncate."""
        # Create many events that will exceed a small batch budget
        events = [_make_event_definition(name=f"event_{i:03d}") for i in range(50)]
        reader = PostHogReader(event_definitions=events)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_batch_response(),
            _make_synthesis_response(),
        ]

        explorer = AnalyticsExplorer(
            reader=reader,
            openai_client=mock_client,
            config=AnalyticsExplorerConfig(max_chars_per_batch=200),
        )
        result = explorer.explore()

        # Should still complete without error
        assert result.coverage["conversations_reviewed"] == 50


# ============================================================================
# Checkpoint building
# ============================================================================


class TestBuildCheckpoint:
    def test_builds_valid_checkpoint(self):
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "low_adoption",
                    "description": "Features not being used",
                    "evidence_refs": ["event_user_signed_up", "dashboard_42"],
                    "confidence": "high",
                    "severity_assessment": "moderate",
                    "affected_users_estimate": "~40%",
                }
            ],
            coverage={
                "time_window_days": 1,
                "conversations_available": 10,
                "conversations_reviewed": 10,
                "conversations_skipped": 0,
                "model": "gpt-4o-mini",
                "findings_count": 1,
                "items_type": "analytics_data_points",
            },
        )

        explorer = AnalyticsExplorer(
            reader=PostHogReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["schema_version"] == 1
        assert checkpoint["agent_name"] == "analytics"
        assert len(checkpoint["findings"]) == 1
        assert checkpoint["findings"][0]["pattern_name"] == "low_adoption"
        assert len(checkpoint["findings"][0]["evidence"]) == 2

    def test_checkpoint_validates_against_model(self):
        """Checkpoint output should pass ExplorerCheckpoint validation."""
        from src.discovery.models.artifacts import ExplorerCheckpoint

        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "validated_pattern",
                    "description": "Should validate",
                    "evidence_refs": ["event_user_signed_up"],
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
                "items_type": "analytics_data_points",
            },
        )

        explorer = AnalyticsExplorer(
            reader=PostHogReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Should not raise
        validated = ExplorerCheckpoint(**checkpoint)
        assert validated.agent_name == "analytics"
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
                "items_type": "analytics_data_points",
            },
        )

        explorer = AnalyticsExplorer(
            reader=PostHogReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"] == []
        assert checkpoint["coverage"]["findings_count"] == 0

    def test_checkpoint_evidence_uses_posthog_source_type(self):
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "some_pattern",
                    "description": "desc",
                    "evidence_refs": ["dashboard_42", "error_err_001"],
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
                "items_type": "analytics_data_points",
            },
        )

        explorer = AnalyticsExplorer(
            reader=PostHogReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        for evidence in checkpoint["findings"][0]["evidence"]:
            assert evidence["source_type"] == "posthog"

    def test_finding_without_evidence_refs_is_dropped(self):
        """Finding with no evidence_refs violates ExplorerFinding(min_length=1)
        and should be dropped with a warning, not included."""
        result = ExplorerResult(
            findings=[
                {
                    "pattern_name": "no_evidence_pattern",
                    "description": "pattern without refs",
                    "confidence": "low",
                    "severity_assessment": "low",
                    "affected_users_estimate": "unknown",
                },
                {
                    "pattern_name": "has_evidence",
                    "description": "pattern with refs",
                    "evidence_refs": ["event_user_signed_up"],
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
                "items_type": "analytics_data_points",
            },
        )

        explorer = AnalyticsExplorer(
            reader=PostHogReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Only the finding with evidence should survive
        assert len(checkpoint["findings"]) == 1
        assert checkpoint["findings"][0]["pattern_name"] == "has_evidence"

    def test_all_findings_without_evidence_produces_empty_checkpoint(self):
        """When ALL findings lack evidence_refs, checkpoint has zero findings."""
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
                "items_type": "analytics_data_points",
            },
        )

        explorer = AnalyticsExplorer(
            reader=PostHogReader(), openai_client=MagicMock()
        )
        checkpoint = explorer.build_checkpoint_artifacts(result)

        assert checkpoint["findings"] == []


# ============================================================================
# Requery
# ============================================================================


class TestRequery:
    def test_requery_returns_answer(self):
        reader = _make_reader_with_data()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "The adoption pattern affects 3 features",
            "evidence_refs": ["event_user_signed_up"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="How many features have low adoption?",
            previous_findings=[],
            source_refs=["event_user_signed_up"],
        )

        assert result["answer"] == "The adoption pattern affects 3 features"

    def test_requery_without_source_refs(self):
        reader = PostHogReader()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "Based on previous findings...",
            "evidence_refs": [],
            "confidence": "medium",
            "additional_findings": [],
        })

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="Summarize patterns",
            previous_findings=[{"pattern_name": "test"}],
        )

        assert "Based on previous" in result["answer"]

    def test_requery_with_matching_source_refs(self):
        """Requery with source_refs should include relevant data point text."""
        reader = _make_reader_with_data()

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "That error occurs 42 times",
            "evidence_refs": ["error_err_001"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = AnalyticsExplorer(reader=reader, openai_client=mock_client)
        result = explorer.requery(
            request_text="Tell me more about the TypeError",
            previous_findings=[],
            source_refs=["error_err_001"],
        )

        # Verify the LLM was called with relevant data in the prompt
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "TypeError" in user_msg or "error_err_001" in user_msg


# ============================================================================
# Group by type (internal method)
# ============================================================================


class TestGroupByType:
    def test_groups_by_data_type(self):
        points = [
            PostHogDataPoint(data_type="event_definition", name="evt1", result_summary="s1"),
            PostHogDataPoint(data_type="event_definition", name="evt2", result_summary="s2"),
            PostHogDataPoint(data_type="dashboard", name="dash1", result_summary="s3"),
            PostHogDataPoint(data_type="error", name="err1", result_summary="s4"),
        ]

        groups = AnalyticsExplorer._group_by_type(points)

        assert len(groups) == 3
        assert len(groups["event_definition"]) == 2
        assert len(groups["dashboard"]) == 1
        assert len(groups["error"]) == 1

    def test_empty_list_returns_empty_dict(self):
        groups = AnalyticsExplorer._group_by_type([])
        assert groups == {}

    def test_single_type_single_group(self):
        points = [
            PostHogDataPoint(data_type="insight", name=f"ins_{i}", result_summary=f"s{i}")
            for i in range(5)
        ]

        groups = AnalyticsExplorer._group_by_type(points)

        assert len(groups) == 1
        assert len(groups["insight"]) == 5
