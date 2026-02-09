"""Unit tests for the Tech Lead Agent (Issue #221).

Tests feasibility evaluation: solution briefs → technical assessment.
Uses mock OpenAI client throughout — no real LLM calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.tech_lead_agent import (
    TechLeadAgent,
    TechLeadAgentConfig,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_llm_response(content_dict):
    """Create mock OpenAI ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 200
    mock_response.usage.completion_tokens = 150
    mock_response.usage.total_tokens = 350
    return mock_response


def _make_agent(response_dict):
    """Create a TechLeadAgent with a mocked OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(
        response_dict
    )
    return TechLeadAgent(openai_client=mock_client)


def _make_solution_brief(**overrides):
    defaults = {
        "proposed_solution": "Consolidate billing forms into shared component",
        "experiment_plan": "A/B test consolidated flow for enterprise segment",
        "success_metrics": "15% reduction in billing support contacts",
        "build_experiment_decision": "build_slice_and_experiment",
        "evidence": [{"source_type": "intercom", "source_id": "conv_001"}],
    }
    defaults.update(overrides)
    return defaults


def _make_opportunity_brief(**overrides):
    defaults = {
        "problem_statement": "Users can't navigate billing workflow",
        "counterfactual": "If resolved, 15-20% fewer support contacts",
        "affected_area": "billing",
        "explorer_coverage": "200 conversations reviewed",
    }
    defaults.update(overrides)
    return defaults


def _feasible_response(**overrides):
    defaults = {
        "feasibility_assessment": "feasible",
        "approach": "Consolidate three billing form implementations into shared component",
        "effort_estimate": "2 weeks +/- 3 days",
        "dependencies": "Payment module test coverage must be added first",
        "acceptance_criteria": "All billing flows use single implementation",
        "evidence_ids": ["conv_001"],
        "confidence": "high",
    }
    defaults.update(overrides)
    return defaults


def _infeasible_response(**overrides):
    defaults = {
        "feasibility_assessment": "infeasible",
        "approach": "",
        "effort_estimate": "",
        "dependencies": "",
        "acceptance_criteria": "",
        "infeasibility_reason": "Would require rewriting the entire payment module",
        "constraints_identified": ["Legacy Stripe integration", "No test coverage"],
        "confidence": "high",
    }
    defaults.update(overrides)
    return defaults


# ============================================================================
# evaluate_feasibility: happy path
# ============================================================================


class TestEvaluateFeasibility:
    def test_feasible_assessment(self):
        agent = _make_agent(_feasible_response())

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["feasibility_assessment"] == "feasible"
        assert result["approach"] != ""
        assert result["effort_estimate"] != ""
        assert result["confidence"] == "high"

    def test_infeasible_assessment(self):
        agent = _make_agent(_infeasible_response())

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["feasibility_assessment"] == "infeasible"
        assert result["infeasibility_reason"] != ""
        assert len(result["constraints_identified"]) == 2

    def test_needs_revision_assessment(self):
        agent = _make_agent(
            _feasible_response(feasibility_assessment="needs_revision")
        )

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["feasibility_assessment"] == "needs_revision"

    def test_token_usage_tracked(self):
        agent = _make_agent(_feasible_response())

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["token_usage"]["total_tokens"] == 350
        assert result["token_usage"]["prompt_tokens"] == 200
        assert result["token_usage"]["completion_tokens"] == 150

    def test_dialogue_history_passed_to_llm(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            _feasible_response()
        )

        agent = TechLeadAgent(openai_client=mock_client)
        history = [
            {
                "round_number": 1,
                "agent": "tech_lead",
                "role": "assessment",
                "content": {"approach": "v1"},
            }
        ]

        agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=history,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_msg = messages[-1]["content"]
        assert "v1" in user_msg

    def test_prior_checkpoints_passed_to_llm(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            _feasible_response()
        )

        agent = TechLeadAgent(openai_client=mock_client)
        prior = [{"stage": "exploration", "artifacts": {"agent_name": "codebase"}}]

        agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=prior,
            dialogue_history=[],
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_msg = messages[-1]["content"]
        assert "codebase" in user_msg

    def test_no_usage_object_defaults_to_zero(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(_feasible_response())
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response

        agent = TechLeadAgent(openai_client=mock_client)

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["token_usage"]["total_tokens"] == 0


# ============================================================================
# revise_approach
# ============================================================================


class TestReviseApproach:
    def test_revision_after_risk_feedback(self):
        agent = _make_agent(
            _feasible_response(
                approach="Revised approach with feature flags for rollback"
            )
        )

        result = agent.revise_approach(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            original_approach=_feasible_response(),
            risk_feedback={
                "risks": [{"description": "No rollback plan", "severity": "high"}],
                "overall_risk_level": "high",
            },
            dialogue_history=[],
        )

        assert result["feasibility_assessment"] == "feasible"
        assert "feature flags" in result["approach"]

    def test_revision_can_become_infeasible(self):
        agent = _make_agent(_infeasible_response())

        result = agent.revise_approach(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            original_approach=_feasible_response(),
            risk_feedback={
                "risks": [{"description": "Critical blocking issue", "severity": "critical"}],
                "overall_risk_level": "critical",
            },
            dialogue_history=[],
        )

        assert result["feasibility_assessment"] == "infeasible"

    def test_revision_tracks_tokens(self):
        agent = _make_agent(_feasible_response())

        result = agent.revise_approach(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            original_approach=_feasible_response(),
            risk_feedback={"risks": [], "overall_risk_level": "medium"},
            dialogue_history=[],
        )

        assert result["token_usage"]["total_tokens"] == 350


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    def test_missing_feasibility_assessment_raises(self):
        agent = _make_agent({"approach": "Some approach"})

        with pytest.raises(ValueError, match="missing required 'feasibility_assessment'"):
            agent.evaluate_feasibility(
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                prior_checkpoints=[],
                dialogue_history=[],
            )

    def test_missing_feasibility_assessment_in_revision_raises(self):
        agent = _make_agent({"approach": "Some approach"})

        with pytest.raises(ValueError, match="missing required 'feasibility_assessment'"):
            agent.revise_approach(
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                original_approach=_feasible_response(),
                risk_feedback={"risks": [], "overall_risk_level": "low"},
                dialogue_history=[],
            )

    def test_malformed_json_raises(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 0
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 0
        mock_client.chat.completions.create.return_value = mock_response

        agent = TechLeadAgent(openai_client=mock_client)

        with pytest.raises(json.JSONDecodeError):
            agent.evaluate_feasibility(
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                prior_checkpoints=[],
                dialogue_history=[],
            )

    def test_unknown_assessment_defaults_to_needs_revision(self):
        agent = _make_agent(
            _feasible_response(feasibility_assessment="maybe_feasible")
        )

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["feasibility_assessment"] == "needs_revision"

    def test_llm_exception_propagates(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        agent = TechLeadAgent(openai_client=mock_client)

        with pytest.raises(RuntimeError, match="API down"):
            agent.evaluate_feasibility(
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                prior_checkpoints=[],
                dialogue_history=[],
            )

    def test_missing_optional_fields_default(self):
        """Response with only feasibility_assessment still returns all keys."""
        agent = _make_agent({"feasibility_assessment": "feasible"})

        result = agent.evaluate_feasibility(
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            dialogue_history=[],
        )

        assert result["approach"] == ""
        assert result["effort_estimate"] == ""
        assert result["dependencies"] == ""
        assert result["acceptance_criteria"] == ""
        assert result["evidence_ids"] == []
        assert result["confidence"] == "medium"


# ============================================================================
# Config
# ============================================================================


class TestConfig:
    def test_default_config(self):
        config = TechLeadAgentConfig()
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.3

    def test_custom_config(self):
        config = TechLeadAgentConfig(model="gpt-4o", temperature=0.1)
        agent = TechLeadAgent(openai_client=MagicMock(), config=config)
        assert agent.config.model == "gpt-4o"
        assert agent.config.temperature == 0.1
