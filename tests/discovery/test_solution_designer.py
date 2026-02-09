"""Unit tests for the SolutionDesigner orchestrator (Issue #220).

Tests the multi-agent dialogue: PM → Validation → Experience → convergence.
Uses mock OpenAI client and mock agents — no real LLM calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.experience_agent import ExperienceAgent
from src.discovery.agents.solution_designer import (
    DialogueTurn,
    SolutionDesigner,
    SolutionDesignerConfig,
    SolutionDesignResult,
)
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.models.artifacts import (
    SolutionBrief,
    SolutionValidationCheckpoint,
)
from src.discovery.models.enums import BuildExperimentDecision


# ============================================================================
# Helpers
# ============================================================================


def _make_llm_response(content_dict):
    """Create mock OpenAI ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 80
    mock_response.usage.total_tokens = 180
    return mock_response


def _make_pm_proposal(**overrides):
    """Build a typical PM proposal LLM response."""
    defaults = {
        "proposed_solution": "Simplify scheduling wizard to 2 steps",
        "experiment_plan": "A/B test with 10% of users",
        "success_metrics": "Scheduling completion rate +15%",
        "build_experiment_decision": "build_slice_and_experiment",
        "decision_rationale": "Strong evidence supports minimal build",
        "evidence_ids": ["conv_001", "conv_002"],
        "confidence": "high",
    }
    defaults.update(overrides)
    return defaults


def _make_validation_response(assessment="approve", **overrides):
    """Build a typical Validation Agent response."""
    defaults = {
        "assessment": assessment,
        "critique": "Well-scoped proposal",
        "experiment_suggestion": "A/B test as proposed",
        "success_criteria": "15% improvement",
        "challenge_reason": "",
    }
    defaults.update(overrides)
    return defaults


def _make_experience_response(**overrides):
    """Build a typical Experience Agent response."""
    defaults = {
        "user_impact_level": "high",
        "experience_direction": "Redesign wizard with progress indicator",
        "engagement_depth": "full",
        "notes": "",
    }
    defaults.update(overrides)
    return defaults


def _make_opportunity_brief():
    """Build a typical OpportunityBrief dict."""
    return {
        "problem_statement": "Users confused by scheduling UI",
        "evidence": [
            {
                "source_type": "intercom",
                "source_id": "conv_001",
                "retrieved_at": "2026-02-01T00:00:00+00:00",
                "confidence": "high",
            }
        ],
        "counterfactual": "15% fewer support tickets if simplified",
        "affected_area": "scheduling",
        "explorer_coverage": "180 conversations over 14 days",
    }


def _make_designer(
    pm_responses,
    validation_responses,
    experience_responses,
    max_rounds=3,
):
    """Create a SolutionDesigner with mocked agents and LLM client.

    pm_responses: list of dicts for PM LLM responses (proposal + revisions)
    validation_responses: list of dicts for Validation Agent responses
    experience_responses: list of dicts for Experience Agent responses
    """
    # Mock OpenAI client for PM calls
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_llm_response(r) for r in pm_responses
    ]

    # Mock Validation Agent
    mock_val_client = MagicMock()
    mock_val_client.chat.completions.create.side_effect = [
        _make_llm_response(r) for r in validation_responses
    ]
    validation_agent = ValidationAgent(openai_client=mock_val_client)

    # Mock Experience Agent
    mock_exp_client = MagicMock()
    mock_exp_client.chat.completions.create.side_effect = [
        _make_llm_response(r) for r in experience_responses
    ]
    experience_agent = ExperienceAgent(openai_client=mock_exp_client)

    config = SolutionDesignerConfig(max_rounds=max_rounds)

    return SolutionDesigner(
        validation_agent=validation_agent,
        experience_agent=experience_agent,
        openai_client=mock_client,
        config=config,
    )


# ============================================================================
# Single-round convergence
# ============================================================================


class TestSingleRoundConvergence:
    """All agents agree in round 1 — fastest path."""

    def test_converges_in_one_round(self):
        """PM proposes, Validation approves, Experience evaluates → done."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[_make_validation_response("approve")],
            experience_responses=[_make_experience_response()],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.dialogue_rounds == 1
        assert result.convergence_forced is False
        assert result.convergence_note == ""
        assert result.proposed_solution != ""
        assert result.build_experiment_decision == "build_slice_and_experiment"

    def test_no_validation_challenges_on_approve(self):
        """No challenges recorded when Validation approves immediately."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[_make_validation_response("approve")],
            experience_responses=[_make_experience_response()],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.validation_challenges == []

    def test_experience_direction_captured(self):
        """Experience direction is included in result."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[_make_validation_response("approve")],
            experience_responses=[
                _make_experience_response(
                    user_impact_level="high",
                    experience_direction="Full wizard redesign",
                )
            ],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.experience_direction["user_impact_level"] == "high"
        assert "wizard" in result.experience_direction["experience_direction"].lower()


# ============================================================================
# Multi-round with challenge
# ============================================================================


class TestMultiRoundChallenge:
    """Validation challenges, PM revises, converges in round 2."""

    def test_challenge_then_approve(self):
        """Round 1: challenge → Round 2: approve."""
        designer = _make_designer(
            pm_responses=[
                _make_pm_proposal(build_experiment_decision="build_direct"),
                _make_pm_proposal(build_experiment_decision="experiment_first"),
            ],
            validation_responses=[
                _make_validation_response(
                    "challenge",
                    challenge_reason="build_direct is premature",
                ),
                _make_validation_response("approve"),
            ],
            experience_responses=[
                _make_experience_response(),
                _make_experience_response(),
            ],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.dialogue_rounds == 2
        assert result.convergence_forced is False
        assert len(result.validation_challenges) == 1
        assert result.validation_challenges[0]["round"] == 1
        assert "premature" in result.validation_challenges[0]["challenge_reason"]

    def test_request_revision_then_approve(self):
        """Round 1: request_revision → Round 2: approve."""
        designer = _make_designer(
            pm_responses=[
                _make_pm_proposal(proposed_solution="Vague improvement"),
                _make_pm_proposal(proposed_solution="Specific 2-step wizard"),
            ],
            validation_responses=[
                _make_validation_response("request_revision"),
                _make_validation_response("approve"),
            ],
            experience_responses=[
                _make_experience_response(),
                _make_experience_response(),
            ],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.dialogue_rounds == 2
        assert result.convergence_forced is False
        # request_revision is not recorded as a challenge
        assert len(result.validation_challenges) == 0


# ============================================================================
# Forced convergence
# ============================================================================


class TestForcedConvergence:
    """Max rounds hit without agreement."""

    def test_forced_convergence_after_max_rounds(self):
        """3 rounds of challenge → forced convergence."""
        designer = _make_designer(
            pm_responses=[
                _make_pm_proposal(),
                _make_pm_proposal(),
                _make_pm_proposal(),
            ],
            validation_responses=[
                _make_validation_response(
                    "challenge", challenge_reason="Too risky"
                ),
                _make_validation_response(
                    "challenge", challenge_reason="Still too risky"
                ),
                _make_validation_response(
                    "challenge", challenge_reason="Not convinced"
                ),
            ],
            experience_responses=[
                _make_experience_response(),
                _make_experience_response(),
                _make_experience_response(),
            ],
            max_rounds=3,
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.dialogue_rounds == 3
        assert result.convergence_forced is True
        assert result.convergence_note != ""
        assert "forced" in result.convergence_note.lower()
        assert len(result.validation_challenges) == 3

    def test_forced_convergence_note_includes_last_challenge(self):
        """Convergence note references the last unresolved challenge."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal(), _make_pm_proposal()],
            validation_responses=[
                _make_validation_response(
                    "challenge", challenge_reason="First issue"
                ),
                _make_validation_response(
                    "challenge", challenge_reason="Second issue"
                ),
            ],
            experience_responses=[
                _make_experience_response(),
                _make_experience_response(),
            ],
            max_rounds=2,
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert "Second issue" in result.convergence_note


# ============================================================================
# Checkpoint building
# ============================================================================


class TestCheckpointBuilding:
    """SolutionDesignResult → SolutionValidationCheckpoint."""

    def test_single_result_produces_valid_checkpoint(self):
        """One result → valid SolutionValidationCheckpoint."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[_make_validation_response("approve")],
            experience_responses=[_make_experience_response()],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([result])

        # Should validate without error
        validated = SolutionValidationCheckpoint(**checkpoint)
        assert len(validated.solutions) == 1
        assert validated.design_metadata.solutions_produced == 1
        assert validated.design_metadata.model == "gpt-4o-mini"

    def test_multiple_results_produce_valid_checkpoint(self):
        """Two results → valid checkpoint with 2 solutions."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal(), _make_pm_proposal()],
            validation_responses=[
                _make_validation_response("approve"),
                _make_validation_response("approve"),
            ],
            experience_responses=[
                _make_experience_response(),
                _make_experience_response(),
            ],
        )

        result1 = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )
        # Reset mocks for second call
        designer.client.chat.completions.create.side_effect = [
            _make_llm_response(_make_pm_proposal())
        ]
        designer.validation_agent.client.chat.completions.create.side_effect = [
            _make_llm_response(_make_validation_response("approve"))
        ]
        designer.experience_agent.client.chat.completions.create.side_effect = [
            _make_llm_response(_make_experience_response())
        ]

        result2 = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([result1, result2])

        validated = SolutionValidationCheckpoint(**checkpoint)
        assert len(validated.solutions) == 2
        assert validated.design_metadata.opportunity_briefs_processed == 2

    def test_each_solution_validates_as_solution_brief(self):
        """Each solution in the checkpoint validates as SolutionBrief."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[_make_validation_response("approve")],
            experience_responses=[_make_experience_response()],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([result])

        for sol_dict in checkpoint["solutions"]:
            validated = SolutionBrief(**sol_dict)
            assert validated.proposed_solution != ""
            assert validated.build_experiment_decision in [
                e.value for e in BuildExperimentDecision
            ]

    def test_extra_fields_stored_in_solution_brief(self):
        """Extra fields (validation_challenges, experience_direction, etc.) are preserved."""
        designer = _make_designer(
            pm_responses=[
                _make_pm_proposal(),
                _make_pm_proposal(),
            ],
            validation_responses=[
                _make_validation_response(
                    "challenge", challenge_reason="Too risky"
                ),
                _make_validation_response("approve"),
            ],
            experience_responses=[
                _make_experience_response(user_impact_level="high"),
                _make_experience_response(user_impact_level="high"),
            ],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([result])
        sol = checkpoint["solutions"][0]

        # These are extra fields on SolutionBrief
        assert "decision_rationale" in sol
        assert "validation_challenges" in sol
        assert "experience_direction" in sol
        assert "convergence_forced" in sol
        assert "convergence_note" in sol

        # SolutionBrief accepts them via extra='allow'
        validated = SolutionBrief(**sol)
        assert validated.proposed_solution != ""

    def test_empty_results_produce_valid_checkpoint(self):
        """Empty results list → valid checkpoint with empty solutions."""
        designer = _make_designer(
            pm_responses=[],
            validation_responses=[],
            experience_responses=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([])

        validated = SolutionValidationCheckpoint(**checkpoint)
        assert validated.solutions == []
        assert validated.design_metadata.solutions_produced == 0
        assert validated.design_metadata.total_dialogue_rounds == 0

    def test_token_usage_aggregated_in_metadata(self):
        """Token usage is summed across all results in metadata."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[_make_validation_response("approve")],
            experience_responses=[_make_experience_response()],
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([result])

        metadata = checkpoint["design_metadata"]
        assert metadata["total_token_usage"]["total_tokens"] > 0

    def test_forced_convergence_fields_in_checkpoint(self):
        """Forced convergence fields appear in the solution brief."""
        designer = _make_designer(
            pm_responses=[_make_pm_proposal()],
            validation_responses=[
                _make_validation_response(
                    "challenge", challenge_reason="Not good enough"
                )
            ],
            experience_responses=[_make_experience_response()],
            max_rounds=1,
        )

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        checkpoint = designer.build_checkpoint_artifacts([result])
        sol = checkpoint["solutions"][0]

        assert sol["convergence_forced"] is True
        assert sol["convergence_note"] != ""


# ============================================================================
# DialogueTurn
# ============================================================================


class TestDialogueTurn:
    """DialogueTurn dataclass basics."""

    def test_dialogue_turn_fields(self):
        turn = DialogueTurn(
            round_number=1,
            agent="opportunity_pm",
            role="proposal",
            content={"proposed_solution": "test"},
        )
        assert turn.round_number == 1
        assert turn.agent == "opportunity_pm"
        assert turn.role == "proposal"
        assert turn.content["proposed_solution"] == "test"


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    """Error propagation from agents."""

    def test_pm_error_propagates(self):
        """PM LLM failure propagates to caller."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("PM failed")

        designer = SolutionDesigner(
            validation_agent=ValidationAgent(openai_client=MagicMock()),
            experience_agent=ExperienceAgent(openai_client=MagicMock()),
            openai_client=mock_client,
        )

        with pytest.raises(RuntimeError, match="PM failed"):
            designer.design_solution(
                opportunity_brief=_make_opportunity_brief(),
                prior_checkpoints=[],
            )

    def test_pm_missing_key_raises(self):
        """PM response without proposed_solution raises ValueError."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {"some_other_key": "value"}
        )

        designer = SolutionDesigner(
            validation_agent=ValidationAgent(openai_client=MagicMock()),
            experience_agent=ExperienceAgent(openai_client=MagicMock()),
            openai_client=mock_client,
        )

        with pytest.raises(ValueError, match="missing required 'proposed_solution'"):
            designer.design_solution(
                opportunity_brief=_make_opportunity_brief(),
                prior_checkpoints=[],
            )
