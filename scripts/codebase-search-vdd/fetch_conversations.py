"""
Intercom conversation fetcher for VDD codebase search testing.

Fetches diverse conversations across product areas and classifies them
using keyword matching. Part of the Validation-Driven Development system
for testing codebase search logic quality.

Usage:
    python fetch_conversations.py --batch-size 35  # For baseline (from Intercom)
    python fetch_conversations.py --batch-size 18  # For iterations (from Intercom)
    python fetch_conversations.py --batch-size 35 --from-db  # From database (offline)
    python fetch_conversations.py --batch-size 35 --from-db --intercom-only  # Real Intercom only
"""

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.intercom_client import IntercomClient
from src.db.connection import get_connection


@dataclass
class ProductAreaClassification:
    """Result of keyword-based product area classification."""

    product_area: str
    confidence: float  # 0.0 to 1.0
    matched_keywords: list[str]


@dataclass
class FetchedConversation:
    """Conversation data for VDD testing."""

    conversation_id: str
    issue_summary: str
    product_area: str
    classification_confidence: float
    created_at: str
    source_url: Optional[str] = None
    matched_keywords: list[str] = None


class ProductAreaClassifier:
    """Classify conversations into product areas using keyword matching."""

    def __init__(self, product_areas: list[dict]):
        """
        Initialize classifier with product area definitions.

        Args:
            product_areas: List of dicts with "name" and "keywords" fields
        """
        self.product_areas = product_areas
        self.uncertain_threshold = 0.4  # Below this = uncertain

    def classify(self, text: str) -> ProductAreaClassification:
        """
        Classify text into a product area based on keyword matching.

        Args:
            text: The conversation text to classify

        Returns:
            ProductAreaClassification with area, confidence, and matched keywords
        """
        text_lower = text.lower()
        scores = {}
        matches = {}

        # Score each product area by keyword matches
        for area in self.product_areas:
            area_name = area["name"]
            keywords = area["keywords"]

            matched = [kw for kw in keywords if kw.lower() in text_lower]
            match_count = len(matched)

            # Simple scoring: normalize by keyword count
            # More sophisticated: could weight by keyword importance
            score = match_count / len(keywords) if keywords else 0.0

            scores[area_name] = score
            matches[area_name] = matched

        # Find best match
        if not scores or max(scores.values()) == 0:
            # No matches - uncertain
            return ProductAreaClassification(
                product_area="uncertain",
                confidence=0.0,
                matched_keywords=[],
            )

        best_area = max(scores, key=scores.get)
        confidence = scores[best_area]
        matched_keywords = matches[best_area]

        # Tag as uncertain if confidence is low
        if confidence < self.uncertain_threshold:
            product_area = "uncertain"
        else:
            product_area = best_area

        return ProductAreaClassification(
            product_area=product_area,
            confidence=confidence,
            matched_keywords=matched_keywords,
        )


class ConversationFetcher:
    """Fetch and classify Intercom conversations for VDD testing."""

    def __init__(self, config_path: str):
        """
        Initialize fetcher with config.

        Args:
            config_path: Path to config.json with product area definitions
        """
        with open(config_path) as f:
            self.config = json.load(f)

        self.client = IntercomClient()
        self.classifier = ProductAreaClassifier(self.config["product_areas"])

    def extract_issue_summary(self, body: str) -> str:
        """
        Extract customer issue/symptom from conversation body.

        For VDD testing, we need concise issue descriptions that capture
        the customer's problem without excessive detail.

        Args:
            body: Full conversation body text

        Returns:
            Truncated/cleaned issue summary (max 300 chars)
        """
        # Take first 300 chars as summary
        # More sophisticated: could use sentence boundaries
        summary = body[:300].strip()

        # Add ellipsis if truncated
        if len(body) > 300:
            # Try to break at word boundary
            last_space = summary.rfind(" ")
            if last_space > 200:  # Don't break too early
                summary = summary[:last_space]
            summary = summary.rstrip() + " ..."

        return summary

    def fetch_recent_conversations(
        self,
        batch_size: int,
        days_back: int = 30,
        max_api_pages: int = 10,
    ) -> list[FetchedConversation]:
        """
        Fetch recent conversations with lightweight diversity sampling.

        Optimized for speed:
        - Limits API pagination to avoid long waits
        - Simplified diversity: only light balancing, no strict enforcement
        - Early exit when batch is full

        Args:
            batch_size: Number of conversations to fetch
            days_back: How far back to look for conversations
            max_api_pages: Maximum API pages to fetch (avoids infinite pagination)

        Returns:
            List of FetchedConversation objects
        """
        since = datetime.utcnow() - timedelta(days=days_back)

        fetched = []
        area_counts = {area["name"]: 0 for area in self.config["product_areas"]}
        area_counts["uncertain"] = 0

        # Soft target for diversity (not enforced strictly)
        num_areas = len(self.config["product_areas"]) + 1
        soft_cap_per_area = max(3, (batch_size * 2) // num_areas)

        print(f"Fetching up to {batch_size} conversations from last {days_back} days...", file=sys.stderr)
        print(f"  (max {max_api_pages} API pages, soft cap {soft_cap_per_area}/area)", file=sys.stderr)

        # Fetch with pagination limit for speed
        conversations_seen = 0
        for parsed, _ in self.client.fetch_quality_conversations(
            since=since,
            max_pages=max_api_pages
        ):
            conversations_seen += 1

            # Early exit when we have enough
            if len(fetched) >= batch_size:
                break

            # Extract issue summary
            issue_summary = self.extract_issue_summary(parsed.source_body)

            # Classify
            classification = self.classifier.classify(parsed.source_body)
            area = classification.product_area

            # Light diversity: only skip if an area is heavily over-represented
            # AND we still have room to be picky
            if area_counts[area] >= soft_cap_per_area and len(fetched) < batch_size * 0.9:
                # Skip this one, but don't be too strict - keep 1 in 3
                if conversations_seen % 3 != 0:
                    continue

            # Add conversation
            conv = FetchedConversation(
                conversation_id=parsed.id,
                issue_summary=issue_summary,
                product_area=classification.product_area,
                classification_confidence=classification.confidence,
                created_at=parsed.created_at.isoformat(),
                source_url=parsed.source_url,
                matched_keywords=classification.matched_keywords,
            )

            fetched.append(conv)
            area_counts[area] += 1

            # Progress indicator
            if len(fetched) % 5 == 0:
                print(f"  Fetched {len(fetched)}/{batch_size}...", file=sys.stderr)

        # Log results
        print(f"\nFetched {len(fetched)} conversations (saw {conversations_seen})", file=sys.stderr)
        print("Distribution by product area:", file=sys.stderr)
        for area, count in sorted(area_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                pct = count / len(fetched) * 100 if fetched else 0
                print(f"  {area}: {count} ({pct:.0f}%)", file=sys.stderr)

        return fetched

    def fetch_and_output(self, batch_size: int, days_back: int = 30):
        """
        Fetch conversations and output as JSON to stdout.

        Args:
            batch_size: Number of conversations to fetch
            days_back: How far back to look
        """
        conversations = self.fetch_recent_conversations(batch_size, days_back)

        # Convert to dict for JSON serialization
        output = [
            {
                "conversation_id": c.conversation_id,
                "issue_summary": c.issue_summary,
                "product_area": c.product_area,
                "classification_confidence": c.classification_confidence,
                "created_at": c.created_at,
                "source_url": c.source_url,
                "matched_keywords": c.matched_keywords,
            }
            for c in conversations
        ]

        # Output to stdout as JSON
        print(json.dumps(output, indent=2))


class DatabaseConversationFetcher:
    """Fetch conversations from the local database for offline VDD testing."""

    # Mapping from database stage1_type to VDD product areas
    TYPE_TO_PRODUCT_AREA = {
        "product_issue": "core_product",
        "how_to_question": "documentation",
        "feature_request": "feature_requests",
        "account_issue": "account_management",
        "billing_question": "billing",
        "configuration_help": "integrations",
        "general_inquiry": "uncertain",
        "spam": "uncertain",
    }

    def __init__(self, config_path: str, intercom_only: bool = False):
        """
        Initialize fetcher with config.

        Args:
            config_path: Path to config.json with product area definitions
            intercom_only: If True, exclude Coda imports (research data)
        """
        with open(config_path) as f:
            self.config = json.load(f)

        self.classifier = ProductAreaClassifier(self.config["product_areas"])
        self.intercom_only = intercom_only

    def extract_issue_summary(self, body: str) -> str:
        """
        Extract customer issue/symptom from conversation body.

        Args:
            body: Full conversation body text

        Returns:
            Truncated/cleaned issue summary (max 300 chars)
        """
        summary = body[:300].strip()

        if len(body) > 300:
            last_space = summary.rfind(" ")
            if last_space > 200:
                summary = summary[:last_space]
            summary = summary.rstrip() + " ..."

        return summary

    def fetch_from_database(
        self,
        batch_size: int,
        days_back: int = 30,
        intercom_only: bool = False,
    ) -> list[FetchedConversation]:
        """
        Fetch conversations from the database.

        Uses pre-classified conversations stored in PostgreSQL.
        Falls back to keyword classification if stage1_type is not set.

        Args:
            batch_size: Number of conversations to fetch
            days_back: How far back to look for conversations
            intercom_only: If True, exclude Coda imports (research data)

        Returns:
            List of FetchedConversation objects
        """
        since = datetime.utcnow() - timedelta(days=days_back)

        mode_str = "real Intercom only" if intercom_only else "all sources"
        print(f"Fetching up to {batch_size} conversations from database ({mode_str}, last {days_back} days)...", file=sys.stderr)

        # Query conversations with source_body from database
        if intercom_only:
            # Exclude Coda imports (research/interview data)
            query = """
                SELECT id, source_body, source_url, created_at, stage1_type
                FROM conversations
                WHERE source_body IS NOT NULL
                  AND LENGTH(source_body) > 50
                  AND created_at >= %s
                  AND id NOT LIKE 'coda_%%'
                ORDER BY RANDOM()
                LIMIT %s
            """
        else:
            query = """
                SELECT id, source_body, source_url, created_at, stage1_type
                FROM conversations
                WHERE source_body IS NOT NULL
                  AND LENGTH(source_body) > 50
                  AND created_at >= %s
                ORDER BY RANDOM()
                LIMIT %s
            """

        fetched = []
        area_counts = {area["name"]: 0 for area in self.config["product_areas"]}
        area_counts["uncertain"] = 0

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (since, batch_size * 3))  # Fetch extra for diversity
                rows = cur.fetchall()

        print(f"  Found {len(rows)} candidates in database", file=sys.stderr)

        # Soft target for diversity
        num_areas = len(self.config["product_areas"]) + 1
        soft_cap_per_area = max(3, (batch_size * 2) // num_areas)

        for row in rows:
            if len(fetched) >= batch_size:
                break

            conv_id, source_body, source_url, created_at, stage1_type = row

            # Extract issue summary
            issue_summary = self.extract_issue_summary(source_body)

            # Determine product area
            if stage1_type and stage1_type in self.TYPE_TO_PRODUCT_AREA:
                # Use existing classification
                product_area = self.TYPE_TO_PRODUCT_AREA[stage1_type]
                classification_confidence = 0.8  # Assume reasonable confidence
                matched_keywords = []
            else:
                # Fall back to keyword classification
                classification = self.classifier.classify(source_body)
                product_area = classification.product_area
                classification_confidence = classification.confidence
                matched_keywords = classification.matched_keywords

            # Light diversity balancing
            if area_counts.get(product_area, 0) >= soft_cap_per_area and len(fetched) < batch_size * 0.9:
                if random.random() > 0.33:  # Skip 2/3 of over-represented areas
                    continue

            conv = FetchedConversation(
                conversation_id=conv_id,
                issue_summary=issue_summary,
                product_area=product_area,
                classification_confidence=classification_confidence,
                created_at=created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at),
                source_url=source_url,
                matched_keywords=matched_keywords,
            )

            fetched.append(conv)
            area_counts[product_area] = area_counts.get(product_area, 0) + 1

            # Progress indicator
            if len(fetched) % 5 == 0:
                print(f"  Fetched {len(fetched)}/{batch_size}...", file=sys.stderr)

        # Log results
        print(f"\nFetched {len(fetched)} conversations from database", file=sys.stderr)
        print("Distribution by product area:", file=sys.stderr)
        for area, count in sorted(area_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                pct = count / len(fetched) * 100 if fetched else 0
                print(f"  {area}: {count} ({pct:.0f}%)", file=sys.stderr)

        return fetched

    def fetch_and_output(self, batch_size: int, days_back: int = 30):
        """
        Fetch conversations from database and output as JSON to stdout.

        Args:
            batch_size: Number of conversations to fetch
            days_back: How far back to look
        """
        conversations = self.fetch_from_database(batch_size, days_back, self.intercom_only)

        # Convert to dict for JSON serialization
        output = [
            {
                "conversation_id": c.conversation_id,
                "issue_summary": c.issue_summary,
                "product_area": c.product_area,
                "classification_confidence": c.classification_confidence,
                "created_at": c.created_at,
                "source_url": c.source_url,
                "matched_keywords": c.matched_keywords,
            }
            for c in conversations
        ]

        # Output to stdout as JSON
        print(json.dumps(output, indent=2))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch Intercom conversations for VDD codebase search testing"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        required=True,
        help="Number of conversations to fetch (35 for baseline, 18 for iterations)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="How far back to look for conversations (default: 30 days)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json (default: scripts/codebase-search-vdd/config.json)",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Fetch from local database instead of Intercom API (offline mode)",
    )
    parser.add_argument(
        "--intercom-only",
        action="store_true",
        help="When using --from-db, exclude Coda imports (research data) and only use real Intercom conversations",
    )

    args = parser.parse_args()

    # Determine config path
    if args.config:
        config_path = args.config
    else:
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.json"

    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Choose fetcher based on mode
    if args.from_db:
        # Database mode - no Intercom token needed
        mode_desc = "database mode (offline)"
        if args.intercom_only:
            mode_desc += ", real Intercom only"
        print(f"Using {mode_desc}", file=sys.stderr)
        fetcher = DatabaseConversationFetcher(str(config_path), intercom_only=args.intercom_only)
    else:
        # Intercom mode - requires token
        if not os.getenv("INTERCOM_ACCESS_TOKEN"):
            print("Error: INTERCOM_ACCESS_TOKEN not set", file=sys.stderr)
            print("Hint: Use --from-db to fetch from local database instead", file=sys.stderr)
            sys.exit(1)
        fetcher = ConversationFetcher(str(config_path))

    # Fetch and output
    fetcher.fetch_and_output(args.batch_size, args.days_back)


if __name__ == "__main__":
    main()
