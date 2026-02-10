"""Tests for Discovery Engine state machine.

Covers: happy path, failure, retry, backward transitions (send-back),
invalid transitions, terminal states, and invariants.

Uses mock storage to isolate state machine logic from DB.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.discovery.models.enums import (
    AgentStatus,
    RunStatus,
    StageStatus,
    StageType,
    STAGE_ORDER,
)
from src.discovery.models.run import (
    DiscoveryRun,
    RunConfig,
    RunMetadata,
    StageExecution,
)
from src.discovery.services.state_machine import (
    ALLOWED_BACKWARD_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    DiscoveryStateMachine,
    InvalidTransitionError,
)


# ============================================================================
# In-memory storage mock
# ============================================================================


class InMemoryStorage:
    """In-memory storage for testing state machine logic without a database."""

    def __init__(self):
        self.runs: Dict[UUID, DiscoveryRun] = {}
        self.stage_executions: Dict[int, StageExecution] = {}
        self.next_stage_id = 1

    def create_run(self, run: DiscoveryRun) -> DiscoveryRun:
        run_id = uuid4()
        now = datetime.now(timezone.utc)
        created = DiscoveryRun(
            id=run_id,
            status=run.status,
            current_stage=run.current_stage,
            config=run.config,
            metadata=run.metadata,
            started_at=now,
            errors=run.errors,
            warnings=run.warnings,
        )
        self.runs[run_id] = created
        return created

    def get_run(self, run_id: UUID) -> Optional[DiscoveryRun]:
        return self.runs.get(run_id)

    _UNSET = object()

    def update_run_status(
        self,
        run_id: UUID,
        status: RunStatus,
        current_stage=_UNSET,
        completed_at: Optional[datetime] = None,
    ) -> Optional[DiscoveryRun]:
        run = self.runs.get(run_id)
        if not run:
            return None
        run.status = status
        if current_stage is not self._UNSET:
            run.current_stage = current_stage
        if completed_at is not None:
            run.completed_at = completed_at
        return run

    def update_run_metadata(self, run_id: UUID, metadata: RunMetadata) -> Optional[DiscoveryRun]:
        run = self.runs.get(run_id)
        if not run:
            return None
        run.metadata = metadata
        return run

    def append_run_error(self, run_id: UUID, error: Dict[str, Any]) -> None:
        run = self.runs.get(run_id)
        if run:
            run.errors.append(error)

    def list_runs(self, status=None, limit=50):
        runs = list(self.runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        return runs[:limit]

    def create_stage_execution(self, stage_exec: StageExecution) -> StageExecution:
        stage_id = self.next_stage_id
        self.next_stage_id += 1
        created = StageExecution(
            id=stage_id,
            run_id=stage_exec.run_id,
            stage=stage_exec.stage,
            status=stage_exec.status,
            attempt_number=stage_exec.attempt_number,
            participating_agents=stage_exec.participating_agents,
            artifacts=stage_exec.artifacts,
            artifact_schema_version=stage_exec.artifact_schema_version,
            conversation_id=stage_exec.conversation_id,
            sent_back_from=stage_exec.sent_back_from,
            send_back_reason=stage_exec.send_back_reason,
            started_at=stage_exec.started_at,
        )
        self.stage_executions[stage_id] = created
        return created

    def get_stage_execution(self, execution_id: int) -> Optional[StageExecution]:
        return self.stage_executions.get(execution_id)

    def get_stage_executions_for_run(
        self, run_id: UUID, stage: Optional[StageType] = None
    ) -> List[StageExecution]:
        execs = [se for se in self.stage_executions.values() if se.run_id == run_id]
        if stage:
            execs = [se for se in execs if se.stage == stage]
        execs.sort(key=lambda se: (se.started_at or datetime.min.replace(tzinfo=timezone.utc), se.id))
        return execs

    def get_active_stage(self, run_id: UUID) -> Optional[StageExecution]:
        for se in self.stage_executions.values():
            if se.run_id == run_id and se.status in (
                StageStatus.IN_PROGRESS,
                StageStatus.CHECKPOINT_REACHED,
            ):
                return se
        return None

    def update_stage_status(
        self,
        execution_id: int,
        status: StageStatus,
        artifacts: Optional[Dict[str, Any]] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[StageExecution]:
        se = self.stage_executions.get(execution_id)
        if not se:
            return None
        se.status = status
        if artifacts is not None:
            se.artifacts = artifacts
        if completed_at is not None:
            se.completed_at = completed_at
        return se

    def save_stage_artifacts(
        self,
        run_id: UUID,
        stage_execution_id: int,
        artifacts: Dict[str, Any],
    ) -> None:
        se = self.stage_executions.get(stage_execution_id)
        if se and se.run_id == run_id:
            se.artifacts = artifacts

    def get_latest_attempt_number(self, run_id: UUID, stage: StageType) -> int:
        attempts = [
            se.attempt_number
            for se in self.stage_executions.values()
            if se.run_id == run_id and se.stage == stage
        ]
        return max(attempts) if attempts else 0


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def sm(storage):
    return DiscoveryStateMachine(storage=storage)


@pytest.fixture
def running_run(sm):
    """Create a run and start it (pending → running, exploration stage active)."""
    run = sm.create_run()
    return sm.start_run(run.id)


# ============================================================================
# Run creation and start
# ============================================================================


class TestRunCreation:
    def test_create_run_defaults(self, sm):
        run = sm.create_run()
        assert run.status == RunStatus.PENDING
        assert run.current_stage is None
        assert run.id is not None

    def test_create_run_with_config(self, sm):
        config = RunConfig(target_domain="billing", time_window_days=7)
        run = sm.create_run(config=config)
        assert run.config.target_domain == "billing"
        assert run.config.time_window_days == 7

    def test_create_run_with_metadata(self, sm):
        metadata = RunMetadata(
            agent_versions={"customer_voice": "v1.0"},
            input_snapshot_ref="intercom 2026-01-25 to 2026-02-07",
        )
        run = sm.create_run(metadata=metadata)
        assert run.metadata.agent_versions["customer_voice"] == "v1.0"

    def test_start_run(self, sm):
        run = sm.create_run()
        started = sm.start_run(run.id)
        assert started.status == RunStatus.RUNNING
        assert started.current_stage == StageType.EXPLORATION

    def test_start_run_creates_exploration_stage(self, sm, storage):
        run = sm.create_run()
        sm.start_run(run.id)
        stages = storage.get_stage_executions_for_run(run.id)
        assert len(stages) == 1
        assert stages[0].stage == StageType.EXPLORATION
        assert stages[0].status == StageStatus.IN_PROGRESS
        assert stages[0].attempt_number == 1

    def test_start_already_running_rejected(self, sm):
        run = sm.create_run()
        sm.start_run(run.id)
        with pytest.raises(InvalidTransitionError):
            sm.start_run(run.id)

    def test_start_nonexistent_run_rejected(self, sm):
        with pytest.raises(ValueError, match="not found"):
            sm.start_run(uuid4())


# ============================================================================
# Happy path: forward through all stages
# ============================================================================


class TestHappyPath:
    def test_advance_through_all_stages(self, sm, storage, running_run):
        run_id = running_run.id
        artifacts = {"test": "data"}

        # Advance through stages 1-5 (exploration is already active)
        for i, expected_next in enumerate(STAGE_ORDER[1:]):
            new_stage = sm.advance_stage(run_id, artifacts=artifacts)
            assert new_stage.stage == expected_next
            assert new_stage.status == StageStatus.IN_PROGRESS

            run = storage.get_run(run_id)
            assert run.current_stage == expected_next

        # Now at human_review — complete the run
        completed = sm.complete_run(run_id, artifacts=artifacts)
        assert completed.status == RunStatus.COMPLETED
        assert completed.completed_at is not None

    def test_stage_progression_order(self, sm, storage, running_run):
        run_id = running_run.id

        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})

        sm.complete_run(run_id, artifacts={"data": True})

        progression = sm.get_stage_progression(run_id)
        stage_names = [se.stage for se in progression]
        assert stage_names == STAGE_ORDER

    def test_advance_stores_artifacts(self, sm, storage, running_run):
        run_id = running_run.id
        artifacts = {"problem_statement": "test", "evidence": []}
        sm.advance_stage(run_id, artifacts=artifacts)

        stages = storage.get_stage_executions_for_run(run_id)
        completed_stage = [s for s in stages if s.status == StageStatus.COMPLETED][0]
        assert completed_stage.artifacts == artifacts

    def test_completed_stages_have_completed_at(self, sm, storage, running_run):
        run_id = running_run.id
        sm.advance_stage(run_id, artifacts={"data": True})

        stages = storage.get_stage_executions_for_run(run_id)
        completed = [s for s in stages if s.status == StageStatus.COMPLETED]
        assert len(completed) == 1
        assert completed[0].completed_at is not None

    def test_advance_without_artifacts_rejected(self, sm, running_run):
        """Checkpoint output is required for forward transitions (#212)."""
        with pytest.raises(InvalidTransitionError, match="artifacts"):
            sm.advance_stage(running_run.id, artifacts=None)

    def test_advance_with_empty_artifacts_rejected(self, sm, running_run):
        with pytest.raises(InvalidTransitionError, match="artifacts"):
            sm.advance_stage(running_run.id, artifacts={})


# ============================================================================
# Failure handling
# ============================================================================


class TestFailure:
    def test_fail_running_run(self, sm, running_run):
        error = {"stage": "exploration", "message": "Agent crashed", "details": {}}
        failed = sm.fail_run(running_run.id, error)
        assert failed.status == RunStatus.FAILED
        assert failed.completed_at is not None

    def test_fail_pending_run(self, sm):
        run = sm.create_run()
        error = {"stage": "startup", "message": "Config invalid"}
        failed = sm.fail_run(run.id, error)
        assert failed.status == RunStatus.FAILED

    def test_fail_records_error(self, sm, running_run):
        error = {"stage": "exploration", "message": "timeout"}
        sm.fail_run(running_run.id, error)
        run = sm.storage.get_run(running_run.id)
        assert len(run.errors) == 1
        assert run.errors[0]["message"] == "timeout"

    def test_fail_also_fails_active_stage(self, sm, storage, running_run):
        sm.fail_run(running_run.id, {"message": "boom"})
        stages = storage.get_stage_executions_for_run(running_run.id)
        assert stages[0].status == StageStatus.FAILED

    def test_fail_already_failed_rejected(self, sm, running_run):
        sm.fail_run(running_run.id, {"message": "first"})
        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.fail_run(running_run.id, {"message": "second"})

    def test_fail_at_each_stage(self, sm, storage):
        """Verify failure works at every stage in the pipeline."""
        for i, stage in enumerate(STAGE_ORDER):
            run = sm.create_run()
            sm.start_run(run.id)

            # Advance to target stage
            for _ in range(i):
                sm.advance_stage(run.id, artifacts={"data": True})

            # Fail at this stage
            failed = sm.fail_run(run.id, {"stage": stage.value, "message": "test failure"})
            assert failed.status == RunStatus.FAILED

            active = storage.get_active_stage(run.id)
            assert active is None  # no active stage after failure


# ============================================================================
# Stop handling
# ============================================================================


class TestStop:
    def test_stop_running_run(self, sm, running_run):
        stopped = sm.stop_run(running_run.id)
        assert stopped.status == RunStatus.STOPPED
        assert stopped.completed_at is not None

    def test_stop_pending_run(self, sm):
        run = sm.create_run()
        stopped = sm.stop_run(run.id)
        assert stopped.status == RunStatus.STOPPED

    def test_stop_also_fails_active_stage(self, sm, storage, running_run):
        sm.stop_run(running_run.id)
        stages = storage.get_stage_executions_for_run(running_run.id)
        assert stages[0].status == StageStatus.FAILED

    def test_stop_already_stopped_rejected(self, sm, running_run):
        sm.stop_run(running_run.id)
        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.stop_run(running_run.id)


# ============================================================================
# Backward transitions (send-back)
# ============================================================================


class TestSendBack:
    def _advance_to_stage(self, sm, run_id, target_stage):
        """Helper to advance a running run to a specific stage."""
        current_idx = 0
        target_idx = STAGE_ORDER.index(target_stage)
        for _ in range(target_idx):
            sm.advance_stage(run_id, artifacts={"data": True})

    def test_feasibility_risk_to_solution_validation(self, sm, storage, running_run):
        run_id = running_run.id
        self._advance_to_stage(sm, run_id, StageType.FEASIBILITY_RISK)

        new_stage = sm.send_back(
            run_id,
            StageType.SOLUTION_VALIDATION,
            reason="Technical approach is infeasible — payment module has no tests",
        )

        assert new_stage.stage == StageType.SOLUTION_VALIDATION
        assert new_stage.status == StageStatus.IN_PROGRESS
        assert new_stage.sent_back_from == StageType.FEASIBILITY_RISK
        assert new_stage.send_back_reason == "Technical approach is infeasible — payment module has no tests"
        assert new_stage.attempt_number == 2

    def test_human_review_to_any_earlier_stage(self, sm, storage, running_run):
        run_id = running_run.id
        self._advance_to_stage(sm, run_id, StageType.HUMAN_REVIEW)

        # Can send back to any stage
        for target in STAGE_ORDER:
            # Create fresh run for each test
            run = sm.create_run()
            started = sm.start_run(run.id)
            self._advance_to_stage(sm, run.id, StageType.HUMAN_REVIEW)

            new_stage = sm.send_back(
                run.id,
                target,
                reason=f"Send back to {target.value} for revision",
            )
            assert new_stage.stage == target
            assert new_stage.sent_back_from == StageType.HUMAN_REVIEW

    def test_send_back_marks_current_stage_as_sent_back(self, sm, storage, running_run):
        run_id = running_run.id
        self._advance_to_stage(sm, run_id, StageType.FEASIBILITY_RISK)

        sm.send_back(run_id, StageType.SOLUTION_VALIDATION, reason="infeasible")

        stages = storage.get_stage_executions_for_run(run_id)
        feasibility_stages = [s for s in stages if s.stage == StageType.FEASIBILITY_RISK]
        assert feasibility_stages[0].status == StageStatus.SENT_BACK

    def test_send_back_increments_attempt_number(self, sm, storage, running_run):
        run_id = running_run.id
        self._advance_to_stage(sm, run_id, StageType.FEASIBILITY_RISK)

        new_stage = sm.send_back(run_id, StageType.SOLUTION_VALIDATION, reason="try again")

        assert new_stage.attempt_number == 2

        # Advance back to feasibility and send back again
        sm.advance_stage(run_id, artifacts={"revised": True})
        new_stage2 = sm.send_back(run_id, StageType.SOLUTION_VALIDATION, reason="still wrong")
        assert new_stage2.attempt_number == 3

    def test_invalid_send_back_from_exploration(self, sm, running_run):
        """Exploration can't send back — it's the first stage."""
        with pytest.raises(InvalidTransitionError, match="Cannot send back"):
            sm.send_back(
                running_run.id,
                StageType.EXPLORATION,
                reason="no reason",
            )

    def test_invalid_send_back_from_opportunity_framing(self, sm, running_run):
        sm.advance_stage(running_run.id, artifacts={"data": True})
        with pytest.raises(InvalidTransitionError, match="Cannot send back"):
            sm.send_back(
                running_run.id,
                StageType.EXPLORATION,
                reason="not allowed",
            )

    def test_send_back_not_running_rejected(self, sm):
        run = sm.create_run()
        with pytest.raises(InvalidTransitionError, match="not running"):
            sm.send_back(run.id, StageType.EXPLORATION, reason="nope")


# ============================================================================
# Invalid transitions
# ============================================================================


class TestInvalidTransitions:
    def test_advance_past_last_stage(self, sm, running_run):
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})

        # Now at human_review — can't advance, must complete
        with pytest.raises(InvalidTransitionError, match="last stage"):
            sm.advance_stage(run_id, artifacts={"data": True})

    def test_advance_not_running(self, sm):
        run = sm.create_run()
        with pytest.raises(InvalidTransitionError, match="not running"):
            sm.advance_stage(run.id, artifacts={"data": True})

    def test_complete_not_at_human_review(self, sm, running_run):
        # At exploration, can't complete
        with pytest.raises(InvalidTransitionError, match="must be at human_review"):
            sm.complete_run(running_run.id, artifacts={"data": True})

    def test_complete_not_running(self, sm):
        run = sm.create_run()
        with pytest.raises(InvalidTransitionError, match="not running"):
            sm.complete_run(run.id, artifacts={"data": True})

    def test_complete_without_artifacts_rejected(self, sm, running_run):
        """human_review checkpoint output is required."""
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})
        with pytest.raises(InvalidTransitionError, match="artifacts"):
            sm.complete_run(run_id, artifacts={})

    def test_complete_with_none_artifacts_rejected(self, sm, running_run):
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})
        with pytest.raises(InvalidTransitionError, match="artifacts"):
            sm.complete_run(run_id, artifacts=None)


# ============================================================================
# Terminal states
# ============================================================================


class TestTerminalStates:
    def test_failed_blocks_all_transitions(self, sm, running_run):
        sm.fail_run(running_run.id, {"message": "fatal"})

        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.fail_run(running_run.id, {"message": "again"})

        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.stop_run(running_run.id)

    def test_stopped_blocks_all_transitions(self, sm, running_run):
        sm.stop_run(running_run.id)

        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.stop_run(running_run.id)

        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.fail_run(running_run.id, {"message": "too late"})

    def test_completed_blocks_all_transitions(self, sm, storage, running_run):
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})
        sm.complete_run(run_id, artifacts={"final": True})

        with pytest.raises(InvalidTransitionError, match="terminal"):
            sm.fail_run(run_id, {"message": "too late"})

    def test_all_terminal_statuses_covered(self):
        """Verify our terminal set matches expectations."""
        assert TERMINAL_RUN_STATUSES == {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.STOPPED,
        }


# ============================================================================
# Stage progression (derived)
# ============================================================================


class TestStageProgression:
    def test_progression_matches_execution_order(self, sm, running_run):
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})

        progression = sm.get_stage_progression(run_id)
        stages = [se.stage for se in progression]
        assert stages == STAGE_ORDER

    def test_progression_includes_send_backs(self, sm, storage, running_run):
        run_id = running_run.id

        # Advance to feasibility_risk
        for _ in range(3):
            sm.advance_stage(run_id, artifacts={"data": True})

        # Send back to solution_validation
        sm.send_back(run_id, StageType.SOLUTION_VALIDATION, reason="infeasible")

        progression = sm.get_stage_progression(run_id)
        # Should have: exploration, opp_framing, sol_val, feas_risk, sol_val(attempt 2)
        assert len(progression) == 5
        assert progression[3].status == StageStatus.SENT_BACK
        assert progression[4].stage == StageType.SOLUTION_VALIDATION
        assert progression[4].attempt_number == 2

    def test_empty_progression_for_pending_run(self, sm):
        run = sm.create_run()
        progression = sm.get_stage_progression(run.id)
        assert progression == []


# ============================================================================
# Run metadata
# ============================================================================


class TestRunMetadata:
    def test_metadata_captured_on_creation(self, sm, storage):
        metadata = RunMetadata(
            agent_versions={
                "customer_voice": "abc123",
                "analytics": "def456",
            },
            toolset_versions={
                "customer_voice": "tool_v1",
            },
            input_snapshot_ref="intercom conversations 2026-01-25 to 2026-02-07",
        )
        run = sm.create_run(metadata=metadata)

        retrieved = storage.get_run(run.id)
        assert retrieved.metadata.agent_versions["customer_voice"] == "abc123"
        assert retrieved.metadata.input_snapshot_ref == "intercom conversations 2026-01-25 to 2026-02-07"

    def test_metadata_queryable(self, sm, storage):
        """Run metadata should be retrievable after creation."""
        metadata = RunMetadata(
            agent_versions={"explorer_1": "v1"},
        )
        run = sm.create_run(metadata=metadata)

        runs = storage.list_runs()
        assert len(runs) == 1
        assert runs[0].metadata.agent_versions["explorer_1"] == "v1"


# ============================================================================
# Invariant: one active stage per run
# ============================================================================


class TestInvariants:
    def test_only_one_active_stage(self, sm, storage, running_run):
        """At any point, a run should have at most one active stage."""
        run_id = running_run.id

        # Advance through a few stages
        sm.advance_stage(run_id, artifacts={"data": True})
        sm.advance_stage(run_id, artifacts={"data": True})

        active = storage.get_active_stage(run_id)
        assert active is not None

        # Count active stages
        all_stages = storage.get_stage_executions_for_run(run_id)
        active_stages = [
            s for s in all_stages
            if s.status in (StageStatus.IN_PROGRESS, StageStatus.CHECKPOINT_REACHED)
        ]
        assert len(active_stages) == 1

    def test_no_active_stage_after_completion(self, sm, storage, running_run):
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})
        sm.complete_run(run_id, artifacts={"final": True})

        active = storage.get_active_stage(run_id)
        assert active is None

    def test_no_active_stage_after_failure(self, sm, storage, running_run):
        sm.fail_run(running_run.id, {"message": "boom"})
        active = storage.get_active_stage(running_run.id)
        assert active is None

    def test_current_stage_preserved_after_fail(self, sm, storage, running_run):
        """fail_run should NOT null out current_stage — it records where the failure happened."""
        run_id = running_run.id
        # Advance to opportunity_framing so current_stage is non-trivial
        sm.advance_stage(run_id, artifacts={"data": True})
        run = storage.get_run(run_id)
        assert run.current_stage == StageType.OPPORTUNITY_FRAMING

        sm.fail_run(run_id, {"message": "agent crashed"})
        run = storage.get_run(run_id)
        assert run.status == RunStatus.FAILED
        assert run.current_stage == StageType.OPPORTUNITY_FRAMING

    def test_current_stage_preserved_after_stop(self, sm, storage, running_run):
        """stop_run should NOT null out current_stage."""
        run_id = running_run.id
        sm.advance_stage(run_id, artifacts={"data": True})
        sm.advance_stage(run_id, artifacts={"data": True})
        run = storage.get_run(run_id)
        assert run.current_stage == StageType.SOLUTION_VALIDATION

        sm.stop_run(run_id)
        run = storage.get_run(run_id)
        assert run.status == RunStatus.STOPPED
        assert run.current_stage == StageType.SOLUTION_VALIDATION

    def test_current_stage_preserved_after_complete(self, sm, storage, running_run):
        """complete_run should preserve current_stage as human_review."""
        run_id = running_run.id
        for _ in STAGE_ORDER[1:]:
            sm.advance_stage(run_id, artifacts={"data": True})
        sm.complete_run(run_id, artifacts={"final": True})

        run = storage.get_run(run_id)
        assert run.status == RunStatus.COMPLETED
        assert run.current_stage == StageType.HUMAN_REVIEW
