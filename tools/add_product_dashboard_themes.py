"""
Add Product Dashboard themes to theme_vocabulary.json.

Adds 3 new themes for Product Dashboard coverage:
1. product_dashboard_sync_failure - Products not syncing/refreshing
2. product_dashboard_integration_loop - Stuck in integration loop
3. product_dashboard_feature_question - How to use Product Dashboard
"""

import json
from pathlib import Path

VOCAB_PATH = Path(__file__).parent.parent / "config" / "theme_vocabulary.json"


def load_vocabulary():
    """Load current vocabulary."""
    with open(VOCAB_PATH) as f:
        return json.load(f)


def add_product_dashboard_themes(vocab: dict) -> dict:
    """Add Product Dashboard themes."""

    # Theme 1: Product sync failures
    vocab["themes"]["product_dashboard_sync_failure"] = {
        "issue_signature": "product_dashboard_sync_failure",
        "product_area": "product_dashboard",
        "component": "sync",
        "description": "Products not syncing, refreshing, or pulling from e-commerce platform (Shopify, WooCommerce, Wix)",
        "keywords": [
            "products not refreshing",
            "error syncing",
            "unable to pull products",
            "product imports failing",
            "products not syncing",
            "error fetching products",
            "no response from fetching",
            "product import failed",
            "sync failed",
            "refresh products",
            "products aren't loading",
            "can't pull products"
        ],
        "example_intents": [
            "My products aren't syncing from Shopify",
            "Products not refreshing in Product Dashboard",
            "Error pulling products from my store"
        ],
        "engineering_fix": "E-commerce API integration (Shopify, WooCommerce, Wix), product sync service, error handling",
        "status": "active",
        "merged_into": None,
        "created_at": "2026-01-07T00:00:00",
        "updated_at": "2026-01-07T00:00:00"
    }

    # Theme 2: Integration loop / stuck
    vocab["themes"]["product_dashboard_integration_loop"] = {
        "issue_signature": "product_dashboard_integration_loop",
        "product_area": "product_dashboard",
        "component": "integration",
        "description": "User stuck in integration loop - store shows as connected but Product Dashboard keeps asking to integrate",
        "keywords": [
            "stuck in shopify loop",
            "integration loop",
            "prompting to integrate",
            "prompting me to integrate",
            "product dashboard prompting",
            "keeps asking to integrate",
            "store connected but",
            "shows connected but doesn't",
            "connect on every visit"
        ],
        "example_intents": [
            "Product Dashboard keeps asking me to connect my store even though it's connected",
            "Stuck in an integration loop with Shopify",
            "Store shows as connected but Product Dashboard won't load"
        ],
        "engineering_fix": "Integration state management, OAuth token handling, store connection verification",
        "status": "active",
        "merged_into": None,
        "created_at": "2026-01-07T00:00:00",
        "updated_at": "2026-01-07T00:00:00"
    }

    # Theme 3: Feature questions
    vocab["themes"]["product_dashboard_feature_question"] = {
        "issue_signature": "product_dashboard_feature_question",
        "product_area": "product_dashboard",
        "component": "features",
        "description": "User needs help understanding how to use Product Dashboard features - setup, product selection, pin generation",
        "keywords": [
            "how to use product dashboard",
            "setup product dashboard",
            "connect my store",
            "product dashboard help",
            "what is product dashboard",
            "how does product dashboard work"
        ],
        "example_intents": [
            "How do I set up Product Dashboard?",
            "How do I connect my Shopify store?",
            "What can I do with Product Dashboard?"
        ],
        "engineering_fix": "Documentation, onboarding flow, tooltips, feature discoverability",
        "status": "active",
        "merged_into": None,
        "created_at": "2026-01-07T00:00:00",
        "updated_at": "2026-01-07T00:00:00"
    }

    # Add to product_area_mapping
    vocab["product_area_mapping"]["Product Dashboard"] = [
        "product_dashboard_sync_failure",
        "product_dashboard_integration_loop",
        "product_dashboard_feature_question"
    ]

    # Update version
    vocab["version"] = "2.7"
    vocab["updated_at"] = "2026-01-07T14:00:00"
    vocab["description"] = "v2.7: Added 3 Product Dashboard themes for coverage gap (18 stories)"

    return vocab


def main():
    print("Loading theme_vocabulary.json...")
    vocab = load_vocabulary()

    print(f"Current version: {vocab['version']}")
    print(f"Current themes: {len(vocab['themes'])}")

    print("\nAdding Product Dashboard themes...")
    vocab = add_product_dashboard_themes(vocab)

    print(f"\nNew themes added:")
    print("  1. product_dashboard_sync_failure - Products not syncing/refreshing")
    print("  2. product_dashboard_integration_loop - Stuck in integration loop")
    print("  3. product_dashboard_feature_question - How to use Product Dashboard")

    print(f"\nTotal themes: {len(vocab['themes'])}")

    # Save
    print(f"\nSaving enhanced vocabulary...")
    with open(VOCAB_PATH, "w") as f:
        json.dump(vocab, f, indent=2)

    print(f"✓ Saved v{vocab['version']} to {VOCAB_PATH}")
    print("\nNext: Run tools/validate_shortcut_data.py to measure accuracy improvement")


if __name__ == "__main__":
    main()
