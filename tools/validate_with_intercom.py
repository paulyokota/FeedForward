#!/usr/bin/env python3
"""
Validate theme extraction on real Intercom conversations with URL context.

Workflow:
1. Fetch Shortcut stories with Intercom links (from Epic 57994)
2. Extract Intercom conversation IDs from external_links
3. Fetch those conversations from Intercom API (includes source.url)
4. Run theme extraction with URL context enabled
5. Compare product area routing against Shortcut labels

This tests whether URL context improves classification accuracy on real data.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.models import Conversation
from theme_extractor import ThemeExtractor
from intercom_client import IntercomClient


class ShortcutClient:
    """Minimal Shortcut API client for fetching stories."""

    BASE_URL = "https://api.app.shortcut.com/api/v3"

    def __init__(self, api_token: str = None):
        self.api_token = api_token or os.getenv("SHORTCUT_API_TOKEN")
        if not self.api_token:
            raise ValueError("SHORTCUT_API_TOKEN not set")

        self.session = requests.Session()
        self.session.headers.update({
            "Shortcut-Token": self.api_token,
            "Content-Type": "application/json",
        })

    def get_epic(self, epic_id: int) -> dict:
        """Get an epic by ID."""
        response = self.session.get(f"{self.BASE_URL}/epics/{epic_id}")
        response.raise_for_status()
        return response.json()

    def get_epic_stories(self, epic_id: int) -> list[dict]:
        """Get all stories in an epic."""
        epic = self.get_epic(epic_id)
        story_ids = epic.get("story_ids", [])

        stories = []
        for story_id in story_ids:
            try:
                story = self.get_story(story_id)
                stories.append(story)
            except Exception as e:
                print(f"Warning: Failed to fetch story {story_id}: {e}")
                continue

        return stories

    def get_story(self, story_id: int) -> dict:
        """Get a story by ID."""
        response = self.session.get(f"{self.BASE_URL}/stories/{story_id}")
        response.raise_for_status()
        return response.json()


def extract_intercom_conversation_id(url: str) -> str:
    """Extract conversation ID from Intercom URL."""
    # URL format: https://app.intercom.com/a/apps/{app_id}/inbox/inbox/{team_id}/inbox/conversation/{conversation_id}
    # or: https://app.intercom.com/a/inbox/{workspace_id}/inbox/conversation/{conversation_id}
    parts = url.split("/")
    if "conversation" in parts:
        idx = parts.index("conversation")
        if idx + 1 < len(parts):
            return parts[idx + 1].split("?")[0]  # Remove query params
    return None


def find_stories_with_intercom_links(stories: list[dict]) -> list[dict]:
    """Filter stories that have Intercom conversation links."""
    stories_with_intercom = []

    for story in stories:
        external_links = story.get("external_links", [])
        intercom_links = [
            link for link in external_links
            if "intercom.com" in link.lower() and "conversation" in link.lower()
        ]

        if intercom_links:
            # Extract conversation ID from first link
            conv_id = extract_intercom_conversation_id(intercom_links[0])
            if conv_id:
                stories_with_intercom.append({
                    "shortcut_id": story.get("id"),
                    "shortcut_name": story.get("name"),
                    "shortcut_product_area": story.get("labels", []),  # Labels contain product area
                    "intercom_conv_id": conv_id,
                    "intercom_link": intercom_links[0],
                })

    return stories_with_intercom


def normalize_product_area(labels: list) -> str:
    """Extract Product Area from Shortcut labels."""
    # Labels are objects with 'name' field
    label_names = [label.get("name", "") if isinstance(label, dict) else label for label in labels]

    # Map common label names to product areas
    area_mappings = {
        "Pin Scheduler": "Next Publisher",
        "Original Publisher": "Legacy Publisher",
        "Legacy Publisher": "Legacy Publisher",
        "Multi-Network": "Multi-Network",
        "Multi-Network Scheduler": "Multi-Network",
        "Extension": "Extension",
        "Create": "Create",
        "Analytics": "Analytics",
        "Smart.bio": "Smart.bio",
        "SmartLoop": "SmartLoop",
        "Communities": "Communities",
        "Billing": "Billing & Settings",
        "GW Labs": "GW Labs",
        "Made For You": "Made For You",
    }

    for label in label_names:
        if label in area_mappings:
            return area_mappings[label]

    # Return first label if no match
    return label_names[0] if label_names else "Unknown"


def fetch_and_classify(
    stories: list[dict],
    intercom_client: IntercomClient,
    extractor: ThemeExtractor,
    max_conversations: int = None
) -> list[dict]:
    """Fetch conversations from Intercom and classify them."""
    results = []

    for i, story in enumerate(stories):
        if max_conversations and i >= max_conversations:
            break

        conv_id = story["intercom_conv_id"]
        print(f"[{i+1}/{len(stories)}] Fetching conversation {conv_id}...")

        try:
            # Fetch conversation from Intercom
            raw_conv = intercom_client.get_conversation(conv_id)

            # Parse conversation
            parsed = intercom_client.parse_conversation(raw_conv)

            # Check if it's a quality conversation
            filter_result = intercom_client.quality_filter(raw_conv)
            if not filter_result.passed:
                print(f"  ⚠️  Filtered out: {filter_result.reason}")
                continue

            # Create Conversation object for classification
            # Note: We don't have full classification yet, so use placeholders
            conv = Conversation(
                id=parsed.id,
                created_at=parsed.created_at,
                source_body=parsed.source_body,
                source_url=parsed.source_url,
                source_type=parsed.source_type,
                source_subject=parsed.source_subject,
                contact_email=parsed.contact_email,
                contact_id=parsed.contact_id,
                issue_type="bug_report",  # Placeholder
                sentiment="neutral",
                churn_risk=False,
                priority="normal",
            )

            # Extract theme with URL context
            theme = extractor.extract(conv, strict_mode=True)

            # Get expected product area from Shortcut
            expected_area = normalize_product_area(story["shortcut_product_area"])

            # Record result
            result = {
                "shortcut_id": story["shortcut_id"],
                "shortcut_name": story["shortcut_name"],
                "expected_product_area": expected_area,
                "extracted_product_area": theme.product_area,
                "extracted_theme": theme.issue_signature,
                "source_url": parsed.source_url,
                "url_matched": parsed.source_url is not None,
                "correct": theme.product_area.lower() == expected_area.lower(),
                "conversation_preview": parsed.source_body[:100] + "..." if parsed.source_body else "",
            }

            results.append(result)

            status = "✓" if result["correct"] else "✗"
            print(f"  {status} Expected: {expected_area}, Got: {theme.product_area}")
            if parsed.source_url:
                print(f"     URL: {parsed.source_url}")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue

    return results


def generate_report(results: list[dict]) -> None:
    """Generate validation report."""
    if not results:
        print("\n❌ No results to report")
        return

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    with_url = sum(1 for r in results if r["url_matched"])

    print("\n" + "="*60)
    print("VALIDATION REPORT")
    print("="*60)
    print(f"\nOverall Accuracy: {correct}/{total} ({100*correct/total:.1f}%)")
    print(f"Conversations with URL: {with_url}/{total} ({100*with_url/total:.1f}%)")

    # Accuracy by URL presence
    results_with_url = [r for r in results if r["url_matched"]]
    results_no_url = [r for r in results if not r["url_matched"]]

    if results_with_url:
        correct_with_url = sum(1 for r in results_with_url if r["correct"])
        print(f"\nWith URL Context: {correct_with_url}/{len(results_with_url)} ({100*correct_with_url/len(results_with_url):.1f}%)")

    if results_no_url:
        correct_no_url = sum(1 for r in results_no_url if r["correct"])
        print(f"Without URL Context: {correct_no_url}/{len(results_no_url)} ({100*correct_no_url/len(results_no_url):.1f}%)")

    # Accuracy by product area
    print("\nAccuracy by Product Area:")
    print("-" * 60)

    by_area = defaultdict(list)
    for r in results:
        by_area[r["expected_product_area"]].append(r)

    for area in sorted(by_area.keys()):
        area_results = by_area[area]
        area_correct = sum(1 for r in area_results if r["correct"])
        area_total = len(area_results)
        area_with_url = sum(1 for r in area_results if r["url_matched"])

        print(f"  {area:20} {area_correct}/{area_total} ({100*area_correct/area_total:.1f}%) - {area_with_url} with URL")

    # Show misclassifications
    misclassified = [r for r in results if not r["correct"]]
    if misclassified:
        print("\nMisclassifications:")
        print("-" * 60)
        for r in misclassified:
            print(f"\n✗ [{r['shortcut_id']}] {r['shortcut_name'][:60]}")
            print(f"   Expected: {r['expected_product_area']}")
            print(f"   Got: {r['extracted_product_area']} ({r['extracted_theme']})")
            if r['url_matched']:
                print(f"   URL: {r['source_url']}")
            else:
                print(f"   URL: (none)")
            print(f"   Message: {r['conversation_preview']}")


def save_results(results: list[dict], output_path: Path) -> None:
    """Save validation results to JSON file."""
    output = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_conversations": len(results),
        "correct": sum(1 for r in results if r["correct"]),
        "accuracy": 100 * sum(1 for r in results if r["correct"]) / len(results) if results else 0,
        "results": results,
    }

    output_path.write_text(json.dumps(output, indent=2))
    print(f"\n✓ Results saved to {output_path}")


def load_training_data() -> list[dict]:
    """Load existing Shortcut training data."""
    data_path = Path(__file__).parent.parent / "data" / "shortcut_training_data.json"
    with open(data_path) as f:
        data = json.load(f)
    return data["stories"]


def main():
    parser = argparse.ArgumentParser(description="Validate theme extraction on real Intercom data")
    parser.add_argument("--max", type=int, help="Maximum conversations to process")
    parser.add_argument("--output", type=str, default="data/intercom_validation_results.json",
                        help="Output file for results")
    parser.add_argument("--use-training-data", action="store_true",
                        help="Use existing training data instead of fetching from Shortcut")
    args = parser.parse_args()

    print("="*60)
    print("Intercom Validation with URL Context")
    print("="*60)

    # Step 1: Load stories from training data or fetch from Shortcut
    if args.use_training_data:
        print(f"\n1. Loading stories from training data...")
        all_stories_data = load_training_data()
        print(f"   Found {len(all_stories_data)} stories in training data")

        # Fetch full story details from Shortcut to get external_links
        print(f"\n2. Fetching full story details from Shortcut API...")
        shortcut = ShortcutClient()
        all_stories = []

        for i, story_data in enumerate(all_stories_data):
            if i % 50 == 0:
                print(f"   Fetching {i}/{len(all_stories_data)}...")
            try:
                story = shortcut.get_story(story_data["id"])
                # Add training data fields
                story["training_product_area"] = story_data.get("product_area")
                all_stories.append(story)
            except Exception as e:
                print(f"   Warning: Failed to fetch story {story_data['id']}: {e}")
                continue

        print(f"   Successfully fetched {len(all_stories)} stories")
    else:
        print(f"\n1. Fetching stories from Shortcut Epic...")
        print("   ❌ Epic-based fetching not yet implemented")
        print("   Use --use-training-data flag instead")
        return 1

    # Step 2: Filter for stories with Intercom links
    print("\n3. Filtering for stories with Intercom links...")
    stories_with_intercom = find_stories_with_intercom_links(all_stories)
    print(f"   Found {len(stories_with_intercom)} stories with Intercom conversations")

    if not stories_with_intercom:
        print("   ❌ No stories with Intercom links found")
        return 1

    # Show sample
    print(f"\n   Sample stories:")
    for story in stories_with_intercom[:3]:
        print(f"   - [{story['shortcut_id']}] {story['shortcut_name'][:60]}")
        print(f"     Product Area: {normalize_product_area(story['shortcut_product_area'])}")
        print(f"     Intercom: {story['intercom_conv_id']}")

    # Step 4: Fetch conversations and classify
    print("\n4. Fetching conversations from Intercom and classifying...")
    intercom_client = IntercomClient()
    extractor = ThemeExtractor(use_vocabulary=True)

    results = fetch_and_classify(
        stories_with_intercom,
        intercom_client,
        extractor,
        max_conversations=args.max
    )

    # Step 4: Generate report
    generate_report(results)

    # Step 5: Save results
    output_path = Path(args.output)
    save_results(results, output_path)

    return 0


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
