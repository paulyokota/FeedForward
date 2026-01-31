#!/usr/bin/env python3
"""
Backfill multi-factor scores for existing stories.

Issue #188: Add sortable multi-factor story scoring

This script computes actionability, fix_size, severity, and churn_risk scores
for existing stories that don't have them.

Usage:
    python scripts/backfill_scores.py --dry-run    # Preview changes
    python scripts/backfill_scores.py              # Execute backfill
    python scripts/backfill_scores.py --batch 50   # Custom batch size
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.connection import get_db_connection
from src.multi_factor_scorer import (
    MultiFactorScorer,
    StoryScoreInput,
    ConversationScoreData,
    create_default_scores,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Safe defaults for missing data (from plan)
DEFAULT_ACTIONABILITY = 0.0
DEFAULT_FIX_SIZE = 0.0
DEFAULT_SEVERITY = 40.0  # Neutral midpoint
DEFAULT_CHURN_RISK = 40.0  # Neutral midpoint


class BackfillStats:
    """Track backfill statistics for logging."""

    def __init__(self):
        self.total_stories = 0
        self.already_scored = 0
        self.backfilled = 0
        self.failed = 0
        self.missing_conversations = 0
        self.missing_impl_context = 0
        self.missing_code_context = 0
        self.missing_priority = 0
        self.missing_churn_risk = 0

    def log_summary(self):
        """Log final summary."""
        logger.info("=" * 60)
        logger.info("BACKFILL SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total stories processed: {self.total_stories}")
        logger.info(f"Already had scores (skipped): {self.already_scored}")
        logger.info(f"Successfully backfilled: {self.backfilled}")
        logger.info(f"Failed: {self.failed}")
        logger.info("-" * 60)
        logger.info("Missing data counts:")
        logger.info(f"  - No conversations: {self.missing_conversations}")
        logger.info(f"  - No impl_context: {self.missing_impl_context}")
        logger.info(f"  - No code_context: {self.missing_code_context}")
        logger.info(f"  - No priority data: {self.missing_priority}")
        logger.info(f"  - No churn_risk data: {self.missing_churn_risk}")


def get_stories_without_scores(conn, limit: int, offset: int) -> List[Dict]:
    """Get stories that don't have multi-factor scores."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, title, implementation_context, code_context
            FROM stories
            WHERE actionability_score IS NULL
               OR fix_size_score IS NULL
               OR severity_score IS NULL
               OR churn_risk_score IS NULL
            ORDER BY created_at
            LIMIT %s OFFSET %s
        """, (limit, offset))
        return cur.fetchall()


def get_total_unscored_count(conn) -> int:
    """Get total count of stories without scores."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as count
            FROM stories
            WHERE actionability_score IS NULL
               OR fix_size_score IS NULL
               OR severity_score IS NULL
               OR churn_risk_score IS NULL
        """)
        return cur.fetchone()["count"]


def get_conversation_data_for_story(conn, story_id: UUID) -> List[Dict]:
    """Get conversation data for scoring from story evidence."""
    with conn.cursor() as cur:
        # Get conversation_ids from story_evidence
        cur.execute("""
            SELECT conversation_ids
            FROM story_evidence
            WHERE story_id = %s
        """, (str(story_id),))
        row = cur.fetchone()

        if not row or not row["conversation_ids"]:
            return []

        conversation_ids = row["conversation_ids"]

        # Get conversation data with priority and churn_risk
        cur.execute("""
            SELECT c.id, c.priority, c.churn_risk, c.org_id,
                   t.diagnostic_summary, t.key_excerpts, t.symptoms,
                   t.resolution_action, t.resolution_category
            FROM conversations c
            LEFT JOIN themes t ON t.conversation_id = c.id
            WHERE c.id = ANY(%s)
        """, (conversation_ids,))

        return cur.fetchall()


def update_story_scores(
    conn,
    story_id: UUID,
    actionability: float,
    fix_size: float,
    severity: float,
    churn_risk: float,
    metadata: Dict,
    dry_run: bool = False,
) -> bool:
    """Update story with computed scores."""
    if dry_run:
        logger.debug(
            f"[DRY-RUN] Would update story {story_id}: "
            f"actionability={actionability:.1f}, fix_size={fix_size:.1f}, "
            f"severity={severity:.1f}, churn_risk={churn_risk:.1f}"
        )
        return True

    try:
        import json
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE stories
                SET actionability_score = %s,
                    fix_size_score = %s,
                    severity_score = %s,
                    churn_risk_score = %s,
                    score_metadata = %s
                WHERE id = %s
            """, (
                actionability,
                fix_size,
                severity,
                churn_risk,
                json.dumps(metadata),
                str(story_id),
            ))
        return True
    except Exception as e:
        logger.error(f"Failed to update story {story_id}: {e}")
        return False


def process_story(
    conn,
    story: Dict,
    scorer: MultiFactorScorer,
    stats: BackfillStats,
    dry_run: bool = False,
) -> bool:
    """Process a single story and compute its scores."""
    story_id = story["id"]
    stats.total_stories += 1

    # Get conversation data
    conv_rows = get_conversation_data_for_story(conn, story_id)

    if not conv_rows:
        stats.missing_conversations += 1
        # Use defaults
        scores = create_default_scores()
        return update_story_scores(
            conn,
            story_id,
            scores.actionability_score,
            scores.fix_size_score,
            scores.severity_score,
            scores.churn_risk_score,
            {"note": "Backfill with defaults - no conversation data"},
            dry_run,
        )

    # Build ConversationScoreData from rows
    conversations = []
    has_priority = False
    has_churn_risk = False

    for row in conv_rows:
        if row.get("priority"):
            has_priority = True
        if row.get("churn_risk") is not None:
            has_churn_risk = True

        conversations.append(ConversationScoreData(
            id=row["id"],
            priority=row.get("priority"),
            churn_risk=row.get("churn_risk"),
            org_id=row.get("org_id"),
            diagnostic_summary=row.get("diagnostic_summary"),
            key_excerpts=row.get("key_excerpts") or [],
            symptoms=row.get("symptoms") or [],
            resolution_action=row.get("resolution_action"),
            resolution_category=row.get("resolution_category"),
        ))

    if not has_priority:
        stats.missing_priority += 1
    if not has_churn_risk:
        stats.missing_churn_risk += 1

    # Check for implementation_context and code_context
    impl_context = story.get("implementation_context")
    code_context = story.get("code_context")

    if not impl_context:
        stats.missing_impl_context += 1
    if not code_context:
        stats.missing_code_context += 1

    # Build input and score
    input_data = StoryScoreInput(
        conversations=conversations,
        implementation_context=impl_context if isinstance(impl_context, dict) else None,
        code_context=code_context if isinstance(code_context, dict) else None,
        evidence_count=len(conversations),
    )

    try:
        scores = scorer.score(input_data)

        # Add backfill note to metadata
        scores.metadata["backfill_source"] = "scripts/backfill_scores.py"
        scores.metadata["backfilled_at"] = datetime.now(timezone.utc).isoformat()

        success = update_story_scores(
            conn,
            story_id,
            scores.actionability_score,
            scores.fix_size_score,
            scores.severity_score,
            scores.churn_risk_score,
            scores.metadata,
            dry_run,
        )

        if success:
            stats.backfilled += 1
        else:
            stats.failed += 1

        return success

    except Exception as e:
        logger.error(f"Failed to score story {story_id}: {e}")
        stats.failed += 1
        return False


def run_backfill(
    dry_run: bool = False,
    batch_size: int = 100,
):
    """Run the backfill process."""
    logger.info("=" * 60)
    logger.info("MULTI-FACTOR SCORE BACKFILL")
    logger.info("=" * 60)
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    logger.info(f"Batch size: {batch_size}")

    # Initialize
    conn = get_db_connection()
    scorer = MultiFactorScorer()
    stats = BackfillStats()

    # Get total count
    total_unscored = get_total_unscored_count(conn)
    logger.info(f"Stories needing scores: {total_unscored}")

    if total_unscored == 0:
        logger.info("No stories need backfill. Exiting.")
        return

    # Process in batches
    offset = 0
    processed = 0

    while processed < total_unscored:
        logger.info(f"Processing batch at offset {offset}...")
        stories = get_stories_without_scores(conn, batch_size, offset)

        if not stories:
            break

        for story in stories:
            process_story(conn, story, scorer, stats, dry_run)
            processed += 1

            if processed % 10 == 0:
                logger.info(f"Processed {processed}/{total_unscored} stories...")

        # Commit after each batch (unless dry run)
        if not dry_run:
            conn.commit()

        offset += batch_size

    # Final commit
    if not dry_run:
        conn.commit()

    # Log summary
    stats.log_summary()

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill multi-factor scores for existing stories"
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
