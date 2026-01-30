#!/usr/bin/env python3
"""
Phase 4: Functional Test for Vocabulary Guidance (Issue #153)

Tests whether the vocabulary distinction examples help the LLM
make correct signature distinctions during theme extraction.

Test cases based on #152 false positive patterns:
1. Drafts vs scheduled pins (object_type distinction)
2. Scheduling vs unscheduling (action distinction)
3. DURING vs AFTER connection (timing distinction)
4. Selection vs generation stage (stage distinction)

Usage:
    python scripts/test_vocabulary_guidance.py
    python scripts/test_vocabulary_guidance.py --verbose
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vocabulary import ThemeVocabulary
from src.theme_extractor import ThemeExtractor
from src.db.models import Conversation

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """A functional test case for vocabulary guidance."""
    name: str
    description: str
    conversation_text: str
    expected_distinction: str  # Which facet should distinguish
    should_match: list[str]  # Expected signature patterns (any match = pass)
    should_not_match: list[str]  # Should NOT match any of these patterns


# Synonym groups for flexible matching
SYNONYMS = {
    "import": ["import", "fetch", "pull", "load"],
    "export": ["export", "push", "send"],
    "scheduled": ["scheduled", "scheduling", "schedule", "queued"],
    "draft": ["draft", "drafts"],
    "delete": ["delete", "remove", "clear"],
    "sync": ["sync", "syncing", "synchron"],
    "connection": ["connection", "connect", "oauth", "auth"],
    "generate": ["generate", "generat", "creation", "create"],
}


# Test cases based on #152 false positive patterns
TEST_CASES = [
    TestCase(
        name="drafts_vs_scheduled_pins",
        description="User wants to bulk delete DRAFTS (not scheduled pins)",
        conversation_text="""
        User: I have a bunch of drafts that I don't want anymore. How do I delete them all at once?
        Agent: You can select multiple drafts and delete them from the drafts tab.
        User: Great, I want to bulk delete all my drafts, not the scheduled ones.
        """,
        expected_distinction="object_type",
        should_match=["draft"],
        should_not_match=["scheduled_pin", "queued_pin"],
    ),
    TestCase(
        name="scheduled_pins_vs_drafts",
        description="User wants to bulk delete SCHEDULED PINS (not drafts)",
        conversation_text="""
        User: I scheduled a bunch of pins for next week but I changed my mind. How do I remove them all?
        Agent: You can select the scheduled pins and unschedule or delete them.
        User: I want to delete all my scheduled pins, not move them to drafts.
        """,
        expected_distinction="object_type",
        should_match=["scheduled", "scheduling", "queued"],  # Synonyms for scheduled content
        should_not_match=["draft"],
    ),
    TestCase(
        name="scheduling_action",
        description="User wants to SCHEDULE pins (not unschedule)",
        conversation_text="""
        User: How do I schedule multiple pins at once?
        Agent: You can use bulk scheduling to schedule pins in batches.
        User: Yes, I want to schedule them all for next week.
        """,
        expected_distinction="action",
        should_match=["schedul"],  # schedule/scheduling
        should_not_match=["unschedul"],
    ),
    TestCase(
        name="unscheduling_action",
        description="User wants to UNSCHEDULE pins (not schedule)",
        conversation_text="""
        User: I need to unschedule all my pins for tomorrow.
        Agent: You can select the pins and choose unschedule.
        User: How do I bulk unschedule? I don't want to delete them, just move them back.
        """,
        expected_distinction="action",
        should_match=["unschedul"],
        should_not_match=["delete", "remove"],
    ),
    TestCase(
        name="connection_during",
        description="Error DURING connection attempt (not after)",
        conversation_text="""
        User: I'm trying to connect my Pinterest account but I keep getting an error.
        Agent: What error do you see?
        User: It says "connection failed" when I try to authorize. The OAuth popup shows an error.
        """,
        expected_distinction="timing",
        should_match=["connection", "oauth", "connect"],
        should_not_match=["sync", "board"],
    ),
    TestCase(
        name="connection_after",
        description="Issue AFTER successful connection (sync problem)",
        conversation_text="""
        User: I connected my Pinterest account but my boards aren't showing up.
        Agent: When did you connect?
        User: Yesterday. The connection went through but my boards still aren't syncing.
        """,
        expected_distinction="timing",
        should_match=["sync", "board", "missing"],  # Post-connection issues
        should_not_match=["oauth_fail", "connection_fail"],
    ),
    TestCase(
        name="image_import_stage",
        description="Image IMPORT failure (fetching images)",
        conversation_text="""
        User: SmartPin can't fetch images from my website.
        Agent: What error do you see?
        User: It says it can't import the images. The scraping isn't working.
        """,
        expected_distinction="stage",
        should_match=["import", "fetch", "scrape", "pull"],  # Synonyms for import
        should_not_match=["generat", "create", "design"],
    ),
    TestCase(
        name="image_generation_stage",
        description="Image GENERATION failure (creating pins)",
        conversation_text="""
        User: SmartPin imported my images but the pin designs aren't generating.
        Agent: What happens when you try to generate?
        User: The images are there but when I click generate, nothing happens.
        """,
        expected_distinction="stage",
        should_match=["generat", "create", "design"],
        should_not_match=["import", "fetch", "scrape"],
    ),
]


def run_test(extractor: ThemeExtractor, test: TestCase, verbose: bool = False) -> tuple[bool, str]:
    """
    Run a single test case.

    Returns (passed, reason).
    """
    try:
        # Create a Conversation object with required fields
        conv = Conversation(
            id="test_" + test.name,
            created_at=datetime.utcnow(),
            source_body=test.conversation_text,
            source_type="email",
            # Required classification fields (use defaults for testing)
            issue_type="product_question",
            sentiment="neutral",
            churn_risk=False,
            priority="normal",
        )

        # Extract theme using full_conversation parameter
        result = extractor.extract(
            conv=conv,
            full_conversation=test.conversation_text,
            use_full_conversation=True,
        )

        if not result:
            return False, "No theme extracted"

        # Get the extracted signature
        signature = result.issue_signature.lower()

        if verbose:
            logger.info(f"  Extracted signature: {result.issue_signature}")
            logger.info(f"  Product area: {result.product_area}")

        # Check should_match (any pattern in list = pass)
        matched_pattern = None
        for pattern in test.should_match:
            if pattern.lower() in signature:
                matched_pattern = pattern
                break

        if not matched_pattern:
            return False, f"Expected one of {test.should_match} in signature, got '{result.issue_signature}'"

        # Check should_not_match (any pattern in list = fail)
        for pattern in test.should_not_match:
            if pattern.lower() in signature:
                return False, f"Should NOT contain '{pattern}', got '{result.issue_signature}'"

        return True, f"Correct: {result.issue_signature} (matched '{matched_pattern}')"

    except Exception as e:
        import traceback
        if verbose:
            traceback.print_exc()
        return False, f"Error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Phase 4: Test vocabulary guidance")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--test", type=str, help="Run specific test by name")
    args = parser.parse_args()

    # Check vocabulary has term distinctions (Issue #153 Phase 3 output)
    vocab = ThemeVocabulary()
    term_distinctions = vocab._term_distinctions

    if not term_distinctions:
        logger.error("No term_distinctions in vocabulary! Run Phase 3 first.")
        sys.exit(1)

    similar_ux_count = len([k for k in term_distinctions.get("similar_ux", {}).keys() if not k.startswith("_")])
    different_model_count = len([k for k in term_distinctions.get("different_model", {}).keys() if not k.startswith("_")])
    name_confusion_count = len([k for k in term_distinctions.get("name_confusion", {}).keys() if not k.startswith("_")])
    logger.info(f"Vocabulary has {similar_ux_count} similar_ux + {different_model_count} different_model + {name_confusion_count} name_confusion term pairs")

    # Show prompt preview
    if args.verbose:
        term_guidance = vocab.format_term_distinctions()
        logger.info(f"\nTerm distinctions preview:\n{term_guidance}\n")

    # Initialize extractor
    logger.info("Initializing theme extractor...")
    extractor = ThemeExtractor()

    # Filter tests if specific one requested
    tests = TEST_CASES
    if args.test:
        tests = [t for t in TEST_CASES if t.name == args.test]
        if not tests:
            logger.error(f"Test '{args.test}' not found")
            sys.exit(1)

    # Run tests
    print("\n" + "=" * 60)
    print("FUNCTIONAL TESTS: Vocabulary Guidance")
    print("=" * 60)

    passed = 0
    failed = 0
    results = []

    for test in tests:
        print(f"\n[{test.name}] {test.description}")
        print(f"  Expected distinction: {test.expected_distinction}")

        success, reason = run_test(extractor, test, verbose=args.verbose)

        if success:
            print(f"  ✅ PASS: {reason}")
            passed += 1
        else:
            print(f"  ❌ FAIL: {reason}")
            failed += 1

        results.append({
            "name": test.name,
            "passed": success,
            "reason": reason,
        })

    # Summary
    total = passed + failed
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} passed ({100*passed/total:.1f}%)")
    print("=" * 60)

    # Save results
    results_path = Path(__file__).parent.parent / "data" / "vocabulary_guidance_results.json"
    with open(results_path, "w") as f:
        json.dump({
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "results": results,
        }, f, indent=2)

    print(f"\nResults saved to: {results_path}")

    # Exit code
    target_rate = 0.875  # 7/8 = 87.5%
    actual_rate = passed / total if total > 0 else 0

    if actual_rate >= target_rate:
        print(f"✅ Target met: {actual_rate:.1%} >= {target_rate:.1%}")
        sys.exit(0)
    else:
        print(f"❌ Target not met: {actual_rate:.1%} < {target_rate:.1%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
