-- Migration 022: Pipeline Checkpoint for Resumability
-- Issue: #202 - Backfill readiness
--
-- Adds checkpoint column to pipeline_runs for storing resume state during
-- long-running backfills. Checkpoint contains cursor, counts, and phase info.

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    checkpoint JSONB DEFAULT '{}';

COMMENT ON COLUMN pipeline_runs.checkpoint IS
    'Checkpoint for resume: {phase, intercom_cursor, counts, updated_at}';
