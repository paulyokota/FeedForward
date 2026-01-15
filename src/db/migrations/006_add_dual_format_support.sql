-- Migration 006: Add Dual-Format Story Output Support
-- Enables stories to support both human-readable and AI-facing formats
-- with codebase-aware context from Agent SDK exploration.
-- Reference: docs/architecture/dual-format-story-architecture.md
-- Related: GitHub Issue #37

-- Add dual format fields to stories table
ALTER TABLE stories
ADD COLUMN IF NOT EXISTS format_version VARCHAR(10) DEFAULT 'v1',
ADD COLUMN IF NOT EXISTS ai_section TEXT,
ADD COLUMN IF NOT EXISTS codebase_context JSONB;

-- Add comments for new columns
COMMENT ON COLUMN stories.format_version IS 'Story format version: "v1" = human-only (legacy), "v2" = dual-format with AI section';
COMMENT ON COLUMN stories.ai_section IS 'AI-facing task specification with codebase context and implementation suggestions (v2 only)';
COMMENT ON COLUMN stories.codebase_context IS 'JSONB storing Agent SDK exploration results: {files[], snippets[], queries[], repo_name, explored_at}';

-- Index for filtering stories by format version
CREATE INDEX IF NOT EXISTS idx_stories_format_version ON stories(format_version);

-- Repo sync metrics table for observability
CREATE TABLE IF NOT EXISTS repo_sync_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Repository identification
    repo_name VARCHAR(50) NOT NULL,

    -- Performance metrics
    fetch_duration_ms INTEGER,              -- Time for git fetch operation
    pull_duration_ms INTEGER,               -- Time for git pull operation
    total_duration_ms INTEGER,              -- Total sync duration

    -- Status tracking
    success BOOLEAN DEFAULT true,
    error_message TEXT,

    -- Timestamp
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_repo_sync_metrics_repo_name ON repo_sync_metrics(repo_name);
CREATE INDEX IF NOT EXISTS idx_repo_sync_metrics_synced_at ON repo_sync_metrics(synced_at DESC);

-- Partial index for failed syncs (debugging/alerting)
CREATE INDEX IF NOT EXISTS idx_repo_sync_metrics_failures ON repo_sync_metrics(repo_name, synced_at DESC)
    WHERE success = false;

-- Table comments
COMMENT ON TABLE repo_sync_metrics IS 'Tracks background repository sync job performance for observability and alerting';
COMMENT ON COLUMN repo_sync_metrics.repo_name IS 'Repository name from APPROVED_REPOS (e.g., "aero", "tack", "charlotte")';
COMMENT ON COLUMN repo_sync_metrics.fetch_duration_ms IS 'Duration of git fetch operation in milliseconds';
COMMENT ON COLUMN repo_sync_metrics.pull_duration_ms IS 'Duration of git pull operation in milliseconds';
COMMENT ON COLUMN repo_sync_metrics.total_duration_ms IS 'Total sync operation duration (fetch + pull + overhead) in milliseconds';

-- Rollback instructions (for manual rollback if needed):
--
-- ALTER TABLE stories DROP COLUMN IF EXISTS format_version;
-- ALTER TABLE stories DROP COLUMN IF EXISTS ai_section;
-- ALTER TABLE stories DROP COLUMN IF EXISTS codebase_context;
-- DROP INDEX IF EXISTS idx_stories_format_version;
-- DROP TABLE IF EXISTS repo_sync_metrics;
