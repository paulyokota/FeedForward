"""Unit tests for the TPM Agent (Issue #222).

Tests priority ranking: opportunity packages -> advisory ranked list.
Uses mock OpenAI client throughout — no real LLM calls.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.tpm_agent import (
    TPMAgent,
    TPMAgentConfig,
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
    mock_response.usage.prompt_tokens = 250
    mock_response.usage.completion_tokens = 200
    mock_response.usage.total_tokens = 450
    return mock_response


def _make_agent(response_dict):
    """Create a TPMAgent with a mocked OpenAI client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response(
        response_dict
    )
    return TPMAgent(openai_client=mock_client)


def _make_package(opportunity_id="opp_billing", **overrides):
    """Create a minimal opportunity package."""
    defaults = {
        "opportunity_id": opportunity_id,
        "opportunity_brief": {
            "problem_statement": "Users struggle with billing",
            "affected_area": "billing",
        },
        "solution_brief": {
            "proposed_solution": "Consolidate billing forms",
        },
        "technical_spec": {
            "opportunity_id": opportunity_id,
            "approach": "Shared component",
            "effort_estimate": "2 weeks",
        },
    }
    defaults.update(overrides)
    return defaults


def _three_packages():
    """Create 3 opportunity packages for ranking tests."""
    return [
        _make_package("opp_billing"),
        _make_package("opp_onboarding"),
        _make_package("opp_search"),
    ]


def _three_rankings():
    """LLM response with 3 ranked opportunities."""
    return {
        "rankings": [
            {
                "opportunity_id": "opp_billing",
                "rationale": "High impact, low effort",
                "dependencies": [],
                "flags": [],
            },
            {
                "opportunity_id": "opp_onboarding",
                "rationale": "Medium impact, medium effort",
                "dependencies": ["opp_billing"],
                "flags": [],
            },
            {
                "opportunity_id": "opp_search",
                "rationale": "Lower priority — high effort",
                "dependencies": [],
                "flags": ["Requires infrastructure upgrade"],
            },
        ]
    }


# ============================================================================
# rank_opportunities: happy path
# ============================================================================


class TestRankOpportunities:
    def test_three_opportunities_ranked(self):
        agent = _make_agent(_three_rankings())

        result = agent.rank_opportunities(_three_packages())

        assert len(result["rankings"]) == 3
        assert result["rankings"][0]["opportunity_id"] == "opp_billing"
        assert result["rankings"][0]["recommended_rank"] == 1
        assert result["rankings"][1]["recommended_rank"] == 2
        assert result["rankings"][2]["recommended_rank"] == 3

    def test_single_opportunity(self):
        agent = _make_agent({
            "rankings": [
                {
                    "opportunity_id": "opp_solo",
                    "rationale": "Only one",
                    "dependencies": [],
                    "flags": [],
                }
            ]
        })

        result = agent.rank_opportunities([_make_package("opp_solo")])

        assert len(result["rankings"]) == 1
        assert result["rankings"][0]["recommended_rank"] == 1

    def test_empty_input_no_llm_call(self):
        mock_client = MagicMock()
        agent = TPMAgent(openai_client=mock_client)

        result = agent.rank_opportunities([])

        assert result["rankings"] == []
        assert result["token_usage"]["total_tokens"] == 0
        mock_client.chat.completions.create.assert_not_called()

    def test_token_usage_tracked(self):
        agent = _make_agent(_three_rankings())

        result = agent.rank_opportunities(_three_packages())

        assert result["token_usage"]["total_tokens"] == 450
        assert result["token_usage"]["prompt_tokens"] == 250
        assert result["token_usage"]["completion_tokens"] == 200

    def test_rationale_preserved(self):
        agent = _make_agent(_three_rankings())

        result = agent.rank_opportunities(_three_packages())

        assert "High impact" in result["rankings"][0]["rationale"]

    def test_dependencies_preserved(self):
        agent = _make_agent(_three_rankings())

        result = agent.rank_opportunities(_three_packages())

        assert result["rankings"][1]["dependencies"] == ["opp_billing"]

    def test_flags_preserved(self):
        agent = _make_agent(_three_rankings())

        result = agent.rank_opportunities(_three_packages())

        assert "infrastructure" in result["rankings"][2]["flags"][0]

    def test_no_usage_object_defaults_to_zero(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(_three_rankings())
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response

        agent = TPMAgent(openai_client=mock_client)

        result = agent.rank_opportunities(_three_packages())

        assert result["token_usage"]["total_tokens"] == 0


# ============================================================================
# _normalize_rankings
# ============================================================================


class TestNormalizeRankings:
    def test_duplicate_ids_deduped(self):
        agent = _make_agent({
            "rankings": [
                {"opportunity_id": "opp_a", "rationale": "First"},
                {"opportunity_id": "opp_a", "rationale": "Duplicate"},
                {"opportunity_id": "opp_b", "rationale": "Second"},
            ]
        })

        result = agent.rank_opportunities([
            _make_package("opp_a"),
            _make_package("opp_b"),
        ])

        ids = [r["opportunity_id"] for r in result["rankings"]]
        assert ids == ["opp_a", "opp_b"]
        assert result["rankings"][0]["rationale"] == "First"
        assert result["rankings"][0]["recommended_rank"] == 1
        assert result["rankings"][1]["recommended_rank"] == 2

    def test_missing_ids_appended(self):
        agent = _make_agent({
            "rankings": [
                {"opportunity_id": "opp_a", "rationale": "Only ranked one"},
            ]
        })

        result = agent.rank_opportunities([
            _make_package("opp_a"),
            _make_package("opp_b"),
            _make_package("opp_c"),
        ])

        ids = [r["opportunity_id"] for r in result["rankings"]]
        assert ids == ["opp_a", "opp_b", "opp_c"]
        assert result["rankings"][1]["rationale"] == "Not ranked by agent"
        assert "Auto-appended" in result["rankings"][1]["flags"][0]
        assert result["rankings"][2]["rationale"] == "Not ranked by agent"

    def test_duplicate_ranks_normalized(self):
        """LLM may assign same rank to multiple items — we ignore LLM ranks."""
        agent = _make_agent({
            "rankings": [
                {"opportunity_id": "opp_x", "rationale": "First", "recommended_rank": 1},
                {"opportunity_id": "opp_y", "rationale": "Second", "recommended_rank": 1},
            ]
        })

        result = agent.rank_opportunities([
            _make_package("opp_x"),
            _make_package("opp_y"),
        ])

        ranks = [r["recommended_rank"] for r in result["rankings"]]
        assert ranks == [1, 2]

    def test_reranks_sequentially(self):
        """Position in list determines rank, not any rank the LLM assigned."""
        agent = _make_agent({
            "rankings": [
                {"opportunity_id": "opp_a", "rationale": "A", "recommended_rank": 5},
                {"opportunity_id": "opp_b", "rationale": "B", "recommended_rank": 10},
            ]
        })

        result = agent.rank_opportunities([
            _make_package("opp_a"),
            _make_package("opp_b"),
        ])

        assert result["rankings"][0]["recommended_rank"] == 1
        assert result["rankings"][1]["recommended_rank"] == 2

    def test_missing_rationale_gets_default(self):
        """LLM may omit rationale — normalization fills it for Pydantic min_length=1."""
        agent = _make_agent({
            "rankings": [
                {"opportunity_id": "opp_a", "rationale": ""},
                {"opportunity_id": "opp_b"},
            ]
        })

        result = agent.rank_opportunities([
            _make_package("opp_a"),
            _make_package("opp_b"),
        ])

        assert result["rankings"][0]["rationale"] == "No rationale provided by agent"
        assert result["rankings"][1]["rationale"] == "No rationale provided by agent"


# ============================================================================
# build_checkpoint_artifacts
# ============================================================================


class TestBuildCheckpointArtifacts:
    def test_checkpoint_structure(self):
        agent = TPMAgent(openai_client=MagicMock())
        rankings = [
            {
                "opportunity_id": "opp_a",
                "recommended_rank": 1,
                "rationale": "Top priority",
                "dependencies": [],
                "flags": [],
            }
        ]
        token_usage = {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}

        checkpoint = agent.build_checkpoint_artifacts(rankings, token_usage)

        assert checkpoint["schema_version"] == 1
        assert len(checkpoint["rankings"]) == 1
        assert checkpoint["rankings"][0]["opportunity_id"] == "opp_a"
        assert checkpoint["prioritization_metadata"]["opportunities_ranked"] == 1
        assert checkpoint["prioritization_metadata"]["model"] == "gpt-4o-mini"

    def test_empty_rankings_valid(self):
        agent = TPMAgent(openai_client=MagicMock())

        checkpoint = agent.build_checkpoint_artifacts([], {"total_tokens": 0})

        assert checkpoint["rankings"] == []
        assert checkpoint["prioritization_metadata"]["opportunities_ranked"] == 0
        assert checkpoint["prioritization_metadata"]["model"] == "gpt-4o-mini"

    def test_custom_model_in_metadata(self):
        config = TPMAgentConfig(model="gpt-4o")
        agent = TPMAgent(openai_client=MagicMock(), config=config)

        checkpoint = agent.build_checkpoint_artifacts([], {"total_tokens": 0})

        assert checkpoint["prioritization_metadata"]["model"] == "gpt-4o"


# ============================================================================
# Validation
# ============================================================================


class TestValidation:
    def test_missing_opportunity_id_raises(self):
        agent = TPMAgent(openai_client=MagicMock())

        with pytest.raises(ValueError, match="missing 'opportunity_id'"):
            agent.rank_opportunities([
                {"opportunity_brief": {}, "solution_brief": {}, "technical_spec": {}},
            ])

    def test_empty_opportunity_id_raises(self):
        agent = TPMAgent(openai_client=MagicMock())

        with pytest.raises(ValueError, match="missing 'opportunity_id'"):
            agent.rank_opportunities([
                _make_package(""),
            ])

    def test_second_package_missing_id_raises(self):
        agent = TPMAgent(openai_client=MagicMock())

        with pytest.raises(ValueError, match="index 1"):
            agent.rank_opportunities([
                _make_package("opp_a"),
                {"opportunity_brief": {}, "solution_brief": {}, "technical_spec": {}},
            ])


# ============================================================================
# Error handling
# ============================================================================


class TestErrorHandling:
    def test_missing_rankings_key_raises(self):
        agent = _make_agent({"some_other_key": []})

        with pytest.raises(ValueError, match="missing required 'rankings'"):
            agent.rank_opportunities([_make_package("opp_a")])

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

        agent = TPMAgent(openai_client=mock_client)

        with pytest.raises(json.JSONDecodeError):
            agent.rank_opportunities([_make_package("opp_a")])

    def test_llm_exception_propagates(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        agent = TPMAgent(openai_client=mock_client)

        with pytest.raises(RuntimeError, match="API down"):
            agent.rank_opportunities([_make_package("opp_a")])


# ============================================================================
# Config
# ============================================================================


class TestConfig:
    def test_default_config(self):
        config = TPMAgentConfig()
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.3

    def test_custom_config(self):
        config = TPMAgentConfig(model="gpt-4o", temperature=0.1)
        agent = TPMAgent(openai_client=MagicMock(), config=config)
        assert agent.config.model == "gpt-4o"
        assert agent.config.temperature == 0.1
