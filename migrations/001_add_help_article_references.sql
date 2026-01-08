-- Migration: Add help_article_references table
-- Phase 4a: Help Article Context Injection
-- Created: 2026-01-07

-- Help article references: tracks which articles users referenced in conversations
CREATE TABLE IF NOT EXISTS help_article_references (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    article_id TEXT NOT NULL,
    article_url TEXT NOT NULL,
    article_title TEXT,
    article_category TEXT,
    referenced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Prevent duplicate article references per conversation
    UNIQUE (conversation_id, article_id)
);

-- Index for finding all conversations that referenced a specific article
CREATE INDEX IF NOT EXISTS idx_help_article_references_article_id
    ON help_article_references(article_id);

-- Index for finding all articles referenced in a conversation
CREATE INDEX IF NOT EXISTS idx_help_article_references_conversation_id
    ON help_article_references(conversation_id);

-- Index for finding recently referenced articles
CREATE INDEX IF NOT EXISTS idx_help_article_references_referenced_at
    ON help_article_references(referenced_at DESC);

-- Analytics view: Most referenced articles
CREATE OR REPLACE VIEW most_referenced_articles AS
SELECT
    h.article_id,
    h.article_title,
    h.article_category,
    COUNT(DISTINCT h.conversation_id) as reference_count,
    MIN(h.referenced_at) as first_referenced,
    MAX(h.referenced_at) as last_referenced,
    -- Count how many conversations still had issues after referencing this article
    COUNT(DISTINCT c.id) FILTER (WHERE c.issue_type IN ('bug_report', 'product_question')) as still_had_issues_count
FROM help_article_references h
LEFT JOIN conversations c ON h.conversation_id = c.id
WHERE h.referenced_at > NOW() - INTERVAL '30 days'
GROUP BY h.article_id, h.article_title, h.article_category
ORDER BY reference_count DESC;

-- Analytics view: Conversations with article references
CREATE OR REPLACE VIEW conversations_with_articles AS
SELECT
    c.id,
    c.created_at,
    c.issue_type,
    c.sentiment,
    c.priority,
    array_agg(h.article_title) as referenced_articles,
    COUNT(h.id) as article_count
FROM conversations c
JOIN help_article_references h ON c.id = h.conversation_id
GROUP BY c.id, c.created_at, c.issue_type, c.sentiment, c.priority
ORDER BY c.created_at DESC;

COMMENT ON TABLE help_article_references IS 'Tracks help articles referenced by users in conversations (Phase 4a)';
COMMENT ON COLUMN help_article_references.article_id IS 'Intercom article ID extracted from URL';
COMMENT ON COLUMN help_article_references.article_url IS 'Canonical help article URL';
COMMENT ON COLUMN help_article_references.article_title IS 'Article title fetched from Intercom API';
COMMENT ON COLUMN help_article_references.article_category IS 'Article category/collection';
