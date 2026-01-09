"""
Theme Analysis Endpoints

Browse trending themes, orphans, and theme details.
"""

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db
from src.api.schemas.themes import (
    OrphanThemesResponse,
    ThemeAggregate,
    ThemeDetail,
    ThemeListResponse,
    TrendingThemesResponse,
)


router = APIRouter(prefix="/api/themes", tags=["themes"])


def _row_to_theme_aggregate(row: dict) -> ThemeAggregate:
    """Convert database row to ThemeAggregate model."""
    symptoms = row.get("sample_symptoms", [])
    if isinstance(symptoms, str):
        try:
            symptoms = json.loads(symptoms)
        except (json.JSONDecodeError, TypeError):
            symptoms = []

    return ThemeAggregate(
        issue_signature=row["issue_signature"],
        product_area=row["product_area"] or "",
        component=row["component"] or "",
        occurrence_count=row["occurrence_count"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        sample_user_intent=row.get("sample_user_intent"),
        sample_symptoms=symptoms or [],
        sample_affected_flow=row.get("sample_affected_flow"),
        sample_root_cause_hypothesis=row.get("sample_root_cause_hypothesis"),
        ticket_created=row.get("ticket_created", False),
        ticket_id=row.get("ticket_id"),
    )


@router.get("/trending", response_model=TrendingThemesResponse)
def get_trending_themes(
    db=Depends(get_db),
    days: int = Query(default=7, ge=1, le=90, description="Lookback period"),
    min_occurrences: int = Query(default=2, ge=1, description="Minimum occurrence count"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Get trending themes.

    Returns themes with multiple occurrences in the specified time window,
    ordered by occurrence count (descending).

    **Use cases:**
    - Identify emerging issues
    - Find high-impact problems to prioritize
    - Track theme trends over time
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                issue_signature, product_area, component,
                occurrence_count, first_seen_at, last_seen_at,
                sample_user_intent, sample_symptoms,
                sample_affected_flow, sample_root_cause_hypothesis,
                ticket_created, ticket_id
            FROM theme_aggregates
            WHERE last_seen_at > NOW() - INTERVAL '%s days'
              AND occurrence_count >= %s
            ORDER BY occurrence_count DESC, last_seen_at DESC
            LIMIT %s
        """, (days, min_occurrences, limit))
        rows = cur.fetchall()

    themes = [_row_to_theme_aggregate(row) for row in rows]

    return TrendingThemesResponse(
        themes=themes,
        days=days,
        min_occurrences=min_occurrences,
        total=len(themes),
    )


@router.get("/orphans", response_model=OrphanThemesResponse)
def get_orphan_themes(
    db=Depends(get_db),
    threshold: int = Query(default=2, ge=1, description="Max occurrence count for orphans"),
    days: int = Query(default=30, ge=1, le=365, description="Only show orphans from last N days"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get orphan (low-count) themes.

    Returns themes below the occurrence threshold. These are candidates for:
    - PM review and merging with similar themes
    - Dismissal as one-off issues
    - Monitoring for emerging patterns

    **Parameters:**
    - **threshold**: Max count to be considered orphan (default 2 = singletons + pairs)
    - **days**: Only show recent orphans to avoid historical noise
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                issue_signature, product_area, component,
                occurrence_count, first_seen_at, last_seen_at,
                sample_user_intent, sample_symptoms,
                sample_affected_flow, sample_root_cause_hypothesis,
                ticket_created, ticket_id
            FROM theme_aggregates
            WHERE occurrence_count < %s
              AND last_seen_at > NOW() - INTERVAL '%s days'
            ORDER BY last_seen_at DESC, occurrence_count DESC
            LIMIT %s
        """, (threshold, days, limit))
        rows = cur.fetchall()

    themes = [_row_to_theme_aggregate(row) for row in rows]

    return OrphanThemesResponse(
        themes=themes,
        threshold=threshold,
        total=len(themes),
    )


@router.get("/singletons", response_model=OrphanThemesResponse)
def get_singleton_themes(
    db=Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get singleton themes (exactly 1 occurrence).

    Singletons may be:
    - Newly emerging issues (watch for future occurrences)
    - Unique edge cases (likely won't recur)
    - Misclassified themes (may need merging)
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                issue_signature, product_area, component,
                occurrence_count, first_seen_at, last_seen_at,
                sample_user_intent, sample_symptoms,
                sample_affected_flow, sample_root_cause_hypothesis,
                ticket_created, ticket_id
            FROM theme_aggregates
            WHERE occurrence_count = 1
              AND last_seen_at > NOW() - INTERVAL '%s days'
            ORDER BY last_seen_at DESC
            LIMIT %s
        """, (days, limit))
        rows = cur.fetchall()

    themes = [_row_to_theme_aggregate(row) for row in rows]

    return OrphanThemesResponse(
        themes=themes,
        threshold=2,  # Singletons are count=1
        total=len(themes),
    )


@router.get("/all", response_model=ThemeListResponse)
def list_all_themes(
    db=Depends(get_db),
    product_area: Optional[str] = Query(default=None, description="Filter by product area"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    List all themes with optional filtering.

    Returns themes ordered by occurrence count.
    Use product_area filter to focus on specific areas.
    """
    with db.cursor() as cur:
        # Get total count
        if product_area:
            cur.execute("""
                SELECT COUNT(*) FROM theme_aggregates WHERE product_area = %s
            """, (product_area,))
        else:
            cur.execute("SELECT COUNT(*) FROM theme_aggregates")
        total = cur.fetchone()["count"]

        # Get themes
        if product_area:
            cur.execute("""
                SELECT
                    issue_signature, product_area, component,
                    occurrence_count, first_seen_at, last_seen_at,
                    sample_user_intent, sample_symptoms,
                    sample_affected_flow, sample_root_cause_hypothesis,
                    ticket_created, ticket_id
                FROM theme_aggregates
                WHERE product_area = %s
                ORDER BY occurrence_count DESC, last_seen_at DESC
                LIMIT %s OFFSET %s
            """, (product_area, limit, offset))
        else:
            cur.execute("""
                SELECT
                    issue_signature, product_area, component,
                    occurrence_count, first_seen_at, last_seen_at,
                    sample_user_intent, sample_symptoms,
                    sample_affected_flow, sample_root_cause_hypothesis,
                    ticket_created, ticket_id
                FROM theme_aggregates
                ORDER BY occurrence_count DESC, last_seen_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
        rows = cur.fetchall()

    themes = [_row_to_theme_aggregate(row) for row in rows]

    return ThemeListResponse(
        themes=themes,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{signature}", response_model=ThemeDetail)
def get_theme_detail(signature: str, db=Depends(get_db)):
    """
    Get detailed information for a specific theme.

    Returns theme data plus list of conversation IDs.
    """
    with db.cursor() as cur:
        # Get theme aggregate
        cur.execute("""
            SELECT
                issue_signature, product_area, component,
                occurrence_count, first_seen_at, last_seen_at,
                sample_user_intent, sample_symptoms,
                sample_affected_flow, sample_root_cause_hypothesis,
                ticket_created, ticket_id
            FROM theme_aggregates
            WHERE issue_signature = %s
        """, (signature,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Theme '{signature}' not found")

        theme = _row_to_theme_aggregate(row)

        # Get conversation IDs
        cur.execute("""
            SELECT conversation_id
            FROM themes
            WHERE issue_signature = %s
            ORDER BY extracted_at DESC
        """, (signature,))
        conv_rows = cur.fetchall()
        conversation_ids = [r["conversation_id"] for r in conv_rows]

    return ThemeDetail(
        theme=theme,
        conversation_ids=conversation_ids,
    )
