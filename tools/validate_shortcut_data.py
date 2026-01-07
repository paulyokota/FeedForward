"""
Validate theme extraction against Shortcut training data.

Uses 829 manually-labeled Shortcut stories to test:
1. Whether our theme extractor routes to the correct Product Area
2. Which Product Areas have coverage gaps

Usage:
    python tools/validate_shortcut_data.py              # Keyword baseline only
    python tools/validate_shortcut_data.py --llm        # Include LLM validation (costs $)
    python tools/validate_shortcut_data.py --sample 10  # LLM on N samples per area
"""

import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# Load data files
DATA_DIR = Path(__file__).parent.parent / "data"
VOCAB_PATH = Path(__file__).parent.parent / "config" / "theme_vocabulary.json"


def load_shortcut_data() -> list[dict]:
    """Load Shortcut training data."""
    with open(DATA_DIR / "shortcut_training_data.json") as f:
        data = json.load(f)
    return data["stories"]


# Product Area synonyms - map to canonical names
PRODUCT_AREA_SYNONYMS = {
    "Pin Scheduler": "Next Publisher",  # Same product, different names
    "Original Publisher": "Legacy Publisher",
    "Original Scheduler": "Legacy Publisher",
    "Pin Inspector": "Analytics",
    "Insights": "Analytics",
}


def normalize_product_area(area: str) -> str:
    """Normalize Product Area to canonical name."""
    return PRODUCT_AREA_SYNONYMS.get(area, area)


def load_vocabulary() -> dict:
    """Load theme vocabulary with product area mapping."""
    with open(VOCAB_PATH) as f:
        return json.load(f)


def build_reverse_mapping(vocab: dict) -> dict:
    """Build theme signature → Product Area mapping."""
    mapping = {}
    for product_area, themes in vocab.get("product_area_mapping", {}).items():
        if product_area.startswith("_"):
            continue
        for theme in themes:
            mapping[theme] = product_area
    return mapping


def get_url_context(vocab: dict) -> dict:
    """Get URL pattern → Product Area mapping."""
    return vocab.get("url_context_mapping", {})


def build_keyword_index(vocab: dict) -> dict:
    """Build keyword → Product Area index for baseline matching."""
    index = defaultdict(set)

    # Add customer-friendly keywords from themes
    for sig, theme in vocab.get("themes", {}).items():
        product_area = None
        # Find which Shortcut Product Area this theme maps to
        for area, themes in vocab.get("product_area_mapping", {}).items():
            if sig in themes:
                product_area = area
                break

        if product_area:
            # Add theme keywords
            for kw in theme.get("keywords", []):
                index[kw.lower()].add(product_area)
            # Add signature words
            for word in sig.split("_"):
                if len(word) > 2:
                    index[word.lower()].add(product_area)

    # Add manual keyword mappings for known Product Areas
    # Note: More specific keywords should be listed first (longer = higher weight)
    manual_mappings = {
        "Next Publisher": [
            "pin scheduler", "scheduler", "scheduling", "schedule", "smartschedule",
            "pin spacing", "interval", "queue", "twnext", "multi-network scheduler",
            "quick schedule", "2.0 scheduler", "frictionless uploads", "drafts queue"
        ],
        "Legacy Publisher": [
            "original publisher", "legacy publisher", "old dashboard", "legacy scheduler",
            "legacy", "original scheduler", "your schedule"  # "your schedule" is legacy UI
        ],
        "Analytics": [
            "insights", "analytics", "inspector", "pin inspector", "metrics",
            "performance", "engagement", "profile performance"
        ],
        "Billing & Settings": [
            "billing", "payment", "subscription", "cancel", "upgrade", "plan",
            "pricing", "credit card", "refund", "checkout", "dunning"
        ],
        "Communities": ["communities", "tribes", "community", "turbo"],
        "GW Labs": [
            "ghostwriter", "gw labs", "ai text", "generate text", "ai writing",
            "fb labs", "ai labs"  # FB Labs = Facebook version of GW Labs
        ],
        "Create": [
            "tailwind create", "in create", "create design", "image design",
            "createclassic", "createnext", "image cropping", "create is",
            "create not", "create error"
        ],
        "Made For You": [
            "made for you", "m4u", "ai generated pins", "auto generated",
            "m4u drafts", "ai content"
        ],
        "SmartPin": ["smartpin", "smart pin", "auto pin"],
        "Product Dashboard": [
            "shopify", "product dashboard", "product dash", "e-commerce", "ecommerce",
            "woocommerce", "charlotte"  # Charlotte = Product Dashboard backend
        ],
        "Smart.bio": ["smart.bio", "smartbio", "bio link", "link in bio"],
        "Extension": [
            "extension", "browser extension", "chrome extension", "safari extension",
            "pin from extension"
        ],
        "Ads": [
            "pinterest ads", "ads onboarding", "ads oauth", "ads settings",
            "promoted pins", "advertising"
        ],
        "CoPilot": [
            "copilot", "marketing plan", "content plan", "suggested posts",
            "copilot plan", "task complete"
        ],
        "Onboarding": [
            "onboarding", "signup", "sign up", "getting started", "new user",
            "learn tailwind", "walkthrough"
        ],
        "SmartLoop": ["smartloop", "smart loop", "looping"],
        "Email": ["email automation", "email template", "cakemail"],
        "Jarvis": ["jarvis"],  # Internal tool
    }

    for area, keywords in manual_mappings.items():
        for kw in keywords:
            index[kw.lower()].add(area)

    return index


def keyword_match(title: str, keyword_index: dict) -> str | None:
    """Match title to Product Area using keywords with context boosting."""
    title_lower = title.lower()

    matches = defaultdict(int)
    for keyword, areas in keyword_index.items():
        if keyword in title_lower:
            for area in areas:
                # Weight by keyword length (longer = more specific)
                matches[area] += len(keyword)

    # Context boosting: If strong context keywords present, boost that area
    # This helps with overlapping keywords (e.g., "extension spinning" vs "spinning wheel")
    context_boosts = {
        "Extension": ["extension", "browser extension", "chrome extension"],
        "Legacy Publisher": ["legacy", "original publisher", "original scheduler"],
        "Smart.bio": ["smart.bio", "smartbio", "bio link"],
        "Product Dashboard": ["shopify", "product dashboard", "charlotte"],
        "Ads": ["pinterest ads", "ads oauth", "promoted pins"],
        "CoPilot": ["copilot", "marketing plan"],
    }

    for area, context_keywords in context_boosts.items():
        for ctx_keyword in context_keywords:
            if ctx_keyword in title_lower and area in matches:
                # Boost by 50 points (stronger than typical keyword matches)
                matches[area] += 50

    if matches:
        return max(matches.keys(), key=lambda a: matches[a])
    return None


def validate_with_llm(stories: list[dict], vocab: dict, sample_size: int = None):
    """Run LLM validation on stories."""
    from db.models import Conversation
    from theme_extractor import ThemeExtractor

    extractor = ThemeExtractor()
    reverse_map = build_reverse_mapping(vocab)

    results = defaultdict(lambda: {"correct": 0, "incorrect": 0, "examples": []})

    # Sample if requested
    if sample_size:
        by_area = defaultdict(list)
        for s in stories:
            if s["product_area"]:
                by_area[s["product_area"]].append(s)

        sampled = []
        for area, area_stories in by_area.items():
            sampled.extend(area_stories[:sample_size])
        stories = sampled
        print(f"\nSampled {len(stories)} stories ({sample_size} per area)")

    print(f"\nRunning LLM validation on {len(stories)} stories...")

    for i, story in enumerate(stories):
        if not story["product_area"]:
            continue

        expected_area = story["product_area"]
        title = story["name"]

        # Create fake conversation from title
        conv = Conversation(
            id=str(story["id"]),
            created_at=datetime.now(),
            source_body=title,
            issue_type="bug_report",
            sentiment="neutral",
            churn_risk=False,
            priority="normal",
        )

        try:
            theme = extractor.extract(conv, strict_mode=True)
            predicted_area = reverse_map.get(theme.issue_signature, "System wide")

            is_correct = predicted_area == expected_area
            results[expected_area]["correct" if is_correct else "incorrect"] += 1

            if not is_correct:
                results[expected_area]["examples"].append({
                    "title": title,
                    "expected": expected_area,
                    "predicted": predicted_area,
                    "theme": theme.issue_signature,
                })

            status = "✓" if is_correct else "✗"
            print(f"  [{i+1}/{len(stories)}] {status} {title[:50]}... → {theme.issue_signature}")

        except Exception as e:
            print(f"  [{i+1}/{len(stories)}] ERROR: {e}")
            results[expected_area]["incorrect"] += 1

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate theme extraction against Shortcut data")
    parser.add_argument("--llm", action="store_true", help="Run LLM validation (costs $)")
    parser.add_argument("--sample", type=int, help="Sample N stories per Product Area for LLM")
    args = parser.parse_args()

    print("Loading data...")
    stories = load_shortcut_data()
    vocab = load_vocabulary()

    # Filter to stories with Product Area and normalize
    labeled_stories = []
    for s in stories:
        if s.get("product_area"):
            s["product_area"] = normalize_product_area(s["product_area"])
            labeled_stories.append(s)
    print(f"Loaded {len(labeled_stories)} stories with Product Area labels")

    # Show synonym normalization
    print(f"Product Area synonyms applied: {list(PRODUCT_AREA_SYNONYMS.keys())}")

    # Build keyword index
    keyword_index = build_keyword_index(vocab)
    print(f"Built keyword index with {len(keyword_index)} keywords")

    # Run keyword baseline
    print("\n" + "="*60)
    print("KEYWORD BASELINE")
    print("="*60)

    results = defaultdict(lambda: {"correct": 0, "incorrect": 0, "no_match": 0, "examples": []})

    for story in labeled_stories:
        expected = story["product_area"]
        predicted = keyword_match(story["name"], keyword_index)

        if predicted is None:
            results[expected]["no_match"] += 1
        elif predicted == expected:
            results[expected]["correct"] += 1
        else:
            results[expected]["incorrect"] += 1
            if len(results[expected]["examples"]) < 3:
                results[expected]["examples"].append({
                    "title": story["name"][:60],
                    "predicted": predicted,
                })

    # Print results
    print(f"\n{'Product Area':<25} {'Correct':<10} {'Wrong':<10} {'No Match':<10} {'Accuracy':<10}")
    print("-"*65)

    total_correct = 0
    total_incorrect = 0
    total_no_match = 0

    for area in sorted(results.keys()):
        r = results[area]
        total = r["correct"] + r["incorrect"] + r["no_match"]
        accuracy = r["correct"] / total if total > 0 else 0

        total_correct += r["correct"]
        total_incorrect += r["incorrect"]
        total_no_match += r["no_match"]

        print(f"{area:<25} {r['correct']:<10} {r['incorrect']:<10} {r['no_match']:<10} {accuracy:.1%}")

        # Show example mismatches
        for ex in r["examples"]:
            print(f"  ↳ \"{ex['title']}\" → {ex['predicted']}")

    print("-"*65)
    total = total_correct + total_incorrect + total_no_match
    overall_accuracy = total_correct / total if total > 0 else 0
    print(f"{'TOTAL':<25} {total_correct:<10} {total_incorrect:<10} {total_no_match:<10} {overall_accuracy:.1%}")

    # Coverage gaps
    print("\n" + "="*60)
    print("COVERAGE GAPS (No themes yet)")
    print("="*60)

    no_theme_areas = [
        area for area, themes in vocab.get("product_area_mapping", {}).items()
        if not area.startswith("_") and len(themes) == 0
    ]

    for area in no_theme_areas:
        count = sum(1 for s in labeled_stories if s["product_area"] == area)
        if count > 0:
            print(f"  {area}: {count} stories (0 themes)")

    # Run LLM validation if requested
    if args.llm:
        print("\n" + "="*60)
        print("LLM VALIDATION")
        print("="*60)

        llm_results = validate_with_llm(labeled_stories, vocab, sample_size=args.sample)

        print(f"\n{'Product Area':<25} {'Correct':<10} {'Wrong':<10} {'Accuracy':<10}")
        print("-"*55)

        for area in sorted(llm_results.keys()):
            r = llm_results[area]
            total = r["correct"] + r["incorrect"]
            accuracy = r["correct"] / total if total > 0 else 0
            print(f"{area:<25} {r['correct']:<10} {r['incorrect']:<10} {accuracy:.1%}")

            # Show misclassifications
            for ex in r["examples"][:2]:
                print(f"  ↳ \"{ex['title'][:40]}...\" → {ex['theme']} ({ex['predicted']})")


if __name__ == "__main__":
    main()
