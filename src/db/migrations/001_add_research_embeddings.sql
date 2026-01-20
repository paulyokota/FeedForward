-- Migration: Add research_embeddings table for RAG/Search functionality
-- Date: 2026-01-13
-- Description: Creates pgvector extension and research_embeddings table for unified search

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Research embeddings table: stores embedded content from multiple sources
CREATE TABLE IF NOT EXISTS research_embeddings (
    id SERIAL PRIMARY KEY,

    -- Source identification
    source_type TEXT NOT NULL,              -- 'coda_page', 'coda_theme', 'intercom'
    source_id TEXT NOT NULL,                -- Unique ID within source
    content_hash TEXT NOT NULL,             -- SHA-256 hash for change detection

    -- Content
    title TEXT NOT NULL,                    -- Display title
    content TEXT NOT NULL,                  -- Full text content for embedding
    url TEXT NOT NULL,                      -- Link to original source

    -- Vector embedding (OpenAI text-embedding-3-small = 1536 dimensions)
    embedding vector(1536) NOT NULL,

    -- Metadata (source-specific fields)
    metadata JSONB DEFAULT '{}',            -- participant, tags, url, etc.

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Ensure unique source entries
    UNIQUE(source_type, source_id)
);

-- HNSW index for fast approximate nearest neighbor search
-- Using cosine similarity which works well for semantic search
CREATE INDEX IF NOT EXISTS idx_research_embeddings_hnsw
    ON research_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- Source type index for filtered queries
CREATE INDEX IF NOT EXISTS idx_research_source_type
    ON research_embeddings(source_type);

-- Content hash index for upsert efficiency
CREATE INDEX IF NOT EXISTS idx_research_content_hash
    ON research_embeddings(content_hash);

-- Created at index for ordering
CREATE INDEX IF NOT EXISTS idx_research_created_at
    ON research_embeddings(created_at DESC);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_research_embeddings_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating timestamp
DROP TRIGGER IF EXISTS research_embeddings_updated_at ON research_embeddings;
CREATE TRIGGER research_embeddings_updated_at
    BEFORE UPDATE ON research_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_research_embeddings_timestamp();

-- Comments for documentation
COMMENT ON TABLE research_embeddings IS 'Unified embeddings table for RAG/Search across all data sources';
COMMENT ON COLUMN research_embeddings.source_type IS 'Data source: coda_page, coda_theme, intercom';
COMMENT ON COLUMN research_embeddings.source_id IS 'Unique identifier within the source system';
COMMENT ON COLUMN research_embeddings.content_hash IS 'SHA-256 hash of content for change detection';
COMMENT ON COLUMN research_embeddings.embedding IS 'OpenAI text-embedding-3-small vector (1536 dims)';
COMMENT ON COLUMN research_embeddings.metadata IS 'Source-specific metadata as JSONB';
