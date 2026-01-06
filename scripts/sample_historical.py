#!/usr/bin/env python
"""
Sample historical conversations from Intercom for pattern analysis.

Fetches conversations across different time periods to establish baseline
patterns for theme escalation logic.
"""

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
from intercom_client import IntercomClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sampling configuration: (start_date, end_date, target_count, label)
SAMPLE_CONFIG = [
    ("2025-01-01", "2025-01-31", 40, "jan_2025"),
    ("2025-03-01", "2025-03-31", 40, "mar_2025"),
    ("2025-05-01", "2025-05-31", 40, "may_2025"),
    ("2025-07-01", "2025-07-31", 40, "jul_2025"),
    ("2025-09-01", "2025-09-30", 40, "sep_2025"),
    ("2025-10-01", "2025-10-31", 50, "oct_2025"),
    ("2025-11-01", "2025-11-30", 50, "nov_2025"),
    ("2025-12-01", "2025-12-31", 50, "dec_2025"),
    ("2026-01-01", "2026-01-06", 50, "jan_2026"),
]


def date_to_timestamp(date_str: str) -> int:
    """Convert date string to Unix timestamp."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp())


def get_existing_conversation_ids() -> set:
    """Get IDs of conversations already in database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM conversations")
                return {row[0] for row in cur.fetchall()}
    except Exception as e:
        logger.warning(f"Could not fetch existing IDs: {e}")
        return set()


def fetch_sample_for_period(
    client: IntercomClient,
    start_date: str,
    end_date: str,
    target_count: int,
    existing_ids: set,
) -> list:
    """Fetch a sample of quality conversations for a specific time period."""
    start_ts = date_to_timestamp(start_date)
    end_ts = date_to_timestamp(end_date)

    logger.info(f"Fetching up to {target_count} conversations from {start_date} to {end_date}")

    samples = []
    fetched = 0
    filtered = 0

    # Fetch more than needed to account for quality filtering
    max_fetch = target_count * 3

    for raw_conv in client.search_by_date_range(start_ts, end_ts, max_results=max_fetch):
        fetched += 1
        conv_id = str(raw_conv.get('id', ''))

        # Skip if already in database
        if conv_id in existing_ids:
            continue

        # Quality filter
        filter_result = client.quality_filter(raw_conv)
        if not filter_result.passed:
            filtered += 1
            continue

        # Parse and add
        parsed = client.parse_conversation(raw_conv)
        samples.append({
            'id': parsed.id,
            'created_at': parsed.created_at.isoformat(),
            'source_body': parsed.source_body,
            'source_type': parsed.source_type,
            'source_subject': parsed.source_subject,
            'contact_email': parsed.contact_email,
        })

        if len(samples) >= target_count:
            break

    logger.info(f"  Fetched: {fetched}, Filtered: {filtered}, Samples: {len(samples)}")
    return samples


def save_samples(samples: list, label: str, output_dir: Path) -> None:
    """Save samples to JSON file."""
    output_file = output_dir / f"sample_{label}.json"
    with open(output_file, 'w') as f:
        json.dump(samples, f, indent=2)
    logger.info(f"  Saved to {output_file}")


def main():
    """Run the historical sampling."""
    output_dir = Path(__file__).parent.parent / "data" / "historical_samples"
    output_dir.mkdir(parents=True, exist_ok=True)

    client = IntercomClient()
    existing_ids = get_existing_conversation_ids()
    logger.info(f"Found {len(existing_ids)} existing conversations in database")

    all_samples = []
    summary = []

    for start_date, end_date, target_count, label in SAMPLE_CONFIG:
        samples = fetch_sample_for_period(
            client, start_date, end_date, target_count, existing_ids
        )

        if samples:
            save_samples(samples, label, output_dir)
            all_samples.extend(samples)
            summary.append((label, len(samples)))

            # Track IDs to avoid duplicates across periods
            for s in samples:
                existing_ids.add(s['id'])

    # Save combined file
    combined_file = output_dir / "all_samples.json"
    with open(combined_file, 'w') as f:
        json.dump(all_samples, f, indent=2)

    # Print summary
    print("\n" + "=" * 50)
    print("SAMPLING COMPLETE")
    print("=" * 50)
    for label, count in summary:
        print(f"  {label}: {count}")
    print(f"\nTotal: {len(all_samples)} conversations")
    print(f"Output: {output_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
