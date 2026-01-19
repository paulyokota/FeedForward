#!/usr/bin/env python3
"""
Test script to run the 3 confirmed "pins not appearing in communities"
conversations through the FeedForward pipeline.

This tests how well our theme extraction handles this specific bug pattern.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from classifier import classify_conversation
from theme_extractor import ThemeExtractor, format_theme_for_ticket
from db.models import Conversation

# The 3 confirmed cases from Intercom
CONVERSATIONS = [
    {
        "id": "215472646393365",
        "name": "Nicole",
        "email": "nicole.kanzler@googlemail.com",
        "created_at": datetime(2026, 1, 12, 13, 38, 32),  # from Intercom
        "source_body": """Hello,
I would like to ask you to check my account and clarify why my pins published via you have not been appearing in my tribes/communities for two months (since around the beginning of November).
I have assigned all of my English pins, including those planned for the future, to a community when creating them. The pins appear correctly on Pinterest, but not in the communities.
This is a big problem and I would like to ask you to resolve it as soon as possible.

Thank you in advance.

Have a nice day
Nicole Kanzler
PS: My German pins are not planned for communities.""",
        "source_url": "https://www.tailwindapp.com/dashboard/tribes",
    },
    {
        "id": "215472620832941",
        "name": "Katie",
        "email": "katienelson131@gmail.com",
        "created_at": datetime(2026, 1, 9, 23, 5, 34),
        "source_body": "I'm not seeing posts I made to my communities.",
        "followup": "The pins are published but aren't in the yours tab",
        "source_url": "https://www.tailwindapp.com/dashboard/tribes/2383",
    },
    {
        "id": "215472406229172",
        "name": "Chili to Choc",
        "email": "chilitochoc@gmail.com",
        "created_at": datetime(2025, 12, 23, 20, 31, 15),
        "source_body": """My pins are not being posted in the communities. Even after they are published on Pinterest.

The Pins I add to Communities are not showing up in the Communities even after they are published. I have checked the Yours tab. This has been happening for around two weeks, and I was hoping it would sort itself out eventually, but it is still the same.

I am talking about adding them to Communities via the scheduler.""",
        "followup": """Hi, thank you for getting back to me. I have tried the steps but the problem still persists. I have to manually add each pin after it is posted which is quite a hassle. I'm unable to do this while scheduling all my pins for the upcoming weeks.

So this time I scheduled the pins and added them to communities, with screenshots showing they were definitely added.
Pin 1 (Chocolate Muffins): https://www.pinterest.com/pin/708542953917735973/
Pin 2 (Garlic Rolls): https://www.pinterest.com/pin/708542953917736802/

Tailwind is supposed to be about scheduling in advance and being hands-free. And for how expensive it is, these kinds of small but constant glitches really shouldn't be happening.""",
        "source_url": "https://www.tailwindapp.com/dashboard/tribes/4743",
    },
]


def run_single_conversation(conv_data: dict, verbose: bool = True) -> dict:
    """Process a single conversation through classify -> extract."""

    if verbose:
        print(f"\n{'='*70}")
        print(f"CONVERSATION: {conv_data['id']} ({conv_data['name']})")
        print(f"{'='*70}")

    # Combine source_body with followup if present
    full_text = conv_data["source_body"]
    if "followup" in conv_data:
        full_text += "\n\n[Follow-up message]\n" + conv_data["followup"]

    if verbose:
        print(f"\nMessage preview:\n{full_text[:300]}{'...' if len(full_text) > 300 else ''}")

    # Step 1: Classify the conversation
    if verbose:
        print(f"\n--- CLASSIFICATION ---")

    classification = classify_conversation(full_text)

    if verbose:
        print(f"Issue Type: {classification['issue_type']}")
        print(f"Sentiment: {classification['sentiment']}")
        print(f"Churn Risk: {classification['churn_risk']}")
        print(f"Priority: {classification['priority']}")

    # Step 2: Create Conversation object
    conv = Conversation(
        id=conv_data["id"],
        created_at=conv_data["created_at"],
        source_body=full_text,
        source_url=conv_data.get("source_url"),
        contact_email=conv_data.get("email"),
        issue_type=classification['issue_type'],
        sentiment=classification['sentiment'],
        churn_risk=classification['churn_risk'],
        priority=classification['priority'],
    )

    # Step 3: Extract theme
    if verbose:
        print(f"\n--- THEME EXTRACTION ---")

    extractor = ThemeExtractor()
    theme = extractor.extract(conv)

    if verbose:
        print(format_theme_for_ticket(theme))

    return {
        "conversation_id": conv_data["id"],
        "name": conv_data["name"],
        "classification": {
            "issue_type": classification['issue_type'],
            "sentiment": classification['sentiment'],
            "churn_risk": classification['churn_risk'],
            "priority": classification['priority'],
        },
        "theme": {
            "product_area": theme.product_area,
            "component": theme.component,
            "issue_signature": theme.issue_signature,
            "user_intent": theme.user_intent,
            "symptoms": theme.symptoms,
            "affected_flow": theme.affected_flow,
            "root_cause_hypothesis": theme.root_cause_hypothesis,
        }
    }


def main():
    print("\n" + "="*70)
    print("FEEDFORWARD PIPELINE TEST: Pins Not Appearing in Communities Bug")
    print("="*70)
    print(f"\nTesting {len(CONVERSATIONS)} confirmed cases of the same bug:")
    for c in CONVERSATIONS:
        print(f"  - {c['id']} ({c['name']})")

    results = []
    for conv_data in CONVERSATIONS:
        try:
            result = run_single_conversation(conv_data)
            results.append(result)
        except Exception as e:
            print(f"\nERROR processing {conv_data['id']}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    # Check if all conversations got the same/similar theme signatures
    signatures = [r["theme"]["issue_signature"] for r in results]
    unique_signatures = set(signatures)

    print(f"\nTotal conversations: {len(results)}")
    print(f"Unique issue signatures: {len(unique_signatures)}")

    if len(unique_signatures) == 1:
        print(f"\n✓ SUCCESS: All conversations extracted the SAME signature:")
        print(f"  '{signatures[0]}'")
    else:
        print(f"\n⚠ WARNING: Multiple signatures extracted:")
        for sig in unique_signatures:
            count = signatures.count(sig)
            print(f"  - '{sig}' ({count}x)")
        print("\nThis indicates the theme extraction may need tuning to")
        print("recognize these as the same underlying issue.")

    # Show all results
    print("\n--- Detailed Results ---")
    for r in results:
        print(f"\n{r['name']} ({r['conversation_id']}):")
        print(f"  Classification: {r['classification']['issue_type']} | {r['classification']['sentiment']} | priority={r['classification']['priority']}")
        print(f"  Theme: {r['theme']['product_area']} → {r['theme']['component']}")
        print(f"  Signature: {r['theme']['issue_signature']}")

    # Write results to JSON for later analysis
    output_path = Path(__file__).parent / "communities_bug_pipeline_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n[Results saved to {output_path}]")

    return results


if __name__ == "__main__":
    main()
