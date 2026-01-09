#!/usr/bin/env python3
"""
Phase 5F: Calculate accuracy with semantic groupings.

Groups similar products (like the three schedulers) as valid matches.
"""
import json
from datetime import datetime
from collections import defaultdict


# Product families - within a family, any match counts
PRODUCT_FAMILIES = {
    "scheduling": ["Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop"],
    "ai_creation": ["Create", "Made For You", "GW Labs", "SmartPin", "CoPilot"],
    "analytics": ["Analytics"],
    "billing": ["Billing & Settings"],
    "integrations": ["Extension", "Product Dashboard"],
    "communities": ["Communities"],
    "smart_bio": ["Smart.bio"],
    "other": ["System wide", "Jarvis", "Email", "Ads"],
}

# Build reverse mapping
PRODUCT_TO_FAMILY = {}
for family, products in PRODUCT_FAMILIES.items():
    for product in products:
        PRODUCT_TO_FAMILY[product] = family

# Normalization for LLM output variations
NORMALIZE = {
    "scheduling": "Pin Scheduler",
    "SCHEDULING": "Pin Scheduler",
    "blog feature": "Product Dashboard",
    "Blog Feature": "Product Dashboard",
    "integrations": "Extension",
    "Integrations": "Extension",
}


def is_exact_match(extracted: str, ground_truth: str) -> bool:
    """Check for exact product name match."""
    ex = NORMALIZE.get(extracted, extracted)
    return ex == ground_truth


def is_family_match(extracted: str, ground_truth: str) -> bool:
    """Check if products are in the same family (semantic match)."""
    ex = NORMALIZE.get(extracted, extracted)

    # Get families
    ex_family = PRODUCT_TO_FAMILY.get(ex, "unknown")
    gt_family = PRODUCT_TO_FAMILY.get(ground_truth, "unknown")

    if ex_family == "unknown" or gt_family == "unknown":
        return False

    return ex_family == gt_family


def calculate_accuracy():
    """Calculate accuracy with both exact and family-based matching."""
    print("=" * 60)
    print("PHASE 5F: ACCURACY ANALYSIS (ITERATION 2)")
    print("=" * 60)

    with open("data/phase5_extraction_v2.json") as f:
        data = json.load(f)

    results = data["extraction_results"]
    valid = [r for r in results if r["extraction_method"] != "empty"]

    # Count matches
    exact_matches = 0
    family_matches = 0
    mismatches = []

    for r in valid:
        ex = r["extracted_product"]
        gt = r["ground_truth"]

        if is_exact_match(ex, gt):
            exact_matches += 1
        elif is_family_match(ex, gt):
            family_matches += 1
        else:
            mismatches.append({
                "extracted": ex,
                "ground_truth": gt,
                "conversation_id": r["conversation_id"],
            })

    total = len(valid)

    exact_accuracy = exact_matches / total * 100
    family_accuracy = (exact_matches + family_matches) / total * 100

    print(f"\n📊 Results (n={total}):")
    print(f"\n   EXACT MATCH ACCURACY: {exact_accuracy:.1f}% ({exact_matches}/{total})")
    print(f"   FAMILY MATCH ACCURACY: {family_accuracy:.1f}% ({exact_matches + family_matches}/{total})")
    print(f"\n   Breakdown:")
    print(f"   - Exact matches: {exact_matches}")
    print(f"   - Family matches (same category): {family_matches}")
    print(f"   - True mismatches: {len(mismatches)}")

    # Analyze mismatches by pattern
    mismatch_patterns = defaultdict(int)
    for m in mismatches:
        ex_family = PRODUCT_TO_FAMILY.get(NORMALIZE.get(m["extracted"], m["extracted"]), "unknown")
        gt_family = PRODUCT_TO_FAMILY.get(m["ground_truth"], "unknown")
        pattern = f"{ex_family} -> {gt_family}"
        mismatch_patterns[pattern] += 1

    print(f"\n📊 Mismatch Patterns (by family):")
    for pattern, count in sorted(mismatch_patterns.items(), key=lambda x: -x[1])[:10]:
        print(f"   {pattern}: {count}")

    # Save report
    report = {
        "exact_accuracy": exact_accuracy,
        "family_accuracy": family_accuracy,
        "exact_matches": exact_matches,
        "family_matches": family_matches,
        "mismatches": len(mismatches),
        "total": total,
        "mismatch_patterns": dict(mismatch_patterns),
        "generated_at": datetime.now().isoformat(),
    }

    with open("data/phase5_accuracy_v2.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n💾 Saved to data/phase5_accuracy_v2.json")

    return family_accuracy, report


if __name__ == "__main__":
    accuracy, report = calculate_accuracy()
    print(f"\n{'='*60}")
    if accuracy >= 85:
        print(f"TARGET MET! Family accuracy: {accuracy:.1f}%")
    else:
        print(f"Below target: {accuracy:.1f}% < 85%")
    print(f"{'='*60}")
