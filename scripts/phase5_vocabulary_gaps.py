#!/usr/bin/env python3
"""
Phase 5D: Identify vocabulary gaps.

Finds Shortcut product areas that aren't well-covered by FeedForward extraction.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# FeedForward extraction categories -> Shortcut product areas mapping
EXTRACTION_TO_SHORTCUT = {
    # Scheduling family
    "scheduling": ["Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop"],
    "pinterest_publishing": ["Pin Scheduler", "Next Publisher", "Legacy Publisher"],
    "pin_scheduler": ["Pin Scheduler"],
    "next_publisher": ["Next Publisher"],
    "legacy_publisher": ["Legacy Publisher"],
    "smartloop": ["SmartLoop"],

    # AI/Creation family
    "ai_creation": ["Made For You", "GW Labs", "Create", "SmartPin", "CoPilot"],
    "create": ["Create"],
    "made_for_you": ["Made For You"],
    "gw_labs": ["GW Labs"],
    "smartpin": ["SmartPin"],
    "copilot": ["CoPilot"],

    # Analytics
    "analytics": ["Analytics"],

    # Billing/Account
    "billing": ["Billing & Settings"],
    "account": ["Billing & Settings"],

    # Integrations
    "integrations": ["Extension", "Product Dashboard"],
    "extension": ["Extension"],
    "product_dashboard": ["Product Dashboard"],

    # Communities
    "communities": ["Communities"],

    # Smart.bio
    "smart_bio": ["Smart.bio"],

    # Other
    "other": ["System wide", "Jarvis", "Internal Tracking and Reporting", "Email", "Ads"],
}


def analyze_vocabulary_gaps():
    """Analyze gaps between FeedForward vocabulary and Shortcut labels."""
    print("=" * 60)
    print("PHASE 5D: IDENTIFY VOCABULARY GAPS")
    print("=" * 60)

    # Load ground truth data
    with open("data/phase5_ground_truth.json") as f:
        gt_data = json.load(f)

    with open("data/phase5_extraction_results.json") as f:
        extraction_data = json.load(f)

    # Build reverse mapping: Shortcut product area -> FeedForward categories that could match
    shortcut_to_ff = defaultdict(list)
    for ff_cat, sc_areas in EXTRACTION_TO_SHORTCUT.items():
        for sc_area in sc_areas:
            shortcut_to_ff[sc_area].append(ff_cat)

    # Count all Shortcut product areas in ground truth
    shortcut_counts = defaultdict(int)
    for conv in gt_data.get("all_conversations", []):
        pa = conv.get("product_area")
        if pa:
            shortcut_counts[pa] += 1

    print(f"\n📊 Shortcut Product Areas in Ground Truth:")
    for pa, count in sorted(shortcut_counts.items(), key=lambda x: -x[1]):
        coverage = "✅ Covered" if pa in shortcut_to_ff else "❌ NOT COVERED"
        print(f"   {pa}: {count} ({coverage})")

    # Identify gaps: Shortcut areas with no FeedForward mapping
    gaps = []
    for pa, count in shortcut_counts.items():
        if pa not in shortcut_to_ff:
            gaps.append({
                "shortcut_area": pa,
                "count": count,
                "priority": "high" if count >= 10 else "medium" if count >= 5 else "low",
            })

    gaps.sort(key=lambda x: -x["count"])

    print(f"\n❌ Vocabulary Gaps Found: {len(gaps)}")
    for gap in gaps:
        print(f"   {gap['shortcut_area']}: {gap['count']} occurrences ({gap['priority']} priority)")

    # Analyze mismatch patterns to find semantic gaps
    results = extraction_data.get("extraction_results", [])
    mismatch_patterns = defaultdict(lambda: {"count": 0, "examples": []})

    for r in results:
        extracted = r.get("extracted_product_area", "")
        ground_truth = r.get("ground_truth_product_area", "")

        if not ground_truth:
            continue

        # Check if it's a match using our mapping
        mapped = EXTRACTION_TO_SHORTCUT.get(extracted.lower(), [])
        if ground_truth not in mapped:
            pattern = f"{extracted} -> {ground_truth}"
            mismatch_patterns[pattern]["count"] += 1
            if len(mismatch_patterns[pattern]["examples"]) < 3:
                mismatch_patterns[pattern]["examples"].append({
                    "conversation_id": r.get("conversation_id"),
                    "preview": r.get("source_body_preview", "")[:100],
                })

    # Sort patterns by frequency
    sorted_patterns = sorted(mismatch_patterns.items(), key=lambda x: -x[1]["count"])

    print(f"\n📊 Most Common Mismatch Patterns:")
    for pattern, data in sorted_patterns[:15]:
        print(f"   {pattern}: {data['count']} times")

    # Generate recommendations
    recommendations = []

    # 1. Gaps - areas not in our mapping at all
    for gap in gaps:
        recommendations.append({
            "type": "new_mapping",
            "shortcut_area": gap["shortcut_area"],
            "occurrences": gap["count"],
            "priority": gap["priority"],
            "recommendation": f"Add '{gap['shortcut_area']}' to FeedForward vocabulary",
        })

    # 2. Frequent mismatches - might need mapping fixes or LLM prompt improvement
    for pattern, data in sorted_patterns[:10]:
        if data["count"] >= 3:
            extracted, ground_truth = pattern.split(" -> ")
            recommendations.append({
                "type": "mapping_fix",
                "pattern": pattern,
                "occurrences": data["count"],
                "priority": "high" if data["count"] >= 5 else "medium",
                "recommendation": f"Consider mapping '{extracted}' to include '{ground_truth}'",
                "examples": data["examples"],
            })

    # Generate report
    report = generate_gap_report(gaps, sorted_patterns, recommendations, shortcut_counts, shortcut_to_ff)

    with open("prompts/phase5_vocabulary_gaps.md", "w") as f:
        f.write(report)

    print(f"\n📝 Saved to prompts/phase5_vocabulary_gaps.md")

    # Save detailed data
    output = {
        "gaps": gaps,
        "mismatch_patterns": {k: v for k, v in sorted_patterns},
        "recommendations": recommendations,
        "shortcut_counts": dict(shortcut_counts),
        "generated_at": datetime.now().isoformat(),
    }

    with open("data/phase5_vocabulary_gaps.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"💾 Saved to data/phase5_vocabulary_gaps.json")

    return len(gaps), recommendations


def generate_gap_report(gaps, patterns, recommendations, shortcut_counts, shortcut_to_ff):
    """Generate vocabulary gaps markdown report."""

    high_priority = [g for g in gaps if g["priority"] == "high"]
    medium_priority = [g for g in gaps if g["priority"] == "medium"]
    low_priority = [g for g in gaps if g["priority"] == "low"]

    md = f"""# Phase 5D: Vocabulary Gap Analysis

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Vocabulary Gaps | {len(gaps)} |
| High Priority Gaps (10+ occurrences) | {len(high_priority)} |
| Medium Priority Gaps (5-9 occurrences) | {len(medium_priority)} |
| Low Priority Gaps (<5 occurrences) | {len(low_priority)} |

---

## Shortcut Product Area Coverage

| Product Area | Count | Coverage Status |
|--------------|-------|-----------------|
"""
    for pa, count in sorted(shortcut_counts.items(), key=lambda x: -x[1]):
        status = "Covered" if pa in shortcut_to_ff else "**GAP**"
        ff_cats = ", ".join(shortcut_to_ff.get(pa, [])) if pa in shortcut_to_ff else "-"
        md += f"| {pa} | {count} | {status} |\n"

    if gaps:
        md += f"""
---

## Vocabulary Gaps (Shortcut areas not in FeedForward)

"""
        if high_priority:
            md += "### High Priority (10+ occurrences)\n\n"
            for g in high_priority:
                md += f"- **{g['shortcut_area']}**: {g['count']} occurrences\n"
            md += "\n"

        if medium_priority:
            md += "### Medium Priority (5-9 occurrences)\n\n"
            for g in medium_priority:
                md += f"- **{g['shortcut_area']}**: {g['count']} occurrences\n"
            md += "\n"

        if low_priority:
            md += "### Low Priority (<5 occurrences)\n\n"
            for g in low_priority:
                md += f"- {g['shortcut_area']}: {g['count']} occurrences\n"
            md += "\n"
    else:
        md += """
---

## Vocabulary Gaps

**No gaps found!** All Shortcut product areas have FeedForward mappings.

"""

    md += f"""---

## Most Common Mismatch Patterns

These patterns show where FeedForward extraction differs from Shortcut labels:

| Extracted -> Ground Truth | Count |
|---------------------------|-------|
"""
    for pattern, data in patterns[:15]:
        md += f"| {pattern} | {data['count']} |\n"

    md += """
---

## Recommendations

"""
    if not recommendations:
        md += "No specific recommendations - vocabulary coverage is complete.\n"
    else:
        for i, rec in enumerate(recommendations[:15], 1):
            if rec["type"] == "new_mapping":
                md += f"""### {i}. Add New Mapping: {rec['shortcut_area']}
- **Occurrences**: {rec['occurrences']}
- **Priority**: {rec['priority']}
- **Action**: Add `{rec['shortcut_area'].lower().replace(' ', '_').replace('.', '')}` to FeedForward vocabulary

"""
            else:
                md += f"""### {i}. Fix Mapping: {rec['pattern']}
- **Occurrences**: {rec['occurrences']}
- **Priority**: {rec['priority']}
- **Action**: {rec['recommendation']}

"""

    md += """---

## Root Cause Analysis

Based on the mismatch patterns, the main accuracy issues stem from:

1. **Granularity Mismatch**: FeedForward uses broad categories (scheduling, ai_creation) while Shortcut uses specific product names (Pin Scheduler, Create, Made For You)

2. **Ambiguous Messages**: Short messages like "help" or "not working" lack context to determine the specific product

3. **Multi-Product Conversations**: Some conversations mention multiple products, making single-label classification difficult

4. **Keyword False Positives**: Keyword matching sometimes picks wrong category (e.g., "account" keyword in Pin Scheduler context)

## Next Steps

1. If gaps exist: Add new vocabulary entries for uncovered Shortcut areas
2. Consider training extraction to output Shortcut-specific labels instead of broad FeedForward categories
3. Improve LLM prompt to be aware of specific Tailwind product names
"""

    return md


if __name__ == "__main__":
    num_gaps, recommendations = analyze_vocabulary_gaps()
    print(f"\n{'='*60}")
    print(f"PHASE 5D COMPLETE - Found {num_gaps} vocabulary gaps")
    print(f"{'='*60}")
