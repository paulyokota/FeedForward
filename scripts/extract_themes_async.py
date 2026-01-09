#!/usr/bin/env python3
"""
Async theme extraction from classification results.

Optimized version that:
1. Reads existing classification results (skips Stage 1 - already done)
2. Runs theme extraction in parallel using asyncio
3. Reuses org_ids from classification output

~10-20x faster than sequential extract_themes_to_file.py

Usage:
    python scripts/extract_themes_async.py --max 1000
    python scripts/extract_themes_async.py --max 1000 --concurrency 30
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import AsyncOpenAI
from theme_extractor import ThemeExtractor
from db.models import Conversation

INPUT_FILE = Path(__file__).parent.parent / "data" / "classification_results.jsonl"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "theme_extraction_results.jsonl"


async def extract_theme_async(
    client: AsyncOpenAI,
    extractor: ThemeExtractor,
    record: dict,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Extract theme from a single record asynchronously."""
    async with semaphore:
        try:
            # Build Conversation object from classification result
            conv = Conversation(
                id=record["id"],
                created_at=datetime.fromisoformat(record["created_at"]),
                source_body=record["excerpt"],  # Use excerpt as source_body
                source_type="conversation",
                source_url=record.get("source_url"),
                contact_email=record.get("email"),
                # Map category to issue_type
                issue_type=map_category_to_issue_type(record["category"]),
                sentiment="neutral",
                priority="normal",
                churn_risk=False,
            )

            # Extract theme (this makes an LLM call)
            theme = await asyncio.to_thread(
                extractor.extract,
                conv=conv,
                strict_mode=False,
            )

            return {
                "id": record["id"],
                "issue_signature": theme.issue_signature,
                "product_area": theme.product_area,
                "component": theme.component,
                "user_intent": theme.user_intent,
                "symptoms": theme.symptoms,
                "affected_flow": theme.affected_flow,
                "root_cause_hypothesis": theme.root_cause_hypothesis,
                "excerpt": record["excerpt"],
                "created_at": record["created_at"],
                "email": record.get("email"),
                "user_id": record.get("user_id"),
                "org_id": record.get("org_id"),
                "intercom_url": record.get("intercom_url"),
                "jarvis_org_url": record.get("jarvis_org_url"),
                "jarvis_user_url": record.get("jarvis_user_url"),
            }
        except Exception as e:
            print(f"  Error extracting {record['id']}: {e}")
            return None


def map_category_to_issue_type(category: str) -> str:
    """Map classification category to IssueType for Conversation model."""
    mapping = {
        "product_issue": "bug_report",
        "how_to_question": "product_question",
        "feature_request": "feature_request",
        "billing_question": "billing",
        "account_issue": "account_access",
        "configuration_help": "product_question",
        "general_inquiry": "other",
        "spam": "other",
    }
    return mapping.get(category, "other")


async def main(max_records: int = 1000, concurrency: int = 20):
    """Run async theme extraction."""
    if not INPUT_FILE.exists():
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        print("Run classify_to_file.py first.")
        sys.exit(1)

    # Load classification results
    records = []
    with open(INPUT_FILE) as f:
        for line in f:
            r = json.loads(line)
            if r["category"] != "spam":  # Skip spam
                records.append(r)
            if len(records) >= max_records:
                break

    print(f"Extracting themes from {len(records)} conversations")
    print(f"Concurrency: {concurrency}")
    print(f"Output: {OUTPUT_FILE}")
    print("-" * 60)

    # Initialize extractor
    extractor = ThemeExtractor(model="gpt-4o-mini", use_vocabulary=True)
    client = AsyncOpenAI()
    semaphore = asyncio.Semaphore(concurrency)

    # Process in batches to show progress
    batch_size = 50
    all_results = []
    start_time = datetime.now()

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        tasks = [
            extract_theme_async(client, extractor, r, semaphore)
            for r in batch
        ]
        results = await asyncio.gather(*tasks)

        # Filter out None results (errors)
        valid_results = [r for r in results if r is not None]
        all_results.extend(valid_results)

        elapsed = (datetime.now() - start_time).total_seconds()
        rate = len(all_results) / elapsed if elapsed > 0 else 0
        print(f"Progress: {len(all_results)}/{len(records)} ({rate:.1f}/sec)")
        sys.stdout.flush()

    # Write results
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")

    elapsed = (datetime.now() - start_time).total_seconds()
    print("-" * 60)
    print(f"Done! {len(all_results)} themes extracted in {elapsed:.1f}s")
    print(f"Rate: {len(all_results) / elapsed:.1f} conversations/sec")

    # Summary
    from collections import Counter
    signatures = Counter(r["issue_signature"] for r in all_results)
    areas = Counter(r["product_area"] for r in all_results)

    print(f"\nTop Issue Signatures:")
    for sig, cnt in signatures.most_common(15):
        print(f"  {sig}: {cnt}")

    print(f"\nBy Product Area:")
    for area, cnt in areas.most_common():
        print(f"  {area}: {cnt}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Async theme extraction")
    parser.add_argument("--max", type=int, default=1000, help="Max records to process")
    parser.add_argument("--concurrency", type=int, default=20, help="Parallel requests")
    args = parser.parse_args()
    asyncio.run(main(max_records=args.max, concurrency=args.concurrency))
