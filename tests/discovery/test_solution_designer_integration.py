"""Integration tests for the SolutionDesigner with the state machine.

Tests the full flow: EXPLORATION → OPPORTUNITY_FRAMING → SOLUTION_VALIDATION →
checkpoint validates → state machine advances to FEASIBILITY_RISK.

Marked @pytest.mark.slow for the test runner.
Uses InMemoryTransport and InMemoryStorage.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.customer_voice import (
    CustomerVoiceExplorer,
    ExplorerConfig,
)
from src.discovery.agents.data_access import RawConversation
from src.discovery.agents.experience_agent import ExperienceAgent
from src.discovery.agents.opportunity_pm import OpportunityPM
from src.discovery.agents.solution_designer import (
    SolutionDesigner,
    SolutionDesignerConfig,
)
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.models.artifacts import (
    OpportunityFramingCheckpoint,
    SolutionValidationCheckpoint,
)
from src.discovery.models.conversation import EventType
from src.discovery.models.enums import (
    STAGE_ORDER,
    StageStatus,
    StageType,
)
from src.discovery.services.conversation import ConversationService
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import InMemoryTransport
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


def _setup_run_at_solution_validation():
    """Create a run that has completed EXPLORATION and OPPORTUNITY_FRAMING,
    ready for SOLUTION_VALIDATION.

    Returns (storage, transport, state_machine, service, run, opp_checkpoint, sol_convo_id).
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

    # --- Stage 0: EXPLORATION ---
    active = storage.get_active_stage(run.id)
    exploration_convo_id = service.create_stage_conversation(run.id, active.id)

    explorer_findings = [
        {
            "pattern_name": "scheduling_confusion",
            "description": "Users confused by scheduling UI",
            "evidence_conversation_ids": ["conv_001", "conv_002"],
            "confidence": "high",
            "severity_assessment": "moderate",
            "affected_users_estimate": "~20%",
        },
    ]

    convos = [_make_conversation(conversation_id=f"conv_{i:03d}") for i in range(5)]
    reader = MockReader(conversations=convos, count=5)
    mock_explorer_client = MagicMock()
    mock_explorer_client.chat.completions.create.side_effect = [
        _make_llm_response({"findings": explorer_findings, "batch_notes": ""}),
        _make_llm_response({"findings": explorer_findings, "synthesis_notes": ""}),
    ]

    explorer = CustomerVoiceExplorer(
        reader=reader,
        openai_client=mock_explorer_client,
        config=ExplorerConfig(batch_size=20),
    )
    explore_result = explorer.explore()
    exploration_checkpoint = explorer.build_checkpoint_artifacts(explore_result)

    opp_stage = service.submit_checkpoint(
        exploration_convo_id, run.id, "customer_voice", artifacts=exploration_checkpoint
    )
    assert opp_stage.stage == StageType.OPPORTUNITY_FRAMING

    # --- Stage 1: OPPORTUNITY_FRAMING ---
    opp_convo_id = opp_stage.conversation_id

    opp_response = {
        "opportunities": [
            {
                "problem_statement": "Users confused by scheduling UI across multiple flows",
                "evidence_conversation_ids": ["conv_001", "conv_002"],
                "counterfactual": "If simplified, 15% fewer tickets",
                "affected_area": "scheduling",
                "confidence": "high",
                "source_findings": ["scheduling_confusion"],
            },
        ],
        "framing_notes": "Single opportunity from scheduling findings",
    }

    mock_pm_client = MagicMock()
    mock_pm_client.chat.completions.create.return_value = _make_llm_response(
        opp_response
    )

    pm = OpportunityPM(openai_client=mock_pm_client)
    framing_result = pm.frame_opportunities(exploration_checkpoint)
    opp_checkpoint_dict = pm.build_checkpoint_artifacts(framing_result)

    sol_stage = service.submit_checkpoint(
        opp_convo_id, run.id, "opportunity_pm", artifacts=opp_checkpoint_dict
    )
    assert sol_stage.stage == StageType.SOLUTION_VALIDATION

    sol_convo_id = sol_stage.conversation_id

    return (
        storage,
        transport,
        state_machine,
        service,
        run,
        opp_checkpoint_dict,
        sol_convo_id,
    )


# ============================================================================
# Full flow integration tests
# ============================================================================


@pytest.mark.slow
class TestSolutionDesignerFullFlow:
    """Full flow: OPPORTUNITY_FRAMING → SOLUTION_VALIDATION → checkpoint → advance."""

    def test_solution_validation_advances_to_next_stage(self):
        """End-to-end: SolutionDesigner produces briefs → checkpoint validates →
        state machine advances past SOLUTION_VALIDATION."""
        (
            storage, transport, state_machine, service, run,
            opp_checkpoint, sol_convo_id,
        ) = _setup_run_at_solution_validation()

        # Extract opportunity briefs from prior checkpoint
        prior = service.get_prior_checkpoints(run.id)
        opp_artifacts = next(
            p["artifacts"]
            for p in prior
            if p["stage"] == StageType.OPPORTUNITY_FRAMING.value
        )
        briefs = opp_artifacts.get("briefs", [])
        assert len(briefs) >= 1

        # Set up SolutionDesigner with mocks
        pm_proposal = {
            "proposed_solution": "2-step scheduling wizard",
            "experiment_plan": "A/B test with 10% of users",
            "success_metrics": "+15% completion rate",
            "build_experiment_decision": "build_slice_and_experiment",
            "decision_rationale": "Strong evidence",
            "evidence_ids": ["conv_001", "conv_002"],
            "confidence": "high",
        }

        validation_response = {
            "assessment": "approve",
            "critique": "Well-scoped",
            "experiment_suggestion": "A/B test as proposed",
            "success_criteria": "15% improvement",
            "challenge_reason": "",
        }

        experience_response = {
            "user_impact_level": "high",
            "experience_direction": "Progress indicator + simplified form",
            "engagement_depth": "full",
            "notes": "",
        }

        mock_pm_client = MagicMock()
        mock_pm_client.chat.completions.create.return_value = _make_llm_response(
            pm_proposal
        )

        mock_val_client = MagicMock()
        mock_val_client.chat.completions.create.return_value = _make_llm_response(
            validation_response
        )

        mock_exp_client = MagicMock()
        mock_exp_client.chat.completions.create.return_value = _make_llm_response(
            experience_response
        )

        designer = SolutionDesigner(
            validation_agent=ValidationAgent(openai_client=mock_val_client),
            experience_agent=ExperienceAgent(openai_client=mock_exp_client),
            openai_client=mock_pm_client,
        )

        # Process each brief
        results = []
        for brief in briefs:
            result = designer.design_solution(
                opportunity_brief=brief,
                prior_checkpoints=prior,
            )
            results.append(result)

        # Build checkpoint
        sol_checkpoint = designer.build_checkpoint_artifacts(results)

        # Validate before submission
        validated = SolutionValidationCheckpoint(**sol_checkpoint)
        assert len(validated.solutions) == len(briefs)

        # Submit checkpoint — should advance
        next_stage = service.submit_checkpoint(
            sol_convo_id, run.id, "solution_designer", artifacts=sol_checkpoint
        )

        sol_idx = STAGE_ORDER.index(StageType.SOLUTION_VALIDATION)
        expected_next = STAGE_ORDER[sol_idx + 1]
        assert next_stage.stage == expected_next
        assert next_stage.status == StageStatus.IN_PROGRESS

    def test_solution_validation_stage_completed(self):
        """Verify SOLUTION_VALIDATION stage is marked completed."""
        (
            storage, transport, state_machine, service, run,
            opp_checkpoint, sol_convo_id,
        ) = _setup_run_at_solution_validation()

        # Minimal flow — single brief, single round
        prior = service.get_prior_checkpoints(run.id)
        opp_artifacts = next(
            p["artifacts"]
            for p in prior
            if p["stage"] == StageType.OPPORTUNITY_FRAMING.value
        )
        briefs = opp_artifacts.get("briefs", [])

        mock_pm_client = MagicMock()
        mock_pm_client.chat.completions.create.return_value = _make_llm_response(
            {
                "proposed_solution": "Quick fix",
                "experiment_plan": "Test",
                "success_metrics": "Metric",
                "build_experiment_decision": "experiment_first",
                "decision_rationale": "Reason",
                "evidence_ids": ["conv_001"],
                "confidence": "medium",
            }
        )

        mock_val_client = MagicMock()
        mock_val_client.chat.completions.create.return_value = _make_llm_response(
            {
                "assessment": "approve",
                "critique": "OK",
                "experiment_suggestion": "Test",
                "success_criteria": "Pass",
                "challenge_reason": "",
            }
        )

        mock_exp_client = MagicMock()
        mock_exp_client.chat.completions.create.return_value = _make_llm_response(
            {
                "user_impact_level": "low",
                "experience_direction": "Minor",
                "engagement_depth": "minimal",
                "notes": "",
            }
        )

        designer = SolutionDesigner(
            validation_agent=ValidationAgent(openai_client=mock_val_client),
            experience_agent=ExperienceAgent(openai_client=mock_exp_client),
            openai_client=mock_pm_client,
        )

        results = [
            designer.design_solution(brief, prior)
            for brief in briefs
        ]
        sol_checkpoint = designer.build_checkpoint_artifacts(results)

        service.submit_checkpoint(
            sol_convo_id, run.id, "solution_designer", artifacts=sol_checkpoint
        )

        # Verify old stage is completed
        sol_stages = storage.get_stage_executions_for_run(
            run.id, StageType.SOLUTION_VALIDATION
        )
        assert any(s.status == StageStatus.COMPLETED for s in sol_stages)


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
            opp_checkpoint, sol_convo_id,
        ) = _setup_run_at_solution_validation()

        prior = service.get_prior_checkpoints(run.id)
        opp_artifacts = next(
            p["artifacts"]
            for p in prior
            if p["stage"] == StageType.OPPORTUNITY_FRAMING.value
        )
        briefs = opp_artifacts.get("briefs", [])

        mock_pm_client = MagicMock()
        mock_pm_client.chat.completions.create.return_value = _make_llm_response(
            {
                "proposed_solution": "Fix it",
                "experiment_plan": "Test it",
                "success_metrics": "Measure it",
                "build_experiment_decision": "experiment_first",
                "decision_rationale": "Because",
                "evidence_ids": ["conv_001"],
                "confidence": "high",
            }
        )

        mock_val_client = MagicMock()
        mock_val_client.chat.completions.create.return_value = _make_llm_response(
            {
                "assessment": "approve",
                "critique": "Fine",
                "experiment_suggestion": "Good test",
                "success_criteria": "Pass",
                "challenge_reason": "",
            }
        )

        mock_exp_client = MagicMock()
        mock_exp_client.chat.completions.create.return_value = _make_llm_response(
            {
                "user_impact_level": "moderate",
                "experience_direction": "Some changes",
                "engagement_depth": "partial",
                "notes": "",
            }
        )

        designer = SolutionDesigner(
            validation_agent=ValidationAgent(openai_client=mock_val_client),
            experience_agent=ExperienceAgent(openai_client=mock_exp_client),
            openai_client=mock_pm_client,
        )

        results = [designer.design_solution(brief, prior) for brief in briefs]
        sol_checkpoint = designer.build_checkpoint_artifacts(results)

        service.submit_checkpoint(
            sol_convo_id, run.id, "solution_designer", artifacts=sol_checkpoint
        )

        history = service.read_history(sol_convo_id)
        event_types = [e.event_type for e in history]

        assert EventType.CHECKPOINT_SUBMIT in event_types
        assert EventType.STAGE_TRANSITION in event_types


# ============================================================================
# Prior checkpoints
# ============================================================================


@pytest.mark.slow
class TestPriorCheckpoints:
    """Verify Stage 2 can read Stage 0 + Stage 1 artifacts."""

    def test_prior_checkpoints_include_exploration_and_framing(self):
        """get_prior_checkpoints returns both EXPLORATION and OPPORTUNITY_FRAMING."""
        (
            storage, transport, state_machine, service, run,
            opp_checkpoint, sol_convo_id,
        ) = _setup_run_at_solution_validation()

        prior = service.get_prior_checkpoints(run.id)

        stages = [p["stage"] for p in prior]
        assert StageType.EXPLORATION.value in stages
        assert StageType.OPPORTUNITY_FRAMING.value in stages

    def test_opportunity_briefs_extractable_from_prior(self):
        """Can extract OpportunityBriefs from prior checkpoint."""
        (
            storage, transport, state_machine, service, run,
            opp_checkpoint, sol_convo_id,
        ) = _setup_run_at_solution_validation()

        prior = service.get_prior_checkpoints(run.id)
        opp_artifacts = next(
            p["artifacts"]
            for p in prior
            if p["stage"] == StageType.OPPORTUNITY_FRAMING.value
        )

        briefs = opp_artifacts.get("briefs", [])
        assert len(briefs) > 0
        assert all("problem_statement" in b for b in briefs)
