-- Migration: Add conversation_embeddings and conversation_facets tables
-- Date: 2026-01-22
-- Issue: #105 - Data model for embedding-based clustering
-- Description: Creates tables for storing conversation embeddings and extracted facets
--              for hybrid clustering (embeddings + facet sub-grouping per T-006)

-- Note: pgvector extension already enabled in 001_add_research_embeddings.sql
-- CREATE EXTENSION IF NOT EXISTS vector;  -- Uncomment if running standalone

-- =============================================================================
-- conversation_embeddings: Vector embeddings for semantic clustering
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversation_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys (not enforced to allow orphan cleanup flexibility)
    conversation_id VARCHAR(255) NOT NULL,
    pipeline_run_id UUID,  -- Links to pipeline_runs.id (T-004 run scoping)

    -- Embedding data
    embedding vector(1536) NOT NULL,  -- text-embedding-3-small dimensions
    model_version VARCHAR(50) NOT NULL DEFAULT 'text-embedding-3-small',

    -- Content hash for change detection (re-embed if conversation changed)
    content_hash VARCHAR(64),  -- SHA-256 hex

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for run-scoped lookups (critical for T-004 isolation)
CREATE INDEX IF NOT EXISTS idx_conv_embeddings_run_conv
    ON conversation_embeddings(pipeline_run_id, conversation_id);

-- Index for finding existing embeddings for a conversation
CREATE INDEX IF NOT EXISTS idx_conv_embeddings_conv_id
    ON conversation_embeddings(conversation_id);

-- HNSW index for fast approximate nearest neighbor search
-- Using cosine similarity (same as research_embeddings)
CREATE INDEX IF NOT EXISTS idx_conv_embeddings_hnsw
    ON conversation_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- conversation_facets: Extracted facets for fine-grained sub-clustering
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversation_facets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys
    conversation_id VARCHAR(255) NOT NULL,
    pipeline_run_id UUID,  -- Links to pipeline_runs.id (T-004 run scoping)

    -- Facet data (per T-006 hybrid clustering design)
    action_type VARCHAR(50) NOT NULL,  -- inquiry, complaint, bug_report, how_to_question, feature_request, account_change, delete_request
    direction VARCHAR(50) NOT NULL,     -- excess, deficit, creation, deletion, modification, performance, neutral
    symptom TEXT,                        -- Brief description (10 words max)
    user_goal TEXT,                      -- What user is trying to accomplish (10 words max)

    -- Extraction metadata
    model_version VARCHAR(50) NOT NULL DEFAULT 'gpt-4o-mini',
    extraction_confidence VARCHAR(10),  -- high, medium, low

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for run-scoped lookups (critical for T-004 isolation)
CREATE INDEX IF NOT EXISTS idx_conv_facets_run_conv
    ON conversation_facets(pipeline_run_id, conversation_id);

-- Index for finding existing facets for a conversation
CREATE INDEX IF NOT EXISTS idx_conv_facets_conv_id
    ON conversation_facets(conversation_id);

-- Indexes for facet-based grouping/filtering
CREATE INDEX IF NOT EXISTS idx_conv_facets_action_type
    ON conversation_facets(action_type);

CREATE INDEX IF NOT EXISTS idx_conv_facets_direction
    ON conversation_facets(direction);

-- Composite index for sub-clustering queries (action_type + direction)
CREATE INDEX IF NOT EXISTS idx_conv_facets_action_direction
    ON conversation_facets(pipeline_run_id, action_type, direction);

-- =============================================================================
-- Comments for documentation
-- =============================================================================
COMMENT ON TABLE conversation_embeddings IS 'Vector embeddings for conversation semantic clustering (T-006 hybrid approach)';
COMMENT ON COLUMN conversation_embeddings.conversation_id IS 'References conversations.id';
COMMENT ON COLUMN conversation_embeddings.pipeline_run_id IS 'Run scoping per T-004 - links to pipeline_runs.id';
COMMENT ON COLUMN conversation_embeddings.embedding IS 'OpenAI text-embedding-3-small vector (1536 dims)';
COMMENT ON COLUMN conversation_embeddings.content_hash IS 'SHA-256 hash of embedded content for change detection';

COMMENT ON TABLE conversation_facets IS 'Extracted facets for fine-grained sub-clustering within embedding clusters';
COMMENT ON COLUMN conversation_facets.conversation_id IS 'References conversations.id';
COMMENT ON COLUMN conversation_facets.pipeline_run_id IS 'Run scoping per T-004 - links to pipeline_runs.id';
COMMENT ON COLUMN conversation_facets.action_type IS 'inquiry, complaint, bug_report, how_to_question, feature_request, account_change, delete_request';
COMMENT ON COLUMN conversation_facets.direction IS 'excess, deficit, creation, deletion, modification, performance, neutral';
COMMENT ON COLUMN conversation_facets.symptom IS 'Brief description of user issue (10 words max)';
COMMENT ON COLUMN conversation_facets.user_goal IS 'What user is trying to accomplish (10 words max)';
