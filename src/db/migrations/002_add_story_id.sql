-- Migration: Add story_id column for Shortcut ticket tracking
-- Date: 2026-01-07
-- Purpose: Enable ground-truth clustering analysis by tracking which conversations
--          are linked to the same Shortcut story/ticket

-- Add story_id column to conversations table
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS story_id TEXT;

-- Create index on story_id for efficient grouping queries
CREATE INDEX IF NOT EXISTS idx_conversations_story_id
ON conversations(story_id)
WHERE story_id IS NOT NULL;

-- Add comment to document the column purpose
COMMENT ON COLUMN conversations.story_id IS
'Shortcut story/ticket ID that this conversation is linked to. Multiple conversations may share the same story_id, providing ground truth clustering for categorization validation.';

-- Create view for analyzing conversations grouped by story_id
CREATE OR REPLACE VIEW conversation_clusters AS
SELECT
    story_id,
    COUNT(*) as conversation_count,
    ARRAY_AGG(id ORDER BY created_at) as conversation_ids,
    MIN(created_at) as first_conversation_at,
    MAX(created_at) as last_conversation_at,
    ARRAY_AGG(DISTINCT issue_type) as issue_types,
    -- Theme data (if available)
    (SELECT ARRAY_AGG(DISTINCT t.product_area)
     FROM themes t
     WHERE t.conversation_id = ANY(ARRAY_AGG(c.id))
    ) as product_areas,
    (SELECT ARRAY_AGG(DISTINCT t.issue_signature)
     FROM themes t
     WHERE t.conversation_id = ANY(ARRAY_AGG(c.id))
    ) as issue_signatures
FROM conversations c
WHERE story_id IS NOT NULL
GROUP BY story_id
HAVING COUNT(*) >= 2  -- Only clusters with 2+ conversations
ORDER BY COUNT(*) DESC;

COMMENT ON VIEW conversation_clusters IS
'Groups conversations by Shortcut story_id to analyze clustering patterns and categorization consistency.';
