-- Migration 021: Add excerpt_count field to stories table
-- Issue #197: Raise story evidence quality
--
-- excerpt_count tracks the number of evidence excerpts (diagnostic_summary + key_excerpts)
-- This provides a more accurate measure of evidence quality than evidence_count
-- (which counts theme_signatures).

-- Add excerpt_count column to stories table
ALTER TABLE stories ADD COLUMN IF NOT EXISTS excerpt_count INTEGER DEFAULT 0;

-- Backfill from existing evidence (with COALESCE safety for NULL/empty excerpts)
UPDATE stories s
SET excerpt_count = COALESCE((
    SELECT jsonb_array_length(COALESCE(se.excerpts, '[]'::jsonb))
    FROM story_evidence se
    WHERE se.story_id = s.id
), 0);

-- Index for filtering stories by evidence quality
CREATE INDEX IF NOT EXISTS idx_stories_excerpt_count ON stories(excerpt_count);

-- Add column comment for documentation
COMMENT ON COLUMN stories.excerpt_count IS 'Number of evidence excerpts (diagnostic summaries + key excerpts). Issue #197.';
