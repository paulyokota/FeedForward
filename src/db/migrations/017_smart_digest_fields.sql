-- Migration 017: Smart Digest Fields for Theme Extraction
-- Issue #144: Replace heuristic digests with LLM-powered summarization
--
-- Adds fields for richer theme context:
-- - diagnostic_summary: 2-4 sentence summary optimized for developers
-- - key_excerpts: Relevant conversation excerpts with relevance explanations
-- - context_usage_logs: Tracks which product docs were used (for optimization)

-- 1) Add diagnostic_summary to themes table
-- A concise summary for developers debugging the issue
ALTER TABLE themes ADD COLUMN IF NOT EXISTS diagnostic_summary TEXT;

-- 2) Add key_excerpts as JSONB
-- Format: [{"text": "...", "relevance": "Why this excerpt matters for diagnosing the issue"}, ...]
-- Stores the most diagnostic parts of the conversation with explanations
ALTER TABLE themes ADD COLUMN IF NOT EXISTS key_excerpts JSONB DEFAULT '[]'::jsonb;

-- 3) Create context_usage_logs table for analytics
-- Tracks which product context was used/missing during theme extraction
-- Enables optimization of product context loading (Phase 2)
CREATE TABLE IF NOT EXISTS context_usage_logs (
    id SERIAL PRIMARY KEY,
    theme_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    -- Context sections that were used in analysis
    -- Format: ["section_name", ...] - from product context docs
    context_used JSONB DEFAULT '[]'::jsonb,

    -- Hints about missing context that would improve analysis
    -- Format: ["missing context description", ...]
    context_gaps JSONB DEFAULT '[]'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4) Indexes for context_usage_logs queries
-- Support analysis of context effectiveness and gap patterns
CREATE INDEX IF NOT EXISTS idx_context_usage_logs_pipeline_run
    ON context_usage_logs(pipeline_run_id);

CREATE INDEX IF NOT EXISTS idx_context_usage_logs_created_at
    ON context_usage_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_context_usage_logs_theme_id
    ON context_usage_logs(theme_id);

-- 5) Comments for documentation
COMMENT ON COLUMN themes.diagnostic_summary IS 'LLM-generated 2-4 sentence summary for developers (Issue #144)';
COMMENT ON COLUMN themes.key_excerpts IS 'Key conversation excerpts: [{text, relevance (descriptive string)}] (Issue #144)';
COMMENT ON TABLE context_usage_logs IS 'Tracks product context usage during theme extraction for optimization (Issue #144)';
COMMENT ON COLUMN context_usage_logs.context_used IS 'Product doc sections used in analysis';
COMMENT ON COLUMN context_usage_logs.context_gaps IS 'Missing context hints for future improvement';
