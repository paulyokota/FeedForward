#!/usr/bin/env python3
"""
Test Integrated Two-Stage Classification System

Tests the complete system on 75 conversations with support responses:
1. Resolution pattern detection
2. Knowledge extraction per conversation
3. Knowledge aggregation across conversations
4. Theme relationship mapping
5. Self-service gap identification
6. Vocabulary update suggestions

Uses existing conversation data from context_classification_full_20260107_140759.json
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from resolution_analyzer import ResolutionAnalyzer
from knowledge_extractor import KnowledgeExtractor
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
    """Test the integrated system."""
    # Load conversation data
    data_path = Path(__file__).parent.parent / "data" / "conversation_types" / "context_classification_full_20260107_140759.json"

    if not data_path.exists():
        print(f"Error: Conversation data not found at {data_path}")
        print("Please run classify_with_support_context.py first")
        return

    with open(data_path) as f:
        data = json.load(f)

    conversations = data["results"]

    print("=" * 80)
    print("TWO-STAGE CLASSIFICATION SYSTEM TEST")
    print("=" * 80)
    print(f"\nLoaded {len(conversations)} conversations\n")

    # Initialize components
    resolution_analyzer = ResolutionAnalyzer()
    knowledge_extractor = KnowledgeExtractor()
    knowledge_aggregator = KnowledgeAggregator()

    # Process each conversation
    resolution_stats = {
        "total": 0,
        "with_support": 0,
        "actions_detected": 0,
        "conversations_with_actions": 0
    }

    action_types = Counter()
    action_categories = Counter()

    print("Processing conversations...")
    print("-" * 80)

    for i, conv in enumerate(conversations, 1):
        messages = extract_messages(conv)

        if not messages["support_messages"]:
            continue

        resolution_stats["total"] += 1
        resolution_stats["with_support"] += 1

        # 1. Analyze resolution actions
        resolution_analysis = resolution_analyzer.analyze_conversation(
            messages["support_messages"]
        )

        if resolution_analysis["action_count"] > 0:
            resolution_stats["conversations_with_actions"] += 1
            resolution_stats["actions_detected"] += resolution_analysis["action_count"]

            for action in resolution_analysis["all_actions"]:
                action_types[action["action"]] += 1
                action_categories[action["action_category"]] += 1

        # 2. Extract knowledge
        conversation_type = conv.get("classification", {}).get("conversation_type", "unknown")
        themes = conv.get("classification", {}).get("themes", [conversation_type])

        knowledge = knowledge_extractor.extract_from_conversation(
            messages["customer_message"],
            messages["support_messages"],
            conversation_type
        )

        # 3. Add to aggregator
        knowledge_aggregator.add_conversation_knowledge(knowledge, themes)

        # Progress indicator
        if i % 10 == 0:
            print(f"  Processed {i}/{len(conversations)} conversations...")

    print(f"  Processed {len(conversations)}/{len(conversations)} conversations.\n")

    # Generate reports
    print("=" * 80)
    print("RESOLUTION ANALYSIS RESULTS")
    print("=" * 80)

    print(f"\nConversations with support: {resolution_stats['with_support']}")
    print(f"Conversations with actions detected: {resolution_stats['conversations_with_actions']}")
    print(f"Detection rate: {(resolution_stats['conversations_with_actions'] / resolution_stats['with_support'] * 100):.1f}%")
    print(f"Total actions detected: {resolution_stats['actions_detected']}")

    print("\nTop Action Types:")
    for action, count in action_types.most_common(10):
        print(f"  {action}: {count}")

    print("\nAction Categories:")
    for category, count in action_categories.most_common():
        print(f"  {category}: {count}")

    # Knowledge extraction results
    print("\n" + "=" * 80)
    print("KNOWLEDGE EXTRACTION RESULTS")
    print("=" * 80)

    summaries = knowledge_aggregator.get_all_summaries(min_conversations=2)

    print(f"\nThemes with knowledge: {len(summaries)}")

    for theme_id, summary in list(summaries.items())[:10]:  # Top 10 themes
        print(f"\n{theme_id}:")
        print(f"  Conversations: {summary['conversation_count']}")

        if summary['top_root_causes']:
            print(f"  Top root causes:")
            for cause, count in summary['top_root_causes'][:3]:
                print(f"    - [{count}x] {cause[:60]}...")

        if summary['top_solutions']:
            print(f"  Top solutions:")
            for solution, count in summary['top_solutions'][:3]:
                print(f"    - [{count}x] {solution[:60]}...")

        if summary['related_themes']:
            related = ', '.join(f"{t} ({c})" for t, c in summary['related_themes'][:3])
            print(f"  Related themes: {related}")

    # Self-service opportunities
    print("\n" + "=" * 80)
    print("SELF-SERVICE OPPORTUNITIES")
    print("=" * 80)

    opportunities = knowledge_aggregator.get_self_service_opportunities()

    print(f"\nFound {len(opportunities)} self-service opportunities\n")

    for i, opp in enumerate(opportunities[:10], 1):  # Top 10
        print(f"{i}. {opp['theme']}")
        print(f"   Gap count: {opp['gap_count']} / {opp['conversation_count']} conversations ({opp['impact_percentage']:.1f}%)")
        if opp['common_evidence']:
            print(f"   Evidence: {opp['common_evidence'][0][0]}")

    # Vocabulary suggestions
    print("\n" + "=" * 80)
    print("VOCABULARY UPDATE SUGGESTIONS")
    print("=" * 80)

    vocab_suggestions = knowledge_aggregator.generate_vocabulary_updates(min_term_frequency=2)

    print(f"\nKeyword suggestions for {len(vocab_suggestions)} themes\n")

    for theme, keywords in list(vocab_suggestions.items())[:10]:  # Top 10
        print(f"{theme}:")
        print(f"  Suggested keywords: {', '.join(keywords[:5])}")

    # Emerging patterns
    print("\n" + "=" * 80)
    print("EMERGING PATTERNS")
    print("=" * 80)

    emerging = knowledge_aggregator.detect_emerging_patterns(frequency_threshold=3)

    print(f"\nFound {len(emerging)} emerging patterns\n")

    for i, pattern in enumerate(emerging[:10], 1):  # Top 10
        print(f"{i}. [{pattern['type']}] {pattern['pattern'][:60]}...")
        print(f"   Frequency: {pattern['frequency']}")
        print(f"   Recommendation: {pattern['recommendation']}")

    # Save results
    print("\n" + "=" * 80)
    print("SAVING RESULTS")
    print("=" * 80)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / "data" / "knowledge_base"
    output_dir.mkdir(exist_ok=True)

    # Save theme summaries
    summaries_path = output_dir / f"theme_knowledge_{timestamp}.json"
    with open(summaries_path, 'w') as f:
        json.dump(summaries, f, indent=2)
    print(f"\n✓ Saved theme knowledge: {summaries_path}")

    # Save self-service opportunities
    opportunities_path = output_dir / f"self_service_opportunities_{timestamp}.json"
    with open(opportunities_path, 'w') as f:
        json.dump(opportunities, f, indent=2)
    print(f"✓ Saved self-service opportunities: {opportunities_path}")

    # Save vocabulary suggestions
    vocab_path = output_dir / f"vocabulary_suggestions_{timestamp}.json"
    with open(vocab_path, 'w') as f:
        json.dump(vocab_suggestions, f, indent=2)
    print(f"✓ Saved vocabulary suggestions: {vocab_path}")

    # Save resolution stats
    resolution_path = output_dir / f"resolution_stats_{timestamp}.json"
    with open(resolution_path, 'w') as f:
        json.dump({
            "stats": resolution_stats,
            "action_types": dict(action_types),
            "action_categories": dict(action_categories)
        }, f, indent=2)
    print(f"✓ Saved resolution stats: {resolution_path}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
