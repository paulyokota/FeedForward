"""
FeedForward batch pipeline.

Orchestrates: Intercom fetch → Quality filter → Classify → Store to PostgreSQL

Usage:
    python -m src.pipeline --days 7
    python -m src.pipeline --since 2024-01-01 --until 2024-01-07
"""

import argparse
import os
from pathlib import Path

# Load .env file if present
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
import logging
from datetime import datetime, timedelta
from typing import Optional

from .classifier import classify_conversation
from .intercom_client import IntercomClient, IntercomConversation
from .db.models import Conversation, PipelineRun
from .db.connection import (
    init_db,
    bulk_upsert_conversations,
    create_pipeline_run,
    update_pipeline_run,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CLASSIFIER_VERSION = "v1"


def run_pipeline(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    days: Optional[int] = None,
    dry_run: bool = False,
    max_conversations: Optional[int] = None,
) -> PipelineRun:
    """
    Run the full classification pipeline.

    Args:
        since: Start date for conversations
        until: End date for conversations
        days: Alternative to since/until - fetch last N days
        dry_run: If True, don't write to database
        max_conversations: Limit number of conversations to process

    Returns:
        PipelineRun with results
    """
    # Resolve date range
    if days:
        until = datetime.utcnow()
        since = until - timedelta(days=days)
    elif not since:
        # Default to last 7 days
        until = datetime.utcnow()
        since = until - timedelta(days=7)

    logger.info(f"Starting pipeline: {since} to {until}")

    # Create pipeline run record
    run = PipelineRun(
        date_from=since,
        date_to=until,
        status="running",
    )

    if not dry_run:
        try:
            init_db()
            run.id = create_pipeline_run(run)
            logger.info(f"Created pipeline run #{run.id}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    try:
        # Fetch and process conversations
        client = IntercomClient()
        conversations_to_store: list[Conversation] = []

        fetched_count = 0
        filtered_count = 0
        classified_count = 0

        logger.info("Fetching conversations from Intercom...")

        for raw_conv in client.fetch_conversations(since=since, until=until):
            fetched_count += 1

            # Quality filter
            filter_result = client.quality_filter(raw_conv)
            if not filter_result.passed:
                filtered_count += 1
                continue

            # Parse conversation
            parsed = client.parse_conversation(raw_conv)

            # Classify
            try:
                classification = classify_conversation(parsed.source_body)
                classified_count += 1

                # Build conversation record
                conv = Conversation(
                    id=parsed.id,
                    created_at=parsed.created_at,
                    source_body=parsed.source_body,
                    source_type=parsed.source_type,
                    source_subject=parsed.source_subject,
                    contact_email=parsed.contact_email,
                    contact_id=parsed.contact_id,
                    issue_type=classification["issue_type"],
                    sentiment=classification["sentiment"],
                    churn_risk=classification["churn_risk"],
                    priority=classification["priority"],
                    classifier_version=CLASSIFIER_VERSION,
                )
                conversations_to_store.append(conv)

                if classified_count % 10 == 0:
                    logger.info(f"Classified {classified_count} conversations...")

            except Exception as e:
                logger.warning(f"Failed to classify conversation {parsed.id}: {e}")

            # Check limit
            if max_conversations and classified_count >= max_conversations:
                logger.info(f"Reached max conversations limit ({max_conversations})")
                break

        # Store to database
        stored_count = 0
        if not dry_run and conversations_to_store:
            logger.info(f"Storing {len(conversations_to_store)} conversations...")
            stored_count = bulk_upsert_conversations(conversations_to_store)

        # Update run record
        run.completed_at = datetime.utcnow()
        run.conversations_fetched = fetched_count
        run.conversations_filtered = filtered_count
        run.conversations_classified = classified_count
        run.conversations_stored = stored_count
        run.status = "completed"

        if not dry_run and run.id:
            update_pipeline_run(run)

        # Log summary
        logger.info("=" * 50)
        logger.info("Pipeline completed!")
        logger.info(f"  Fetched:    {fetched_count}")
        logger.info(f"  Filtered:   {filtered_count} ({filtered_count/max(fetched_count,1)*100:.0f}%)")
        logger.info(f"  Classified: {classified_count}")
        logger.info(f"  Stored:     {stored_count}")
        logger.info("=" * 50)

        return run

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        run.completed_at = datetime.utcnow()
        run.status = "failed"
        run.error_message = str(e)

        if not dry_run and run.id:
            update_pipeline_run(run)

        raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run FeedForward classification pipeline"
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Fetch conversations from last N days",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        type=str,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database",
    )
    parser.add_argument(
        "--max",
        type=int,
        dest="max_conversations",
        help="Maximum conversations to process",
    )

    args = parser.parse_args()

    # Parse dates
    since = None
    until = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")
    if args.until:
        until = datetime.strptime(args.until, "%Y-%m-%d")

    run_pipeline(
        since=since,
        until=until,
        days=args.days,
        dry_run=args.dry_run,
        max_conversations=args.max_conversations,
    )


if __name__ == "__main__":
    main()
