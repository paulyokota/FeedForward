-- Migration 023: Discovery Engine Foundation
-- Issue: #213 - State machine, artifact contracts, and run metadata
--
-- Creates the core tables for the Discovery Engine:
--   discovery_runs        — top-level run lifecycle
--   stage_executions      — per-stage records with checkpoint artifacts
--   agent_invocations     — per-agent records within a stage
--
-- Design decisions:
--   - UUID PK for discovery_runs (matches #212 spec)
--   - Stage progression derived from stage_executions rows, not stored redundantly
--   - Atomic transitions enforced via partial unique index (one active stage per run)
--   - ON DELETE CASCADE from runs → stages → invocations
--   - All timestamps are timestamptz

-- Stage type enum
CREATE TYPE discovery_stage AS ENUM (
    'exploration',
    'opportunity_framing',
    'solution_validation',
    'feasibility_risk',
    'prioritization',
    'human_review'
);

-- Run status enum
CREATE TYPE discovery_run_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed',
    'stopped'
);

-- Stage execution status enum
CREATE TYPE discovery_stage_status AS ENUM (
    'pending',
    'in_progress',
    'checkpoint_reached',
    'completed',
    'failed',
    'sent_back'
);

-- Agent invocation status enum
CREATE TYPE discovery_agent_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed'
);

-- ============================================================================
-- discovery_runs — top-level run record
-- ============================================================================
CREATE TABLE discovery_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status discovery_run_status NOT NULL DEFAULT 'pending',
    current_stage discovery_stage,  -- NULL before first stage starts

    -- Configuration
    config JSONB NOT NULL DEFAULT '{}',  -- scope boundaries, resource constraints

    -- Run metadata (per #212: agent_versions, toolset_versions, input_snapshot_ref)
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Timestamps
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Error tracking
    errors JSONB NOT NULL DEFAULT '[]',
    warnings JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX idx_discovery_runs_status ON discovery_runs(status);

COMMENT ON TABLE discovery_runs IS 'Top-level discovery cycle runs. Each run progresses through 6 stages.';
COMMENT ON COLUMN discovery_runs.config IS 'Run configuration: scope boundaries, resource constraints per Stage 0 scope conditions';
COMMENT ON COLUMN discovery_runs.metadata IS 'Run metadata: {agent_versions, toolset_versions, input_snapshot_ref, ...}';
COMMENT ON COLUMN discovery_runs.current_stage IS 'Current stage in the 6-stage pipeline. NULL before first stage starts.';

-- ============================================================================
-- stage_executions — per-stage records
-- ============================================================================
CREATE TABLE stage_executions (
    id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    stage discovery_stage NOT NULL,
    status discovery_stage_status NOT NULL DEFAULT 'pending',
    attempt_number INTEGER NOT NULL DEFAULT 1,

    -- Participants
    participating_agents TEXT[] NOT NULL DEFAULT '{}',

    -- Checkpoint artifact (validated by Pydantic on write)
    artifacts JSONB,
    artifact_schema_version INTEGER DEFAULT 1,

    -- Send-back tracking
    sent_back_from discovery_stage,  -- which stage triggered the send-back
    send_back_reason TEXT,           -- guidance from the stage that sent it back

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Uniqueness: one attempt per stage per run
    CONSTRAINT uq_stage_execution_attempt UNIQUE (run_id, stage, attempt_number)
);

-- One active stage per run (prevents concurrent in-progress stages)
CREATE UNIQUE INDEX idx_one_active_stage_per_run
    ON stage_executions(run_id)
    WHERE status IN ('in_progress', 'checkpoint_reached');

CREATE INDEX idx_stage_executions_run_stage ON stage_executions(run_id, stage, status);

COMMENT ON TABLE stage_executions IS 'Per-stage execution records. Stage progression is derived from these rows ordered by started_at.';
COMMENT ON COLUMN stage_executions.artifacts IS 'Checkpoint artifact JSONB, validated against Pydantic models on write';
COMMENT ON COLUMN stage_executions.sent_back_from IS 'If this execution was created from a send-back, which stage initiated it';

-- ============================================================================
-- agent_invocations — per-agent records within a stage
-- ============================================================================
CREATE TABLE agent_invocations (
    id SERIAL PRIMARY KEY,
    stage_execution_id INTEGER NOT NULL REFERENCES stage_executions(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,  -- denormalized for queries

    agent_name VARCHAR(100) NOT NULL,
    status discovery_agent_status NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,

    -- Output
    output JSONB,
    error TEXT,

    -- Cost tracking (Phase 1: recorded, not budgeted)
    token_usage JSONB,  -- {prompt_tokens, completion_tokens, total_tokens, estimated_cost}

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_agent_invocations_stage ON agent_invocations(stage_execution_id);
CREATE INDEX idx_agent_invocations_run ON agent_invocations(run_id);

COMMENT ON TABLE agent_invocations IS 'Per-agent invocation records within a stage execution';
COMMENT ON COLUMN agent_invocations.run_id IS 'Denormalized from stage_executions for query convenience';
COMMENT ON COLUMN agent_invocations.token_usage IS 'Phase 1: recorded for auditability, not used for budgeting';
