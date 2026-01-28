#!/usr/bin/env python3
"""
Context Gap Analysis Script (Phase 4 - Context Usage Instrumentation)

Analyzes the context_usage_logs table to identify:
1. Most frequently missing context (context_gaps)
2. Most frequently used context (context_used)
3. Recommendations for documentation improvements

Usage:
    # Analyze last 7 days (default)
    python scripts/analyze_context_gaps.py

    # Analyze last 30 days
    python scripts/analyze_context_gaps.py --days 30

    # Analyze specific pipeline run
    python scripts/analyze_context_gaps.py --pipeline-run 123

    # Output as JSON
    python scripts/analyze_context_gaps.py --json

    # Save to file
    python scripts/analyze_context_gaps.py --output results/context_gaps.txt
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.connection import get_connection


@dataclass
class ContextGapAnalysis:
    """Results of context gap analysis."""

    period_start: datetime
    period_end: datetime
    pipeline_run_id: Optional[int] = None
    total_extractions: int = 0
    total_with_gaps: int = 0
    total_with_context: int = 0

    # Top gaps and usage
    top_gaps: list[tuple[str, int]] = field(default_factory=list)
    top_used: list[tuple[str, int]] = field(default_factory=list)

    # Product area breakdown
    gaps_by_product_area: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    used_by_product_area: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


def analyze_context_gaps(
    days: int = 7,
    pipeline_run_id: Optional[int] = None,
    limit: int = 20,
) -> ContextGapAnalysis:
    """
    Analyze context_usage_logs for patterns in missing and used context.

    Args:
        days: Number of days to look back (ignored if pipeline_run_id provided)
        pipeline_run_id: Specific pipeline run to analyze
        limit: Maximum number of items to return in top lists

    Returns:
        ContextGapAnalysis with aggregated results
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Determine date range
            if pipeline_run_id:
                # Get date range from specific run
                cur.execute(
                    """
                    SELECT started_at, COALESCE(completed_at, NOW()) as end_time
                    FROM pipeline_runs WHERE id = %s
                    """,
                    (pipeline_run_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Pipeline run {pipeline_run_id} not found")
                period_start = row[0]
                period_end = row[1]

                # Query with pipeline_run_id filter
                cur.execute(
                    """
                    SELECT
                        c.context_used,
                        c.context_gaps,
                        t.product_area
                    FROM context_usage_logs c
                    LEFT JOIN themes t ON c.theme_id = t.id
                    WHERE c.pipeline_run_id = %s
                    """,
                    (pipeline_run_id,),
                )
            else:
                # Use date range
                period_end = datetime.now(timezone.utc)
                period_start = period_end - timedelta(days=days)

                cur.execute(
                    """
                    SELECT
                        c.context_used,
                        c.context_gaps,
                        t.product_area
                    FROM context_usage_logs c
                    LEFT JOIN themes t ON c.theme_id = t.id
                    WHERE c.created_at >= %s AND c.created_at <= %s
                    """,
                    (period_start, period_end),
                )

            rows = cur.fetchall()

    # Aggregate results
    gap_counter: Counter[str] = Counter()
    used_counter: Counter[str] = Counter()
    gaps_by_area: dict[str, Counter[str]] = {}
    used_by_area: dict[str, Counter[str]] = {}

    total_with_gaps = 0
    total_with_context = 0

    for context_used, context_gaps, product_area in rows:
        product_area = product_area or "unknown"

        # Initialize counters for product area if needed
        if product_area not in gaps_by_area:
            gaps_by_area[product_area] = Counter()
        if product_area not in used_by_area:
            used_by_area[product_area] = Counter()

        # Process context_gaps
        if context_gaps and isinstance(context_gaps, list):
            total_with_gaps += 1
            for gap in context_gaps:
                if isinstance(gap, str) and gap.strip():
                    gap_counter[gap] += 1
                    gaps_by_area[product_area][gap] += 1

        # Process context_used
        if context_used and isinstance(context_used, list):
            total_with_context += 1
            for used in context_used:
                if isinstance(used, str) and used.strip():
                    used_counter[used] += 1
                    used_by_area[product_area][used] += 1

    # Build result
    analysis = ContextGapAnalysis(
        period_start=period_start,
        period_end=period_end,
        pipeline_run_id=pipeline_run_id,
        total_extractions=len(rows),
        total_with_gaps=total_with_gaps,
        total_with_context=total_with_context,
        top_gaps=gap_counter.most_common(limit),
        top_used=used_counter.most_common(limit),
    )

    # Add product area breakdowns (top 5 per area)
    for area, counter in gaps_by_area.items():
        if counter:
            analysis.gaps_by_product_area[area] = counter.most_common(5)

    for area, counter in used_by_area.items():
        if counter:
            analysis.used_by_product_area[area] = counter.most_common(5)

    return analysis


def format_text_report(analysis: ContextGapAnalysis) -> str:
    """Format analysis results as human-readable text."""
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append("Context Gap Analysis Report")
    lines.append("=" * 70)
    lines.append("")

    # Period info
    if analysis.pipeline_run_id:
        lines.append(f"Pipeline Run: {analysis.pipeline_run_id}")
    lines.append(
        f"Period: {analysis.period_start.strftime('%Y-%m-%d %H:%M')} to "
        f"{analysis.period_end.strftime('%Y-%m-%d %H:%M')}"
    )
    lines.append(f"Total extractions analyzed: {analysis.total_extractions}")
    lines.append(f"Extractions with gaps: {analysis.total_with_gaps}")
    lines.append(f"Extractions with context used: {analysis.total_with_context}")
    lines.append("")

    # Top missing context
    lines.append("-" * 70)
    lines.append("TOP MISSING CONTEXT (context_gaps)")
    lines.append("-" * 70)
    lines.append("")

    if analysis.top_gaps:
        for i, (gap, count) in enumerate(analysis.top_gaps, 1):
            # Truncate long gaps for display
            display_gap = gap[:60] + "..." if len(gap) > 60 else gap
            lines.append(f"  {i:2}. \"{display_gap}\" - {count} occurrences")
    else:
        lines.append("  No context gaps recorded in this period.")
    lines.append("")

    # Top used context
    lines.append("-" * 70)
    lines.append("TOP USED CONTEXT (context_used)")
    lines.append("-" * 70)
    lines.append("")

    if analysis.top_used:
        for i, (used, count) in enumerate(analysis.top_used, 1):
            display_used = used[:60] + "..." if len(used) > 60 else used
            lines.append(f"  {i:2}. \"{display_used}\" - {count} occurrences")
    else:
        lines.append("  No context usage recorded in this period.")
    lines.append("")

    # Product area breakdown for gaps
    if analysis.gaps_by_product_area:
        lines.append("-" * 70)
        lines.append("GAPS BY PRODUCT AREA")
        lines.append("-" * 70)
        lines.append("")

        for area in sorted(analysis.gaps_by_product_area.keys()):
            gaps = analysis.gaps_by_product_area[area]
            lines.append(f"  {area}:")
            for gap, count in gaps:
                display_gap = gap[:50] + "..." if len(gap) > 50 else gap
                lines.append(f"    - \"{display_gap}\" ({count})")
            lines.append("")

    # Recommendations
    lines.append("-" * 70)
    lines.append("RECOMMENDATIONS")
    lines.append("-" * 70)
    lines.append("")

    if analysis.top_gaps:
        top_gap = analysis.top_gaps[0][0]
        lines.append(f"  Priority 1: Add documentation for \"{top_gap[:50]}...\"")
        lines.append(f"             ({analysis.top_gaps[0][1]} occurrences)")
        lines.append("")

        if len(analysis.top_gaps) >= 3:
            lines.append("  Top 3 documentation gaps to address:")
            for gap, count in analysis.top_gaps[:3]:
                lines.append(f"    - {gap[:60]}")
    else:
        lines.append("  No recommendations - context coverage looks good!")

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    return "\n".join(lines)


def format_json_report(analysis: ContextGapAnalysis) -> str:
    """Format analysis results as JSON."""
    data = {
        "period": {
            "start": analysis.period_start.isoformat(),
            "end": analysis.period_end.isoformat(),
            "pipeline_run_id": analysis.pipeline_run_id,
        },
        "summary": {
            "total_extractions": analysis.total_extractions,
            "extractions_with_gaps": analysis.total_with_gaps,
            "extractions_with_context": analysis.total_with_context,
        },
        "top_gaps": [{"gap": gap, "count": count} for gap, count in analysis.top_gaps],
        "top_used": [
            {"context": used, "count": count} for used, count in analysis.top_used
        ],
        "gaps_by_product_area": {
            area: [{"gap": gap, "count": count} for gap, count in gaps]
            for area, gaps in analysis.gaps_by_product_area.items()
        },
        "used_by_product_area": {
            area: [{"context": used, "count": count} for used, count in items]
            for area, items in analysis.used_by_product_area.items()
        },
    }
    return json.dumps(data, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze context usage logs to identify documentation gaps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze last 7 days (default)
  python scripts/analyze_context_gaps.py

  # Analyze last 30 days
  python scripts/analyze_context_gaps.py --days 30

  # Analyze specific pipeline run
  python scripts/analyze_context_gaps.py --pipeline-run 123

  # Output as JSON
  python scripts/analyze_context_gaps.py --json

  # Save to file
  python scripts/analyze_context_gaps.py --output results/context_gaps.txt
        """,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    parser.add_argument(
        "--pipeline-run",
        type=int,
        dest="pipeline_run_id",
        help="Analyze specific pipeline run ID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum items in top lists (default: 20)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save output to file",
    )

    args = parser.parse_args()

    # Run analysis
    try:
        analysis = analyze_context_gaps(
            days=args.days,
            pipeline_run_id=args.pipeline_run_id,
            limit=args.limit,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        print("\nEnsure DATABASE_URL is set correctly.", file=sys.stderr)
        sys.exit(1)

    # Format output
    if args.json:
        output = format_json_report(analysis)
    else:
        output = format_text_report(analysis)

    # Print to console
    print(output)

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
        print(f"\nReport saved to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
