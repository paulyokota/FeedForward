#!/usr/bin/env python
"""
Backfill historical conversations from Intercom.

Processes conversations newest-first in monthly batches to:
1. Minimize creation of tickets for old/resolved issues
2. Leverage 30-day recency filter for ticket creation
3. Allow incremental processing with resume capability

Usage:
    python scripts/backfill_historical.py [--months N] [--dry-run] [--resume]
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from classifier import classify_conversation
from db.models import Conversation
from db.connection import get_connection
from intercom_client import IntercomClient
from theme_extractor import ThemeExtractor
from theme_tracker import ThemeTracker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# State file for resume capability
STATE_FILE = Path(__file__).parent.parent / "data" / "backfill_state.json"


def load_state() -> dict:
    """Load backfill state from file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "last_processed_month": None,
        "months_completed": [],
        "total_processed": 0,
        "total_stored": 0,
        "total_themes": 0,
    }


def save_state(state: dict):
    """Save backfill state to file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """Get start and end datetime for a month."""
    start = datetime(year, month, 1)
    # Handle year rollover for end date
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def generate_months_newest_first(num_months: int) -> list[tuple[int, int]]:
    """Generate (year, month) tuples from current month backwards."""
    now = datetime.utcnow()
    months = []

    for i in range(num_months):
        # Calculate month offset
        year = now.year
        month = now.month - i

        # Handle year rollback
        while month <= 0:
            month += 12
            year -= 1

        months.append((year, month))

    return months


def classify_and_store(
    conv_data: dict,
    extractor: ThemeExtractor,
    tracker: ThemeTracker,
    dry_run: bool = False,
    strict_mode: bool = False,
) -> tuple[bool, bool]:
    """
    Classify a conversation and store it with theme extraction.

    Args:
        conv_data: Parsed conversation data
        extractor: Theme extractor instance
        tracker: Theme tracker instance
        dry_run: If True, don't actually store
        strict_mode: If True, force vocabulary-only matching

    Returns (stored, theme_extracted) booleans.
    """
    conv_id = conv_data['id']
    source_body = conv_data.get('source_body', '')

    if not source_body or len(source_body) < 20:
        return False, False

    # Prepare text for classification
    text = source_body
    if conv_data.get('source_subject'):
        text = f"Subject: {conv_data['source_subject']}\n\n{text}"

    try:
        # Classify
        result = classify_conversation(text)

        if dry_run:
            logger.info(f"[DRY RUN] Would classify {conv_id}: {result['issue_type']}")
            return True, True

        # Store conversation
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO conversations (
                        id, created_at, source_body, source_type, source_subject,
                        contact_email, contact_id, user_id, org_id,
                        issue_type, sentiment, churn_risk, priority
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    RETURNING id
                """, (
                    conv_id,
                    conv_data['created_at'],
                    conv_data.get('source_body'),
                    conv_data.get('source_type'),
                    conv_data.get('source_subject'),
                    conv_data.get('contact_email'),
                    conv_data.get('contact_id'),
                    conv_data.get('user_id'),
                    conv_data.get('org_id'),
                    result['issue_type'],
                    result['sentiment'],
                    result['churn_risk'],
                    result['priority'],
                ))
                stored = cur.fetchone() is not None

        if not stored:
            # Already exists
            return False, False

        # Extract theme
        conv = Conversation(
            id=conv_id,
            created_at=datetime.fromisoformat(str(conv_data['created_at'])),
            source_body=conv_data.get('source_body'),
            issue_type=result['issue_type'],
            sentiment=result['sentiment'],
            churn_risk=result['churn_risk'],
            priority=result['priority'],
        )

        theme = extractor.extract(conv, canonicalize=True, strict_mode=strict_mode)
        theme_stored = tracker.store_theme(theme)

        return True, theme_stored

    except Exception as e:
        logger.error(f"Error processing {conv_id}: {e}")
        return False, False


def process_month(
    client: IntercomClient,
    extractor: ThemeExtractor,
    tracker: ThemeTracker,
    year: int,
    month: int,
    max_per_month: int = None,
    dry_run: bool = False,
    strict_mode: bool = False,
) -> dict:
    """
    Process all conversations from a specific month.

    Returns stats dict with counts.
    """
    start, end = get_month_range(year, month)
    month_name = start.strftime("%Y-%m")

    logger.info(f"\n{'='*50}")
    logger.info(f"Processing {month_name}")
    logger.info(f"{'='*50}")

    stats = {
        "month": month_name,
        "fetched": 0,
        "filtered": 0,
        "stored": 0,
        "themes": 0,
        "errors": 0,
    }

    try:
        # Fetch conversations using date range search
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())

        for raw_conv in client.search_by_date_range(
            start_ts, end_ts,
            max_results=max_per_month
        ):
            stats["fetched"] += 1

            # Quality filter
            filter_result = client.quality_filter(raw_conv)
            if not filter_result.passed:
                stats["filtered"] += 1
                continue

            # Parse and process
            parsed = client.parse_conversation(raw_conv)

            # Fetch org_id from contact (requires extra API call)
            org_id = None
            if parsed.contact_id:
                org_id = client.fetch_contact_org_id(parsed.contact_id)

            conv_data = {
                'id': parsed.id,
                'created_at': parsed.created_at,
                'source_body': parsed.source_body,
                'source_type': parsed.source_type,
                'source_subject': parsed.source_subject,
                'contact_email': parsed.contact_email,
                'contact_id': parsed.contact_id,
                'user_id': parsed.user_id,
                'org_id': org_id,
            }

            stored, theme_extracted = classify_and_store(
                conv_data, extractor, tracker, dry_run, strict_mode
            )

            if stored:
                stats["stored"] += 1
            if theme_extracted:
                stats["themes"] += 1

            # Progress every 50
            if stats["fetched"] % 50 == 0:
                logger.info(
                    f"  Progress: {stats['fetched']} fetched, "
                    f"{stats['stored']} stored, {stats['themes']} themes"
                )

    except Exception as e:
        logger.error(f"Error processing {month_name}: {e}")
        stats["errors"] += 1

    logger.info(
        f"  {month_name} complete: {stats['stored']} stored, "
        f"{stats['themes']} themes ({stats['filtered']} filtered)"
    )

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical conversations from Intercom"
    )
    parser.add_argument(
        "--months", type=int, default=24,
        help="Number of months to backfill (default: 24)"
    )
    parser.add_argument(
        "--max-per-month", type=int, default=None,
        help="Max conversations per month (for testing)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't actually store data, just log what would happen"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last saved state"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Reset state and start fresh"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Use strict mode: force vocabulary-only theme matching (no new themes)"
    )

    args = parser.parse_args()

    # Handle state
    if args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("State reset.")

    state = load_state() if args.resume else {
        "last_processed_month": None,
        "months_completed": [],
        "total_processed": 0,
        "total_stored": 0,
        "total_themes": 0,
    }

    # Initialize clients
    print(f"\nBackfill Configuration:")
    print(f"  Months: {args.months}")
    print(f"  Max per month: {args.max_per_month or 'unlimited'}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Resume: {args.resume}")
    print(f"  Strict mode: {args.strict}")
    print()

    try:
        client = IntercomClient()
    except ValueError as e:
        print(f"Error: {e}")
        print("Set INTERCOM_ACCESS_TOKEN in .env")
        return 1

    extractor = ThemeExtractor()
    tracker = ThemeTracker()

    # Generate months to process (newest first)
    months = generate_months_newest_first(args.months)

    # Filter out already completed months if resuming
    if args.resume and state["months_completed"]:
        completed = set(state["months_completed"])
        months = [(y, m) for y, m in months if f"{y}-{m:02d}" not in completed]
        print(f"Resuming: {len(state['months_completed'])} months already done")
        print(f"Remaining: {len(months)} months")

    print(f"\nProcessing {len(months)} months (newest first)...")
    print("=" * 50)

    # Process each month
    for year, month in months:
        month_key = f"{year}-{month:02d}"

        stats = process_month(
            client, extractor, tracker,
            year, month,
            max_per_month=args.max_per_month,
            dry_run=args.dry_run,
            strict_mode=args.strict,
        )

        # Update state
        state["last_processed_month"] = month_key
        state["months_completed"].append(month_key)
        state["total_processed"] += stats["fetched"]
        state["total_stored"] += stats["stored"]
        state["total_themes"] += stats["themes"]

        # Save state after each month (for resume)
        if not args.dry_run:
            save_state(state)

    # Final summary
    print("\n" + "=" * 50)
    print("BACKFILL COMPLETE")
    print("=" * 50)
    print(f"  Total fetched: {state['total_processed']}")
    print(f"  Total stored: {state['total_stored']}")
    print(f"  Total themes: {state['total_themes']}")
    print(f"  Months processed: {len(state['months_completed'])}")
    print("=" * 50)

    # Show top themes
    if not args.dry_run:
        print("\nTop themes by occurrence:")
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT issue_signature, occurrence_count, product_area
                        FROM theme_aggregates
                        ORDER BY occurrence_count DESC
                        LIMIT 15
                    """)
                    for row in cur.fetchall():
                        print(f"  {row[1]:>3}x  {row[0]:<40} [{row[2]}]")
        except Exception as e:
            logger.error(f"Could not fetch theme summary: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
