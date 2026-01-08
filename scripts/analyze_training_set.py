#!/usr/bin/env python3
"""
Phase 3: Analyze Human Grouping Patterns
Classify training set conversations and identify patterns.
"""

import json
import os
import sys
import time
import re
from pathlib import Path
from collections import Counter, defaultdict

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
            source = conv.get('source', {})
            body = source.get('body', '')
            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', body)
            text = re.sub(r'\s+', ' ', text).strip()
            return text if text else None
        return None
    except Exception as e:
        print(f"Error fetching {conv_id}: {e}")
        return None


def analyze_group_coherence(classifications: list) -> dict:
    """Analyze how coherent a group is based on classifications."""
    if len(classifications) < 2:
        return {"coherent": True, "categories": [], "dominant": None}

    categories = [c['issue_type'] for c in classifications]
    unique_cats = set(categories)

    # Most common category
    cat_counts = Counter(categories)
    dominant = cat_counts.most_common(1)[0][0]
    dominant_pct = cat_counts[dominant] / len(categories) * 100

    return {
        "coherent": len(unique_cats) == 1,
        "categories": list(unique_cats),
        "dominant": dominant,
        "dominant_pct": dominant_pct,
        "category_counts": dict(cat_counts),
        "total": len(categories)
    }


def main():
    # Load ground truth
    with open('data/story_id_ground_truth.json', 'r') as f:
        gt = json.load(f)

    groups = gt.get('groups_by_story_id', {})
    test_ids = gt.get('test_story_ids', [])

    # Get training groups (2+ convos, not in test, exclude catch-alls)
    catch_all_ids = ['66666', '88']  # Known catch-all stories
    training_groups = {}
    for sid, convos in groups.items():
        if len(convos) >= 2 and sid not in test_ids and sid not in catch_all_ids:
            # Also exclude very large groups (likely catch-alls)
            if len(convos) <= 20:
                training_groups[sid] = convos

    print(f"Training groups: {len(training_groups)}")
    total_convos = sum(len(c) for c in training_groups.values())
    print(f"Total training conversations: {total_convos}")

    # Classify each conversation
    results = {}  # story_id -> [{conv_id, text, classification}, ...]
    classified = 0
    errors = 0

    for story_id, convos in training_groups.items():
        print(f"\n{'='*50}")
        print(f"Story {story_id} ({len(convos)} conversations)")
        results[story_id] = []

        for conv in convos:
            conv_id = conv.get('id') or conv.get('conversation_id')

            # Fetch text
            text = get_conversation_text(conv_id)
            if not text:
                print(f"  Skip {conv_id}: No text")
                errors += 1
                continue

            # Classify
            try:
                classification = classify_conversation(text)
                classified += 1

                results[story_id].append({
                    'conversation_id': conv_id,
                    'text': text[:500],
                    'issue_type': classification['issue_type'],
                    'full_classification': classification
                })

                print(f"  {conv_id}: {classification['issue_type']} | {text[:60]}...")

            except Exception as e:
                print(f"  Error classifying {conv_id}: {e}")
                errors += 1

            time.sleep(0.15)  # Rate limiting

    print(f"\n{'='*60}")
    print(f"CLASSIFICATION COMPLETE")
    print(f"Classified: {classified}")
    print(f"Errors: {errors}")

    # Analyze patterns
    print(f"\n{'='*60}")
    print("GROUP COHERENCE ANALYSIS")

    coherent_count = 0
    incoherent_groups = []
    category_confusion = defaultdict(list)  # (cat1, cat2) -> [story_ids]

    for story_id, convos in results.items():
        if len(convos) < 2:
            continue

        analysis = analyze_group_coherence(convos)

        if analysis['coherent']:
            coherent_count += 1
        else:
            incoherent_groups.append({
                'story_id': story_id,
                'analysis': analysis,
                'conversations': convos
            })

            # Track which categories get confused
            cats = sorted(analysis['categories'])
            if len(cats) == 2:
                category_confusion[tuple(cats)].append(story_id)

    total_analyzed = len([s for s, c in results.items() if len(c) >= 2])
    accuracy = coherent_count / total_analyzed * 100 if total_analyzed > 0 else 0

    print(f"\nCoherent groups: {coherent_count}/{total_analyzed} ({accuracy:.1f}%)")
    print(f"Incoherent groups: {len(incoherent_groups)}")

    print(f"\n{'='*60}")
    print("CATEGORY CONFUSION MATRIX")
    for cats, story_ids in sorted(category_confusion.items(), key=lambda x: -len(x[1])):
        print(f"\n{cats[0]} <-> {cats[1]}: {len(story_ids)} groups")
        for sid in story_ids[:3]:
            print(f"  Story {sid}")

    print(f"\n{'='*60}")
    print("DETAILED INCOHERENT GROUP ANALYSIS")
    for ig in incoherent_groups[:10]:  # Show first 10
        print(f"\n--- Story {ig['story_id']} ---")
        print(f"Categories: {ig['analysis']['categories']}")
        print(f"Dominant: {ig['analysis']['dominant']} ({ig['analysis']['dominant_pct']:.0f}%)")
        for c in ig['conversations'][:4]:
            print(f"  [{c['issue_type']}] {c['text'][:80]}...")

    # Save results
    output = {
        'training_accuracy': accuracy,
        'coherent_count': coherent_count,
        'total_groups': total_analyzed,
        'incoherent_groups': incoherent_groups,
        'category_confusion': {f"{k[0]}_vs_{k[1]}": v for k, v in category_confusion.items()},
        'all_results': results
    }

    with open('data/training_analysis_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n\nSaved to data/training_analysis_results.json")


if __name__ == '__main__':
    main()
