-- Migration 011: Theme Quality Gates & Error Propagation
-- Adds quality tracking and structured error reporting to pipeline runs
-- Reference: Issue #104

-- 1) Add themes_filtered counter for themes rejected by quality gates
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    themes_filtered INTEGER DEFAULT 0;

-- 2) Add structured error tracking (JSONB for flexibility)
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    errors JSONB DEFAULT '[]';

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS
    warnings JSONB DEFAULT '[]';

-- 3) Add theme quality metadata to themes table
ALTER TABLE themes ADD COLUMN IF NOT EXISTS
    quality_score REAL;  -- 0.0-1.0 composite score

ALTER TABLE themes ADD COLUMN IF NOT EXISTS
    quality_details JSONB;  -- {vocabulary_match: bool, confidence: float, ...}

-- 4) Index for finding low-quality themes
CREATE INDEX IF NOT EXISTS idx_themes_quality_score
    ON themes(quality_score)
    WHERE quality_score IS NOT NULL;

COMMENT ON COLUMN pipeline_runs.themes_filtered IS 'Count of themes filtered by quality gates (low confidence, unknown vocabulary)';
COMMENT ON COLUMN pipeline_runs.errors IS 'Array of structured errors: [{phase, message, details}, ...]';
COMMENT ON COLUMN pipeline_runs.warnings IS 'Array of warning messages for non-fatal issues';
COMMENT ON COLUMN themes.quality_score IS 'Composite quality score 0.0-1.0 from vocabulary match + confidence';
COMMENT ON COLUMN themes.quality_details IS 'Breakdown of quality gate checks: vocabulary_match, confidence, etc.';
