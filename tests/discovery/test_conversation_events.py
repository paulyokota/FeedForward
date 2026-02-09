"""Tests for conversation event parsing and checkpoint validation.

Covers: structured event detection, plain text fallback, malformed JSON handling,
checkpoint submission parsing, artifact validation per stage, and event building.
"""

import json
from datetime import datetime, timezone

import pytest

from src.discovery.models.conversation import (
    CheckpointSubmission,
    ConversationEvent,
    ConversationTurn,
    EventType,
    build_event_text,
    parse_checkpoint_submission,
    parse_turn,
)
from src.discovery.models.enums import (
    ConfidenceLevel,
    SourceType,
    StageType,
)
from src.discovery.services.conversation import (
    STAGE_ARTIFACT_MODELS,
    ArtifactValidationError,
    ConversationService,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_turn(text, role="agent", turn_id="turn-1"):
    return ConversationTurn(
        id=turn_id,
        role=role,
        text=text,
        mode="claude",
        createdAt=datetime.now(timezone.utc).isoformat(),
    )


def _valid_evidence():
    return {
        "source_type": SourceType.INTERCOM.value,
        "source_id": "conv_123",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "confidence": ConfidenceLevel.HIGH.value,
    }


# ============================================================================
# Event parsing: structured events
# ============================================================================


class TestEventParsing:
    def test_plain_text_message(self):
        turn = _make_turn("I found some interesting patterns in the data")
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE
        assert event.payload is None
        assert event.text == "I found some interesting patterns in the data"

    def test_checkpoint_submit_event(self):
        payload = {
            "_event": "checkpoint:submit",
            "agent": "customer_voice",
            "artifacts": {"problem_statement": "test"},
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        assert event.event_type == EventType.CHECKPOINT_SUBMIT
        assert event.payload == payload
        assert event.agent_name == "customer_voice"

    def test_explorer_request_event(self):
        payload = {
            "_event": "explorer:request",
            "agent": "synthesis",
            "query": "How many billing complaints in last 30 days?",
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        assert event.event_type == EventType.EXPLORER_REQUEST
        assert event.agent_name == "synthesis"

    def test_explorer_response_event(self):
        payload = {
            "_event": "explorer:response",
            "agent": "customer_voice",
            "data": {"count": 42},
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        assert event.event_type == EventType.EXPLORER_RESPONSE

    def test_stage_transition_event(self):
        payload = {
            "_event": "stage:transition",
            "agent": "orchestrator",
            "from_stage": "exploration",
            "to_stage": "opportunity_framing",
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        assert event.event_type == EventType.STAGE_TRANSITION

    def test_all_event_types(self):
        for event_type in EventType:
            if event_type == EventType.MESSAGE:
                continue  # MESSAGE is the default, not a JSON event
            payload = {"_event": event_type.value, "agent": "test"}
            turn = _make_turn(json.dumps(payload))
            event = parse_turn(turn)
            assert event.event_type == event_type

    def test_unknown_event_type_falls_back_to_message(self):
        payload = {"_event": "unknown:event", "agent": "test"}
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE

    def test_preserves_turn_metadata(self):
        turn = _make_turn("hello", role="human", turn_id="turn-42")
        event = parse_turn(turn)
        assert event.turn_id == "turn-42"
        assert event.role == "human"


# ============================================================================
# Event parsing: malformed input handling
# ============================================================================


class TestMalformedInput:
    def test_invalid_json_treated_as_message(self):
        turn = _make_turn("{not valid json")
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE
        assert event.payload is None

    def test_json_without_event_field_treated_as_message(self):
        turn = _make_turn(json.dumps({"key": "value", "data": 42}))
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE
        assert event.payload is None

    def test_json_array_treated_as_message(self):
        turn = _make_turn(json.dumps([1, 2, 3]))
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE

    def test_json_string_treated_as_message(self):
        turn = _make_turn(json.dumps("just a string"))
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE

    def test_json_number_treated_as_message(self):
        turn = _make_turn(json.dumps(42))
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE

    def test_empty_string_treated_as_message(self):
        turn = _make_turn("")
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE

    def test_json_with_event_null_treated_as_message(self):
        turn = _make_turn(json.dumps({"_event": None}))
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE

    def test_text_that_looks_like_json_prefix(self):
        """Text starting with { but not valid JSON should be treated as message."""
        turn = _make_turn('{"_event": "checkpoint:submit", oops no closing')
        event = parse_turn(turn)
        assert event.event_type == EventType.MESSAGE


# ============================================================================
# Checkpoint submission parsing
# ============================================================================


class TestCheckpointSubmission:
    def test_valid_checkpoint_submission(self):
        payload = {
            "_event": "checkpoint:submit",
            "agent": "customer_voice",
            "stage": "exploration",
            "artifacts": {"findings": "data"},
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        submission = parse_checkpoint_submission(event)
        assert submission.agent_name == "customer_voice"
        assert submission.artifacts == {"findings": "data"}
        assert submission.stage == "exploration"

    def test_wrong_event_type_rejected(self):
        turn = _make_turn("plain text")
        event = parse_turn(turn)
        with pytest.raises(ValueError, match="Expected checkpoint:submit"):
            parse_checkpoint_submission(event)

    def test_missing_agent_rejected(self):
        payload = {
            "_event": "checkpoint:submit",
            "artifacts": {"data": True},
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        with pytest.raises(ValueError, match="missing 'agent'"):
            parse_checkpoint_submission(event)

    def test_missing_artifacts_rejected(self):
        payload = {
            "_event": "checkpoint:submit",
            "agent": "test_agent",
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        with pytest.raises(ValueError, match="missing or invalid 'artifacts'"):
            parse_checkpoint_submission(event)

    def test_non_dict_artifacts_rejected(self):
        payload = {
            "_event": "checkpoint:submit",
            "agent": "test_agent",
            "artifacts": [1, 2, 3],
        }
        turn = _make_turn(json.dumps(payload))
        event = parse_turn(turn)
        with pytest.raises(ValueError, match="missing or invalid 'artifacts'"):
            parse_checkpoint_submission(event)


# ============================================================================
# Event building
# ============================================================================


class TestEventBuilding:
    def test_build_checkpoint_event(self):
        text = build_event_text(
            EventType.CHECKPOINT_SUBMIT,
            {"agent": "customer_voice", "artifacts": {"data": True}},
        )
        parsed = json.loads(text)
        assert parsed["_event"] == "checkpoint:submit"
        assert parsed["agent"] == "customer_voice"
        assert parsed["artifacts"] == {"data": True}

    def test_built_event_is_parseable(self):
        """Events built by build_event_text should be parseable by parse_turn."""
        text = build_event_text(
            EventType.EXPLORER_REQUEST,
            {"agent": "synthesis", "query": "how many?"},
        )
        turn = _make_turn(text)
        event = parse_turn(turn)
        assert event.event_type == EventType.EXPLORER_REQUEST
        assert event.agent_name == "synthesis"


# ============================================================================
# Artifact validation per stage
# ============================================================================


class TestArtifactValidation:
    """Tests for _validate_artifacts via the STAGE_ARTIFACT_MODELS mapping."""

    def test_stages_with_models_are_mapped(self):
        """Verify the mapping covers all stages."""
        for stage in StageType:
            assert stage in STAGE_ARTIFACT_MODELS

    def test_opportunity_framing_valid(self):
        """OpportunityFramingCheckpoint validation with valid data."""
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,  # not needed for validation
            state_machine=None,
        )
        artifacts = {
            "schema_version": 1,
            "briefs": [
                {
                    "problem_statement": "Users can't reset passwords",
                    "evidence": [_valid_evidence()],
                    "counterfactual": "If we fix this, support tickets drop 20%",
                    "affected_area": "authentication",
                    "explorer_coverage": "Intercom last 14 days",
                },
            ],
            "framing_metadata": {
                "explorer_findings_count": 1,
                "opportunities_identified": 1,
                "model": "gpt-4o-mini",
            },
        }
        # Should not raise
        svc._validate_artifacts(StageType.OPPORTUNITY_FRAMING, artifacts)

    def test_opportunity_framing_invalid(self):
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,
            state_machine=None,
        )
        # Missing required fields
        artifacts = {"problem_statement": "test"}
        with pytest.raises(ArtifactValidationError) as exc_info:
            svc._validate_artifacts(StageType.OPPORTUNITY_FRAMING, artifacts)
        assert exc_info.value.stage == StageType.OPPORTUNITY_FRAMING
        assert len(exc_info.value.errors) > 0

    def test_solution_validation_valid(self):
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,
            state_machine=None,
        )
        artifacts = {
            "schema_version": 1,
            "solutions": [
                {
                    "proposed_solution": "Add password reset flow",
                    "experiment_plan": "A/B test with 10% of users",
                    "success_metrics": "Support tickets for password issues drop from 50/week to 10/week",
                    "build_experiment_decision": "experiment_first",
                    "evidence": [_valid_evidence()],
                },
            ],
            "design_metadata": {
                "opportunity_briefs_processed": 1,
                "solutions_produced": 1,
                "total_dialogue_rounds": 1,
                "total_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "model": "gpt-4o-mini",
            },
        }
        svc._validate_artifacts(StageType.SOLUTION_VALIDATION, artifacts)

    def test_feasibility_risk_valid(self):
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,
            state_machine=None,
        )
        artifacts = {
            "approach": "Use existing auth module",
            "effort_estimate": "2-3 sprints (medium confidence)",
            "dependencies": "Requires auth-service v2.1+",
            "risks": ["Rate limiting not implemented", "No rollback plan"],
            "acceptance_criteria": "Password reset works for all user types",
        }
        svc._validate_artifacts(StageType.FEASIBILITY_RISK, artifacts)

    def test_exploration_validates_explorer_checkpoint(self):
        """EXPLORATION stage validates against ExplorerCheckpoint model."""
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,
            state_machine=None,
        )
        valid_checkpoint = {
            "agent_name": "customer_voice",
            "findings": [],
            "coverage": {
                "time_window_days": 14,
                "conversations_available": 100,
                "conversations_reviewed": 95,
                "conversations_skipped": 5,
                "model": "gpt-4o-mini",
                "findings_count": 0,
            },
        }
        svc._validate_artifacts(StageType.EXPLORATION, valid_checkpoint)

    def test_exploration_rejects_invalid(self):
        """EXPLORATION rejects artifacts that don't match ExplorerCheckpoint."""
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,
            state_machine=None,
        )
        with pytest.raises(ArtifactValidationError, match="Field required"):
            svc._validate_artifacts(StageType.EXPLORATION, {})

    def test_extra_fields_allowed(self):
        """Artifact models use extra='allow', so extra fields should pass."""
        from src.discovery.services.conversation import ConversationService
        from src.discovery.services.transport import InMemoryTransport

        svc = ConversationService(
            transport=InMemoryTransport(),
            storage=None,
            state_machine=None,
        )
        artifacts = {
            "schema_version": 1,
            "briefs": [
                {
                    "problem_statement": "Users can't reset passwords",
                    "evidence": [_valid_evidence()],
                    "counterfactual": "If we fix this, tickets drop 20%",
                    "affected_area": "authentication",
                    "explorer_coverage": "Intercom last 14 days",
                    "extra_field": "this should be allowed on brief",
                },
            ],
            "framing_metadata": {
                "explorer_findings_count": 1,
                "opportunities_identified": 1,
                "model": "gpt-4o-mini",
            },
            "extra_field": "this should be allowed on checkpoint",
            "another_extra": 42,
        }
        # Should not raise
        svc._validate_artifacts(StageType.OPPORTUNITY_FRAMING, artifacts)
