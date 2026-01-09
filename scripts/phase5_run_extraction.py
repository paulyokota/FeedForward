#!/usr/bin/env python3
"""
Phase 5B: Run theme extraction on ground truth data.

Extracts product area from each validation conversation to compare against
Shortcut ground truth labels.
"""
import json
import os
import sys
import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()

from openai import OpenAI

# Load vocabulary
VOCAB_PATH = Path(__file__).parent.parent / "config" / "theme_vocabulary.json"
with open(VOCAB_PATH) as f:
    VOCABULARY = json.load(f)


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Clean up whitespace
    clean = ' '.join(clean.split())
    return clean.strip()


def extract_product_area_keywords(text: str) -> Optional[str]:
    """
    Extract product area using keyword matching from vocabulary.

    Returns the product area with the most keyword matches, or None if no matches.
    """
    text_lower = text.lower()

    # Score each product area based on keyword matches
    product_area_scores = {}

    for theme_sig, theme in VOCABULARY.get("themes", {}).items():
        if theme.get("status") != "active":
            continue

        keywords = theme.get("keywords", [])
        product_area = theme.get("product_area", "other")

        # Count keyword matches
        for keyword in keywords:
            if keyword.lower() in text_lower:
                product_area_scores[product_area] = product_area_scores.get(product_area, 0) + 1

    if product_area_scores:
        # Return product area with highest score
        best = max(product_area_scores.items(), key=lambda x: x[1])
        if best[1] >= 1:  # At least 1 keyword match
            return best[0]

    return None


# Product area mapping: FeedForward names -> Shortcut names
PRODUCT_AREA_MAPPING = {
    # FeedForward product_area -> Shortcut product_area equivalents
    "scheduling": ["Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop"],
    "pinterest_publishing": ["Pin Scheduler", "Next Publisher", "Legacy Publisher"],
    "ai_creation": ["Made For You", "GW Labs", "Create", "SmartPin"],
    "analytics": ["Analytics"],
    "billing": ["Billing & Settings"],
    "account": ["Billing & Settings"],  # Account issues often grouped here
    "integrations": ["Extension", "Product Dashboard"],
    "communities": ["Communities"],
    "smart_bio": ["Smart.bio"],
    "other": ["System wide", "Jarvis", "Internal Tracking and Reporting"],
}

# Reverse mapping: Shortcut names -> FeedForward equivalent
SHORTCUT_TO_FEEDFORWARD = {}
for ff_area, sc_areas in PRODUCT_AREA_MAPPING.items():
    for sc_area in sc_areas:
        if sc_area not in SHORTCUT_TO_FEEDFORWARD:
            SHORTCUT_TO_FEEDFORWARD[sc_area] = ff_area


# Simple LLM prompt for product area extraction
PRODUCT_AREA_PROMPT = """Classify this customer support message into ONE product area.

**Message:**
{message}

**Product Areas (choose ONE):**
- scheduling (Pin Scheduler, queue, SmartSchedule, time slots)
- pinterest_publishing (pins, boards, Pinterest connection)
- ai_creation (SmartPin, Ghostwriter, AI-generated content, Create designs)
- analytics (performance, insights, keywords, statistics)
- billing (plans, payments, subscriptions, cancel, upgrade)
- account (login, password, OAuth, connect account)
- integrations (extension, browser, CSV, Shopify, WooCommerce)
- communities (Tailwind Communities)
- smart_bio (Smart.bio, bio link)
- other (doesn't fit any category)

Respond with JSON: {{"product_area": "category_name", "confidence": "high|medium|low"}}"""


def extract_product_area_llm(text: str, client: OpenAI) -> dict:
    """Extract product area using LLM (fallback when keywords don't match)."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You classify customer support messages. Respond with JSON only."},
                {"role": "user", "content": PRODUCT_AREA_PROMPT.format(message=text[:1500])},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=100,
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "product_area": result.get("product_area", "other"),
            "confidence": result.get("confidence", "medium"),
            "method": "llm",
        }
    except Exception as e:
        print(f"  LLM error: {e}")
        return {"product_area": "other", "confidence": "low", "method": "llm_error"}


def run_extraction():
    """Run product area extraction on all validation conversations."""
    print("=" * 60)
    print("PHASE 5B: RUN THEME EXTRACTION")
    print("=" * 60)

    # Load ground truth data
    with open("data/phase5_ground_truth.json") as f:
        data = json.load(f)

    validation_set = data.get("validation_set", [])
    analysis_set = data.get("analysis_set", [])
    all_convs = validation_set + analysis_set

    print(f"\n📊 Conversations to process: {len(all_convs)}")
    print(f"   Validation set: {len(validation_set)}")
    print(f"   Analysis set: {len(analysis_set)}")

    # Initialize OpenAI client for fallback
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results = []
    stats = {
        "total": len(all_convs),
        "keyword_matches": 0,
        "llm_fallback": 0,
        "errors": 0,
    }

    print("\n🔍 Extracting product areas...")

    for i, conv in enumerate(all_convs, 1):
        conv_id = conv["conversation_id"]
        source_body = clean_html(conv.get("source_body", ""))
        ground_truth_pa = conv.get("product_area")  # Shortcut's label

        print(f"  [{i}/{len(all_convs)}] {conv_id}...", end=" ")

        if not source_body or len(source_body) < 10:
            print("⚠️ Empty/short message")
            results.append({
                "conversation_id": conv_id,
                "extracted_product_area": "other",
                "extraction_method": "empty",
                "confidence": "low",
                "ground_truth_product_area": ground_truth_pa,
                "source_body_preview": source_body[:100] if source_body else "",
            })
            stats["errors"] += 1
            continue

        # Try keyword matching first (free, fast)
        keyword_pa = extract_product_area_keywords(source_body)

        if keyword_pa:
            print(f"✅ keywords → {keyword_pa}")
            results.append({
                "conversation_id": conv_id,
                "extracted_product_area": keyword_pa,
                "extraction_method": "keywords",
                "confidence": "medium",
                "ground_truth_product_area": ground_truth_pa,
                "source_body_preview": source_body[:200],
            })
            stats["keyword_matches"] += 1
        else:
            # Fallback to LLM
            llm_result = extract_product_area_llm(source_body, client)
            print(f"🤖 llm → {llm_result['product_area']} ({llm_result['confidence']})")
            results.append({
                "conversation_id": conv_id,
                "extracted_product_area": llm_result["product_area"],
                "extraction_method": llm_result["method"],
                "confidence": llm_result["confidence"],
                "ground_truth_product_area": ground_truth_pa,
                "source_body_preview": source_body[:200],
            })
            stats["llm_fallback"] += 1

    # Save results
    output = {
        "extraction_results": results,
        "statistics": stats,
        "product_area_mapping": PRODUCT_AREA_MAPPING,
        "shortcut_to_feedforward": SHORTCUT_TO_FEEDFORWARD,
    }

    with open("data/phase5_extraction_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n📊 Extraction Statistics:")
    print(f"   Total processed: {stats['total']}")
    print(f"   Keyword matches: {stats['keyword_matches']} ({stats['keyword_matches']/stats['total']*100:.1f}%)")
    print(f"   LLM fallback: {stats['llm_fallback']} ({stats['llm_fallback']/stats['total']*100:.1f}%)")
    print(f"   Errors: {stats['errors']}")

    print(f"\n💾 Saved to data/phase5_extraction_results.json")

    return output


if __name__ == "__main__":
    run_extraction()
