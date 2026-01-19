#!/usr/bin/env python3
"""
Store the 3 confirmed "pins not appearing in communities" conversations
in the database with a unified theme signature, then generate a story.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.connection import get_connection, init_db
from db.models import Conversation
from theme_extractor import Theme
from theme_tracker import ThemeTracker, generate_ticket_content

# Unified signature for all 3 conversations
UNIFIED_SIGNATURE = "community_pins_not_appearing_in_yours_tab"

# The 3 confirmed cases
CONVERSATIONS = [
    {
        "id": "215472646393365",
        "name": "Nicole",
        "email": "nicole.kanzler@googlemail.com",
        "created_at": datetime(2026, 1, 12, 13, 38, 32),
        "source_body": """Hello,
I would like to ask you to check my account and clarify why my pins published via you have not been appearing in my tribes/communities for two months (since around the beginning of November).
I have assigned all of my English pins, including those planned for the future, to a community when creating them. The pins appear correctly on Pinterest, but not in the communities.
This is a big problem and I would like to ask you to resolve it as soon as possible.

Thank you in advance.

Have a nice day
Nicole Kanzler
PS: My German pins are not planned for communities.""",
        "source_url": "https://www.tailwindapp.com/dashboard/tribes",
        "issue_type": "bug_report",
        "sentiment": "neutral",
        "churn_risk": False,
        "priority": "high",
    },
    {
        "id": "215472620832941",
        "name": "Katie",
        "email": "katienelson131@gmail.com",
        "created_at": datetime(2026, 1, 9, 23, 5, 34),
        "source_body": """I'm not seeing posts I made to my communities.

[Follow-up message]
The pins are published but aren't in the yours tab""",
        "source_url": "https://www.tailwindapp.com/dashboard/tribes/2383",
        "issue_type": "bug_report",
        "sentiment": "neutral",
        "churn_risk": False,
        "priority": "normal",
    },
    {
        "id": "215472406229172",
        "name": "Chili to Choc",
        "email": "chilitochoc@gmail.com",
        "created_at": datetime(2025, 12, 23, 20, 31, 15),
        "source_body": """My pins are not being posted in the communities. Even after they are published on Pinterest.

The Pins I add to Communities are not showing up in the Communities even after they are published. I have checked the Yours tab. This has been happening for around two weeks, and I was hoping it would sort itself out eventually, but it is still the same.

I am talking about adding them to Communities via the scheduler.

[Follow-up message]
Hi, thank you for getting back to me. I have tried the steps but the problem still persists. I have to manually add each pin after it is posted which is quite a hassle. I'm unable to do this while scheduling all my pins for the upcoming weeks.

So this time I scheduled the pins and added them to communities, with screenshots showing they were definitely added.
Pin 1 (Chocolate Muffins): https://www.pinterest.com/pin/708542953917735973/
Pin 2 (Garlic Rolls): https://www.pinterest.com/pin/708542953917736802/

Tailwind is supposed to be about scheduling in advance and being hands-free. And for how expensive it is, these kinds of small but constant glitches really shouldn't be happening.""",
        "source_url": "https://www.tailwindapp.com/dashboard/tribes/4743",
        "issue_type": "bug_report",
        "sentiment": "frustrated",
        "churn_risk": False,
        "priority": "high",
    },
]


def store_conversation(conv_data: dict):
    """Store a conversation in the database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations (
                    id, created_at, source_body, source_url, contact_email,
                    issue_type, sentiment, churn_risk, priority, classifier_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    source_body = EXCLUDED.source_body,
                    issue_type = EXCLUDED.issue_type,
                    sentiment = EXCLUDED.sentiment,
                    churn_risk = EXCLUDED.churn_risk,
                    priority = EXCLUDED.priority
            """, (
                conv_data["id"],
                conv_data["created_at"],
                conv_data["source_body"],
                conv_data.get("source_url"),
                conv_data.get("email"),
                conv_data["issue_type"],
                conv_data["sentiment"],
                conv_data["churn_risk"],
                conv_data["priority"],
                "v1",
            ))
            conn.commit()


def create_unified_theme(conv_data: dict) -> Theme:
    """Create a Theme with the unified signature."""
    return Theme(
        conversation_id=conv_data["id"],
        product_area="communities",
        component="tailwind_communities",
        issue_signature=UNIFIED_SIGNATURE,
        user_intent="User wants scheduled pins to appear in Communities 'Yours' tab after publishing",
        symptoms=[
            "Pins scheduled with community assignment",
            "Pins publish successfully to Pinterest",
            "Pins do not appear in Communities 'Yours' tab",
            "DB records (tribe_content_documents) exist for submissions",
        ],
        affected_flow="Pin Scheduler → Tailwind Communities → Yours Tab Display",
        root_cause_hypothesis="Synchronization issue between pin publishing and community visibility - backend records exist but UI doesn't reflect them",
    )


def main():
    print("\n" + "="*70)
    print("STORING CONVERSATIONS AND UNIFIED THEMES")
    print("="*70)

    # Initialize database
    print("\nInitializing database...")
    init_db()

    # Store conversations
    print(f"\nStoring {len(CONVERSATIONS)} conversations...")
    for conv in CONVERSATIONS:
        store_conversation(conv)
        print(f"  ✓ Stored {conv['id']} ({conv['name']})")

    # Create and store unified themes
    print(f"\nStoring themes with unified signature: {UNIFIED_SIGNATURE}")
    tracker = ThemeTracker()

    for conv in CONVERSATIONS:
        theme = create_unified_theme(conv)
        is_new = tracker.store_theme(theme)
        status = "new" if is_new else "duplicate"
        print(f"  ✓ Theme for {conv['name']}: {status}")

    # Check the aggregate
    print("\n" + "="*70)
    print("THEME AGGREGATE")
    print("="*70)

    agg = tracker.get_aggregate(UNIFIED_SIGNATURE)
    if agg:
        print(f"\nSignature: {agg.issue_signature}")
        print(f"Occurrences: {agg.occurrence_count}")
        print(f"First seen: {agg.first_seen_at}")
        print(f"Last seen: {agg.last_seen_at}")
        print(f"Affected conversations: {agg.affected_conversations}")
        print(f"Ticket created: {agg.ticket_created}")
    else:
        print("\n⚠ Aggregate not found - checking database directly...")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM theme_aggregates WHERE issue_signature = %s", (UNIFIED_SIGNATURE,))
                row = cur.fetchone()
                if row:
                    print(f"  Found in DB: {row}")
                else:
                    print("  Not found in database either")

    # Generate ticket content
    print("\n" + "="*70)
    print("TICKET CONTENT PREVIEW")
    print("="*70)

    if agg and agg.occurrence_count >= 1:
        content = generate_ticket_content(tracker, UNIFIED_SIGNATURE)
        print(content)
    else:
        print("\nNo ticket content - aggregate not found or no occurrences")

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"\n✓ Stored {len(CONVERSATIONS)} conversations")
    print(f"✓ Created unified theme signature: {UNIFIED_SIGNATURE}")
    if agg:
        print(f"✓ Aggregate shows {agg.occurrence_count} occurrences")
        print(f"✓ Ready for ticket creation (threshold is typically 3)")
    print("\nTo create a Shortcut ticket, run:")
    print(f"  python src/cli.py ticket {UNIFIED_SIGNATURE}")


if __name__ == "__main__":
    main()
