-- Migration 007: Add Suggested Evidence Decisions Table
-- Tracks user accept/reject decisions for vector-suggested evidence on stories.
-- Part of Vector Integration Phase 1 for enhanced story evidence management.
-- Reference: docs/story-tracking-web-app-architecture.md
-- Related: GitHub Issue #48, #43 (Vector Integration Phase 1)

-- Suggested evidence decisions table
-- Records when users accept or reject vector-suggested evidence for stories
CREATE TABLE IF NOT EXISTS suggested_evidence_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Story reference (cascade delete when story is removed)
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,

    -- Evidence identification
    evidence_id TEXT NOT NULL CHECK (evidence_id != ''),  -- Composite key format: "{source_type}:{source_id}"
    source_type TEXT NOT NULL CHECK (source_type IN ('coda_page', 'coda_theme', 'intercom')),
    source_id TEXT NOT NULL CHECK (source_id != ''),  -- Source-specific identifier

    -- Decision tracking
    decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    similarity_score DECIMAL(5,4) CHECK (similarity_score >= 0 AND similarity_score <= 1),  -- Cosine similarity (0-1)

    -- Timestamp
    decided_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Prevent duplicate decisions for the same story-evidence pair
    UNIQUE(story_id, evidence_id)
);

-- Index for common query patterns
-- Composite index covers both story-only and story+decision queries (leftmost prefix)
CREATE INDEX IF NOT EXISTS idx_evidence_decisions_story_decision ON suggested_evidence_decisions(story_id, decision);

-- Table and column comments
COMMENT ON TABLE suggested_evidence_decisions IS 'Tracks user accept/reject decisions for vector-suggested evidence on stories';
COMMENT ON COLUMN suggested_evidence_decisions.evidence_id IS 'Composite identifier in format "{source_type}:{source_id}" for unique evidence lookup';
COMMENT ON COLUMN suggested_evidence_decisions.source_type IS 'Evidence source type: coda_page (Coda documents), coda_theme (extracted themes), intercom (conversations)';
COMMENT ON COLUMN suggested_evidence_decisions.source_id IS 'Source-specific identifier (e.g., Coda page ID, conversation ID)';
COMMENT ON COLUMN suggested_evidence_decisions.similarity_score IS 'Vector similarity score (0-1) at decision time for audit/analytics';
COMMENT ON COLUMN suggested_evidence_decisions.decided_at IS 'Timestamp when user made the accept/reject decision';

-- Rollback instructions (for manual rollback if needed):
--
-- DROP INDEX IF EXISTS idx_evidence_decisions_story_decision;
-- DROP TABLE IF EXISTS suggested_evidence_decisions;
