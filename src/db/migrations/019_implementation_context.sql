-- Migration 019: Add implementation_context column to stories table
-- Purpose: Store hybrid retrieval + synthesis implementation guidance
-- Issue: #180 - Hybrid Implementation Context
-- Schema version: 1.0

-- Add implementation_context JSONB column
ALTER TABLE stories ADD COLUMN IF NOT EXISTS implementation_context JSONB;

-- Partial index for "has context" queries (lightweight)
CREATE INDEX IF NOT EXISTS idx_stories_has_impl_context
ON stories ((implementation_context IS NOT NULL))
WHERE implementation_context IS NOT NULL;

-- Partial index for "successful context" queries
CREATE INDEX IF NOT EXISTS idx_stories_impl_context_success
ON stories ((implementation_context->>'success'))
WHERE implementation_context IS NOT NULL;

-- Skip GIN index - not needed for current access patterns
-- Add later if JSON path queries become common

COMMENT ON COLUMN stories.implementation_context IS
  'JSONB blob containing hybrid implementation context (schema v1.0): '
  'summary, relevant_files, next_steps, prior_art_references, metadata. '
  'See ImplementationContext model. Issue #180.';
