"""
Analytics Service

Analytics queries for story tracking dashboard.
Reference: docs/story-tracking-web-app-architecture.md
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID


@dataclass
class StoryMetrics:
    """Aggregated story metrics."""

    total_stories: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_severity: Dict[str, int]
    by_product_area: Dict[str, int]
    created_last_7_days: int
    created_last_30_days: int
    avg_confidence_score: Optional[float]
    total_evidence_count: int
    total_conversation_count: int


@dataclass
class ThemeTrend:
    """A trending theme with metrics."""

    theme_signature: str
    product_area: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    trend_direction: str  # "rising" | "stable" | "declining"
    linked_story_count: int


@dataclass
class SourceDistribution:
    """Distribution of evidence by source."""

    source: str
    conversation_count: int
    story_count: int
    percentage: float


@dataclass
class EvidenceSummary:
    """Summary of evidence across all stories."""

    total_evidence_records: int
    total_conversations_linked: int
    total_themes_linked: int
    sources: List[SourceDistribution]


class AnalyticsService:
    """Service for analytics queries."""

    def __init__(self, db_connection):
        """Initialize with database connection."""
        self.db = db_connection

    def get_story_metrics(self) -> StoryMetrics:
        """
        Get aggregated story metrics.

        Returns metrics grouped by status, priority, severity, and product area.
        """
        with self.db.cursor() as cur:
            # Total stories
            cur.execute("SELECT COUNT(*) as count FROM stories")
            total_stories = cur.fetchone()["count"]

            # By status
            cur.execute("""
                SELECT status, COUNT(*) as count
                FROM stories
                GROUP BY status
            """)
            by_status = {row["status"]: row["count"] for row in cur.fetchall()}

            # By priority
            cur.execute("""
                SELECT COALESCE(priority, 'none') as priority, COUNT(*) as count
                FROM stories
                GROUP BY priority
            """)
            by_priority = {row["priority"]: row["count"] for row in cur.fetchall()}

            # By severity
            cur.execute("""
                SELECT COALESCE(severity, 'none') as severity, COUNT(*) as count
                FROM stories
                GROUP BY severity
            """)
            by_severity = {row["severity"]: row["count"] for row in cur.fetchall()}

            # By product area
            cur.execute("""
                SELECT COALESCE(product_area, 'unknown') as product_area, COUNT(*) as count
                FROM stories
                GROUP BY product_area
            """)
            by_product_area = {row["product_area"]: row["count"] for row in cur.fetchall()}

            # Created recently
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as last_7,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') as last_30
                FROM stories
            """)
            recent = cur.fetchone()
            created_last_7 = recent["last_7"]
            created_last_30 = recent["last_30"]

            # Average confidence score
            cur.execute("""
                SELECT AVG(confidence_score) as avg_score
                FROM stories
                WHERE confidence_score IS NOT NULL
            """)
            avg_confidence = cur.fetchone()["avg_score"]

            # Totals from evidence
            cur.execute("""
                SELECT
                    SUM(evidence_count) as total_evidence,
                    SUM(conversation_count) as total_conversations
                FROM stories
            """)
            totals = cur.fetchone()
            total_evidence = totals["total_evidence"] or 0
            total_conversations = totals["total_conversations"] or 0

        return StoryMetrics(
            total_stories=total_stories,
            by_status=by_status,
            by_priority=by_priority,
            by_severity=by_severity,
            by_product_area=by_product_area,
            created_last_7_days=created_last_7,
            created_last_30_days=created_last_30,
            avg_confidence_score=float(avg_confidence) if avg_confidence else None,
            total_evidence_count=total_evidence,
            total_conversation_count=total_conversations,
        )

    def get_trending_themes(self, days: int = 7, limit: int = 20) -> List[ThemeTrend]:
        """
        Get trending themes over the specified period.

        Themes are ranked by occurrence count and recency.
        Only themes with 2+ occurrences are included.

        Trend direction is calculated as:
        - "rising": last seen within 1 day
        - "stable": last seen within 3 days
        - "declining": last seen more than 3 days ago
        """
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT
                    ta.theme_signature,
                    ta.product_area,
                    ta.occurrence_count,
                    ta.first_seen_at,
                    ta.last_seen_at,
                    COUNT(DISTINCT se.story_id) as linked_story_count
                FROM theme_aggregates ta
                LEFT JOIN story_evidence se ON ta.theme_signature = ANY(se.theme_signatures)
                WHERE ta.last_seen_at > NOW() - INTERVAL '%s days'
                  AND ta.occurrence_count >= 2
                GROUP BY ta.theme_signature, ta.product_area, ta.occurrence_count,
                         ta.first_seen_at, ta.last_seen_at
                ORDER BY ta.occurrence_count DESC, ta.last_seen_at DESC
                LIMIT %s
            """, (days, limit))

            themes = []
            now = datetime.now(timezone.utc)
            for row in cur.fetchall():
                # Determine trend direction based on recency
                # Handle timezone-aware vs naive datetime from DB
                first_seen = row["first_seen_at"]
                last_seen = row["last_seen_at"]
                if first_seen.tzinfo is None:
                    first_seen = first_seen.replace(tzinfo=timezone.utc)
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)

                days_since_first = (now - first_seen).days
                days_since_last = (now - last_seen).days

                if days_since_last <= 1:
                    trend = "rising"
                elif days_since_last <= 3:
                    trend = "stable"
                else:
                    trend = "declining"

                themes.append(ThemeTrend(
                    theme_signature=row["theme_signature"],
                    product_area=row["product_area"] or "unknown",
                    occurrence_count=row["occurrence_count"],
                    first_seen_at=row["first_seen_at"],
                    last_seen_at=row["last_seen_at"],
                    trend_direction=trend,
                    linked_story_count=row["linked_story_count"] or 0,
                ))

        return themes

    def get_source_distribution(self) -> List[SourceDistribution]:
        """
        Get distribution of evidence by source.

        Returns the count and percentage of conversations from each source.
        """
        with self.db.cursor() as cur:
            # Get total conversations across all evidence
            cur.execute("""
                SELECT
                    key as source,
                    SUM(value::int) as conversation_count,
                    COUNT(DISTINCT story_id) as story_count
                FROM story_evidence,
                     jsonb_each_text(source_stats)
                GROUP BY key
                ORDER BY conversation_count DESC
            """)

            rows = cur.fetchall()
            total_conversations = sum(row["conversation_count"] for row in rows)

            sources = []
            for row in rows:
                percentage = (
                    (row["conversation_count"] / total_conversations * 100)
                    if total_conversations > 0
                    else 0
                )
                sources.append(SourceDistribution(
                    source=row["source"],
                    conversation_count=row["conversation_count"],
                    story_count=row["story_count"],
                    percentage=round(percentage, 2),
                ))

        return sources

    def get_evidence_summary(self) -> EvidenceSummary:
        """
        Get summary of all evidence.

        Returns aggregate evidence statistics.
        """
        with self.db.cursor() as cur:
            # Total evidence records
            cur.execute("SELECT COUNT(*) as count FROM story_evidence")
            total_records = cur.fetchone()["count"]

            # Total conversations linked (sum of array lengths)
            cur.execute("""
                SELECT COALESCE(SUM(array_length(conversation_ids, 1)), 0) as total
                FROM story_evidence
            """)
            total_conversations = cur.fetchone()["total"]

            # Total unique themes
            cur.execute("""
                SELECT COUNT(DISTINCT unnest) as count
                FROM story_evidence, unnest(theme_signatures)
            """)
            total_themes = cur.fetchone()["count"]

        # Get source distribution
        sources = self.get_source_distribution()

        return EvidenceSummary(
            total_evidence_records=total_records,
            total_conversations_linked=total_conversations,
            total_themes_linked=total_themes,
            sources=sources,
        )

    def get_sync_metrics(self) -> Dict:
        """
        Get Shortcut sync metrics.

        Returns counts of synced vs unsynced stories.
        """
        with self.db.cursor() as cur:
            # Stories with sync metadata
            cur.execute("""
                SELECT
                    COUNT(*) as total_synced,
                    COUNT(*) FILTER (WHERE last_sync_status = 'success') as success_count,
                    COUNT(*) FILTER (WHERE last_sync_status = 'error') as error_count,
                    COUNT(*) FILTER (WHERE last_sync_direction = 'push') as push_count,
                    COUNT(*) FILTER (WHERE last_sync_direction = 'pull') as pull_count
                FROM story_sync_metadata
                WHERE shortcut_story_id IS NOT NULL AND shortcut_story_id != ''
            """)
            row = cur.fetchone()

            # Stories without sync
            cur.execute("""
                SELECT COUNT(*) as count
                FROM stories s
                LEFT JOIN story_sync_metadata sm ON s.id = sm.story_id
                WHERE sm.shortcut_story_id IS NULL OR sm.shortcut_story_id = ''
            """)
            unsynced = cur.fetchone()["count"]

        return {
            "total_synced": row["total_synced"],
            "success_count": row["success_count"],
            "error_count": row["error_count"],
            "push_count": row["push_count"],
            "pull_count": row["pull_count"],
            "unsynced_count": unsynced,
        }
