#!/usr/bin/env python3
"""
Validate story grouping accuracy against human-labeled ground truth.

Compares our pipeline's groupings (issue_signature after PM review)
against human groupings (story_id from Shortcut).

Metrics:
- Grouping Precision: % of our groups that match a human group
- Grouping Recall: % of human groups that we correctly identified
- Pairwise Precision: % of conversation pairs we grouped that humans also grouped
- Pairwise Recall: % of conversation pairs humans grouped that we also grouped
"""
import json
import os
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI

# Import our modules
from theme_extractor import ThemeExtractor
from confidence_scorer import ConfidenceScorer

# Constants
GROUND_TRUTH_FILE = Path(__file__).parent.parent / "data" / "story_id_ground_truth.json"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "validation"
MIN_GROUP_SIZE = 3
CATCH_ALL_STORY_ID = "66666"  # Exclude this catch-all group

# PM Review prompt (same as run_pm_review_all.py)
PRODUCT_CONTEXT = """
Tailwind is a social media scheduling and marketing tool focused on Pinterest and Instagram.

Key product areas:
- Pinterest Publishing: Pin scheduling, Smart Schedule, board management
- Instagram Publishing: Post scheduling, visual planning, link in bio
- Tailwind Create: AI-powered design tool for creating pins and posts
- Ghostwriter: AI tool for generating pin titles and descriptions
- Analytics: Performance tracking and reporting
- Communities: Collaborative sharing groups (legacy feature)
- Billing: Subscription management, plans, payments
"""

PM_REVIEW_PROMPT = """You are a PM reviewing tickets before sprint planning for Tailwind, a social media scheduling tool.

## Product Context
{product_context}

## Proposed Grouping
Signature: {signature}
Conversations: {count}

{conversations}

## Your Task
Would you put ALL of these in ONE implementation ticket? Consider:
1. Same root cause? (Would one fix address all of these?)
2. Same implementation surface? (Same code area, same team?)
3. Same user goal? (Users trying to accomplish the same thing?)

## Response Format
Return valid JSON only:
{{
  "decision": "keep_together" or "split",
  "reasoning": "Brief explanation",
  "sub_groups": [
    {{
      "suggested_signature": "more_specific_name",
      "conversation_ids": ["id1", "id2"],
      "rationale": "Why these belong together"
    }}
  ]
}}

If decision is "keep_together", sub_groups should be empty array.
"""


def load_ground_truth() -> tuple[dict[str, list[dict]], list[dict]]:
    """
    Load ground truth data.

    Returns:
        (human_groups, all_conversations)
        - human_groups: story_id -> list of conversations
        - all_conversations: flat list of all conversations
    """
    with open(GROUND_TRUTH_FILE) as f:
        data = json.load(f)

    # Filter out catch-all and get usable groups (3+ conversations)
    groups = data["groups_by_story_id"]
    usable_groups = {
        k: v for k, v in groups.items()
        if k != CATCH_ALL_STORY_ID and len(v) >= MIN_GROUP_SIZE
    }

    # Flatten to get all conversations
    all_convos = []
    for story_id, convos in usable_groups.items():
        for conv in convos:
            conv["story_id"] = story_id  # Ensure story_id is set
            all_convos.append(conv)

    return usable_groups, all_convos


class SimpleConversation:
    """Minimal conversation object for theme extraction."""

    def __init__(self, conv_dict: dict):
        self.id = conv_dict.get("conversation_id", "")
        self.source_body = conv_dict.get("source_body", "")
        self.source_url = conv_dict.get("source_url")
        self.created_at = conv_dict.get("created_at")

        # Default classification values (required by ThemeExtractor)
        self.issue_type = "bug_report"
        self.sentiment = "neutral"
        self.priority = "medium"
        self.churn_risk = False


def run_theme_extraction(conversations: list[dict], verbose: bool = False) -> list[dict]:
    """Run theme extraction on conversations."""
    extractor = ThemeExtractor()
    results = []

    for i, conv in enumerate(conversations):
        if verbose and i % 10 == 0:
            print(f"  Extracting {i+1}/{len(conversations)}...")

        # Build conversation object for extractor
        conv_obj = SimpleConversation(conv)

        try:
            theme = extractor.extract(conv_obj, strict_mode=True)
            result = {
                "conversation_id": conv["conversation_id"],
                "story_id": conv["story_id"],
                "issue_signature": theme.issue_signature,
                "product_area": theme.product_area,
                "component": theme.component,
                "user_intent": theme.user_intent,
                "symptoms": theme.symptoms,
                "affected_flow": theme.affected_flow,
                "excerpt": conv.get("source_body", "")[:300],
            }
            results.append(result)
        except Exception as e:
            if verbose:
                print(f"    ERROR extracting {conv['conversation_id']}: {e}")
            # Still include with minimal data
            results.append({
                "conversation_id": conv["conversation_id"],
                "story_id": conv["story_id"],
                "issue_signature": "extraction_error",
                "error": str(e)
            })

    return results


def group_by_signature(extractions: list[dict]) -> dict[str, list[dict]]:
    """Group extraction results by issue_signature."""
    groups = defaultdict(list)
    for ext in extractions:
        sig = ext.get("issue_signature", "unknown")
        groups[sig].append(ext)
    return dict(groups)


def format_conversations_for_pm(conversations: list[dict], max_convos: int = 30) -> str:
    """Format conversations for PM review prompt."""
    sample = conversations[:max_convos]
    lines = []

    for i, conv in enumerate(sample, 1):
        lines.append(f"### Conversation {i} (ID: {conv['conversation_id']})")
        lines.append(f"- User Intent: {conv.get('user_intent', 'N/A')}")
        lines.append(f"- Symptoms: {', '.join(conv.get('symptoms', [])) or 'N/A'}")
        lines.append(f"- Affected Flow: {conv.get('affected_flow', 'N/A')}")

        # Use excerpt or source_body
        text = conv.get("excerpt") or conv.get("source_body", "N/A")
        if text:
            text = text[:200].replace("<p>", "").replace("</p>", "")
        lines.append(f"- Excerpt: {text}...")
        lines.append("")

    if len(conversations) > max_convos:
        lines.append(f"... and {len(conversations) - max_convos} more conversations")

    return "\n".join(lines)


def run_pm_review(client: OpenAI, signature: str, conversations: list[dict]) -> dict:
    """Run PM review on a single group."""
    prompt = PM_REVIEW_PROMPT.format(
        product_context=PRODUCT_CONTEXT,
        signature=signature,
        count=len(conversations),
        conversations=format_conversations_for_pm(conversations)
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)


def run_pm_review_all(groups: dict[str, list[dict]], verbose: bool = False) -> dict[str, list[dict]]:
    """
    Run PM review on all groups and return final groupings.

    Returns dict of final_signature -> list of conversations
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    final_groups = {}

    for sig, convos in groups.items():
        if len(convos) < MIN_GROUP_SIZE:
            # Under-sized groups become orphans, skip for now
            continue

        if verbose:
            print(f"  PM reviewing {sig} ({len(convos)} convos)...")

        try:
            result = run_pm_review(client, sig, convos)

            if result.get("decision") == "keep_together":
                final_groups[sig] = convos
                if verbose:
                    print(f"    -> KEEP")
            else:
                # Split into sub-groups
                sub_groups = result.get("sub_groups", [])
                if verbose:
                    print(f"    -> SPLIT into {len(sub_groups)} sub-groups")

                # Map conversation IDs to conversations
                conv_by_id = {c["conversation_id"]: c for c in convos}

                for sg in sub_groups:
                    sub_sig = sg.get("suggested_signature", f"{sig}_sub")
                    sub_conv_ids = sg.get("conversation_ids", [])
                    sub_convos = [conv_by_id[cid] for cid in sub_conv_ids if cid in conv_by_id]

                    if len(sub_convos) >= MIN_GROUP_SIZE:
                        final_groups[sub_sig] = sub_convos
                    # Smaller sub-groups become orphans

        except Exception as e:
            print(f"    ERROR: {e}")
            # Keep original group on error
            final_groups[sig] = convos

    return final_groups


def get_pairs(group: list[dict], id_field: str = "conversation_id") -> set[tuple[str, str]]:
    """Get all pairs of conversation IDs in a group."""
    ids = [c[id_field] for c in group]
    return {tuple(sorted([a, b])) for a, b in combinations(ids, 2)}


def calculate_metrics(
    our_groups: dict[str, list[dict]],
    human_groups: dict[str, list[dict]]
) -> dict:
    """
    Calculate precision/recall metrics.

    Pairwise metrics: Did we pair the same conversations humans did?
    """
    # Get all pairs from our groupings
    our_pairs = set()
    for convos in our_groups.values():
        our_pairs.update(get_pairs(convos))

    # Get all pairs from human groupings
    human_pairs = set()
    for convos in human_groups.values():
        human_pairs.update(get_pairs(convos))

    # Calculate overlap
    correct_pairs = our_pairs & human_pairs

    # Pairwise metrics
    pairwise_precision = len(correct_pairs) / len(our_pairs) if our_pairs else 0
    pairwise_recall = len(correct_pairs) / len(human_pairs) if human_pairs else 0
    pairwise_f1 = (
        2 * pairwise_precision * pairwise_recall / (pairwise_precision + pairwise_recall)
        if (pairwise_precision + pairwise_recall) > 0 else 0
    )

    return {
        "our_groups": len(our_groups),
        "human_groups": len(human_groups),
        "our_pairs": len(our_pairs),
        "human_pairs": len(human_pairs),
        "correct_pairs": len(correct_pairs),
        "pairwise_precision": round(pairwise_precision, 3),
        "pairwise_recall": round(pairwise_recall, 3),
        "pairwise_f1": round(pairwise_f1, 3),
    }


def analyze_group_mapping(
    our_groups: dict[str, list[dict]],
    human_groups: dict[str, list[dict]]
) -> list[dict]:
    """Analyze how our groups map to human groups."""
    analysis = []

    for our_sig, our_convos in our_groups.items():
        # Which human groups do these conversations belong to?
        story_ids = [c["story_id"] for c in our_convos]
        story_id_counts = defaultdict(int)
        for sid in story_ids:
            story_id_counts[sid] += 1

        # Calculate purity (% from dominant story_id)
        dominant_story = max(story_id_counts.items(), key=lambda x: x[1])
        purity = dominant_story[1] / len(our_convos)

        analysis.append({
            "our_signature": our_sig,
            "our_count": len(our_convos),
            "story_id_distribution": dict(story_id_counts),
            "dominant_story_id": dominant_story[0],
            "purity": round(purity, 3),
            "is_pure": purity == 1.0,
        })

    return analysis


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate grouping accuracy against ground truth")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print progress")
    parser.add_argument("--skip-extraction", action="store_true",
                       help="Skip extraction, load from previous run")
    parser.add_argument("--skip-pm-review", action="store_true",
                       help="Skip PM review, use signature groups directly")
    args = parser.parse_args()

    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Step 1: Load ground truth
    print("Loading ground truth...")
    human_groups, all_convos = load_ground_truth()
    print(f"  {len(human_groups)} human groups, {len(all_convos)} conversations")

    # Step 2: Run theme extraction (or load from cache)
    extraction_file = OUTPUT_DIR / "extraction_results.json"

    if args.skip_extraction and extraction_file.exists():
        print("Loading cached extraction results...")
        with open(extraction_file) as f:
            extractions = json.load(f)
    else:
        print("Running theme extraction...")
        extractions = run_theme_extraction(all_convos, verbose=args.verbose)

        # Save for reuse
        with open(extraction_file, "w") as f:
            json.dump(extractions, f, indent=2)
        print(f"  Saved to {extraction_file}")

    print(f"  {len(extractions)} conversations extracted")

    # Step 3: Group by signature
    print("\nGrouping by issue_signature...")
    signature_groups = group_by_signature(extractions)
    print(f"  {len(signature_groups)} unique signatures")

    # Show distribution
    sizes = sorted([len(v) for v in signature_groups.values()], reverse=True)
    print(f"  Group sizes: {sizes[:15]}...")

    # Step 4: Run PM review (or skip)
    if args.skip_pm_review:
        print("\nSkipping PM review, using signature groups directly...")
        # Filter to MIN_GROUP_SIZE
        final_groups = {k: v for k, v in signature_groups.items() if len(v) >= MIN_GROUP_SIZE}
    else:
        print("\nRunning PM review...")
        final_groups = run_pm_review_all(signature_groups, verbose=args.verbose)

        # Save PM review results
        pm_results_file = OUTPUT_DIR / "pm_review_results.json"
        with open(pm_results_file, "w") as f:
            json.dump({k: [c["conversation_id"] for c in v] for k, v in final_groups.items()}, f, indent=2)

    print(f"  {len(final_groups)} final groups after PM review")

    # Step 5: Calculate metrics
    print("\n" + "=" * 60)
    print("VALIDATION METRICS")
    print("=" * 60)

    metrics = calculate_metrics(final_groups, human_groups)

    print(f"\nGroup Counts:")
    print(f"  Our groups: {metrics['our_groups']}")
    print(f"  Human groups: {metrics['human_groups']}")

    print(f"\nPairwise Metrics:")
    print(f"  Our pairs: {metrics['our_pairs']}")
    print(f"  Human pairs: {metrics['human_pairs']}")
    print(f"  Correct pairs: {metrics['correct_pairs']}")
    print(f"  Precision: {metrics['pairwise_precision']:.1%}")
    print(f"  Recall: {metrics['pairwise_recall']:.1%}")
    print(f"  F1: {metrics['pairwise_f1']:.1%}")

    # Step 6: Analyze group mapping
    print("\n" + "=" * 60)
    print("GROUP PURITY ANALYSIS")
    print("=" * 60)

    analysis = analyze_group_mapping(final_groups, human_groups)

    pure_groups = [a for a in analysis if a["is_pure"]]
    print(f"\nPure groups (100% from one story_id): {len(pure_groups)} / {len(analysis)}")

    print("\nGroup details:")
    for a in sorted(analysis, key=lambda x: -x["purity"]):
        purity_str = f"{a['purity']:.0%}"
        dist_str = ", ".join(f"{k}:{v}" for k, v in a["story_id_distribution"].items())
        print(f"  {a['our_signature'][:40]:<40} | {a['our_count']:>3} convos | {purity_str:>4} pure | {dist_str}")

    # Save full results
    results_file = OUTPUT_DIR / "validation_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "metrics": metrics,
            "group_analysis": analysis,
            "config": {
                "min_group_size": MIN_GROUP_SIZE,
                "skip_pm_review": args.skip_pm_review,
            }
        }, f, indent=2)

    print(f"\nResults saved to {results_file}")


if __name__ == "__main__":
    main()
