#!/usr/bin/env python3
"""
Phase 5: Evaluate Improved Classifier v2
Run v2 classifier on test set and measure accuracy improvement.
"""

import json
import os
import sys
import time
import re
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from dotenv import load_dotenv
load_dotenv()

from src.classifier_v2 import classify_conversation_v2

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
            source = conv.get('source', {})
            body = source.get('body', '')
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
    catch_all_ids = ['66666', '88']
    test_groups = {}
    for sid in test_ids:
        if sid in groups and sid not in catch_all_ids:
            test_groups[sid] = groups[sid]

    print(f"Test set: {len(test_groups)} groups")
    print("=" * 60)

    # Classify each conversation
    results = {}
    total_convos = 0
    classified = 0
    errors = 0
    ambiguous_count = 0

    for story_id, convos in test_groups.items():
        print(f"\nStory {story_id} ({len(convos)} conversations)")
        results[story_id] = []

        for conv in convos:
            conv_id = conv.get('id') or conv.get('conversation_id')
            total_convos += 1

            text = get_conversation_text(conv_id)
            if not text:
                print(f"  Skip {conv_id}: No text")
                errors += 1
                continue

            try:
                classification = classify_conversation_v2(text)
                issue_type = classification['issue_type']
                is_ambiguous = classification['is_ambiguous']
                classified += 1

                if is_ambiguous:
                    ambiguous_count += 1

                results[story_id].append({
                    'conversation_id': conv_id,
                    'text': text[:500],
                    'issue_type': issue_type,
                    'is_ambiguous': is_ambiguous,
                    'full_classification': classification
                })

                amb_marker = " [AMBIGUOUS]" if is_ambiguous else ""
                print(f"  {conv_id}: {issue_type}{amb_marker}")

            except Exception as e:
                print(f"  Error classifying {conv_id}: {e}")
                errors += 1

            time.sleep(0.15)

    print(f"\n{'='*60}")
    print(f"Total: {total_convos} | Classified: {classified} | Errors: {errors}")
    print(f"Ambiguous messages: {ambiguous_count}")

    # Calculate accuracy (group coherence)
    correct_groups = 0
    mismatches = []

    for story_id, convos in results.items():
        if len(convos) < 2:
            continue

        issue_types = set(c['issue_type'] for c in convos)

        if len(issue_types) == 1:
            correct_groups += 1
            print(f"\n[OK] Story {story_id}: All {len(convos)} convos = {list(issue_types)[0]}")
        else:
            mismatches.append({
                'story_id': story_id,
                'conversations': convos,
                'issue_types': list(issue_types)
            })
            print(f"\n[MISMATCH] Story {story_id}: {issue_types}")
            for c in convos:
                amb = " [AMB]" if c['is_ambiguous'] else ""
                print(f"  [{c['issue_type']}{amb}] {c['text'][:60]}...")

    total_groups = len([s for s, c in results.items() if len(c) >= 2])
    accuracy = (correct_groups / total_groups * 100) if total_groups > 0 else 0

    print(f"\n{'='*60}")
    print(f"V2 CLASSIFIER ACCURACY: {accuracy:.1f}%")
    print(f"Correct groups: {correct_groups}/{total_groups}")
    print(f"Mismatched groups: {len(mismatches)}")

    # Compare to baseline
    baseline_accuracy = 41.7
    improvement = accuracy - baseline_accuracy
    print(f"\nBaseline accuracy: {baseline_accuracy}%")
    print(f"Improvement: {improvement:+.1f} percentage points")

    # Category distribution
    all_types = [c['issue_type'] for convos in results.values() for c in convos]
    print(f"\nCategory distribution:")
    for cat, count in Counter(all_types).most_common():
        print(f"  {cat}: {count}")

    # Save results
    output = {
        'version': 'v2',
        'accuracy': accuracy,
        'baseline_accuracy': baseline_accuracy,
        'improvement': improvement,
        'correct_groups': correct_groups,
        'total_groups': total_groups,
        'ambiguous_count': ambiguous_count,
        'mismatches': mismatches,
        'all_results': results
    }

    with open('data/v2_evaluation_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to data/v2_evaluation_results.json")

    return accuracy >= 85.0  # Return True if target reached


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
