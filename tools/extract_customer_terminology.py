"""
Extract customer terminology from Shortcut story descriptions and comments.

Mines:
1. Customer terminology from story descriptions
2. Direct customer quotes from comments
3. Problem/symptom phrases for theme vocabulary expansion
"""

import json
import re
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"


def load_enriched_data() -> dict:
    """Load the full enriched Shortcut data."""
    with open(DATA_DIR / "shortcut_full_enriched.json") as f:
        return json.load(f)


def extract_customer_phrases(text: str) -> list[str]:
    """Extract customer-like phrases from text."""
    if not text:
        return []

    phrases = []

    # Patterns for customer problem descriptions
    patterns = [
        # User is experiencing / having issues
        r"(?:user|member|customer)\s+(?:is\s+)?(?:having|experiencing|reporting|seeing|getting)\s+(.{10,60})",
        # Not working / broken phrases
        r"(?:is\s+)?(?:not\s+)?(?:working|loading|showing|displaying|updating|connecting)\s+(.{5,40})",
        # Error messages
        r"(?:error|issue|bug|problem)(?:\s+message)?[:\s]+[\"']?(.{10,80})[\"']?",
        # Can't / won't do something
        r"(?:can'?t|won'?t|unable to|doesn'?t|isn'?t)\s+(.{5,50})",
        # Shows / displays incorrectly
        r"(?:shows?|displays?|appears?)\s+(?:as\s+)?(.{5,40})\s+(?:instead|incorrectly|wrong)",
        # User reported / said
        r"(?:user|member|customer)\s+(?:reported|said|mentioned|noted)(?:\s+that)?\s+(.{10,80})",
        # Stuck / loop / spinning
        r"(?:stuck|looping?|spinning|frozen)\s+(.{5,40})",
    ]

    text_lower = text.lower()
    for pattern in patterns:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        phrases.extend(matches)

    return phrases


def extract_quoted_text(text: str) -> list[str]:
    """Extract text in quotes that might be customer quotes."""
    if not text:
        return []

    quotes = []
    # Match various quote styles
    patterns = [
        r'"([^"]{10,100})"',  # Double quotes
        r"'([^']{10,100})'",  # Single quotes
        r'"([^"]{10,100})"',  # Smart quotes
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        quotes.extend(matches)

    return quotes


def extract_symptom_phrases(text: str) -> list[str]:
    """Extract symptom/problem phrases for theme vocabulary."""
    if not text:
        return []

    symptoms = []
    text_lower = text.lower()

    # Symptom patterns
    symptom_patterns = [
        r"(pins?\s+(?:not|won't|aren't|isn't)\s+\w+)",
        r"((?:unable|can't|won't)\s+(?:to\s+)?\w+\s+\w+)",
        r"(\w+\s+(?:is|are)\s+(?:broken|failing|missing|wrong|incorrect|blank|empty))",
        r"((?:posts?|images?|pins?)\s+(?:not\s+)?(?:showing|loading|appearing|displaying))",
        r"((?:error|issue)\s+(?:when|while|with)\s+\w+)",
        r"((?:spinning|loading)\s+(?:forever|endlessly|stuck))",
        r"((?:blank|white|empty)\s+(?:page|screen|box))",
    ]

    for pattern in symptom_patterns:
        matches = re.findall(pattern, text_lower)
        symptoms.extend(matches)

    return symptoms


def categorize_by_product_area(stories: list[dict]) -> dict:
    """Group stories by product area with extracted terminology."""
    by_area = defaultdict(lambda: {
        "stories": [],
        "customer_phrases": [],
        "quoted_text": [],
        "symptoms": [],
    })

    for story in stories:
        area = story.get("product_area") or "Unassigned"
        desc = story.get("description", "")
        comments = story.get("comments", [])

        story_data = {
            "id": story["id"],
            "name": story["name"],
            "has_description": bool(desc),
            "comment_count": len(comments),
        }
        by_area[area]["stories"].append(story_data)

        # Extract from description
        by_area[area]["customer_phrases"].extend(extract_customer_phrases(desc))
        by_area[area]["quoted_text"].extend(extract_quoted_text(desc))
        by_area[area]["symptoms"].extend(extract_symptom_phrases(desc))

        # Extract from comments
        for comment in comments:
            by_area[area]["customer_phrases"].extend(extract_customer_phrases(comment))
            by_area[area]["quoted_text"].extend(extract_quoted_text(comment))
            by_area[area]["symptoms"].extend(extract_symptom_phrases(comment))

    # Deduplicate and clean
    for area in by_area:
        by_area[area]["customer_phrases"] = list(set(by_area[area]["customer_phrases"]))
        by_area[area]["quoted_text"] = list(set(by_area[area]["quoted_text"]))
        by_area[area]["symptoms"] = list(set(by_area[area]["symptoms"]))

    return dict(by_area)


def extract_comment_quotes(stories: list[dict]) -> list[dict]:
    """Extract direct customer quotes from comments."""
    quotes = []

    for story in stories:
        area = story.get("product_area")
        comments = story.get("comments", [])

        for comment in comments:
            # Look for patterns that indicate customer quotes
            if any(marker in comment.lower() for marker in [
                "user said", "customer said", "member said",
                "user reported", "customer reported", "member reported",
                "they said", "they mentioned", "convo",
            ]):
                # Extract the quoted portions
                quoted = extract_quoted_text(comment)
                if quoted:
                    quotes.append({
                        "story_id": story["id"],
                        "story_name": story["name"],
                        "product_area": area,
                        "quotes": quoted,
                        "source": "comment",
                    })

    return quotes


def extract_description_terminology(stories: list[dict]) -> dict:
    """Extract terminology patterns from descriptions."""
    # Common customer vocabulary by category
    terminology = {
        "action_verbs": defaultdict(int),  # schedule, post, upload, connect
        "problem_indicators": defaultdict(int),  # not working, broken, stuck
        "feature_names": defaultdict(int),  # smartloop, communities, create
        "error_phrases": defaultdict(int),  # error message, failed, timeout
    }

    action_verbs = [
        "schedule", "post", "upload", "connect", "publish", "share",
        "edit", "delete", "create", "save", "drag", "drop", "add",
        "remove", "change", "update", "refresh", "sync", "link",
    ]

    problem_indicators = [
        "not working", "doesn't work", "won't work", "broken",
        "stuck", "frozen", "spinning", "loading", "failing",
        "error", "bug", "issue", "problem", "incorrect", "wrong",
        "missing", "blank", "empty", "can't", "unable",
    ]

    feature_names = [
        "smartloop", "smart.bio", "smartbio", "communities", "tribes",
        "create", "pin scheduler", "advanced scheduler", "quick schedule",
        "extension", "ghostwriter", "copilot", "made for you", "m4u",
        "analytics", "insights", "inspector", "drafts", "queue",
        "calendar", "grid", "profile", "dashboard", "shopify",
    ]

    for story in stories:
        desc = (story.get("description") or "").lower()
        title = story.get("name", "").lower()
        combined = desc + " " + title

        for verb in action_verbs:
            if verb in combined:
                terminology["action_verbs"][verb] += 1

        for indicator in problem_indicators:
            if indicator in combined:
                terminology["problem_indicators"][indicator] += 1

        for feature in feature_names:
            if feature in combined:
                terminology["feature_names"][feature] += 1

    # Convert to sorted lists
    return {
        "action_verbs": sorted(terminology["action_verbs"].items(), key=lambda x: -x[1]),
        "problem_indicators": sorted(terminology["problem_indicators"].items(), key=lambda x: -x[1]),
        "feature_names": sorted(terminology["feature_names"].items(), key=lambda x: -x[1]),
    }


def main():
    print("Loading enriched Shortcut data...")
    data = load_enriched_data()
    stories = data["stories"]
    print(f"Loaded {len(stories)} stories")

    # Extract terminology from descriptions
    print("\nExtracting description terminology...")
    terminology = extract_description_terminology(stories)

    print("\nTop Action Verbs:")
    for verb, count in terminology["action_verbs"][:15]:
        print(f"  {verb}: {count}")

    print("\nTop Problem Indicators:")
    for indicator, count in terminology["problem_indicators"][:15]:
        print(f"  {indicator}: {count}")

    print("\nTop Feature Names:")
    for feature, count in terminology["feature_names"][:15]:
        print(f"  {feature}: {count}")

    # Categorize by product area
    print("\nCategorizing by product area...")
    by_area = categorize_by_product_area(stories)

    # Extract customer quotes from comments
    print("\nExtracting customer quotes from comments...")
    quotes = extract_comment_quotes(stories)
    print(f"Found {len(quotes)} stories with customer quotes")

    # Save results
    output = {
        "source": "shortcut_full_enriched.json",
        "generated_at": "2026-01-07",
        "stats": {
            "total_stories": len(stories),
            "stories_with_product_area": sum(1 for s in stories if s.get("product_area")),
            "stories_with_comments": sum(1 for s in stories if s.get("comments")),
            "total_comments": sum(len(s.get("comments", [])) for s in stories),
            "stories_with_quotes": len(quotes),
        },
        "terminology": terminology,
        "by_product_area": {},
        "customer_quotes": quotes[:50],  # Top 50
    }

    # Add summary by product area
    for area, area_data in by_area.items():
        output["by_product_area"][area] = {
            "story_count": len(area_data["stories"]),
            "unique_symptoms": area_data["symptoms"][:20],
            "customer_phrases": area_data["customer_phrases"][:20],
            "quoted_text": area_data["quoted_text"][:10],
        }

    output_path = DATA_DIR / "shortcut_terminology.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved terminology to {output_path}")

    # Print summary by product area
    print("\n" + "="*60)
    print("PRODUCT AREA SUMMARY")
    print("="*60)

    sorted_areas = sorted(by_area.items(), key=lambda x: -len(x[1]["stories"]))
    for area, area_data in sorted_areas[:15]:
        story_count = len(area_data["stories"])
        symptom_count = len(area_data["symptoms"])
        phrase_count = len(area_data["customer_phrases"])
        print(f"\n{area}: {story_count} stories, {symptom_count} symptoms, {phrase_count} phrases")
        if area_data["symptoms"][:3]:
            print(f"  Symptoms: {area_data['symptoms'][:3]}")


if __name__ == "__main__":
    main()
