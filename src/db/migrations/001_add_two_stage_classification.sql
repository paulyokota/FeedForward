-- Migration: Add Two-Stage Classification System Fields
-- Date: 2026-01-07
-- Description: Adds Stage 1 and Stage 2 classification fields to conversations table

-- Add Stage 1 classification fields
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS stage1_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS stage1_confidence VARCHAR(20),
ADD COLUMN IF NOT EXISTS stage1_routing_priority VARCHAR(20),
ADD COLUMN IF NOT EXISTS stage1_urgency VARCHAR(20),
ADD COLUMN IF NOT EXISTS stage1_auto_response_eligible BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS stage1_routing_team VARCHAR(50);

-- Add Stage 2 classification fields
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS stage2_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS stage2_confidence VARCHAR(20),
ADD COLUMN IF NOT EXISTS classification_changed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS disambiguation_level VARCHAR(20),
ADD COLUMN IF NOT EXISTS stage2_reasoning TEXT;

-- Add support context tracking
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS has_support_response BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS support_response_count INTEGER DEFAULT 0;

-- Add source URL (if not already exists from theme extraction work)
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Add resolution analysis
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS resolution_action VARCHAR(100),
ADD COLUMN IF NOT EXISTS resolution_detected BOOLEAN DEFAULT FALSE;

-- Add support insights (JSONB for flexible structure)
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS support_insights JSONB;

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_conversations_stage1_type
    ON conversations(stage1_type)
    WHERE stage1_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_stage2_type
    ON conversations(stage2_type)
    WHERE stage2_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_classification_changed
    ON conversations(classification_changed)
    WHERE classification_changed = TRUE;

CREATE INDEX IF NOT EXISTS idx_conversations_disambiguation_level
    ON conversations(disambiguation_level)
    WHERE disambiguation_level IN ('high', 'medium');

CREATE INDEX IF NOT EXISTS idx_conversations_has_support_response
    ON conversations(has_support_response)
    WHERE has_support_response = TRUE;

-- Add comment explaining the two-stage system
COMMENT ON COLUMN conversations.stage1_type IS 'Fast routing classification (8 types: product_issue, how_to_question, feature_request, account_issue, billing_question, configuration_help, general_inquiry, spam)';
COMMENT ON COLUMN conversations.stage2_type IS 'Refined classification with full conversation context';
COMMENT ON COLUMN conversations.classification_changed IS 'TRUE if Stage 2 classification differs from Stage 1';
COMMENT ON COLUMN conversations.disambiguation_level IS 'How much support clarified vague customer message (high, medium, low, none)';
COMMENT ON COLUMN conversations.support_insights IS 'Extracted insights: {issue_confirmed, root_cause, solution_type, products_mentioned, features_mentioned}';
