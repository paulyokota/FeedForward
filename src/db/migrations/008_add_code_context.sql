-- Migration: Add code_context column to stories table
-- Purpose: Store classification-guided codebase exploration results with stories
-- Issue: #44 - Wire classification-guided exploration into story creation
--
-- Schema Decision: Option A - JSONB column (vs. separate table)
-- Rationale:
--   - Code context is 1:1 with stories (no separate querying needed)
--   - JSONB allows flexible evolution of structure
--   - Avoids join overhead for story detail views
--   - Simpler API (single response object)

-- Add code_context JSONB column to stories table
ALTER TABLE stories ADD COLUMN IF NOT EXISTS code_context JSONB;

-- Add index for JSONB queries (GIN index for containment/existence checks)
CREATE INDEX IF NOT EXISTS idx_stories_code_context
ON stories USING GIN (code_context);

-- Add partial index for stories with code context (for filtering)
CREATE INDEX IF NOT EXISTS idx_stories_has_code_context
ON stories ((code_context IS NOT NULL))
WHERE code_context IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN stories.code_context IS 'JSONB blob containing classification-guided codebase exploration results: relevant_files, code_snippets, classification_category, exploration_duration_ms';

-- Example code_context structure:
-- {
--   "classification": {
--     "category": "scheduling",
--     "confidence": "high",
--     "reasoning": "Issue mentions scheduled pins and Pinterest posting",
--     "keywords_matched": ["schedule", "pin", "pinterest"]
--   },
--   "relevant_files": [
--     {
--       "path": "packages/scheduler/src/services/pin_scheduler.ts",
--       "line_start": 142,
--       "relevance": "5 matches: schedule, pin, post"
--     }
--   ],
--   "code_snippets": [
--     {
--       "file_path": "packages/scheduler/src/services/pin_scheduler.ts",
--       "line_start": 140,
--       "line_end": 160,
--       "content": "async function schedulePin(...) { ... }",
--       "language": "typescript",
--       "context": "Main scheduling function"
--     }
--   ],
--   "exploration_duration_ms": 450,
--   "classification_duration_ms": 280,
--   "explored_at": "2025-01-20T12:00:00Z"
-- }
