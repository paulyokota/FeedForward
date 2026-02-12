#!/usr/bin/env python3
"""
Search the Intercom conversation search index using PostgreSQL full-text search.

Issue #284: Intercom full-text search index

Usage:
  python box/intercom-search.py "RSS feed"                    # Full-text search
  python box/intercom-search.py "pins disappeared" --since 90 # Last 90 days
  python box/intercom-search.py "invoice" --email "%@de"      # Filter by email pattern
  python box/intercom-search.py --count "smartpin"             # Just count matches
  python box/intercom-search.py "test" --limit 50             # Custom limit
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.connection import get_connection

INTERCOM_APP_ID = "2t3d8az2"
INTERCOM_URL_BASE = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/all/conversations"


def search_tsquery(conn, query: str, since_days=None, email_pattern=None,
                   limit=20, count_only=False):
    """Search using websearch_to_tsquery (natural language query parsing)."""
    conditions = ["full_text IS NOT NULL"]
    params = []

    # Build tsquery
    conditions.append("full_text_tsv @@ websearch_to_tsquery('english', %s)")
    params.append(query)

    if since_days:
        conditions.append("created_at > NOW() - interval '%s days'")
        params.append(since_days)

    if email_pattern:
        conditions.append("contact_email LIKE %s")
        params.append(email_pattern)

    where = " AND ".join(conditions)

    if count_only:
        sql = f"SELECT COUNT(*) FROM conversation_search_index WHERE {where}"
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]

    sql = f"""
        SELECT
            conversation_id,
            created_at,
            contact_email,
            ts_headline(
                'english', full_text,
                websearch_to_tsquery('english', %s),
                'MaxWords=35, MinWords=15, StartSel=>>>, StopSel=<<<'
            ) AS snippet,
            ts_rank(full_text_tsv, websearch_to_tsquery('english', %s)) AS rank
        FROM conversation_search_index
        WHERE {where}
        ORDER BY rank DESC
        LIMIT %s
    """
    # For ts_headline and ts_rank we need the query param twice more
    full_params = [query, query] + params + [limit]

    with conn.cursor() as cur:
        cur.execute(sql, full_params)
        return cur.fetchall()


def search_ilike(conn, query: str, since_days=None, email_pattern=None,
                 limit=20, count_only=False):
    """Fallback search using ILIKE (for invalid tsquery syntax)."""
    conditions = ["full_text IS NOT NULL"]
    params = []

    conditions.append("full_text ILIKE %s")
    params.append(f"%{query}%")

    if since_days:
        conditions.append("created_at > NOW() - interval '%s days'")
        params.append(since_days)

    if email_pattern:
        conditions.append("contact_email LIKE %s")
        params.append(email_pattern)

    where = " AND ".join(conditions)

    if count_only:
        sql = f"SELECT COUNT(*) FROM conversation_search_index WHERE {where}"
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]

    sql = f"""
        SELECT
            conversation_id,
            created_at,
            contact_email,
            SUBSTRING(full_text FROM POSITION(LOWER(%s) IN LOWER(full_text)) FOR 200) AS snippet
        FROM conversation_search_index
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %s
    """
    full_params = [query] + params + [limit]

    with conn.cursor() as cur:
        cur.execute(sql, full_params)
        return cur.fetchall()


def format_results(results, count_only=False, query=""):
    """Format and print search results."""
    if count_only:
        print(f"\nMatches: {results:,}")
        return

    if not results:
        print("\nNo results found.")
        return

    print(f"\n{len(results)} result(s) for \"{query}\":\n")
    print("-" * 80)

    for row in results:
        conv_id, created_at, email, snippet = row[0], row[1], row[2], row[3]
        url = f"{INTERCOM_URL_BASE}/{conv_id}"

        print(f"  ID:      {conv_id}")
        print(f"  Date:    {created_at}")
        if email:
            print(f"  Email:   {email}")
        print(f"  URL:     {url}")
        print(f"  Snippet: {snippet}")
        print("-" * 80)


def main():
    parser = argparse.ArgumentParser(description="Search Intercom conversation index")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("--since", type=int, help="Only search conversations from last N days")
    parser.add_argument("--email", type=str, help="Filter by email pattern (LIKE syntax, e.g. '%%@de')")
    parser.add_argument("--count", action="store_true", help="Just count matches")
    parser.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    args = parser.parse_args()

    with get_connection() as conn:
        try:
            results = search_tsquery(
                conn, args.query,
                since_days=args.since,
                email_pattern=args.email,
                limit=args.limit,
                count_only=args.count,
            )
        except Exception as e:
            # Check if it's a tsquery parse error
            error_str = str(e)
            if "syntax error" in error_str.lower() or "tsquery" in error_str.lower():
                conn.rollback()
                print(f"(tsquery parse error, falling back to ILIKE search)")
                results = search_ilike(
                    conn, args.query,
                    since_days=args.since,
                    email_pattern=args.email,
                    limit=args.limit,
                    count_only=args.count,
                )
            else:
                raise

        format_results(results, count_only=args.count, query=args.query)


if __name__ == "__main__":
    main()
