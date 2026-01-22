-- Migration: Add conversation_embeddings and conversation_facet tables
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

    -- Foreign keys with cascade behavior matching migration 010 pattern
    conversation_id VARCHAR(255) NOT NULL,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    -- Embedding data
    embedding vector(1536) NOT NULL,  -- text-embedding-3-small dimensions
    model_version VARCHAR(50) NOT NULL DEFAULT 'text-embedding-3-small',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Prevent duplicate embeddings per conversation per run
    UNIQUE (conversation_id, pipeline_run_id)
);

-- Index for run-scoped lookups (critical for T-004 isolation)
CREATE INDEX IF NOT EXISTS idx_conv_embeddings_run_conv
    ON conversation_embeddings(pipeline_run_id, conversation_id);

-- HNSW index for fast approximate nearest neighbor search
-- Using cosine similarity (same as research_embeddings)
CREATE INDEX IF NOT EXISTS idx_conv_embeddings_hnsw
    ON conversation_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- conversation_facet: Extracted facets for fine-grained sub-clustering
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversation_facet (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys with cascade behavior matching migration 010 pattern
    conversation_id VARCHAR(255) NOT NULL,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    -- Facet data (per T-006 hybrid clustering design)
    action_type VARCHAR(20) NOT NULL,   -- inquiry, complaint, bug_report, how_to_question, feature_request, account_change, delete_request
    direction VARCHAR(15) NOT NULL,      -- excess, deficit, creation, deletion, modification, performance, neutral
    symptom VARCHAR(200),                -- Brief description (10 words max, ~200 chars)
    user_goal VARCHAR(200),              -- What user is trying to accomplish (10 words max, ~200 chars)

    -- Extraction metadata
    model_version VARCHAR(50) NOT NULL DEFAULT 'gpt-4o-mini',
    extraction_confidence VARCHAR(10),  -- high, medium, low

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Prevent duplicate facets per conversation per run
    UNIQUE (conversation_id, pipeline_run_id)
);

-- Index for run-scoped lookups (critical for T-004 isolation)
CREATE INDEX IF NOT EXISTS idx_conv_facet_run_conv
    ON conversation_facet(pipeline_run_id, conversation_id);

-- Composite index for sub-clustering queries (action_type + direction within a run)
CREATE INDEX IF NOT EXISTS idx_conv_facet_action_direction
    ON conversation_facet(pipeline_run_id, action_type, direction);

-- =============================================================================
-- Comments for documentation
-- =============================================================================
COMMENT ON TABLE conversation_embeddings IS 'Vector embeddings for conversation semantic clustering (T-006 hybrid approach)';
COMMENT ON COLUMN conversation_embeddings.conversation_id IS 'References conversations.id';
COMMENT ON COLUMN conversation_embeddings.pipeline_run_id IS 'Run scoping per T-004 - links to pipeline_runs.id';
COMMENT ON COLUMN conversation_embeddings.embedding IS 'OpenAI text-embedding-3-small vector (1536 dims)';

COMMENT ON TABLE conversation_facet IS 'Extracted facets for fine-grained sub-clustering within embedding clusters';
COMMENT ON COLUMN conversation_facet.conversation_id IS 'References conversations.id';
COMMENT ON COLUMN conversation_facet.pipeline_run_id IS 'Run scoping per T-004 - links to pipeline_runs.id';
COMMENT ON COLUMN conversation_facet.action_type IS 'inquiry, complaint, bug_report, how_to_question, feature_request, account_change, delete_request';
COMMENT ON COLUMN conversation_facet.direction IS 'excess, deficit, creation, deletion, modification, performance, neutral';
COMMENT ON COLUMN conversation_facet.symptom IS 'Brief description of user issue (10 words max)';
COMMENT ON COLUMN conversation_facet.user_goal IS 'What user is trying to accomplish (10 words max)';
