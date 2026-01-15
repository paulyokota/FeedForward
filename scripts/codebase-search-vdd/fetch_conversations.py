"""
Intercom conversation fetcher for VDD codebase search testing.

Fetches diverse conversations across product areas and classifies them
using keyword matching. Part of the Validation-Driven Development system
for testing codebase search logic quality.

Usage:
    python fetch_conversations.py --batch-size 35  # For baseline
    python fetch_conversations.py --batch-size 18  # For iterations
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.intercom_client import IntercomClient


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

    # Check for Intercom token
    if not os.getenv("INTERCOM_ACCESS_TOKEN"):
        print("Error: INTERCOM_ACCESS_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    # Fetch and output
    fetcher = ConversationFetcher(str(config_path))
    fetcher.fetch_and_output(args.batch_size, args.days_back)


if __name__ == "__main__":
    main()
