#!/usr/bin/env python3
"""
Timing script for Issue #152: Measure canonicalization throughput.

Runs a batch of conversations through theme extraction and measures
time to identify runtime impact of serializing canonicalization.

Usage:
    python scripts/timing_canonicalization.py --count 20 --concurrency 5
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.connection import get_connection
from src.db.models import Conversation
from src.theme_extractor import ThemeExtractor
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_timing_test(count: int, concurrency: int) -> dict:
    """
    Run timing test for theme extraction.

    Returns dict with timing metrics.
    """
    # Fetch recent conversations that have themes (known to work)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT c.id, c.created_at, c.source_body, c.source_url,
                       COALESCE(c.stage2_type, c.stage1_type) as issue_type,
                       c.sentiment, c.priority, c.churn_risk,
                       c.support_insights->>'customer_digest' as customer_digest,
                       c.support_insights->>'full_conversation' as full_conversation
                FROM conversations c
                JOIN themes t ON t.conversation_id = c.id
                WHERE c.source_body IS NOT NULL
                  AND LENGTH(c.source_body) > 50
                ORDER BY c.created_at DESC
                LIMIT %s
            """, (count,))
            rows = cur.fetchall()

    if not rows:
        logger.error("No conversations found for timing test")
        return {"error": "No conversations found"}

    logger.info(f"Loaded {len(rows)} conversations for timing test")

    # Map types
    NEW_TO_LEGACY_TYPE = {
        "product_issue": "bug_report",
        "feature_request": "feature_request",
        "how_to_question": "product_question",
    }

    # Build conversation objects
    conversations = []
    conversation_digests = {}
    conversation_full_texts = {}

    for row in rows:
        new_type = row.get("issue_type") or "other"
        legacy_type = NEW_TO_LEGACY_TYPE.get(new_type, "other")

        conv = Conversation(
            id=row["id"],
            created_at=row["created_at"],
            source_body=row["source_body"],
            source_url=row.get("source_url"),
            issue_type=legacy_type,
            sentiment=row.get("sentiment") or "neutral",
            priority=row.get("priority") or "normal",
            churn_risk=row.get("churn_risk") or False,
        )
        conversations.append(conv)

        if row.get("customer_digest"):
            conversation_digests[row["id"]] = row["customer_digest"]
        if row.get("full_conversation"):
            conversation_full_texts[row["id"]] = row["full_conversation"]

    # Create extractor and semaphore
    extractor = ThemeExtractor()
    extractor.clear_session_signatures()
    semaphore = asyncio.Semaphore(concurrency)

    extraction_times = []

    async def extract_one(conv: Conversation) -> float:
        """Extract theme and return time taken."""
        async with semaphore:
            start = time.perf_counter()
            try:
                customer_digest = conversation_digests.get(conv.id)
                full_conversation = conversation_full_texts.get(conv.id)

                await extractor.extract_async(
                    conv,
                    strict_mode=False,
                    customer_digest=customer_digest,
                    full_conversation=full_conversation,
                    use_full_conversation=True,
                )

                elapsed = time.perf_counter() - start
                return elapsed
            except Exception as e:
                logger.warning(f"Extraction failed for {conv.id}: {e}")
                return time.perf_counter() - start

    # Run all extractions
    logger.info(f"Starting {len(conversations)} extractions with concurrency={concurrency}")

    overall_start = time.perf_counter()
    tasks = [extract_one(conv) for conv in conversations]
    extraction_times = await asyncio.gather(*tasks)
    overall_elapsed = time.perf_counter() - overall_start

    # Calculate metrics
    valid_times = [t for t in extraction_times if t is not None]

    metrics = {
        "count": len(conversations),
        "concurrency": concurrency,
        "total_time_seconds": round(overall_elapsed, 2),
        "throughput_per_minute": round(len(conversations) / (overall_elapsed / 60), 1),
        "avg_extraction_seconds": round(sum(valid_times) / len(valid_times), 2) if valid_times else 0,
        "min_extraction_seconds": round(min(valid_times), 2) if valid_times else 0,
        "max_extraction_seconds": round(max(valid_times), 2) if valid_times else 0,
    }

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Time canonicalization throughput")
    parser.add_argument("--count", type=int, default=20, help="Number of conversations")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent extractions")
    args = parser.parse_args()

    logger.info(f"=== Canonicalization Timing Test ===")
    logger.info(f"Count: {args.count}, Concurrency: {args.concurrency}")

    metrics = asyncio.run(run_timing_test(args.count, args.concurrency))

    print("\n" + "=" * 50)
    print("TIMING RESULTS")
    print("=" * 50)
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    print("=" * 50)

    return metrics


if __name__ == "__main__":
    main()
