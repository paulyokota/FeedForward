#!/usr/bin/env python3
"""
Create Shortcut stories from classification results with rich formatting.

Uses shared formatting from src/story_formatter.py for consistent output.

Usage:
    python scripts/create_shortcut_stories.py
    python scripts/create_shortcut_stories.py --input data/classification_results.jsonl
    python scripts/create_shortcut_stories.py --dry-run  # Preview without creating
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from story_formatter import (
    format_excerpt,
    build_story_description,
    build_story_name,
    get_story_type,
)


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_backlog_state_id(headers: dict) -> int:
    """Get the Backlog workflow state ID from Shortcut."""
    resp = requests.get(
        "https://api.app.shortcut.com/api/v3/workflows",
        headers=headers
    )
    resp.raise_for_status()
    workflows = resp.json()

    for wf in workflows:
        for state in wf.get("states", []):
            if state["name"] == "Backlog":
                return state["id"]

    raise ValueError("Could not find Backlog state in Shortcut workflows")


def create_stories(input_file: Path, dry_run: bool = False):
    """Create Shortcut stories from classification results."""
    load_env()

    token = os.getenv("SHORTCUT_API_TOKEN")
    if not token:
        print("ERROR: SHORTCUT_API_TOKEN not set in .env")
        sys.exit(1)

    token = token.strip()
    headers = {
        "Content-Type": "application/json",
        "Shortcut-Token": token,
    }

    # Load and aggregate results
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        print("Run classify_to_file.py first to generate classification results.")
        sys.exit(1)

    aggregated = defaultdict(lambda: {"count": 0, "samples": []})

    with open(input_file) as f:
        for line in f:
            r = json.loads(line)
            cat = r["category"]
            aggregated[cat]["count"] += 1
            if len(aggregated[cat]["samples"]) < 5:
                aggregated[cat]["samples"].append(r)

    total = sum(d["count"] for d in aggregated.values())
    sorted_cats = sorted(aggregated.items(), key=lambda x: x[1]["count"], reverse=True)

    print(f"\n{'='*60}")
    print("Creating Shortcut Stories from Classification Results")
    print(f"{'='*60}")
    print(f"Input: {input_file}")
    print(f"Total conversations: {total}")
    print(f"Categories: {len(sorted_cats)}")
    print(f"Dry run: {dry_run}")
    print()

    if not dry_run:
        backlog_state_id = get_backlog_state_id(headers)
        print(f"Backlog state ID: {backlog_state_id}")
        print()

    stories_created = []

    for category, data in sorted_cats:
        if data["count"] == 0 or category in ["spam", "error"]:
            print(f"Skipping: {category} (count={data['count']})")
            continue

        # Use shared formatting module
        story_type = get_story_type(category)
        story_name = build_story_name(category, data["count"])
        description = build_story_description(
            category=category,
            count=data["count"],
            total=total,
            samples=data["samples"],
        )

        if dry_run:
            print(f"Would create: {story_name}")
            print(f"  Type: {story_type}")
            print(f"  Samples: {len(data['samples'])}")
            # Show first excerpt format
            if data["samples"]:
                sample = data["samples"][0]
                formatted = format_excerpt(
                    conversation_id=sample.get("id", "unknown"),
                    email=sample.get("email"),
                    excerpt=sample.get("excerpt", ""),
                    org_id=sample.get("org_id"),
                    user_id=sample.get("user_id"),
                    intercom_url=sample.get("intercom_url"),
                    jarvis_org_url=sample.get("jarvis_org_url"),
                    jarvis_user_url=sample.get("jarvis_user_url"),
                )
                print(f"  First excerpt format:")
                print(f"    {formatted[:100]}...")
            print()
        else:
            story_data = {
                "name": story_name,
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
                    "name": story_name,
                    "url": story["app_url"]
                })
                print(f"Created: {story_name}")
                print(f"  URL: {story['app_url']}")
            except Exception as e:
                print(f"ERROR creating story for {category}: {e}")

    print(f"\n{'='*60}")
    if dry_run:
        print(f"Dry run complete. Would create {len(sorted_cats) - 2} stories.")
    else:
        print(f"Created {len(stories_created)} Shortcut stories for review")
    print("="*60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create Shortcut stories from classification results")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "classification_results.jsonl",
        help="Input JSONL file from classify_to_file.py"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview stories without creating them"
    )

    args = parser.parse_args()
    create_stories(args.input, args.dry_run)
