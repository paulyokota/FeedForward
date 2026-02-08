"""Conversation service for the Discovery Engine.

Manages stage conversations, structured event handling, and checkpoint
validation. Uses a ConversationTransport for the actual read/write
operations (Agenterminal in production, in-memory for tests).

Per #214: "The conversation transcript serves as the audit trail —
no separate logging needed."
"""

import logging
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from pydantic import BaseModel, ValidationError

from src.discovery.db.storage import DiscoveryStorage
from src.discovery.models.artifacts import (
    OpportunityBrief,
    SolutionBrief,
    TechnicalSpec,
)
from src.discovery.models.conversation import (
    CheckpointSubmission,
    ConversationEvent,
    ConversationTurn,
    EventType,
    build_event_text,
    parse_checkpoint_submission,
    parse_turn,
)
from src.discovery.models.enums import StageType
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import ConversationTransport

logger = logging.getLogger(__name__)

# Stage → artifact model mapping.
# Stages without a specific model use None (accept any non-empty dict).
STAGE_ARTIFACT_MODELS: Dict[StageType, Optional[Type[BaseModel]]] = {
    StageType.EXPLORATION: None,  # Phase 1: no formal schema yet
    StageType.OPPORTUNITY_FRAMING: OpportunityBrief,
    StageType.SOLUTION_VALIDATION: SolutionBrief,
    StageType.FEASIBILITY_RISK: TechnicalSpec,
    StageType.PRIORITIZATION: None,  # Phase 1: no formal schema yet
    StageType.HUMAN_REVIEW: None,  # Human decisions, no fixed schema
}


class ArtifactValidationError(Exception):
    """Raised when checkpoint artifacts fail validation against the stage contract."""

    def __init__(self, stage: StageType, errors: List[str]):
        self.stage = stage
        self.errors = errors
        super().__init__(
            f"Artifact validation failed for {stage.value}: {'; '.join(errors)}"
        )


class ConversationService:
    """Manages stage conversations, event handling, and checkpoint validation.

    Coordinates between the conversation transport (Agenterminal), the storage
    layer (Postgres), and the state machine.
    """

    def __init__(
        self,
        transport: ConversationTransport,
        storage: DiscoveryStorage,
        state_machine: DiscoveryStateMachine,
    ):
        self.transport = transport
        self.storage = storage
        self.state_machine = state_machine

    def create_stage_conversation(
        self,
        run_id: UUID,
        stage_execution_id: int,
    ) -> str:
        """Create a conversation for a stage execution and link it.

        Validates that stage_execution_id belongs to run_id before linking.
        Retries ID generation on collision (up to 3 attempts).

        Returns the conversation_id.
        """
        # Verify stage_execution_id belongs to run_id
        all_stages = self.storage.get_stage_executions_for_run(run_id)
        if not any(se.id == stage_execution_id for se in all_stages):
            raise ValueError(
                f"Stage execution {stage_execution_id} does not belong to run {run_id}"
            )

        # Generate ID with collision retry
        max_attempts = 3
        for attempt in range(max_attempts):
            conversation_id = self.transport.generate_conversation_id()
            try:
                self.transport.create_conversation(conversation_id)
                break
            except Exception:
                if attempt == max_attempts - 1:
                    raise
                logger.warning(
                    "Conversation ID collision on %s, retrying (%d/%d)",
                    conversation_id, attempt + 1, max_attempts,
                )

        # Link conversation to stage execution in Postgres
        self.storage.update_stage_conversation_id(
            stage_execution_id, conversation_id
        )

        logger.info(
            "Created conversation %s for stage execution %d (run %s)",
            conversation_id,
            stage_execution_id,
            run_id,
        )
        return conversation_id

    def post_message(
        self,
        conversation_id: str,
        agent_name: str,
        text: str,
    ) -> str:
        """Post a plain text message to a stage conversation.

        agent_name is accepted for API consistency but not embedded in the turn.
        Plain text messages use the transport's role field for attribution.
        Structured events (post_event) include agent in the JSON payload.

        Returns the turn ID.
        """
        return self.transport.post_turn(
            conversation_id,
            role="agent",
            text=text,
        )

    def post_event(
        self,
        conversation_id: str,
        agent_name: str,
        event_type: EventType,
        payload: Dict[str, Any],
    ) -> str:
        """Post a structured event to a stage conversation.

        The payload is wrapped in a JSON envelope with `_event` and `agent`.
        Returns the turn ID.
        """
        full_payload = {"agent": agent_name, **payload}
        text = build_event_text(event_type, full_payload)
        return self.transport.post_turn(
            conversation_id,
            role="agent",
            text=text,
        )

    def read_history(
        self,
        conversation_id: str,
        since_id: Optional[str] = None,
    ) -> List[ConversationEvent]:
        """Read conversation history, parsing structured events from turns.

        Returns a list of ConversationEvents (parsed from raw turns).
        """
        raw_turns = self.transport.read_turns(conversation_id, since_id=since_id)
        events = []
        for raw in raw_turns:
            turn = ConversationTurn(
                id=raw.get("id", ""),
                role=raw.get("role", "agent"),
                text=raw.get("text", ""),
                mode=raw.get("mode"),
                createdAt=raw.get("createdAt"),
            )
            events.append(parse_turn(turn))
        return events

    def submit_checkpoint(
        self,
        conversation_id: str,
        run_id: UUID,
        agent_name: str,
        artifacts: Dict[str, Any],
    ) -> "StageExecution":
        """Submit checkpoint artifacts, validate, and advance the stage.

        Order of operations:
        1. Determine current stage and validate artifacts against Pydantic model
        2. Post checkpoint:submit event to conversation
        3. Advance the state machine (completes current stage, creates next)
        4. Create conversation for the new stage

        Returns the new StageExecution.

        Raises:
            ArtifactValidationError: if artifacts fail Pydantic validation
            InvalidTransitionError: if state machine rejects the transition
        """
        from src.discovery.models.run import StageExecution

        # Get current stage to determine which model to validate against
        active_stage = self.storage.get_active_stage(run_id)
        if not active_stage:
            raise ValueError(f"No active stage for run {run_id}")

        # Verify conversation belongs to the active stage
        self._verify_conversation_ownership(conversation_id, active_stage)

        # Validate artifacts against stage-specific model
        self._validate_artifacts(active_stage.stage, artifacts)

        # Post checkpoint event to conversation
        self.post_event(
            conversation_id,
            agent_name,
            EventType.CHECKPOINT_SUBMIT,
            {"stage": active_stage.stage.value, "artifacts": artifacts},
        )

        # Advance the state machine
        new_stage = self.state_machine.advance_stage(run_id, artifacts=artifacts)

        # Create conversation for the new stage
        new_conversation_id = self.create_stage_conversation(
            run_id, new_stage.id
        )

        # Post stage transition event to the OLD conversation (audit trail)
        self.post_event(
            conversation_id,
            agent_name,
            EventType.STAGE_TRANSITION,
            {
                "from_stage": active_stage.stage.value,
                "to_stage": new_stage.stage.value,
                "new_conversation_id": new_conversation_id,
            },
        )

        logger.info(
            "Checkpoint submitted for run %s: %s → %s (new conversation: %s)",
            run_id,
            active_stage.stage.value,
            new_stage.stage.value,
            new_conversation_id,
        )

        return new_stage

    def complete_with_checkpoint(
        self,
        conversation_id: str,
        run_id: UUID,
        agent_name: str,
        artifacts: Dict[str, Any],
    ) -> "DiscoveryRun":
        """Submit final checkpoint and complete the run (human_review stage).

        Similar to submit_checkpoint but calls complete_run instead of advance_stage.

        Returns the completed DiscoveryRun.
        """
        from src.discovery.models.run import DiscoveryRun

        active_stage = self.storage.get_active_stage(run_id)
        if not active_stage:
            raise ValueError(f"No active stage for run {run_id}")

        # Verify conversation belongs to the active stage
        self._verify_conversation_ownership(conversation_id, active_stage)

        # Validate artifacts
        self._validate_artifacts(active_stage.stage, artifacts)

        # Post checkpoint event
        self.post_event(
            conversation_id,
            agent_name,
            EventType.CHECKPOINT_SUBMIT,
            {"stage": active_stage.stage.value, "artifacts": artifacts},
        )

        # Complete the run
        completed_run = self.state_machine.complete_run(run_id, artifacts=artifacts)

        # Post completion event
        self.post_event(
            conversation_id,
            agent_name,
            EventType.STAGE_TRANSITION,
            {"from_stage": active_stage.stage.value, "to_stage": "completed"},
        )

        return completed_run

    def get_prior_checkpoints(self, run_id: UUID) -> List[Dict[str, Any]]:
        """Get checkpoint artifacts from all completed stages.

        Agents can reference prior stage output when working on their stage.
        Reads from Postgres (the validated artifacts), not from conversations.
        """
        stages = self.storage.get_stage_executions_for_run(run_id)
        checkpoints = []
        for stage in stages:
            if stage.artifacts is not None:
                checkpoints.append(
                    {
                        "stage": stage.stage.value,
                        "attempt": stage.attempt_number,
                        "artifacts": stage.artifacts,
                    }
                )
        return checkpoints

    def get_conversation_for_stage(
        self,
        run_id: UUID,
        stage: StageType,
    ) -> Optional[str]:
        """Get the conversation_id for a specific stage of a run."""
        return self.storage.get_stage_conversation_id(run_id, stage)

    # ========================================================================
    # Internal helpers
    # ========================================================================

    def _verify_conversation_ownership(
        self,
        conversation_id: str,
        active_stage: "StageExecution",
    ) -> None:
        """Verify that conversation_id matches the active stage's conversation.

        Prevents a stale or wrong conversation from advancing the run.
        """
        if active_stage.conversation_id and active_stage.conversation_id != conversation_id:
            raise ValueError(
                f"Conversation {conversation_id} does not match active stage's "
                f"conversation {active_stage.conversation_id} "
                f"(stage: {active_stage.stage.value})"
            )

    def _validate_artifacts(
        self,
        stage: StageType,
        artifacts: Dict[str, Any],
    ) -> None:
        """Validate artifacts against the stage-specific Pydantic model.

        Stages without a specific model (exploration, prioritization,
        human_review) accept any non-empty dict.

        Raises ArtifactValidationError on validation failure.
        """
        model_class = STAGE_ARTIFACT_MODELS.get(stage)

        if model_class is None:
            # No specific model — just check non-empty
            if not artifacts:
                raise ArtifactValidationError(
                    stage, ["Artifacts cannot be empty"]
                )
            return

        try:
            model_class(**artifacts)
        except ValidationError as e:
            errors = [
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
                for err in e.errors()
            ]
            raise ArtifactValidationError(stage, errors) from e
