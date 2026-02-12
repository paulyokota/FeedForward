-- Migration 026: Conversation search index for full-text search across complete threads
-- Issue #284: Intercom full-text search index

CREATE TABLE IF NOT EXISTS conversation_search_index (
    conversation_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    contact_email TEXT,
    source_body TEXT,              -- opening message (for quick preview)
    full_text TEXT,                -- NULL = not yet indexed; all parts concatenated: [Customer]: ... [Support]: ...
    full_text_tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', COALESCE(full_text, ''))
    ) STORED,
    part_count INTEGER DEFAULT 0,
    truncated BOOLEAN DEFAULT FALSE, -- TRUE if full_text was capped (100k chars or >500 parts)
    failed_at TIMESTAMPTZ,         -- set if thread fetch failed after retries
    failed_reason TEXT,            -- e.g., 'http_404: Not Found', 'error: TimeoutError: ...'
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_csi_full_text_tsv ON conversation_search_index USING GIN (full_text_tsv);
CREATE INDEX IF NOT EXISTS idx_csi_created_at ON conversation_search_index (created_at);
CREATE INDEX IF NOT EXISTS idx_csi_updated_at ON conversation_search_index (updated_at);
CREATE INDEX IF NOT EXISTS idx_csi_contact_email ON conversation_search_index (contact_email);
CREATE INDEX IF NOT EXISTS idx_csi_not_indexed ON conversation_search_index (conversation_id)
    WHERE full_text IS NULL AND failed_at IS NULL;

CREATE TABLE IF NOT EXISTS conversation_sync_state (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sync_type TEXT NOT NULL,           -- 'full' or 'incremental'
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    last_cursor TEXT,                   -- pagination cursor for resume
    conversations_listed INTEGER DEFAULT 0,
    conversations_indexed INTEGER DEFAULT 0,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE
    -- Advisory lock (pg_advisory_lock(hashtext('intercom_sync'))) used at
    -- application level to prevent concurrent syncs. The active flag is for
    -- human observability, not enforcement.
);
