#!/usr/bin/env python3
"""
Phase 5A: Load ground truth data for validation.

Loads conversations with story_id_v2 metadata and enriches with Shortcut story labels.
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
import requests
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()

SHORTCUT_API_TOKEN = os.getenv("SHORTCUT_API_TOKEN")
SHORTCUT_API_URL = "https://api.app.shortcut.com/api/v3"


def fetch_story_from_shortcut(story_id: str) -> Optional[dict]:
    """Fetch story details from Shortcut API."""
    if not SHORTCUT_API_TOKEN:
        return None

    try:
        response = requests.get(
            f"{SHORTCUT_API_URL}/stories/{story_id}",
            headers={
                "Content-Type": "application/json",
                "Shortcut-Token": SHORTCUT_API_TOKEN,
            },
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"  Story {story_id} not found in Shortcut")
            return None
        else:
            print(f"  Error {response.status_code} for story {story_id}")
            return None
    except requests.RequestException as e:
        print(f"  Request error for story {story_id}: {e}")
        return None


def extract_labels_from_story(story: dict) -> dict:
    """Extract relevant labels from a Shortcut story."""
    labels = []
    for label in story.get("labels", []):
        if isinstance(label, dict):
            labels.append(label.get("name", ""))
        else:
            labels.append(str(label))

    # Get product area from custom field if available
    product_area = None
    for cf in story.get("custom_fields", []):
        if cf.get("field_id") == "product_area" or "product" in cf.get("name", "").lower():
            product_area = cf.get("value")
            break

    return {
        "id": str(story.get("id")),
        "name": story.get("name", ""),
        "story_type": story.get("story_type", ""),
        "labels": labels,
        "product_area": product_area,
        "epic_id": story.get("epic_id"),
        "workflow_state_id": story.get("workflow_state_id"),
    }


def load_ground_truth():
    """Load and enrich ground truth data."""
    print("=" * 60)
    print("PHASE 5A: LOAD GROUND TRUTH DATA")
    print("=" * 60)

    # Load existing data
    with open("data/story_id_ground_truth.json") as f:
        gt_data = json.load(f)

    with open("data/shortcut_training_data.json") as f:
        sc_data = json.load(f)

    all_conversations = gt_data.get("all_conversations", [])
    print(f"\n📊 Ground truth conversations: {len(all_conversations)}")

    # Build story ID -> story map from existing data
    existing_stories = {str(s["id"]): s for s in sc_data.get("stories", [])}
    print(f"📚 Existing Shortcut stories: {len(existing_stories)}")

    # Parse all unique story IDs (handle comma-separated)
    all_story_ids = set()
    for conv in all_conversations:
        story_id_raw = conv.get("story_id", "")
        # Handle comma-separated IDs
        for sid in str(story_id_raw).split(","):
            sid = sid.strip()
            if sid and sid.isdigit():
                all_story_ids.add(sid)

    print(f"🔗 Unique story IDs in ground truth: {len(all_story_ids)}")

    # Find missing stories
    missing_ids = all_story_ids - set(existing_stories.keys())
    print(f"❓ Stories not in existing data: {len(missing_ids)}")

    # Fetch missing stories from Shortcut API
    fetched_stories = {}
    if SHORTCUT_API_TOKEN and missing_ids:
        print(f"\n🌐 Fetching {len(missing_ids)} stories from Shortcut API...")
        for i, sid in enumerate(missing_ids, 1):
            print(f"  [{i}/{len(missing_ids)}] Fetching story {sid}...", end=" ")
            story = fetch_story_from_shortcut(sid)
            if story:
                fetched_stories[sid] = extract_labels_from_story(story)
                print("✅")
            else:
                print("❌")
            time.sleep(0.2)  # Rate limiting
    elif not SHORTCUT_API_TOKEN:
        print("\n⚠️  SHORTCUT_API_TOKEN not set - using existing data only")

    # Combine all stories
    all_stories = {}
    for sid, story in existing_stories.items():
        all_stories[sid] = {
            "id": str(story.get("id")),
            "name": story.get("name", ""),
            "story_type": story.get("story_type", "bug"),
            "labels": [l.get("name") if isinstance(l, dict) else l for l in story.get("labels", [])],
            "product_area": story.get("product_area"),
            "tech_area": story.get("tech_area"),
        }
    all_stories.update(fetched_stories)

    print(f"\n📦 Total stories with metadata: {len(all_stories)}")

    # Build validation dataset
    validation_data = []
    for conv in all_conversations:
        story_id_raw = str(conv.get("story_id", ""))
        # Take first story ID if comma-separated
        story_id = story_id_raw.split(",")[0].strip()

        if story_id in all_stories:
            story = all_stories[story_id]
            validation_data.append({
                "conversation_id": conv["conversation_id"],
                "story_id": story_id,
                "source_body": conv.get("source_body", ""),
                "created_at": conv.get("created_at"),
                "story_name": story.get("name"),
                "story_labels": story.get("labels", []),
                "product_area": story.get("product_area"),
                "tech_area": story.get("tech_area"),
            })

    print(f"✅ Validation dataset: {len(validation_data)} conversations")

    # Filter to conversations with product_area (meaningful ground truth)
    with_product_area = [v for v in validation_data if v.get("product_area")]
    print(f"   With product_area: {len(with_product_area)}")

    # Split into validation (80%) and analysis (20%)
    import random
    random.seed(42)
    random.shuffle(with_product_area)

    split_idx = int(len(with_product_area) * 0.8)
    validation_set = with_product_area[:split_idx]
    analysis_set = with_product_area[split_idx:]

    print(f"   Validation set (80%): {len(validation_set)}")
    print(f"   Analysis set (20%): {len(analysis_set)}")

    # Compute statistics
    stats = compute_statistics(validation_data, all_stories)

    # Save results
    output = {
        "all_conversations": validation_data,
        "validation_set": validation_set,
        "analysis_set": analysis_set,
        "stories": list(all_stories.values()),
        "statistics": stats,
    }

    with open("data/phase5_ground_truth.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n💾 Saved to data/phase5_ground_truth.json")

    # Generate summary markdown
    generate_summary_markdown(output, stats)

    return output


def compute_statistics(validation_data: list, all_stories: dict) -> dict:
    """Compute dataset statistics."""
    import datetime

    # Product area distribution
    pa_counts = {}
    for v in validation_data:
        pa = v.get("product_area")
        if pa:
            pa_counts[pa] = pa_counts.get(pa, 0) + 1

    # Date range
    dates = [v["created_at"] for v in validation_data if v.get("created_at")]
    date_range = {
        "min": datetime.datetime.fromtimestamp(min(dates)).isoformat() if dates else None,
        "max": datetime.datetime.fromtimestamp(max(dates)).isoformat() if dates else None,
    }

    # Label distribution
    label_counts = {}
    for v in validation_data:
        for label in v.get("story_labels", []):
            label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "total_conversations": len(validation_data),
        "total_stories": len(all_stories),
        "with_product_area": sum(1 for v in validation_data if v.get("product_area")),
        "date_range": date_range,
        "product_area_distribution": dict(sorted(pa_counts.items(), key=lambda x: -x[1])),
        "label_distribution": dict(sorted(label_counts.items(), key=lambda x: -x[1])[:20]),
    }


def generate_summary_markdown(output: dict, stats: dict):
    """Generate phase5_data_summary.md."""
    md = f"""# Phase 5A: Ground Truth Data Summary

**Generated**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Dataset Overview

| Metric | Value |
|--------|-------|
| Total conversations with story_id | {stats['total_conversations']} |
| Total unique Shortcut stories | {stats['total_stories']} |
| Conversations with product_area | {stats['with_product_area']} |
| Date range | {stats['date_range']['min'][:10] if stats['date_range']['min'] else 'N/A'} to {stats['date_range']['max'][:10] if stats['date_range']['max'] else 'N/A'} |

## Dataset Splits

| Split | Count | Purpose |
|-------|-------|---------|
| Validation Set (80%) | {len(output['validation_set'])} | Accuracy measurement |
| Analysis Set (20%) | {len(output['analysis_set'])} | Vocabulary gap discovery |

## Product Area Distribution

| Product Area | Count | % of Dataset |
|--------------|-------|--------------|
"""

    total_with_pa = stats['with_product_area']
    for pa, count in stats['product_area_distribution'].items():
        pct = (count / total_with_pa * 100) if total_with_pa > 0 else 0
        md += f"| {pa} | {count} | {pct:.1f}% |\n"

    md += f"""
## Top 20 Shortcut Labels

| Label | Count |
|-------|-------|
"""

    for label, count in stats['label_distribution'].items():
        md += f"| {label} | {count} |\n"

    md += """
## Data Quality Notes

- **Target Met**: {target_met}
- **Product area as ground truth**: We use the `product_area` field from Shortcut stories as the primary ground truth label
- **Conversations without product_area**: Excluded from validation (no ground truth label)

## Files Generated

- `data/phase5_ground_truth.json` - Full dataset with all conversations and metadata
- `prompts/phase5_data_summary.md` - This summary

## Next Steps

Proceed to **Phase 5B**: Run theme extraction on all validation set conversations.
""".format(
        target_met="✅ Yes (200+ conversations)" if stats['with_product_area'] >= 200 else f"❌ No ({stats['with_product_area']} < 200)"
    )

    with open("prompts/phase5_data_summary.md", "w") as f:
        f.write(md)

    print(f"📝 Generated prompts/phase5_data_summary.md")


if __name__ == "__main__":
    load_ground_truth()
