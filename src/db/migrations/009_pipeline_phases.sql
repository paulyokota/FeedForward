-- Migration 009: Pipeline Phase Tracking
-- Extends pipeline to support theme extraction and optional story creation
-- Reference: Architecture review 2026-01-21

-- 1) Fix CHECK constraint to include stopping/stopped states
-- (These are already used in code but weren't in the constraint)
ALTER TABLE pipeline_runs DROP CONSTRAINT IF EXISTS pipeline_runs_status_check;
ALTER TABLE pipeline_runs ADD CONSTRAINT pipeline_runs_status_check
    CHECK (status IN ('running', 'stopping', 'stopped', 'completed', 'failed'));

-- 2) Add phase tracking to pipeline_runs
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    current_phase VARCHAR(50) DEFAULT 'classification';

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    auto_create_stories BOOLEAN DEFAULT FALSE;

-- 3) Add theme extraction stats
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    themes_extracted INTEGER DEFAULT 0;

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    themes_new INTEGER DEFAULT 0;

-- 4) Add story creation stats
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    stories_created INTEGER DEFAULT 0;

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    orphans_created INTEGER DEFAULT 0;

-- 5) Add stories_ready flag (true when themes extracted, stories can be created)
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    stories_ready BOOLEAN DEFAULT FALSE;

-- 6) Link stories to pipeline runs for "Run Results" panel
ALTER TABLE stories ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id);

CREATE INDEX IF NOT EXISTS idx_stories_pipeline_run_id
    ON stories(pipeline_run_id);

-- 7) Link themes to pipeline runs for tracking
ALTER TABLE themes ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id);

CREATE INDEX IF NOT EXISTS idx_themes_pipeline_run_id
    ON themes(pipeline_run_id);

-- 8) Backfill existing completed runs with phase='completed'
UPDATE pipeline_runs
SET current_phase = 'completed'
WHERE status IN ('completed', 'failed', 'stopped')
  AND current_phase IS NULL;

-- 9) Backfill running runs with phase='classification'
UPDATE pipeline_runs
SET current_phase = 'classification'
WHERE status = 'running'
  AND current_phase IS NULL;

COMMENT ON COLUMN pipeline_runs.current_phase IS 'Current execution phase: classification, theme_extraction, pm_review, story_creation, completed';
COMMENT ON COLUMN pipeline_runs.auto_create_stories IS 'Whether to automatically run PM review and create stories after theme extraction';
COMMENT ON COLUMN pipeline_runs.stories_ready IS 'True when theme extraction complete - stories can be created manually';
