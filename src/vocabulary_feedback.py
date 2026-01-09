#!/usr/bin/env python3
"""
Vocabulary Feedback Loop for FeedForward.

Monitors Shortcut stories for new labels/product areas that aren't in our vocabulary.
Run periodically (weekly/monthly) to detect vocabulary drift.

Usage:
    python -m src.vocabulary_feedback --days 30
    python -m src.vocabulary_feedback --days 90 --output report.md
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

SHORTCUT_API_TOKEN = os.getenv("SHORTCUT_API_TOKEN")
SHORTCUT_API_URL = "https://api.app.shortcut.com/api/v3"

# Current FeedForward vocabulary coverage
COVERED_PRODUCT_AREAS = {
    # Scheduling family
    "Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop",
    # AI/Creation family
    "Create", "Made For You", "GW Labs", "SmartPin", "CoPilot",
    # Analytics
    "Analytics",
    # Billing
    "Billing & Settings",
    # Integrations
    "Extension", "Product Dashboard",
    # Communities
    "Communities",
    # Smart.bio
    "Smart.bio",
    # Other/System
    "System wide", "Jarvis", "Internal Tracking and Reporting", "Email", "Ads",
}


def fetch_recent_stories(days: int = 30) -> list:
    """Fetch stories created/updated in the last N days from Shortcut."""
    if not SHORTCUT_API_TOKEN:
        print("ERROR: SHORTCUT_API_TOKEN not set in environment")
        return []

    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    print(f"Fetching stories updated since {since_date}...")

    try:
        # Use search endpoint to find recent stories
        response = requests.post(
            f"{SHORTCUT_API_URL}/stories/search",
            headers={
                "Content-Type": "application/json",
                "Shortcut-Token": SHORTCUT_API_TOKEN,
            },
            json={
                "updated_at_start": since_date,
            },
            timeout=60,
        )

        if response.status_code in (200, 201):
            data = response.json()
            # API returns list directly or wrapped in "data"
            if isinstance(data, list):
                stories = data
            else:
                stories = data.get("data", [])
            print(f"Found {len(stories)} stories")
            return stories
        else:
            print(f"Error: {response.status_code} - {response.text[:200]}")
            return []

    except requests.RequestException as e:
        print(f"Request error: {e}")
        return []


def extract_labels_and_areas(stories: list) -> dict:
    """Extract all labels and product areas from stories."""
    labels = defaultdict(int)
    product_areas = defaultdict(int)

    for story in stories:
        # Extract labels
        for label in story.get("labels", []):
            if isinstance(label, dict):
                label_name = label.get("name", "")
            else:
                label_name = str(label)
            if label_name:
                labels[label_name] += 1

        # Extract product area from custom fields
        for cf in story.get("custom_fields", []):
            if "product" in cf.get("name", "").lower():
                value = cf.get("value")
                if value:
                    product_areas[value] += 1

    return {
        "labels": dict(labels),
        "product_areas": dict(product_areas),
    }


def identify_gaps(extracted: dict) -> dict:
    """Identify labels/areas not in current vocabulary."""
    gaps = {
        "product_areas": {},
        "labels": {},
    }

    # Check product areas
    for pa, count in extracted.get("product_areas", {}).items():
        if pa not in COVERED_PRODUCT_AREAS:
            gaps["product_areas"][pa] = {
                "count": count,
                "priority": "high" if count >= 10 else "medium" if count >= 5 else "low",
            }

    # Check labels (for potential theme expansion)
    for label, count in extracted.get("labels", {}).items():
        # Filter out generic labels
        if label.lower() in ["bug", "feature", "urgent", "low", "medium", "high"]:
            continue
        if count >= 3:  # Only report labels with multiple occurrences
            gaps["labels"][label] = {
                "count": count,
                "priority": "high" if count >= 10 else "medium" if count >= 5 else "low",
            }

    return gaps


def generate_report(gaps: dict, extracted: dict, days: int) -> str:
    """Generate markdown feedback report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    high_priority_pa = [pa for pa, info in gaps["product_areas"].items() if info["priority"] == "high"]
    med_priority_pa = [pa for pa, info in gaps["product_areas"].items() if info["priority"] == "medium"]

    report = f"""# Vocabulary Feedback Report

**Generated**: {timestamp}
**Period**: Last {days} days
**Total Product Areas Seen**: {len(extracted.get('product_areas', {}))}
**Total Labels Seen**: {len(extracted.get('labels', {}))}

## Summary

| Metric | Count |
|--------|-------|
| Product Area Gaps | {len(gaps['product_areas'])} |
| High Priority Gaps | {len(high_priority_pa)} |
| Medium Priority Gaps | {len(med_priority_pa)} |

## Product Area Coverage

### Currently Covered ({len(COVERED_PRODUCT_AREAS)} areas)
{', '.join(sorted(COVERED_PRODUCT_AREAS))}

"""

    if gaps["product_areas"]:
        report += "### Gaps Found (NOT in vocabulary)\n\n"
        report += "| Product Area | Occurrences | Priority |\n"
        report += "|--------------|-------------|----------|\n"

        for pa, info in sorted(gaps["product_areas"].items(), key=lambda x: -x[1]["count"]):
            report += f"| {pa} | {info['count']} | {info['priority']} |\n"
    else:
        report += "### No Product Area Gaps Found\n\n"
        report += "All product areas in recent stories are covered by the current vocabulary.\n"

    if gaps["labels"]:
        report += "\n## Notable Labels (potential theme candidates)\n\n"
        report += "| Label | Occurrences | Priority |\n"
        report += "|-------|-------------|----------|\n"

        for label, info in sorted(gaps["labels"].items(), key=lambda x: -x[1]["count"])[:20]:
            report += f"| {label} | {info['count']} | {info['priority']} |\n"

    report += f"""

## Recommendations

"""

    if high_priority_pa:
        report += f"### Immediate Action Required\n\n"
        for pa in high_priority_pa:
            count = gaps["product_areas"][pa]["count"]
            report += f"- **Add '{pa}'** to vocabulary ({count} occurrences)\n"
        report += "\n"

    if med_priority_pa:
        report += f"### Monitor These Areas\n\n"
        for pa in med_priority_pa:
            count = gaps["product_areas"][pa]["count"]
            report += f"- '{pa}' ({count} occurrences)\n"
        report += "\n"

    if not gaps["product_areas"] and not gaps["labels"]:
        report += "No action required. Vocabulary is up to date.\n"

    report += """
## Next Steps

1. Review high-priority gaps and add to vocabulary if confirmed
2. Run this report monthly to catch vocabulary drift
3. Update `COVERED_PRODUCT_AREAS` in this script after adding new areas

## CLI Commands

```bash
# Run monthly check
python -m src.vocabulary_feedback --days 30

# Run quarterly check
python -m src.vocabulary_feedback --days 90

# Save to file
python -m src.vocabulary_feedback --days 30 --output reports/vocab_feedback.md
```
"""

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Monitor Shortcut for vocabulary gaps in FeedForward"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: print to stdout)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of markdown"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("VOCABULARY FEEDBACK LOOP")
    print("=" * 60)

    # Fetch recent stories
    stories = fetch_recent_stories(args.days)

    if not stories:
        print("No stories found or API error. Check SHORTCUT_API_TOKEN.")
        sys.exit(1)

    # Extract labels and product areas
    extracted = extract_labels_and_areas(stories)

    print(f"Product areas found: {len(extracted['product_areas'])}")
    print(f"Labels found: {len(extracted['labels'])}")

    # Identify gaps
    gaps = identify_gaps(extracted)

    print(f"Product area gaps: {len(gaps['product_areas'])}")

    if args.json:
        output = json.dumps({
            "gaps": gaps,
            "extracted": extracted,
            "days": args.days,
            "generated_at": datetime.now().isoformat(),
        }, indent=2)
    else:
        output = generate_report(gaps, extracted, args.days)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + "=" * 60)
        print(output)

    # Summary
    if gaps["product_areas"]:
        print(f"\n ACTION REQUIRED: {len(gaps['product_areas'])} vocabulary gaps found")
    else:
        print("\n Vocabulary is up to date!")


if __name__ == "__main__":
    main()
