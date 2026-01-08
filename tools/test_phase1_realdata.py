#!/usr/bin/env python3
"""
Phase 1 Real Data Test: Test classifiers on real Intercom conversations

Fetches recent conversations from Intercom and tests the complete Phase 1 system:
1. Stage 1: Fast LLM classification (customer-only)
2. Stage 2: Refined LLM classification (full context)
3. Resolution pattern detection
4. Knowledge extraction

Uses actual production data to validate system accuracy.
"""
import os
import sys
import json
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from classification_manager import ClassificationManager


# Sample conversation IDs from recent searches
# These will be replaced with MCP integration fetches
SAMPLE_CONVERSATION_IDS = [
    "215472581229755",
    "215401337769355",
    "215349453854099",
    "215320653234707",
    "215263377671699",
    "215248178293395",
    "215241546055187",
    "215223420551699",
    "215194687430163",
    "215166421368339"
]


def extract_messages_from_mcp_conversation(conv: dict) -> dict:
    """Extract customer and support messages from MCP conversation object."""
    result = {
        "customer_message": "",
        "support_messages": [],
        "source_url": None,
        "source_type": None
    }

    # Get customer message from source
    source = conv.get("source", {})
    source_body = source.get("body", "")
    if source_body:
        # Strip HTML tags if present
        import re
        source_body = re.sub(r'<[^>]+>', '', source_body)
        result["customer_message"] = source_body.strip()

    result["source_url"] = source.get("url")
    result["source_type"] = source.get("type")

    # Get support messages from conversation_parts
    conv_parts = conv.get("conversation_parts", {}).get("conversation_parts", [])
    for part in conv_parts:
        author = part.get("author", {})
        author_type = author.get("type", "")
        body = part.get("body", "")

        # Include admin, teammate, and bot responses
        if author_type in ["admin", "teammate", "bot"] and body:
            # Strip HTML tags
            import re
            body = re.sub(r'<[^>]+>', '', body)
            result["support_messages"].append(body.strip())

    return result


def main():
    """Test Phase 1 system on real Intercom conversations."""
    print("=" * 80)
    print("PHASE 1 REAL DATA TEST: Testing on Production Conversations")
    print("=" * 80)

    # Initialize
    classification_manager = ClassificationManager()

    print(f"\nNote: This is a simplified test using conversation IDs.")
    print(f"To fetch conversations, use the MCP Intercom integration tools.")
    print(f"\nPlease provide conversation data fetched from MCP to run this test.\n")

    # Statistics
    stats = {
        "total": 0,
        "stage1_confidence": Counter(),
        "stage2_confidence": Counter(),
        "classification_changes": 0,
        "stage1_types": Counter(),
        "stage2_types": Counter(),
        "resolution_detected": 0,
        "disambiguation_high": 0,
        "disambiguation_medium": 0,
        "errors": 0
    }

    results = []

    # Placeholder for actual conversation data
    # In production, this would be fetched via MCP tools
    conversations = []

    if not conversations:
        print("=" * 80)
        print("TEST SETUP")
        print("=" * 80)
        print("\nThis script is ready to test on real conversations.")
        print("\nTo run the test:")
        print("1. Use MCP Intercom tools to fetch conversations")
        print("2. Pass conversation objects to extract_messages_from_mcp_conversation()")
        print("3. Run through classification_manager.classify_complete_conversation()")
        print("\nExample conversation IDs to test:")
        for conv_id in SAMPLE_CONVERSATION_IDS[:5]:
            print(f"  - {conv_id}")
        return

    # Process conversations
    print("-" * 80)
    print("PROCESSING CONVERSATIONS")
    print("-" * 80)

    for i, conv in enumerate(conversations, 1):
        messages = extract_messages_from_mcp_conversation(conv)

        if not messages["customer_message"]:
            print(f"  [{i}] Skipping - no customer message")
            continue

        try:
            # Run complete classification
            result = classification_manager.classify_complete_conversation(
                messages["customer_message"],
                messages["support_messages"],
                source_url=messages["source_url"],
                source_type=messages["source_type"]
            )

            # Track statistics
            stats["total"] += 1
            stats["stage1_confidence"][result["stage1"]["confidence"]] += 1
            stats["stage1_types"][result["stage1"]["conversation_type"]] += 1

            if result["stage2"]:
                stats["stage2_confidence"][result["stage2"]["confidence"]] += 1
                stats["stage2_types"][result["stage2"]["conversation_type"]] += 1

                if result["classification_updated"]:
                    stats["classification_changes"] += 1

                if result["stage2"]["resolution_analysis"]["primary_action"]:
                    stats["resolution_detected"] += 1

                # Disambiguation tracking
                disamb_level = result["stage2"].get("disambiguation_level", "none")
                if disamb_level == "high":
                    stats["disambiguation_high"] += 1
                elif disamb_level == "medium":
                    stats["disambiguation_medium"] += 1

            results.append({
                "conversation_id": conv.get("id"),
                "stage1": result["stage1"],
                "stage2": result["stage2"],
                "final_type": result["final_type"],
                "classification_updated": result["classification_updated"]
            })

            # Show progress
            print(f"  [{i}] {messages['customer_message'][:40]}...")
            print(f"      Stage 1: {result['stage1']['conversation_type']} ({result['stage1']['confidence']})")
            if result["stage2"]:
                print(f"      Stage 2: {result['stage2']['conversation_type']} ({result['stage2']['confidence']})")
                if result["classification_updated"]:
                    print(f"      ✓ Classification updated")

        except Exception as e:
            print(f"  [{i}] Error: {str(e)}")
            stats["errors"] += 1

    # Generate reports
    print("\n" + "=" * 80)
    print("PHASE 1 REAL DATA RESULTS")
    print("=" * 80)

    if stats["total"] == 0:
        print("\nNo conversations processed.")
        return

    print(f"\n## Overall Statistics")
    print(f"Total conversations: {stats['total']}")
    print(f"Successfully processed: {len(results)}")
    print(f"Errors: {stats['errors']}")

    print(f"\n## Stage 1 Performance (Fast Routing)")
    print(f"Confidence distribution:")
    for conf, count in stats["stage1_confidence"].most_common():
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {conf}: {count} ({pct:.1f}%)")

    print(f"\nTop conversation types:")
    for type_name, count in stats["stage1_types"].most_common(5):
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {type_name}: {count} ({pct:.1f}%)")

    print(f"\n## Stage 2 Performance (Refined Analysis)")
    print(f"Confidence distribution:")
    for conf, count in stats["stage2_confidence"].most_common():
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {conf}: {count} ({pct:.1f}%)")

    print(f"\nTop conversation types:")
    for type_name, count in stats["stage2_types"].most_common(5):
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {type_name}: {count} ({pct:.1f}%)")

    print(f"\n## Classification Changes")
    pct = (stats['classification_changes'] / stats['total'] * 100) if stats['total'] > 0 else 0
    print(f"Stage 2 updated Stage 1: {stats['classification_changes']} ({pct:.1f}%)")

    print(f"\n## Resolution Detection")
    pct = (stats['resolution_detected'] / stats['total'] * 100) if stats['total'] > 0 else 0
    print(f"Actions detected: {stats['resolution_detected']} ({pct:.1f}%)")

    print(f"\n## Disambiguation")
    high_pct = (stats['disambiguation_high'] / stats['total'] * 100) if stats['total'] > 0 else 0
    med_pct = (stats['disambiguation_medium'] / stats['total'] * 100) if stats['total'] > 0 else 0
    print(f"High disambiguation: {stats['disambiguation_high']} ({high_pct:.1f}%)")
    print(f"Medium disambiguation: {stats['disambiguation_medium']} ({med_pct:.1f}%)")

    print("\n" + "=" * 80)
    print("PHASE 1 REAL DATA TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
