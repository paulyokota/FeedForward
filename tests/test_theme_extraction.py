"""
Theme extraction validation tests.

Validates theme extraction against human-labeled fixtures.
Run before/after vocabulary changes to ensure accuracy.

Usage:
    pytest tests/test_theme_extraction.py -v
    python tests/test_theme_extraction.py  # standalone
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.models import Conversation
from theme_extractor import ThemeExtractor


FIXTURES_PATH = Path(__file__).parent.parent / "data" / "theme_fixtures.json"


def load_fixtures() -> list[dict]:
    """Load theme fixtures from JSON file."""
    with open(FIXTURES_PATH) as f:
        data = json.load(f)
    return data["fixtures"]


def fixture_to_conversation(fixture: dict) -> Conversation:
    """Convert fixture dict to Conversation object."""
    return Conversation(
        id=fixture["id"],
        created_at=datetime.now(),
        source_body=fixture["source_body"],
        issue_type=fixture.get("issue_type"),
        sentiment=fixture.get("sentiment"),
        churn_risk=fixture.get("churn_risk", False),
        priority=fixture.get("priority"),
    )


class TestThemeExtraction:
    """Test theme extraction against labeled fixtures."""

    @pytest.fixture(scope="class")
    def extractor(self):
        """Create extractor once for all tests."""
        return ThemeExtractor()

    @pytest.fixture(scope="class")
    def fixtures(self):
        """Load fixtures once for all tests."""
        return load_fixtures()

    def test_fixtures_exist(self, fixtures):
        """Verify fixtures file exists and has data."""
        assert len(fixtures) > 0, "No fixtures found"
        print(f"\nLoaded {len(fixtures)} fixtures")

    @pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda f: f["id"])
    def test_theme_extraction(self, extractor, fixture):
        """Test each fixture extracts to expected theme."""
        conv = fixture_to_conversation(fixture)
        expected = fixture["expected_theme"]
        rationale = fixture.get("rationale", "")

        theme = extractor.extract(conv, strict_mode=True)
        actual = theme.issue_signature

        assert actual == expected, (
            f"\nConversation {fixture['id']}:\n"
            f"  Body: {fixture['source_body'][:80]}...\n"
            f"  Expected: {expected}\n"
            f"  Actual: {actual}\n"
            f"  Rationale: {rationale}"
        )


def run_validation() -> dict:
    """
    Run validation and return results summary.

    Returns dict with:
        - total: number of fixtures
        - passed: number correct
        - failed: number incorrect
        - accuracy: percentage correct
        - failures: list of failure details
    """
    fixtures = load_fixtures()
    extractor = ThemeExtractor()

    results = {
        "total": len(fixtures),
        "passed": 0,
        "failed": 0,
        "accuracy": 0.0,
        "failures": [],
    }

    print(f"\nValidating {len(fixtures)} fixtures...\n")

    for fixture in fixtures:
        conv = fixture_to_conversation(fixture)
        expected = fixture["expected_theme"]

        theme = extractor.extract(conv, strict_mode=True)
        actual = theme.issue_signature

        if actual == expected:
            results["passed"] += 1
            print(f"  ✓ {fixture['id']}: {expected}")
        else:
            results["failed"] += 1
            results["failures"].append({
                "id": fixture["id"],
                "expected": expected,
                "actual": actual,
                "body": fixture["source_body"][:100],
            })
            print(f"  ✗ {fixture['id']}: expected {expected}, got {actual}")

    results["accuracy"] = results["passed"] / results["total"] if results["total"] > 0 else 0

    print(f"\n{'='*50}")
    print(f"RESULTS: {results['passed']}/{results['total']} ({results['accuracy']*100:.1f}%)")
    print(f"{'='*50}")

    if results["failures"]:
        print("\nFailures:")
        for f in results["failures"]:
            print(f"  - {f['id']}: {f['expected']} → {f['actual']}")
            print(f"    {f['body']}...")

    return results


if __name__ == "__main__":
    results = run_validation()
    sys.exit(0 if results["failed"] == 0 else 1)
