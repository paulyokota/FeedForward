"""Discovery Engine State Machine.

Manages run lifecycle and stage transitions with validation.
All state transitions are atomic — run status update, stage creation,
and stage completion happen in a single DB transaction.

Transition rules from #212:
- Forward by default: exploration → opportunity_framing → ... → human_review → completed
- Backward on explicit challenge:
  - feasibility_risk → solution_validation (technical infeasibility)
  - human_review → any earlier stage (send-back with guidance)
- Terminal states: failed, stopped (no transitions out)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.discovery.db.storage import DiscoveryStorage
from src.discovery.models.enums import (
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

logger = logging.getLogger(__name__)

# Terminal run statuses — no transitions allowed out of these
TERMINAL_RUN_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED}

# Valid run status transitions
VALID_RUN_TRANSITIONS = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.STOPPED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED},
}

# Valid stage status transitions
VALID_STAGE_TRANSITIONS = {
    StageStatus.PENDING: {StageStatus.IN_PROGRESS, StageStatus.FAILED},
    StageStatus.IN_PROGRESS: {
        StageStatus.CHECKPOINT_REACHED,
        StageStatus.COMPLETED,
        StageStatus.FAILED,
        StageStatus.SENT_BACK,
    },
    StageStatus.CHECKPOINT_REACHED: {
        StageStatus.COMPLETED,
        StageStatus.FAILED,
        StageStatus.SENT_BACK,
    },
}

# Allowed backward transitions (stage_from → set of stages it can go back to)
ALLOWED_BACKWARD_TRANSITIONS = {
    StageType.FEASIBILITY_RISK: {StageType.SOLUTION_VALIDATION},
    StageType.HUMAN_REVIEW: set(STAGE_ORDER),  # can send back to any stage
}


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    pass


class DiscoveryStateMachine:
    """Manages discovery run lifecycle and stage transitions.

    All public methods that modify state are designed to be called within
    a database transaction. The caller is responsible for committing.
    """

    def __init__(self, storage: DiscoveryStorage):
        self.storage = storage

    def create_run(
        self,
        config: Optional[RunConfig] = None,
        metadata: Optional[RunMetadata] = None,
    ) -> DiscoveryRun:
        """Create a new discovery run in pending status."""
        run = DiscoveryRun(
            config=config or RunConfig(),
            metadata=metadata or RunMetadata(),
        )
        return self.storage.create_run(run)

    def start_run(self, run_id: UUID) -> DiscoveryRun:
        """Transition a run from pending to running and start the first stage.

        This is atomic: updates run status AND creates the first stage execution.
        """
        run = self._get_run_or_raise(run_id)
        self._validate_run_transition(run, RunStatus.RUNNING)

        now = datetime.now(timezone.utc)
        first_stage = STAGE_ORDER[0]

        # Update run to running
        updated_run = self.storage.update_run_status(
            run_id, RunStatus.RUNNING, current_stage=first_stage
        )

        # Create first stage execution
        self.storage.create_stage_execution(
            StageExecution(
                run_id=run_id,
                stage=first_stage,
                status=StageStatus.IN_PROGRESS,
                attempt_number=1,
                started_at=now,
            )
        )

        return updated_run

    def advance_stage(
        self,
        run_id: UUID,
        artifacts: Dict[str, Any],
    ) -> StageExecution:
        """Complete the current stage and advance to the next one.

        Requires artifacts for the current stage (output validation per #212).
        Creates a new stage execution for the next stage.

        Note: Caller is responsible for validating artifacts against the
        stage-specific contract models (OpportunityBrief, SolutionBrief, etc.).
        This method only checks that artifacts are non-empty.

        Returns the new stage execution.

        Raises:
            InvalidTransitionError: if run is not running, no active stage,
                at last stage, or artifacts not provided.
        """
        if not artifacts:
            raise InvalidTransitionError(
                "Cannot advance stage without artifacts — checkpoint output is required"
            )

        run = self._get_run_or_raise(run_id)

        if run.status != RunStatus.RUNNING:
            raise InvalidTransitionError(
                f"Cannot advance stage: run {run_id} is {run.status.value}, not running"
            )

        active_stage = self.storage.get_active_stage(run_id)
        if not active_stage:
            raise InvalidTransitionError(
                f"Cannot advance stage: no active stage for run {run_id}"
            )

        current_idx = STAGE_ORDER.index(active_stage.stage)
        if current_idx >= len(STAGE_ORDER) - 1:
            raise InvalidTransitionError(
                f"Cannot advance past {active_stage.stage.value} — it's the last stage. "
                "Use complete_run() instead."
            )

        next_stage = STAGE_ORDER[current_idx + 1]
        now = datetime.now(timezone.utc)

        # Complete current stage
        self.storage.update_stage_status(
            active_stage.id,
            StageStatus.COMPLETED,
            artifacts=artifacts,
            completed_at=now,
        )

        # Update run's current_stage
        self.storage.update_run_status(run_id, RunStatus.RUNNING, current_stage=next_stage)

        # Create next stage execution
        attempt = self.storage.get_latest_attempt_number(run_id, next_stage) + 1
        new_stage = self.storage.create_stage_execution(
            StageExecution(
                run_id=run_id,
                stage=next_stage,
                status=StageStatus.IN_PROGRESS,
                attempt_number=attempt,
                started_at=now,
            )
        )

        logger.info(
            "Run %s: advanced from %s to %s (attempt %d)",
            run_id,
            active_stage.stage.value,
            next_stage.value,
            attempt,
        )

        return new_stage

    def send_back(
        self,
        run_id: UUID,
        target_stage: StageType,
        reason: str,
        artifacts: Optional[Dict[str, Any]] = None,
    ) -> StageExecution:
        """Send the run back to an earlier stage.

        Only allowed from feasibility_risk (→ solution_validation) or
        human_review (→ any earlier stage).

        Returns the new stage execution for the target stage.
        """
        run = self._get_run_or_raise(run_id)

        if run.status != RunStatus.RUNNING:
            raise InvalidTransitionError(
                f"Cannot send back: run {run_id} is {run.status.value}, not running"
            )

        active_stage = self.storage.get_active_stage(run_id)
        if not active_stage:
            raise InvalidTransitionError(
                f"Cannot send back: no active stage for run {run_id}"
            )

        # Validate backward transition
        allowed_targets = ALLOWED_BACKWARD_TRANSITIONS.get(active_stage.stage, set())
        if target_stage not in allowed_targets:
            raise InvalidTransitionError(
                f"Cannot send back from {active_stage.stage.value} to {target_stage.value}. "
                f"Allowed targets: {[s.value for s in allowed_targets] if allowed_targets else 'none'}"
            )

        now = datetime.now(timezone.utc)

        # Mark current stage as sent_back
        self.storage.update_stage_status(
            active_stage.id,
            StageStatus.SENT_BACK,
            artifacts=artifacts,
            completed_at=now,
        )

        # Update run's current_stage
        self.storage.update_run_status(run_id, RunStatus.RUNNING, current_stage=target_stage)

        # Create new stage execution for target stage
        attempt = self.storage.get_latest_attempt_number(run_id, target_stage) + 1
        new_stage = self.storage.create_stage_execution(
            StageExecution(
                run_id=run_id,
                stage=target_stage,
                status=StageStatus.IN_PROGRESS,
                attempt_number=attempt,
                sent_back_from=active_stage.stage,
                send_back_reason=reason,
                started_at=now,
            )
        )

        logger.info(
            "Run %s: sent back from %s to %s (attempt %d). Reason: %s",
            run_id,
            active_stage.stage.value,
            target_stage.value,
            attempt,
            reason,
        )

        return new_stage

    def complete_run(
        self,
        run_id: UUID,
        artifacts: Dict[str, Any],
    ) -> DiscoveryRun:
        """Complete a run after the final stage (human_review).

        Requires artifacts for the human_review stage (same as advance_stage).
        Completes the active stage and marks the run as completed.

        Note: Caller is responsible for validating artifacts against the
        stage-specific contract models. This method only checks non-empty.

        Raises:
            InvalidTransitionError: if run is not running, no active stage,
                not at human_review, or artifacts not provided.
        """
        if not artifacts:
            raise InvalidTransitionError(
                "Cannot complete run without artifacts — human_review checkpoint output is required"
            )
        run = self._get_run_or_raise(run_id)

        if run.status != RunStatus.RUNNING:
            raise InvalidTransitionError(
                f"Cannot complete: run {run_id} is {run.status.value}, not running"
            )

        active_stage = self.storage.get_active_stage(run_id)
        if not active_stage:
            raise InvalidTransitionError(
                f"Cannot complete: no active stage for run {run_id}"
            )

        if active_stage.stage != StageType.HUMAN_REVIEW:
            raise InvalidTransitionError(
                f"Cannot complete run from {active_stage.stage.value} — "
                "must be at human_review stage"
            )

        now = datetime.now(timezone.utc)

        # Complete the final stage
        self.storage.update_stage_status(
            active_stage.id,
            StageStatus.COMPLETED,
            artifacts=artifacts,
            completed_at=now,
        )

        # Complete the run (current_stage preserved as human_review)
        return self.storage.update_run_status(
            run_id, RunStatus.COMPLETED, completed_at=now
        )  # current_stage not passed → preserved via COALESCE

    def fail_run(self, run_id: UUID, error: Dict[str, Any]) -> DiscoveryRun:
        """Mark a run as failed. Terminal state — no further transitions.

        Also fails the active stage if one exists.
        """
        run = self._get_run_or_raise(run_id)

        if run.status in TERMINAL_RUN_STATUSES:
            raise InvalidTransitionError(
                f"Cannot fail: run {run_id} is already in terminal state {run.status.value}"
            )

        now = datetime.now(timezone.utc)

        # Fail active stage if exists
        active_stage = self.storage.get_active_stage(run_id)
        if active_stage:
            self.storage.update_stage_status(
                active_stage.id, StageStatus.FAILED, completed_at=now
            )

        # Record error
        self.storage.append_run_error(run_id, error)

        return self.storage.update_run_status(
            run_id, RunStatus.FAILED, completed_at=now
        )

    def stop_run(self, run_id: UUID) -> DiscoveryRun:
        """Stop a run gracefully. Terminal state — no further transitions.

        Also fails the active stage if one exists.
        """
        run = self._get_run_or_raise(run_id)

        if run.status in TERMINAL_RUN_STATUSES:
            raise InvalidTransitionError(
                f"Cannot stop: run {run_id} is already in terminal state {run.status.value}"
            )

        now = datetime.now(timezone.utc)

        # Fail active stage if exists
        active_stage = self.storage.get_active_stage(run_id)
        if active_stage:
            self.storage.update_stage_status(
                active_stage.id, StageStatus.FAILED, completed_at=now
            )

        return self.storage.update_run_status(
            run_id, RunStatus.STOPPED, completed_at=now
        )

    def get_stage_progression(self, run_id: UUID) -> List[StageExecution]:
        """Get the stage progression for a run (derived from stage_executions)."""
        return self.storage.get_stage_executions_for_run(run_id)

    # ========================================================================
    # Internal helpers
    # ========================================================================

    def _get_run_or_raise(self, run_id: UUID) -> DiscoveryRun:
        """Get a run by ID or raise ValueError."""
        run = self.storage.get_run(run_id)
        if not run:
            raise ValueError(f"Discovery run {run_id} not found")
        return run

    def _validate_run_transition(self, run: DiscoveryRun, target_status: RunStatus) -> None:
        """Validate that a run status transition is allowed."""
        if run.status in TERMINAL_RUN_STATUSES:
            raise InvalidTransitionError(
                f"Run {run.id} is in terminal state {run.status.value} — no transitions allowed"
            )

        allowed = VALID_RUN_TRANSITIONS.get(run.status, set())
        if target_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition run from {run.status.value} to {target_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
