-- Migration 013: Embedding Generation Phase
-- Adds tracking for embedding generation in pipeline runs
-- Issue: #106 - Pipeline step: embedding generation for conversations

-- 1) Add embeddings_generated count to pipeline_runs
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    embeddings_generated INTEGER DEFAULT 0;

-- 2) Add embeddings_failed count for tracking errors
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    embeddings_failed INTEGER DEFAULT 0;

-- 3) Update current_phase comment to include embedding_generation
COMMENT ON COLUMN pipeline_runs.current_phase IS 'Current execution phase: classification, embedding_generation, theme_extraction, pm_review, story_creation, completed';

-- 4) Add comment for new columns
COMMENT ON COLUMN pipeline_runs.embeddings_generated IS 'Number of conversation embeddings successfully generated (#106)';
COMMENT ON COLUMN pipeline_runs.embeddings_failed IS 'Number of conversations where embedding generation failed (#106)';
