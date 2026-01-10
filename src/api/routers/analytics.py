"""
Analytics Endpoints

Dashboard metrics and classification statistics for operational visibility.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_db
from src.api.schemas.analytics import (
    ClassificationStats,
    ConfidenceDistribution,
    DashboardMetrics,
    EvidenceSummaryResponse,
    PipelineRunSummary,
    SourceDistributionResponse,
    StoryMetricsResponse,
    SyncMetricsResponse,
    ThemeTrendResponse,
)
from src.db.classification_storage import get_classification_stats
from src.story_tracking.services import AnalyticsService


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardMetrics)
def get_dashboard_metrics(
    db=Depends(get_db),
    days: int = Query(default=30, ge=1, le=365, description="Lookback period in days"),
):
    """
    Get aggregated dashboard metrics.

    Returns a comprehensive overview of system state including:
    - Conversation counts (total, 7-day, 30-day)
    - Classification confidence distributions
    - Theme counts (total, trending, orphans)
    - Recent pipeline runs

    This endpoint is optimized for the Streamlit dashboard,
    combining multiple queries into a single response.
    """
    with db.cursor() as cur:
        # Total conversations
        cur.execute("SELECT COUNT(*) FROM conversations")
        total_conversations = cur.fetchone()["count"]

        # Conversations in windows
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as last_7,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') as last_30
            FROM conversations
        """)
        row = cur.fetchone()
        conversations_7d = row["last_7"]
        conversations_30d = row["last_30"]

        # Theme counts
        cur.execute("SELECT COUNT(*) FROM theme_aggregates")
        total_themes = cur.fetchone()["count"]

        cur.execute("""
            SELECT COUNT(*) FROM theme_aggregates
            WHERE last_seen_at > NOW() - INTERVAL '7 days'
              AND occurrence_count >= 2
        """)
        trending_count = cur.fetchone()["count"]

        cur.execute("""
            SELECT COUNT(*) FROM theme_aggregates
            WHERE occurrence_count = 1
        """)
        orphan_count = cur.fetchone()["count"]

        # Recent pipeline runs
        cur.execute("""
            SELECT id, started_at, completed_at, status,
                   conversations_fetched, conversations_classified, conversations_stored
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT 5
        """)
        runs = cur.fetchall()
        recent_runs = [
            PipelineRunSummary(
                id=r["id"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                status=r["status"],
                conversations_fetched=r["conversations_fetched"] or 0,
                conversations_classified=r["conversations_classified"] or 0,
                conversations_stored=r["conversations_stored"] or 0,
            )
            for r in runs
        ]
        last_run_at = runs[0]["started_at"] if runs else None

    # Get classification stats using existing function
    stats = get_classification_stats(days=days)

    # Build confidence distributions
    s1_conf = ConfidenceDistribution(
        high=stats["stage1_confidence_distribution"].get("high", 0),
        medium=stats["stage1_confidence_distribution"].get("medium", 0),
        low=stats["stage1_confidence_distribution"].get("low", 0),
    )
    s2_conf = ConfidenceDistribution(
        high=stats["stage2_confidence_distribution"].get("high", 0),
        medium=stats["stage2_confidence_distribution"].get("medium", 0),
        low=stats["stage2_confidence_distribution"].get("low", 0),
    )

    return DashboardMetrics(
        total_conversations=total_conversations,
        conversations_last_7_days=conversations_7d,
        conversations_last_30_days=conversations_30d,
        classification_changes=stats["classification_changes"],
        disambiguation_high_count=stats["disambiguation_high_count"],
        resolution_detected_count=stats["resolution_detected_count"],
        stage1_confidence=s1_conf,
        stage2_confidence=s2_conf,
        top_conversation_types=stats["top_stage2_types"],
        total_themes=total_themes,
        trending_themes_count=trending_count,
        orphan_themes_count=orphan_count,
        recent_runs=recent_runs,
        last_run_at=last_run_at,
    )


@router.get("/stats", response_model=ClassificationStats)
def get_stats(
    days: int = Query(default=30, ge=1, le=365, description="Lookback period in days"),
):
    """
    Get detailed classification statistics.

    Returns raw classification stats for deeper analysis:
    - Confidence distributions for both stages
    - Classification change count
    - Top conversation types
    """
    stats = get_classification_stats(days=days)

    return ClassificationStats(
        days=days,
        total_conversations=stats["total_conversations"],
        stage1_confidence_distribution=stats["stage1_confidence_distribution"],
        stage2_confidence_distribution=stats["stage2_confidence_distribution"],
        classification_changes=stats["classification_changes"],
        disambiguation_high_count=stats["disambiguation_high_count"],
        resolution_detected_count=stats["resolution_detected_count"],
        top_stage1_types=stats["top_stage1_types"],
        top_stage2_types=stats["top_stage2_types"],
    )


# -----------------------------------------------------------------------------
# Story Tracking Analytics Endpoints
# -----------------------------------------------------------------------------


def get_analytics_service(db=Depends(get_db)) -> AnalyticsService:
    """Dependency for AnalyticsService."""
    return AnalyticsService(db)


@router.get("/stories", response_model=StoryMetricsResponse)
def get_story_metrics(
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get aggregated story metrics.

    Returns:
    - Total story count and breakdown by status, priority, severity, product area
    - Recent creation counts (7 and 30 days)
    - Average confidence score
    - Total evidence and conversation counts
    """
    metrics = service.get_story_metrics()

    return StoryMetricsResponse(
        total_stories=metrics.total_stories,
        by_status=metrics.by_status,
        by_priority=metrics.by_priority,
        by_severity=metrics.by_severity,
        by_product_area=metrics.by_product_area,
        created_last_7_days=metrics.created_last_7_days,
        created_last_30_days=metrics.created_last_30_days,
        avg_confidence_score=metrics.avg_confidence_score,
        total_evidence_count=metrics.total_evidence_count,
        total_conversation_count=metrics.total_conversation_count,
    )


@router.get("/themes/trending", response_model=List[ThemeTrendResponse])
def get_trending_themes(
    days: int = Query(default=7, ge=1, le=90, description="Lookback period in days"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum themes to return"),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get trending themes over the specified period.

    Themes are ranked by occurrence count and recency.
    Only themes with 2+ occurrences are included.

    Returns trend direction:
    - "rising": Last seen within 1 day
    - "stable": Last seen within 3 days
    - "declining": Last seen more than 3 days ago
    """
    themes = service.get_trending_themes(days=days, limit=limit)

    return [
        ThemeTrendResponse(
            theme_signature=t.theme_signature,
            product_area=t.product_area,
            occurrence_count=t.occurrence_count,
            first_seen_at=t.first_seen_at,
            last_seen_at=t.last_seen_at,
            trend_direction=t.trend_direction,
            linked_story_count=t.linked_story_count,
        )
        for t in themes
    ]


@router.get("/sources", response_model=List[SourceDistributionResponse])
def get_source_distribution(
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get distribution of evidence by source.

    Returns the count and percentage of conversations from each source
    (e.g., intercom, slack, coda).
    """
    sources = service.get_source_distribution()

    return [
        SourceDistributionResponse(
            source=s.source,
            conversation_count=s.conversation_count,
            story_count=s.story_count,
            percentage=s.percentage,
        )
        for s in sources
    ]


@router.get("/evidence", response_model=EvidenceSummaryResponse)
def get_evidence_summary(
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get summary of all evidence.

    Returns aggregate counts of evidence records, linked conversations,
    and linked themes, along with source distribution.
    """
    summary = service.get_evidence_summary()

    return EvidenceSummaryResponse(
        total_evidence_records=summary.total_evidence_records,
        total_conversations_linked=summary.total_conversations_linked,
        total_themes_linked=summary.total_themes_linked,
        sources=[
            SourceDistributionResponse(
                source=s.source,
                conversation_count=s.conversation_count,
                story_count=s.story_count,
                percentage=s.percentage,
            )
            for s in summary.sources
        ],
    )


@router.get("/sync", response_model=SyncMetricsResponse)
def get_sync_metrics(
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get Shortcut sync metrics.

    Returns counts of synced vs unsynced stories, success/error rates,
    and push/pull direction counts.
    """
    metrics = service.get_sync_metrics()

    return SyncMetricsResponse(
        total_synced=metrics["total_synced"],
        success_count=metrics["success_count"],
        error_count=metrics["error_count"],
        push_count=metrics["push_count"],
        pull_count=metrics["pull_count"],
        unsynced_count=metrics["unsynced_count"],
    )
