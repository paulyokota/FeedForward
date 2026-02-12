# Plan: Issue #284 — Intercom Full-Text Search Index

## Overview

Three deliverables: a PostgreSQL migration, a sync script, and a search script. All reuse existing `IntercomClient`, `build_full_conversation_text`, and `get_connection` from the codebase.

---

## Deliverable 1: Migration (`src/db/migrations/026_conversation_search_index.sql`)

Verbatim from the issue schema. Two tables:

**`conversation_search_index`** — Primary index table:

- `conversation_id TEXT PRIMARY KEY`
- `created_at`, `updated_at`, `contact_email`, `source_body` — metadata
- `full_text TEXT` — all parts concatenated (`[Customer]: ...` / `[Support]: ...`), NULL = not yet indexed
- `full_text_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', COALESCE(full_text, '')))` — auto-maintained tsvector
- `part_count`, `truncated`, `failed_at`, `failed_reason`, `synced_at` — sync metadata

**`conversation_sync_state`** — Sync run tracking:

- `sync_type` ('full'/'incremental'), `started_at`, `completed_at`
- `last_cursor` for pagination resume
- `conversations_listed`, `conversations_indexed` — counters
- `date_range_start`, `date_range_end` — for incremental
- `active` flag (observability, not enforcement)

**Five indexes:**

1. GIN on `full_text_tsv`
2. btree on `created_at`
3. btree on `updated_at` (used by incremental sync filtering and status queries)
4. btree on `contact_email`
5. Partial index: `conversation_id WHERE full_text IS NULL AND failed_at IS NULL`

No changes to existing tables.

---

## Deliverable 2: Sync Script (`box/intercom-sync.py`)

### Reused Code

| Function                         | Source                        | Usage                                                    |
| -------------------------------- | ----------------------------- | -------------------------------------------------------- |
| `IntercomClient`                 | `src/intercom_client.py`      | API client with retry/rate-limit                         |
| `get_conversation_async()`       | `src/intercom_client.py:544`  | Fetch single conversation (async)                        |
| `search_by_date_range_async()`   | `src/intercom_client.py:552`  | Paginate by date range with cursor checkpoint            |
| `build_full_conversation_text()` | `src/digest_extractor.py:302` | Concatenate parts, strip HTML (pass `max_length=100000`) |
| `get_connection()`               | `src/db/connection.py:29`     | PostgreSQL context manager                               |

### CLI Interface

```
python box/intercom-sync.py --full              # Full sync (Phase 1 + Phase 2)
python box/intercom-sync.py --list-only         # Phase 1 only
python box/intercom-sync.py --index-only        # Phase 2 only
python box/intercom-sync.py --since 2026-02-01  # Incremental
python box/intercom-sync.py --status            # Show sync state
python box/intercom-sync.py --full --max 100    # Cap for testing
python box/intercom-sync.py --full --force      # Override stale lock
```

### Concurrent Sync Prevention

1. At script start, acquire `pg_advisory_lock(hashtext('intercom_sync'))`
2. If lock not acquired → print "Another sync is running" and exit
3. Check for stale active syncs (started > 2h ago, not completed) → override with `--force`
4. On start, insert `conversation_sync_state` row with `active = TRUE`
5. On completion, update with `completed_at` and `active = FALSE`

### Phase 1 — List Conversations

1. Determine date range and API query:
   - `--full`: Use `search_by_date_range_async()` with `created_at` from epoch (0) to now
   - `--since DATE`: Build a custom Intercom search query using `updated_at > DATE` (NOT `created_at`), since `search_by_date_range_async()` filters by `created_at` only. This is critical: Intercom's `updated_at` changes when new parts are added, so filtering by `updated_at` catches conversations with new replies. The sync script will construct the search query directly using `IntercomClient._request_with_retry_async()` with the same pagination pattern.
2. Use `cursor_callback` → checkpoint cursor in `conversation_sync_state.last_cursor`, and `initial_cursor` → resume from last checkpoint if restarting.
3. For each conversation from the API:
   - Extract: `id`, `created_at` (unix → datetime), `updated_at`, `contact_email` (from `source.author.email`), `source_body` (strip HTML from `source.body`)
4. Batch upsert (per page, ~150 rows):
   ```sql
   INSERT INTO conversation_search_index (conversation_id, created_at, updated_at, contact_email, source_body)
   VALUES ...
   ON CONFLICT (conversation_id) DO UPDATE SET
     updated_at = EXCLUDED.updated_at,
     contact_email = EXCLUDED.contact_email,
     source_body = EXCLUDED.source_body,
     -- CRITICAL: Reset full_text to NULL when updated_at changes, so Phase 2
     -- re-fetches the thread for conversations with new replies
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
   ```
   New rows get `full_text = NULL` (triggers Phase 2 indexing). Updated rows with a changed `updated_at` also get `full_text = NULL` so Phase 2 re-fetches their threads.
5. Respect `--max` cap: stop after N conversations listed.
6. Update `conversation_sync_state.conversations_listed` counter.

### Phase 2 — Fetch Threads

1. Query unindexed rows:
   ```sql
   SELECT conversation_id FROM conversation_search_index
   WHERE full_text IS NULL AND failed_at IS NULL
   ```
   (Uses partial index `idx_csi_not_indexed`)
2. Respect `--max` cap: only fetch up to N threads.
3. Use `asyncio.Semaphore(concurrency)` where `concurrency = INTERCOM_FETCH_CONCURRENCY` (env, default 10).
4. For each conversation_id:
   a. `get_conversation_async(session, conv_id)` → full thread JSON
   b. `build_full_conversation_text(raw_conv, max_length=100000)` → formatted text
   c. Count parts from `raw_conv["conversation_parts"]["conversation_parts"]`
   d. `truncated = len(full_text) >= 100000 or part_count >= 500`
   e. Update row: `full_text`, `part_count`, `truncated`, `synced_at = NOW()`
5. On failure (after client's built-in retries, 5 max total attempts):
   - 404 → `failed_at = NOW()`, `failed_reason = 'http_404: Not Found'`
   - Other HTTP errors → `failed_at = NOW()`, `failed_reason = 'http_{status}: {message}'`
   - Non-HTTP errors → `failed_at = NOW()`, `failed_reason = 'error: {type}: {message}'`
   - Row drops out of Phase 2 queue via partial index
6. Progress: print count every 100 conversations.
7. Update `conversation_sync_state.conversations_indexed` counter.

### `--status` Command

Query and display:

- Latest sync state (type, started, completed, counts)
- Total rows in index
- Indexed rows (`full_text IS NOT NULL`)
- Pending rows (`full_text IS NULL AND failed_at IS NULL`) — same condition as partial index
- Failed rows (`failed_at IS NOT NULL`)
- Oldest/newest conversation in index

### Error Handling

- Script is idempotent: kill and restart safely
- Phase 1 resumes via cursor checkpoint
- Phase 2 resumes by re-querying NULL full_text rows
- All DB operations use `get_connection()` context manager (auto commit/rollback)

---

## Deliverable 3: Search Script (`box/intercom-search.py`)

### CLI Interface

```
python box/intercom-search.py "RSS feed"                    # Full-text search
python box/intercom-search.py "pins disappeared" --since 90 # Last 90 days
python box/intercom-search.py "invoice" --email "%@de"      # Email pattern
python box/intercom-search.py --count "smartpin"             # Count only
python box/intercom-search.py "test" --limit 50             # Custom limit
```

### Implementation

1. **Primary search**: `websearch_to_tsquery('english', $query)` with:
   - `ts_rank(full_text_tsv, query)` for ordering
   - `ts_headline('english', full_text, query, 'MaxWords=35, MinWords=15, StartSel=>>>, StopSel=<<<')` for snippets
2. **Fallback**: On PostgreSQL tsquery parse error only → `ILIKE '%query%'` substring search
3. **Zero results from valid tsquery = real zero** (no fallback)
4. **Filters**:
   - `--since N` → `created_at > NOW() - interval 'N days'`
   - `--email PATTERN` → `contact_email LIKE pattern`
5. **Output per row**:
   - Conversation ID
   - Created date
   - Contact email
   - Text snippet with highlights
   - Intercom URL: `https://app.intercom.com/a/apps/2t3d8az2/inbox/inbox/all/conversations/{id}`
6. **`--count`**: Just `SELECT COUNT(*)`
7. **Default limit**: 20, configurable with `--limit`

---

## File Changes Summary

| File                                                  | Action | Lines (est) |
| ----------------------------------------------------- | ------ | ----------- |
| `src/db/migrations/026_conversation_search_index.sql` | Create | ~35         |
| `box/intercom-sync.py`                                | Create | ~400        |
| `box/intercom-search.py`                              | Create | ~150        |

## What This Does NOT Touch

- No changes to existing `conversations` table or pipeline
- No frontend/API changes
- No classification/categorization
- No scheduled auto-sync

## Testing Strategy

1. Migration applies cleanly: `psql $DATABASE_URL -f src/db/migrations/026_conversation_search_index.sql`
2. `python box/intercom-sync.py --full --max 100` completes without errors
3. `python box/intercom-sync.py --status` shows sync state
4. `python box/intercom-search.py "test"` returns results with snippets and Intercom URLs
5. Resumability: `--index-only` picks up where `--full` left off
6. Run `pytest -m "fast"` to verify no regressions
