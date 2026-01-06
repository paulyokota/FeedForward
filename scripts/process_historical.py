#!/usr/bin/env python
"""
Process historical samples: classify and extract themes.

Runs the full pipeline on sampled historical conversations.
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

from classifier import classify_conversation, ClassificationResult
from db.models import Conversation
from db.connection import get_connection
from theme_extractor import ThemeExtractor
from theme_tracker import ThemeTracker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_samples(samples_dir: Path) -> list:
    """Load all samples from JSON files."""
    combined_file = samples_dir / "all_samples.json"
    if combined_file.exists():
        with open(combined_file) as f:
            return json.load(f)
    return []


def classify_sample(sample: dict) -> dict:
    """Classify a single sample."""
    text = sample.get('source_body', '')
    if sample.get('source_subject'):
        text = f"Subject: {sample['source_subject']}\n\n{text}"

    result = classify_conversation(text)
    return {
        'issue_type': result['issue_type'],
        'sentiment': result['sentiment'],
        'churn_risk': result['churn_risk'],
        'priority': result['priority'],
    }


def store_conversation(sample: dict, classification: dict) -> bool:
    """Store classified conversation in database."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO conversations (
                        id, created_at, source_body, source_type, source_subject,
                        contact_email, issue_type, sentiment, churn_risk, priority
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    RETURNING id
                """, (
                    sample['id'],
                    sample['created_at'],
                    sample.get('source_body'),
                    sample.get('source_type'),
                    sample.get('source_subject'),
                    sample.get('contact_email'),
                    classification['issue_type'],
                    classification['sentiment'],
                    classification['churn_risk'],
                    classification['priority'],
                ))
                return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Failed to store {sample['id']}: {e}")
        return False


def main():
    samples_dir = Path(__file__).parent.parent / "data" / "historical_samples"
    samples = load_samples(samples_dir)

    if not samples:
        print("No samples found. Run sample_historical.py first.")
        return

    print(f"\nProcessing {len(samples)} historical samples...")
    print("=" * 50)

    extractor = ThemeExtractor()
    tracker = ThemeTracker()

    # Stats
    classified = 0
    stored = 0
    themes_extracted = 0
    errors = 0

    # Process in batches for progress visibility
    batch_size = 10

    for i in range(0, len(samples), batch_size):
        batch = samples[i:i+batch_size]

        for sample in batch:
            try:
                # Classify
                classification = classify_sample(sample)
                classified += 1

                # Store
                if store_conversation(sample, classification):
                    stored += 1

                    # Extract theme
                    conv = Conversation(
                        id=sample['id'],
                        created_at=datetime.fromisoformat(sample['created_at']),
                        source_body=sample.get('source_body'),
                        issue_type=classification['issue_type'],
                        sentiment=classification['sentiment'],
                        churn_risk=classification['churn_risk'],
                        priority=classification['priority'],
                    )

                    theme = extractor.extract(conv, canonicalize=True)
                    if tracker.store_theme(theme):
                        themes_extracted += 1

            except Exception as e:
                logger.error(f"Error processing {sample.get('id', 'unknown')}: {e}")
                errors += 1

        # Progress
        progress = min(i + batch_size, len(samples))
        print(f"Progress: {progress}/{len(samples)} ({100*progress/len(samples):.0f}%)")

    # Summary
    print("\n" + "=" * 50)
    print("PROCESSING COMPLETE")
    print("=" * 50)
    print(f"  Classified: {classified}")
    print(f"  Stored: {stored}")
    print(f"  Themes extracted: {themes_extracted}")
    print(f"  Errors: {errors}")
    print("=" * 50)

    # Show theme summary
    print("\nTop themes by occurrence:")
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


if __name__ == "__main__":
    main()
