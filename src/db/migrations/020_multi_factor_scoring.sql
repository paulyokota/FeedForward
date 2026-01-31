-- Migration 020: Multi-Factor Story Scoring
-- Adds actionability, fix_size, severity, and churn_risk scores for sortable story prioritization
-- Issue: #188 - Add sortable multi-factor story scoring
--
-- Scores are 0-100 continuous values computed from:
-- - actionability: presence of impl context, resolution data, evidence quality
-- - fix_size: estimated complexity based on files, excerpts, symptoms
-- - severity: priority mapping + error indicators
-- - churn_risk: churn flag + org breadth
--
-- score_metadata stores per-factor breakdown for explainability

-- 1) Add score columns (DECIMAL 5,2 matches existing confidence_score)
ALTER TABLE stories ADD COLUMN IF NOT EXISTS actionability_score DECIMAL(5,2);
ALTER TABLE stories ADD COLUMN IF NOT EXISTS fix_size_score DECIMAL(5,2);
ALTER TABLE stories ADD COLUMN IF NOT EXISTS severity_score DECIMAL(5,2);
ALTER TABLE stories ADD COLUMN IF NOT EXISTS churn_risk_score DECIMAL(5,2);

-- 2) Add score_metadata JSONB for per-factor breakdown
ALTER TABLE stories ADD COLUMN IF NOT EXISTS score_metadata JSONB;

-- 3) Plain b-tree indexes for sorting (Postgres can scan in either direction)
CREATE INDEX IF NOT EXISTS idx_stories_actionability ON stories(actionability_score);
CREATE INDEX IF NOT EXISTS idx_stories_fix_size ON stories(fix_size_score);
CREATE INDEX IF NOT EXISTS idx_stories_severity ON stories(severity_score);
CREATE INDEX IF NOT EXISTS idx_stories_churn_risk ON stories(churn_risk_score);

-- 4) Column comments for documentation
COMMENT ON COLUMN stories.actionability_score IS 'How actionable (0-100): impl context, resolution data, evidence quality';
COMMENT ON COLUMN stories.fix_size_score IS 'Estimated fix complexity (0-100): files involved, symptoms count';
COMMENT ON COLUMN stories.severity_score IS 'Business severity (0-100): priority mapping, error indicators';
COMMENT ON COLUMN stories.churn_risk_score IS 'Customer churn risk (0-100): churn flag, org diversity';
COMMENT ON COLUMN stories.score_metadata IS 'JSONB breakdown of per-factor scoring components for explainability';
