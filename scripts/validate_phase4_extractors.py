#!/usr/bin/env python3
"""
Validation script for Phase 4a and 4b extractors.

Tests extractors against real Intercom conversations to:
1. Measure extraction rates (help articles and Story ID v2)
2. Validate data quality
3. Identify edge cases not covered by unit tests
4. Verify API integrations work with real credentials

Usage:
    python scripts/validate_phase4_extractors.py --sample-size 100
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.help_article_extractor import HelpArticleExtractor
from src.shortcut_story_extractor import ShortcutStoryExtractor


def fetch_sample_conversations(sample_size: int = 100) -> List[dict]:
    """
    Fetch sample conversations from Intercom API.

    Args:
        sample_size: Number of conversations to fetch

    Returns:
        List of conversation dictionaries
    """
    # TODO: Implement using Intercom MCP or API client
    # For now, return empty list - requires MCP integration
    print(f"⚠️  Intercom API integration required to fetch {sample_size} conversations")
    print("    Options:")
    print("    1. Use Intercom MCP server (recommended)")
    print("    2. Use Intercom Python SDK")
    print("    3. Load from test data file")
    return []


def validate_help_article_extraction(
    conversations: List[dict],
    article_extractor: HelpArticleExtractor
) -> Dict[str, any]:
    """
    Validate help article extraction on real conversations.

    Returns:
        Dictionary with validation results and metrics
    """
    results = {
        "total_conversations": len(conversations),
        "articles_found": 0,
        "extraction_rate": 0.0,
        "successful_api_calls": 0,
        "failed_api_calls": 0,
        "url_patterns_seen": {},
        "sample_extractions": []
    }

    for i, conversation in enumerate(conversations):
        try:
            # Extract and format
            context = article_extractor.extract_and_format(conversation)

            if context:
                results["articles_found"] += 1

                # Track URL patterns
                urls = article_extractor.extract_article_urls(conversation)
                for url in urls:
                    if "help.tailwindapp.com" in url:
                        pattern = "help.tailwindapp.com"
                    elif "intercom.help" in url:
                        pattern = "intercom.help"
                    elif "intercom://" in url:
                        pattern = "intercom://"
                    else:
                        pattern = "other"

                    results["url_patterns_seen"][pattern] = \
                        results["url_patterns_seen"].get(pattern, 0) + 1

                # Save first 5 examples
                if len(results["sample_extractions"]) < 5:
                    results["sample_extractions"].append({
                        "conversation_id": conversation.get("id"),
                        "urls": urls,
                        "context_length": len(context),
                        "context_preview": context[:200] + "..." if len(context) > 200 else context
                    })

        except Exception as e:
            print(f"Error processing conversation {conversation.get('id')}: {e}")
            results["failed_api_calls"] += 1

    # Calculate extraction rate
    if results["total_conversations"] > 0:
        results["extraction_rate"] = (
            results["articles_found"] / results["total_conversations"] * 100
        )

    return results


def validate_shortcut_story_extraction(
    conversations: List[dict],
    story_extractor: ShortcutStoryExtractor
) -> Dict[str, any]:
    """
    Validate Shortcut story extraction on real conversations.

    Returns:
        Dictionary with validation results and metrics
    """
    results = {
        "total_conversations": len(conversations),
        "stories_found": 0,
        "extraction_rate": 0.0,
        "successful_api_calls": 0,
        "failed_api_calls": 0,
        "story_id_formats": {"with_prefix": 0, "without_prefix": 0},
        "label_counts": {},
        "epic_counts": {},
        "sample_extractions": []
    }

    for conversation in conversations:
        try:
            # Extract story ID
            story_id = story_extractor.get_story_id_from_conversation(conversation)

            if not story_id:
                continue

            # Track ID format
            custom_attrs = conversation.get("custom_attributes", {})
            raw_id = custom_attrs.get("story_id_v2", "")
            if raw_id.startswith("sc-"):
                results["story_id_formats"]["with_prefix"] += 1
            else:
                results["story_id_formats"]["without_prefix"] += 1

            # Fetch and format
            context = story_extractor.extract_and_format(conversation)

            if context:
                results["stories_found"] += 1
                results["successful_api_calls"] += 1

                # Fetch story for label/epic analysis
                story = story_extractor.fetch_story_metadata(story_id)
                if story:
                    # Track labels
                    for label in story.labels:
                        results["label_counts"][label] = \
                            results["label_counts"].get(label, 0) + 1

                    # Track epics
                    if story.epic_name:
                        results["epic_counts"][story.epic_name] = \
                            results["epic_counts"].get(story.epic_name, 0) + 1

                    # Save first 5 examples
                    if len(results["sample_extractions"]) < 5:
                        results["sample_extractions"].append({
                            "conversation_id": conversation.get("id"),
                            "story_id": story_id,
                            "labels": story.labels,
                            "epic": story.epic_name,
                            "context_length": len(context),
                            "context_preview": context[:200] + "..." if len(context) > 200 else context
                        })
            else:
                results["failed_api_calls"] += 1

        except Exception as e:
            print(f"Error processing conversation {conversation.get('id')}: {e}")
            results["failed_api_calls"] += 1

    # Calculate extraction rate
    if results["total_conversations"] > 0:
        results["extraction_rate"] = (
            results["stories_found"] / results["total_conversations"] * 100
        )

    return results


def print_results(
    article_results: Dict,
    story_results: Dict,
    output_file: Optional[str] = None
):
    """
    Print validation results to console and optionally save to file.
    """
    report = []

    report.append("=" * 80)
    report.append("Phase 4 Extractor Validation Results")
    report.append("=" * 80)
    report.append(f"Timestamp: {datetime.now().isoformat()}")
    report.append("")

    # Phase 4a Results
    report.append("Phase 4a: Help Article Context Extraction")
    report.append("-" * 80)
    report.append(f"Total conversations analyzed: {article_results['total_conversations']}")
    report.append(f"Conversations with help articles: {article_results['articles_found']}")
    report.append(f"Extraction rate: {article_results['extraction_rate']:.1f}%")
    report.append(f"Target: 15-20% → {'✅ PASS' if 15 <= article_results['extraction_rate'] <= 25 else '⚠️  Outside expected range'}")
    report.append("")

    if article_results['url_patterns_seen']:
        report.append("URL Patterns Observed:")
        for pattern, count in sorted(
            article_results['url_patterns_seen'].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            report.append(f"  - {pattern}: {count}")
        report.append("")

    if article_results['sample_extractions']:
        report.append("Sample Extractions (first 5):")
        for i, sample in enumerate(article_results['sample_extractions'], 1):
            report.append(f"\n  Sample {i}:")
            report.append(f"    Conversation ID: {sample['conversation_id']}")
            report.append(f"    URLs found: {sample['urls']}")
            report.append(f"    Context preview: {sample['context_preview']}")
        report.append("")

    # Phase 4b Results
    report.append("Phase 4b: Shortcut Story Context Extraction")
    report.append("-" * 80)
    report.append(f"Total conversations analyzed: {story_results['total_conversations']}")
    report.append(f"Conversations with Story ID v2: {story_results['stories_found']}")
    report.append(f"Extraction rate: {story_results['extraction_rate']:.1f}%")
    report.append(f"Target: 30-40% → {'✅ PASS' if 30 <= story_results['extraction_rate'] <= 45 else '⚠️  Outside expected range'}")
    report.append(f"Successful API calls: {story_results['successful_api_calls']}")
    report.append(f"Failed API calls: {story_results['failed_api_calls']}")
    report.append("")

    report.append("Story ID Formats:")
    report.append(f"  - With 'sc-' prefix: {story_results['story_id_formats']['with_prefix']}")
    report.append(f"  - Without prefix: {story_results['story_id_formats']['without_prefix']}")
    report.append("")

    if story_results['label_counts']:
        report.append("Top 10 Story Labels:")
        for label, count in sorted(
            story_results['label_counts'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]:
            report.append(f"  - {label}: {count}")
        report.append("")

    if story_results['epic_counts']:
        report.append("Top 5 Epics:")
        for epic, count in sorted(
            story_results['epic_counts'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]:
            report.append(f"  - {epic}: {count}")
        report.append("")

    if story_results['sample_extractions']:
        report.append("Sample Extractions (first 5):")
        for i, sample in enumerate(story_results['sample_extractions'], 1):
            report.append(f"\n  Sample {i}:")
            report.append(f"    Conversation ID: {sample['conversation_id']}")
            report.append(f"    Story ID: {sample['story_id']}")
            report.append(f"    Labels: {', '.join(sample['labels'])}")
            report.append(f"    Epic: {sample['epic']}")
            report.append(f"    Context preview: {sample['context_preview']}")
        report.append("")

    report.append("=" * 80)

    # Print to console
    report_text = "\n".join(report)
    print(report_text)

    # Save to file if requested
    if output_file:
        with open(output_file, 'w') as f:
            f.write(report_text)
        print(f"\n✅ Results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate Phase 4 extractors on real Intercom data"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of conversations to analyze (default: 100)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to file (e.g., validation_results.txt)"
    )
    parser.add_argument(
        "--test-data",
        type=str,
        help="Path to JSON file with test conversations (alternative to live API)"
    )

    args = parser.parse_args()

    print("Initializing Phase 4 extractors...")

    # Initialize extractors
    try:
        article_extractor = HelpArticleExtractor()
        print("✅ Help Article Extractor initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Help Article Extractor: {e}")
        print("   Check INTERCOM_ACCESS_TOKEN environment variable")
        sys.exit(1)

    try:
        story_extractor = ShortcutStoryExtractor()
        print("✅ Shortcut Story Extractor initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Shortcut Story Extractor: {e}")
        print("   Check SHORTCUT_API_TOKEN environment variable")
        sys.exit(1)

    print()

    # Fetch conversations
    if args.test_data:
        print(f"Loading conversations from {args.test_data}...")
        with open(args.test_data, 'r') as f:
            conversations = json.load(f)
        print(f"✅ Loaded {len(conversations)} conversations from test data")
    else:
        print(f"Fetching {args.sample_size} conversations from Intercom API...")
        conversations = fetch_sample_conversations(args.sample_size)

        if not conversations:
            print("\n⚠️  No conversations fetched. To proceed:")
            print("   1. Implement Intercom API integration in fetch_sample_conversations()")
            print("   2. Or provide test data with --test-data path/to/conversations.json")
            sys.exit(1)

    print()

    # Validate Phase 4a
    print("Validating Phase 4a: Help Article Extraction...")
    article_results = validate_help_article_extraction(conversations, article_extractor)
    print(f"✅ Phase 4a validation complete")
    print()

    # Validate Phase 4b
    print("Validating Phase 4b: Shortcut Story Extraction...")
    story_results = validate_shortcut_story_extraction(conversations, story_extractor)
    print(f"✅ Phase 4b validation complete")
    print()

    # Print results
    print_results(article_results, story_results, args.output)


if __name__ == "__main__":
    main()
