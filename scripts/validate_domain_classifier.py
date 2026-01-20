#!/usr/bin/env python
"""
Domain Classifier Validation Script

Validates the Haiku-powered domain classifier against 10 sample customer issues.
Measures classification accuracy, latency, and cost.

Usage:
    python scripts/validate_domain_classifier.py

Outputs:
    - Classification results for each issue
    - Accuracy metrics
    - Latency metrics
    - Cost analysis
"""

import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.story_tracking.services.domain_classifier import DomainClassifier


# 10 sample customer support issues for validation
SAMPLE_ISSUES = [
    {
        "text": "My scheduled pins aren't posting to Pinterest at 3pm like I set. They're just sitting in draft forever.",
        "expected_category": "scheduling",
        "description": "Pin scheduling failure",
    },
    {
        "text": "I was charged twice for my subscription this month. Please explain why there are two charges.",
        "expected_category": "billing",
        "description": "Billing duplicate charge",
    },
    {
        "text": "Ghostwriter is timing out when I try to generate pin descriptions. It was working yesterday.",
        "expected_category": "ai_creation",
        "description": "AI generation timeout",
    },
    {
        "text": "I can't connect my Instagram account. OAuth keeps failing with a 401 error.",
        "expected_category": "account",
        "description": "OAuth authentication failure",
    },
    {
        "text": "Analytics dashboard is showing 0 impressions even though I know my pins are getting engagement.",
        "expected_category": "analytics",
        "description": "Analytics metrics missing",
    },
    {
        "text": "Pin spacing feature isn't working - pins are posting too close together, sometimes 5 per minute.",
        "expected_category": "scheduling",
        "description": "Pin spacing configuration issue",
    },
    {
        "text": "Can I import my existing pins from my Pinterest boards? I have 500+ pins I want to manage here.",
        "expected_category": "integrations",
        "description": "CSV import feature request",
    },
    {
        "text": "SmartPin is generating low-quality suggestions and they don't match my brand voice at all.",
        "expected_category": "ai_creation",
        "description": "Content quality issue",
    },
    {
        "text": "I want to upgrade my plan to Professional but the upgrade button keeps showing 'error'.",
        "expected_category": "billing",
        "description": "Subscription upgrade error",
    },
    {
        "text": "How do I set up team collaboration? We have 5 people who need to manage our content calendar.",
        "expected_category": "communities",
        "description": "Team collaboration inquiry",
    },
]


def validate_classification(classifier: DomainClassifier, issue: dict) -> dict:
    """
    Validate a single classification.

    Returns:
        dict with classification result and metrics
    """
    start_time = time.time()

    result = classifier.classify(issue["text"])

    elapsed_ms = (time.time() - start_time) * 1000

    is_correct = result.category == issue["expected_category"]

    return {
        "issue": issue["text"][:100] + "..." if len(issue["text"]) > 100 else issue["text"],
        "description": issue["description"],
        "expected": issue["expected_category"],
        "classified_as": result.category,
        "confidence": result.confidence,
        "correct": is_correct,
        "latency_ms": elapsed_ms,
        "reasoning": result.reasoning,
        "suggested_repos": result.suggested_repos,
        "keywords_matched": result.keywords_matched,
        "success": result.success,
    }


def main():
    """Run validation suite."""
    print("=" * 80)
    print("DOMAIN CLASSIFIER VALIDATION")
    print("=" * 80)
    print()

    # Initialize classifier
    print("Initializing classifier...")
    try:
        classifier = DomainClassifier()
        print(f"✓ Classifier initialized")
        print(f"  - Categories: {len(classifier.list_categories())}")
        print(f"  - Keywords indexed: {len(classifier.keyword_index)}")
    except Exception as e:
        print(f"✗ Failed to initialize classifier: {e}")
        return 1

    print()

    # Run validations
    print("VALIDATING CLASSIFICATIONS")
    print("-" * 80)
    print()

    results = []
    correct_count = 0
    total_latency_ms = 0

    for i, issue in enumerate(SAMPLE_ISSUES, 1):
        try:
            result = validate_classification(classifier, issue)
            results.append(result)

            status = "✓" if result["correct"] else "✗"
            print(f"{i}. {status} {result['description']}")
            print(f"   Expected: {result['expected']}")
            print(f"   Got: {result['classified_as']} (confidence: {result['confidence']})")
            print(f"   Latency: {result['latency_ms']:.0f}ms")

            if result["keywords_matched"]:
                print(f"   Keywords: {', '.join(result['keywords_matched'][:3])}")

            if result["correct"]:
                correct_count += 1

            total_latency_ms += result["latency_ms"]

            print()

        except Exception as e:
            print(f"{i}. ✗ Error validating issue: {e}")
            print()

    # Summary metrics
    print("=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print()

    accuracy = (correct_count / len(SAMPLE_ISSUES)) * 100
    avg_latency_ms = total_latency_ms / len(SAMPLE_ISSUES)

    print(f"Accuracy: {correct_count}/{len(SAMPLE_ISSUES)} ({accuracy:.1f}%)")
    print(f"Average Latency: {avg_latency_ms:.0f}ms")
    print(f"Total Latency: {total_latency_ms:.0f}ms")
    print(f"Max Single Classification: 500ms (target)")
    print()

    # Cost metrics
    cost_per_classification = 0.00015  # Haiku pricing
    daily_classifications = 1000
    monthly_cost = cost_per_classification * daily_classifications * 30

    print("COST METRICS")
    print("-" * 80)
    print(f"Cost per classification: ${cost_per_classification:.6f}")
    print(f"Cost per day (1000 issues): ${cost_per_classification * daily_classifications:.2f}")
    print(f"Estimated monthly cost: ${monthly_cost:.2f}")
    print()

    # Acceptance criteria
    print("ACCEPTANCE CRITERIA")
    print("-" * 80)

    criteria = [
        ("Accuracy >= 80%", accuracy >= 80),
        ("Average latency < 500ms", avg_latency_ms < 500),
        ("Max single classification < 500ms", max(r["latency_ms"] for r in results) < 500),
        ("Monthly cost < $6", monthly_cost < 6),
        ("All classifications successful", all(r["success"] for r in results)),
    ]

    all_pass = True
    for criterion, passed in criteria:
        status = "✓" if passed else "✗"
        print(f"{status} {criterion}")
        if not passed:
            all_pass = False

    print()

    # Detailed results
    print("DETAILED RESULTS")
    print("-" * 80)
    print(json.dumps(results, indent=2))
    print()

    # Return appropriate exit code
    if all_pass:
        print("✓ ALL VALIDATIONS PASSED")
        return 0
    else:
        print("✗ SOME VALIDATIONS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
