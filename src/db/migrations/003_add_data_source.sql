-- Migration 003: Add multi-source data tracking
-- Extends schema to support Coda research data alongside Intercom conversations

-- Add source tracking to conversations
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50) DEFAULT 'intercom',
ADD COLUMN IF NOT EXISTS source_metadata JSONB;

-- Add source tracking to themes
ALTER TABLE themes
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50) DEFAULT 'intercom';

-- Add source breakdown to aggregates
ALTER TABLE theme_aggregates
ADD COLUMN IF NOT EXISTS source_counts JSONB DEFAULT '{}';
-- Example: {"intercom": 45, "coda": 3}

-- Indexes for source filtering
CREATE INDEX IF NOT EXISTS idx_themes_data_source ON themes(data_source);
CREATE INDEX IF NOT EXISTS idx_conversations_data_source ON conversations(data_source);
CREATE INDEX IF NOT EXISTS idx_theme_aggregates_source_counts ON theme_aggregates USING GIN(source_counts);

-- Update existing records to have explicit intercom source
UPDATE conversations SET data_source = 'intercom' WHERE data_source IS NULL;
UPDATE themes SET data_source = 'intercom' WHERE data_source IS NULL;

-- Create view for cross-source theme analysis
CREATE OR REPLACE VIEW cross_source_themes AS
SELECT
    ta.issue_signature,
    ta.product_area,
    ta.component,
    ta.occurrence_count as total_conversations,
    ta.source_counts,
    COALESCE((ta.source_counts->>'coda')::int, 0) as coda_count,
    COALESCE((ta.source_counts->>'intercom')::int, 0) as intercom_count,
    CASE
        WHEN ta.source_counts ? 'coda' AND ta.source_counts ? 'intercom'
        THEN 'high_confidence'
        WHEN ta.source_counts ? 'coda'
        THEN 'strategic'
        ELSE 'tactical'
    END as priority_category,
    ta.first_seen_at,
    ta.last_seen_at,
    ta.ticket_created,
    ta.ticket_id
FROM theme_aggregates ta
WHERE ta.occurrence_count >= 1
ORDER BY
    (COALESCE((ta.source_counts->>'coda')::int, 0) > 0)::int DESC,
    (COALESCE((ta.source_counts->>'intercom')::int, 0)) DESC;

COMMENT ON COLUMN conversations.data_source IS 'Source of the conversation: intercom, coda, etc.';
COMMENT ON COLUMN conversations.source_metadata IS 'Source-specific metadata (page_id, participant, etc.)';
COMMENT ON COLUMN themes.data_source IS 'Source of the theme: intercom, coda, etc.';
COMMENT ON COLUMN theme_aggregates.source_counts IS 'Count of occurrences by source: {"intercom": N, "coda": M}';
