-- Migration 010: Conversation Run Scoping
-- Fix #103: Use pipeline_run_id instead of timestamp heuristics for run scoping.
--
-- This migration adds explicit pipeline_run_id tracking to conversations,
-- replacing the broken timestamp heuristic (c.classified_at >= pr.started_at)
-- that incorrectly associated conversations with runs.

-- 1) Add pipeline_run_id column to conversations table
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id);

-- 2) Create index for efficient run-scoped queries
CREATE INDEX IF NOT EXISTS idx_conversations_pipeline_run_id
    ON conversations(pipeline_run_id);

-- 3) Add comment documenting the column's purpose
COMMENT ON COLUMN conversations.pipeline_run_id IS 'Pipeline run that classified this conversation. Replaces timestamp heuristics for accurate run scoping.';
