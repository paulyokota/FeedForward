-- Migration 018: LLM-Powered Resolution Extraction
-- Issue #146: Replace regex-based extraction with LLM extraction in theme extractor
--
-- Adds resolution fields to themes table that are populated by the LLM
-- during theme extraction (instead of the old regex-based ResolutionAnalyzer
-- and KnowledgeExtractor which had only 8-14% coverage).

-- Add resolution_action: What action support took
-- Values: escalated_to_engineering, provided_workaround, user_education,
--         manual_intervention, no_resolution
ALTER TABLE themes ADD COLUMN IF NOT EXISTS resolution_action VARCHAR(50);

-- Add root_cause: LLM hypothesis for why this happened (1 sentence)
ALTER TABLE themes ADD COLUMN IF NOT EXISTS root_cause TEXT;

-- Add solution_provided: What solution was given (1-2 sentences)
ALTER TABLE themes ADD COLUMN IF NOT EXISTS solution_provided TEXT;

-- Add resolution_category: Category for analytics
-- Values: escalation, workaround, education, self_service_gap, unresolved
ALTER TABLE themes ADD COLUMN IF NOT EXISTS resolution_category VARCHAR(50);

-- Index for analytics queries on resolution_category
CREATE INDEX IF NOT EXISTS idx_themes_resolution_category
    ON themes(resolution_category)
    WHERE resolution_category IS NOT NULL;

-- Comments for documentation
COMMENT ON COLUMN themes.resolution_action IS 'LLM-detected support action: escalated_to_engineering, provided_workaround, user_education, manual_intervention, no_resolution (Issue #146)';
COMMENT ON COLUMN themes.root_cause IS 'LLM hypothesis for root cause - 1 sentence (Issue #146)';
COMMENT ON COLUMN themes.solution_provided IS 'Solution given by support - 1-2 sentences (Issue #146)';
COMMENT ON COLUMN themes.resolution_category IS 'Category for analytics: escalation, workaround, education, self_service_gap, unresolved (Issue #146)';
