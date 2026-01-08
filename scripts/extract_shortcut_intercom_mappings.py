#!/usr/bin/env python3
"""
Extract Shortcut story ID → Intercom conversation ID mappings from CSV.
Then fetch those conversations from Intercom to get their Story ID v2 values.
"""

import csv
import re
import json
import os
import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Pattern to match conversation IDs in Intercom URLs
CONVERSATION_PATTERN = re.compile(r'/conversation/(\d+)')

def extract_mappings_from_csv(csv_path: str) -> dict[str, list[str]]:
    """Extract story_id -> [conversation_ids] mappings from CSV."""
    mappings = {}

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            story_id = row.get('id', '').strip()
            description = row.get('description', '')

            if not story_id or not description:
                continue

            # Find all conversation IDs in the description
            conv_ids = CONVERSATION_PATTERN.findall(description)

            if conv_ids:
                if story_id not in mappings:
                    mappings[story_id] = []
                for conv_id in conv_ids:
                    if conv_id not in mappings[story_id]:
                        mappings[story_id].append(conv_id)

    return mappings


def main():
    csv_path = 'data/shortcut_stories_with_intercom_links.csv'

    print(f"Reading {csv_path}...")
    mappings = extract_mappings_from_csv(csv_path)

    # Count stats
    total_stories = len(mappings)
    total_conversations = sum(len(convs) for convs in mappings.values())
    stories_with_multiple = sum(1 for convs in mappings.values() if len(convs) > 1)

    print(f"\nExtracted mappings:")
    print(f"  Stories with Intercom links: {total_stories}")
    print(f"  Total conversation IDs: {total_conversations}")
    print(f"  Stories with 2+ conversations: {stories_with_multiple}")

    # Distribution of conversations per story
    print(f"\nDistribution:")
    dist = {}
    for convs in mappings.values():
        n = len(convs)
        dist[n] = dist.get(n, 0) + 1
    for n in sorted(dist.keys()):
        print(f"  {n} convos: {dist[n]} stories")

    # Save mappings
    output_path = 'data/shortcut_all_mappings.json'
    with open(output_path, 'w') as f:
        json.dump(mappings, f, indent=2)
    print(f"\nSaved to {output_path}")

    # Show sample of stories with multiple conversations
    if stories_with_multiple > 0:
        print(f"\nStories with multiple conversations:")
        count = 0
        for story_id, convs in mappings.items():
            if len(convs) > 1:
                print(f"  Story {story_id}: {convs}")
                count += 1
                if count >= 10:
                    break


if __name__ == '__main__':
    main()
