#!/usr/bin/env python
"""
FeedForward CLI - View themes, tickets, and reports.

Usage:
    python src/cli.py themes          # List all themes
    python src/cli.py trending        # Show trending themes
    python src/cli.py ticket <sig>    # Preview ticket for issue signature
    python src/cli.py extract <id>    # Extract theme from conversation ID
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from db.connection import get_connection
from db.models import Conversation
from theme_extractor import ThemeExtractor, format_theme_for_ticket
from theme_tracker import ThemeTracker, generate_ticket_content, ThemeAggregate

logging.basicConfig(level=logging.WARNING)


def cmd_themes(args):
    """List all themes."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.issue_signature, t.product_area, t.component,
                       COUNT(*) as count, MAX(t.extracted_at) as last_seen
                FROM themes t
                GROUP BY t.issue_signature, t.product_area, t.component
                ORDER BY count DESC, last_seen DESC
                LIMIT %s
            """, (args.limit,))
            rows = cur.fetchall()

    if not rows:
        print("No themes found.")
        return

    print(f"\n{'Issue Signature':<40} {'Area':<20} {'Component':<15} {'Count':<6}")
    print("-" * 85)
    for row in rows:
        print(f"{row[0]:<40} {row[1]:<20} {row[2]:<15} {row[3]:<6}")
    print()


def cmd_trending(args):
    """Show trending themes with ticket previews."""
    tracker = ThemeTracker()
    themes = tracker.get_trending_themes(days=args.days, min_occurrences=args.min)

    if not themes:
        print(f"\nNo trending themes (2+ occurrences) in the last {args.days} days.\n")

        # Show all themes instead
        print("All themes:")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT issue_signature, product_area, component, occurrence_count
                    FROM theme_aggregates
                    ORDER BY occurrence_count DESC
                    LIMIT 10
                """)
                for row in cur.fetchall():
                    print(f"  - {row[0]} ({row[3]}x) [{row[1]}/{row[2]}]")
        return

    print(f"\n# Trending Themes (Last {args.days} Days)\n")

    for agg in themes:
        ticket_badge = " ✓ ticket" if agg.ticket_created else ""
        print(f"## {agg.issue_signature} ({agg.occurrence_count}x){ticket_badge}")
        print(f"   Product: {agg.product_area} → {agg.component}")
        print(f"   First: {agg.first_seen_at.strftime('%Y-%m-%d')} | Last: {agg.last_seen_at.strftime('%Y-%m-%d')}")

        if args.verbose:
            print(f"\n{generate_ticket_content(tracker, agg.issue_signature)}")
        print()


def cmd_ticket(args):
    """Preview ticket content for an issue signature."""
    tracker = ThemeTracker()

    # Try exact match first
    agg = tracker.get_aggregate(args.signature)

    if agg is None:
        # Try partial match
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT issue_signature FROM theme_aggregates
                    WHERE issue_signature ILIKE %s
                    LIMIT 5
                """, (f"%{args.signature}%",))
                matches = [row[0] for row in cur.fetchall()]

        if matches:
            print(f"Theme '{args.signature}' not found. Did you mean:")
            for m in matches:
                print(f"  - {m}")
        else:
            print(f"Theme '{args.signature}' not found.")
        return

    print(f"\n{'=' * 70}")
    print(f"TICKET PREVIEW: {agg.issue_signature}")
    print(f"{'=' * 70}\n")

    content = generate_ticket_content(tracker, agg.issue_signature)
    print(content)

    # Show metadata
    print(f"\n{'=' * 70}")
    print("METADATA")
    print(f"{'=' * 70}")
    print(f"  Occurrences: {agg.occurrence_count}")
    print(f"  First seen:  {agg.first_seen_at}")
    print(f"  Last seen:   {agg.last_seen_at}")
    print(f"  Ticket:      {'Created (' + agg.ticket_id + ')' if agg.ticket_created else 'Not created'}")

    if agg.affected_conversations:
        print(f"  Conversations: {', '.join(agg.affected_conversations[:5])}")
        if len(agg.affected_conversations) > 5:
            print(f"                 ... and {len(agg.affected_conversations) - 5} more")


def cmd_extract(args):
    """Extract and display theme for a conversation."""
    # Fetch conversation from database
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, created_at, source_body, issue_type, sentiment, churn_risk, priority
                FROM conversations
                WHERE id = %s
            """, (args.id,))
            row = cur.fetchone()

    if row is None:
        print(f"Conversation {args.id} not found in database.")
        return

    conv = Conversation(
        id=row[0],
        created_at=row[1],
        source_body=row[2],
        issue_type=row[3],
        sentiment=row[4],
        churn_risk=row[5],
        priority=row[6],
    )

    print(f"\n{'=' * 70}")
    print(f"CONVERSATION: {conv.id}")
    print(f"{'=' * 70}")
    print(f"Type: {conv.issue_type} | Sentiment: {conv.sentiment} | Priority: {conv.priority}")
    print(f"\nMessage:\n{conv.source_body[:500]}{'...' if len(conv.source_body or '') > 500 else ''}")

    print(f"\n{'=' * 70}")
    print("EXTRACTING THEME...")
    print(f"{'=' * 70}\n")

    extractor = ThemeExtractor()
    theme = extractor.extract(conv)

    print(format_theme_for_ticket(theme))

    if args.store:
        tracker = ThemeTracker()
        stored = tracker.store_theme(theme)
        print(f"\n[{'Stored' if stored else 'Already exists'}]")


def cmd_preview_all(args):
    """Preview all pending tickets."""
    tracker = ThemeTracker(ticket_threshold=args.threshold)
    needing = tracker.get_themes_needing_tickets()

    if not needing:
        print(f"\nNo themes have reached the ticket threshold ({args.threshold}).\n")

        # Show themes approaching threshold
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT issue_signature, occurrence_count
                    FROM theme_aggregates
                    WHERE ticket_created = FALSE
                    ORDER BY occurrence_count DESC
                    LIMIT 5
                """)
                approaching = cur.fetchall()

        if approaching:
            print("Themes approaching threshold:")
            for sig, count in approaching:
                print(f"  - {sig}: {count}/{args.threshold}")
        return

    print(f"\n# {len(needing)} Themes Ready for Tickets\n")

    for agg in needing:
        print("=" * 70)
        print(generate_ticket_content(tracker, agg.issue_signature))
        print()


def main():
    parser = argparse.ArgumentParser(
        description="FeedForward CLI - View themes and tickets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/cli.py themes                    # List all themes
  python src/cli.py trending -d 30            # Trending in last 30 days
  python src/cli.py trending -v               # With full ticket content
  python src/cli.py ticket pins_not_posting   # Preview specific ticket
  python src/cli.py pending                   # Show all pending tickets
  python src/cli.py extract CONV_ID --store   # Extract & store theme
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # themes
    p_themes = subparsers.add_parser("themes", help="List all themes")
    p_themes.add_argument("-l", "--limit", type=int, default=20, help="Limit results")
    p_themes.set_defaults(func=cmd_themes)

    # trending
    p_trending = subparsers.add_parser("trending", help="Show trending themes")
    p_trending.add_argument("-d", "--days", type=int, default=7, help="Time window in days")
    p_trending.add_argument("-m", "--min", type=int, default=2, help="Min occurrences")
    p_trending.add_argument("-v", "--verbose", action="store_true", help="Show full ticket content")
    p_trending.set_defaults(func=cmd_trending)

    # ticket
    p_ticket = subparsers.add_parser("ticket", help="Preview ticket for issue signature")
    p_ticket.add_argument("signature", help="Issue signature (partial match OK)")
    p_ticket.set_defaults(func=cmd_ticket)

    # pending
    p_pending = subparsers.add_parser("pending", help="Preview all pending tickets")
    p_pending.add_argument("-t", "--threshold", type=int, default=3, help="Ticket threshold")
    p_pending.set_defaults(func=cmd_preview_all)

    # extract
    p_extract = subparsers.add_parser("extract", help="Extract theme from conversation")
    p_extract.add_argument("id", help="Conversation ID")
    p_extract.add_argument("--store", action="store_true", help="Store the extracted theme")
    p_extract.set_defaults(func=cmd_extract)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
