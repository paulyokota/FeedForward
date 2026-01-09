-- Migration 004: Story Tracking Web App Schema
-- Canonical data model for system of record with bidirectional Shortcut sync
-- Reference: docs/story-tracking-web-app-architecture.md

-- 1) stories: Canonical work items stored internally
CREATE TABLE IF NOT EXISTS stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Shortcut-shared fields (bidirectional sync)
    title TEXT NOT NULL,
    description TEXT,
    labels TEXT[] DEFAULT '{}',
    priority VARCHAR(20),           -- Shortcut enum: none, low, medium, high, urgent
    severity VARCHAR(20),           -- Shortcut enum: none, minor, moderate, major, critical
    product_area VARCHAR(100),      -- Shortcut enum value
    technical_area VARCHAR(100),    -- Shortcut enum value

    -- Internal-only fields
    status VARCHAR(50) DEFAULT 'candidate',  -- Free-form, lifecycle-agnostic
    confidence_score DECIMAL(5,2),
    evidence_count INTEGER DEFAULT 0,
    conversation_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2) story_comments: Comments with source tracking to avoid duplicates
CREATE TABLE IF NOT EXISTS story_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,

    external_id VARCHAR(100),       -- Shortcut comment ID if synced
    source VARCHAR(20) NOT NULL,    -- 'internal' or 'shortcut'
    body TEXT NOT NULL,
    author VARCHAR(255),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(story_id, external_id, source)
);

-- 3) story_evidence: Evidence bundles grounding stories in sources
CREATE TABLE IF NOT EXISTS story_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,

    conversation_ids TEXT[] DEFAULT '{}',
    theme_signatures TEXT[] DEFAULT '{}',
    source_stats JSONB DEFAULT '{}',    -- {"intercom": 10, "coda": 2}
    excerpts JSONB DEFAULT '[]',        -- Array of {text, source, conversation_id}

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4) story_sync_metadata: Sync bookkeeping for Shortcut
CREATE TABLE IF NOT EXISTS story_sync_metadata (
    story_id UUID PRIMARY KEY REFERENCES stories(id) ON DELETE CASCADE,

    shortcut_story_id VARCHAR(50),      -- Shortcut story ID when linked

    last_internal_update_at TIMESTAMP WITH TIME ZONE,
    last_external_update_at TIMESTAMP WITH TIME ZONE,
    last_synced_at TIMESTAMP WITH TIME ZONE,

    last_sync_status VARCHAR(20),       -- 'success', 'failed', 'pending'
    last_sync_error TEXT,
    last_sync_direction VARCHAR(10),    -- 'push' or 'pull'

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5) label_registry: Tracks Shortcut taxonomy + internal extensions
CREATE TABLE IF NOT EXISTS label_registry (
    label_name VARCHAR(100) PRIMARY KEY,
    source VARCHAR(20) NOT NULL,        -- 'shortcut' or 'internal'
    category VARCHAR(50),               -- Optional grouping

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);
CREATE INDEX IF NOT EXISTS idx_stories_product_area ON stories(product_area);
CREATE INDEX IF NOT EXISTS idx_stories_updated_at ON stories(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_confidence ON stories(confidence_score DESC);

CREATE INDEX IF NOT EXISTS idx_story_evidence_story_id ON story_evidence(story_id);
CREATE INDEX IF NOT EXISTS idx_story_comments_story_id ON story_comments(story_id);

CREATE INDEX IF NOT EXISTS idx_sync_metadata_shortcut_id ON story_sync_metadata(shortcut_story_id);
CREATE INDEX IF NOT EXISTS idx_sync_metadata_last_synced ON story_sync_metadata(last_synced_at);

-- Trigger to update updated_at on stories
CREATE OR REPLACE FUNCTION update_stories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS stories_updated_at_trigger ON stories;
CREATE TRIGGER stories_updated_at_trigger
    BEFORE UPDATE ON stories
    FOR EACH ROW
    EXECUTE FUNCTION update_stories_updated_at();

-- View for stories with evidence summary
CREATE OR REPLACE VIEW stories_with_evidence AS
SELECT
    s.*,
    se.conversation_ids,
    se.theme_signatures,
    se.source_stats,
    se.excerpts,
    sm.shortcut_story_id,
    sm.last_synced_at,
    sm.last_sync_status
FROM stories s
LEFT JOIN story_evidence se ON s.id = se.story_id
LEFT JOIN story_sync_metadata sm ON s.id = sm.story_id;

COMMENT ON TABLE stories IS 'Canonical story records - system of record for FeedForward';
COMMENT ON TABLE story_evidence IS 'Evidence bundles linking stories to conversations and themes';
COMMENT ON TABLE story_sync_metadata IS 'Bidirectional sync state with Shortcut';
COMMENT ON TABLE label_registry IS 'Label taxonomy from Shortcut plus internal extensions';
