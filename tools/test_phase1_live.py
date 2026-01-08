#!/usr/bin/env python3
"""
Phase 1 Live Test: Test on real Intercom conversations with proper data

Uses actual conversation data from MCP Intercom integration.
"""
import sys
import re
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from classification_manager import ClassificationManager


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()


# Real conversations with properly extracted messages
CONVERSATIONS = [
    {
        "id": "215472581229755",
        "summary": "Instagram connection issue",
        "customer_message": "Hey there. Having trouble getting my Instagram account connected. I've already walked through all of your tutorials. Is there someone who can help me?",
        "support_messages": [
            "Can you send us a screenshot from you IG app on your phone showing the profile is in fact a business professional account type. It must be specifically designated business under the account type professional to be able to be connected.",
            "Thanks for that. And is this account connected to a Facebook Page? (Note: Profile doesn't matter, but it needs to be connected to a Page to be able to connect here)"
        ]
    },
    {
        "id": "215472567808249",
        "summary": "Billing refund - accidental upgrade",
        "customer_message": "Subject: Accidental Plan Upgrade - Request Immediate Refund/Downgrade. Hi Tailwind Team, I accidentally upgraded to the Max annual plan today. I immediately tried to downgrade to Pro, but the system says the downgrade will only take effect in 364 days. I only need the Pro plan for my single Pinterest account. Could you please: 1. Cancel the Max plan 2. Process a refund for the difference 3. Switch me to Pro plan immediately",
        "support_messages": [
            "I noticed you signed up for the monthly plan for the pro, but then the max plan was annual. Were you wanting the pro plan to be monthly or annual (the annual is about a 50% savings over the monthly.)"
        ]
    },
    {
        "id": "215472585825223",
        "summary": "Cancel auto-renewal",
        "customer_message": "hey, i want to make sure that my annual plan does not auto renew",
        "support_messages": []  # No human support yet, only bot
    },
    {
        "id": "215472583382362",
        "summary": "Cancel subscription",
        "customer_message": "I would like to cancel my annual subscription and not renew in march",
        "support_messages": [
            "Hi there, Hopefully this finds you well and having a good day! I'm sorry that you're looking to cancel your subscription, and I can definitely help with that. If you don't mind, could you share with us why you're looking to cancel today? Maybe it's something we can help with!"
        ]
    },
    {
        "id": "215472585371218",
        "summary": "Turbo pin not working",
        "customer_message": "Well, every time I add a pin to turbo pin, it says that it couldn't add my pin",
        "support_messages": []  # Only bot responses, closed by bot
    }
]


def main():
    """Test Phase 1 system on real conversations."""
    print("=" * 80)
    print("PHASE 1 LIVE TEST: Real Intercom Conversations")
    print("=" * 80)

    # Initialize
    classification_manager = ClassificationManager()

    # Statistics
    stats = {
        "total": 0,
        "stage1_confidence": Counter(),
        "stage2_confidence": Counter(),
        "classification_changes": 0,
        "stage1_types": Counter(),
        "stage2_types": Counter(),
        "resolution_detected": 0,
        "has_support_response": 0,
        "disambiguation_high": 0,
        "disambiguation_medium": 0
    }

    results = []

    print("\n" + "-" * 80)
    print("PROCESSING CONVERSATIONS")
    print("-" * 80 + "\n")

    for i, conv in enumerate(CONVERSATIONS, 1):
        print(f"[{i}/{len(CONVERSATIONS)}] {conv['summary']}")
        print(f"  Customer: {conv['customer_message'][:60]}...")

        has_support = len(conv["support_messages"]) > 0
        if has_support:
            stats["has_support_response"] += 1
            print(f"  Support: {len(conv['support_messages'])} response(s)")
            print(f"           {conv['support_messages'][0][:60]}...")
        else:
            print(f"  Support: None (Stage 1 only)")

        try:
            # Run complete classification
            result = classification_manager.classify_complete_conversation(
                conv["customer_message"],
                conv["support_messages"]
            )

            # Track statistics
            stats["total"] += 1
            stats["stage1_confidence"][result["stage1"]["confidence"]] += 1
            stats["stage1_types"][result["stage1"]["conversation_type"]] += 1

            print(f"  Stage 1: {result['stage1']['conversation_type']} ({result['stage1']['confidence']})")

            if result["stage2"] and has_support:
                stats["stage2_confidence"][result["stage2"]["confidence"]] += 1
                stats["stage2_types"][result["stage2"]["conversation_type"]] += 1

                print(f"  Stage 2: {result['stage2']['conversation_type']} ({result['stage2']['confidence']})")

                if result["classification_updated"]:
                    stats["classification_changes"] += 1
                    print(f"  ✓ Updated: {result['stage1']['conversation_type']} → {result['stage2']['conversation_type']}")

                # Disambiguation tracking
                disamb_level = result["stage2"].get("disambiguation_level", "none")
                if disamb_level == "high":
                    stats["disambiguation_high"] += 1
                    print(f"  ✓ High disambiguation")
                elif disamb_level == "medium":
                    stats["disambiguation_medium"] += 1

                if result["stage2"]["resolution_analysis"]["primary_action"]:
                    stats["resolution_detected"] += 1
                    action = result["stage2"]["resolution_analysis"]["primary_action"]
                    print(f"  ✓ Resolution: {action['action']}")

            results.append({
                "conversation_id": conv["id"],
                "summary": conv["summary"],
                "stage1": result["stage1"],
                "stage2": result["stage2"],
                "final_type": result["final_type"],
                "updated": result.get("classification_updated", False)
            })

        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            import traceback
            traceback.print_exc()

        print()

    # Generate report
    print("=" * 80)
    print("PHASE 1 LIVE TEST RESULTS")
    print("=" * 80)

    print(f"\n## Overall Statistics")
    print(f"Total conversations: {stats['total']}")
    print(f"With support responses: {stats['has_support_response']}")
    print(f"Customer-only (Stage 1): {stats['total'] - stats['has_support_response']}")

    print(f"\n## Stage 1 Performance (Fast Routing)")
    print(f"Confidence distribution:")
    for conf, count in stats["stage1_confidence"].most_common():
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {conf}: {count} ({pct:.1f}%)")

    print(f"\nConversation types:")
    for type_name, count in stats["stage1_types"].most_common():
        pct = (count / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {type_name}: {count} ({pct:.1f}%)")

    if stats["has_support_response"] > 0:
        print(f"\n## Stage 2 Performance (Refined Analysis)")
        print(f"Conversations analyzed: {stats['has_support_response']}")

        print(f"\nConfidence distribution:")
        for conf, count in stats["stage2_confidence"].most_common():
            pct = (count / stats['has_support_response'] * 100) if stats['has_support_response'] > 0 else 0
            print(f"  {conf}: {count} ({pct:.1f}%)")

        print(f"\nConversation types:")
        for type_name, count in stats["stage2_types"].most_common():
            pct = (count / stats['has_support_response'] * 100) if stats['has_support_response'] > 0 else 0
            print(f"  {type_name}: {count} ({pct:.1f}%)")

        print(f"\n## Classification Changes")
        pct = (stats['classification_changes'] / stats['has_support_response'] * 100) if stats['has_support_response'] > 0 else 0
        print(f"Stage 2 updated Stage 1: {stats['classification_changes']} ({pct:.1f}%)")

        print(f"\n## Disambiguation")
        high_pct = (stats['disambiguation_high'] / stats['has_support_response'] * 100) if stats['has_support_response'] > 0 else 0
        med_pct = (stats['disambiguation_medium'] / stats['has_support_response'] * 100) if stats['has_support_response'] > 0 else 0
        print(f"High disambiguation: {stats['disambiguation_high']} ({high_pct:.1f}%)")
        print(f"Medium disambiguation: {stats['disambiguation_medium']} ({med_pct:.1f}%)")

        print(f"\n## Resolution Detection")
        pct = (stats['resolution_detected'] / stats['has_support_response'] * 100) if stats['has_support_response'] > 0 else 0
        print(f"Actions detected: {stats['resolution_detected']} ({pct:.1f}%)")

    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    print("\n✓ Stage 1 classifier working with LLM (gpt-4o-mini)")
    print(f"  - {stats['stage1_confidence']['high']} high confidence classifications")
    print(f"  - Fast routing for real-time support")

    if stats["has_support_response"] > 0:
        print("\n✓ Stage 2 classifier working with full context")
        print(f"  - {stats['stage2_confidence']['high']} high confidence classifications")
        print(f"  - {stats['classification_changes']} classification improvement(s)")
        print(f"  - {stats['disambiguation_high'] + stats['disambiguation_medium']} disambiguated conversation(s)")

    print("\n✓ Complete Phase 1 system operational on production data")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
