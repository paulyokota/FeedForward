-- Migration 024: Add conversation_id to stage_executions
-- Issue: #214 - Conversation protocol integration for agent dialogue
--
-- Links each stage execution to its Agenterminal conversation thread.
-- Nullable because conversations are created when stages start (not on row creation).

ALTER TABLE stage_executions
    ADD COLUMN conversation_id TEXT;

COMMENT ON COLUMN stage_executions.conversation_id IS 'Agenterminal conversation ID for this stage execution. Created when stage starts.';

-- One conversation per stage execution (prevents accidental reuse)
CREATE UNIQUE INDEX idx_stage_conversation
    ON stage_executions(conversation_id)
    WHERE conversation_id IS NOT NULL;
