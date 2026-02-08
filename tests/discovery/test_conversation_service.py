"""Tests for the ConversationService.

Covers: conversation creation/linking, message posting, event posting,
history reading, checkpoint submission with stage advancement, prior
checkpoints retrieval, and error handling.

Uses InMemoryTransport and InMemoryStorage to isolate from real backends.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pytest

from src.discovery.models.enums import (
    ConfidenceLevel,
    RunStatus,
    SourceType,
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
from src.discovery.models.conversation import EventType
from src.discovery.services.conversation import (
    ArtifactValidationError,
    ConversationService,
)
from src.discovery.services.state_machine import (
    DiscoveryStateMachine,
    InvalidTransitionError,
)
from src.discovery.services.transport import InMemoryTransport


# ============================================================================
# In-memory storage mock (extended from test_state_machine.py with conversation_id)
# ============================================================================


class InMemoryStorage:
    """In-memory storage for testing conversation service without a database."""

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

    def append_run_error(self, run_id: UUID, error: Dict[str, Any]) -> None:
        run = self.runs.get(run_id)
        if run:
            run.errors.append(error)

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

    def get_active_stage(self, run_id: UUID) -> Optional[StageExecution]:
        for se in self.stage_executions.values():
            if se.run_id == run_id and se.status in (
                StageStatus.IN_PROGRESS,
                StageStatus.CHECKPOINT_REACHED,
            ):
                return se
        return None

    def get_stage_executions_for_run(
        self, run_id: UUID, stage: Optional[StageType] = None
    ) -> List[StageExecution]:
        execs = [se for se in self.stage_executions.values() if se.run_id == run_id]
        if stage:
            execs = [se for se in execs if se.stage == stage]
        execs.sort(key=lambda se: (se.started_at or datetime.min.replace(tzinfo=timezone.utc), se.id))
        return execs

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

    def get_latest_attempt_number(self, run_id: UUID, stage: StageType) -> int:
        attempts = [
            se.attempt_number
            for se in self.stage_executions.values()
            if se.run_id == run_id and se.stage == stage
        ]
        return max(attempts) if attempts else 0

    def update_stage_conversation_id(
        self, execution_id: int, conversation_id: str
    ) -> Optional[StageExecution]:
        se = self.stage_executions.get(execution_id)
        if not se:
            return None
        se.conversation_id = conversation_id
        return se

    def get_stage_conversation_id(
        self, run_id: UUID, stage: StageType
    ) -> Optional[str]:
        execs = [
            se
            for se in self.stage_executions.values()
            if se.run_id == run_id and se.stage == stage and se.conversation_id
        ]
        if not execs:
            return None
        execs.sort(key=lambda se: se.attempt_number, reverse=True)
        return execs[0].conversation_id


# ============================================================================
# Fixtures
# ============================================================================


def _valid_evidence():
    return {
        "source_type": SourceType.INTERCOM.value,
        "source_id": "conv_123",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "confidence": ConfidenceLevel.HIGH.value,
    }


def _valid_opportunity_brief():
    return {
        "problem_statement": "Users can't reset passwords",
        "evidence": [_valid_evidence()],
        "counterfactual": "If fixed, support tickets drop 20%",
        "affected_area": "authentication",
        "explorer_coverage": "Intercom last 14 days",
    }


def _valid_solution_brief():
    return {
        "proposed_solution": "Add password reset via email link",
        "experiment_plan": "A/B test reset flow with 10% of users",
        "success_metrics": "Reduce password tickets from 50/week to 10/week",
        "build_experiment_decision": "experiment_first",
        "evidence": [_valid_evidence()],
    }


def _valid_technical_spec():
    return {
        "approach": "Add /reset-password endpoint with token-based flow",
        "effort_estimate": "3-5 days, medium confidence",
        "dependencies": "Email service must support transactional templates",
        "risks": ["Token expiry race condition", "Email deliverability"],
        "acceptance_criteria": "User can reset password within 2 clicks from login page",
    }


@pytest.fixture
def transport():
    return InMemoryTransport()


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def state_machine(storage):
    return DiscoveryStateMachine(storage=storage)


@pytest.fixture
def service(transport, storage, state_machine):
    return ConversationService(
        transport=transport,
        storage=storage,
        state_machine=state_machine,
    )


@pytest.fixture
def running_run(state_machine):
    run = state_machine.create_run()
    return state_machine.start_run(run.id)


# ============================================================================
# Conversation creation and linking
# ============================================================================


class TestConversationCreation:
    def test_create_stage_conversation(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        assert convo_id is not None
        assert len(convo_id) > 0

        # Verify linked in storage
        updated = storage.stage_executions[active.id]
        assert updated.conversation_id == convo_id

    def test_conversation_exists_in_transport(self, service, transport, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        assert convo_id in transport.conversations

    def test_get_conversation_for_stage(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        retrieved = service.get_conversation_for_stage(
            running_run.id, StageType.EXPLORATION
        )
        assert retrieved == convo_id

    def test_create_rejects_wrong_run_id(self, service, storage, state_machine):
        """stage_execution_id must belong to the given run_id."""
        run_a = state_machine.create_run()
        run_a = state_machine.start_run(run_a.id)
        run_b = state_machine.create_run()
        run_b = state_machine.start_run(run_b.id)

        active_a = storage.get_active_stage(run_a.id)

        # Try to link run_a's stage execution to run_b
        with pytest.raises(ValueError, match="does not belong to run"):
            service.create_stage_conversation(run_b.id, active_a.id)


# ============================================================================
# Message posting and reading
# ============================================================================


class TestMessaging:
    def test_post_and_read_message(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        turn_id = service.post_message(
            convo_id, "customer_voice", "Found 3 billing issues"
        )
        assert turn_id is not None

        history = service.read_history(convo_id)
        assert len(history) == 1
        assert history[0].text == "Found 3 billing issues"
        assert history[0].event_type.value == "message"

    def test_post_multiple_messages(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        service.post_message(convo_id, "agent_a", "First message")
        service.post_message(convo_id, "agent_b", "Second message")
        service.post_message(convo_id, "agent_a", "Third message")

        history = service.read_history(convo_id)
        assert len(history) == 3

    def test_read_with_since_id(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        id1 = service.post_message(convo_id, "a", "first")
        id2 = service.post_message(convo_id, "b", "second")
        id3 = service.post_message(convo_id, "a", "third")

        history = service.read_history(convo_id, since_id=id1)
        assert len(history) == 2
        assert history[0].text == "second"

    def test_read_empty_conversation(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        history = service.read_history(convo_id)
        assert history == []


# ============================================================================
# Structured event posting
# ============================================================================


class TestEventPosting:
    def test_post_structured_event(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        service.post_event(
            convo_id,
            "customer_voice",
            EventType.EXPLORER_REQUEST,
            {"query": "How many billing complaints?"},
        )

        history = service.read_history(convo_id)
        assert len(history) == 1
        assert history[0].event_type == EventType.EXPLORER_REQUEST
        assert history[0].agent_name == "customer_voice"
        assert history[0].payload["query"] == "How many billing complaints?"

    def test_post_event_includes_agent(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        service.post_event(
            convo_id,
            "analytics_explorer",
            EventType.EXPLORER_RESPONSE,
            {"data": {"count": 42}},
        )

        history = service.read_history(convo_id)
        assert history[0].payload["agent"] == "analytics_explorer"


# ============================================================================
# Checkpoint submission (integration with state machine)
# ============================================================================


class TestCheckpointSubmission:
    def test_submit_checkpoint_advances_stage(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        # Submit checkpoint with valid exploration artifacts (no specific model)
        new_stage = service.submit_checkpoint(
            convo_id,
            running_run.id,
            "exploration_agent",
            artifacts={"findings": "data", "coverage": "intercom 14d"},
        )

        assert new_stage.stage == StageType.OPPORTUNITY_FRAMING
        assert new_stage.status == StageStatus.IN_PROGRESS

    def test_submit_checkpoint_creates_next_conversation(
        self, service, storage, transport, running_run
    ):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        new_stage = service.submit_checkpoint(
            convo_id,
            running_run.id,
            "agent",
            artifacts={"data": True},
        )

        # New stage should have a conversation
        assert new_stage.conversation_id is not None
        assert new_stage.conversation_id != convo_id
        assert new_stage.conversation_id in transport.conversations

    def test_submit_checkpoint_posts_events(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        service.submit_checkpoint(
            convo_id,
            running_run.id,
            "agent",
            artifacts={"data": True},
        )

        # Check that checkpoint and transition events were posted
        history = service.read_history(convo_id)
        event_types = [e.event_type for e in history]
        assert EventType.CHECKPOINT_SUBMIT in event_types
        assert EventType.STAGE_TRANSITION in event_types

    def test_submit_checkpoint_validates_artifacts(self, service, storage, running_run):
        """Advance to opportunity_framing, then submit invalid artifacts."""
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        # Advance to opportunity_framing (which requires OpportunityBrief)
        service.submit_checkpoint(
            convo_id, running_run.id, "agent", artifacts={"data": True}
        )

        # Get new stage conversation
        new_active = storage.get_active_stage(running_run.id)
        new_convo = new_active.conversation_id

        # Submit invalid artifacts (missing required fields for OpportunityBrief)
        with pytest.raises(ArtifactValidationError) as exc_info:
            service.submit_checkpoint(
                new_convo,
                running_run.id,
                "agent",
                artifacts={"problem_statement": "test"},  # Missing other fields
            )
        assert exc_info.value.stage == StageType.OPPORTUNITY_FRAMING

    def test_submit_valid_opportunity_brief(self, service, storage, running_run):
        """Full path: exploration → opportunity_framing with valid OpportunityBrief."""
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        # Advance past exploration
        service.submit_checkpoint(
            convo_id, running_run.id, "agent", artifacts={"data": True}
        )

        new_active = storage.get_active_stage(running_run.id)
        new_convo = new_active.conversation_id

        # Submit valid OpportunityBrief
        new_stage = service.submit_checkpoint(
            new_convo,
            running_run.id,
            "synthesis_agent",
            artifacts=_valid_opportunity_brief(),
        )

        assert new_stage.stage == StageType.SOLUTION_VALIDATION

    def test_no_active_stage_raises(self, service, storage, running_run):
        """submit_checkpoint with no active stage should raise."""
        service.state_machine.stop_run(running_run.id)

        with pytest.raises(ValueError, match="No active stage"):
            service.submit_checkpoint(
                "some-convo", running_run.id, "agent", artifacts={"data": True}
            )

    def test_wrong_conversation_id_rejected(self, service, storage, running_run):
        """submit_checkpoint with a stale/wrong conversation_id should raise."""
        active = storage.get_active_stage(running_run.id)
        real_convo = service.create_stage_conversation(running_run.id, active.id)

        with pytest.raises(ValueError, match="does not match active stage"):
            service.submit_checkpoint(
                "wrong-convo-id",
                running_run.id,
                "agent",
                artifacts={"data": True},
            )

    def test_stale_conversation_id_rejected_after_advance(
        self, service, storage, running_run
    ):
        """After advancing, the old conversation can't submit checkpoints."""
        active = storage.get_active_stage(running_run.id)
        first_convo = service.create_stage_conversation(running_run.id, active.id)

        # Advance to opportunity_framing
        service.submit_checkpoint(
            first_convo, running_run.id, "agent", artifacts={"data": True}
        )

        # Try to submit with the old conversation (now stale)
        with pytest.raises(ValueError, match="does not match active stage"):
            service.submit_checkpoint(
                first_convo,
                running_run.id,
                "agent",
                artifacts=_valid_opportunity_brief(),
            )


# ============================================================================
# Complete with checkpoint (human_review → completed)
# ============================================================================


class TestCompleteWithCheckpoint:
    # Stage-appropriate artifacts for advancing through the pipeline
    _stage_artifacts = {
        StageType.EXPLORATION: {"findings": "data", "coverage": "intercom 14d"},
        StageType.OPPORTUNITY_FRAMING: _valid_opportunity_brief(),
        StageType.SOLUTION_VALIDATION: _valid_solution_brief(),
        StageType.FEASIBILITY_RISK: _valid_technical_spec(),
        StageType.PRIORITIZATION: {"ranking": [1, 2, 3], "rationale": "impact"},
    }

    def _advance_to_human_review(self, service, storage, run_id):
        """Helper to advance through all stages to human_review."""
        for stage in STAGE_ORDER[:-1]:
            active = storage.get_active_stage(run_id)
            convo_id = active.conversation_id
            if not convo_id:
                convo_id = service.create_stage_conversation(run_id, active.id)
            artifacts = self._stage_artifacts[active.stage]
            service.submit_checkpoint(
                convo_id, run_id, "agent", artifacts=artifacts
            )

    def test_complete_run_with_checkpoint(self, service, storage, running_run):
        self._advance_to_human_review(service, storage, running_run.id)

        active = storage.get_active_stage(running_run.id)
        assert active.stage == StageType.HUMAN_REVIEW

        convo_id = active.conversation_id or service.create_stage_conversation(
            running_run.id, active.id
        )

        completed = service.complete_with_checkpoint(
            convo_id,
            running_run.id,
            "human_reviewer",
            artifacts={"decision": "approved", "notes": "Ship it"},
        )

        assert completed.status == RunStatus.COMPLETED

    def test_complete_rejects_wrong_conversation(self, service, storage, running_run):
        """complete_with_checkpoint with wrong conversation_id should raise."""
        self._advance_to_human_review(service, storage, running_run.id)

        active = storage.get_active_stage(running_run.id)
        assert active.stage == StageType.HUMAN_REVIEW

        # Create the real conversation
        real_convo = active.conversation_id or service.create_stage_conversation(
            running_run.id, active.id
        )

        with pytest.raises(ValueError, match="does not match active stage"):
            service.complete_with_checkpoint(
                "wrong-convo",
                running_run.id,
                "reviewer",
                artifacts={"decision": "approved"},
            )


# ============================================================================
# Prior checkpoints
# ============================================================================


class TestPriorCheckpoints:
    def test_get_prior_checkpoints(self, service, storage, running_run):
        active = storage.get_active_stage(running_run.id)
        convo_id = service.create_stage_conversation(running_run.id, active.id)

        # Submit checkpoint for exploration
        service.submit_checkpoint(
            convo_id, running_run.id, "agent", artifacts={"exploration": "data"}
        )

        # Now at opportunity_framing — should see exploration checkpoint
        checkpoints = service.get_prior_checkpoints(running_run.id)
        assert len(checkpoints) == 1
        assert checkpoints[0]["stage"] == "exploration"
        assert checkpoints[0]["artifacts"] == {"exploration": "data"}

    def test_empty_checkpoints_for_new_run(self, service, running_run):
        checkpoints = service.get_prior_checkpoints(running_run.id)
        assert checkpoints == []


# ============================================================================
# Transport isolation
# ============================================================================


class TestTransportIsolation:
    def test_in_memory_transport_generates_ids(self, transport):
        id1 = transport.generate_conversation_id()
        id2 = transport.generate_conversation_id()
        assert id1 != id2

    def test_in_memory_transport_read_nonexistent(self, transport):
        turns = transport.read_turns("nonexistent")
        assert turns == []

    def test_in_memory_transport_post_and_read(self, transport):
        transport.create_conversation("test-conv")
        turn_id = transport.post_turn("test-conv", "agent", "hello")
        turns = transport.read_turns("test-conv")
        assert len(turns) == 1
        assert turns[0]["text"] == "hello"
        assert turns[0]["id"] == turn_id
