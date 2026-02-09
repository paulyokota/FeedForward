"""Unit tests for the Experience Agent (Issue #220).

Tests the evaluation logic: proposed solutions → experience direction.
Uses mock OpenAI client throughout — no real LLM calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.experience_agent import (
    ExperienceAgent,
    ExperienceAgentConfig,
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
    mock_response.usage.prompt_tokens = 120
    mock_response.usage.completion_tokens = 80
    mock_response.usage.total_tokens = 200
    return mock_response


def _make_agent(response_dict):
    """Create an ExperienceAgent with a mocked OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(
        response_dict
    )
    return ExperienceAgent(openai_client=mock_client)


def _make_proposal(**overrides):
    """Build a typical PM proposal dict."""
    defaults = {
        "proposed_solution": "Simplify the scheduling wizard to 2 steps",
        "experiment_plan": "A/B test with 10% of users for 2 weeks",
        "success_metrics": "Scheduling completion rate +15%",
        "build_experiment_decision": "build_slice_and_experiment",
    }
    defaults.update(overrides)
    return defaults


def _make_opportunity_brief(**overrides):
    """Build a typical OpportunityBrief dict."""
    defaults = {
        "problem_statement": "Users confused by scheduling UI across multiple flows",
        "counterfactual": "If we simplified scheduling, we'd expect 15% fewer tickets",
        "affected_area": "scheduling",
    }
    defaults.update(overrides)
    return defaults


# ============================================================================
# Happy path
# ============================================================================


class TestEvaluateExperience:
    """Core evaluation logic: proposal → experience direction."""

    def test_high_impact_full_engagement(self):
        """User-facing change gets full engagement depth."""
        agent = _make_agent(
            {
                "user_impact_level": "high",
                "experience_direction": "Redesign wizard: step 1 select content, step 2 confirm schedule. Add progress indicator. Error state for past dates.",
                "engagement_depth": "full",
                "notes": "Consider accessibility for date picker",
            }
        )

        result = agent.evaluate_experience(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["user_impact_level"] == "high"
        assert result["engagement_depth"] == "full"
        assert result["experience_direction"] != ""

    def test_backend_only_transparent_minimal(self):
        """Backend-only change gets transparent impact, minimal engagement."""
        agent = _make_agent(
            {
                "user_impact_level": "transparent",
                "experience_direction": "No user-facing changes needed",
                "engagement_depth": "minimal",
                "notes": "Improvement is transparent to users — performance gain only",
            }
        )

        result = agent.evaluate_experience(
            proposed_solution=_make_proposal(
                proposed_solution="Optimize database query for scheduling lookups"
            ),
            opportunity_brief=_make_opportunity_brief(
                problem_statement="Scheduling page loads slowly due to N+1 queries"
            ),
            dialogue_history=[],
        )

        assert result["user_impact_level"] == "transparent"
        assert result["engagement_depth"] == "minimal"

    def test_moderate_impact_partial_engagement(self):
        """Moderate change gets partial engagement."""
        agent = _make_agent(
            {
                "user_impact_level": "moderate",
                "experience_direction": "Update confirmation dialog text and add inline help",
                "engagement_depth": "partial",
                "notes": "",
            }
        )

        result = agent.evaluate_experience(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["user_impact_level"] == "moderate"
        assert result["engagement_depth"] == "partial"

    def test_low_impact(self):
        """Low impact change gets minimal direction."""
        agent = _make_agent(
            {
                "user_impact_level": "low",
                "experience_direction": "Minor copy change in error message",
                "engagement_depth": "minimal",
                "notes": "Users unlikely to notice",
            }
        )

        result = agent.evaluate_experience(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["user_impact_level"] == "low"

    def test_validation_feedback_included(self):
        """Validation feedback is passed to the LLM."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response(
            {
                "user_impact_level": "high",
                "experience_direction": "Direction",
                "engagement_depth": "full",
                "notes": "",
            }
        )

        agent = ExperienceAgent(openai_client=mock_client)
        validation_feedback = {
            "assessment": "challenge",
            "critique": "Experiment too large",
        }

        agent.evaluate_experience(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
            validation_feedback=validation_feedback,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_msg = messages[-1]["content"]
        assert "challenge" in user_msg


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    """Graceful failure on malformed LLM responses."""

    def test_missing_user_impact_level_raises(self):
        """Response without 'user_impact_level' raises ValueError."""
        agent = _make_agent({"experience_direction": "Some direction"})

        with pytest.raises(ValueError, match="missing required 'user_impact_level'"):
            agent.evaluate_experience(
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

        agent = ExperienceAgent(openai_client=mock_client)

        with pytest.raises(json.JSONDecodeError):
            agent.evaluate_experience(
                proposed_solution=_make_proposal(),
                opportunity_brief=_make_opportunity_brief(),
                dialogue_history=[],
            )

    def test_unknown_impact_level_defaults_to_moderate(self):
        """Unknown user_impact_level is normalized to moderate."""
        agent = _make_agent(
            {
                "user_impact_level": "mega",
                "experience_direction": "Unknown",
                "engagement_depth": "full",
                "notes": "",
            }
        )

        result = agent.evaluate_experience(
            proposed_solution=_make_proposal(),
            opportunity_brief=_make_opportunity_brief(),
            dialogue_history=[],
        )

        assert result["user_impact_level"] == "moderate"

    def test_llm_exception_propagates(self):
        """OpenAI API exception propagates to caller."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API error")
        agent = ExperienceAgent(openai_client=mock_client)

        with pytest.raises(RuntimeError, match="API error"):
            agent.evaluate_experience(
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
        config = ExperienceAgentConfig()
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.5

    def test_custom_config(self):
        config = ExperienceAgentConfig(model="gpt-4o", temperature=0.3)
        agent = ExperienceAgent(openai_client=MagicMock(), config=config)
        assert agent.config.model == "gpt-4o"
        assert agent.config.temperature == 0.3
