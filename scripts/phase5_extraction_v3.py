#!/usr/bin/env python3
"""
Phase 5F: Iteration 3 - Context-aware extraction with uncertainty handling.

Key improvements:
1. Better handling of ambiguous/low-context messages
2. Multi-product detection
3. Improved prompt for edge cases
"""
import json
import os
import sys
import re
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()

from openai import OpenAI

SHORTCUT_PRODUCTS = [
    "Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop",
    "Create", "Made For You", "GW Labs", "SmartPin", "CoPilot",
    "Analytics", "Billing & Settings", "Extension", "Product Dashboard",
    "Communities", "Smart.bio", "System wide"
]


def clean_html(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    return ' '.join(clean.split()).strip()


def has_sufficient_context(text: str) -> bool:
    """Check if message has enough context for classification."""
    if len(text) < 20:
        return False
    # Check for reference to previous conversation
    ref_phrases = ["my last", "my inquiry", "my ticket", "any update", "follow up", "following up"]
    text_lower = text.lower()
    for phrase in ref_phrases:
        if phrase in text_lower:
            return False
    return True


def extract_product_keywords_v3(text: str) -> Tuple[Optional[str], str]:
    """
    Improved keyword extraction with confidence.
    Returns (product, confidence).
    """
    text_lower = text.lower()

    # High-confidence direct mentions
    high_conf_keywords = {
        "Pin Scheduler": ["pin scheduler", "new scheduler"],
        "Next Publisher": ["next publisher"],
        "Legacy Publisher": ["legacy publisher", "original publisher", "old publisher"],
        "SmartLoop": ["smartloop", "smart loop"],
        "Create": ["create tool", "design tool", "tailwind create"],
        "Made For You": ["made for you", "mfy"],
        "GW Labs": ["ghostwriter", "gw labs"],
        "Analytics": ["analytics", "pin inspector", "insights"],
        "Billing & Settings": ["billing", "subscription", "cancel", "payment", "refund"],
        "Extension": ["browser extension", "chrome extension", "tailwind extension"],
        "Product Dashboard": ["wordpress", "shopify", "woocommerce"],
        "Communities": ["communities", "tailwind communities"],
        "Smart.bio": ["smart.bio", "bio link", "link in bio"],
    }

    for product, keywords in high_conf_keywords.items():
        for kw in keywords:
            if kw in text_lower:
                return (product, "high")

    # Medium-confidence contextual keywords
    med_conf_keywords = {
        "Billing & Settings": ["plan", "upgrade", "pricing"],
        "Analytics": ["stats", "performance", "statistics"],
        "Extension": ["extension", "browser"],
        "Create": ["design", "template"],
    }

    for product, keywords in med_conf_keywords.items():
        for kw in keywords:
            if kw in text_lower:
                return (product, "medium")

    return (None, "low")


IMPROVED_PROMPT = """Classify this Tailwind customer support message by the PRIMARY product discussed.

**Message:**
{message}

**Products:**
SCHEDULING (for posting content):
- Pin Scheduler: New scheduling interface, schedule pins, time slots
- Next Publisher: Publishing queue, post scheduling
- Legacy Publisher: Old/original scheduler
- SmartLoop: Evergreen content, looping/republishing pins

CONTENT CREATION (for making content):
- Create: Design tool, pin designs, templates
- Made For You: AI-suggested pins, recommendations
- GW Labs: Ghostwriter, AI writing, captions
- SmartPin: Smart pin creation from URLs

OTHER:
- Analytics: Stats, insights, performance metrics
- Billing & Settings: Plans, payments, subscriptions
- Extension: Browser extension for scheduling
- Product Dashboard: E-commerce integrations (Shopify, WordPress)
- Communities: Content sharing groups
- Smart.bio: Link in bio pages
- System wide: Unclear or general issue

**Instructions:**
1. Identify the PRIMARY product being discussed (not all mentioned products)
2. If message references a previous conversation without details, classify as "System wide"
3. If genuinely ambiguous, prefer the most specific product mentioned

Respond with JSON: {{"product": "Product Name", "confidence": "high|medium|low", "reason": "brief explanation"}}"""


def extract_product_llm_v3(text: str, client: OpenAI) -> dict:
    """Extract with improved prompt."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You classify Tailwind support messages. Be specific but acknowledge uncertainty. JSON only."},
                {"role": "user", "content": IMPROVED_PROMPT.format(message=text[:2000])},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=150,
        )
        result = json.loads(response.choices[0].message.content)
        product = normalize_product(result.get("product", "System wide"))
        return {
            "product": product,
            "confidence": result.get("confidence", "medium"),
            "method": "llm_v3",
            "reason": result.get("reason", ""),
        }
    except Exception as e:
        print(f"  LLM error: {e}")
        return {"product": "System wide", "confidence": "low", "method": "llm_error", "reason": str(e)}


def normalize_product(product: str) -> str:
    """Normalize to canonical Shortcut product names."""
    mapping = {
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
        "extension": "Extension",
        "browser extension": "Extension",
        "product dashboard": "Product Dashboard",
        "communities": "Communities",
        "smart.bio": "Smart.bio",
        "system wide": "System wide",
        "general": "System wide",
        "unclear": "System wide",
    }
    return mapping.get(product.lower().strip(), product)


def run_extraction_v3():
    """Run iteration 3 extraction."""
    print("=" * 60)
    print("PHASE 5F: ITERATION 3 - Context-Aware Extraction")
    print("=" * 60)

    with open("data/phase5_ground_truth.json") as f:
        data = json.load(f)

    all_convs = data.get("validation_set", []) + data.get("analysis_set", [])
    print(f"\n📊 Conversations: {len(all_convs)}")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results = []
    stats = {"total": len(all_convs), "keyword": 0, "llm": 0, "empty": 0, "low_context": 0}

    for i, conv in enumerate(all_convs, 1):
        conv_id = conv["conversation_id"]
        source_body = clean_html(conv.get("source_body", ""))
        ground_truth = conv.get("product_area")

        print(f"  [{i}/{len(all_convs)}] {conv_id}...", end=" ")

        if not source_body or len(source_body) < 10:
            print("⚠️ Empty")
            results.append({
                "conversation_id": conv_id,
                "extracted_product": "System wide",
                "extraction_method": "empty",
                "confidence": "low",
                "ground_truth": ground_truth,
                "preview": source_body[:100],
            })
            stats["empty"] += 1
            continue

        # Check context sufficiency
        sufficient_context = has_sufficient_context(source_body)

        # Try keywords first
        kw_product, kw_conf = extract_product_keywords_v3(source_body)

        if kw_product and kw_conf == "high":
            print(f"✅ kw → {kw_product}")
            results.append({
                "conversation_id": conv_id,
                "extracted_product": kw_product,
                "extraction_method": "keywords_v3",
                "confidence": kw_conf,
                "ground_truth": ground_truth,
                "preview": source_body[:200],
            })
            stats["keyword"] += 1
        else:
            # LLM fallback
            llm_result = extract_product_llm_v3(source_body, client)
            print(f"🤖 llm → {llm_result['product']} ({llm_result['confidence']})")
            results.append({
                "conversation_id": conv_id,
                "extracted_product": llm_result["product"],
                "extraction_method": llm_result["method"],
                "confidence": llm_result["confidence"],
                "ground_truth": ground_truth,
                "preview": source_body[:200],
                "reason": llm_result.get("reason", ""),
            })
            stats["llm"] += 1

            if not sufficient_context:
                stats["low_context"] += 1

    # Calculate accuracy (exact and family)
    FAMILIES = {
        "scheduling": ["Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop"],
        "ai_creation": ["Create", "Made For You", "GW Labs", "SmartPin", "CoPilot"],
        "analytics": ["Analytics"],
        "billing": ["Billing & Settings"],
        "integrations": ["Extension", "Product Dashboard"],
        "communities": ["Communities"],
        "smart_bio": ["Smart.bio"],
        "other": ["System wide", "Jarvis", "Email", "Ads"],
    }

    def get_family(product):
        for fam, prods in FAMILIES.items():
            if product in prods:
                return fam
        return "unknown"

    valid = [r for r in results if r["extraction_method"] != "empty"]
    exact = sum(1 for r in valid if r["extracted_product"] == r["ground_truth"])
    family = sum(1 for r in valid if get_family(r["extracted_product"]) == get_family(r["ground_truth"]))

    exact_acc = exact / len(valid) * 100
    family_acc = family / len(valid) * 100

    output = {
        "results": results,
        "stats": stats,
        "exact_accuracy": exact_acc,
        "family_accuracy": family_acc,
        "iteration": 3,
    }

    with open("data/phase5_extraction_v3.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n📊 Statistics:")
    print(f"   Keyword matches: {stats['keyword']}")
    print(f"   LLM fallback: {stats['llm']}")
    print(f"   Low context: {stats['low_context']}")
    print(f"   Empty: {stats['empty']}")
    print(f"\n🎯 EXACT ACCURACY: {exact_acc:.1f}% ({exact}/{len(valid)})")
    print(f"🎯 FAMILY ACCURACY: {family_acc:.1f}% ({family}/{len(valid)})")
    print(f"\n💾 Saved to data/phase5_extraction_v3.json")

    return family_acc, output


if __name__ == "__main__":
    accuracy, output = run_extraction_v3()
    print(f"\n{'='*60}")
    if accuracy >= 85:
        print(f"TARGET MET! Family accuracy: {accuracy:.1f}%")
    else:
        print(f"Below target: {accuracy:.1f}% < 85%")
    print(f"{'='*60}")
