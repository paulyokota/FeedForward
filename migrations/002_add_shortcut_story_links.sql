-- Migration: Add shortcut_story_links table
-- Phase 4b: Shortcut Story Context Injection
-- Created: 2026-01-07

-- Shortcut story links: tracks which conversations are linked to Shortcut stories
CREATE TABLE IF NOT EXISTS shortcut_story_links (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    story_id TEXT NOT NULL,
    story_name TEXT,
    story_labels JSONB DEFAULT '[]',  -- Array of label strings
    story_epic TEXT,
    story_state TEXT,
    linked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Prevent duplicate story links per conversation
    UNIQUE (conversation_id, story_id)
);

-- Index for finding all conversations linked to a specific story
CREATE INDEX IF NOT EXISTS idx_story_links_story_id
    ON shortcut_story_links(story_id);

-- Index for finding all stories linked to a conversation
CREATE INDEX IF NOT EXISTS idx_story_links_conversation_id
    ON shortcut_story_links(conversation_id);

-- Index for finding recently linked stories
CREATE INDEX IF NOT EXISTS idx_story_links_linked_at
    ON shortcut_story_links(linked_at DESC);

-- Analytics view: Most referenced stories
CREATE OR REPLACE VIEW most_linked_stories AS
SELECT
    s.story_id,
    s.story_name,
    s.story_labels,
    s.story_epic,
    COUNT(DISTINCT s.conversation_id) as conversation_count,
    MIN(s.linked_at) as first_linked,
    MAX(s.linked_at) as last_linked,
    -- Count conversations by type
    COUNT(DISTINCT c.id) FILTER (WHERE c.issue_type = 'bug_report') as bug_count,
    COUNT(DISTINCT c.id) FILTER (WHERE c.issue_type = 'product_question') as question_count,
    COUNT(DISTINCT c.id) FILTER (WHERE c.issue_type = 'feature_request') as feature_request_count
FROM shortcut_story_links s
LEFT JOIN conversations c ON s.conversation_id = c.id
WHERE s.linked_at > NOW() - INTERVAL '30 days'
GROUP BY s.story_id, s.story_name, s.story_labels, s.story_epic
ORDER BY conversation_count DESC;

-- Analytics view: Conversations with Shortcut story context
CREATE OR REPLACE VIEW conversations_with_stories AS
SELECT
    c.id,
    c.created_at,
    c.issue_type,
    c.sentiment,
    c.priority,
    s.story_id,
    s.story_name,
    s.story_labels,
    s.story_epic
FROM conversations c
JOIN shortcut_story_links s ON c.id = s.conversation_id
ORDER BY c.created_at DESC;

-- Analytics view: Story label frequency (for vocabulary expansion)
CREATE OR REPLACE VIEW story_label_frequency AS
SELECT
    label,
    COUNT(DISTINCT story_id) as story_count,
    COUNT(DISTINCT conversation_id) as conversation_count,
    MIN(linked_at) as first_seen,
    MAX(linked_at) as last_seen
FROM shortcut_story_links s,
     jsonb_array_elements_text(s.story_labels) as label
WHERE s.linked_at > NOW() - INTERVAL '30 days'
GROUP BY label
ORDER BY story_count DESC;

COMMENT ON TABLE shortcut_story_links IS 'Tracks Shortcut stories linked to conversations via Story ID v2 (Phase 4b)';
COMMENT ON COLUMN shortcut_story_links.story_id IS 'Shortcut story ID from Story ID v2 custom attribute';
COMMENT ON COLUMN shortcut_story_links.story_labels IS 'JSON array of Shortcut story labels (product areas)';
COMMENT ON COLUMN shortcut_story_links.story_epic IS 'Epic name or ID if story belongs to an epic';
