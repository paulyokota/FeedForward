"""
Context Gaps Endpoint Tests (Phase 4)

Tests for the /api/analytics/context-gaps endpoint.
Run with: pytest tests/test_context_gaps_endpoint.py -v

This endpoint analyzes context_usage_logs to identify documentation gaps.

Owner: Kenji (Testing)

Note: Full endpoint integration tests with database mocking are complex due to
psycopg2's generator-based dependency injection. These tests focus on:
1. Response structure validation (empty data case works with mocked DB)
2. Query parameter validation (days, limit bounds)
3. CLI script unit tests (analyze_context_gaps.py functions)

For integration testing with real data, use functional tests against a live DB.
"""

import pytest

# Mark entire module as medium - uses TestClient with mocked dependencies
pytestmark = pytest.mark.medium
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from collections import Counter

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient


# =============================================================================
# Unit Tests - Context Gap Aggregation Logic
# =============================================================================


class TestContextGapAggregationLogic:
    """Unit tests for the context gap aggregation logic used by the endpoint."""

    def test_aggregate_gaps_from_rows(self):
        """Test aggregating context gaps from row data."""
        # Simulating the logic from the endpoint
        rows = [
            {"context_used": ["A", "B"], "context_gaps": ["X"], "product_area": "pub"},
            {"context_used": ["A"], "context_gaps": ["X", "Y"], "product_area": "pub"},
            {"context_used": ["C"], "context_gaps": ["Z"], "product_area": "bill"},
        ]

        gap_counter: Counter = Counter()
        used_counter: Counter = Counter()
        gaps_by_area: dict = {}
        total_with_gaps = 0
        total_with_context = 0

        for row in rows:
            context_used = row["context_used"]
            context_gaps = row["context_gaps"]
            product_area = row["product_area"] or "unknown"

            if product_area not in gaps_by_area:
                gaps_by_area[product_area] = Counter()

            if context_gaps and isinstance(context_gaps, list):
                total_with_gaps += 1
                for gap in context_gaps:
                    if isinstance(gap, str) and gap.strip():
                        gap_counter[gap] += 1
                        gaps_by_area[product_area][gap] += 1

            if context_used and isinstance(context_used, list):
                total_with_context += 1
                for used in context_used:
                    if isinstance(used, str) and used.strip():
                        used_counter[used] += 1

        # Verify aggregation
        assert total_with_gaps == 3
        assert total_with_context == 3
        assert gap_counter["X"] == 2  # Most common gap
        assert gap_counter["Y"] == 1
        assert gap_counter["Z"] == 1
        assert used_counter["A"] == 2  # Most common used context
        assert "pub" in gaps_by_area
        assert "bill" in gaps_by_area
        assert gaps_by_area["pub"]["X"] == 2

    def test_filters_empty_string_gaps(self):
        """Test that empty string gaps are filtered out."""
        rows = [
            {"context_used": [], "context_gaps": ["", "  ", "Valid"], "product_area": "test"},
        ]

        gap_counter: Counter = Counter()
        for row in rows:
            context_gaps = row["context_gaps"]
            if context_gaps and isinstance(context_gaps, list):
                for gap in context_gaps:
                    if isinstance(gap, str) and gap.strip():
                        gap_counter[gap] += 1

        assert len(gap_counter) == 1
        assert gap_counter["Valid"] == 1

    def test_null_product_area_defaults_to_unknown(self):
        """Test that null product_area defaults to 'unknown'."""
        rows = [
            {"context_used": [], "context_gaps": ["Gap1"], "product_area": None},
        ]

        gaps_by_area: dict = {}
        for row in rows:
            product_area = row["product_area"] or "unknown"
            if product_area not in gaps_by_area:
                gaps_by_area[product_area] = Counter()
            gaps_by_area[product_area]["Gap1"] += 1

        assert "unknown" in gaps_by_area
        assert gaps_by_area["unknown"]["Gap1"] == 1

    def test_handles_null_context_fields(self):
        """Test handling of null context_used and context_gaps."""
        rows = [
            {"context_used": None, "context_gaps": None, "product_area": "test"},
        ]

        total_with_gaps = 0
        total_with_context = 0

        for row in rows:
            context_used = row["context_used"]
            context_gaps = row["context_gaps"]

            if context_gaps and isinstance(context_gaps, list):
                total_with_gaps += 1

            if context_used and isinstance(context_used, list):
                total_with_context += 1

        assert total_with_gaps == 0
        assert total_with_context == 0

    def test_recommendation_generation_logic(self):
        """Test the recommendation generation logic."""
        # Top gaps list (like what the endpoint returns)
        top_gaps = [("Pinterest API rate limits", 25), ("Timezone handling", 10)]

        # Recommendation generation logic from endpoint
        recommendation = None
        if top_gaps:
            top_gap_text, top_gap_count = top_gaps[0]
            recommendation = (
                f"Add documentation for \"{top_gap_text[:50]}...\" "
                f"({top_gap_count} occurrences)"
                if len(top_gap_text) > 50
                else f"Add documentation for \"{top_gap_text}\" ({top_gap_count} occurrences)"
            )

        assert recommendation is not None
        assert "Pinterest API rate limits" in recommendation
        assert "25 occurrences" in recommendation

    def test_recommendation_truncates_long_text(self):
        """Test that long gap text is truncated in recommendation."""
        long_text = "A" * 100
        top_gaps = [(long_text, 5)]

        recommendation = None
        if top_gaps:
            top_gap_text, top_gap_count = top_gaps[0]
            recommendation = (
                f"Add documentation for \"{top_gap_text[:50]}...\" "
                f"({top_gap_count} occurrences)"
                if len(top_gap_text) > 50
                else f"Add documentation for \"{top_gap_text}\" ({top_gap_count} occurrences)"
            )

        assert "..." in recommendation
        assert len(recommendation) < len(long_text) + 50


# =============================================================================
# Endpoint Validation Tests
# =============================================================================


@pytest.fixture
def mock_db_generator():
    """Create a mock database connection that works with FastAPI's generator dependency."""
    db = MagicMock()
    cursor = MagicMock()

    # Setup context manager for db.cursor()
    cursor_cm = MagicMock()
    cursor_cm.__enter__ = MagicMock(return_value=cursor)
    cursor_cm.__exit__ = MagicMock(return_value=False)
    db.cursor.return_value = cursor_cm

    # Default empty results
    cursor.fetchall.return_value = []

    return db, cursor


@pytest.fixture
def client(mock_db_generator):
    """Create test client with mocked database dependency."""
    db, cursor = mock_db_generator

    # Import here to avoid import errors during collection
    from api.main import app
    # IMPORTANT: Must match the import path used by the routers (src.api.deps)
    # not the shorter path (api.deps) - they're different Python objects!
    from src.api.deps import get_db

    # Override dependency with a generator that yields our mock
    def mock_get_db():
        yield db

    app.dependency_overrides[get_db] = mock_get_db

    yield TestClient(app)

    # Clean up
    app.dependency_overrides.clear()


class TestContextGapsEndpointValidation:
    """Validation tests for context-gaps endpoint parameters."""

    def test_endpoint_returns_valid_structure_empty_data(self, mock_db_generator, client):
        """Test that endpoint returns valid structure with empty data."""
        db, cursor = mock_db_generator
        cursor.fetchall.return_value = []

        response = client.get("/api/analytics/context-gaps")

        assert response.status_code == 200
        data = response.json()

        # Verify required fields exist
        assert "period_start" in data
        assert "period_end" in data
        assert "total_extractions" in data
        assert "extractions_with_gaps" in data
        assert "extractions_with_context" in data
        assert "top_gaps" in data
        assert "top_used" in data
        assert "gaps_by_product_area" in data
        assert "recommendation" in data

        # Verify empty data values
        assert data["total_extractions"] == 0
        assert data["top_gaps"] == []
        assert data["recommendation"] is None

    def test_days_minimum_validation(self, mock_db_generator, client):
        """Test that days parameter rejects values < 1."""
        response = client.get("/api/analytics/context-gaps?days=0")
        assert response.status_code == 422  # Validation error

    def test_days_maximum_validation(self, mock_db_generator, client):
        """Test that days parameter rejects values > 90."""
        response = client.get("/api/analytics/context-gaps?days=100")
        assert response.status_code == 422  # Validation error

    def test_limit_minimum_validation(self, mock_db_generator, client):
        """Test that limit parameter rejects values < 1."""
        response = client.get("/api/analytics/context-gaps?limit=0")
        assert response.status_code == 422  # Validation error

    def test_limit_maximum_validation(self, mock_db_generator, client):
        """Test that limit parameter rejects values > 100."""
        response = client.get("/api/analytics/context-gaps?limit=150")
        assert response.status_code == 422  # Validation error

    def test_days_valid_range(self, mock_db_generator, client):
        """Test that days parameter accepts valid values."""
        db, cursor = mock_db_generator
        cursor.fetchall.return_value = []

        # Test lower bound
        response = client.get("/api/analytics/context-gaps?days=1")
        assert response.status_code == 200

        # Test upper bound
        response = client.get("/api/analytics/context-gaps?days=90")
        assert response.status_code == 200

    def test_limit_valid_range(self, mock_db_generator, client):
        """Test that limit parameter accepts valid values."""
        db, cursor = mock_db_generator
        cursor.fetchall.return_value = []

        # Test lower bound
        response = client.get("/api/analytics/context-gaps?limit=1")
        assert response.status_code == 200

        # Test upper bound
        response = client.get("/api/analytics/context-gaps?limit=100")
        assert response.status_code == 200

    def test_pipeline_run_id_not_found(self, mock_db_generator, client):
        """Test 404 response for nonexistent pipeline run."""
        db, cursor = mock_db_generator
        cursor.fetchone.return_value = None  # Pipeline run not found

        response = client.get("/api/analytics/context-gaps?pipeline_run_id=99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# =============================================================================
# Script Tests (analyze_context_gaps.py)
# =============================================================================


class TestAnalyzeContextGapsScript:
    """Tests for the analyze_context_gaps.py CLI script functions."""

    def test_context_gap_analysis_dataclass(self):
        """Test ContextGapAnalysis dataclass initialization."""
        # Import here to avoid collection issues
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

        from analyze_context_gaps import ContextGapAnalysis

        now = datetime.now(timezone.utc)
        analysis = ContextGapAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_extractions=100,
            total_with_gaps=30,
            total_with_context=80,
            top_gaps=[("Gap 1", 15), ("Gap 2", 10)],
            top_used=[("Context 1", 50), ("Context 2", 30)],
        )

        assert analysis.total_extractions == 100
        assert analysis.total_with_gaps == 30
        assert len(analysis.top_gaps) == 2
        assert analysis.top_gaps[0] == ("Gap 1", 15)

    def test_format_text_report(self):
        """Test text report formatting."""
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

        from analyze_context_gaps import ContextGapAnalysis, format_text_report

        now = datetime.now(timezone.utc)
        analysis = ContextGapAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_extractions=100,
            total_with_gaps=30,
            total_with_context=80,
            top_gaps=[("Missing Pinterest docs", 15)],
            top_used=[("Tailwind codebase map", 50)],
        )

        report = format_text_report(analysis)

        assert "Context Gap Analysis Report" in report
        assert "Total extractions analyzed: 100" in report
        assert "Missing Pinterest docs" in report
        assert "Tailwind codebase map" in report
        assert "RECOMMENDATIONS" in report

    def test_format_json_report(self):
        """Test JSON report formatting."""
        import json
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

        from analyze_context_gaps import ContextGapAnalysis, format_json_report

        now = datetime.now(timezone.utc)
        analysis = ContextGapAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_extractions=100,
            total_with_gaps=30,
            total_with_context=80,
            top_gaps=[("Gap 1", 15)],
            top_used=[("Context 1", 50)],
        )

        json_str = format_json_report(analysis)
        data = json.loads(json_str)

        assert "period" in data
        assert "summary" in data
        assert data["summary"]["total_extractions"] == 100
        assert len(data["top_gaps"]) == 1
        assert data["top_gaps"][0]["gap"] == "Gap 1"
        assert data["top_gaps"][0]["count"] == 15

    def test_format_text_report_empty(self):
        """Test text report with no data."""
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

        from analyze_context_gaps import ContextGapAnalysis, format_text_report

        now = datetime.now(timezone.utc)
        analysis = ContextGapAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_extractions=0,
            total_with_gaps=0,
            total_with_context=0,
            top_gaps=[],
            top_used=[],
        )

        report = format_text_report(analysis)

        assert "No context gaps recorded" in report
        assert "No context usage recorded" in report

    def test_format_text_report_with_product_area_breakdown(self):
        """Test text report with product area breakdown."""
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

        from analyze_context_gaps import ContextGapAnalysis, format_text_report

        now = datetime.now(timezone.utc)
        analysis = ContextGapAnalysis(
            period_start=now - timedelta(days=7),
            period_end=now,
            total_extractions=100,
            total_with_gaps=30,
            total_with_context=80,
            top_gaps=[("Gap 1", 15)],
            top_used=[("Context 1", 50)],
            gaps_by_product_area={
                "publishing": [("Pinterest gap", 10)],
                "billing": [("Billing gap", 5)],
            },
        )

        report = format_text_report(analysis)

        assert "GAPS BY PRODUCT AREA" in report
        assert "publishing:" in report
        assert "Pinterest gap" in report
