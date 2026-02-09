-- Migration 025: Add parent_run_id for experiment re-entry runs
-- Issue: #224 - Experiment Results Intake
--
-- Adds parent_run_id to discovery_runs so re-entry runs (triggered after
-- experiment results come in) can link back to the original run that
-- produced the experiment plan.
--
-- Experiment results are stored in the existing metadata JSONB column
-- (no schema change needed for that).

ALTER TABLE discovery_runs
    ADD COLUMN parent_run_id UUID REFERENCES discovery_runs(id);

COMMENT ON COLUMN discovery_runs.parent_run_id IS 'Links re-entry runs to their parent run. NULL for original runs.';

-- Index for looking up child runs of a parent
CREATE INDEX idx_discovery_runs_parent
    ON discovery_runs(parent_run_id)
    WHERE parent_run_id IS NOT NULL;
