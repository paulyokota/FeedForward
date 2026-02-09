"""
Pipeline Dry Run Preview Tests

Tests for the dry run preview feature (Issue #75):
- _store_dry_run_preview() helper
- GET /api/pipeline/status/{run_id}/preview endpoint
- Cleanup logic
- Edge cases

Run with: pytest tests/api/test_pipeline_dry_run_preview.py -v
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.deps import get_db
from src.api.schemas.pipeline import DryRunPreview, DryRunSample, DryRunClassificationBreakdown
import src.api.routers.pipeline as pipeline_module

pytestmark = pytest.mark.medium


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_module_state():
    """Clear module-level state before and after each test."""
    # Clear before test
    pipeline_module._active_runs.clear()
    pipeline_module._dry_run_previews.clear()

    yield

    # Clear after test
    pipeline_module._active_runs.clear()
    pipeline_module._dry_run_previews.clear()


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    return mock_conn


@pytest.fixture
def client(mock_db):
    """Create a test client with overridden dependencies."""
    app.dependency_overrides[get_db] = lambda: mock_db

    yield TestClient(app)

    # Clean up dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sample_classification_results():
    """Sample classification results as returned by run_pipeline_async."""
    return [
        {
            "conversation_id": "conv_001",
            "source_body": "I'm having trouble with the login feature. It keeps timing out when I try to authenticate with SSO.",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": ["authentication", "sso", "login"],
            },
            "stage2_result": None,
            "support_messages": [{"body": "Thanks for reporting this."}],
        },
        {
            "conversation_id": "conv_002",
            "source_body": "Can you add dark mode to the dashboard?",
            "stage1_result": {
                "conversation_type": "feature_request",
                "confidence": "high",
                "themes": ["ui", "dark_mode", "dashboard"],
            },
            "stage2_result": None,
            "support_messages": [],
        },
        {
            "conversation_id": "conv_003",
            "source_body": "How do I export data to CSV?",
            "stage1_result": {
                "conversation_type": "how_to_question",
                "confidence": "medium",
                "themes": ["export", "csv"],
            },
            "stage2_result": None,
            "support_messages": [{"body": "Here's how to do that."}],
        },
        {
            "conversation_id": "conv_004",
            "source_body": "The API returns 500 errors when I send large payloads.",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": ["api", "errors", "performance"],
            },
            "stage2_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
            },
            "support_messages": [],
        },
        {
            "conversation_id": "conv_005",
            "source_body": "Great service! Love the new features.",
            "stage1_result": {
                "conversation_type": "praise",
                "confidence": "high",
                "themes": [],
            },
            "stage2_result": None,
            "support_messages": [],
        },
    ]


@pytest.fixture
def sample_preview(sample_classification_results):
    """Create a sample DryRunPreview object."""
    return DryRunPreview(
        run_id=42,
        classification_breakdown=DryRunClassificationBreakdown(
            by_type={"bug_report": 2, "feature_request": 1, "how_to_question": 1, "praise": 1},
            by_confidence={"high": 4, "medium": 1},
        ),
        samples=[
            DryRunSample(
                conversation_id="conv_001",
                snippet="I'm having trouble with the login feature. It keeps timing out...",
                conversation_type="bug_report",
                confidence="high",
                themes=["authentication", "sso", "login"],
                has_support_response=True,
            ),
        ],
        top_themes=[("authentication", 1), ("sso", 1), ("login", 1), ("ui", 1), ("dark_mode", 1)],
        total_classified=5,
        timestamp=datetime.now(timezone.utc),
    )


# -----------------------------------------------------------------------------
# _store_dry_run_preview() Helper Tests
# -----------------------------------------------------------------------------


class TestStoreDryRunPreview:
    """Tests for the _store_dry_run_preview() helper function."""

    def test_builds_correct_classification_breakdown_by_type(self, sample_classification_results):
        """Test that classification breakdown counts types correctly."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, sample_classification_results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        by_type = preview.classification_breakdown.by_type
        assert by_type["bug_report"] == 2
        assert by_type["feature_request"] == 1
        assert by_type["how_to_question"] == 1
        assert by_type["praise"] == 1

    def test_builds_correct_classification_breakdown_by_confidence(self, sample_classification_results):
        """Test that classification breakdown counts confidence levels correctly."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, sample_classification_results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        by_confidence = preview.classification_breakdown.by_confidence
        assert by_confidence["high"] == 4
        assert by_confidence["medium"] == 1

    def test_samples_five_to_ten_conversations(self, sample_classification_results):
        """Test that 5-10 conversation samples are included."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, sample_classification_results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # With 5 results, should have all 5 as samples
        assert len(preview.samples) == 5

    def test_samples_prioritize_type_diversity(self):
        """Test that samples prioritize type diversity (one of each type first)."""
        run_id = 100

        # Create results with 10 items, mostly bug_reports
        results = [
            {
                "conversation_id": f"conv_{i:03d}",
                "source_body": f"Bug report content {i}",
                "stage1_result": {
                    "conversation_type": "bug_report",
                    "confidence": "high",
                    "themes": [],
                },
                "stage2_result": None,
                "support_messages": [],
            }
            for i in range(8)
        ]
        # Add two different types
        results.append({
            "conversation_id": "conv_feature",
            "source_body": "Feature request content",
            "stage1_result": {
                "conversation_type": "feature_request",
                "confidence": "high",
                "themes": [],
            },
            "stage2_result": None,
            "support_messages": [],
        })
        results.append({
            "conversation_id": "conv_howto",
            "source_body": "How to question content",
            "stage1_result": {
                "conversation_type": "how_to_question",
                "confidence": "medium",
                "themes": [],
            },
            "stage2_result": None,
            "support_messages": [],
        })

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Should have exactly 10 samples
        assert len(preview.samples) == 10

        # Check that different types are represented in samples
        sample_types = {s.conversation_type for s in preview.samples}
        assert "bug_report" in sample_types
        assert "feature_request" in sample_types
        assert "how_to_question" in sample_types

    def test_computes_top_themes_correctly(self, sample_classification_results):
        """Test that top themes are computed correctly."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, sample_classification_results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Verify top themes is a list of tuples (theme, count)
        assert len(preview.top_themes) <= 5
        for theme, count in preview.top_themes:
            assert isinstance(theme, str)
            assert isinstance(count, int)
            assert count > 0

    def test_handles_empty_results_list(self):
        """Test that empty results list doesn't store a preview."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, [])

        # Should not store preview for empty results
        assert run_id not in pipeline_module._dry_run_previews

    def test_uses_stage2_type_when_available(self):
        """Test that stage2 classification type is used when available."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": {
                "conversation_type": "general_inquiry",
                "confidence": "low",
                "themes": [],
            },
            "stage2_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
            },
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Should use stage2 type
        assert preview.classification_breakdown.by_type["bug_report"] == 1
        assert "general_inquiry" not in preview.classification_breakdown.by_type

        # Sample should also use stage2 type
        assert preview.samples[0].conversation_type == "bug_report"
        assert preview.samples[0].confidence == "high"

    def test_snippet_truncates_to_200_chars(self):
        """Test that snippet is truncated to first 200 characters."""
        run_id = 100

        long_body = "A" * 500  # 500 characters

        results = [{
            "conversation_id": "conv_001",
            "source_body": long_body,
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": [],
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert len(preview.samples[0].snippet) == 200

    def test_has_support_response_is_set_correctly(self, sample_classification_results):
        """Test that has_support_response is set based on support_messages."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, sample_classification_results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Find samples and verify support response flag
        sample_map = {s.conversation_id: s for s in preview.samples}

        # conv_001 has support messages
        if "conv_001" in sample_map:
            assert sample_map["conv_001"].has_support_response is True

        # conv_002 has no support messages
        if "conv_002" in sample_map:
            assert sample_map["conv_002"].has_support_response is False

    def test_limits_themes_per_sample_to_5(self):
        """Test that themes per sample are limited to 5."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": ["theme1", "theme2", "theme3", "theme4", "theme5", "theme6", "theme7"],
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert len(preview.samples[0].themes) == 5


# -----------------------------------------------------------------------------
# Preview Endpoint Tests
# -----------------------------------------------------------------------------


class TestPreviewEndpoint:
    """Tests for GET /api/pipeline/status/{run_id}/preview endpoint."""

    def test_returns_404_for_non_existent_run(self, client, mock_db):
        """Test that 404 is returned for non-existent run_id."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)
        mock_cursor.fetchone.return_value = None

        response = client.get("/api/pipeline/status/999/preview")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_404_for_non_dry_run(self, client, mock_db):
        """Test that 404 is returned when run stored conversations (not a dry run)."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        # Run exists with conversations_stored > 0 (not a dry run)
        mock_cursor.fetchone.return_value = {
            "id": 42,
            "status": "completed",
            "conversations_stored": 100,  # Not a dry run
        }

        response = client.get("/api/pipeline/status/42/preview")

        assert response.status_code == 404
        assert "not a dry run" in response.json()["detail"].lower()

    def test_returns_404_for_expired_preview(self, client, mock_db):
        """Test that 404 is returned when preview has expired."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        # Run exists and was a dry run (stored = 0)
        mock_cursor.fetchone.return_value = {
            "id": 42,
            "status": "completed",
            "conversations_stored": 0,
        }

        # But preview is not in memory (expired or server restarted)
        # _dry_run_previews is already cleared by fixture

        response = client.get("/api/pipeline/status/42/preview")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        assert "expired" in response.json()["detail"].lower() or "cleaned up" in response.json()["detail"].lower()

    def test_returns_valid_preview_for_dry_run(self, client, mock_db, sample_preview):
        """Test that valid preview is returned for dry run."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        # Run exists and was a dry run
        mock_cursor.fetchone.return_value = {
            "id": 42,
            "status": "completed",
            "conversations_stored": 0,
        }

        # Store preview in memory
        pipeline_module._dry_run_previews[42] = sample_preview

        response = client.get("/api/pipeline/status/42/preview")

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == 42
        assert data["total_classified"] == 5

    def test_response_matches_dry_run_preview_schema(self, client, mock_db, sample_preview):
        """Test that response matches DryRunPreview schema."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_cursor.fetchone.return_value = {
            "id": 42,
            "status": "completed",
            "conversations_stored": 0,
        }

        pipeline_module._dry_run_previews[42] = sample_preview

        response = client.get("/api/pipeline/status/42/preview")

        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields are present
        assert "run_id" in data
        assert "classification_breakdown" in data
        assert "samples" in data
        assert "top_themes" in data
        assert "total_classified" in data
        assert "timestamp" in data

        # Verify classification_breakdown structure
        assert "by_type" in data["classification_breakdown"]
        assert "by_confidence" in data["classification_breakdown"]

        # Verify samples structure
        if data["samples"]:
            sample = data["samples"][0]
            assert "conversation_id" in sample
            assert "snippet" in sample
            assert "conversation_type" in sample
            assert "confidence" in sample
            assert "themes" in sample
            assert "has_support_response" in sample

    def test_returns_404_for_null_conversations_stored(self, client, mock_db):
        """Test behavior when conversations_stored is NULL (run may still be in progress)."""
        mock_cursor = Mock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        # Run exists with conversations_stored = None (still running)
        mock_cursor.fetchone.return_value = {
            "id": 42,
            "status": "running",
            "conversations_stored": None,
        }

        # No preview stored yet
        response = client.get("/api/pipeline/status/42/preview")

        # Should return 404 because preview doesn't exist
        assert response.status_code == 404


# -----------------------------------------------------------------------------
# Cleanup Logic Tests
# -----------------------------------------------------------------------------


class TestCleanupLogic:
    """Tests for dry run preview cleanup logic."""

    def test_cleanup_triggered_when_more_than_5_previews(self):
        """Test that cleanup is triggered when >5 previews are stored."""
        # Clear any existing previews
        pipeline_module._dry_run_previews.clear()

        # Store 6 previews with different timestamps
        for i in range(6):
            preview = DryRunPreview(
                run_id=i,
                classification_breakdown=DryRunClassificationBreakdown(
                    by_type={"bug_report": 1},
                    by_confidence={"high": 1},
                ),
                samples=[],
                top_themes=[],
                total_classified=1,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=6 - i),  # Oldest to newest
            )
            pipeline_module._dry_run_previews[i] = preview

        # Now store one more, which should trigger cleanup
        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test",
            "stage1_result": {"conversation_type": "bug_report", "confidence": "high", "themes": []},
            "stage2_result": None,
            "support_messages": [],
        }]
        pipeline_module._store_dry_run_preview(100, results)

        # Should have at most 5 previews after cleanup
        assert len(pipeline_module._dry_run_previews) <= 5

        # The newest previews should be kept
        assert 100 in pipeline_module._dry_run_previews  # Most recent
        assert 5 in pipeline_module._dry_run_previews    # Second most recent

    def test_oldest_previews_removed_first(self):
        """Test that oldest previews are removed first during cleanup.

        Note: Cleanup is designed to be called BEFORE storing a new preview,
        so it keeps N-1 items to make room. This test verifies that after
        storing a new preview, the oldest items are removed.
        """
        pipeline_module._dry_run_previews.clear()

        # Store 7 previews with known timestamps
        base_time = datetime.now(timezone.utc)
        for i in range(7):
            preview = DryRunPreview(
                run_id=i,
                classification_breakdown=DryRunClassificationBreakdown(
                    by_type={"bug_report": 1},
                    by_confidence={"high": 1},
                ),
                samples=[],
                top_themes=[],
                total_classified=1,
                timestamp=base_time - timedelta(hours=7 - i),  # run_id 0 is oldest
            )
            pipeline_module._dry_run_previews[i] = preview

        # Store a new preview (which triggers cleanup proactively)
        results = [{
            "conversation_id": "conv_new",
            "source_body": "Test",
            "stage1_result": {"conversation_type": "bug_report", "confidence": "high", "themes": []},
            "stage2_result": None,
            "support_messages": [],
        }]
        pipeline_module._store_dry_run_preview(100, results)

        # Should have exactly 5 previews after cleanup + store
        assert len(pipeline_module._dry_run_previews) == 5

        # The new preview (run_id=100) should be present
        assert 100 in pipeline_module._dry_run_previews

        # Run IDs 0-2 (oldest 3) should be removed
        assert 0 not in pipeline_module._dry_run_previews
        assert 1 not in pipeline_module._dry_run_previews
        assert 2 not in pipeline_module._dry_run_previews

        # Run IDs 3-6 (newest 4) plus new one (100) should remain = 4 + 1 = 5
        assert 3 in pipeline_module._dry_run_previews
        assert 4 in pipeline_module._dry_run_previews
        assert 5 in pipeline_module._dry_run_previews
        assert 6 in pipeline_module._dry_run_previews

    def test_cleanup_does_nothing_when_under_limit(self):
        """Test that cleanup doesn't remove anything when under the limit.

        Note: With proactive cleanup, having fewer than MAX items means
        no cleanup is needed before storing a new preview.
        """
        pipeline_module._dry_run_previews.clear()

        # Store 4 previews (under the limit of 5)
        for i in range(4):
            preview = DryRunPreview(
                run_id=i,
                classification_breakdown=DryRunClassificationBreakdown(
                    by_type={"bug_report": 1},
                    by_confidence={"high": 1},
                ),
                samples=[],
                top_themes=[],
                total_classified=1,
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
            )
            pipeline_module._dry_run_previews[i] = preview

        # Trigger cleanup (should do nothing since we're under limit)
        pipeline_module._cleanup_old_dry_run_previews()

        # All 4 should remain
        assert len(pipeline_module._dry_run_previews) == 4
        for i in range(4):
            assert i in pipeline_module._dry_run_previews

        # Now store a 5th preview - should work without cleanup needed
        results = [{
            "conversation_id": "conv_new",
            "source_body": "Test",
            "stage1_result": {"conversation_type": "bug_report", "confidence": "high", "themes": []},
            "stage2_result": None,
            "support_messages": [],
        }]
        pipeline_module._store_dry_run_preview(100, results)

        # Should now have exactly 5 previews
        assert len(pipeline_module._dry_run_previews) == 5
        assert 100 in pipeline_module._dry_run_previews


# -----------------------------------------------------------------------------
# Edge Case Tests
# -----------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases in dry run preview functionality."""

    def test_empty_classification_results(self):
        """Test handling of empty classification results."""
        run_id = 100

        pipeline_module._store_dry_run_preview(run_id, [])

        # Should not create a preview for empty results
        assert run_id not in pipeline_module._dry_run_previews

    def test_results_without_themes_field(self):
        """Test handling of results without themes field in stage1_result."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                # No themes field
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert preview.top_themes == []  # No themes to count
        assert preview.samples[0].themes == []  # Empty themes list

    def test_results_with_non_list_themes(self):
        """Test handling of results with non-list themes value."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": "not a list",  # Invalid type
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert preview.samples[0].themes == []  # Should handle gracefully

    def test_large_number_of_results(self):
        """Test handling of large number of results (1000+)."""
        run_id = 100

        # Generate 1000+ results
        results = []
        types = ["bug_report", "feature_request", "how_to_question", "praise", "complaint"]
        for i in range(1200):
            results.append({
                "conversation_id": f"conv_{i:04d}",
                "source_body": f"Content for conversation {i}. " * 10,
                "stage1_result": {
                    "conversation_type": types[i % len(types)],
                    "confidence": "high" if i % 3 == 0 else "medium",
                    "themes": [f"theme_{i % 20}"],
                },
                "stage2_result": None,
                "support_messages": [{"body": "Support"}] if i % 2 == 0 else [],
            })

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Should have correct total count
        assert preview.total_classified == 1200

        # Should have 10 samples (max)
        assert len(preview.samples) == 10

        # Breakdown should have all types
        assert len(preview.classification_breakdown.by_type) == 5

        # Top themes should be limited to 5
        assert len(preview.top_themes) <= 5

    def test_results_with_empty_source_body(self):
        """Test handling of results with empty source_body."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "",  # Empty body
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": [],
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert preview.samples[0].snippet == ""

    def test_results_with_null_source_body(self):
        """Test handling of results with None source_body."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": None,  # None body
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": [],
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert preview.samples[0].snippet == ""

    def test_results_with_missing_stage1_result(self):
        """Test handling of results with missing stage1_result."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": None,  # Missing stage1
            "stage2_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
            },
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Should use stage2 values
        assert preview.classification_breakdown.by_type["bug_report"] == 1
        assert preview.samples[0].conversation_type == "bug_report"

    def test_results_with_both_stages_missing(self):
        """Test handling of results with both stage results missing."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": None,
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Should default to "unknown" type and "low" confidence
        assert preview.classification_breakdown.by_type["unknown"] == 1
        assert preview.classification_breakdown.by_confidence["low"] == 1

    def test_results_with_empty_themes_list(self):
        """Test handling of results with empty themes list."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": [],  # Empty list
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None
        assert preview.top_themes == []

    def test_themes_with_empty_string_entries(self):
        """Test handling of themes list containing empty strings."""
        run_id = 100

        results = [{
            "conversation_id": "conv_001",
            "source_body": "Test content",
            "stage1_result": {
                "conversation_type": "bug_report",
                "confidence": "high",
                "themes": ["valid_theme", "", "another_valid", ""],  # Contains empty strings
            },
            "stage2_result": None,
            "support_messages": [],
        }]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Empty strings should not be counted in top_themes
        theme_names = [t[0] for t in preview.top_themes]
        assert "" not in theme_names

    def test_multiple_results_same_type_different_confidence(self):
        """Test counting with same type but different confidence levels."""
        run_id = 100

        results = [
            {
                "conversation_id": "conv_001",
                "source_body": "Test 1",
                "stage1_result": {
                    "conversation_type": "bug_report",
                    "confidence": "high",
                    "themes": [],
                },
                "stage2_result": None,
                "support_messages": [],
            },
            {
                "conversation_id": "conv_002",
                "source_body": "Test 2",
                "stage1_result": {
                    "conversation_type": "bug_report",
                    "confidence": "medium",
                    "themes": [],
                },
                "stage2_result": None,
                "support_messages": [],
            },
            {
                "conversation_id": "conv_003",
                "source_body": "Test 3",
                "stage1_result": {
                    "conversation_type": "bug_report",
                    "confidence": "low",
                    "themes": [],
                },
                "stage2_result": None,
                "support_messages": [],
            },
        ]

        pipeline_module._store_dry_run_preview(run_id, results)

        preview = pipeline_module._dry_run_previews.get(run_id)
        assert preview is not None

        # Type count should be 3 bug_reports
        assert preview.classification_breakdown.by_type["bug_report"] == 3

        # Confidence counts should be separate
        assert preview.classification_breakdown.by_confidence["high"] == 1
        assert preview.classification_breakdown.by_confidence["medium"] == 1
        assert preview.classification_breakdown.by_confidence["low"] == 1
