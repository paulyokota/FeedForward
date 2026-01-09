"""
Cross-Source Analytics
Analyze themes across multiple data sources (Intercom, Coda).
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional

# Handle both module and script execution
try:
    from ..db.connection import get_connection
except ImportError:
    from db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class CrossSourceTheme:
    """Theme with cross-source analytics."""

    issue_signature: str
    product_area: str
    component: str
    total_conversations: int
    source_counts: Dict[str, int]
    coda_count: int
    intercom_count: int
    priority_category: str  # "high_confidence", "strategic", "tactical"
    first_seen_at: datetime
    last_seen_at: datetime
    ticket_created: bool
    ticket_id: Optional[str]


def get_cross_source_themes(
    min_conversations: int = 1,
    limit: int = 100,
) -> List[CrossSourceTheme]:
    """
    Find themes that appear in BOTH research and support.
    These are high-confidence priorities.

    Args:
        min_conversations: Minimum total occurrences
        limit: Maximum results to return

    Returns:
        List of CrossSourceTheme objects, prioritized by cross-source presence
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        issue_signature,
                        product_area,
                        component,
                        occurrence_count as total_conversations,
                        source_counts,
                        COALESCE((source_counts->>'coda')::int, 0) as coda_count,
                        COALESCE((source_counts->>'intercom')::int, 0) as intercom_count,
                        CASE
                            WHEN source_counts ? 'coda' AND source_counts ? 'intercom'
                            THEN 'high_confidence'
                            WHEN source_counts ? 'coda'
                            THEN 'strategic'
                            ELSE 'tactical'
                        END as priority_category,
                        first_seen_at,
                        last_seen_at,
                        ticket_created,
                        ticket_id
                    FROM theme_aggregates
                    WHERE occurrence_count >= %s
                    ORDER BY
                        (COALESCE((source_counts->>'coda')::int, 0) > 0)::int DESC,
                        (COALESCE((source_counts->>'intercom')::int, 0)) DESC
                    LIMIT %s
                    """,
                    (min_conversations, limit)
                )

                results = []
                for row in cur.fetchall():
                    source_counts = row[4] or {}
                    if isinstance(source_counts, str):
                        import json
                        source_counts = json.loads(source_counts)

                    results.append(CrossSourceTheme(
                        issue_signature=row[0],
                        product_area=row[1],
                        component=row[2],
                        total_conversations=row[3],
                        source_counts=source_counts,
                        coda_count=row[5],
                        intercom_count=row[6],
                        priority_category=row[7],
                        first_seen_at=row[8],
                        last_seen_at=row[9],
                        ticket_created=row[10],
                        ticket_id=row[11],
                    ))

                return results

    except Exception as e:
        logger.error(f"Failed to get cross-source themes: {e}")
        return []


def get_high_confidence_themes(limit: int = 50) -> List[CrossSourceTheme]:
    """
    Get themes that appear in BOTH Coda research AND Intercom support.
    These have highest confidence for prioritization.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        issue_signature,
                        product_area,
                        component,
                        occurrence_count,
                        source_counts,
                        COALESCE((source_counts->>'coda')::int, 0) as coda_count,
                        COALESCE((source_counts->>'intercom')::int, 0) as intercom_count,
                        'high_confidence' as priority_category,
                        first_seen_at,
                        last_seen_at,
                        ticket_created,
                        ticket_id
                    FROM theme_aggregates
                    WHERE source_counts ? 'coda'
                      AND source_counts ? 'intercom'
                      AND COALESCE((source_counts->>'coda')::int, 0) > 0
                      AND COALESCE((source_counts->>'intercom')::int, 0) > 0
                    ORDER BY occurrence_count DESC
                    LIMIT %s
                    """,
                    (limit,)
                )

                results = []
                for row in cur.fetchall():
                    source_counts = row[4] or {}
                    if isinstance(source_counts, str):
                        import json
                        source_counts = json.loads(source_counts)

                    results.append(CrossSourceTheme(
                        issue_signature=row[0],
                        product_area=row[1],
                        component=row[2],
                        total_conversations=row[3],
                        source_counts=source_counts,
                        coda_count=row[5],
                        intercom_count=row[6],
                        priority_category=row[7],
                        first_seen_at=row[8],
                        last_seen_at=row[9],
                        ticket_created=row[10],
                        ticket_id=row[11],
                    ))

                return results

    except Exception as e:
        logger.error(f"Failed to get high-confidence themes: {e}")
        return []


def get_source_comparison_report() -> Dict:
    """
    Generate a report comparing themes across sources.

    Returns summary statistics and breakdown by priority category.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get summary stats
                cur.execute("""
                    SELECT
                        COUNT(*) as total_themes,
                        COUNT(*) FILTER (WHERE source_counts ? 'coda' AND source_counts ? 'intercom'
                            AND COALESCE((source_counts->>'coda')::int, 0) > 0
                            AND COALESCE((source_counts->>'intercom')::int, 0) > 0) as high_confidence,
                        COUNT(*) FILTER (WHERE source_counts ? 'coda'
                            AND COALESCE((source_counts->>'coda')::int, 0) > 0
                            AND (NOT source_counts ? 'intercom'
                                 OR COALESCE((source_counts->>'intercom')::int, 0) = 0)) as strategic_only,
                        COUNT(*) FILTER (WHERE source_counts ? 'intercom'
                            AND COALESCE((source_counts->>'intercom')::int, 0) > 0
                            AND (NOT source_counts ? 'coda'
                                 OR COALESCE((source_counts->>'coda')::int, 0) = 0)) as tactical_only,
                        SUM(COALESCE((source_counts->>'coda')::int, 0)) as total_coda,
                        SUM(COALESCE((source_counts->>'intercom')::int, 0)) as total_intercom
                    FROM theme_aggregates
                """)
                row = cur.fetchone()

                # Get top themes by category
                high_confidence = get_high_confidence_themes(limit=10)

                return {
                    "summary": {
                        "total_themes": row[0],
                        "high_confidence_themes": row[1],
                        "strategic_only_themes": row[2],
                        "tactical_only_themes": row[3],
                        "total_coda_occurrences": row[4] or 0,
                        "total_intercom_occurrences": row[5] or 0,
                    },
                    "high_confidence_themes": [
                        {
                            "signature": t.issue_signature,
                            "product_area": t.product_area,
                            "coda_count": t.coda_count,
                            "intercom_count": t.intercom_count,
                            "total": t.total_conversations,
                        }
                        for t in high_confidence
                    ],
                    "recommendations": _generate_recommendations(row),
                }

    except Exception as e:
        logger.error(f"Failed to generate source comparison report: {e}")
        return {"error": str(e)}


def _generate_recommendations(stats_row) -> List[str]:
    """Generate actionable recommendations based on stats."""
    recommendations = []

    total, high_conf, strategic, tactical, coda_total, intercom_total = stats_row

    if high_conf and high_conf > 0:
        recommendations.append(
            f"✅ {high_conf} themes confirmed in both research AND support - prioritize these"
        )

    if strategic and strategic > 0:
        recommendations.append(
            f"📊 {strategic} themes from research only - validate with support team"
        )

    if tactical and tactical > 0:
        recommendations.append(
            f"🎯 {tactical} themes from support only - consider deeper research"
        )

    if coda_total and coda_total > 100:
        recommendations.append(
            f"📚 Rich research data ({coda_total} research insights) available for analysis"
        )

    return recommendations


def format_cross_source_report(themes: List[CrossSourceTheme]) -> str:
    """Format themes into a readable markdown report."""
    lines = [
        "# Cross-Source Theme Analysis",
        "",
        "## Priority Categories",
        "",
        "- **High Confidence**: Confirmed in both research interviews AND support tickets",
        "- **Strategic**: Found in research only - proactive insights",
        "- **Tactical**: Found in support only - reactive issues",
        "",
        "## Themes",
        "",
    ]

    # Group by priority
    high_conf = [t for t in themes if t.priority_category == "high_confidence"]
    strategic = [t for t in themes if t.priority_category == "strategic"]
    tactical = [t for t in themes if t.priority_category == "tactical"]

    if high_conf:
        lines.append("### 🏆 High Confidence (Both Sources)")
        lines.append("")
        for t in high_conf[:10]:
            lines.append(
                f"- **{t.issue_signature}** [{t.product_area}] "
                f"(Research: {t.coda_count}, Support: {t.intercom_count})"
            )
        lines.append("")

    if strategic:
        lines.append("### 📊 Strategic (Research Only)")
        lines.append("")
        for t in strategic[:10]:
            lines.append(
                f"- **{t.issue_signature}** [{t.product_area}] "
                f"(Research: {t.coda_count})"
            )
        lines.append("")

    if tactical:
        lines.append("### 🎯 Tactical (Support Only)")
        lines.append("")
        for t in tactical[:10]:
            lines.append(
                f"- **{t.issue_signature}** [{t.product_area}] "
                f"(Support: {t.intercom_count})"
            )
        lines.append("")

    return "\n".join(lines)


# CLI for quick testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("CROSS-SOURCE THEME ANALYSIS")
    print("=" * 60)

    themes = get_cross_source_themes(min_conversations=1)
    print(f"\nTotal themes: {len(themes)}")

    high_conf = get_high_confidence_themes()
    print(f"High-confidence themes: {len(high_conf)}")

    if high_conf:
        print("\nTop high-confidence themes:")
        for t in high_conf[:5]:
            print(f"  - {t.issue_signature}: {t.coda_count} research, {t.intercom_count} support")

    print("\n" + "=" * 60)
    print("SOURCE COMPARISON REPORT")
    print("=" * 60)
    report = get_source_comparison_report()
    print(f"\nSummary: {report.get('summary', {})}")
    print(f"\nRecommendations:")
    for rec in report.get("recommendations", []):
        print(f"  {rec}")
