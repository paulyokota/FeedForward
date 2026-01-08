#!/usr/bin/env python3
"""
Backfill story_id for existing conversations.

Fetches linked Shortcut ticket data from Intercom API and updates
the story_id field in the database.

Usage:
    python scripts/backfill_story_ids.py [--dry-run] [--limit N]

Options:
    --dry-run    Show what would be updated without making changes
    --limit N    Only process first N conversations (for testing)
"""
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Optional
import requests
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.connection import get_connection

# Load environment variables
load_dotenv()

INTERCOM_ACCESS_TOKEN = os.getenv("INTERCOM_ACCESS_TOKEN")
if not INTERCOM_ACCESS_TOKEN:
    print("❌ Error: INTERCOM_ACCESS_TOKEN not found in environment")
    sys.exit(1)


def extract_story_id_from_conversation(conversation_data: dict) -> Optional[str]:
    """
    Extract Shortcut story ID from Intercom conversation data.

    IMPORTANT: Uses the 'v2' field from linked_objects, not 'id'.

    Args:
        conversation_data: Intercom API conversation response

    Returns:
        Shortcut story ID (e.g., "sc-12345") or None if not linked
    """
    if "linked_objects" not in conversation_data:
        return None

    linked_objects = conversation_data["linked_objects"]
    if "data" not in linked_objects:
        return None

    for linked_obj in linked_objects["data"]:
        if linked_obj.get("type") == "ticket":
            # CRITICAL: Use v2 field, not id field
            story_id = linked_obj.get("v2")
            if story_id:
                return story_id

    return None


def fetch_conversation_from_intercom(conversation_id: str) -> Optional[dict]:
    """
    Fetch conversation details from Intercom API.

    Args:
        conversation_id: Intercom conversation ID

    Returns:
        Conversation data or None on error
    """
    try:
        response = requests.get(
            f"https://api.intercom.io/conversations/{conversation_id}",
            headers={
                "Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}",
                "Accept": "application/json"
            },
            timeout=10
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"  ⚠️  Conversation {conversation_id} not found in Intercom")
            return None
        else:
            print(f"  ❌ Error {response.status_code} for {conversation_id}: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request error for {conversation_id}: {e}")
        return None


def backfill_story_ids(dry_run: bool = False, limit: Optional[int] = None):
    """
    Backfill story_id for existing conversations.

    Args:
        dry_run: If True, don't update database
        limit: If set, only process first N conversations
    """
    print("🔍 Fetching conversations without story_id...")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Get conversations without story_id
            query = "SELECT id FROM conversations WHERE story_id IS NULL ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            conversation_ids = [row[0] for row in cursor.fetchall()]

            total = len(conversation_ids)
            print(f"📊 Found {total} conversations to process")

            if dry_run:
                print("🔍 DRY RUN MODE - No changes will be made")

            print()

            # Track statistics
            stats = {
                "total": total,
                "fetched": 0,
                "with_story_id": 0,
                "without_story_id": 0,
                "errors": 0,
                "updated": 0
            }

            for i, conv_id in enumerate(conversation_ids, 1):
                print(f"[{i}/{total}] Processing {conv_id}...", end=" ")

                # Fetch from Intercom
                conversation_data = fetch_conversation_from_intercom(conv_id)

                if conversation_data is None:
                    stats["errors"] += 1
                    print("❌ Failed to fetch")
                    time.sleep(0.5)  # Rate limiting
                    continue

                stats["fetched"] += 1

                # Extract story_id
                story_id = extract_story_id_from_conversation(conversation_data)

                if story_id:
                    stats["with_story_id"] += 1
                    print(f"✅ Found story_id: {story_id}")

                    if not dry_run:
                        # Update database
                        cursor.execute(
                            "UPDATE conversations SET story_id = %s WHERE id = %s",
                            (story_id, conv_id)
                        )
                        conn.commit()
                        stats["updated"] += 1
                    else:
                        print(f"   (Would update story_id to {story_id})")
                else:
                    stats["without_story_id"] += 1
                    print("⚪ No linked story")

                # Rate limiting (2 requests per second)
                time.sleep(0.5)

            print()
            print("=" * 60)
            print("📊 BACKFILL SUMMARY")
            print("=" * 60)
            print(f"Total conversations:     {stats['total']}")
            print(f"Successfully fetched:    {stats['fetched']}")
            print(f"With story_id:           {stats['with_story_id']}")
            print(f"Without story_id:        {stats['without_story_id']}")
            print(f"Errors:                  {stats['errors']}")

            if not dry_run:
                print(f"Database updates:        {stats['updated']}")
            else:
                print(f"Would update:            {stats['with_story_id']}")

            print()

            if stats['with_story_id'] > 0:
                coverage_pct = (stats['with_story_id'] / stats['total']) * 100
                print(f"📈 Story ID Coverage: {coverage_pct:.1f}%")

            if not dry_run and stats['updated'] > 0:
                print()
                print("✅ Backfill complete! Run this to see clusters:")
                print()
                print("   SELECT * FROM conversation_clusters")
                print("   WHERE conversation_count >= 3")
                print("   ORDER BY conversation_count DESC;")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill story_id for existing conversations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process first N conversations (for testing)"
    )

    args = parser.parse_args()

    backfill_story_ids(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
