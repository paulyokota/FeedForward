#!/usr/bin/env python3
"""Compare Customer Voice Explorer findings against pipeline theme extraction.

This is the capability thesis evidence script for Issue #215. It reads:
1. Explorer findings from a checkpoint artifact (JSON file or stdin)
2. Pipeline themes from the `themes` table for the same time period

Then uses LLM-assisted comparison to produce a report with sections:
- Overlap: patterns found by both explorer and pipeline
- Novel: patterns the explorer found that the pipeline missed
- Pipeline-only: themes the pipeline extracted that the explorer didn't surface

Comparison prompt:
  The LLM receives explorer findings (pattern names + descriptions) and
  pipeline themes (issue_signatures + product_areas + diagnostic_summaries).
  It identifies semantic matches even when naming differs (e.g., explorer's
  "scheduling_confusion" matching pipeline's "scheduler/post-timing-confusion").

Inputs:
  --checkpoint-file: Path to JSON file with ExplorerCheckpoint artifacts
  --days: Time window (default 14) — matches explorer's time_window_days
  --run-id: Optional run ID for stable output filenames

Output:
  - Structured JSON report: reports/explorer_comparison_{run_id}_{days}d.json
  - Human-readable text to stdout

Usage:
  python scripts/compare_explorer_vs_pipeline.py --checkpoint-file artifacts.json
  python scripts/compare_explorer_vs_pipeline.py --checkpoint-file artifacts.json --days 7 --run-id abc123
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")


COMPARISON_PROMPT = """\
You are comparing two different approaches to analyzing customer support conversations.

**Approach A: Explorer Agent** (open-ended pattern discovery, no predefined categories)
Findings:
{explorer_findings}

**Approach B: Pipeline** (structured extraction with predefined taxonomy)
Themes extracted:
{pipeline_themes}

---

Compare these two sets of findings. For each explorer finding, determine if the
pipeline captured something semantically similar (even if named differently).
For each pipeline theme, determine if the explorer surfaced it.

Return as JSON:

{{
  "overlap": [
    {{
      "explorer_pattern": "pattern name from explorer",
      "pipeline_match": "issue_signature or product_area from pipeline",
      "match_quality": "exact|strong|weak",
      "notes": "how they relate"
    }}
  ],
  "novel_explorer": [
    {{
      "pattern_name": "pattern the explorer found but pipeline missed",
      "description": "what the explorer found",
      "why_pipeline_missed": "your hypothesis for why structured extraction missed this"
    }}
  ],
  "pipeline_only": [
    {{
      "issue_signature": "theme the pipeline found but explorer didn't surface",
      "product_area": "...",
      "why_explorer_missed": "your hypothesis"
    }}
  ],
  "summary": "1-2 paragraph assessment of the explorer's added value"
}}
"""


def load_checkpoint(filepath: str) -> dict:
    """Load ExplorerCheckpoint from a JSON file."""
    with open(filepath) as f:
        return json.load(f)


def fetch_pipeline_themes(days: int) -> list:
    """Fetch pipeline themes from the database for the given time window."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    from src.db.connection import get_connection_string

    conn = psycopg2.connect(get_connection_string())
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (issue_signature, product_area)
                    issue_signature,
                    product_area,
                    component,
                    diagnostic_summary,
                    COUNT(*) OVER (PARTITION BY issue_signature, product_area) as occurrence_count
                FROM themes
                WHERE extracted_at >= NOW() - INTERVAL '%s days'
                ORDER BY issue_signature, product_area, extracted_at DESC
                """,
                (days,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def format_explorer_findings(checkpoint: dict) -> str:
    """Format explorer findings for the comparison prompt."""
    findings = checkpoint.get("findings", [])
    if not findings:
        return "(no findings)"

    lines = []
    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. **{f.get('pattern_name', 'unnamed')}**: "
            f"{f.get('description', 'no description')} "
            f"(confidence: {f.get('confidence', 'unknown')}, "
            f"evidence: {len(f.get('evidence', []))} conversations)"
        )
    return "\n".join(lines)


def format_pipeline_themes(themes: list) -> str:
    """Format pipeline themes for the comparison prompt.

    Aggregates by product_area/component to stay within LLM context limits.
    Shows top issue signatures per area (by occurrence count) rather than
    listing every individual theme.
    """
    if not themes:
        return "(no themes extracted)"

    # Aggregate by product_area/component
    from collections import defaultdict

    areas = defaultdict(lambda: {"count": 0, "signatures": defaultdict(int)})
    for t in themes:
        key = f"{t['product_area']}/{t.get('component', 'general')}"
        areas[key]["count"] += t.get("occurrence_count", 1)
        areas[key]["signatures"][t["issue_signature"]] += t.get("occurrence_count", 1)

    # Sort areas by total count descending
    sorted_areas = sorted(areas.items(), key=lambda x: x[1]["count"], reverse=True)

    lines = [f"Total: {len(themes)} distinct themes across {len(sorted_areas)} product areas\n"]
    for i, (area, data) in enumerate(sorted_areas, 1):
        top_sigs = sorted(data["signatures"].items(), key=lambda x: x[1], reverse=True)[:5]
        sig_list = "; ".join(f"{sig} ({cnt})" for sig, cnt in top_sigs)
        lines.append(
            f"{i}. **{area}** (total: {data['count']})\n"
            f"   Top issues: {sig_list}"
        )
    return "\n".join(lines)


def run_comparison(explorer_text: str, pipeline_text: str) -> dict:
    """Use LLM to compare explorer findings against pipeline themes."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = COMPARISON_PROMPT.format(
        explorer_findings=explorer_text,
        pipeline_themes=pipeline_text,
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are an analyst comparing two approaches to customer feedback analysis.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


def print_report(comparison: dict, checkpoint: dict, theme_count: int) -> None:
    """Print human-readable comparison report."""
    coverage = checkpoint.get("coverage", {})
    findings_count = len(checkpoint.get("findings", []))

    print("=" * 70)
    print("EXPLORER vs PIPELINE COMPARISON REPORT")
    print("=" * 70)
    print()
    print(f"Explorer: {findings_count} findings from {coverage.get('conversations_reviewed', '?')} conversations")
    print(f"Pipeline: {theme_count} distinct themes")
    print(f"Time window: {coverage.get('time_window_days', '?')} days")
    print()

    overlap = comparison.get("overlap", [])
    novel = comparison.get("novel_explorer", [])
    pipeline_only = comparison.get("pipeline_only", [])

    print(f"--- OVERLAP ({len(overlap)} matches) ---")
    for item in overlap:
        print(f"  [{item.get('match_quality', '?')}] {item.get('explorer_pattern')} <-> {item.get('pipeline_match')}")
        if item.get("notes"):
            print(f"    {item['notes']}")
    print()

    print(f"--- NOVEL EXPLORER FINDINGS ({len(novel)}) ---")
    if novel:
        print("  (Patterns the explorer found that the pipeline missed)")
        for item in novel:
            print(f"  * {item.get('pattern_name')}: {item.get('description', '')[:100]}")
            if item.get("why_pipeline_missed"):
                print(f"    Why missed: {item['why_pipeline_missed']}")
    else:
        print("  (none)")
    print()

    print(f"--- PIPELINE-ONLY ({len(pipeline_only)}) ---")
    if pipeline_only:
        print("  (Themes the pipeline found that the explorer didn't surface)")
        for item in pipeline_only:
            print(f"  * {item.get('issue_signature')} ({item.get('product_area', '')})")
            if item.get("why_explorer_missed"):
                print(f"    Why missed: {item['why_explorer_missed']}")
    else:
        print("  (none)")
    print()

    print("--- SUMMARY ---")
    print(comparison.get("summary", "(no summary)"))
    print()
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Compare explorer findings against pipeline themes"
    )
    parser.add_argument(
        "--checkpoint-file",
        required=True,
        help="Path to JSON file with ExplorerCheckpoint artifacts",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=14,
        help="Time window in days (default: 14)",
    )
    parser.add_argument(
        "--run-id",
        default="manual",
        help="Run ID for output filename (default: 'manual')",
    )
    args = parser.parse_args()

    # Load explorer checkpoint
    print(f"Loading checkpoint from {args.checkpoint_file}...")
    checkpoint = load_checkpoint(args.checkpoint_file)

    # Fetch pipeline themes
    print(f"Fetching pipeline themes for last {args.days} days...")
    themes = fetch_pipeline_themes(args.days)
    print(f"Found {len(themes)} distinct pipeline themes")

    # Format for comparison
    explorer_text = format_explorer_findings(checkpoint)
    pipeline_text = format_pipeline_themes(themes)

    # Run LLM comparison
    print("Running LLM-assisted comparison...")
    comparison = run_comparison(explorer_text, pipeline_text)

    # Build full report
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "time_window_days": args.days,
        "explorer_findings_count": len(checkpoint.get("findings", [])),
        "pipeline_themes_count": len(themes),
        "explorer_coverage": checkpoint.get("coverage", {}),
        "comparison": comparison,
    }

    # Save structured report
    reports_dir = project_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_filename = f"explorer_comparison_{args.run_id}_{args.days}d.json"
    report_path = reports_dir / report_filename

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nStructured report saved to: {report_path}")

    # Print human-readable report
    print()
    print_report(comparison, checkpoint, len(themes))


if __name__ == "__main__":
    main()
