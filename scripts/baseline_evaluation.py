#!/usr/bin/env python3
"""
Phase 2: Baseline Evaluation
Run existing classifier on test set and measure accuracy.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from dotenv import load_dotenv
load_dotenv()

from src.classifier import classify_conversation

# Intercom API
INTERCOM_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
HEADERS = {
    'Authorization': f'Bearer {INTERCOM_TOKEN}',
    'Accept': 'application/json',
    'Intercom-Version': '2.11'
}


def get_conversation_text(conv_id: str) -> str | None:
    """Fetch conversation text from Intercom."""
    url = f'https://api.intercom.io/conversations/{conv_id}'
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            conv = resp.json()
            # Get first message body
            source = conv.get('source', {})
            body = source.get('body', '')
            # Strip HTML tags
            import re
            text = re.sub(r'<[^>]+>', ' ', body)
            text = re.sub(r'\s+', ' ', text).strip()
            return text if text else None
        return None
    except Exception as e:
        print(f"Error fetching {conv_id}: {e}")
        return None


def main():
    # Load ground truth
    with open('data/story_id_ground_truth.json', 'r') as f:
        gt = json.load(f)

    test_ids = gt.get('test_story_ids', [])
    groups = gt.get('groups_by_story_id', {})

    # Get test groups (excluding catch-alls)
    test_groups = {}
    for sid in test_ids:
        if sid in groups and sid not in ['66666', '88']:
            test_groups[sid] = groups[sid]

    print(f"Test set: {len(test_groups)} groups")

    # Classify each conversation
    results = {}  # story_id -> [{conv_id, text, issue_type}, ...]
    total_convos = 0
    classified = 0
    errors = 0

    for story_id, convos in test_groups.items():
        print(f"\nProcessing Story {story_id} ({len(convos)} conversations)...")
        results[story_id] = []

        for conv in convos:
            conv_id = conv.get('id') or conv.get('conversation_id')
            total_convos += 1

            # Fetch text
            text = get_conversation_text(conv_id)
            if not text:
                print(f"  Conv {conv_id}: No text (skipped)")
                errors += 1
                continue

            # Classify
            try:
                classification = classify_conversation(text)
                issue_type = classification['issue_type']
                classified += 1
                print(f"  Conv {conv_id}: {issue_type}")

                results[story_id].append({
                    'conversation_id': conv_id,
                    'text': text[:500],  # Truncate for storage
                    'issue_type': issue_type,
                    'full_classification': classification
                })
            except Exception as e:
                print(f"  Conv {conv_id}: Classification error - {e}")
                errors += 1

            time.sleep(0.2)  # Rate limiting

    print(f"\n{'='*50}")
    print(f"Total conversations: {total_convos}")
    print(f"Successfully classified: {classified}")
    print(f"Errors: {errors}")

    # Calculate accuracy
    # A group is "correct" if ALL conversations got the same issue_type
    correct_groups = 0
    mismatches = []

    for story_id, convos in results.items():
        if len(convos) < 2:
            continue  # Skip groups with insufficient data

        issue_types = set(c['issue_type'] for c in convos)

        if len(issue_types) == 1:
            correct_groups += 1
        else:
            mismatches.append({
                'story_id': story_id,
                'conversations': convos,
                'issue_types': list(issue_types)
            })

    total_groups = len([s for s, c in results.items() if len(c) >= 2])
    accuracy = (correct_groups / total_groups * 100) if total_groups > 0 else 0

    print(f"\n{'='*50}")
    print(f"BASELINE ACCURACY: {accuracy:.1f}%")
    print(f"Correct groups: {correct_groups}/{total_groups}")
    print(f"Mismatched groups: {len(mismatches)}")

    # Save results
    output = {
        'accuracy': accuracy,
        'correct_groups': correct_groups,
        'total_groups': total_groups,
        'mismatches': mismatches,
        'all_results': results
    }

    with open('data/baseline_evaluation_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to data/baseline_evaluation_results.json")

    # Show mismatches
    if mismatches:
        print(f"\n{'='*50}")
        print("MISMATCH DETAILS:")
        for m in mismatches[:5]:
            print(f"\nStory {m['story_id']} - Categories: {m['issue_types']}")
            for c in m['conversations']:
                print(f"  - {c['issue_type']}: {c['text'][:100]}...")


if __name__ == '__main__':
    main()
