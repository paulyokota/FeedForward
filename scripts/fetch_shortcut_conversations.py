#!/usr/bin/env python3
"""
Fetch conversations from Intercom that are linked from Shortcut stories.
Get their Story ID v2 values and merge with existing ground truth.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import requests

INTERCOM_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
HEADERS = {
    'Authorization': f'Bearer {INTERCOM_TOKEN}',
    'Accept': 'application/json',
    'Intercom-Version': '2.11'
}

def get_conversation(conv_id: str) -> dict | None:
    """Fetch a conversation from Intercom."""
    url = f'https://api.intercom.io/conversations/{conv_id}'
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  Error fetching {conv_id}: {resp.status_code}")
            return None
    except Exception as e:
        print(f"  Exception fetching {conv_id}: {e}")
        return None


def extract_story_id_v2(conv: dict) -> str | None:
    """Extract Story ID v2 from conversation custom attributes."""
    custom_attrs = conv.get('custom_attributes', {})
    return custom_attrs.get('Story ID v2') or custom_attrs.get('story_id_v2')


def main():
    # Load Shortcut mappings (story_id -> [conversation_ids])
    with open('data/shortcut_all_mappings.json', 'r') as f:
        shortcut_mappings = json.load(f)

    # Load existing ground truth
    with open('data/story_id_ground_truth.json', 'r') as f:
        ground_truth = json.load(f)

    existing_story_ids = set(ground_truth.get('all_story_ids', {}).keys())
    existing_conv_ids = set()
    for convs in ground_truth.get('all_story_ids', {}).values():
        existing_conv_ids.update(c['id'] for c in convs)

    print(f"Existing ground truth: {len(existing_story_ids)} story IDs, {len(existing_conv_ids)} conversations")

    # Collect all conversation IDs from Shortcut mappings
    all_conv_ids = []
    shortcut_story_map = {}  # conv_id -> shortcut_story_id
    for story_id, conv_ids in shortcut_mappings.items():
        for conv_id in conv_ids:
            all_conv_ids.append(conv_id)
            shortcut_story_map[conv_id] = story_id

    print(f"Shortcut mappings: {len(shortcut_mappings)} stories, {len(all_conv_ids)} conversations")

    # Fetch conversations and get Story ID v2
    new_mappings = []  # [(story_id_v2, conv_id, shortcut_story_id)]
    matched = 0
    mismatched = 0
    no_story_id = 0
    fetch_errors = 0

    for i, conv_id in enumerate(all_conv_ids):
        if i > 0 and i % 10 == 0:
            print(f"Progress: {i}/{len(all_conv_ids)}")

        conv = get_conversation(conv_id)
        if not conv:
            fetch_errors += 1
            continue

        story_id_v2 = extract_story_id_v2(conv)
        shortcut_story_id = shortcut_story_map[conv_id]

        if story_id_v2:
            new_mappings.append({
                'story_id_v2': str(story_id_v2),
                'shortcut_story_id': shortcut_story_id,
                'conversation_id': conv_id,
                'match': str(story_id_v2) == shortcut_story_id
            })
            if str(story_id_v2) == shortcut_story_id:
                matched += 1
            else:
                mismatched += 1
                print(f"  Mismatch: conv {conv_id} has story_id_v2={story_id_v2} but linked from Shortcut {shortcut_story_id}")
        else:
            no_story_id += 1
            print(f"  No Story ID v2: conv {conv_id} (from Shortcut {shortcut_story_id})")

        time.sleep(0.1)  # Rate limiting

    print(f"\n=== RESULTS ===")
    print(f"Fetched: {len(all_conv_ids) - fetch_errors}/{len(all_conv_ids)}")
    print(f"With Story ID v2: {matched + mismatched}")
    print(f"  Matched Shortcut story: {matched}")
    print(f"  Mismatched: {mismatched}")
    print(f"No Story ID v2: {no_story_id}")
    print(f"Fetch errors: {fetch_errors}")

    # Save results
    output = {
        'mappings': new_mappings,
        'stats': {
            'total_conversations': len(all_conv_ids),
            'fetched': len(all_conv_ids) - fetch_errors,
            'with_story_id_v2': matched + mismatched,
            'matched': matched,
            'mismatched': mismatched,
            'no_story_id': no_story_id,
            'fetch_errors': fetch_errors
        }
    }

    with open('data/shortcut_conversation_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to data/shortcut_conversation_results.json")

    # Now merge into ground truth
    # Add conversations with Story ID v2 to the appropriate story groups
    all_story_ids = ground_truth.get('all_story_ids', {})
    added_count = 0

    for mapping in new_mappings:
        story_id = mapping['story_id_v2']
        conv_id = mapping['conversation_id']

        # Check if already in ground truth
        if conv_id in existing_conv_ids:
            continue

        if story_id not in all_story_ids:
            all_story_ids[story_id] = []

        # Add minimal conv data
        all_story_ids[story_id].append({
            'id': conv_id,
            'source': 'shortcut_link'
        })
        added_count += 1

    print(f"\nAdded {added_count} new conversations to ground truth")

    # Recalculate usable groups
    usable = {k: v for k, v in all_story_ids.items() if len(v) >= 2}
    print(f"Usable groups (2+ convos): {len(usable)}")

    # Save updated ground truth
    ground_truth['all_story_ids'] = all_story_ids
    ground_truth['usable_story_ids'] = list(usable.keys())

    with open('data/story_id_ground_truth.json', 'w') as f:
        json.dump(ground_truth, f, indent=2)
    print(f"Updated data/story_id_ground_truth.json")


if __name__ == '__main__':
    main()
