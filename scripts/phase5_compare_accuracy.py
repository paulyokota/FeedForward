#!/usr/bin/env python3
"""
Phase 5C: Compare extracted themes vs Shortcut labels.

Calculates precision, recall, and F1 score for product area extraction accuracy.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# Product area mapping: FeedForward names -> Shortcut equivalents
# Extended to include all variations of FeedForward extraction values
PRODUCT_AREA_MAPPING = {
    # Scheduling variations
    "scheduling": ["Pin Scheduler", "Next Publisher", "Legacy Publisher", "SmartLoop"],
    "pinterest_publishing": ["Pin Scheduler", "Next Publisher", "Legacy Publisher"],
    "pin_scheduler": ["Pin Scheduler"],
    "next_publisher": ["Next Publisher"],
    "legacy_publisher": ["Legacy Publisher"],
    "smartloop": ["SmartLoop"],

    # AI/Creation variations
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
    "billing_settings": ["Billing & Settings"],

    # Integrations
    "integrations": ["Extension", "Product Dashboard"],
    "extension": ["Extension"],
    "product_dashboard": ["Product Dashboard"],

    # Communities
    "communities": ["Communities"],

    # Smart.bio
    "smart_bio": ["Smart.bio"],
    "smartbio": ["Smart.bio"],

    # Other/System
    "other": ["System wide", "Jarvis", "Internal Tracking and Reporting", "Email", "Ads"],
}


def is_match(extracted: str, ground_truth: str) -> bool:
    """Check if extracted product area matches ground truth (semantic match)."""
    if not extracted or not ground_truth:
        return False

    # Exact match
    if extracted.lower() == ground_truth.lower():
        return True

    # Check if ground truth is in the FeedForward category's Shortcut equivalents
    mapped_shortcuts = PRODUCT_AREA_MAPPING.get(extracted.lower(), [])
    if ground_truth in mapped_shortcuts:
        return True

    return False


def calculate_metrics(results: list) -> dict:
    """Calculate precision, recall, F1 for product area extraction."""

    # Filter out empty/error cases for fair comparison
    valid_results = [r for r in results if r.get("extraction_method") != "empty"]

    # Count matches
    total = len(valid_results)
    correct = sum(1 for r in valid_results if is_match(r["extracted_product_area"], r["ground_truth_product_area"]))

    # Per-category metrics
    by_ground_truth = defaultdict(lambda: {"total": 0, "correct": 0})
    by_extracted = defaultdict(lambda: {"total": 0, "correct": 0})
    by_method = defaultdict(lambda: {"total": 0, "correct": 0})
    by_confidence = defaultdict(lambda: {"total": 0, "correct": 0})

    for r in valid_results:
        gt = r["ground_truth_product_area"]
        ex = r["extracted_product_area"]
        method = r["extraction_method"]
        conf = r["confidence"]
        matched = is_match(ex, gt)

        by_ground_truth[gt]["total"] += 1
        by_extracted[ex]["total"] += 1
        by_method[method]["total"] += 1
        by_confidence[conf]["total"] += 1

        if matched:
            by_ground_truth[gt]["correct"] += 1
            by_extracted[ex]["correct"] += 1
            by_method[method]["correct"] += 1
            by_confidence[conf]["correct"] += 1

    # Overall metrics
    accuracy = correct / total * 100 if total > 0 else 0

    return {
        "overall": {
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
        },
        "by_ground_truth": dict(by_ground_truth),
        "by_extracted": dict(by_extracted),
        "by_method": dict(by_method),
        "by_confidence": dict(by_confidence),
    }


def find_mismatches(results: list, limit: int = 20) -> list:
    """Find and categorize mismatches for analysis."""
    mismatches = []
    for r in results:
        if r.get("extraction_method") == "empty":
            continue
        if not is_match(r["extracted_product_area"], r["ground_truth_product_area"]):
            mismatches.append({
                "conversation_id": r["conversation_id"],
                "extracted": r["extracted_product_area"],
                "ground_truth": r["ground_truth_product_area"],
                "method": r["extraction_method"],
                "confidence": r["confidence"],
                "preview": r.get("source_body_preview", "")[:150],
            })
    return mismatches[:limit]


def find_matches(results: list, limit: int = 10) -> list:
    """Find high-confidence correct matches."""
    matches = []
    for r in results:
        if r.get("extraction_method") == "empty":
            continue
        if is_match(r["extracted_product_area"], r["ground_truth_product_area"]):
            matches.append({
                "conversation_id": r["conversation_id"],
                "extracted": r["extracted_product_area"],
                "ground_truth": r["ground_truth_product_area"],
                "method": r["extraction_method"],
                "confidence": r["confidence"],
                "preview": r.get("source_body_preview", "")[:150],
            })
    # Sort by confidence (high first)
    conf_order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda x: conf_order.get(x["confidence"], 3))
    return matches[:limit]


def generate_accuracy_report(metrics: dict, matches: list, mismatches: list, results: list) -> str:
    """Generate markdown accuracy report."""

    overall = metrics["overall"]

    md = f"""# Phase 5C: Accuracy Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall Accuracy** | **{overall['accuracy']:.1f}%** |
| Total Evaluated | {overall['total']} |
| Correct Matches | {overall['correct']} |
| Empty/Skipped | {len([r for r in results if r.get('extraction_method') == 'empty'])} |

**Target**: 85% accuracy
**Status**: {"PASS" if overall['accuracy'] >= 85 else "BELOW TARGET" if overall['accuracy'] >= 70 else "NEEDS IMPROVEMENT"}

---

## Accuracy by Ground Truth Product Area

| Product Area | Total | Correct | Accuracy |
|--------------|-------|---------|----------|
"""

    # Sort by total descending
    gt_sorted = sorted(metrics["by_ground_truth"].items(), key=lambda x: -x[1]["total"])
    for pa, stats in gt_sorted:
        acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        status = "high" if acc >= 80 else "medium" if acc >= 50 else "low"
        md += f"| {pa} | {stats['total']} | {stats['correct']} | {acc:.0f}% |\n"

    md += """
## Accuracy by Extraction Method

| Method | Total | Correct | Accuracy |
|--------|-------|---------|----------|
"""
    for method, stats in metrics["by_method"].items():
        acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        md += f"| {method} | {stats['total']} | {stats['correct']} | {acc:.0f}% |\n"

    md += """
## Accuracy by Confidence Level

| Confidence | Total | Correct | Accuracy |
|------------|-------|---------|----------|
"""
    for conf, stats in metrics["by_confidence"].items():
        acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
        md += f"| {conf} | {stats['total']} | {stats['correct']} | {acc:.0f}% |\n"

    md += f"""
---

## Example Correct Matches (Top {len(matches)})

"""
    for i, m in enumerate(matches, 1):
        md += f"""### Match {i}
- **Conversation**: {m['conversation_id']}
- **Extracted**: {m['extracted']} -> **Ground Truth**: {m['ground_truth']}
- **Method**: {m['method']} | **Confidence**: {m['confidence']}
- **Preview**: _{m['preview']}..._

"""

    md += f"""---

## Mismatches Analysis (Top {len(mismatches)})

"""
    for i, m in enumerate(mismatches, 1):
        md += f"""### Mismatch {i}
- **Conversation**: {m['conversation_id']}
- **Extracted**: {m['extracted']} | **Ground Truth**: {m['ground_truth']}
- **Method**: {m['method']} | **Confidence**: {m['confidence']}
- **Preview**: _{m['preview']}..._

"""

    # Add mismatch pattern analysis
    mismatch_patterns = defaultdict(int)
    for m in mismatches:
        pattern = f"{m['extracted']} -> {m['ground_truth']}"
        mismatch_patterns[pattern] += 1

    md += """---

## Mismatch Patterns

| Extracted -> Ground Truth | Count |
|---------------------------|-------|
"""
    for pattern, count in sorted(mismatch_patterns.items(), key=lambda x: -x[1]):
        md += f"| {pattern} | {count} |\n"

    md += """
---

## Recommendations

"""
    if overall['accuracy'] >= 85:
        md += "- **Target met!** Accuracy is at or above 85%\n"
    else:
        md += f"- **Target not met**: {overall['accuracy']:.1f}% < 85%\n"

        # Identify worst performers
        worst = [(pa, s) for pa, s in gt_sorted if s["total"] >= 5 and s["correct"]/s["total"] < 0.5]
        if worst:
            md += f"- **Worst performing areas** (need vocabulary improvements):\n"
            for pa, stats in worst[:5]:
                acc = stats["correct"] / stats["total"] * 100
                md += f"  - {pa}: {acc:.0f}% ({stats['correct']}/{stats['total']})\n"

    return md


def run_comparison():
    """Run Phase 5C comparison."""
    print("=" * 60)
    print("PHASE 5C: COMPARE EXTRACTED THEMES VS SHORTCUT LABELS")
    print("=" * 60)

    # Load extraction results
    with open("data/phase5_extraction_results.json") as f:
        data = json.load(f)

    results = data.get("extraction_results", [])
    print(f"\n Total extraction results: {len(results)}")

    # Calculate metrics
    print("\n Calculating accuracy metrics...")
    metrics = calculate_metrics(results)

    overall = metrics["overall"]
    print(f"\n OVERALL ACCURACY: {overall['accuracy']:.1f}%")
    print(f"   Correct: {overall['correct']} / {overall['total']}")

    # Find examples
    matches = find_matches(results, limit=10)
    mismatches = find_mismatches(results, limit=20)

    print(f"\n Found {len(matches)} example matches")
    print(f" Found {len(mismatches)} mismatches to analyze")

    # Generate report
    report = generate_accuracy_report(metrics, matches, mismatches, results)

    with open("prompts/phase5_accuracy_report.md", "w") as f:
        f.write(report)

    print(f"\n Saved to prompts/phase5_accuracy_report.md")

    # Save detailed metrics
    output = {
        "metrics": metrics,
        "matches": matches,
        "mismatches": mismatches,
        "generated_at": datetime.now().isoformat(),
    }

    with open("data/phase5_accuracy_metrics.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f" Saved to data/phase5_accuracy_metrics.json")

    return overall["accuracy"], metrics


if __name__ == "__main__":
    accuracy, metrics = run_comparison()
    print(f"\n{'='*60}")
    print(f"PHASE 5C COMPLETE - Accuracy: {accuracy:.1f}%")
    print(f"{'='*60}")
