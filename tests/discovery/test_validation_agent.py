"""Unit tests for the Validation Agent (Issue #220).

Tests the evaluation logic: proposed solutions → assessment + experiment.
Uses mock OpenAI client throughout — no real LLM calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.validation_agent import (
    ValidationAgent,
    ValidationAgentConfig,
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
    mock_response.usage.prompt_tokens = 150
    mock_response.usage.completion_tokens = 100
    mock_response.usage.total_tokens = 250
    return mock_response


def _make_agent(response_dict):
    """Create a ValidationAgent with a mocked OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(
        response_dict
    )
    return ValidationAgent(openai_client=mock_client)


def _make_proposal(**overrides):
    """Build a typical PM proposal dict."""
    defaults = {
        "proposed_solution": "Simplify the scheduling wizard to 2 steps",
        "experiment_plan": "A/B test with 10% of users for 2 weeks",
        "success_metrics": "Scheduling completion rate +15%",
        "build_experiment_decision": "build_slice_and_experiment",
        "decision_rationale": "Evidence is strong enough to build minimal version",
        "evidence_ids": ["conv_001", "conv_002"],
        "confidence": "high",
    }
    defaults.update(overrides)
    return defaults


def _make_opportunity_brief(**overrides):
    """Build a typical OpportunityBrief dict."""
    defaults = {
        "problem_statement": "Users confused by scheduling UI across multiple flows",
        "counterfactual": "If we simplified scheduling, we'd expect 15% fewer tickets",
        "affected_area": "scheduling",
        "explorer_coverage": "180 conversations reviewed over 14 days",
    }
    defaults.update(overrides)
    return defaults


# ============================================================================
# Happy path
# ============================================================================


class TestEvaluateSolution:
    """Core evaluation logic: proposal → assessment."""

    def test_approve_assessment(self):
        """Validation Agent approves a sound proposal."""
        agent = _make_agent(
            {
                "assessment": "approve",
                "critique": "Well-scoped solution with clear metrics",
                "experiment_suggestion": "A/B test as proposed",
                "success_criteria": "15% improvement in completion rate",
                "challenge_reason": "",
            }
        )

        result = agent.evaluate_solution(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["assessment"] == "approve"
        assert result["critique"] != ""
        assert result["challenge_reason"] == ""

    def test_challenge_assessment(self):
        """Validation Agent challenges a build_direct decision."""
        agent = _make_agent(
            {
                "assessment": "challenge",
                "critique": "build_direct is premature without user validation",
                "experiment_suggestion": "Run 5 user interviews first",
                "success_criteria": "3/5 users confirm the problem matches",
                "challenge_reason": "No evidence that the proposed fix addresses root cause",
            }
        )

        result = agent.evaluate_solution(
            proposed_solution=_make_proposal(
                build_experiment_decision="build_direct"
            ),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["assessment"] == "challenge"
        assert result["challenge_reason"] != ""

    def test_request_revision_assessment(self):
        """Validation Agent requests revision for vague proposal."""
        agent = _make_agent(
            {
                "assessment": "request_revision",
                "critique": "Solution is too broad, needs specific components",
                "experiment_suggestion": "Can't suggest experiment without clearer solution",
                "success_criteria": "",
                "challenge_reason": "",
            }
        )

        result = agent.evaluate_solution(
            proposed_solution=_make_proposal(
                proposed_solution="Make scheduling better"
            ),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["assessment"] == "request_revision"

    def test_token_usage_tracked(self):
        """Token usage from LLM response is captured in result."""
        agent = _make_agent(
            {
                "assessment": "approve",
                "critique": "Good",
                "experiment_suggestion": "Test",
                "success_criteria": "Pass",
                "challenge_reason": "",
            }
        )

        result = agent.evaluate_solution(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["token_usage"]["total_tokens"] == 250

    def test_dialogue_history_passed_to_llm(self):
        """Dialogue history is included in the LLM call."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {
                "assessment": "approve",
                "critique": "Revised proposal addresses concerns",
                "experiment_suggestion": "A/B test",
                "success_criteria": "Metric improvement",
                "challenge_reason": "",
            }
        )

        agent = ValidationAgent(openai_client=mock_client)
        history = [
            {
                "round_number": 1,
                "agent": "opportunity_pm",
                "role": "proposal",
                "content": {"proposed_solution": "v1"},
            }
        ]

        agent.evaluate_solution(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=history,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_msg = messages[-1]["content"]
        assert "v1" in user_msg


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    """Graceful failure on malformed LLM responses."""

    def test_missing_assessment_raises(self):
        """Response without 'assessment' key raises ValueError."""
        agent = _make_agent({"critique": "Good stuff"})

        with pytest.raises(ValueError, match="missing required 'assessment'"):
            agent.evaluate_solution(
                proposed_solution=_make_proposal(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )

    def test_malformed_json_raises(self):
        """Non-JSON LLM response raises."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 0
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 0
        mock_client.chat.completions.create.return_value = mock_response

        agent = ValidationAgent(openai_client=mock_client)

        with pytest.raises(json.JSONDecodeError):
            agent.evaluate_solution(
                proposed_solution=_make_proposal(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )

    def test_unknown_assessment_defaults_to_request_revision(self):
        """Unknown assessment value is normalized to request_revision."""
        agent = _make_agent(
            {
                "assessment": "maybe",
                "critique": "Not sure",
                "experiment_suggestion": "",
                "success_criteria": "",
                "challenge_reason": "",
            }
        )

        result = agent.evaluate_solution(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["assessment"] == "request_revision"

    def test_llm_exception_propagates(self):
        """OpenAI API exception propagates to caller."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        agent = ValidationAgent(openai_client=mock_client)

        with pytest.raises(RuntimeError, match="API down"):
            agent.evaluate_solution(
                proposed_solution=_make_proposal(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )


# ============================================================================
# Config
# ============================================================================


class TestConfig:
    """Configuration defaults and overrides."""

    def test_default_config(self):
        config = ValidationAgentConfig()
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.4

    def test_custom_config(self):
        config = ValidationAgentConfig(model="gpt-4o", temperature=0.2)
        agent = ValidationAgent(openai_client=MagicMock(), config=config)
        assert agent.config.model == "gpt-4o"
        assert agent.config.temperature == 0.2
