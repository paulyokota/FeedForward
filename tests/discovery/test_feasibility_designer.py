"""Unit tests for the Feasibility Designer orchestrator (Issue #221).

Tests the dialogue loop between Tech Lead Agent and Risk Agent.
Uses mock agents — no real LLM calls.
"""

import pytest

from src.discovery.agents.feasibility_designer import (
    DialogueTurn,
    FeasibilityDesigner,
    FeasibilityDesignerConfig,
    FeasibilityResult,
)
from src.discovery.agents.risk_agent import RiskAgent
from src.discovery.agents.tech_lead_agent import TechLeadAgent
from src.discovery.models.enums import FeasibilityAssessment


# ============================================================================
# Helpers
# ============================================================================


class MockTechLead:
    """Mock Tech Lead that returns predetermined responses."""

    def __init__(self, responses):
        """responses: list of dicts, consumed in order."""
        self._responses = list(responses)
        self._call_count = 0

    def evaluate_feasibility(self, **kwargs):
        return self._next_response()

    def revise_approach(self, **kwargs):
        return self._next_response()

    def _next_response(self):
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


class MockRiskAgent:
    """Mock Risk Agent that returns predetermined responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._call_count = 0

    def evaluate_risks(self, **kwargs):
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


def _feasible_approach(**overrides):
    defaults = {
        "feasibility_assessment": "feasible",
        "approach": "Consolidate billing forms",
        "effort_estimate": "2 weeks",
        "dependencies": "Payment tests",
        "acceptance_criteria": "All billing flows unified",
        "evidence_ids": ["conv_001"],
        "confidence": "high",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    defaults.update(overrides)
    return defaults


def _infeasible_approach(**overrides):
    defaults = {
        "feasibility_assessment": "infeasible",
        "approach": "",
        "effort_estimate": "",
        "dependencies": "",
        "acceptance_criteria": "",
        "infeasibility_reason": "Would require complete rewrite",
        "constraints_identified": ["Legacy system", "No team capacity"],
        "confidence": "high",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    defaults.update(overrides)
    return defaults


def _low_risk(**overrides):
    defaults = {
        "risks": [
            {"description": "Minor CSS issue", "severity": "low", "mitigation": "Visual tests"},
        ],
        "overall_risk_level": "low",
        "rollout_concerns": "None",
        "regression_potential": "Low",
        "test_scope_estimate": "20 tests",
        "token_usage": {"prompt_tokens": 80, "completion_tokens": 60, "total_tokens": 140},
    }
    defaults.update(overrides)
    return defaults


def _high_risk(**overrides):
    defaults = {
        "risks": [
            {"description": "No rollback plan", "severity": "critical", "mitigation": "Feature flags"},
            {"description": "Stripe webhook handling differs", "severity": "high", "mitigation": "Integration tests"},
        ],
        "overall_risk_level": "high",
        "rollout_concerns": "Revenue impact",
        "regression_potential": "High",
        "test_scope_estimate": "50 tests",
        "token_usage": {"prompt_tokens": 80, "completion_tokens": 60, "total_tokens": 140},
    }
    defaults.update(overrides)
    return defaults


def _make_solution_brief():
    return {
        "proposed_solution": "Consolidate billing forms",
        "experiment_plan": "A/B test",
        "success_metrics": "15% fewer support contacts",
        "build_experiment_decision": "build_slice_and_experiment",
        "evidence": [{"source_type": "intercom", "source_id": "conv_001"}],
    }


def _make_opportunity_brief():
    return {
        "opportunity_id": "opp_billing",
        "problem_statement": "Users can't navigate billing",
        "counterfactual": "15-20% fewer contacts",
        "affected_area": "billing",
    }


# ============================================================================
# Dialogue loop: convergence scenarios
# ============================================================================


class TestDialogueLoop:
    def test_feasible_converges_round_1(self):
        """Feasible + low risk → converges in 1 round."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_feasible_approach()]),
            risk_agent=MockRiskAgent([_low_risk()]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is True
        assert result.total_rounds == 1
        assert len(result.dialogue_history) == 2  # tech_lead + risk_agent

    def test_infeasible_exits_early(self):
        """Infeasible assessment → exits before Risk Agent call."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_infeasible_approach()]),
            risk_agent=MockRiskAgent([]),  # Should never be called
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is False
        assert result.total_rounds == 1
        assert len(result.dialogue_history) == 1  # Only tech_lead

    def test_high_risk_triggers_revision(self):
        """High risk → Tech Lead revises → low risk → converges in round 2."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(),   # Round 1: initial
                _feasible_approach(approach="Revised with feature flags"),  # Round 2: revision
            ]),
            risk_agent=MockRiskAgent([
                _high_risk(),   # Round 1: high risk
                _low_risk(),    # Round 2: now low risk
            ]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is True
        assert result.total_rounds == 2
        assert len(result.dialogue_history) == 4  # 2 tech_lead + 2 risk_agent

    def test_forced_convergence_after_max_rounds(self):
        """Risk stays high through all rounds → forced convergence."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(),
                _feasible_approach(),
                _feasible_approach(),
            ]),
            risk_agent=MockRiskAgent([
                _high_risk(),
                _high_risk(),
                _high_risk(),
            ]),
            config=FeasibilityDesignerConfig(max_rounds=3),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is True  # Forced convergence still marks feasible
        assert result.total_rounds == 3
        assert len(result.dialogue_history) == 6

    def test_medium_risk_converges(self):
        """Medium risk is acceptable — converges in round 1."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_feasible_approach()]),
            risk_agent=MockRiskAgent([_low_risk(overall_risk_level="medium")]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is True
        assert result.total_rounds == 1

    def test_infeasible_in_round_2(self):
        """Feasible initially, then becomes infeasible after revision."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(),
                _infeasible_approach(),  # Revision concludes infeasible
            ]),
            risk_agent=MockRiskAgent([
                _high_risk(),
            ]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is False
        assert result.total_rounds == 2

    def test_needs_revision_with_low_risk_does_not_converge(self):
        """needs_revision + low risk should NOT converge — loop continues.

        The Tech Lead must produce a "feasible" assessment (with filled fields)
        for convergence. A "needs_revision" with empty approach/effort would
        fail TechnicalSpec validation if we built a spec from it.
        """
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(feasibility_assessment="needs_revision"),  # Round 1: not feasible yet
                _feasible_approach(),  # Round 2: now feasible
            ]),
            risk_agent=MockRiskAgent([
                _low_risk(),   # Round 1: risk is low, but assessment isn't feasible
                _low_risk(),   # Round 2: risk still low, assessment now feasible → converge
            ]),
            config=FeasibilityDesignerConfig(max_rounds=3),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is True
        assert result.total_rounds == 2  # Did NOT converge in round 1

    def test_needs_revision_forced_convergence_is_infeasible(self):
        """If needs_revision persists through all rounds, forced convergence
        marks it infeasible rather than producing a broken TechnicalSpec."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(feasibility_assessment="needs_revision"),
                _feasible_approach(feasibility_assessment="needs_revision"),
                _feasible_approach(feasibility_assessment="needs_revision"),
            ]),
            risk_agent=MockRiskAgent([
                _low_risk(),
                _low_risk(),
                _low_risk(),
            ]),
            config=FeasibilityDesignerConfig(max_rounds=3),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.is_feasible is False
        assert result.total_rounds == 3


# ============================================================================
# Token tracking
# ============================================================================


class TestTokenTracking:
    def test_tokens_accumulated_across_rounds(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(),
                _feasible_approach(),
            ]),
            risk_agent=MockRiskAgent([
                _high_risk(),
                _low_risk(),
            ]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        # 2 tech_lead calls (150 each) + 2 risk calls (140 each) = 580
        assert result.token_usage["total_tokens"] == 580
        assert result.token_usage["prompt_tokens"] == 360
        assert result.token_usage["completion_tokens"] == 220

    def test_tokens_for_single_round(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_feasible_approach()]),
            risk_agent=MockRiskAgent([_low_risk()]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.token_usage["total_tokens"] == 290  # 150 + 140


# ============================================================================
# Dialogue history
# ============================================================================


class TestDialogueHistory:
    def test_dialogue_turns_recorded(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_feasible_approach()]),
            risk_agent=MockRiskAgent([_low_risk()]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert len(result.dialogue_history) == 2
        assert result.dialogue_history[0].agent == "tech_lead"
        assert result.dialogue_history[0].role == "assessment"
        assert result.dialogue_history[0].round_number == 1
        assert result.dialogue_history[1].agent == "risk_agent"
        assert result.dialogue_history[1].role == "risk_evaluation"

    def test_revision_turns_marked_correctly(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([
                _feasible_approach(),
                _feasible_approach(),
            ]),
            risk_agent=MockRiskAgent([
                _high_risk(),
                _low_risk(),
            ]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        assert result.dialogue_history[0].role == "assessment"
        assert result.dialogue_history[2].role == "revision"
        assert result.dialogue_history[2].round_number == 2


# ============================================================================
# Checkpoint building
# ============================================================================


class TestBuildCheckpointArtifacts:
    def test_all_feasible(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation=_low_risk(),
                total_rounds=1,
                token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)

        assert len(checkpoint["specs"]) == 1
        assert len(checkpoint["infeasible_solutions"]) == 0
        assert checkpoint["feasibility_metadata"]["solutions_assessed"] == 1
        assert checkpoint["feasibility_metadata"]["feasible_count"] == 1
        assert checkpoint["feasibility_metadata"]["infeasible_count"] == 0

    def test_all_infeasible(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=False,
                assessment=_infeasible_approach(),
                total_rounds=1,
                token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)

        assert len(checkpoint["specs"]) == 0
        assert len(checkpoint["infeasible_solutions"]) == 1
        assert checkpoint["infeasible_solutions"][0]["feasibility_assessment"] == "infeasible"
        assert checkpoint["infeasible_solutions"][0]["infeasibility_reason"] == "Would require complete rewrite"

    def test_mixed_feasible_and_infeasible(self):
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation=_low_risk(),
                total_rounds=1,
                token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            ),
            FeasibilityResult(
                opportunity_id="opp_2",
                is_feasible=False,
                assessment=_infeasible_approach(),
                total_rounds=1,
                token_usage={"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)

        assert checkpoint["feasibility_metadata"]["solutions_assessed"] == 2
        assert checkpoint["feasibility_metadata"]["feasible_count"] == 1
        assert checkpoint["feasibility_metadata"]["infeasible_count"] == 1
        assert checkpoint["feasibility_metadata"]["total_dialogue_rounds"] == 2
        assert checkpoint["feasibility_metadata"]["total_token_usage"]["total_tokens"] == 270

    def test_spec_structure(self):
        """Built specs have the required TechnicalSpec fields."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_billing",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation=_low_risk(),
                total_rounds=1,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)
        spec = checkpoint["specs"][0]

        assert spec["opportunity_id"] == "opp_billing"
        assert spec["approach"] == "Consolidate billing forms"
        assert spec["effort_estimate"] == "2 weeks"
        assert spec["dependencies"] == "Payment tests"
        assert spec["acceptance_criteria"] == "All billing flows unified"
        assert len(spec["risks"]) >= 1

    def test_spec_risks_from_risk_agent(self):
        """Risks in the spec come from Risk Agent output."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation=_high_risk(),
                total_rounds=1,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)
        spec = checkpoint["specs"][0]

        assert len(spec["risks"]) == 2
        assert spec["risks"][0]["description"] == "No rollback plan"
        assert spec["risks"][0]["severity"] == "critical"
        assert spec["risks"][0]["mitigation"] == "Feature flags"

    def test_spec_fallback_risks_when_no_risk_eval(self):
        """If no risk evaluation, spec gets a fallback risk entry."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation=None,
                total_rounds=1,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)
        spec = checkpoint["specs"][0]

        assert len(spec["risks"]) == 1
        assert "No specific risks" in spec["risks"][0]["description"]

    def test_infeasible_solution_structure(self):
        """Built infeasible records have the expected fields."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_2",
                is_feasible=False,
                assessment=_infeasible_approach(),
                total_rounds=1,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)
        inf = checkpoint["infeasible_solutions"][0]

        assert inf["opportunity_id"] == "opp_2"
        assert inf["feasibility_assessment"] == "infeasible"
        assert inf["infeasibility_reason"] == "Would require complete rewrite"
        assert len(inf["constraints_identified"]) == 2

    def test_empty_results(self):
        """No results → empty checkpoint with zero counts."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        checkpoint = designer.build_checkpoint_artifacts([])

        assert len(checkpoint["specs"]) == 0
        assert len(checkpoint["infeasible_solutions"]) == 0
        assert checkpoint["feasibility_metadata"]["solutions_assessed"] == 0

    def test_risk_items_as_strings_handled(self):
        """Risk Agent returning string items (not dicts) still works."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation={
                    "risks": ["Some string risk"],
                    "overall_risk_level": "low",
                },
                total_rounds=1,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)
        spec = checkpoint["specs"][0]

        assert len(spec["risks"]) == 1
        assert spec["risks"][0]["description"] == "Some string risk"
        assert spec["risks"][0]["severity"] == "medium"

    def test_extra_risk_eval_fields_passed_to_spec(self):
        """rollout_concerns, regression_potential, test_scope_estimate, overall_risk_level."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
        )

        results = [
            FeasibilityResult(
                opportunity_id="opp_1",
                is_feasible=True,
                assessment=_feasible_approach(),
                risk_evaluation={
                    "risks": [{"description": "Risk", "severity": "low", "mitigation": "Test"}],
                    "overall_risk_level": "low",
                    "rollout_concerns": "Some concern",
                    "regression_potential": "Low",
                    "test_scope_estimate": "20 tests",
                },
                total_rounds=1,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            ),
        ]

        checkpoint = designer.build_checkpoint_artifacts(results)
        spec = checkpoint["specs"][0]

        assert spec["rollout_concerns"] == "Some concern"
        assert spec["regression_potential"] == "Low"
        assert spec["test_scope_estimate"] == "20 tests"
        assert spec["overall_risk_level"] == "low"


# ============================================================================
# Config
# ============================================================================


class TestConfig:
    def test_default_config(self):
        config = FeasibilityDesignerConfig()
        assert config.max_rounds == 3
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.3

    def test_custom_max_rounds(self):
        config = FeasibilityDesignerConfig(max_rounds=5)
        assert config.max_rounds == 5

    def test_opportunity_id_from_brief(self):
        """opportunity_id is taken from opportunity_brief."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_feasible_approach()]),
            risk_agent=MockRiskAgent([_low_risk()]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief={"opportunity_id": "opp_custom", "affected_area": "billing"},
            prior_checkpoints=[],
        )

        assert result.opportunity_id == "opp_custom"

    def test_opportunity_id_fallback_to_affected_area(self):
        """Falls back to affected_area when opportunity_id missing."""
        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([_feasible_approach()]),
            risk_agent=MockRiskAgent([_low_risk()]),
        )

        result = designer.assess_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief={"affected_area": "billing"},
            prior_checkpoints=[],
        )

        assert result.opportunity_id == "billing"


# ============================================================================
# validate_input — FeasibilityDesigner (Issue #276)
# ============================================================================

import json
from unittest.mock import MagicMock

from src.discovery.agents.feasibility_designer import FeasibilityDesigner


def _make_validation_llm_response(content_dict, prompt_tokens=150, completion_tokens=120):
    """Create mock OpenAI response for validate_input tests."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    mock_response.usage.total_tokens = prompt_tokens + completion_tokens
    return mock_response


def _make_validate_feasibility_designer(response_dict, **response_kwargs):
    """Create a FeasibilityDesigner for validate_input tests."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_validation_llm_response(
        response_dict, **response_kwargs
    )
    return FeasibilityDesigner(
        tech_lead=MockTechLead([]),
        risk_agent=MockRiskAgent([]),
        openai_client=mock_openai,
    )


def _make_solutions(count, prefix="Area"):
    """Build N minimal solution dicts."""
    return [
        {"proposed_solution": f"Fix {prefix} {i}", "success_metrics": f"Metric {i}"}
        for i in range(count)
    ]


def _make_briefs_for_feasibility(count, prefix="Area"):
    """Build N minimal brief dicts with affected_area."""
    return [
        {"affected_area": f"{prefix} {i}", "problem_statement": f"Problem {i}"}
        for i in range(count)
    ]


class TestFeasibilityDesignerValidateInput:
    """FeasibilityDesigner.validate_input() — Issue #276."""

    def test_empty_input_no_llm_call(self):
        """Empty solutions → empty result, no LLM call."""
        designer = _make_validate_feasibility_designer({"accepted_items": [], "rejected_items": []})
        result = designer.validate_input([], [])

        assert result.accepted_items == []
        assert result.rejected_items == []
        assert result.token_usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        designer.client.chat.completions.create.assert_not_called()

    def test_all_accepted(self):
        """LLM accepts all solutions."""
        solutions = _make_solutions(3)
        briefs = _make_briefs_for_feasibility(3)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0", "Area 1", "Area 2"],
            "rejected_items": [],
        })
        result = designer.validate_input(solutions, briefs)

        assert sorted(result.accepted_items) == ["Area 0", "Area 1", "Area 2"]
        assert result.rejected_items == []

    def test_all_rejected(self):
        """LLM rejects all solutions."""
        solutions = _make_solutions(2)
        briefs = _make_briefs_for_feasibility(2)
        designer = _make_validate_feasibility_designer({
            "accepted_items": [],
            "rejected_items": [
                {"item_id": "Area 0", "rejection_reason": "Vague", "rejecting_agent": "tech_lead"},
                {"item_id": "Area 1", "rejection_reason": "No metrics", "rejecting_agent": "tech_lead"},
            ],
        })
        result = designer.validate_input(solutions, briefs)

        assert result.accepted_items == []
        assert len(result.rejected_items) == 2

    def test_mixed_accepted_rejected(self):
        """Some accepted, some rejected."""
        solutions = _make_solutions(4)
        briefs = _make_briefs_for_feasibility(4)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0", "Area 3"],
            "rejected_items": [
                {"item_id": "Area 1", "rejection_reason": "Missing plan", "rejecting_agent": "tech_lead"},
                {"item_id": "Area 2", "rejection_reason": "Contradictory", "rejecting_agent": "tech_lead"},
            ],
        })
        result = designer.validate_input(solutions, briefs)

        assert sorted(result.accepted_items) == ["Area 0", "Area 3"]
        assert len(result.rejected_items) == 2

    def test_single_item_accepted(self):
        """Single solution accepted."""
        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0"],
            "rejected_items": [],
        })
        result = designer.validate_input(solutions, briefs)

        assert result.accepted_items == ["Area 0"]

    def test_single_item_rejected(self):
        """Single solution rejected."""
        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": [],
            "rejected_items": [
                {"item_id": "Area 0", "rejection_reason": "Vague solution", "rejecting_agent": "tech_lead"},
            ],
        })
        result = designer.validate_input(solutions, briefs)

        assert result.accepted_items == []
        assert len(result.rejected_items) == 1

    def test_token_usage_populated(self):
        """Token usage from LLM response is returned."""
        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer(
            {"accepted_items": ["Area 0"], "rejected_items": []},
            prompt_tokens=300,
            completion_tokens=200,
        )
        result = designer.validate_input(solutions, briefs)

        assert result.token_usage["prompt_tokens"] == 300
        assert result.token_usage["completion_tokens"] == 200
        assert result.token_usage["total_tokens"] == 500

    def test_json_decode_error_accepts_all(self):
        """Full JSON parse failure → accept all solutions."""
        solutions = _make_solutions(3)
        briefs = _make_briefs_for_feasibility(3)

        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "{{invalid json"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_openai.chat.completions.create.return_value = mock_response

        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
            openai_client=mock_openai,
        )
        result = designer.validate_input(solutions, briefs)

        assert sorted(result.accepted_items) == ["Area 0", "Area 1", "Area 2"]
        assert result.rejected_items == []

    def test_null_content_accepts_all(self):
        """None LLM content → accept all."""
        solutions = _make_solutions(2)
        briefs = _make_briefs_for_feasibility(2)

        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 50
        mock_openai.chat.completions.create.return_value = mock_response

        designer = FeasibilityDesigner(
            tech_lead=MockTechLead([]),
            risk_agent=MockRiskAgent([]),
            openai_client=mock_openai,
        )
        result = designer.validate_input(solutions, briefs)

        assert sorted(result.accepted_items) == ["Area 0", "Area 1"]

    def test_partial_parse_unmentioned_accepted(self):
        """Items not mentioned in response → accepted."""
        solutions = _make_solutions(4)
        briefs = _make_briefs_for_feasibility(4)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0"],
            "rejected_items": [
                {"item_id": "Area 1", "rejection_reason": "Bad", "rejecting_agent": "tech_lead"},
            ],
        })
        result = designer.validate_input(solutions, briefs)

        # Area 2, Area 3 unmentioned → accepted
        assert "Area 0" in result.accepted_items
        assert "Area 2" in result.accepted_items
        assert "Area 3" in result.accepted_items
        assert len(result.rejected_items) == 1

    def test_extra_fields_ignored(self):
        """Extra fields in LLM response are ignored."""
        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0"],
            "rejected_items": [],
            "notes": "extra field",
        })
        result = designer.validate_input(solutions, briefs)

        assert result.accepted_items == ["Area 0"]

    def test_rejection_with_suggested_improvement(self):
        """Rejection includes suggested_improvement."""
        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": [],
            "rejected_items": [
                {
                    "item_id": "Area 0",
                    "rejection_reason": "No experiment plan",
                    "rejecting_agent": "tech_lead",
                    "suggested_improvement": "Add concrete experiment plan with metrics",
                },
            ],
        })
        result = designer.validate_input(solutions, briefs)

        assert result.rejected_items[0].suggested_improvement == "Add concrete experiment plan with metrics"

    def test_rejection_without_suggested_improvement(self):
        """Rejection without optional suggested_improvement."""
        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": [],
            "rejected_items": [
                {"item_id": "Area 0", "rejection_reason": "Vague", "rejecting_agent": "tech_lead"},
            ],
        })
        result = designer.validate_input(solutions, briefs)

        assert result.rejected_items[0].suggested_improvement is None

    def test_item_id_from_parent_brief_affected_area(self):
        """Item IDs come from briefs[i]['affected_area'], not solutions."""
        solutions = [{"proposed_solution": "Fix the thing"}]
        briefs = [{"affected_area": "Checkout page", "problem_statement": "Slow checkout"}]
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Checkout page"],
            "rejected_items": [],
        })
        result = designer.validate_input(solutions, briefs)

        assert "Checkout page" in result.accepted_items

    def test_more_solutions_than_briefs_fallback_id(self):
        """Solutions outnumber briefs → extra items get fallback IDs."""
        solutions = _make_solutions(3)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": [],
            "rejected_items": [],
        })
        result = designer.validate_input(solutions, briefs)

        # All 3 unmentioned → accepted
        assert "Area 0" in result.accepted_items
        assert "solution_1" in result.accepted_items
        assert "solution_2" in result.accepted_items

    def test_token_usage_zero_when_empty(self):
        """Empty input → zero token usage."""
        designer = _make_validate_feasibility_designer({"accepted_items": [], "rejected_items": []})
        result = designer.validate_input([], [])

        assert result.token_usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def test_correct_prompts_used(self):
        """Verify system prompt is INPUT_VALIDATION_FEASIBILITY_SYSTEM."""
        from src.discovery.agents.prompts import INPUT_VALIDATION_FEASIBILITY_SYSTEM

        solutions = _make_solutions(1)
        briefs = _make_briefs_for_feasibility(1)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0"],
            "rejected_items": [],
        })
        designer.validate_input(solutions, briefs)

        call_args = designer.client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        assert messages[0]["content"] == INPUT_VALIDATION_FEASIBILITY_SYSTEM

    def test_empty_rejected_all_accepted(self):
        """Empty rejected_items, all in accepted."""
        solutions = _make_solutions(2)
        briefs = _make_briefs_for_feasibility(2)
        designer = _make_validate_feasibility_designer({
            "accepted_items": ["Area 0", "Area 1"],
            "rejected_items": [],
        })
        result = designer.validate_input(solutions, briefs)

        assert sorted(result.accepted_items) == ["Area 0", "Area 1"]

    def test_empty_accepted_all_rejected(self):
        """Empty accepted_items, all in rejected."""
        solutions = _make_solutions(2)
        briefs = _make_briefs_for_feasibility(2)
        designer = _make_validate_feasibility_designer({
            "accepted_items": [],
            "rejected_items": [
                {"item_id": "Area 0", "rejection_reason": "Bad", "rejecting_agent": "tech_lead"},
                {"item_id": "Area 1", "rejection_reason": "Bad", "rejecting_agent": "tech_lead"},
            ],
        })
        result = designer.validate_input(solutions, briefs)

        assert result.accepted_items == []
        assert len(result.rejected_items) == 2
