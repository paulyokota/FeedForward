#!/usr/bin/env python3
"""
Documentation Coverage Gap Analysis (Phase 4c)

Analyzes conversation themes and help article references to identify:
1. Undocumented themes (high-frequency themes without help articles)
2. Confusing articles (articles referenced but didn't resolve the issue)
3. Documentation gaps by product area

Requires:
- Phase 4a complete (help_article_references table populated)
- Theme extraction complete (themes table populated)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import RealDictCursor
import os


@dataclass
class ThemeGap:
    """Represents a theme that appears frequently without documentation"""
    product_area: str
    component: str
    issue_signature: str
    conversation_count: int
    article_coverage: float  # % of conversations with article references
    avg_support_responses: float  # Higher = more complex/undocumented
    sample_conversation_ids: List[str]


@dataclass
class ArticleGap:
    """Represents an article that users reference but still have issues"""
    article_id: str
    article_url: str
    article_title: Optional[str]
    article_category: Optional[str]
    reference_count: int
    unresolved_count: int  # Conversations with article that still escalated
    confusion_rate: float  # unresolved_count / reference_count
    common_issues: List[str]  # Issue types from conversations
    sample_conversation_ids: List[str]


@dataclass
class ProductAreaCoverage:
    """Documentation coverage statistics for a product area"""
    product_area: str
    total_conversations: int
    conversations_with_articles: int
    coverage_rate: float
    top_undocumented_themes: List[ThemeGap]


@dataclass
class CoverageReport:
    """Weekly documentation coverage gap report"""
    report_date: datetime
    date_range_start: datetime
    date_range_end: datetime
    top_undocumented_themes: List[ThemeGap]
    top_confusing_articles: List[ArticleGap]
    product_area_breakdown: List[ProductAreaCoverage]
    summary_stats: Dict[str, any]


class DocumentationCoverageAnalyzer:
    """
    Analyzes documentation coverage gaps using conversation themes and help article references.

    Identifies opportunities to improve documentation based on real user conversations.
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize analyzer with database connection.

        Args:
            database_url: PostgreSQL connection string (defaults to DATABASE_URL env var)
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url)

    def find_undocumented_themes(
        self,
        min_frequency: int = 10,
        max_article_coverage: float = 0.20,
        days_back: int = 30
    ) -> List[ThemeGap]:
        """
        Find themes that appear frequently WITHOUT help article references.

        These represent documentation gaps - common issues users encounter
        that don't have (or users can't find) help articles.

        Args:
            min_frequency: Minimum conversation count to be considered
            max_article_coverage: Maximum % of conversations with articles (default 20%)
            days_back: Number of days to analyze (default 30)

        Returns:
            List of ThemeGap objects sorted by conversation count (descending)
        """
        query = """
        WITH theme_stats AS (
            SELECT
                t.product_area,
                t.component,
                t.issue_signature,
                COUNT(DISTINCT t.conversation_id) as total_conversations,
                COUNT(DISTINCT har.conversation_id) as conversations_with_articles,
                COALESCE(
                    ROUND(
                        COUNT(DISTINCT har.conversation_id)::numeric /
                        NULLIF(COUNT(DISTINCT t.conversation_id), 0),
                        3
                    ),
                    0
                ) as article_coverage,
                AVG(c.support_response_count) as avg_support_responses,
                ARRAY_AGG(DISTINCT t.conversation_id)
                    FILTER (WHERE har.conversation_id IS NULL) as sample_ids_without_articles
            FROM themes t
            JOIN conversations c ON t.conversation_id = c.id
            LEFT JOIN help_article_references har ON t.conversation_id = har.conversation_id
            WHERE t.extracted_at > NOW() - INTERVAL '%s days'
            GROUP BY t.product_area, t.component, t.issue_signature
            HAVING COUNT(DISTINCT t.conversation_id) >= %s
                AND COALESCE(
                    COUNT(DISTINCT har.conversation_id)::numeric /
                    NULLIF(COUNT(DISTINCT t.conversation_id), 0),
                    0
                ) <= %s
        )
        SELECT
            product_area,
            component,
            issue_signature,
            total_conversations,
            article_coverage,
            avg_support_responses,
            sample_ids_without_articles[1:5] as sample_conversation_ids
        FROM theme_stats
        ORDER BY total_conversations DESC, article_coverage ASC
        LIMIT 50;
        """

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (days_back, min_frequency, max_article_coverage))
                results = cur.fetchall()

        return [
            ThemeGap(
                product_area=row['product_area'],
                component=row['component'],
                issue_signature=row['issue_signature'],
                conversation_count=row['total_conversations'],
                article_coverage=float(row['article_coverage']),
                avg_support_responses=float(row['avg_support_responses'] or 0),
                sample_conversation_ids=row['sample_conversation_ids'] or []
            )
            for row in results
        ]

    def find_confusing_articles(
        self,
        min_frequency: int = 5,
        min_confusion_rate: float = 0.40,
        days_back: int = 30
    ) -> List[ArticleGap]:
        """
        Find articles that users reference but still have issues/escalations.

        These represent confusing or incomplete documentation - users found the article
        but it didn't resolve their issue (indicated by continued support responses
        or bug reports/escalations).

        Args:
            min_frequency: Minimum reference count to be considered
            min_confusion_rate: Minimum % of refs that didn't resolve (default 40%)
            days_back: Number of days to analyze (default 30)

        Returns:
            List of ArticleGap objects sorted by confusion rate (descending)
        """
        query = """
        WITH article_stats AS (
            SELECT
                har.article_id,
                har.article_url,
                har.article_title,
                har.article_category,
                COUNT(DISTINCT har.conversation_id) as total_references,
                -- Count "unresolved" conversations (bug reports, feature requests, or 2+ support responses)
                COUNT(DISTINCT har.conversation_id) FILTER (
                    WHERE c.issue_type IN ('bug_report', 'feature_request')
                       OR c.support_response_count >= 2
                ) as unresolved_count,
                COALESCE(
                    ROUND(
                        COUNT(DISTINCT har.conversation_id) FILTER (
                            WHERE c.issue_type IN ('bug_report', 'feature_request')
                               OR c.support_response_count >= 2
                        )::numeric /
                        NULLIF(COUNT(DISTINCT har.conversation_id), 0),
                        3
                    ),
                    0
                ) as confusion_rate,
                ARRAY_AGG(DISTINCT c.issue_type) FILTER (
                    WHERE c.issue_type IN ('bug_report', 'feature_request')
                       OR c.support_response_count >= 2
                ) as common_issues,
                ARRAY_AGG(DISTINCT har.conversation_id)
                    FILTER (
                        WHERE c.issue_type IN ('bug_report', 'feature_request')
                           OR c.support_response_count >= 2
                    ) as sample_unresolved_ids
            FROM help_article_references har
            JOIN conversations c ON har.conversation_id = c.id
            WHERE har.referenced_at > NOW() - INTERVAL '%s days'
            GROUP BY har.article_id, har.article_url, har.article_title, har.article_category
            HAVING COUNT(DISTINCT har.conversation_id) >= %s
                AND COALESCE(
                    COUNT(DISTINCT har.conversation_id) FILTER (
                        WHERE c.issue_type IN ('bug_report', 'feature_request')
                           OR c.support_response_count >= 2
                    )::numeric /
                    NULLIF(COUNT(DISTINCT har.conversation_id), 0),
                    0
                ) >= %s
        )
        SELECT
            article_id,
            article_url,
            article_title,
            article_category,
            total_references,
            unresolved_count,
            confusion_rate,
            common_issues,
            sample_unresolved_ids[1:5] as sample_conversation_ids
        FROM article_stats
        ORDER BY confusion_rate DESC, total_references DESC
        LIMIT 30;
        """

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (days_back, min_frequency, min_confusion_rate))
                results = cur.fetchall()

        return [
            ArticleGap(
                article_id=row['article_id'],
                article_url=row['article_url'],
                article_title=row['article_title'],
                article_category=row['article_category'],
                reference_count=row['total_references'],
                unresolved_count=row['unresolved_count'],
                confusion_rate=float(row['confusion_rate']),
                common_issues=row['common_issues'] or [],
                sample_conversation_ids=row['sample_conversation_ids'] or []
            )
            for row in results
        ]

    def analyze_product_area_coverage(
        self,
        days_back: int = 30,
        min_theme_frequency: int = 5
    ) -> List[ProductAreaCoverage]:
        """
        Analyze documentation coverage by product area.

        Shows which product areas have good documentation coverage vs gaps.

        Args:
            days_back: Number of days to analyze (default 30)
            min_theme_frequency: Min frequency for undocumented theme inclusion

        Returns:
            List of ProductAreaCoverage objects sorted by coverage rate (ascending)
        """
        # First, get overall coverage by product area
        coverage_query = """
        SELECT
            t.product_area,
            COUNT(DISTINCT t.conversation_id) as total_conversations,
            COUNT(DISTINCT har.conversation_id) as conversations_with_articles,
            COALESCE(
                ROUND(
                    COUNT(DISTINCT har.conversation_id)::numeric /
                    NULLIF(COUNT(DISTINCT t.conversation_id), 0) * 100,
                    1
                ),
                0
            ) as coverage_rate
        FROM themes t
        LEFT JOIN help_article_references har ON t.conversation_id = har.conversation_id
        WHERE t.extracted_at > NOW() - INTERVAL '%s days'
        GROUP BY t.product_area
        ORDER BY coverage_rate ASC, total_conversations DESC;
        """

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(coverage_query, (days_back,))
                coverage_results = cur.fetchall()

        # For each product area, get top undocumented themes
        product_areas = []
        for row in coverage_results:
            product_area = row['product_area']

            # Get undocumented themes for this product area
            themes_query = """
            WITH theme_stats AS (
                SELECT
                    t.component,
                    t.issue_signature,
                    COUNT(DISTINCT t.conversation_id) as total_conversations,
                    COUNT(DISTINCT har.conversation_id) as conversations_with_articles,
                    COALESCE(
                        ROUND(
                            COUNT(DISTINCT har.conversation_id)::numeric /
                            NULLIF(COUNT(DISTINCT t.conversation_id), 0),
                            3
                        ),
                        0
                    ) as article_coverage,
                    AVG(c.support_response_count) as avg_support_responses,
                    ARRAY_AGG(DISTINCT t.conversation_id)
                        FILTER (WHERE har.conversation_id IS NULL) as sample_ids
                FROM themes t
                JOIN conversations c ON t.conversation_id = c.id
                LEFT JOIN help_article_references har ON t.conversation_id = har.conversation_id
                WHERE t.product_area = %s
                  AND t.extracted_at > NOW() - INTERVAL '%s days'
                GROUP BY t.component, t.issue_signature
                HAVING COUNT(DISTINCT t.conversation_id) >= %s
            )
            SELECT * FROM theme_stats
            ORDER BY total_conversations DESC
            LIMIT 5;
            """

            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(themes_query, (product_area, days_back, min_theme_frequency))
                    theme_results = cur.fetchall()

            top_themes = [
                ThemeGap(
                    product_area=product_area,
                    component=theme['component'],
                    issue_signature=theme['issue_signature'],
                    conversation_count=theme['total_conversations'],
                    article_coverage=float(theme['article_coverage']),
                    avg_support_responses=float(theme['avg_support_responses'] or 0),
                    sample_conversation_ids=(theme['sample_ids'] or [])[:5]
                )
                for theme in theme_results
            ]

            product_areas.append(
                ProductAreaCoverage(
                    product_area=product_area,
                    total_conversations=row['total_conversations'],
                    conversations_with_articles=row['conversations_with_articles'],
                    coverage_rate=float(row['coverage_rate']),
                    top_undocumented_themes=top_themes
                )
            )

        return product_areas

    def generate_weekly_report(
        self,
        days_back: int = 7,
        min_theme_frequency: int = 10,
        min_article_frequency: int = 5
    ) -> CoverageReport:
        """
        Generate comprehensive weekly documentation coverage gap report.

        Args:
            days_back: Number of days to analyze (default 7 for weekly)
            min_theme_frequency: Min conversation count for undocumented themes
            min_article_frequency: Min reference count for confusing articles

        Returns:
            CoverageReport with all gap analysis data
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Gather all analysis data
        undocumented_themes = self.find_undocumented_themes(
            min_frequency=min_theme_frequency,
            max_article_coverage=0.20,
            days_back=days_back
        )

        confusing_articles = self.find_confusing_articles(
            min_frequency=min_article_frequency,
            min_confusion_rate=0.40,
            days_back=days_back
        )

        product_area_coverage = self.analyze_product_area_coverage(
            days_back=days_back,
            min_theme_frequency=5
        )

        # Calculate summary statistics
        total_conversations = sum(pa.total_conversations for pa in product_area_coverage)
        total_with_articles = sum(pa.conversations_with_articles for pa in product_area_coverage)
        overall_coverage = (
            (total_with_articles / total_conversations * 100)
            if total_conversations > 0
            else 0
        )

        summary_stats = {
            "total_conversations": total_conversations,
            "conversations_with_articles": total_with_articles,
            "overall_coverage_rate": round(overall_coverage, 1),
            "undocumented_theme_count": len(undocumented_themes),
            "confusing_article_count": len(confusing_articles),
            "product_areas_analyzed": len(product_area_coverage)
        }

        return CoverageReport(
            report_date=end_date,
            date_range_start=start_date,
            date_range_end=end_date,
            top_undocumented_themes=undocumented_themes[:10],
            top_confusing_articles=confusing_articles[:10],
            product_area_breakdown=product_area_coverage,
            summary_stats=summary_stats
        )
