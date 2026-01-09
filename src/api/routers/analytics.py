"""
Analytics Endpoints

Dashboard metrics and classification statistics for operational visibility.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_db
from src.api.schemas.analytics import (
    ClassificationStats,
    ConfidenceDistribution,
    DashboardMetrics,
    PipelineRunSummary,
)
from src.db.classification_storage import get_classification_stats


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
