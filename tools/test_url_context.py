#!/usr/bin/env python3
"""
Test URL context boosting for theme extraction.

Tests that conversations with different source URLs get routed to the correct product areas.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.models import Conversation
from theme_extractor import ThemeExtractor

# Test cases: URL -> Expected product area
TEST_CASES = [
    {
        "name": "Pin Scheduler (Next Publisher)",
        "url": "https://www.tailwindapp.com/dashboard/v2/advanced-scheduler/pinterest",
        "message": "My pins aren't scheduling correctly. They show as scheduled but never post.",
        "expected_area": "Next Publisher",
    },
    {
        "name": "Legacy Publisher",
        "url": "https://www.tailwindapp.com/publisher/queue",
        "message": "Fill empty time slots feature is not working in my queue.",
        "expected_area": "Legacy Publisher",
    },
    {
        "name": "Multi-Network Scheduler",
        "url": "https://www.tailwindapp.com/dashboard/v2/scheduler",
        "message": "My Instagram posts aren't publishing at the scheduled time.",
        "expected_area": "Multi-Network",
    },
    {
        "name": "Multi-Network Drafts",
        "url": "https://www.tailwindapp.com/dashboard/v2/drafts",
        "message": "I can't find my scheduled Instagram posts in drafts.",
        "expected_area": "Multi-Network",
    },
    {
        "name": "No URL (should not match)",
        "url": None,
        "message": "My pins aren't posting.",
        "expected_area": None,  # No URL context, LLM decides
    },
]


def test_url_context_matching():
    """Test that URL patterns correctly map to product areas."""
    print("="*60)
    print("Testing URL Context Matching")
    print("="*60)

    extractor = ThemeExtractor(use_vocabulary=True)

    if not extractor.vocabulary:
        print("❌ Vocabulary not loaded!")
        return False

    print(f"✓ Loaded vocabulary with {len(extractor.vocabulary._url_context_mapping)} URL patterns")
    print()

    all_passed = True

    for test in TEST_CASES:
        print(f"Test: {test['name']}")
        print(f"  URL: {test['url']}")

        # Test URL matching
        matched_area = extractor.vocabulary.match_url_to_product_area(test['url'])

        if test['expected_area'] is None:
            # No URL or shouldn't match
            if matched_area is None:
                print(f"  ✓ No match (as expected)")
            else:
                print(f"  ⚠️  Unexpectedly matched: {matched_area}")
                all_passed = False
        else:
            # Should match
            if matched_area == test['expected_area']:
                print(f"  ✓ Matched: {matched_area}")
            else:
                print(f"  ❌ Expected {test['expected_area']}, got {matched_area}")
                all_passed = False
        print()

    return all_passed


def test_theme_extraction_with_url():
    """Test full theme extraction with URL context."""
    print("="*60)
    print("Testing Theme Extraction with URL Context")
    print("="*60)

    extractor = ThemeExtractor(use_vocabulary=True)

    # Test Pin Scheduler with URL context
    conv = Conversation(
        id="test_pin_scheduler",
        created_at=datetime.utcnow(),
        source_body="My interval pins aren't showing the correct dates in Pin Scheduler. The drag and drop is also running slow.",
        source_url="https://www.tailwindapp.com/dashboard/v2/advanced-scheduler/pinterest",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
    )

    print("Test Case: Pin Scheduler with URL context")
    print(f"URL: {conv.source_url}")
    print(f"Message: {conv.source_body[:80]}...")
    print()

    theme = extractor.extract(conv, strict_mode=True)

    print(f"Extracted Theme:")
    print(f"  Product Area: {theme.product_area}")
    print(f"  Component: {theme.component}")
    print(f"  Issue Signature: {theme.issue_signature}")
    print()

    # Test Legacy Publisher with URL context
    conv2 = Conversation(
        id="test_legacy_publisher",
        created_at=datetime.utcnow(),
        source_body="Fill empty time slots is not working. Dates in legacy Your Schedule are showing incorrectly.",
        source_url="https://www.tailwindapp.com/publisher/queue",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
    )

    print("Test Case: Legacy Publisher with URL context")
    print(f"URL: {conv2.source_url}")
    print(f"Message: {conv2.source_body[:80]}...")
    print()

    theme2 = extractor.extract(conv2, strict_mode=True)

    print(f"Extracted Theme:")
    print(f"  Product Area: {theme2.product_area}")
    print(f"  Component: {theme2.component}")
    print(f"  Issue Signature: {theme2.issue_signature}")
    print()

    # Test Multi-Network with URL context
    conv3 = Conversation(
        id="test_multinetwork",
        created_at=datetime.utcnow(),
        source_body="My Instagram posts aren't publishing from the scheduler. I've been waiting for hours.",
        source_url="https://www.tailwindapp.com/dashboard/v2/scheduler",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
    )

    print("Test Case: Multi-Network Scheduler with URL context")
    print(f"URL: {conv3.source_url}")
    print(f"Message: {conv3.source_body[:80]}...")
    print()

    theme3 = extractor.extract(conv3, strict_mode=True)

    print(f"Extracted Theme:")
    print(f"  Product Area: {theme3.product_area}")
    print(f"  Component: {theme3.component}")
    print(f"  Issue Signature: {theme3.issue_signature}")
    print()

    return True


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print()
    success = test_url_context_matching()
    print()

    if success:
        print("="*60)
        print("✓ URL matching tests passed!")
        print("="*60)
        print()

        print("Now testing full theme extraction with URL context...")
        print("(This will make API calls to OpenAI)")
        print()

        response = input("Continue? [y/N]: ")
        if response.lower() == 'y':
            test_theme_extraction_with_url()
    else:
        print("="*60)
        print("❌ URL matching tests failed")
        print("="*60)
        sys.exit(1)
