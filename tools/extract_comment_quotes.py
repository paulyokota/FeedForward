"""
Extract customer quotes and feedback from Shortcut story comments.

Focuses on:
1. Direct customer quotes in conversation threads
2. User feedback snippets
3. Problem descriptions that sound like customer language
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


def clean_text(text: str) -> str:
    """Remove markdown, links, and formatting."""
    if not text:
        return ""
    # Remove markdown links
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove shortcut mentions
    text = re.sub(r'\[@\w+\]\([^)]+\)', '', text)
    # Remove image refs
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    # Remove markdown formatting
    text = re.sub(r'[*_`#]+', '', text)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_customer_language_from_description(desc: str) -> list[str]:
    """Extract customer-facing language from issue descriptions."""
    quotes = []
    if not desc:
        return quotes

    desc_clean = clean_text(desc)
    desc_lower = desc_clean.lower()

    # Look for "Brief description" sections - these often contain customer language
    brief_match = re.search(
        r'brief description[^\n]*\n\*?([^*\n]{10,200})',
        desc_lower,
        re.IGNORECASE
    )
    if brief_match:
        quotes.append(brief_match.group(1).strip())

    # Look for customer-reported text patterns
    patterns = [
        # "User said X" / "Member mentioned X"
        r'(?:user|member|customer)\s+(?:said|mentioned|reported|asked|complained)(?:\s+that)?\s*[:\-]?\s*(.{15,150})',
        # Direct feedback markers
        r'(?:feedback|complaint|request)[:\s]+(.{15,150})',
        # Quoted error messages
        r'error\s*(?:message)?[:\s]*["\']([^"\']{10,100})["\']',
        # "shows X instead of Y"
        r'shows?\s+(.{10,60})\s+instead\s+of',
        # Symptom descriptions
        r'(?:is|are)\s+(?:getting|seeing|experiencing)\s+(.{10,100})',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, desc_lower, re.IGNORECASE)
        for match in matches:
            cleaned = clean_text(match)
            if len(cleaned) > 15 and cleaned not in quotes:
                quotes.append(cleaned)

    return quotes[:5]  # Limit per description


def extract_quotes_from_comments(comments: list[str]) -> list[str]:
    """Extract customer quotes from comment threads."""
    quotes = []

    for comment in comments:
        if not comment:
            continue

        comment_clean = clean_text(comment)
        comment_lower = comment_clean.lower()

        # Skip internal-only comments
        skip_markers = [
            "closing", "archiving", "tracking", "merged", "deployed",
            "pr:", "pull request", "github", "shortcut", "workstream",
        ]
        if any(marker in comment_lower for marker in skip_markers):
            continue

        # Customer voice patterns
        patterns = [
            # Direct quotes
            r'(?:user|member|they|customer)\s+(?:said|mentioned|reported|wrote|asked)[:\s]+["\']?(.{15,150})["\']?',
            # Convo snippets
            r'from\s+(?:intercom|convo|conversation)[:\s]+(.{15,150})',
            # Issue reproduction
            r'(?:repro|reproduce|replicate)[:\s]+(.{15,100})',
            # User experience description
            r'(?:user|member)\s+(?:is|was)\s+(?:able|unable|trying|having)\s+(.{15,100})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, comment_lower, re.IGNORECASE)
            for match in matches:
                cleaned = clean_text(match)
                if len(cleaned) > 15 and cleaned not in quotes:
                    quotes.append(cleaned)

        # Also extract well-formed sentences that describe user actions
        sentences = re.split(r'[.!?]\s+', comment_clean)
        for sentence in sentences:
            sentence = sentence.strip()
            if 20 < len(sentence) < 150:
                sentence_lower = sentence.lower()
                # Look for user-focused sentences
                if any(word in sentence_lower for word in [
                    "user", "member", "they", "customer", "her", "his", "their"
                ]) and any(word in sentence_lower for word in [
                    "can't", "cannot", "unable", "doesn't", "won't", "not working",
                    "broken", "failed", "error", "issue", "stuck", "blank"
                ]):
                    if sentence not in quotes:
                        quotes.append(sentence)

    return quotes[:10]  # Limit per story


def process_stories(stories: list[dict]) -> dict:
    """Process all stories to extract customer quotes."""
    results = {
        "from_descriptions": [],
        "from_comments": [],
        "by_product_area": defaultdict(list),
    }

    for story in stories:
        story_id = story["id"]
        name = story["name"]
        area = story.get("product_area") or "Unassigned"
        desc = story.get("description", "")
        comments = story.get("comments", [])

        # Extract from description
        desc_quotes = extract_customer_language_from_description(desc)
        if desc_quotes:
            results["from_descriptions"].append({
                "story_id": story_id,
                "story_name": name,
                "product_area": area,
                "quotes": desc_quotes,
            })
            results["by_product_area"][area].extend(desc_quotes)

        # Extract from comments
        comment_quotes = extract_quotes_from_comments(comments)
        if comment_quotes:
            results["from_comments"].append({
                "story_id": story_id,
                "story_name": name,
                "product_area": area,
                "comment_count": len(comments),
                "quotes": comment_quotes,
            })
            results["by_product_area"][area].extend(comment_quotes)

    # Deduplicate by area
    for area in results["by_product_area"]:
        results["by_product_area"][area] = list(set(results["by_product_area"][area]))

    return results


def generate_theme_vocabulary_additions(results: dict) -> dict:
    """Generate suggested additions to theme vocabulary based on extracted quotes."""
    suggestions = defaultdict(list)

    # Problem phrases that could be keywords
    problem_patterns = [
        (r"can'?t\s+(\w+)\s+(\w+)", "action_blocked"),
        (r"(\w+)\s+(?:not|won't|doesn't)\s+(\w+)", "feature_broken"),
        (r"stuck\s+(?:on|in|at)\s+(\w+)", "stuck_state"),
        (r"blank\s+(\w+)", "blank_ui"),
        (r"error\s+(?:when|while)\s+(\w+)", "error_action"),
    ]

    for area, quotes in results["by_product_area"].items():
        for quote in quotes:
            quote_lower = quote.lower()
            for pattern, category in problem_patterns:
                matches = re.findall(pattern, quote_lower)
                if matches:
                    suggestions[area].append({
                        "phrase": quote[:80],
                        "category": category,
                        "match": matches[0] if matches else None,
                    })

    return dict(suggestions)


def main():
    print("Loading enriched Shortcut data...")
    data = load_enriched_data()
    stories = data["stories"]
    print(f"Loaded {len(stories)} stories")

    print("\nExtracting customer quotes...")
    results = process_stories(stories)

    print(f"\nFound quotes in {len(results['from_descriptions'])} descriptions")
    print(f"Found quotes in {len(results['from_comments'])} comment threads")

    # Generate theme vocabulary suggestions
    print("\nGenerating theme vocabulary suggestions...")
    suggestions = generate_theme_vocabulary_additions(results)

    # Prepare output
    output = {
        "source": "shortcut_full_enriched.json",
        "generated_at": "2026-01-07",
        "extraction_stats": {
            "stories_with_description_quotes": len(results["from_descriptions"]),
            "stories_with_comment_quotes": len(results["from_comments"]),
            "total_unique_quotes": sum(len(q) for q in results["by_product_area"].values()),
        },
        "description_quotes": results["from_descriptions"][:100],
        "comment_quotes": results["from_comments"][:100],
        "by_product_area": {
            area: quotes[:30]
            for area, quotes in sorted(
                results["by_product_area"].items(),
                key=lambda x: -len(x[1])
            )
        },
        "vocabulary_suggestions": suggestions,
    }

    output_path = DATA_DIR / "customer_quotes.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved to {output_path}")

    # Print summary
    print("\n" + "="*60)
    print("EXTRACTED QUOTES BY PRODUCT AREA")
    print("="*60)

    for area, quotes in sorted(results["by_product_area"].items(), key=lambda x: -len(x[1]))[:10]:
        print(f"\n{area}: {len(quotes)} quotes")
        for quote in quotes[:3]:
            print(f"  - \"{quote[:70]}...\"" if len(quote) > 70 else f"  - \"{quote}\"")

    print("\n" + "="*60)
    print("SAMPLE CUSTOMER LANGUAGE")
    print("="*60)

    # Show best examples
    all_quotes = []
    for entry in results["from_descriptions"] + results["from_comments"]:
        for quote in entry.get("quotes", []):
            all_quotes.append({
                "quote": quote,
                "area": entry.get("product_area"),
                "story": entry.get("story_name"),
            })

    # Filter for most customer-sounding quotes
    customer_like = [
        q for q in all_quotes
        if any(word in q["quote"].lower() for word in [
            "can't", "won't", "doesn't", "not working", "broken",
            "stuck", "error", "failed", "missing", "wrong"
        ])
    ]

    print(f"\nTop customer-sounding quotes ({len(customer_like)} found):")
    for item in customer_like[:15]:
        print(f"\n  [{item['area']}] {item['story'][:40]}...")
        print(f"  \"{item['quote'][:100]}\"")


if __name__ == "__main__":
    main()
