"""Unit tests for the Risk/QA Agent (Issue #221).

Tests risk evaluation: technical approach → risk assessment.
Uses mock OpenAI client throughout — no real LLM calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.risk_agent import (
    RiskAgent,
    RiskAgentConfig,
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
    mock_response.usage.prompt_tokens = 180
    mock_response.usage.completion_tokens = 120
    mock_response.usage.total_tokens = 300
    return mock_response


def _make_agent(response_dict):
    """Create a RiskAgent with a mocked OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(
        response_dict
    )
    return RiskAgent(openai_client=mock_client)


def _make_technical_approach(**overrides):
    defaults = {
        "feasibility_assessment": "feasible",
        "approach": "Consolidate billing forms into shared component",
        "effort_estimate": "2 weeks +/- 3 days",
        "dependencies": "Payment module test coverage",
        "acceptance_criteria": "All billing flows use single implementation",
    }
    defaults.update(overrides)
    return defaults


def _make_solution_brief(**overrides):
    defaults = {
        "proposed_solution": "Consolidate billing forms",
        "experiment_plan": "A/B test consolidated flow",
        "success_metrics": "15% reduction in billing support contacts",
        "build_experiment_decision": "build_slice_and_experiment",
    }
    defaults.update(overrides)
    return defaults


def _make_opportunity_brief(**overrides):
    defaults = {
        "problem_statement": "Users can't navigate billing workflow",
        "counterfactual": "If resolved, 15-20% fewer support contacts",
        "affected_area": "billing",
    }
    defaults.update(overrides)
    return defaults


def _low_risk_response(**overrides):
    defaults = {
        "risks": [
            {
                "description": "Minor CSS inconsistencies during migration",
                "severity": "low",
                "mitigation": "Visual regression tests",
            },
        ],
        "overall_risk_level": "low",
        "rollout_concerns": "None significant",
        "regression_potential": "Low — isolated to billing module",
        "test_scope_estimate": "~20 unit tests, 5 integration tests",
    }
    defaults.update(overrides)
    return defaults


def _high_risk_response(**overrides):
    defaults = {
        "risks": [
            {
                "description": "No rollback plan for payment state",
                "severity": "critical",
                "mitigation": "Implement feature flags with kill switch",
            },
            {
                "description": "Stripe webhook handling differs across implementations",
                "severity": "high",
                "mitigation": "Add integration tests for all webhook paths",
            },
        ],
        "overall_risk_level": "high",
        "rollout_concerns": "Payment failures could affect revenue",
        "regression_potential": "High — touches payment processing",
        "test_scope_estimate": "~50 unit tests, 15 integration tests, load test",
    }
    defaults.update(overrides)
    return defaults


# ============================================================================
# evaluate_risks: happy path
# ============================================================================


class TestEvaluateRisks:
    def test_low_risk_assessment(self):
        agent = _make_agent(_low_risk_response())

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["overall_risk_level"] == "low"
        assert len(result["risks"]) == 1
        assert result["risks"][0]["severity"] == "low"

    def test_high_risk_assessment(self):
        agent = _make_agent(_high_risk_response())

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["overall_risk_level"] == "high"
        assert len(result["risks"]) == 2

    def test_critical_risk_level(self):
        agent = _make_agent(_high_risk_response(overall_risk_level="critical"))

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["overall_risk_level"] == "critical"

    def test_medium_risk_level(self):
        agent = _make_agent(_low_risk_response(overall_risk_level="medium"))

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["overall_risk_level"] == "medium"

    def test_token_usage_tracked(self):
        agent = _make_agent(_low_risk_response())

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["token_usage"]["total_tokens"] == 300
        assert result["token_usage"]["prompt_tokens"] == 180

    def test_rollout_concerns_captured(self):
        agent = _make_agent(
            _high_risk_response(rollout_concerns="Payment failures during rollout")
        )

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert "Payment failures" in result["rollout_concerns"]

    def test_regression_potential_captured(self):
        agent = _make_agent(
            _low_risk_response(regression_potential="Low — isolated component")
        )

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert "isolated" in result["regression_potential"]

    def test_test_scope_estimate_captured(self):
        agent = _make_agent(
            _low_risk_response(test_scope_estimate="30 unit tests")
        )

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert "30" in result["test_scope_estimate"]

    def test_dialogue_history_passed_to_llm(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            _low_risk_response()
        )

        agent = RiskAgent(openai_client=mock_client)
        history = [
            {
                "round_number": 1,
                "agent": "tech_lead",
                "role": "assessment",
                "content": {"approach": "v1 approach"},
            }
        ]

        agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=history,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_msg = messages[-1]["content"]
        assert "v1 approach" in user_msg

    def test_no_usage_object_defaults_to_zero(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(_low_risk_response())
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response

        agent = RiskAgent(openai_client=mock_client)

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["token_usage"]["total_tokens"] == 0


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    def test_missing_risks_key_raises(self):
        agent = _make_agent({"overall_risk_level": "low"})

        with pytest.raises(ValueError, match="missing required 'risks'"):
            agent.evaluate_risks(
                technical_approach=_make_technical_approach(),
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )

    def test_malformed_json_raises(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 0
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 0
        mock_client.chat.completions.create.return_value = mock_response

        agent = RiskAgent(openai_client=mock_client)

        with pytest.raises(json.JSONDecodeError):
            agent.evaluate_risks(
                technical_approach=_make_technical_approach(),
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )

    def test_unknown_risk_level_defaults_to_medium(self):
        agent = _make_agent(
            _low_risk_response(overall_risk_level="catastrophic")
        )

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["overall_risk_level"] == "medium"

    def test_missing_optional_fields_default(self):
        """Response with only risks still returns all keys."""
        agent = _make_agent({"risks": [{"description": "Some risk"}]})

        result = agent.evaluate_risks(
            technical_approach=_make_technical_approach(),
            solution_brief=_make_solution_brief(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["rollout_concerns"] == ""
        assert result["regression_potential"] == ""
        assert result["test_scope_estimate"] == ""
        assert result["overall_risk_level"] == "medium"

    def test_llm_exception_propagates(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        agent = RiskAgent(openai_client=mock_client)

        with pytest.raises(RuntimeError, match="API down"):
            agent.evaluate_risks(
                technical_approach=_make_technical_approach(),
                solution_brief=_make_solution_brief(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )


# ============================================================================
# Config
# ============================================================================


class TestConfig:
    def test_default_config(self):
        config = RiskAgentConfig()
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.3

    def test_custom_config(self):
        config = RiskAgentConfig(model="gpt-4o", temperature=0.1)
        agent = RiskAgent(openai_client=MagicMock(), config=config)
        assert agent.config.model == "gpt-4o"
        assert agent.config.temperature == 0.1
