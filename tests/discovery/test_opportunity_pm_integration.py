"""Integration tests for the Opportunity PM agent with the state machine.

Tests the full flow: explorer checkpoint submitted → OPPORTUNITY_FRAMING stage
active → Opportunity PM produces briefs → checkpoint validates against
OpportunityFramingCheckpoint → state machine advances to SOLUTION_VALIDATION.

Marked @pytest.mark.slow for the test runner.
Uses InMemoryTransport and InMemoryStorage (same as test_explorer_integration.py).
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.customer_voice import (
    CustomerVoiceExplorer,
    ExplorerConfig,
)
from src.discovery.agents.data_access import RawConversation
from src.discovery.agents.opportunity_pm import (
    OpportunityPM,
    OpportunityPMConfig,
)
from src.discovery.models.artifacts import (
    OpportunityBrief,
    OpportunityFramingCheckpoint,
)
from src.discovery.models.conversation import EventType
from src.discovery.models.enums import (
    STAGE_ORDER,
    RunStatus,
    StageStatus,
    StageType,
)
from src.discovery.services.conversation import ConversationService
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import InMemoryTransport

# Import InMemoryStorage from existing test module
from tests.discovery.test_conversation_service import InMemoryStorage


# ============================================================================
# Helpers
# ============================================================================


def _make_llm_response(content_dict):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    return mock_response


def _make_conversation(**overrides) -> RawConversation:
    defaults = {
        "conversation_id": "conv_001",
        "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "source_body": "I can't schedule posts",
        "full_conversation": "Customer: I can't schedule posts\nAgent: Can you describe?",
        "source_url": "https://app.example.com/scheduler",
        "used_fallback": False,
    }
    defaults.update(overrides)
    return RawConversation(**defaults)


class MockReader:
    def __init__(self, conversations=None, count=None):
        self._conversations = conversations or []
        self._count = count if count is not None else len(self._conversations)
        self._by_id = {c.conversation_id: c for c in self._conversations}

    def fetch_conversations(self, days, limit=None):
        result = self._conversations
        if limit:
            result = result[:limit]
        return result

    def fetch_conversation_by_id(self, conversation_id):
        return self._by_id.get(conversation_id)

    def get_conversation_count(self, days):
        return self._count


def _setup_run_at_opportunity_framing():
    """Create a run that has completed EXPLORATION and is ready for OPPORTUNITY_FRAMING.

    Returns (storage, transport, state_machine, service, run, exploration_checkpoint, opp_convo_id).
    """
    storage = InMemoryStorage()
    transport = InMemoryTransport()
    state_machine = DiscoveryStateMachine(storage=storage)
    service = ConversationService(
        transport=transport, storage=storage, state_machine=state_machine
    )

    # Create and start run
    run = state_machine.create_run()
    run = state_machine.start_run(run.id)

    # Create exploration stage conversation
    active = storage.get_active_stage(run.id)
    exploration_convo_id = service.create_stage_conversation(run.id, active.id)

    # Explorer produces findings and submits checkpoint
    explorer_findings = [
        {
            "pattern_name": "scheduling_confusion",
            "description": "Users confused by scheduling UI",
            "evidence_conversation_ids": ["conv_001", "conv_002"],
            "confidence": "high",
            "severity_assessment": "moderate",
            "affected_users_estimate": "~20%",
        },
        {
            "pattern_name": "payment_flow_friction",
            "description": "Checkout causes abandonment",
            "evidence_conversation_ids": ["conv_003", "conv_004"],
            "confidence": "medium",
            "severity_assessment": "high",
            "affected_users_estimate": "~15%",
        },
    ]

    convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(5)]
    reader = MockReader(conversations=convos, count=5)
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_llm_response({"findings": explorer_findings, "batch_notes": ""}),
        _make_llm_response({"findings": explorer_findings, "synthesis_notes": ""}),
    ]

    explorer = CustomerVoiceExplorer(
        reader=reader,
        openai_client=mock_client,
        config=ExplorerConfig(batch_size=20),
    )
    result = explorer.explore()
    exploration_checkpoint = explorer.build_checkpoint_artifacts(result)

    # Submit exploration checkpoint — advances to OPPORTUNITY_FRAMING
    opp_stage = service.submit_checkpoint(
        exploration_convo_id, run.id, "customer_voice", artifacts=exploration_checkpoint
    )
    assert opp_stage.stage == StageType.OPPORTUNITY_FRAMING

    # Get the conversation_id for the opportunity framing stage
    opp_convo_id = opp_stage.conversation_id

    return (
        storage,
        transport,
        state_machine,
        service,
        run,
        exploration_checkpoint,
        opp_convo_id,
    )


# ============================================================================
# Full flow integration tests
# ============================================================================


@pytest.mark.slow
class TestOpportunityPMFullFlow:
    """Full flow: EXPLORATION → OPPORTUNITY_FRAMING → checkpoint → advance."""

    def test_opportunity_framing_advances_to_next_stage(self):
        """End-to-end: Opportunity PM produces briefs → checkpoint validates →
        state machine advances past OPPORTUNITY_FRAMING."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        # Opportunity PM produces briefs
        opp_response = {
            "opportunities": [
                {
                    "problem_statement": "Users confused by scheduling UI across multiple flows",
                    "evidence_conversation_ids": ["conv_001", "conv_002"],
                    "counterfactual": "If we simplified the scheduling flow, we'd expect 15% fewer support tickets about scheduling",
                    "affected_area": "scheduling",
                    "confidence": "high",
                    "source_findings": ["scheduling_confusion"],
                },
                {
                    "problem_statement": "Payment checkout friction causing cart abandonment",
                    "evidence_conversation_ids": ["conv_003", "conv_004"],
                    "counterfactual": "If we reduced checkout steps, we'd expect 10% improvement in conversion rate",
                    "affected_area": "billing",
                    "confidence": "medium",
                    "source_findings": ["payment_flow_friction"],
                },
            ],
            "framing_notes": "Grouped scheduling findings into one opportunity",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(opp_response)

        pm = OpportunityPM(openai_client=mock_client)
        result = pm.frame_opportunities(exploration_checkpoint)
        opp_checkpoint = pm.build_checkpoint_artifacts(result)

        # Validate checkpoint structure before submission
        validated = OpportunityFramingCheckpoint(**opp_checkpoint)
        assert len(validated.briefs) == 2

        # Submit checkpoint — should advance to next stage
        next_stage = service.submit_checkpoint(
            opp_convo_id, run.id, "opportunity_pm", artifacts=opp_checkpoint
        )

        # Verify advancement is to the stage after OPPORTUNITY_FRAMING in STAGE_ORDER
        opp_idx = STAGE_ORDER.index(StageType.OPPORTUNITY_FRAMING)
        expected_next = STAGE_ORDER[opp_idx + 1]
        assert next_stage.stage == expected_next
        assert next_stage.status == StageStatus.IN_PROGRESS

    def test_opportunity_framing_stage_completed(self):
        """Verify OPPORTUNITY_FRAMING stage is marked completed after checkpoint."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        opp_response = {
            "opportunities": [{
                "problem_statement": "Single opportunity",
                "evidence_conversation_ids": ["conv_001"],
                "counterfactual": "If addressed, expect measurable improvement",
                "affected_area": "core_product",
                "confidence": "high",
                "source_findings": ["scheduling_confusion"],
            }],
            "framing_notes": "",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(opp_response)

        pm = OpportunityPM(openai_client=mock_client)
        result = pm.frame_opportunities(exploration_checkpoint)
        opp_checkpoint = pm.build_checkpoint_artifacts(result)

        service.submit_checkpoint(
            opp_convo_id, run.id, "opportunity_pm", artifacts=opp_checkpoint
        )

        # Verify old stage is completed
        opp_stages = storage.get_stage_executions_for_run(
            run.id, StageType.OPPORTUNITY_FRAMING
        )
        assert any(s.status == StageStatus.COMPLETED for s in opp_stages)

    def test_empty_briefs_checkpoint_advances(self):
        """Empty briefs list (no actionable opportunities) still advances."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        # Directly build an empty checkpoint (no LLM call needed for empty findings)
        pm = OpportunityPM(openai_client=MagicMock())
        empty_result = pm.frame_opportunities(
            {"findings": [], "coverage": exploration_checkpoint.get("coverage", {})}
        )
        opp_checkpoint = pm.build_checkpoint_artifacts(empty_result)

        # Should validate and advance
        next_stage = service.submit_checkpoint(
            opp_convo_id, run.id, "opportunity_pm", artifacts=opp_checkpoint
        )

        opp_idx = STAGE_ORDER.index(StageType.OPPORTUNITY_FRAMING)
        expected_next = STAGE_ORDER[opp_idx + 1]
        assert next_stage.stage == expected_next


# ============================================================================
# Conversation audit trail
# ============================================================================


@pytest.mark.slow
class TestConversationAuditTrail:
    """Verify events appear in conversation history."""

    def test_checkpoint_and_transition_events(self):
        """checkpoint:submit and stage:transition events appear in conversation."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        opp_response = {
            "opportunities": [{
                "problem_statement": "Test opportunity",
                "evidence_conversation_ids": ["conv_001"],
                "counterfactual": "If addressed, expect improvement",
                "affected_area": "test_area",
                "confidence": "high",
                "source_findings": ["scheduling_confusion"],
            }],
            "framing_notes": "",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(opp_response)

        pm = OpportunityPM(openai_client=mock_client)
        result = pm.frame_opportunities(exploration_checkpoint)
        opp_checkpoint = pm.build_checkpoint_artifacts(result)

        service.submit_checkpoint(
            opp_convo_id, run.id, "opportunity_pm", artifacts=opp_checkpoint
        )

        # Read conversation history for the opportunity framing stage
        history = service.read_history(opp_convo_id)
        event_types = [e.event_type for e in history]

        assert EventType.CHECKPOINT_SUBMIT in event_types
        assert EventType.STAGE_TRANSITION in event_types


# ============================================================================
# Prior checkpoints
# ============================================================================


@pytest.mark.slow
class TestPriorCheckpoints:
    """Verify the Opportunity PM can read Stage 0 artifacts."""

    def test_prior_checkpoints_include_exploration(self):
        """get_prior_checkpoints returns EXPLORATION checkpoint for the Opportunity PM to read."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        prior = service.get_prior_checkpoints(run.id)

        # Should include the completed exploration stage
        exploration_checkpoints = [
            p for p in prior if p["stage"] == StageType.EXPLORATION.value
        ]
        assert len(exploration_checkpoints) == 1

        artifacts = exploration_checkpoints[0]["artifacts"]
        assert "findings" in artifacts
        assert "coverage" in artifacts

    def test_opportunity_pm_reads_prior_findings(self):
        """Opportunity PM can extract findings from prior checkpoint."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        prior = service.get_prior_checkpoints(run.id)
        exploration_artifacts = next(
            p["artifacts"]
            for p in prior
            if p["stage"] == StageType.EXPLORATION.value
        )

        findings = exploration_artifacts.get("findings", [])
        assert len(findings) > 0
        assert all("pattern_name" in f for f in findings)


# ============================================================================
# Requery event flow
# ============================================================================


@pytest.mark.slow
class TestRequeryEventFlow:
    """Verify explorer:request / explorer:response events work through conversation."""

    def test_requery_events_in_conversation(self):
        """Post explorer:request → read it back → post explorer:response."""
        (
            storage, transport, state_machine, service, run,
            exploration_checkpoint, opp_convo_id,
        ) = _setup_run_at_opportunity_framing()

        # Post an explorer:request event (as the orchestrator would)
        service.post_event(
            opp_convo_id,
            "opportunity_pm",
            EventType.EXPLORER_REQUEST,
            {"query": "How many scheduling-related conversations were there?"},
        )

        # Read history and find the request
        history = service.read_history(opp_convo_id)
        requests = [e for e in history if e.event_type == EventType.EXPLORER_REQUEST]
        assert len(requests) == 1

        # Post an explorer:response event
        service.post_event(
            opp_convo_id,
            "customer_voice",
            EventType.EXPLORER_RESPONSE,
            {"answer": "Found 8 scheduling conversations across the dataset"},
        )

        # Verify response in history
        history = service.read_history(opp_convo_id)
        responses = [e for e in history if e.event_type == EventType.EXPLORER_RESPONSE]
        assert len(responses) == 1
        assert "scheduling" in responses[0].payload.get("answer", "")
