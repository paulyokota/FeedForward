#!/usr/bin/env python3
"""
Weekly Documentation Coverage Gap Report Generator (Phase 4c)

Generates actionable reports identifying:
1. Top 10 undocumented themes (high-frequency issues without help articles)
2. Top 10 confusing articles (users reference but still have issues)
3. Documentation coverage by product area

Usage:
    # Generate weekly report (last 7 days)
    python scripts/generate_doc_coverage_report.py --output results/doc_coverage_weekly.txt

    # Generate monthly report (last 30 days)
    python scripts/generate_doc_coverage_report.py --days 30 --output results/doc_coverage_monthly.txt

    # Custom thresholds
    python scripts/generate_doc_coverage_report.py \
        --min-theme-frequency 20 \
        --min-article-frequency 10 \
        --output results/doc_coverage_custom.txt

    # Send to Slack (requires SLACK_WEBHOOK_URL env var)
    python scripts/generate_doc_coverage_report.py --slack
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analytics.doc_coverage import (
    DocumentationCoverageAnalyzer,
    CoverageReport,
    ThemeGap,
    ArticleGap,
    ProductAreaCoverage
)


def format_theme_gap(gap: ThemeGap, rank: int) -> str:
    """Format a ThemeGap for text output"""
    return f"""
{rank}. {gap.product_area} > {gap.component} > {gap.issue_signature}
   Conversations: {gap.conversation_count}
   Article Coverage: {gap.article_coverage * 100:.1f}%
   Avg Support Responses: {gap.avg_support_responses:.1f}
   Sample Conversations: {', '.join(gap.sample_conversation_ids[:3])}
"""


def format_article_gap(gap: ArticleGap, rank: int) -> str:
    """Format an ArticleGap for text output"""
    return f"""
{rank}. {gap.article_title or gap.article_url}
   Category: {gap.article_category or 'Unknown'}
   References: {gap.reference_count}
   Unresolved: {gap.unresolved_count} ({gap.confusion_rate * 100:.1f}%)
   Common Issues: {', '.join(gap.common_issues)}
   Sample Conversations: {', '.join(gap.sample_conversation_ids[:3])}
   URL: {gap.article_url}
"""


def format_product_area_coverage(coverage: ProductAreaCoverage) -> str:
    """Format ProductAreaCoverage for text output"""
    output = f"""
{coverage.product_area}
   Total Conversations: {coverage.total_conversations}
   With Articles: {coverage.conversations_with_articles} ({coverage.coverage_rate:.1f}%)
"""

    if coverage.top_undocumented_themes:
        output += "   Top Undocumented Themes:\n"
        for i, theme in enumerate(coverage.top_undocumented_themes[:3], 1):
            output += f"      {i}. {theme.component} > {theme.issue_signature} ({theme.conversation_count} conversations)\n"

    return output


def generate_text_report(report: CoverageReport) -> str:
    """Generate formatted text report"""
    output = []

    # Header
    output.append("=" * 80)
    output.append("Documentation Coverage Gap Analysis Report")
    output.append("=" * 80)
    output.append(f"\nGenerated: {report.report_date.strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(f"Date Range: {report.date_range_start.strftime('%Y-%m-%d')} to {report.date_range_end.strftime('%Y-%m-%d')}")
    output.append("")

    # Summary Statistics
    output.append("-" * 80)
    output.append("SUMMARY")
    output.append("-" * 80)
    output.append(f"Total Conversations: {report.summary_stats['total_conversations']}")
    output.append(f"Conversations with Articles: {report.summary_stats['conversations_with_articles']}")
    output.append(f"Overall Coverage Rate: {report.summary_stats['overall_coverage_rate']}%")
    output.append(f"Undocumented Themes Identified: {report.summary_stats['undocumented_theme_count']}")
    output.append(f"Confusing Articles Identified: {report.summary_stats['confusing_article_count']}")
    output.append(f"Product Areas Analyzed: {report.summary_stats['product_areas_analyzed']}")
    output.append("")

    # Top Undocumented Themes
    output.append("-" * 80)
    output.append("TOP 10 UNDOCUMENTED THEMES")
    output.append("-" * 80)
    output.append("\nThese are high-frequency issues that users encounter without help article")
    output.append("references. Creating documentation for these could reduce support volume.\n")

    if report.top_undocumented_themes:
        for i, gap in enumerate(report.top_undocumented_themes, 1):
            output.append(format_theme_gap(gap, i))
    else:
        output.append("No undocumented themes found (all themes have good article coverage!)")

    # Top Confusing Articles
    output.append("-" * 80)
    output.append("TOP 10 CONFUSING ARTICLES")
    output.append("-" * 80)
    output.append("\nThese articles are referenced by users but don't resolve their issues.")
    output.append("Consider updating these articles for clarity or completeness.\n")

    if report.top_confusing_articles:
        for i, gap in enumerate(report.top_confusing_articles, 1):
            output.append(format_article_gap(gap, i))
    else:
        output.append("No confusing articles found (all referenced articles are effective!)")

    # Product Area Breakdown
    output.append("-" * 80)
    output.append("DOCUMENTATION COVERAGE BY PRODUCT AREA")
    output.append("-" * 80)
    output.append("\nShows documentation coverage rates and top gaps for each product area.\n")

    for coverage in report.product_area_breakdown:
        output.append(format_product_area_coverage(coverage))

    # Footer
    output.append("-" * 80)
    output.append("RECOMMENDED ACTIONS")
    output.append("-" * 80)
    output.append("""
1. Review undocumented themes and create new help articles for high-frequency issues
2. Update confusing articles with clearer instructions or additional context
3. Focus documentation efforts on product areas with lowest coverage rates
4. Track conversation volume reduction after adding/updating documentation

For conversation details, use: https://app.intercom.com/a/inbox/_/inbox/conversation/<id>
""")

    output.append("=" * 80)
    output.append(f"Report generated by FeedForward Documentation Coverage Analyzer")
    output.append("=" * 80)

    return "\n".join(output)


def send_to_slack(report_text: str, webhook_url: Optional[str] = None):
    """
    Send report to Slack via webhook.

    Args:
        report_text: Formatted report text
        webhook_url: Slack webhook URL (defaults to SLACK_WEBHOOK_URL env var)
    """
    webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL environment variable not set")

    import requests

    # Truncate if too long (Slack has message limits)
    max_length = 3000
    if len(report_text) > max_length:
        report_text = report_text[:max_length] + "\n\n[Report truncated - see full report in file]"

    payload = {
        "text": "📊 Weekly Documentation Coverage Gap Report",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Weekly Documentation Coverage Gap Report*\n" + report_text
                }
            }
        ]
    }

    response = requests.post(webhook_url, json=payload)
    response.raise_for_status()
    print("Report sent to Slack successfully")


def main():
    parser = argparse.ArgumentParser(
        description="Generate documentation coverage gap analysis report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate weekly report
  python scripts/generate_doc_coverage_report.py --output results/weekly.txt

  # Generate monthly report
  python scripts/generate_doc_coverage_report.py --days 30 --output results/monthly.txt

  # Send to Slack
  python scripts/generate_doc_coverage_report.py --slack
        """
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7 for weekly report)"
    )
    parser.add_argument(
        "--min-theme-frequency",
        type=int,
        default=10,
        help="Minimum conversation count for undocumented themes (default: 10)"
    )
    parser.add_argument(
        "--min-article-frequency",
        type=int,
        default=5,
        help="Minimum reference count for confusing articles (default: 5)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (e.g., results/doc_coverage_weekly.txt)"
    )
    parser.add_argument(
        "--slack",
        action="store_true",
        help="Send report to Slack (requires SLACK_WEBHOOK_URL env var)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format instead of text"
    )

    args = parser.parse_args()

    print(f"\n{'=' * 80}")
    print("Documentation Coverage Gap Analysis")
    print(f"{'=' * 80}\n")

    print(f"Analyzing last {args.days} days...")
    print(f"Min theme frequency: {args.min_theme_frequency}")
    print(f"Min article frequency: {args.min_article_frequency}")
    print()

    # Initialize analyzer
    try:
        analyzer = DocumentationCoverageAnalyzer()
    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease set DATABASE_URL environment variable:")
        print("export DATABASE_URL='postgresql://localhost:5432/feedforward'")
        sys.exit(1)

    # Generate report
    try:
        print("Generating report...")
        report = analyzer.generate_weekly_report(
            days_back=args.days,
            min_theme_frequency=args.min_theme_frequency,
            min_article_frequency=args.min_article_frequency
        )
        print("Report generated successfully!\n")
    except Exception as e:
        print(f"Error generating report: {e}")
        sys.exit(1)

    # Format output
    if args.json:
        # JSON output (for programmatic consumption)
        report_data = {
            "report_date": report.report_date.isoformat(),
            "date_range": {
                "start": report.date_range_start.isoformat(),
                "end": report.date_range_end.isoformat()
            },
            "summary": report.summary_stats,
            "undocumented_themes": [
                {
                    "product_area": gap.product_area,
                    "component": gap.component,
                    "issue_signature": gap.issue_signature,
                    "conversation_count": gap.conversation_count,
                    "article_coverage": gap.article_coverage,
                    "sample_ids": gap.sample_conversation_ids
                }
                for gap in report.top_undocumented_themes
            ],
            "confusing_articles": [
                {
                    "article_id": gap.article_id,
                    "article_url": gap.article_url,
                    "article_title": gap.article_title,
                    "reference_count": gap.reference_count,
                    "unresolved_count": gap.unresolved_count,
                    "confusion_rate": gap.confusion_rate,
                    "sample_ids": gap.sample_conversation_ids
                }
                for gap in report.top_confusing_articles
            ],
            "product_areas": [
                {
                    "product_area": pa.product_area,
                    "total_conversations": pa.total_conversations,
                    "coverage_rate": pa.coverage_rate
                }
                for pa in report.product_area_breakdown
            ]
        }
        output_text = json.dumps(report_data, indent=2)
    else:
        # Human-readable text output
        output_text = generate_text_report(report)

    # Print to console
    print(output_text)

    # Save to file
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text)
        print(f"\nReport saved to: {args.output}")

    # Send to Slack
    if args.slack:
        if args.json:
            print("\nWarning: --json format not supported for Slack. Generating text format...")
            output_text = generate_text_report(report)

        try:
            send_to_slack(output_text)
        except Exception as e:
            print(f"Error sending to Slack: {e}")
            sys.exit(1)

    print(f"\n{'=' * 80}")
    print("Next Steps:")
    print(f"{'=' * 80}")
    print("\n1. Review undocumented themes and prioritize documentation creation")
    print("2. Update confusing articles for clarity")
    print("3. Focus on product areas with low coverage rates")
    print("4. Schedule this script to run weekly (cron or GitHub Actions)")
    print()


if __name__ == "__main__":
    main()
