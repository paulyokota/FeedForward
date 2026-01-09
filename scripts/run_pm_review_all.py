#!/usr/bin/env python3
"""
Run PM/Tech Lead review on all valid groups from theme extraction.

Outputs decisions for each group to help calibrate confidence thresholds.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI

INPUT_FILE = Path(__file__).parent.parent / "data" / "theme_extraction_results.jsonl"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "pm_review_results.json"
MIN_GROUP_SIZE = 3
SKIP_SIGNATURES = {"unclassified_needs_review"}  # Known catch-all, skip

# Product context for PM
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

Common user workflows:
- Schedule pins/posts to multiple boards/accounts
- Use AI to generate content (Ghostwriter, Smart Pins)
- Connect social accounts via OAuth
- Manage subscription and billing
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


def load_groups() -> dict[str, list[dict]]:
    """Load theme extraction results grouped by signature."""
    groups: dict[str, list[dict]] = defaultdict(list)

    with open(INPUT_FILE) as f:
        for line in f:
            conv = json.loads(line)
            signature = conv.get("issue_signature", "unknown")
            groups[signature].append(conv)

    return dict(groups)


def format_conversations(conversations: list[dict], max_convos: int = 60) -> str:
    """Format conversations for PM review prompt."""
    # Limit to max_convos to avoid token limits (GPT-4o handles 128k context)
    sample = conversations[:max_convos]

    lines = []
    for i, conv in enumerate(sample, 1):
        lines.append(f"### Conversation {i} (ID: {conv['id']})")
        lines.append(f"- User Intent: {conv.get('user_intent', 'N/A')}")
        lines.append(f"- Symptoms: {', '.join(conv.get('symptoms', [])) or 'N/A'}")
        lines.append(f"- Affected Flow: {conv.get('affected_flow', 'N/A')}")
        lines.append(f"- Excerpt: {conv.get('excerpt', 'N/A')[:200]}...")
        lines.append("")

    if len(conversations) > max_convos:
        lines.append(f"... and {len(conversations) - max_convos} more conversations")

    return "\n".join(lines)


def run_pm_review(client: OpenAI, signature: str, conversations: list[dict]) -> dict:
    """Run PM review for a single group."""
    prompt = PM_REVIEW_PROMPT.format(
        product_context=PRODUCT_CONTEXT,
        signature=signature,
        count=len(conversations),
        conversations=format_conversations(conversations)
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    return result


def main():
    print(f"Loading groups from: {INPUT_FILE}")
    groups = load_groups()

    # Filter to valid groups only
    valid_groups = {
        sig: convs for sig, convs in groups.items()
        if len(convs) >= MIN_GROUP_SIZE and sig not in SKIP_SIGNATURES
    }

    print(f"Found {len(valid_groups)} valid groups to review")
    print("-" * 60)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    results = []

    for sig, convs in sorted(valid_groups.items(), key=lambda x: -len(x[1])):
        print(f"\nReviewing: {sig} ({len(convs)} conversations)...")

        try:
            review = run_pm_review(client, sig, convs)

            result = {
                "signature": sig,
                "conversation_count": len(convs),
                "decision": review.get("decision"),
                "reasoning": review.get("reasoning"),
                "sub_groups": review.get("sub_groups", []),
                "sub_group_count": len(review.get("sub_groups", []))
            }
            results.append(result)

            # Print summary
            decision_icon = "KEEP" if review.get("decision") == "keep_together" else "SPLIT"
            print(f"  Decision: {decision_icon}")
            print(f"  Reasoning: {review.get('reasoning', 'N/A')[:100]}...")

            if review.get("sub_groups"):
                print(f"  Sub-groups: {len(review['sub_groups'])}")
                for sg in review["sub_groups"]:
                    print(f"    - {sg.get('suggested_signature')}: {len(sg.get('conversation_ids', []))} convos")

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "signature": sig,
                "conversation_count": len(convs),
                "decision": "error",
                "reasoning": str(e),
                "sub_groups": [],
                "sub_group_count": 0
            })

    # Save results
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    keep_count = sum(1 for r in results if r["decision"] == "keep_together")
    split_count = sum(1 for r in results if r["decision"] == "split")

    print(f"Total groups reviewed: {len(results)}")
    print(f"Keep together: {keep_count}")
    print(f"Split: {split_count}")
    print(f"\nResults saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
