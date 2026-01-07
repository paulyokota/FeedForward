#!/usr/bin/env python3
"""
Phase 1 System Test: Two-Stage Classification with LLM

Fetches 75 conversations from Intercom and tests complete system:
1. Stage 1: Fast LLM classification (customer-only)
2. Stage 2: Refined LLM classification (full context)
3. Resolution pattern detection
4. Knowledge extraction and aggregation
5. Performance metrics and accuracy analysis
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from intercom_client import IntercomClient
from classification_manager import ClassificationManager
from knowledge_aggregator import KnowledgeAggregator


def extract_messages(conversation: dict) -> dict:
    """Extract customer and support messages from conversation."""
    result = {
        "customer_message": "",
        "support_messages": [],
        "customer_count": 0,
        "support_count": 0
    }

    # Get source body as first customer message
    source_body = conversation.get("source", {}).get("body", "")
    if source_body:
        result["customer_message"] = source_body
        result["customer_count"] = 1

    # Get all admin/teammate responses
    parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])
    for part in parts:
        author_type = part.get("author", {}).get("type", "")
        body = part.get("body")
        if author_type in ["admin", "teammate"] and body:
            result["support_messages"].append(body)
            result["support_count"] += 1

    return result


def main():
    """Test Phase 1 system on 75 conversations."""
    print("=" * 80)
    print("PHASE 1 SYSTEM TEST: Two-Stage LLM Classification")
    print("=" * 80)

    # Initialize components
    intercom = IntercomClient()
    classification_manager = ClassificationManager()
    knowledge_aggregator = KnowledgeAggregator()

    # Fetch conversations
    print("\nFetching conversations from Intercom...")
    print("  Filter: Last 90 days, with support responses")

    ninety_days_ago = datetime.now() - timedelta(days=90)

    conversations = list(intercom.fetch_conversations(
        since=ninety_days_ago,
        per_page=50,
        max_pages=2  # Limit to ~100 conversations to get 75 with support
    ))

    print(f"  Fetched: {len(conversations)} conversations\n")

    # Filter for conversations with support responses
    conversations_with_support = [
        c for c in conversations
        if extract_messages(c)["support_count"] > 0
    ]

    print(f"  With support responses: {len(conversations_with_support)}\n")

    # Statistics
    stats = {
        "total": len(conversations_with_support),
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

    print("-" * 80)
    print("PROCESSING CONVERSATIONS")
    print("-" * 80)

    for i, conv in enumerate(conversations_with_support, 1):
        messages = extract_messages(conv)

        if not messages["customer_message"]:
            continue

        try:
            # Get source info
            source_url = conv.get("source", {}).get("url")
            source_type = conv.get("source", {}).get("type")

            # Run complete classification
            result = classification_manager.classify_complete_conversation(
                messages["customer_message"],
                messages["support_messages"],
                source_url=source_url,
                source_type=source_type
            )

            # Track statistics
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

                # Add to knowledge aggregator
                knowledge = result["stage2"]["knowledge"]
                themes = [result["final_type"]]  # Use final type as theme
                knowledge_aggregator.add_conversation_knowledge(knowledge, themes)

            results.append({
                "conversation_id": conv.get("id"),
                "stage1": result["stage1"],
                "stage2": result["stage2"],
                "final_type": result["final_type"],
                "classification_updated": result["classification_updated"]
            })

            # Progress indicator
            if i % 10 == 0:
                print(f"  Processed {i}/{len(conversations_with_support)} conversations...")

        except Exception as e:
            print(f"  Error processing conversation {i}: {str(e)}")
            stats["errors"] += 1

    print(f"  Processed {len(results)}/{len(conversations_with_support)} conversations.\n")

    # Generate reports
    print("=" * 80)
    print("PHASE 1 RESULTS")
    print("=" * 80)

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

    # Knowledge aggregation
    print("\n" + "=" * 80)
    print("KNOWLEDGE AGGREGATION")
    print("=" * 80)

    summaries = knowledge_aggregator.get_all_summaries(min_conversations=2)
    print(f"\nThemes with knowledge (≥2 conversations): {len(summaries)}")

    opportunities = knowledge_aggregator.get_self_service_opportunities()
    print(f"Self-service opportunities: {len(opportunities)}")

    # Save results
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / "data" / "phase1_results"
    output_dir.mkdir(exist_ok=True)

    # Save detailed results
    results_path = output_dir / f"phase1_results_{timestamp}.json"
    with open(results_path, 'w') as f:
        json.dump({
            "generated_at": timestamp,
            "total": stats["total"],
            "statistics": {k: dict(v) if isinstance(v, Counter) else v for k, v in stats.items()},
            "results": results
        }, f, indent=2)
    print(f"\n✓ Saved results: {results_path}")

    # Save knowledge
    knowledge_path = output_dir / f"knowledge_base_{timestamp}.json"
    with open(knowledge_path, 'w') as f:
        json.dump(summaries, f, indent=2)
    print(f"✓ Saved knowledge base: {knowledge_path}")

    # Save self-service opportunities
    opportunities_path = output_dir / f"self_service_opportunities_{timestamp}.json"
    with open(opportunities_path, 'w') as f:
        json.dump(opportunities, f, indent=2)
    print(f"✓ Saved self-service opportunities: {opportunities_path}")

    print("\n" + "=" * 80)
    print("PHASE 1 TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
