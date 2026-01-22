-- Migration: Add facet extraction phase tracking to pipeline_runs
-- Date: 2026-01-22
-- Issue: #107 - Pipeline step: facet extraction for conversations
-- Description: Adds columns to track facet extraction progress in pipeline_runs

-- Add facet extraction tracking columns
ALTER TABLE pipeline_runs
ADD COLUMN IF NOT EXISTS facets_extracted INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS facets_failed INTEGER DEFAULT 0;

-- Comment for documentation
COMMENT ON COLUMN pipeline_runs.facets_extracted IS 'Number of conversations with successfully extracted facets';
COMMENT ON COLUMN pipeline_runs.facets_failed IS 'Number of conversations where facet extraction failed';
