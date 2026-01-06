-- FeedForward Database Schema
-- PostgreSQL 14+

-- Conversations table: stores classified Intercom conversations
CREATE TABLE IF NOT EXISTS conversations (
    -- Primary key: Intercom conversation ID
    id TEXT PRIMARY KEY,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    classified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Raw input from Intercom
    source_body TEXT,
    source_type TEXT,                 -- 'conversation', 'email', etc.
    source_subject TEXT,              -- Email subject if applicable
    contact_email TEXT,
    contact_id TEXT,

    -- Classification output
    issue_type TEXT NOT NULL CHECK (issue_type IN (
        'bug_report', 'feature_request', 'product_question',
        'plan_question', 'marketing_question', 'billing',
        'account_access', 'feedback', 'other'
    )),
    sentiment TEXT NOT NULL CHECK (sentiment IN (
        'frustrated', 'neutral', 'satisfied'
    )),
    churn_risk BOOLEAN NOT NULL DEFAULT FALSE,
    priority TEXT NOT NULL CHECK (priority IN (
        'urgent', 'high', 'normal', 'low'
    )),

    -- Metadata
    classifier_version TEXT DEFAULT 'v1',
    raw_response JSONB                -- Full LLM response for debugging
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_conversations_created_at
    ON conversations(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversations_issue_type
    ON conversations(issue_type);

CREATE INDEX IF NOT EXISTS idx_conversations_churn_risk
    ON conversations(churn_risk)
    WHERE churn_risk = TRUE;

CREATE INDEX IF NOT EXISTS idx_conversations_priority
    ON conversations(priority)
    WHERE priority IN ('urgent', 'high');

-- Pipeline runs table: tracks batch processing history
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Configuration
    date_from TIMESTAMP WITH TIME ZONE,
    date_to TIMESTAMP WITH TIME ZONE,

    -- Results
    conversations_fetched INTEGER DEFAULT 0,
    conversations_filtered INTEGER DEFAULT 0,
    conversations_classified INTEGER DEFAULT 0,
    conversations_stored INTEGER DEFAULT 0,

    -- Status
    status TEXT CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT
);

-- Escalation log: tracks alerts and tickets created
CREATE TABLE IF NOT EXISTS escalation_log (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    rule_id TEXT NOT NULL,              -- e.g., 'R001', 'R002'
    action_type TEXT NOT NULL CHECK (action_type IN (
        'slack_alert', 'shortcut_ticket', 'log_only'
    )),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Action details
    slack_channel TEXT,                 -- For slack_alert
    shortcut_story_id TEXT,             -- For shortcut_ticket

    -- Deduplication
    UNIQUE (conversation_id, rule_id)
);

CREATE INDEX IF NOT EXISTS idx_escalation_log_conversation
    ON escalation_log(conversation_id);

CREATE INDEX IF NOT EXISTS idx_escalation_log_created_at
    ON escalation_log(created_at DESC);

-- Useful views
CREATE OR REPLACE VIEW conversation_summary AS
SELECT
    issue_type,
    COUNT(*) as count,
    SUM(CASE WHEN churn_risk THEN 1 ELSE 0 END) as churn_risk_count,
    COUNT(*) FILTER (WHERE sentiment = 'frustrated') as frustrated_count
FROM conversations
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY issue_type
ORDER BY count DESC;
