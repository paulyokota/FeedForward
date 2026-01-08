#!/usr/bin/env python3
"""
Phase 5 Alternative: Evaluate with Equivalence Classes

Conservative approach: Keep original classifier, but define category equivalence
for grouping purposes. This preserves the business value of distinct categories
while acknowledging that certain categories should be treated as "same" for
grouping conversations about the same underlying issue.

Equivalence classes:
1. {bug_report, product_question} - Same technical issue, different framing
2. Short messages (<5 words) with "other" classification are skipped (not penalized)
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

from src.classifier import classify_conversation  # Original classifier

# Intercom API
INTERCOM_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
HEADERS = {
    'Authorization': f'Bearer {INTERCOM_TOKEN}',
    'Accept': 'application/json',
    'Intercom-Version': '2.11'
}

# Define equivalence classes for grouping evaluation
EQUIVALENCE_CLASSES = {
    'bug_report': 'technical',
    'product_question': 'technical',
    # All others map to themselves
}

def get_equivalence_class(category: str) -> str:
    """Map a category to its equivalence class."""
    return EQUIVALENCE_CLASSES.get(category, category)


def is_short_ambiguous(text: str, category: str) -> bool:
    """Check if this is a short ambiguous message that should be skipped."""
    word_count = len(text.split())
    if word_count >= 5:
        return False

    # Short message + "other" = ambiguous, skip it
    if category == 'other':
        return True

    return False


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


def evaluate_group_coherence(convos: list) -> dict:
    """
    Evaluate if a group is coherent using equivalence classes.

    Returns:
        {
            'coherent': bool,
            'equivalence_classes': set,
            'raw_categories': set,
            'skipped_ambiguous': int,
            'evaluated_count': int,
        }
    """
    evaluated = []
    skipped = 0

    for c in convos:
        if is_short_ambiguous(c['text'], c['issue_type']):
            skipped += 1
        else:
            evaluated.append(c)

    if len(evaluated) < 2:
        return {
            'coherent': True,  # Can't evaluate with <2 non-ambiguous
            'insufficient_data': True,
            'skipped_ambiguous': skipped,
            'evaluated_count': len(evaluated),
        }

    raw_categories = set(c['issue_type'] for c in evaluated)
    equiv_classes = set(get_equivalence_class(c['issue_type']) for c in evaluated)

    return {
        'coherent': len(equiv_classes) == 1,
        'equivalence_classes': equiv_classes,
        'raw_categories': raw_categories,
        'skipped_ambiguous': skipped,
        'evaluated_count': len(evaluated),
    }


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
    print("Using EQUIVALENCE CLASSES:")
    print("  - bug_report ≈ product_question (both = 'technical')")
    print("  - Short messages (<5 words) + 'other' = SKIPPED")
    print("=" * 60)

    # Classify each conversation using ORIGINAL classifier
    results = {}
    total_convos = 0
    classified = 0
    errors = 0

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
                classification = classify_conversation(text)  # ORIGINAL classifier
                issue_type = classification['issue_type']
                equiv = get_equivalence_class(issue_type)
                classified += 1

                results[story_id].append({
                    'conversation_id': conv_id,
                    'text': text[:500],
                    'issue_type': issue_type,
                    'equivalence_class': equiv,
                    'full_classification': classification
                })

                word_count = len(text.split())
                short_marker = f" ({word_count}w)" if word_count < 5 else ""
                print(f"  {conv_id}: {issue_type} → [{equiv}]{short_marker}")

            except Exception as e:
                print(f"  Error classifying {conv_id}: {e}")
                errors += 1

            time.sleep(0.15)

    print(f"\n{'='*60}")
    print(f"Total: {total_convos} | Classified: {classified} | Errors: {errors}")

    # Calculate accuracy with equivalence classes
    correct_raw = 0  # Original strict matching
    correct_equiv = 0  # With equivalence classes
    total_evaluated = 0
    total_skipped = 0
    mismatches_raw = []
    mismatches_equiv = []

    for story_id, convos in results.items():
        if len(convos) < 2:
            continue

        # Raw (original) evaluation
        raw_types = set(c['issue_type'] for c in convos)
        if len(raw_types) == 1:
            correct_raw += 1
        else:
            mismatches_raw.append({
                'story_id': story_id,
                'categories': list(raw_types),
            })

        # Equivalence class evaluation
        eval_result = evaluate_group_coherence(convos)
        total_skipped += eval_result['skipped_ambiguous']

        if eval_result.get('insufficient_data'):
            continue

        total_evaluated += 1

        if eval_result['coherent']:
            correct_equiv += 1
            print(f"\n[OK] Story {story_id}: {eval_result['equivalence_classes']}")
            print(f"     Raw categories: {eval_result['raw_categories']}")
        else:
            mismatches_equiv.append({
                'story_id': story_id,
                'equivalence_classes': list(eval_result['equivalence_classes']),
                'raw_categories': list(eval_result['raw_categories']),
            })
            print(f"\n[MISMATCH] Story {story_id}: {eval_result['equivalence_classes']}")
            for c in convos:
                skip = " [SKIP]" if is_short_ambiguous(c['text'], c['issue_type']) else ""
                print(f"  [{c['issue_type']} → {c['equivalence_class']}{skip}] {c['text'][:50]}...")

    total_groups_raw = len([s for s, c in results.items() if len(c) >= 2])
    accuracy_raw = (correct_raw / total_groups_raw * 100) if total_groups_raw > 0 else 0
    accuracy_equiv = (correct_equiv / total_evaluated * 100) if total_evaluated > 0 else 0

    print(f"\n{'='*60}")
    print(f"RESULTS COMPARISON")
    print(f"{'='*60}")
    print(f"\nOriginal (strict) accuracy: {accuracy_raw:.1f}% ({correct_raw}/{total_groups_raw})")
    print(f"With equivalence classes:   {accuracy_equiv:.1f}% ({correct_equiv}/{total_evaluated})")
    print(f"Skipped ambiguous messages: {total_skipped}")
    print(f"\nBaseline: 41.7%")
    print(f"Improvement (equivalence): {accuracy_equiv - 41.7:+.1f} pp")

    # Category distribution
    all_types = [c['issue_type'] for convos in results.values() for c in convos]
    print(f"\nCategory distribution (original classifier):")
    for cat, count in Counter(all_types).most_common():
        equiv = get_equivalence_class(cat)
        print(f"  {cat} → [{equiv}]: {count}")

    # Remaining mismatches analysis
    if mismatches_equiv:
        print(f"\n{'='*60}")
        print(f"REMAINING MISMATCHES ({len(mismatches_equiv)}):")
        for m in mismatches_equiv:
            print(f"  Story {m['story_id']}: {m['raw_categories']} → {m['equivalence_classes']}")

    # Save results
    output = {
        'approach': 'equivalence_classes',
        'equivalence_map': EQUIVALENCE_CLASSES,
        'accuracy_raw': accuracy_raw,
        'accuracy_equiv': accuracy_equiv,
        'baseline': 41.7,
        'improvement': accuracy_equiv - 41.7,
        'correct_raw': correct_raw,
        'correct_equiv': correct_equiv,
        'total_groups_raw': total_groups_raw,
        'total_groups_evaluated': total_evaluated,
        'skipped_ambiguous': total_skipped,
        'mismatches_raw': mismatches_raw,
        'mismatches_equiv': mismatches_equiv,
        'all_results': results
    }

    with open('data/equivalence_evaluation_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=list)
    print(f"\nSaved to data/equivalence_evaluation_results.json")

    return accuracy_equiv >= 85.0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
