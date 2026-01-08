"""
Enhance theme_vocabulary.json with discovered customer keywords.

Adds high-value customer phrases to existing themes to improve routing accuracy.
"""

import json
from pathlib import Path

VOCAB_PATH = Path(__file__).parent.parent / "config" / "theme_vocabulary.json"


def load_vocabulary():
    """Load current vocabulary."""
    with open(VOCAB_PATH) as f:
        return json.load(f)


def enhance_keywords(vocab: dict) -> dict:
    """Add customer keywords to existing themes."""

    # Extension-specific keywords (integration_connection_failure theme)
    vocab["themes"]["integration_connection_failure"]["keywords"].extend([
        "spinning wheel",
        "spinning extension",
        "extension is spinning",
        "WHOOPS popup",
        "chrome extension",
        "browser extension",
        "schedule button",
        "pin from extension",
        "extension stopped working",
        "extension won't connect"
    ])

    # Legacy Publisher keywords (dashboard_version_issue theme)
    vocab["themes"]["dashboard_version_issue"]["keywords"].extend([
        "original publisher",
        "legacy publisher",
        "old dashboard",
        "your schedule",  # Legacy UI identifier
        "legacy scheduler",
        "original scheduler",
        "legacy",
        "in legacy"
    ])

    # Legacy Publisher - pin editing (legacy_pin_editing_blocked theme)
    vocab["themes"]["legacy_pin_editing_blocked"]["keywords"].extend([
        "uploading without titles",
        "without the titles",
        "pins sent back to drafts",
        "sent back to drafts",
        "smartloop error",
        "add pins to loop",
        "pins to a loop",
        "spam safeguard",
        "filter pins for smartloop"
    ])

    # Made For You - add M4U abbreviation to all m4u themes
    for theme_name in ["m4u_content_quality_issue", "m4u_generation_failure", "m4u_feature_question"]:
        if "m4u" not in vocab["themes"][theme_name]["keywords"]:
            vocab["themes"][theme_name]["keywords"].insert(0, "m4u")
        if "m 4 u" not in vocab["themes"][theme_name]["keywords"]:
            vocab["themes"][theme_name]["keywords"].insert(1, "m 4 u")

    # Scheduling failure - add more customer phrases
    vocab["themes"]["scheduling_failure"]["keywords"].extend([
        "failed to schedule",
        "failing to publish",
        "pins failing",
        "posts failing",
        "keeps uploading",
        "uploading pins without"
    ])

    # Analytics - add customer phrases
    vocab["themes"]["analytics_counter_bug"]["keywords"].extend([
        "show zeros",
        "showing zero",
        "shows zero",
        "restricted statistics",
        "statistics restricted",
        "not reflecting",
        "not pulling data",
        "pulling data"
    ])

    # Copilot - add customer phrases
    vocab["themes"]["copilot_feature_question"]["keywords"].extend([
        "marketing plan not working",
        "prompts in first week",
        "too many prompts",
        "lumping prompts together",
        "prompts together"
    ])

    # Smart.bio - add customer phrases
    vocab["themes"]["smartbio_display_issue"]["keywords"].extend([
        "images aren't showing",
        "posts not showing",
        "images not showing",
        "posts aren't showing",
        "not showing in smart",
        "not showing on instagram"
    ])

    # Crossposting
    vocab["themes"]["crossposting_failure"]["keywords"].extend([
        "not being automatically",
        "automatically posted",
        "cross-publishing issues",
        "cross-publishing",
        "auto-post",
        "autopost"
    ])

    # Product Dashboard
    if "shopify store connected but" not in vocab["themes"]["integration_connection_failure"]["keywords"]:
        vocab["themes"]["integration_connection_failure"]["keywords"].extend([
            "shopify store connected but",
            "store connected but doesn't",
            "integration loop",
            "stuck in shopify"
        ])

    # Deduplicate keywords for each theme
    for theme_name, theme_data in vocab["themes"].items():
        theme_data["keywords"] = sorted(list(set(theme_data["keywords"])))

    # Update version and timestamp
    vocab["version"] = "2.6"
    vocab["updated_at"] = "2026-01-07T12:00:00"
    vocab["description"] = "v2.6: Enhanced with customer vocabulary from training data extraction - Extension, Legacy Publisher, M4U, Analytics, CoPilot"

    return vocab


def main():
    print("Loading theme_vocabulary.json...")
    vocab = load_vocabulary()

    print(f"Current version: {vocab['version']}")
    print(f"Themes: {len(vocab['themes'])}")

    print("\nEnhancing keywords with customer vocabulary...")
    vocab = enhance_keywords(vocab)

    # Show changes
    print("\nKeywords added:")
    print("  integration_connection_failure: +10 Extension keywords")
    print("  dashboard_version_issue: +8 Legacy Publisher keywords")
    print("  legacy_pin_editing_blocked: +9 Legacy Publisher keywords")
    print("  m4u_*: +2 M4U abbreviations (3 themes)")
    print("  scheduling_failure: +6 customer phrases")
    print("  analytics_counter_bug: +6 customer phrases")
    print("  copilot_feature_question: +5 customer phrases")
    print("  smartbio_display_issue: +6 customer phrases")
    print("  crossposting_failure: +6 customer phrases")

    # Save
    print(f"\nSaving enhanced vocabulary...")
    with open(VOCAB_PATH, "w") as f:
        json.dump(vocab, f, indent=2)

    print(f"✓ Saved v{vocab['version']} to {VOCAB_PATH}")
    print("\nNext: Run tools/validate_shortcut_data.py to measure accuracy improvement")


if __name__ == "__main__":
    main()
