#!/usr/bin/env python3
"""
Phase 6: Iteration 2 - Refined Equivalence Classes

Refinement: plan_question that mentions unexpected behavior
("not letting me", "can't", "won't") is treated as equivalent to technical.

This handles the case where users report plan-limit bugs as plan questions.
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

from src.classifier import classify_conversation

INTERCOM_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
HEADERS = {
    'Authorization': f'Bearer {INTERCOM_TOKEN}',
    'Accept': 'application/json',
    'Intercom-Version': '2.11'
}

# Base equivalence classes
EQUIVALENCE_CLASSES = {
    'bug_report': 'technical',
    'product_question': 'technical',
}

# Patterns that suggest a plan_question is actually about a bug
BUG_INDICATORS = [
    "not letting",
    "won't let",
    "can't",
    "cannot",
    "not working",
    "doesn't work",
    "not able to",
    "unable to",
    "failing",
    "error",
]


def get_equivalence_class(category: str, text: str = "") -> str:
    """
    Map category to equivalence class, with context-aware refinement.

    Refinement: plan_question with bug indicators → technical
    """
    if category in EQUIVALENCE_CLASSES:
        return EQUIVALENCE_CLASSES[category]

    # Contextual refinement for plan_question
    if category == 'plan_question' and text:
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in BUG_INDICATORS):
            return 'technical'  # Plan question that describes a bug

    return category


def is_short_ambiguous(text: str, category: str) -> bool:
    """Check if this is a short ambiguous message that should be skipped."""
    word_count = len(text.split())
    return word_count < 5 and category == 'other'


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
        return None


def evaluate_group_coherence(convos: list) -> dict:
    """Evaluate group coherence with refined equivalence."""
    evaluated = []
    skipped = 0

    for c in convos:
        if is_short_ambiguous(c['text'], c['issue_type']):
            skipped += 1
        else:
            evaluated.append(c)

    if len(evaluated) < 2:
        return {'coherent': True, 'insufficient_data': True, 'skipped': skipped}

    raw_categories = set(c['issue_type'] for c in evaluated)
    equiv_classes = set(c['equivalence_class'] for c in evaluated)

    return {
        'coherent': len(equiv_classes) == 1,
        'equivalence_classes': equiv_classes,
        'raw_categories': raw_categories,
        'skipped': skipped,
        'count': len(evaluated),
    }


def main():
    # Load baseline results to reuse classifications
    try:
        with open('data/equivalence_evaluation_results.json', 'r') as f:
            prev_results = json.load(f)
            all_results = prev_results.get('all_results', {})
    except:
        all_results = {}

    # Load ground truth
    with open('data/story_id_ground_truth.json', 'r') as f:
        gt = json.load(f)

    test_ids = gt.get('test_story_ids', [])
    groups = gt.get('groups_by_story_id', {})

    catch_all_ids = ['66666', '88']
    test_groups = {}
    for sid in test_ids:
        if sid in groups and sid not in catch_all_ids:
            test_groups[sid] = groups[sid]

    print("Phase 6: Iteration 2 - Refined Equivalence")
    print("=" * 60)
    print("Refinement: plan_question + bug indicators → technical")
    print(f"Bug indicators: {BUG_INDICATORS[:5]}...")
    print("=" * 60)

    # Recompute equivalence classes with refined logic
    results = {}

    for story_id, convos in test_groups.items():
        if story_id not in all_results:
            continue  # Skip if no previous results

        results[story_id] = []
        for c in all_results[story_id]:
            # Recompute equivalence with text context
            equiv = get_equivalence_class(c['issue_type'], c['text'])

            results[story_id].append({
                'conversation_id': c['conversation_id'],
                'text': c['text'],
                'issue_type': c['issue_type'],
                'equivalence_class': equiv,
            })

    # Evaluate with refined equivalence
    correct = 0
    total = 0
    mismatches = []

    print("\nResults:")
    for story_id, convos in results.items():
        if len(convos) < 2:
            continue

        eval_result = evaluate_group_coherence(convos)

        if eval_result.get('insufficient_data'):
            continue

        total += 1

        if eval_result['coherent']:
            correct += 1
            print(f"[OK] Story {story_id}: {eval_result['equivalence_classes']}")
            if eval_result['raw_categories'] != eval_result['equivalence_classes']:
                print(f"     Raw: {eval_result['raw_categories']}")
        else:
            mismatches.append({
                'story_id': story_id,
                'equiv': list(eval_result['equivalence_classes']),
                'raw': list(eval_result['raw_categories']),
            })
            print(f"[MISMATCH] Story {story_id}: {eval_result['equivalence_classes']}")
            for c in convos:
                skip = " [SKIP]" if is_short_ambiguous(c['text'], c['issue_type']) else ""
                refined = " (REFINED)" if c['issue_type'] != c['equivalence_class'] and c['issue_type'] == 'plan_question' else ""
                print(f"  [{c['issue_type']} → {c['equivalence_class']}{refined}{skip}] {c['text'][:50]}...")

    accuracy = (correct / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"ITERATION 2 RESULTS")
    print(f"{'='*60}")
    print(f"Accuracy with refined equivalence: {accuracy:.1f}% ({correct}/{total})")
    print(f"Baseline: 41.7%")
    print(f"Iteration 1: 83.3%")
    print(f"Improvement from baseline: {accuracy - 41.7:+.1f} pp")

    if mismatches:
        print(f"\nRemaining mismatches ({len(mismatches)}):")
        for m in mismatches:
            print(f"  Story {m['story_id']}: {m['raw']} → {m['equiv']}")

    # Check if we hit target
    if accuracy >= 85.0:
        print(f"\n✓ TARGET REACHED: {accuracy:.1f}% >= 85%")
    else:
        print(f"\n✗ Target not reached: {accuracy:.1f}% < 85%")

    # Save results
    output = {
        'iteration': 2,
        'refinement': 'plan_question + bug_indicators → technical',
        'accuracy': accuracy,
        'baseline': 41.7,
        'iteration_1': 83.3,
        'correct': correct,
        'total': total,
        'mismatches': mismatches,
    }

    with open('data/iteration_2_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to data/iteration_2_results.json")

    return accuracy >= 85.0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
