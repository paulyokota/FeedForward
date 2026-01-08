#!/usr/bin/env python3
"""
Test URL context on live Intercom conversations.

This is a simpler validation approach that:
1. Fetches recent conversations from Intercom API
2. Filters for quality conversations with source.url
3. Runs theme extraction with URL context
4. Shows results for manual validation

No Shortcut integration required - just tests URL context feature.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.models import Conversation
from theme_extractor import ThemeExtractor
from intercom_client import IntercomClient


def test_url_context_on_live_data(days: int = 7, max_conversations: int = 20):
    """Fetch recent conversations and test URL context."""

    print("="*60)
    print("Testing URL Context on Live Intercom Data")
    print("="*60)

    # Initialize clients
    print(f"\n1. Initializing Intercom client...")
    intercom = IntercomClient()
    extractor = ThemeExtractor(use_vocabulary=True)

    # Fetch recent conversations
    print(f"\n2. Fetching conversations from last {days} days...")
    since = datetime.utcnow() - timedelta(days=days)

    conversations_fetched = 0
    conversations_with_url = []
    conversations_no_url = []

    for parsed, raw in intercom.fetch_quality_conversations(since=since, max_pages=5):
        conversations_fetched += 1

        if parsed.source_url:
            conversations_with_url.append((parsed, raw))
        else:
            conversations_no_url.append((parsed, raw))

        if len(conversations_with_url) >= max_conversations:
            break

    print(f"   Fetched {conversations_fetched} quality conversations")
    print(f"   - With URL: {len(conversations_with_url)}")
    print(f"   - Without URL: {len(conversations_no_url)}")

    if not conversations_with_url:
        print("\n   ⚠️  No conversations with URL found in recent data")
        print("   This is normal - not all conversations include source.url")
        return

    # Test URL context on conversations with URLs
    print(f"\n3. Testing URL context on {len(conversations_with_url)} conversations...")

    results_by_url = defaultdict(list)

    for parsed, raw in conversations_with_url[:max_conversations]:
        # Create conversation object
        conv = Conversation(
            id=parsed.id,
            created_at=parsed.created_at,
            source_body=parsed.source_body,
            source_url=parsed.source_url,
            source_type=parsed.source_type,
            source_subject=parsed.source_subject,
            contact_email=parsed.contact_email,
            contact_id=parsed.contact_id,
            issue_type="bug_report",  # Placeholder
            sentiment="neutral",
            churn_risk=False,
            priority="normal",
        )

        # Extract theme with URL context
        theme = extractor.extract(conv, strict_mode=True)

        # Group by URL pattern for analysis
        url_pattern = None
        for pattern in extractor.vocabulary._url_context_mapping.keys():
            if pattern in parsed.source_url:
                url_pattern = pattern
                break

        results_by_url[url_pattern or "other"].append({
            "url": parsed.source_url,
            "url_pattern": url_pattern,
            "product_area": theme.product_area,
            "theme": theme.issue_signature,
            "message_preview": parsed.source_body[:100] + "..." if parsed.source_body else "",
        })

    # Display results
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)

    for url_pattern in sorted(results_by_url.keys()):
        results = results_by_url[url_pattern]
        print(f"\n{url_pattern if url_pattern != 'other' else 'No matching pattern'} ({len(results)} conversations)")
        print("-" * 60)

        # Count product areas
        area_counts = defaultdict(int)
        for r in results:
            area_counts[r["product_area"]] += 1

        print(f"Product areas: {dict(area_counts)}")
        print()

        # Show samples
        for i, r in enumerate(results[:3]):
            print(f"  [{i+1}] {r['product_area']} / {r['theme']}")
            print(f"      URL: {r['url'][:70]}...")
            print(f"      Message: {r['message_preview'][:70]}...")
            print()

    # Summary
    total = sum(len(results) for results in results_by_url.values())
    matched = sum(len(results) for pattern, results in results_by_url.items() if pattern != "other")

    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total conversations tested: {total}")
    print(f"URL patterns matched: {matched}/{total} ({100*matched/total:.1f}%)")
    print(f"URL patterns found: {len([p for p in results_by_url.keys() if p != 'other'])}")

    if "other" in results_by_url:
        print(f"\nConversations with no matching pattern: {len(results_by_url['other'])}")
        print("(These URLs don't match any pattern in url_context_mapping)")


def main():
    parser = argparse.ArgumentParser(description="Test URL context on live Intercom data")
    parser.add_argument("--days", type=int, default=7, help="Days of history to fetch (default: 7)")
    parser.add_argument("--max", type=int, default=20, help="Max conversations to test (default: 20)")
    args = parser.parse_args()

    test_url_context_on_live_data(days=args.days, max_conversations=args.max)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    main()