#!/usr/bin/env python3
"""
Run classification on last 30 days of Intercom conversations and create
Shortcut stories for manual review.

Creates one story per conversation_type with aggregated counts and sample excerpts.
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from intercom_client import IntercomClient
from classifier_stage1 import classify_stage1


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."


def run_classification(days: int = 30, max_conversations: int = None):
    """
    Fetch and classify conversations, then create Shortcut stories.
    """
    print(f"\n{'='*60}")
    print(f"30-Day Classification Pipeline")
    print(f"{'='*60}")
    print(f"Fetching conversations from last {days} days...")
    print()

    client = IntercomClient()
    since = datetime.utcnow() - timedelta(days=days)

    # Aggregate by conversation_type
    aggregated = defaultdict(lambda: {
        "count": 0,
        "high_confidence": 0,
        "samples": [],  # (id, excerpt, confidence, routing_priority)
    })

    total_fetched = 0
    total_classified = 0

    # Fetch and classify
    print("Fetching and classifying conversations...")
    for parsed, raw_conv in client.fetch_quality_conversations(since=since, max_pages=None):
        total_fetched += 1

        try:
            result = classify_stage1(
                customer_message=parsed.source_body,
                source_type=parsed.source_type
            )
            total_classified += 1

            conv_type = result["conversation_type"]
            confidence = result["confidence"]
            priority = result.get("routing_priority", "normal")

            agg = aggregated[conv_type]
            agg["count"] += 1
            if confidence == "high":
                agg["high_confidence"] += 1

            # Keep up to 5 samples per type
            if len(agg["samples"]) < 5:
                agg["samples"].append({
                    "id": parsed.id,
                    "excerpt": truncate(parsed.source_body),
                    "confidence": confidence,
                    "priority": priority,
                    "created_at": parsed.created_at.isoformat(),
                })

            # Progress indicator
            if total_classified % 10 == 0:
                print(f"  Classified {total_classified} conversations...", flush=True)

        except Exception as e:
            print(f"  Error classifying {parsed.id}: {e}")
            continue

        if max_conversations and total_classified >= max_conversations:
            break

    print(f"\nClassified {total_classified} of {total_fetched} conversations")
    print()

    # Print summary
    print(f"{'='*60}")
    print("Classification Summary")
    print(f"{'='*60}")

    sorted_types = sorted(aggregated.items(), key=lambda x: x[1]["count"], reverse=True)

    for conv_type, data in sorted_types:
        high_pct = (data["high_confidence"] / data["count"] * 100) if data["count"] > 0 else 0
        print(f"\n{conv_type}:")
        print(f"  Count: {data['count']}")
        print(f"  High confidence: {data['high_confidence']} ({high_pct:.0f}%)")
        print(f"  Sample excerpts:")
        for sample in data["samples"][:3]:
            print(f"    - [{sample['priority']}] {sample['excerpt'][:80]}...")

    # Create Shortcut stories
    print(f"\n{'='*60}")
    print("Creating Shortcut Stories")
    print(f"{'='*60}")

    create_shortcut_stories(sorted_types, days)

    return aggregated


def create_shortcut_stories(sorted_types: list, days: int):
    """Create Shortcut stories for each conversation type."""
    import requests

    token = os.getenv("SHORTCUT_API_TOKEN")
    if not token:
        print("ERROR: SHORTCUT_API_TOKEN not set")
        return

    headers = {
        "Content-Type": "application/json",
        "Shortcut-Token": token,
    }

    # Get Backlog state ID
    workflow_resp = requests.get(
        "https://api.app.shortcut.com/api/v3/workflows",
        headers=headers
    )
    workflows = workflow_resp.json()
    backlog_state_id = None
    for wf in workflows:
        for state in wf.get("states", []):
            if state["name"] == "Backlog":
                backlog_state_id = state["id"]
                break

    if not backlog_state_id:
        print("ERROR: Could not find Backlog state")
        return

    stories_created = []

    for conv_type, data in sorted_types:
        if data["count"] == 0:
            continue

        # Build description with samples
        description = f"""## Classification Results (Last {days} Days)

**Conversation Type**: {conv_type}
**Total Count**: {data['count']}
**High Confidence**: {data['high_confidence']} ({data['high_confidence']/data['count']*100:.0f}%)

---

## Sample Conversations

"""
        for i, sample in enumerate(data["samples"], 1):
            description += f"""### Sample {i}
- **Conversation ID**: {sample['id']}
- **Created**: {sample['created_at']}
- **Confidence**: {sample['confidence']}
- **Routing Priority**: {sample['priority']}
- **Excerpt**: {sample['excerpt']}

"""

        description += """---

## Review Checklist
- [ ] Classification accuracy looks correct
- [ ] Sample excerpts match the category
- [ ] Priority assignments are appropriate
- [ ] No obvious misclassifications

---
*Generated by FeedForward Classification Pipeline*
"""

        # Determine story type based on conversation type
        if conv_type in ("bug_report", "product_issue"):
            story_type = "bug"
        elif conv_type == "feature_request":
            story_type = "feature"
        else:
            story_type = "chore"

        # Create story
        story_data = {
            "name": f"[{data['count']}] {conv_type.replace('_', ' ').title()} - Classification Review",
            "description": description,
            "story_type": story_type,
            "workflow_state_id": backlog_state_id,
        }

        try:
            resp = requests.post(
                "https://api.app.shortcut.com/api/v3/stories",
                json=story_data,
                headers=headers,
            )
            resp.raise_for_status()
            story = resp.json()
            stories_created.append({
                "id": story["id"],
                "name": story_data["name"],
                "url": story["app_url"],
            })
            print(f"  Created: {story_data['name']}")
            print(f"    URL: {story['app_url']}")
        except Exception as e:
            print(f"  ERROR creating story for {conv_type}: {e}")

    print(f"\n{'='*60}")
    print(f"Created {len(stories_created)} Shortcut stories for review")
    print(f"{'='*60}")

    return stories_created


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run 30-day classification")
    parser.add_argument("--days", type=int, default=30, help="Days to look back")
    parser.add_argument("--max", type=int, help="Maximum conversations to process")

    args = parser.parse_args()

    run_classification(days=args.days, max_conversations=args.max)
