#!/usr/bin/env python3
"""
Phase 5F: Improved theme extraction using Shortcut product names.

Iteration 1: Extract Shortcut-specific product names instead of FeedForward categories.
"""
import json
import os
import sys
import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()

from openai import OpenAI

# Shortcut product names (the actual ground truth labels)
SHORTCUT_PRODUCTS = [
    "Pin Scheduler",
    "Next Publisher",
    "Legacy Publisher",
    "SmartLoop",
    "Create",
    "Made For You",
    "GW Labs",
    "SmartPin",
    "CoPilot",
    "Analytics",
    "Billing & Settings",
    "Extension",
    "Product Dashboard",
    "Communities",
    "Smart.bio",
    "System wide",
]


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = ' '.join(clean.split())
    return clean.strip()


def extract_product_keywords_v2(text: str) -> Optional[str]:
    """
    Extract Shortcut product name using improved keyword matching.
    """
    text_lower = text.lower()

    # Direct product name matches (highest priority)
    product_keywords = {
        "Pin Scheduler": ["pin scheduler", "scheduler beta", "new scheduler"],
        "Next Publisher": ["next publisher", "new publisher"],
        "Legacy Publisher": ["legacy publisher", "original publisher", "old publisher"],
        "SmartLoop": ["smartloop", "smart loop", "looping"],
        "Create": ["create", "design tool", "canva", "designs"],
        "Made For You": ["made for you", "mfy", "ai suggestions", "suggested pins"],
        "GW Labs": ["ghostwriter", "gw labs", "ghost writer", "ai writer"],
        "SmartPin": ["smartpin", "smart pin"],
        "CoPilot": ["copilot", "co-pilot"],
        "Analytics": ["analytics", "insights", "performance", "statistics", "stats", "pin inspector"],
        "Billing & Settings": ["billing", "subscription", "payment", "cancel", "upgrade", "downgrade", "plan", "pricing", "refund"],
        "Extension": ["extension", "browser", "chrome", "firefox", "safari extension"],
        "Product Dashboard": ["dashboard", "wordpress", "shopify", "woocommerce", "csv"],
        "Communities": ["communities", "community", "tailwind communities", "tribes"],
        "Smart.bio": ["smart.bio", "smartbio", "bio link", "link in bio", "bio page"],
    }

    # Score each product
    scores = {}
    for product, keywords in product_keywords.items():
        score = 0
        for kw in keywords:
            if kw in text_lower:
                # Boost for exact multi-word matches
                score += 2 if " " in kw else 1
        if score > 0:
            scores[product] = score

    if scores:
        best = max(scores.items(), key=lambda x: x[1])
        if best[1] >= 1:
            return best[0]

    return None


# Improved LLM prompt using Shortcut product names
SHORTCUT_PRODUCT_PROMPT = """You are classifying Tailwind customer support messages by product area.

**Message:**
{message}

**Tailwind Products (choose the MOST SPECIFIC match):**

SCHEDULING:
- Pin Scheduler: New scheduling tool, beta scheduler, time slots, queue
- Next Publisher: New/Next publisher for Pinterest publishing
- Legacy Publisher: Original/old publisher, classic scheduling
- SmartLoop: Looping pins, evergreen content republishing

CONTENT CREATION:
- Create: Design tool, pin designs, templates, Canva-like features
- Made For You: AI-suggested pins, personalized recommendations
- GW Labs: Ghostwriter, AI writing, caption generation
- SmartPin: Smart pin creation
- CoPilot: AI assistant, copilot features

ANALYTICS & SETTINGS:
- Analytics: Performance stats, insights, Pin Inspector, metrics
- Billing & Settings: Plans, payments, subscriptions, account settings, cancellation

INTEGRATIONS:
- Extension: Browser extension, Chrome/Firefox/Safari, quick scheduling from web
- Product Dashboard: Shopify, WooCommerce, WordPress, CSV imports

OTHER:
- Communities: Tailwind Communities, content sharing groups
- Smart.bio: Link in bio, bio page, smartbio
- System wide: General issues, doesn't fit specific product

IMPORTANT:
- Choose the most specific product that matches
- Avoid "System wide" unless the message truly doesn't mention any product
- Look for product names, features, and context clues

Respond with JSON: {{"product": "Product Name", "confidence": "high|medium|low"}}"""


def extract_product_llm_v2(text: str, client: OpenAI) -> dict:
    """Extract Shortcut product name using LLM."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You classify Tailwind support messages by product. Be specific, avoid 'System wide' unless necessary. Respond with JSON only."},
                {"role": "user", "content": SHORTCUT_PRODUCT_PROMPT.format(message=text[:2000])},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=100,
        )
        result = json.loads(response.choices[0].message.content)
        product = result.get("product", "System wide")

        # Normalize product name
        product_normalized = normalize_product_name(product)

        return {
            "product": product_normalized,
            "confidence": result.get("confidence", "medium"),
            "method": "llm_v2",
        }
    except Exception as e:
        print(f"  LLM error: {e}")
        return {"product": "System wide", "confidence": "low", "method": "llm_error"}


def normalize_product_name(product: str) -> str:
    """Normalize product name to match Shortcut labels."""
    # Map common variations to canonical names
    normalizations = {
        "pin scheduler": "Pin Scheduler",
        "next publisher": "Next Publisher",
        "legacy publisher": "Legacy Publisher",
        "smartloop": "SmartLoop",
        "smart loop": "SmartLoop",
        "create": "Create",
        "made for you": "Made For You",
        "gw labs": "GW Labs",
        "ghostwriter": "GW Labs",
        "smartpin": "SmartPin",
        "copilot": "CoPilot",
        "analytics": "Analytics",
        "billing & settings": "Billing & Settings",
        "billing": "Billing & Settings",
        "settings": "Billing & Settings",
        "extension": "Extension",
        "browser extension": "Extension",
        "product dashboard": "Product Dashboard",
        "dashboard": "Product Dashboard",
        "communities": "Communities",
        "smart.bio": "Smart.bio",
        "smartbio": "Smart.bio",
        "system wide": "System wide",
        "other": "System wide",
    }

    product_lower = product.lower().strip()
    return normalizations.get(product_lower, product)


def run_extraction_v2():
    """Run improved product extraction on all validation conversations."""
    print("=" * 60)
    print("PHASE 5F: IMPROVED EXTRACTION (ITERATION 1)")
    print("=" * 60)
    print("Using Shortcut product names instead of FeedForward categories")

    # Load ground truth data
    with open("data/phase5_ground_truth.json") as f:
        data = json.load(f)

    validation_set = data.get("validation_set", [])
    analysis_set = data.get("analysis_set", [])
    all_convs = validation_set + analysis_set

    print(f"\n📊 Conversations to process: {len(all_convs)}")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results = []
    stats = {
        "total": len(all_convs),
        "keyword_matches": 0,
        "llm_fallback": 0,
        "errors": 0,
    }

    print("\n🔍 Extracting Shortcut product names...")

    for i, conv in enumerate(all_convs, 1):
        conv_id = conv["conversation_id"]
        source_body = clean_html(conv.get("source_body", ""))
        ground_truth = conv.get("product_area")

        print(f"  [{i}/{len(all_convs)}] {conv_id}...", end=" ")

        if not source_body or len(source_body) < 10:
            print("⚠️ Empty/short message")
            results.append({
                "conversation_id": conv_id,
                "extracted_product": "System wide",
                "extraction_method": "empty",
                "confidence": "low",
                "ground_truth": ground_truth,
                "source_body_preview": source_body[:100] if source_body else "",
            })
            stats["errors"] += 1
            continue

        # Try keyword matching first
        keyword_product = extract_product_keywords_v2(source_body)

        if keyword_product:
            print(f"✅ keywords → {keyword_product}")
            results.append({
                "conversation_id": conv_id,
                "extracted_product": keyword_product,
                "extraction_method": "keywords_v2",
                "confidence": "medium",
                "ground_truth": ground_truth,
                "source_body_preview": source_body[:200],
            })
            stats["keyword_matches"] += 1
        else:
            # Fallback to LLM
            llm_result = extract_product_llm_v2(source_body, client)
            print(f"🤖 llm → {llm_result['product']} ({llm_result['confidence']})")
            results.append({
                "conversation_id": conv_id,
                "extracted_product": llm_result["product"],
                "extraction_method": llm_result["method"],
                "confidence": llm_result["confidence"],
                "ground_truth": ground_truth,
                "source_body_preview": source_body[:200],
            })
            stats["llm_fallback"] += 1

    # Calculate accuracy
    correct = sum(1 for r in results if r["extraction_method"] != "empty"
                  and r["extracted_product"] == r["ground_truth"])
    total_valid = sum(1 for r in results if r["extraction_method"] != "empty")
    accuracy = correct / total_valid * 100 if total_valid > 0 else 0

    # Save results
    output = {
        "extraction_results": results,
        "statistics": stats,
        "accuracy": accuracy,
        "iteration": 1,
    }

    with open("data/phase5_extraction_v2.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n📊 Extraction Statistics:")
    print(f"   Total processed: {stats['total']}")
    print(f"   Keyword matches: {stats['keyword_matches']} ({stats['keyword_matches']/stats['total']*100:.1f}%)")
    print(f"   LLM fallback: {stats['llm_fallback']} ({stats['llm_fallback']/stats['total']*100:.1f}%)")
    print(f"   Errors: {stats['errors']}")
    print(f"\n🎯 ACCURACY: {accuracy:.1f}% ({correct}/{total_valid})")

    print(f"\n💾 Saved to data/phase5_extraction_v2.json")

    return accuracy, output


if __name__ == "__main__":
    accuracy, output = run_extraction_v2()
    print(f"\n{'='*60}")
    target_met = "TARGET MET!" if accuracy >= 85 else f"Below target ({accuracy:.1f}% < 85%)"
    print(f"PHASE 5F ITERATION 1 COMPLETE - {target_met}")
    print(f"{'='*60}")
