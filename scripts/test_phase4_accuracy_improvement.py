#!/usr/bin/env python3
"""
Accuracy improvement testing script for Phase 4a and 4b.

A/B tests Stage 2 classification with/without context enrichment to measure:
1. Help article context impact (+10-15% expected improvement)
2. Shortcut story context impact (+15-20% expected improvement)
3. Combined context impact (potentially +20-30%)

Usage:
    python scripts/test_phase4_accuracy_improvement.py --test-set path/to/conversations.json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.classifier_stage2 import classify_stage2
from src.help_article_extractor import HelpArticleExtractor
from src.shortcut_story_extractor import ShortcutStoryExtractor


def load_test_conversations(file_path: str) -> List[dict]:
    """
    Load test conversations from JSON file.

    Expected format:
    [
        {
            "id": "conversation_123",
            "customer_message": "...",
            "support_messages": ["..."],
            "ground_truth": {
                "primary_theme": "Instagram",
                "issue_type": "Bug"
            },
            "raw_conversation": {...}  # Full Intercom conversation for extractors
        }
    ]

    Args:
        file_path: Path to JSON file with test conversations

    Returns:
        List of conversation dictionaries
    """
    with open(file_path, 'r') as f:
        conversations = json.load(f)

    print(f"✅ Loaded {len(conversations)} test conversations")
    return conversations


def run_classification_test(
    conversation: dict,
    help_article_context: Optional[str] = None,
    shortcut_story_context: Optional[str] = None
) -> dict:
    """
    Run Stage 2 classification with optional context enrichment.

    Args:
        conversation: Test conversation dictionary
        help_article_context: Optional help article context
        shortcut_story_context: Optional Shortcut story context

    Returns:
        Classification result with confidence scores
    """
    customer_message = conversation["customer_message"]
    support_messages = conversation["support_messages"]

    try:
        result = classify_stage2(
            customer_message=customer_message,
            support_messages=support_messages,
            help_article_context=help_article_context,
            shortcut_story_context=shortcut_story_context
        )
        return result
    except Exception as e:
        print(f"❌ Classification failed for conversation {conversation['id']}: {e}")
        return None


def calculate_accuracy(
    result: dict,
    ground_truth: dict
) -> Tuple[bool, float]:
    """
    Calculate if classification matches ground truth and confidence score.

    Args:
        result: Classification result from Stage 2
        ground_truth: Expected classification

    Returns:
        (is_correct, confidence_score)
    """
    if not result:
        return False, 0.0

    # Extract primary theme and issue type from result
    predicted_theme = result.get("primary_theme", "")
    predicted_issue = result.get("issue_type", "")
    confidence = result.get("confidence", 0.0)

    # Check if matches ground truth
    theme_match = predicted_theme == ground_truth.get("primary_theme", "")
    issue_match = predicted_issue == ground_truth.get("issue_type", "")

    is_correct = theme_match and issue_match

    return is_correct, confidence


def run_baseline_test(
    conversations: List[dict]
) -> Dict[str, any]:
    """
    Run Stage 2 classification WITHOUT context enrichment (baseline).

    Returns:
        Dictionary with test results
    """
    results = {
        "total": len(conversations),
        "correct": 0,
        "incorrect": 0,
        "avg_confidence": 0.0,
        "confidence_sum": 0.0,
        "details": []
    }

    print("Running baseline test (no context enrichment)...")

    for i, conversation in enumerate(conversations, 1):
        result = run_classification_test(conversation)

        if result:
            is_correct, confidence = calculate_accuracy(
                result,
                conversation.get("ground_truth", {})
            )

            if is_correct:
                results["correct"] += 1
            else:
                results["incorrect"] += 1

            results["confidence_sum"] += confidence

            results["details"].append({
                "conversation_id": conversation["id"],
                "correct": is_correct,
                "confidence": confidence,
                "predicted": {
                    "primary_theme": result.get("primary_theme"),
                    "issue_type": result.get("issue_type")
                },
                "ground_truth": conversation.get("ground_truth", {})
            })

        if i % 10 == 0:
            print(f"  Progress: {i}/{len(conversations)}")

    # Calculate average confidence
    if results["total"] > 0:
        results["avg_confidence"] = results["confidence_sum"] / results["total"]
        results["accuracy"] = (results["correct"] / results["total"]) * 100

    print(f"✅ Baseline test complete: {results['correct']}/{results['total']} correct ({results['accuracy']:.1f}%)")

    return results


def run_help_article_test(
    conversations: List[dict],
    article_extractor: HelpArticleExtractor
) -> Dict[str, any]:
    """
    Run Stage 2 classification WITH help article context enrichment.

    Returns:
        Dictionary with test results
    """
    results = {
        "total": 0,  # Only conversations with help articles
        "correct": 0,
        "incorrect": 0,
        "avg_confidence": 0.0,
        "confidence_sum": 0.0,
        "extraction_count": 0,
        "details": []
    }

    print("Running help article context test...")

    for i, conversation in enumerate(conversations, 1):
        # Extract help article context
        raw_conversation = conversation.get("raw_conversation", {})
        article_context = article_extractor.extract_and_format(raw_conversation)

        if not article_context:
            continue  # Skip conversations without help articles

        results["extraction_count"] += 1
        results["total"] += 1

        # Run classification with article context
        result = run_classification_test(
            conversation,
            help_article_context=article_context
        )

        if result:
            is_correct, confidence = calculate_accuracy(
                result,
                conversation.get("ground_truth", {})
            )

            if is_correct:
                results["correct"] += 1
            else:
                results["incorrect"] += 1

            results["confidence_sum"] += confidence

            results["details"].append({
                "conversation_id": conversation["id"],
                "correct": is_correct,
                "confidence": confidence,
                "predicted": {
                    "primary_theme": result.get("primary_theme"),
                    "issue_type": result.get("issue_type")
                },
                "ground_truth": conversation.get("ground_truth", {}),
                "article_context_length": len(article_context)
            })

        if i % 10 == 0:
            print(f"  Progress: {i}/{len(conversations)} ({results['extraction_count']} with articles)")

    # Calculate average confidence and accuracy
    if results["total"] > 0:
        results["avg_confidence"] = results["confidence_sum"] / results["total"]
        results["accuracy"] = (results["correct"] / results["total"]) * 100

    extraction_rate = (results["extraction_count"] / len(conversations)) * 100
    print(f"✅ Help article test complete: {results['correct']}/{results['total']} correct ({results['accuracy']:.1f}%)")
    print(f"   Extraction rate: {extraction_rate:.1f}% ({results['extraction_count']}/{len(conversations)})")

    return results


def run_shortcut_story_test(
    conversations: List[dict],
    story_extractor: ShortcutStoryExtractor
) -> Dict[str, any]:
    """
    Run Stage 2 classification WITH Shortcut story context enrichment.

    Returns:
        Dictionary with test results
    """
    results = {
        "total": 0,  # Only conversations with Story ID v2
        "correct": 0,
        "incorrect": 0,
        "avg_confidence": 0.0,
        "confidence_sum": 0.0,
        "extraction_count": 0,
        "details": []
    }

    print("Running Shortcut story context test...")

    for i, conversation in enumerate(conversations, 1):
        # Extract Shortcut story context
        raw_conversation = conversation.get("raw_conversation", {})
        story_context = story_extractor.extract_and_format(raw_conversation)

        if not story_context:
            continue  # Skip conversations without Story ID v2

        results["extraction_count"] += 1
        results["total"] += 1

        # Run classification with story context
        result = run_classification_test(
            conversation,
            shortcut_story_context=story_context
        )

        if result:
            is_correct, confidence = calculate_accuracy(
                result,
                conversation.get("ground_truth", {})
            )

            if is_correct:
                results["correct"] += 1
            else:
                results["incorrect"] += 1

            results["confidence_sum"] += confidence

            results["details"].append({
                "conversation_id": conversation["id"],
                "correct": is_correct,
                "confidence": confidence,
                "predicted": {
                    "primary_theme": result.get("primary_theme"),
                    "issue_type": result.get("issue_type")
                },
                "ground_truth": conversation.get("ground_truth", {}),
                "story_context_length": len(story_context)
            })

        if i % 10 == 0:
            print(f"  Progress: {i}/{len(conversations)} ({results['extraction_count']} with stories)")

    # Calculate average confidence and accuracy
    if results["total"] > 0:
        results["avg_confidence"] = results["confidence_sum"] / results["total"]
        results["accuracy"] = (results["correct"] / results["total"]) * 100

    extraction_rate = (results["extraction_count"] / len(conversations)) * 100
    print(f"✅ Shortcut story test complete: {results['correct']}/{results['total']} correct ({results['accuracy']:.1f}%)")
    print(f"   Extraction rate: {extraction_rate:.1f}% ({results['extraction_count']}/{len(conversations)})")

    return results


def run_combined_test(
    conversations: List[dict],
    article_extractor: HelpArticleExtractor,
    story_extractor: ShortcutStoryExtractor
) -> Dict[str, any]:
    """
    Run Stage 2 classification WITH BOTH help article AND Shortcut story context.

    Returns:
        Dictionary with test results
    """
    results = {
        "total": 0,  # Only conversations with both contexts
        "correct": 0,
        "incorrect": 0,
        "avg_confidence": 0.0,
        "confidence_sum": 0.0,
        "extraction_count": 0,
        "details": []
    }

    print("Running combined context test (articles + stories)...")

    for i, conversation in enumerate(conversations, 1):
        raw_conversation = conversation.get("raw_conversation", {})

        # Extract both contexts
        article_context = article_extractor.extract_and_format(raw_conversation)
        story_context = story_extractor.extract_and_format(raw_conversation)

        if not (article_context and story_context):
            continue  # Skip if missing either context

        results["extraction_count"] += 1
        results["total"] += 1

        # Run classification with both contexts
        result = run_classification_test(
            conversation,
            help_article_context=article_context,
            shortcut_story_context=story_context
        )

        if result:
            is_correct, confidence = calculate_accuracy(
                result,
                conversation.get("ground_truth", {})
            )

            if is_correct:
                results["correct"] += 1
            else:
                results["incorrect"] += 1

            results["confidence_sum"] += confidence

            results["details"].append({
                "conversation_id": conversation["id"],
                "correct": is_correct,
                "confidence": confidence,
                "predicted": {
                    "primary_theme": result.get("primary_theme"),
                    "issue_type": result.get("issue_type")
                },
                "ground_truth": conversation.get("ground_truth", {}),
                "article_context_length": len(article_context),
                "story_context_length": len(story_context)
            })

        if i % 10 == 0:
            print(f"  Progress: {i}/{len(conversations)} ({results['extraction_count']} with both)")

    # Calculate average confidence and accuracy
    if results["total"] > 0:
        results["avg_confidence"] = results["confidence_sum"] / results["total"]
        results["accuracy"] = (results["correct"] / results["total"]) * 100

    extraction_rate = (results["extraction_count"] / len(conversations)) * 100
    print(f"✅ Combined test complete: {results['correct']}/{results['total']} correct ({results['accuracy']:.1f}%)")
    print(f"   Extraction rate: {extraction_rate:.1f}% ({results['extraction_count']}/{len(conversations)})")

    return results


def print_comparison_report(
    baseline_results: dict,
    article_results: dict,
    story_results: dict,
    combined_results: dict,
    output_file: Optional[str] = None
):
    """
    Print comparison report showing accuracy improvements.
    """
    report = []

    report.append("=" * 80)
    report.append("Phase 4 Accuracy Improvement Test Results")
    report.append("=" * 80)
    report.append(f"Timestamp: {datetime.now().isoformat()}")
    report.append("")

    # Baseline Results
    report.append("BASELINE (No Context Enrichment)")
    report.append("-" * 80)
    report.append(f"Total conversations: {baseline_results['total']}")
    report.append(f"Correct: {baseline_results['correct']} ({baseline_results['accuracy']:.1f}%)")
    report.append(f"Average confidence: {baseline_results['avg_confidence']:.2f}")
    report.append("")

    # Help Article Results
    report.append("HELP ARTICLE CONTEXT ENRICHMENT (Phase 4a)")
    report.append("-" * 80)
    report.append(f"Conversations with help articles: {article_results['total']}")
    if article_results['total'] > 0:
        report.append(f"Correct: {article_results['correct']} ({article_results['accuracy']:.1f}%)")
        report.append(f"Average confidence: {article_results['avg_confidence']:.2f}")

        # Calculate improvement
        baseline_subset_accuracy = baseline_results['accuracy']  # Approximate
        accuracy_improvement = article_results['accuracy'] - baseline_subset_accuracy
        confidence_improvement = article_results['avg_confidence'] - baseline_results['avg_confidence']

        report.append(f"Accuracy improvement: {accuracy_improvement:+.1f}%")
        report.append(f"Confidence improvement: {confidence_improvement:+.2f}")
        report.append(f"Target: +10-15% → {'✅ PASS' if 10 <= accuracy_improvement <= 20 else '⚠️  Outside expected range'}")
    else:
        report.append("⚠️  No conversations with help articles in test set")
    report.append("")

    # Shortcut Story Results
    report.append("SHORTCUT STORY CONTEXT ENRICHMENT (Phase 4b)")
    report.append("-" * 80)
    report.append(f"Conversations with Story ID v2: {story_results['total']}")
    if story_results['total'] > 0:
        report.append(f"Correct: {story_results['correct']} ({story_results['accuracy']:.1f}%)")
        report.append(f"Average confidence: {story_results['avg_confidence']:.2f}")

        # Calculate improvement
        baseline_subset_accuracy = baseline_results['accuracy']  # Approximate
        accuracy_improvement = story_results['accuracy'] - baseline_subset_accuracy
        confidence_improvement = story_results['avg_confidence'] - baseline_results['avg_confidence']

        report.append(f"Accuracy improvement: {accuracy_improvement:+.1f}%")
        report.append(f"Confidence improvement: {confidence_improvement:+.2f}")
        report.append(f"Target: +15-20% → {'✅ PASS' if 15 <= accuracy_improvement <= 25 else '⚠️  Outside expected range'}")
    else:
        report.append("⚠️  No conversations with Story ID v2 in test set")
    report.append("")

    # Combined Results
    report.append("COMBINED CONTEXT ENRICHMENT (Phase 4a + 4b)")
    report.append("-" * 80)
    report.append(f"Conversations with both contexts: {combined_results['total']}")
    if combined_results['total'] > 0:
        report.append(f"Correct: {combined_results['correct']} ({combined_results['accuracy']:.1f}%)")
        report.append(f"Average confidence: {combined_results['avg_confidence']:.2f}")

        # Calculate improvement
        baseline_subset_accuracy = baseline_results['accuracy']  # Approximate
        accuracy_improvement = combined_results['accuracy'] - baseline_subset_accuracy
        confidence_improvement = combined_results['avg_confidence'] - baseline_results['avg_confidence']

        report.append(f"Accuracy improvement: {accuracy_improvement:+.1f}%")
        report.append(f"Confidence improvement: {confidence_improvement:+.2f}")
        report.append(f"Target: +20-30% → {'✅ PASS' if 20 <= accuracy_improvement <= 35 else '⚠️  Outside expected range'}")
    else:
        report.append("⚠️  No conversations with both contexts in test set")
    report.append("")

    # Summary
    report.append("SUMMARY")
    report.append("-" * 80)
    report.append(f"Baseline accuracy: {baseline_results['accuracy']:.1f}%")
    if article_results['total'] > 0:
        report.append(f"With help articles: {article_results['accuracy']:.1f}% ({article_results['accuracy'] - baseline_results['accuracy']:+.1f}%)")
    if story_results['total'] > 0:
        report.append(f"With Shortcut stories: {story_results['accuracy']:.1f}% ({story_results['accuracy'] - baseline_results['accuracy']:+.1f}%)")
    if combined_results['total'] > 0:
        report.append(f"With both contexts: {combined_results['accuracy']:.1f}% ({combined_results['accuracy'] - baseline_results['accuracy']:+.1f}%)")
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
        description="Test classification accuracy improvements with Phase 4 context enrichment"
    )
    parser.add_argument(
        "--test-set",
        type=str,
        required=True,
        help="Path to JSON file with test conversations and ground truth"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to file (e.g., accuracy_results.txt)"
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Skip baseline test (useful for re-running with cached results)"
    )

    args = parser.parse_args()

    # Load test conversations
    conversations = load_test_conversations(args.test_set)
    print()

    # Initialize extractors
    print("Initializing extractors...")
    try:
        article_extractor = HelpArticleExtractor()
        print("✅ Help Article Extractor initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Help Article Extractor: {e}")
        sys.exit(1)

    try:
        story_extractor = ShortcutStoryExtractor()
        print("✅ Shortcut Story Extractor initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Shortcut Story Extractor: {e}")
        sys.exit(1)

    print()

    # Run tests
    if not args.skip_baseline:
        baseline_results = run_baseline_test(conversations)
        print()
    else:
        print("⚠️  Skipping baseline test")
        baseline_results = {"total": 0, "correct": 0, "accuracy": 0.0, "avg_confidence": 0.0}
        print()

    article_results = run_help_article_test(conversations, article_extractor)
    print()

    story_results = run_shortcut_story_test(conversations, story_extractor)
    print()

    combined_results = run_combined_test(conversations, article_extractor, story_extractor)
    print()

    # Print comparison report
    print_comparison_report(
        baseline_results,
        article_results,
        story_results,
        combined_results,
        args.output
    )


if __name__ == "__main__":
    main()
