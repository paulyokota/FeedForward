#!/usr/bin/env python3
"""
Intercom conversation search index sync script.

Populates and refreshes the conversation_search_index table with complete
conversation threads for full-text search.

Issue #284: Intercom full-text search index

Two-phase approach:
  Phase 1 (list): Paginate conversations via Intercom search API, upsert metadata
  Phase 2 (index): Fetch full threads for rows with full_text IS NULL

Usage:
  python box/intercom-sync.py --full              # Full sync (both phases)
  python box/intercom-sync.py --list-only         # Phase 1 only
  python box/intercom-sync.py --index-only        # Phase 2 only
  python box/intercom-sync.py --since 2026-02-01  # Incremental (updated_at filter)
  python box/intercom-sync.py --status            # Show sync state
  python box/intercom-sync.py --full --max 100    # Cap for testing
  python box/intercom-sync.py --full --force      # Override stale lock
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiohttp
from psycopg2.extras import execute_values

from src.db.connection import get_connection
from src.digest_extractor import build_full_conversation_text
from src.intercom_client import IntercomClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Concurrency for Phase 2 thread fetching
FETCH_CONCURRENCY = max(1, min(100, int(os.getenv("INTERCOM_FETCH_CONCURRENCY", "10"))))
MAX_FULL_TEXT_LENGTH = 100_000
MAX_PARTS = 500
MAX_RETRIES_PHASE2 = 5


def acquire_advisory_lock(conn) -> bool:
    """Try to acquire the advisory lock. Returns True if acquired."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext('intercom_sync'))")
        return cur.fetchone()[0]


def release_advisory_lock(conn):
    """Release the advisory lock."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(hashtext('intercom_sync'))")


def check_stale_sync(conn) -> bool:
    """Check if there's a stale active sync (started > 2h ago, not completed)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, started_at FROM conversation_sync_state
            WHERE active = TRUE AND completed_at IS NULL
              AND started_at < NOW() - interval '2 hours'
            ORDER BY started_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            logger.warning("Stale sync found: id=%s, started_at=%s", row[0], row[1])
            return True
        return False


def clear_stale_syncs(conn):
    """Mark stale active syncs as inactive."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversation_sync_state
            SET active = FALSE
            WHERE active = TRUE AND completed_at IS NULL
              AND started_at < NOW() - interval '2 hours'
        """)
        logger.info("Cleared stale sync records")


def create_sync_state(conn, sync_type: str, date_start=None, date_end=None) -> str:
    """Create a new sync state record. Returns the UUID."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO conversation_sync_state
                (sync_type, date_range_start, date_range_end)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (sync_type, date_start, date_end))
        return str(cur.fetchone()[0])


def update_sync_cursor(conn, sync_id: str, cursor: str, listed: int):
    """Update the cursor checkpoint and listed count."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversation_sync_state
            SET last_cursor = %s, conversations_listed = %s
            WHERE id = %s::uuid
        """, (cursor, listed, sync_id))


def complete_sync_state(conn, sync_id: str, listed: int, indexed: int):
    """Mark sync as completed."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversation_sync_state
            SET completed_at = NOW(), active = FALSE,
                conversations_listed = %s, conversations_indexed = %s
            WHERE id = %s::uuid
        """, (listed, indexed, sync_id))


def get_last_sync_cursor(conn, sync_id: str) -> tuple:
    """Get the last cursor and listed count for a sync. Returns (cursor, listed)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT last_cursor, conversations_listed
            FROM conversation_sync_state WHERE id = %s::uuid
        """, (sync_id,))
        row = cur.fetchone()
        if row:
            return row[0], row[1] or 0
        return None, 0


def upsert_batch(conn, rows: list):
    """Batch upsert conversation metadata into the search index.

    Resets full_text and related fields when updated_at changes so Phase 2
    re-fetches the thread.
    """
    if not rows:
        return
    sql = """
        INSERT INTO conversation_search_index
            (conversation_id, created_at, updated_at, contact_email, source_body)
        VALUES %s
        ON CONFLICT (conversation_id) DO UPDATE SET
            updated_at = EXCLUDED.updated_at,
            contact_email = EXCLUDED.contact_email,
            source_body = EXCLUDED.source_body,
            full_text = CASE
                WHEN conversation_search_index.updated_at IS DISTINCT FROM EXCLUDED.updated_at
                THEN NULL
                ELSE conversation_search_index.full_text
            END,
            part_count = CASE
                WHEN conversation_search_index.updated_at IS DISTINCT FROM EXCLUDED.updated_at
                THEN 0
                ELSE conversation_search_index.part_count
            END,
            truncated = CASE
                WHEN conversation_search_index.updated_at IS DISTINCT FROM EXCLUDED.updated_at
                THEN FALSE
                ELSE conversation_search_index.truncated
            END,
            failed_at = CASE
                WHEN conversation_search_index.updated_at IS DISTINCT FROM EXCLUDED.updated_at
                THEN NULL
                ELSE conversation_search_index.failed_at
            END,
            failed_reason = CASE
                WHEN conversation_search_index.updated_at IS DISTINCT FROM EXCLUDED.updated_at
                THEN NULL
                ELSE conversation_search_index.failed_reason
            END,
            synced_at = NOW()
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)


def extract_metadata(conv: dict) -> tuple:
    """Extract (conversation_id, created_at, updated_at, contact_email, source_body) from raw conversation."""
    conv_id = str(conv.get("id", ""))
    created_ts = conv.get("created_at", 0)
    updated_ts = conv.get("updated_at")
    created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else None
    updated_at = datetime.fromtimestamp(updated_ts, tz=timezone.utc) if updated_ts else None

    source = conv.get("source", {})
    contact_email = None
    author = source.get("author", {})
    if author:
        contact_email = author.get("email")
    # Also try contacts list
    if not contact_email:
        contacts = conv.get("contacts", {})
        contact_list = contacts.get("contacts", []) if isinstance(contacts, dict) else []
        if contact_list:
            contact_email = contact_list[0].get("email")

    source_body_raw = source.get("body", "")
    source_body = IntercomClient.strip_html(source_body_raw) if source_body_raw else ""

    return (conv_id, created_at, updated_at, contact_email, source_body)


async def phase1_list(client: IntercomClient, conn, sync_id: str,
                      since_date=None, max_convs=None):
    """Phase 1: List conversations and upsert metadata."""
    now_ts = int(time.time())

    if since_date:
        # Incremental: use updated_at filter
        since_ts = int(since_date.timestamp())
        logger.info("Phase 1: Listing conversations updated since %s", since_date.isoformat())
        listed = await _phase1_incremental(client, conn, sync_id, since_ts, now_ts, max_convs)
    else:
        # Full: use created_at filter via search_by_date_range_async
        logger.info("Phase 1: Listing all conversations (full sync)")
        listed = await _phase1_full(client, conn, sync_id, now_ts, max_convs)

    logger.info("Phase 1 complete: %d conversations listed", listed)
    return listed


async def _phase1_full(client, conn, sync_id, end_ts, max_convs):
    """Full sync using search_by_date_range_async (created_at filter)."""
    # Check for resume cursor
    resume_cursor, listed = get_last_sync_cursor(conn, sync_id)
    if resume_cursor:
        logger.info("Resuming from cursor, already listed %d", listed)

    batch = []

    def cursor_cb(cursor):
        nonlocal listed
        update_sync_cursor(conn, sync_id, cursor, listed)

    async for conv in client.search_by_date_range_async(
        start_timestamp=0,
        end_timestamp=end_ts,
        initial_cursor=resume_cursor,
        cursor_callback=cursor_cb,
    ):
        row = extract_metadata(conv)
        batch.append(row)
        listed += 1

        if len(batch) >= 150:
            upsert_batch(conn, batch)
            batch.clear()
            if listed % 1000 == 0:
                logger.info("Phase 1: %d conversations listed", listed)

        if max_convs and listed >= max_convs:
            break

    if batch:
        upsert_batch(conn, batch)

    return listed


async def _phase1_incremental(client, conn, sync_id, since_ts, end_ts, max_convs):
    """Incremental sync using updated_at filter (custom search query)."""
    listed = 0
    batch = []
    per_page = client.PER_PAGE
    starting_after = None

    search_query = {
        "query": {
            "operator": "AND",
            "value": [
                {
                    "field": "updated_at",
                    "operator": ">",
                    "value": since_ts,
                },
                {
                    "field": "updated_at",
                    "operator": "<",
                    "value": end_ts,
                },
            ],
        },
        "pagination": {"per_page": per_page},
    }

    async with client._get_aiohttp_session() as session:
        while True:
            if starting_after:
                search_query["pagination"]["starting_after"] = starting_after
            elif "starting_after" in search_query.get("pagination", {}):
                del search_query["pagination"]["starting_after"]

            data = await client._request_with_retry_async(
                session, "POST", "/conversations/search", json_data=search_query
            )

            conversations = data.get("conversations", [])
            if not conversations:
                break

            for conv in conversations:
                row = extract_metadata(conv)
                batch.append(row)
                listed += 1

                if len(batch) >= 150:
                    upsert_batch(conn, batch)
                    batch.clear()
                    if listed % 1000 == 0:
                        logger.info("Phase 1 (incremental): %d conversations listed", listed)

                if max_convs and listed >= max_convs:
                    break

            if max_convs and listed >= max_convs:
                break

            # Pagination
            pages = data.get("pages", {})
            next_page = pages.get("next", {})
            starting_after = next_page.get("starting_after")

            if starting_after:
                update_sync_cursor(conn, sync_id, starting_after, listed)

            if not starting_after:
                break

    if batch:
        upsert_batch(conn, batch)

    return listed


async def phase2_index(client: IntercomClient, conn, max_convs=None):
    """Phase 2: Fetch full threads for unindexed conversations."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT conversation_id FROM conversation_search_index
            WHERE full_text IS NULL AND failed_at IS NULL
        """)
        conv_ids = [row[0] for row in cur.fetchall()]

    if max_convs:
        conv_ids = conv_ids[:max_convs]

    total = len(conv_ids)
    if total == 0:
        logger.info("Phase 2: No conversations to index")
        return 0

    logger.info("Phase 2: %d conversations to index (concurrency=%d)", total, FETCH_CONCURRENCY)

    indexed = 0
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch_and_index(session, conv_id):
        nonlocal indexed
        async with semaphore:
            for attempt in range(MAX_RETRIES_PHASE2):
                try:
                    raw_conv = await client.get_conversation_async(session, conv_id)
                    full_text = build_full_conversation_text(raw_conv, max_length=MAX_FULL_TEXT_LENGTH)

                    # Count parts
                    parts_container = raw_conv.get("conversation_parts", {})
                    parts_list = (
                        parts_container.get("conversation_parts", [])
                        if isinstance(parts_container, dict)
                        else []
                    )
                    part_count = len(parts_list)
                    truncated = len(full_text) >= MAX_FULL_TEXT_LENGTH or part_count >= MAX_PARTS

                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE conversation_search_index
                            SET full_text = %s, part_count = %s, truncated = %s, synced_at = NOW()
                            WHERE conversation_id = %s
                        """, (full_text, part_count, truncated, conv_id))
                    conn.commit()

                    indexed += 1
                    if indexed % 100 == 0:
                        logger.info("Phase 2: %d / %d indexed", indexed, total)
                    return

                except aiohttp.ClientResponseError as e:
                    if e.status == 404:
                        _mark_failed(conn, conv_id, f"http_404: Not Found")
                        return
                    if attempt < MAX_RETRIES_PHASE2 - 1:
                        delay = 2 ** attempt
                        logger.warning(
                            "Error fetching %s (HTTP %d), retry %d/%d in %ds",
                            conv_id, e.status, attempt + 1, MAX_RETRIES_PHASE2, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        _mark_failed(conn, conv_id, f"http_{e.status}: {e.message}")
                        return

                except Exception as e:
                    if attempt < MAX_RETRIES_PHASE2 - 1:
                        delay = 2 ** attempt
                        logger.warning(
                            "Error fetching %s (%s), retry %d/%d in %ds",
                            conv_id, e, attempt + 1, MAX_RETRIES_PHASE2, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        _mark_failed(conn, conv_id, f"error: {type(e).__name__}: {e}")
                        return

    async with client._get_aiohttp_session() as session:
        tasks = [fetch_and_index(session, cid) for cid in conv_ids]
        await asyncio.gather(*tasks)

    logger.info("Phase 2 complete: %d / %d indexed", indexed, total)
    return indexed


def _mark_failed(conn, conv_id: str, reason: str):
    """Mark a conversation as failed."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE conversation_search_index
            SET failed_at = NOW(), failed_reason = %s
            WHERE conversation_id = %s
        """, (reason, conv_id))
    conn.commit()
    logger.warning("Failed: %s — %s", conv_id, reason)


def show_status():
    """Show sync state and index statistics."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Latest sync
            cur.execute("""
                SELECT sync_type, started_at, completed_at,
                       conversations_listed, conversations_indexed, active
                FROM conversation_sync_state
                ORDER BY started_at DESC LIMIT 3
            """)
            syncs = cur.fetchall()

            # Index stats
            cur.execute("SELECT COUNT(*) FROM conversation_search_index")
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM conversation_search_index WHERE full_text IS NOT NULL")
            indexed = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*) FROM conversation_search_index
                WHERE full_text IS NULL AND failed_at IS NULL
            """)
            pending = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM conversation_search_index WHERE failed_at IS NOT NULL")
            failed = cur.fetchone()[0]

            cur.execute("""
                SELECT MIN(created_at), MAX(created_at)
                FROM conversation_search_index
            """)
            date_range = cur.fetchone()

    print("\n=== Sync State ===")
    if syncs:
        for s in syncs:
            status = "active" if s[5] else ("completed" if s[2] else "incomplete")
            print(f"  {s[0]:12s}  started={s[1]}  completed={s[2]}  "
                  f"listed={s[3]}  indexed={s[4]}  [{status}]")
    else:
        print("  No sync records found")

    print(f"\n=== Index Stats ===")
    print(f"  Total rows:   {total:,}")
    print(f"  Indexed:      {indexed:,}")
    print(f"  Pending:      {pending:,}")
    print(f"  Failed:       {failed:,}")
    if date_range and date_range[0]:
        print(f"  Date range:   {date_range[0]} — {date_range[1]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Sync Intercom conversations to search index")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true", help="Full sync (Phase 1 + Phase 2)")
    group.add_argument("--list-only", action="store_true", help="Phase 1 only (list conversations)")
    group.add_argument("--index-only", action="store_true", help="Phase 2 only (fetch threads)")
    group.add_argument("--since", type=str, help="Incremental sync (updated after date, e.g. 2026-02-01)")
    group.add_argument("--status", action="store_true", help="Show sync state")

    parser.add_argument("--max", type=int, help="Maximum conversations to process")
    parser.add_argument("--force", action="store_true", help="Override stale advisory lock")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    # Parse --since date
    since_date = None
    if args.since:
        since_date = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    client = IntercomClient()

    with get_connection() as conn:
        # Advisory lock
        if not acquire_advisory_lock(conn):
            if args.force and check_stale_sync(conn):
                clear_stale_syncs(conn)
                logger.info("Stale sync cleared, proceeding with --force")
            else:
                print("Another sync is running. Use --force to override if stale.")
                sys.exit(1)

        try:
            sync_type = "incremental" if since_date else "full"
            sync_id = create_sync_state(conn, sync_type, date_start=since_date)
            conn.commit()

            listed = 0
            indexed = 0

            # Phase 1
            if args.full or args.list_only or args.since:
                listed = asyncio.run(phase1_list(client, conn, sync_id, since_date, args.max))
                conn.commit()

            # Phase 2
            if args.full or args.index_only or args.since:
                indexed = asyncio.run(phase2_index(client, conn, args.max))
                conn.commit()

            complete_sync_state(conn, sync_id, listed, indexed)
            conn.commit()

            print(f"\nSync complete: {listed} listed, {indexed} indexed")

        finally:
            release_advisory_lock(conn)


if __name__ == "__main__":
    main()
