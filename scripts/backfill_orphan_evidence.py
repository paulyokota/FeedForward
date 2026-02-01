#!/usr/bin/env python3
"""
Backfill evidence bundles for orphan-graduated stories.

Issue #197: Raise story evidence quality

This script finds stories created via orphan graduation that are missing
evidence bundles, and creates them using OrphanIntegrationService.

Usage:
    python scripts/backfill_orphan_evidence.py --dry-run    # Preview changes
    python scripts/backfill_orphan_evidence.py              # Execute backfill
    python scripts/backfill_orphan_evidence.py --batch 50   # Custom batch size
"""

import argparse
import logging
import os
import sys
from typing import Dict, List
from uuid import UUID

from psycopg2.extras import RealDictCursor

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.connection import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_orphan_graduated_stories_without_evidence(
    conn, limit: int, offset: int
) -> List[Dict]:
    """
    Get stories linked to graduated orphans but missing evidence bundles.

    Returns stories where:
    - story_orphans row exists with graduated_at IS NOT NULL
    - story_evidence row does NOT exist
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT s.id, so.signature, so.conversation_ids
            FROM stories s
            JOIN story_orphans so ON s.id = so.story_id
            LEFT JOIN story_evidence se ON s.id = se.story_id
            WHERE so.graduated_at IS NOT NULL
              AND se.id IS NULL
            ORDER BY s.created_at
            LIMIT %s OFFSET %s
        """, (limit, offset))
        return cur.fetchall()


def get_total_count(conn) -> int:
    """Get total count of stories needing backfill."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT COUNT(*) as count
            FROM stories s
            JOIN story_orphans so ON s.id = so.story_id
            LEFT JOIN story_evidence se ON s.id = se.story_id
            WHERE so.graduated_at IS NOT NULL
              AND se.id IS NULL
        """)
        return cur.fetchone()["count"]


def run_backfill(
    dry_run: bool = False,
    batch_size: int = 100,
):
    """Run the backfill process."""
    # Import here to avoid circular imports and to ensure path is set
    from src.story_tracking.services.orphan_integration import OrphanIntegrationService

    logger.info("=" * 60)
    logger.info("ORPHAN EVIDENCE BACKFILL")
    logger.info("=" * 60)
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    logger.info(f"Batch size: {batch_size}")

    # Stats
    backfilled = 0
    failed = 0
    no_conversation_ids = 0

    with get_connection() as conn:
        # Get total count
        total_needing_backfill = get_total_count(conn)
        logger.info(f"Stories needing evidence backfill: {total_needing_backfill}")

        if total_needing_backfill == 0:
            logger.info("No stories need backfill. Exiting.")
            return

        # Create integration service to reuse evidence creation logic
        integration_service = OrphanIntegrationService(conn, auto_graduate=False)

        # Process in batches
        offset = 0
        processed = 0

        while processed < total_needing_backfill:
            logger.info(f"Processing batch at offset {offset}...")
            stories = get_orphan_graduated_stories_without_evidence(
                conn, batch_size, offset
            )

            if not stories:
                break

            for story in stories:
                story_id = story["id"]
                signature = story["signature"]
                conversation_ids = story["conversation_ids"]

                if not conversation_ids:
                    no_conversation_ids += 1
                    logger.warning(f"Story {story_id} has no conversation_ids, skipping")
                    processed += 1
                    continue

                if dry_run:
                    logger.info(
                        f"[DRY-RUN] Would create evidence for story {story_id} "
                        f"with {len(conversation_ids)} conversations"
                    )
                    backfilled += 1
                else:
                    # Reuse the evidence creation logic from OrphanIntegrationService
                    success = integration_service._create_evidence_for_graduated_story(
                        story_id=UUID(str(story_id)),
                        orphan_signature=signature,
                        conversation_ids=conversation_ids,
                    )

                    if success:
                        backfilled += 1
                    else:
                        failed += 1

                processed += 1

                if processed % 10 == 0:
                    logger.info(
                        f"Processed {processed}/{total_needing_backfill} stories..."
                    )

            # Commit after each batch (unless dry run)
            if not dry_run:
                conn.commit()

            offset += batch_size

        # Final commit
        if not dry_run:
            conn.commit()

    # Log summary
    logger.info("=" * 60)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total processed: {processed}")
    logger.info(f"Successfully backfilled: {backfilled}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Skipped (no conversation_ids): {no_conversation_ids}")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill evidence bundles for orphan-graduated stories"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=100,
        help="Batch size for processing (default: 100)",
    )
    args = parser.parse_args()

    run_backfill(
        dry_run=args.dry_run,
        batch_size=args.batch,
    )


if __name__ == "__main__":
    main()
