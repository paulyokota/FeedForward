#!/usr/bin/env python
"""
Re-extract themes for conversations currently in catch-all buckets.

With expanded vocabulary v2.1, many conversations in:
- general_product_question
- unclassified_needs_review

Can now be properly categorized into specific actionable themes.

Usage:
    python scripts/reextract_catchall.py [--dry-run] [--limit N]
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.connection import get_connection
from db.models import Conversation
from theme_extractor import ThemeExtractor
from theme_tracker import ThemeTracker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Themes to re-extract (catch-all buckets)
CATCHALL_THEMES = [
    'general_product_question',
    'unclassified_needs_review',
]


def get_catchall_conversations(limit: int = None) -> list[dict]:
    """Get conversations currently in catch-all theme buckets."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT c.id, c.created_at, c.source_body, c.issue_type,
                       c.sentiment, c.churn_risk, c.priority,
                       t.issue_signature as old_theme
                FROM conversations c
                JOIN themes t ON c.id = t.conversation_id
                WHERE t.issue_signature = ANY(%s)
                  AND c.source_body IS NOT NULL
                  AND LENGTH(c.source_body) > 30
                ORDER BY c.created_at DESC
            """
            if limit:
                query += f" LIMIT {limit}"

            cur.execute(query, (CATCHALL_THEMES,))

            return [
                {
                    'id': row[0],
                    'created_at': row[1],
                    'source_body': row[2],
                    'issue_type': row[3],
                    'sentiment': row[4],
                    'churn_risk': row[5],
                    'priority': row[6],
                    'old_theme': row[7],
                }
                for row in cur.fetchall()
            ]


def delete_theme(conversation_id: str) -> bool:
    """Delete existing theme for a conversation."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM themes WHERE conversation_id = %s",
                (conversation_id,)
            )
            return cur.rowcount > 0


def update_aggregate_count(issue_signature: str, delta: int) -> None:
    """Update aggregate count (decrement for old, handled by store for new)."""
    if delta >= 0:
        return  # Store handles increments

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE theme_aggregates
                SET occurrence_count = occurrence_count + %s
                WHERE issue_signature = %s
            """, (delta, issue_signature))


def main():
    parser = argparse.ArgumentParser(
        description="Re-extract themes for catch-all bucket conversations"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't actually update data, just show what would happen"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of conversations to process"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Use strict mode (vocabulary-only matching)"
    )

    args = parser.parse_args()

    print(f"\nRe-extraction Configuration:")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Limit: {args.limit or 'none'}")
    print(f"  Strict mode: {args.strict}")
    print(f"  Catch-all themes: {CATCHALL_THEMES}")
    print()

    # Get conversations to re-process
    conversations = get_catchall_conversations(limit=args.limit)
    print(f"Found {len(conversations)} conversations in catch-all buckets")

    if not conversations:
        print("Nothing to re-extract")
        return 0

    # Initialize extractor and tracker
    extractor = ThemeExtractor()
    tracker = ThemeTracker()

    # Track results
    stats = {
        'processed': 0,
        'reclassified': 0,
        'same': 0,
        'errors': 0,
        'new_themes': {},
    }

    for i, conv_data in enumerate(conversations, 1):
        conv_id = conv_data['id']
        old_theme = conv_data['old_theme']

        # Create Conversation object for extractor
        conv = Conversation(
            id=conv_id,
            created_at=conv_data['created_at'],
            source_body=conv_data['source_body'],
            issue_type=conv_data['issue_type'],
            sentiment=conv_data['sentiment'],
            churn_risk=conv_data['churn_risk'],
            priority=conv_data['priority'],
        )

        try:
            # Extract new theme
            new_theme = extractor.extract(conv, strict_mode=args.strict)

            if new_theme.issue_signature == old_theme:
                stats['same'] += 1
                logger.debug(f"{conv_id}: stays {old_theme}")
            else:
                stats['reclassified'] += 1

                # Track new theme distribution
                if new_theme.issue_signature not in stats['new_themes']:
                    stats['new_themes'][new_theme.issue_signature] = 0
                stats['new_themes'][new_theme.issue_signature] += 1

                logger.info(f"{conv_id}: {old_theme} -> {new_theme.issue_signature}")

                if not args.dry_run:
                    # Delete old theme
                    delete_theme(conv_id)
                    update_aggregate_count(old_theme, -1)

                    # Store new theme
                    tracker.store_theme(new_theme)

            stats['processed'] += 1

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Error processing {conv_id}: {e}")

        # Progress update
        if i % 20 == 0:
            print(f"Progress: {i}/{len(conversations)} ({stats['reclassified']} reclassified)")

    # Print summary
    print("\n" + "=" * 50)
    print("RE-EXTRACTION COMPLETE")
    print("=" * 50)
    print(f"  Processed: {stats['processed']}")
    print(f"  Reclassified: {stats['reclassified']}")
    print(f"  Stayed same: {stats['same']}")
    print(f"  Errors: {stats['errors']}")

    if stats['new_themes']:
        print("\n  New theme distribution:")
        for sig, count in sorted(stats['new_themes'].items(), key=lambda x: -x[1]):
            print(f"    {count:>3}x {sig}")

    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
