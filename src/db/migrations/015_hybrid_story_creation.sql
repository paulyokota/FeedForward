-- Migration 015: Hybrid Story Creation Support
-- Adds tracking for hybrid cluster-based story creation
-- Issue: #109 - Story creation: integrate hybrid cluster output

-- 1) Add grouping_method to stories table for audit/tracking
-- Distinguishes how the story's conversations were grouped:
--   - 'signature': Legacy signature-based grouping (default for existing stories)
--   - 'hybrid_cluster': New embedding + facet clustering from #108
ALTER TABLE stories ADD COLUMN IF NOT EXISTS
    grouping_method VARCHAR(50) DEFAULT 'signature';

-- 2) Add cluster_id to stories for tracing back to hybrid clusters
-- Format: "emb_{embedding_cluster}_facet_{action_type}_{direction}"
ALTER TABLE stories ADD COLUMN IF NOT EXISTS
    cluster_id VARCHAR(255);

-- 3) Add facet metadata stored with stories for context
-- JSONB allows flexible storage of action_type, direction, etc.
ALTER TABLE stories ADD COLUMN IF NOT EXISTS
    cluster_metadata JSONB;

-- 4) Comments for documentation
COMMENT ON COLUMN stories.grouping_method IS 'How conversations were grouped: signature (legacy) or hybrid_cluster (#108/#109)';
COMMENT ON COLUMN stories.cluster_id IS 'Hybrid cluster ID: emb_{n}_facet_{action_type}_{direction}';
COMMENT ON COLUMN stories.cluster_metadata IS 'Facet metadata: {action_type, direction, embedding_cluster, conversation_count}';

-- 5) Index for querying by grouping method
CREATE INDEX IF NOT EXISTS idx_stories_grouping_method ON stories(grouping_method);
