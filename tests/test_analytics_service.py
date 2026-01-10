"""
Analytics Service Tests

Tests for AnalyticsService - story tracking analytics.
Run with: pytest tests/test_analytics_service.py -v
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.services import AnalyticsService
from story_tracking.services.analytics_service import (
    StoryMetrics,
    ThemeTrend,
    SourceDistribution,
    EvidenceSummary,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    db = Mock()
    cursor = MagicMock()
    db.cursor.return_value.__enter__ = Mock(return_value=cursor)
    db.cursor.return_value.__exit__ = Mock(return_value=False)
    return db, cursor


@pytest.fixture
def analytics_service(mock_db):
    """Create an AnalyticsService with mock database."""
    db, _ = mock_db
    return AnalyticsService(db)


# -----------------------------------------------------------------------------
# Story Metrics Tests
# -----------------------------------------------------------------------------


class TestStoryMetrics:
    """Tests for get_story_metrics."""

    def test_get_story_metrics(self, mock_db, analytics_service):
        """Test getting aggregated story metrics."""
        db, cursor = mock_db

        # Mock query responses
        cursor.fetchone.side_effect = [
            {"count": 50},  # total stories
            {"last_7": 10, "last_30": 30},  # recent counts
            {"avg_score": 85.5},  # avg confidence
            {"total_evidence": 150, "total_conversations": 500},  # totals
        ]
        cursor.fetchall.side_effect = [
            [{"status": "candidate", "count": 20}, {"status": "triaged", "count": 15}, {"status": "validated", "count": 15}],  # by status
            [{"priority": "high", "count": 10}, {"priority": "medium", "count": 25}, {"priority": "none", "count": 15}],  # by priority
            [{"severity": "critical", "count": 5}, {"severity": "major", "count": 20}, {"severity": "none", "count": 25}],  # by severity
            [{"product_area": "billing", "count": 20}, {"product_area": "scheduler", "count": 30}],  # by product area
        ]

        result = analytics_service.get_story_metrics()

        assert isinstance(result, StoryMetrics)
        assert result.total_stories == 50
        assert result.created_last_7_days == 10
        assert result.created_last_30_days == 30
        assert result.avg_confidence_score == 85.5
        assert result.total_evidence_count == 150
        assert result.total_conversation_count == 500
        assert result.by_status["candidate"] == 20
        assert result.by_priority["high"] == 10

    def test_get_story_metrics_empty(self, mock_db, analytics_service):
        """Test metrics with no stories."""
        db, cursor = mock_db

        cursor.fetchone.side_effect = [
            {"count": 0},  # total stories
            {"last_7": 0, "last_30": 0},  # recent counts
            {"avg_score": None},  # no avg
            {"total_evidence": None, "total_conversations": None},  # no totals
        ]
        cursor.fetchall.side_effect = [
            [],  # by status
            [],  # by priority
            [],  # by severity
            [],  # by product area
        ]

        result = analytics_service.get_story_metrics()

        assert result.total_stories == 0
        assert result.avg_confidence_score is None
        assert result.total_evidence_count == 0


# -----------------------------------------------------------------------------
# Trending Themes Tests
# -----------------------------------------------------------------------------


class TestTrendingThemes:
    """Tests for get_trending_themes."""

    def test_get_trending_themes(self, mock_db, analytics_service):
        """Test getting trending themes."""
        db, cursor = mock_db

        now = datetime.now()
        cursor.fetchall.return_value = [
            {
                "theme_signature": "Billing: Subscription cancellation issues",
                "product_area": "billing",
                "occurrence_count": 15,
                "first_seen_at": now - timedelta(days=5),
                "last_seen_at": now - timedelta(hours=2),
                "linked_story_count": 3,
            },
            {
                "theme_signature": "Scheduler: Pin scheduling fails",
                "product_area": "scheduler",
                "occurrence_count": 10,
                "first_seen_at": now - timedelta(days=3),
                "last_seen_at": now - timedelta(days=2),
                "linked_story_count": 2,
            },
        ]

        result = analytics_service.get_trending_themes(days=7, limit=10)

        assert len(result) == 2
        assert isinstance(result[0], ThemeTrend)
        assert result[0].theme_signature == "Billing: Subscription cancellation issues"
        assert result[0].occurrence_count == 15
        assert result[0].trend_direction == "rising"  # last seen < 1 day ago
        assert result[1].trend_direction == "stable"  # last seen 2 days ago

    def test_get_trending_themes_empty(self, mock_db, analytics_service):
        """Test trending themes with no results."""
        db, cursor = mock_db
        cursor.fetchall.return_value = []

        result = analytics_service.get_trending_themes()

        assert result == []


# -----------------------------------------------------------------------------
# Source Distribution Tests
# -----------------------------------------------------------------------------


class TestSourceDistribution:
    """Tests for get_source_distribution."""

    def test_get_source_distribution(self, mock_db, analytics_service):
        """Test getting source distribution."""
        db, cursor = mock_db

        cursor.fetchall.return_value = [
            {"source": "intercom", "conversation_count": 400, "story_count": 40},
            {"source": "slack", "conversation_count": 100, "story_count": 25},
        ]

        result = analytics_service.get_source_distribution()

        assert len(result) == 2
        assert isinstance(result[0], SourceDistribution)
        assert result[0].source == "intercom"
        assert result[0].conversation_count == 400
        assert result[0].percentage == 80.0  # 400/500 * 100
        assert result[1].percentage == 20.0  # 100/500 * 100

    def test_get_source_distribution_empty(self, mock_db, analytics_service):
        """Test source distribution with no data."""
        db, cursor = mock_db
        cursor.fetchall.return_value = []

        result = analytics_service.get_source_distribution()

        assert result == []


# -----------------------------------------------------------------------------
# Evidence Summary Tests
# -----------------------------------------------------------------------------


class TestEvidenceSummary:
    """Tests for get_evidence_summary."""

    def test_get_evidence_summary(self, mock_db, analytics_service):
        """Test getting evidence summary."""
        db, cursor = mock_db

        cursor.fetchone.side_effect = [
            {"count": 50},  # total evidence records
            {"total": 500},  # total conversations
            {"count": 75},  # total themes
        ]
        cursor.fetchall.return_value = [
            {"source": "intercom", "conversation_count": 400, "story_count": 40},
            {"source": "slack", "conversation_count": 100, "story_count": 25},
        ]

        result = analytics_service.get_evidence_summary()

        assert isinstance(result, EvidenceSummary)
        assert result.total_evidence_records == 50
        assert result.total_conversations_linked == 500
        assert result.total_themes_linked == 75
        assert len(result.sources) == 2


# -----------------------------------------------------------------------------
# Sync Metrics Tests
# -----------------------------------------------------------------------------


class TestSyncMetrics:
    """Tests for get_sync_metrics."""

    def test_get_sync_metrics(self, mock_db, analytics_service):
        """Test getting sync metrics."""
        db, cursor = mock_db

        cursor.fetchone.side_effect = [
            {
                "total_synced": 30,
                "success_count": 28,
                "error_count": 2,
                "push_count": 20,
                "pull_count": 10,
            },
            {"count": 20},  # unsynced stories
        ]

        result = analytics_service.get_sync_metrics()

        assert result["total_synced"] == 30
        assert result["success_count"] == 28
        assert result["error_count"] == 2
        assert result["push_count"] == 20
        assert result["pull_count"] == 10
        assert result["unsynced_count"] == 20

    def test_get_sync_metrics_no_synced(self, mock_db, analytics_service):
        """Test sync metrics with no synced stories."""
        db, cursor = mock_db

        cursor.fetchone.side_effect = [
            {
                "total_synced": 0,
                "success_count": 0,
                "error_count": 0,
                "push_count": 0,
                "pull_count": 0,
            },
            {"count": 50},  # all unsynced
        ]

        result = analytics_service.get_sync_metrics()

        assert result["total_synced"] == 0
        assert result["unsynced_count"] == 50
