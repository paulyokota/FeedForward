-- Migration 005: Add story_orphans table for Phase 5 Story Grouping
--
-- Orphans are sub-groups with <3 conversations that accumulate over time.
-- When an orphan reaches MIN_GROUP_SIZE (3), it graduates to a full story.

CREATE TABLE IF NOT EXISTS story_orphans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Signature identification
    signature TEXT NOT NULL UNIQUE,           -- PM-approved canonical signature
    original_signature TEXT,                   -- Pre-split signature (for tracking lineage)

    -- Accumulated conversations
    conversation_ids TEXT[] NOT NULL DEFAULT '{}',

    -- Theme data from extractions (user_intent, symptoms, excerpts, product_area, etc.)
    theme_data JSONB NOT NULL DEFAULT '{}',

    -- Confidence score from last scoring run
    confidence_score FLOAT,

    -- Lifecycle timestamps
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Graduation tracking
    graduated_at TIMESTAMPTZ,                  -- NULL until graduated to story
    story_id UUID REFERENCES stories(id)       -- The story it graduated into
);

-- Index for signature lookups (primary access pattern)
CREATE INDEX IF NOT EXISTS idx_orphans_signature ON story_orphans(signature);

-- Partial index for active (non-graduated) orphans
CREATE INDEX IF NOT EXISTS idx_orphans_active ON story_orphans(signature)
    WHERE graduated_at IS NULL;

-- Index for finding orphans by first seen date (for cleanup/reporting)
CREATE INDEX IF NOT EXISTS idx_orphans_first_seen ON story_orphans(first_seen_at DESC);

-- Index for finding graduated orphans by story
CREATE INDEX IF NOT EXISTS idx_orphans_story ON story_orphans(story_id)
    WHERE story_id IS NOT NULL;

COMMENT ON TABLE story_orphans IS 'Accumulates conversation groups with <3 items until they reach MIN_GROUP_SIZE for graduation to stories';
COMMENT ON COLUMN story_orphans.signature IS 'PM-approved canonical signature from PM review splits';
COMMENT ON COLUMN story_orphans.original_signature IS 'Original signature before PM review split (for lineage tracking)';
COMMENT ON COLUMN story_orphans.theme_data IS 'Merged theme data: {user_intent, symptoms, excerpts[], product_area, component}';
COMMENT ON COLUMN story_orphans.graduated_at IS 'Timestamp when orphan was converted to a story (NULL = still active)';
