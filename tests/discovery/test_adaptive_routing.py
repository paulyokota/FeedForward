"""Tests for adaptive pipeline routing (Issue #261).

Verifies that the discovery pipeline adapts behavior based on
opportunity_nature and stage_hints — skipping Experience Agent for
internal engineering opportunities, making SolutionBrief fields
Optional, and preserving backward compatibility.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.opportunity_pm import (
    KNOWN_STAGE_HINTS,
    FramingResult,
    OpportunityPM,
)
from src.discovery.agents.solution_designer import (
    SolutionDesignResult,
    SolutionDesigner,
    SolutionDesignerConfig,
    should_skip_experience,
)
from src.discovery.agents.experience_agent import ExperienceAgent
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.models.artifacts import (
    OpportunityBrief,
    SolutionBrief,
    SolutionValidationCheckpoint,
)
from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
    SourceType,
)


NOW = datetime.now(timezone.utc).isoformat()


# ============================================================================
# Helpers
# ============================================================================


def _evidence():
    return {
        "source_type": SourceType.INTERCOM.value,
        "source_id": "conv_001",
        "retrieved_at": NOW,
        "confidence": ConfidenceLevel.HIGH.value,
    }


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


def _make_validation_response(assessment="approve"):
    return {
        "assessment": assessment,
        "critique": "Looks good",
        "experiment_suggestion": "Run test suite",
        "success_criteria": "All tests pass",
        "challenge_reason": "",
        "token_usage": {"prompt_tokens": 50, "completion_tokens": 40, "total_tokens": 90},
    }


# ============================================================================
# Schema tests
# ============================================================================


@pytest.mark.fast
class TestOpportunityBriefAdaptiveFields:
    """Test OpportunityBrief with new adaptive routing fields."""

    def test_opportunity_brief_with_nature_fields(self):
        """OpportunityBrief validates with new Optional fields present."""
        brief = OpportunityBrief(
            problem_statement="Instrumentation gap in event tracking",
            evidence=[_evidence()],
            counterfactual="If we fix this, we'd have 30% more event coverage",
            affected_area="src/analytics/event_tracker.py",
            explorer_coverage="10 files reviewed",
            opportunity_nature="internal engineering: instrumentation gap",
            recommended_response="internal task, no user experiment needed",
            stage_hints=["skip_experience", "internal_risk_framing"],
        )
        assert brief.opportunity_nature == "internal engineering: instrumentation gap"
        assert brief.recommended_response == "internal task, no user experiment needed"
        assert brief.stage_hints == ["skip_experience", "internal_risk_framing"]

    def test_backward_compat_brief_without_new_fields(self):
        """Existing briefs (no opportunity_nature) still validate."""
        brief = OpportunityBrief(
            problem_statement="Users confused by scheduling UI",
            evidence=[_evidence()],
            counterfactual="Scheduling completion rate +15%",
            affected_area="Schedule page calendar widget",
            explorer_coverage="20 conversations reviewed",
        )
        assert brief.opportunity_nature is None
        assert brief.recommended_response is None
        assert brief.stage_hints is None


@pytest.mark.fast
class TestSolutionBriefOptionalFields:
    """Test SolutionBrief with Optional experiment_plan and build_experiment_decision."""

    def test_solution_brief_optional_experiment_plan(self):
        """SolutionBrief validates with experiment_plan=None and skip_rationale."""
        brief = SolutionBrief(
            proposed_solution="Add event tracking to billing flow",
            experiment_plan=None,
            success_metrics="Event coverage increases from 70% to 95%",
            build_experiment_decision=None,
            evidence=[_evidence()],
            skip_rationale="Internal engineering opportunity: no user experiment needed",
        )
        assert brief.experiment_plan is None
        assert brief.build_experiment_decision is None
        assert brief.skip_rationale is not None

    def test_solution_brief_optional_build_decision(self):
        """SolutionBrief validates with build_experiment_decision=None."""
        brief = SolutionBrief(
            proposed_solution="Fix instrumentation gap",
            success_metrics="Error rate drops by 50%",
            evidence=[_evidence()],
        )
        assert brief.build_experiment_decision is None
        assert brief.experiment_plan is None

    def test_solution_brief_with_all_fields(self):
        """SolutionBrief validates normally with all fields set."""
        exp_dir = {
            "user_impact_level": "high",
            "experience_direction": "Full UX redesign of wizard flow",
            "engagement_depth": "full",
            "notes": "",
        }
        brief = SolutionBrief(
            proposed_solution="Simplify scheduling wizard",
            experiment_plan="A/B test with 10% of users",
            success_metrics="Scheduling completion rate +15%",
            build_experiment_decision=BuildExperimentDecision.BUILD_SLICE_AND_EXPERIMENT,
            evidence=[_evidence()],
            experience_direction=exp_dir,
        )
        assert brief.experiment_plan == "A/B test with 10% of users"
        assert brief.build_experiment_decision == BuildExperimentDecision.BUILD_SLICE_AND_EXPERIMENT
        assert brief.experience_direction == exp_dir

    def test_checkpoint_serialization_with_none_fields(self):
        """SolutionValidationCheckpoint serializes correctly with None fields."""
        checkpoint = SolutionValidationCheckpoint(
            solutions=[
                SolutionBrief(
                    proposed_solution="Internal fix",
                    experiment_plan=None,
                    success_metrics="Coverage +30%",
                    build_experiment_decision=None,
                    evidence=[_evidence()],
                    skip_rationale="Internal engineering opportunity",
                ),
            ],
            design_metadata={
                "opportunity_briefs_processed": 1,
                "solutions_produced": 1,
                "total_dialogue_rounds": 1,
                "total_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "model": "gpt-4o-mini",
            },
        )
        d = checkpoint.model_dump()
        sol = d["solutions"][0]
        assert sol["experiment_plan"] is None
        assert sol["build_experiment_decision"] is None
        assert sol["skip_rationale"] == "Internal engineering opportunity"


# ============================================================================
# Routing logic tests
# ============================================================================


@pytest.mark.fast
class TestShouldSkipExperience:
    """Test the canonical should_skip_experience() helper."""

    def test_skip_via_stage_hints(self):
        assert should_skip_experience({"stage_hints": ["skip_experience"]}) is True

    def test_skip_via_opportunity_nature_internal(self):
        assert should_skip_experience({
            "opportunity_nature": "internal engineering: instrumentation gap"
        }) is True

    def test_skip_via_nature_infrastructure(self):
        assert should_skip_experience({
            "opportunity_nature": "Infrastructure improvement needed"
        }) is True

    def test_no_skip_user_facing(self):
        assert should_skip_experience({
            "opportunity_nature": "user-facing: checkout friction"
        }) is False

    def test_no_skip_empty_brief(self):
        assert should_skip_experience({}) is False

    def test_no_skip_none_fields(self):
        assert should_skip_experience({
            "opportunity_nature": None,
            "stage_hints": None,
        }) is False

    def test_case_insensitive_nature(self):
        assert should_skip_experience({
            "opportunity_nature": "INTERNAL Engineering task"
        }) is True


# ============================================================================
# Solution Designer routing tests
# ============================================================================


@pytest.mark.fast
class TestSolutionDesignerAdaptiveRouting:
    """Test that SolutionDesigner conditionally skips Experience Agent."""

    def _make_designer(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "proposed_solution": "Add event tracking",
            "experiment_plan": "",
            "success_metrics": "Event coverage +30%",
            "build_experiment_decision": "build_direct",
            "decision_rationale": "Straightforward internal fix",
            "evidence_ids": ["conv_001"],
            "confidence": "high",
        })

        val_agent = MagicMock(spec=ValidationAgent)
        val_agent.evaluate_solution.return_value = _make_validation_response("approve")

        exp_agent = MagicMock(spec=ExperienceAgent)
        exp_agent.evaluate_experience.return_value = {
            "user_impact_level": "moderate",
            "experience_direction": "Some UX direction",
            "engagement_depth": "partial",
            "notes": "Consider edge cases",
            "token_usage": {"prompt_tokens": 50, "completion_tokens": 40, "total_tokens": 90},
        }

        designer = SolutionDesigner(
            val_agent, exp_agent, openai_client=mock_client,
            config=SolutionDesignerConfig(max_rounds=1),
        )
        return designer, val_agent, exp_agent

    def test_skips_experience_for_internal(self):
        """SolutionDesigner doesn't call ExperienceAgent when stage_hints say skip."""
        designer, val_agent, exp_agent = self._make_designer()
        brief = {
            "problem_statement": "Missing event tracking",
            "evidence": [_evidence()],
            "counterfactual": "Better coverage",
            "affected_area": "src/analytics/events.py",
            "explorer_coverage": "10 files",
            "opportunity_nature": "internal engineering: instrumentation gap",
            "stage_hints": ["skip_experience"],
        }

        result = designer.design_solution(brief, [])

        # Experience Agent should NOT have been called
        exp_agent.evaluate_experience.assert_not_called()
        # Validation Agent should still have been called
        val_agent.evaluate_solution.assert_called_once()
        # experience_direction should be None
        assert result.experience_direction is None
        # skip_rationale should be populated
        assert result.skip_rationale is not None
        assert "Experience Agent skipped" in result.skip_rationale

    def test_full_pipeline_no_hints(self):
        """Without stage_hints, ExperienceAgent is called normally."""
        designer, val_agent, exp_agent = self._make_designer()
        brief = {
            "problem_statement": "Checkout friction",
            "evidence": [_evidence()],
            "counterfactual": "Conversion rate +5%",
            "affected_area": "Checkout page",
            "explorer_coverage": "20 conversations",
            "opportunity_nature": "user-facing: checkout friction",
        }

        result = designer.design_solution(brief, [])

        # Experience Agent should have been called
        exp_agent.evaluate_experience.assert_called_once()
        # experience_direction should be populated
        assert result.experience_direction is not None
        assert result.experience_direction["user_impact_level"] == "moderate"

    def test_skip_rationale_populated(self):
        """When experience is skipped, skip_rationale is populated and experience_direction is None."""
        designer, val_agent, exp_agent = self._make_designer()
        brief = {
            "problem_statement": "Missing instrumentation",
            "evidence": [_evidence()],
            "counterfactual": "Better monitoring",
            "affected_area": "src/telemetry/",
            "explorer_coverage": "5 files",
            "stage_hints": ["skip_experience"],
        }

        result = designer.design_solution(brief, [])

        assert result.experience_direction is None
        assert result.skip_rationale is not None
        assert "Experience Agent skipped" in result.skip_rationale

        # Build checkpoint and verify skip_rationale propagates
        artifacts = designer.build_checkpoint_artifacts([result])
        solution = artifacts["solutions"][0]
        assert solution["skip_rationale"] is not None
        assert solution["experience_direction"] is None


# ============================================================================
# OpportunityPM propagation tests
# ============================================================================


@pytest.mark.fast
class TestOpportunityPMPropagation:
    """Test that OpportunityPM propagates adaptive routing fields."""

    def test_propagates_nature_fields(self):
        """build_checkpoint_artifacts includes nature fields from LLM output."""
        pm = OpportunityPM(openai_client=MagicMock())
        result = FramingResult(
            opportunities=[
                {
                    "problem_statement": "Missing event tracking",
                    "evidence_conversation_ids": ["conv_001"],
                    "counterfactual": "Better coverage",
                    "affected_area": "src/analytics/events.py",
                    "confidence": "high",
                    "source_findings": ["pattern_1"],
                    "opportunity_nature": "internal engineering: instrumentation gap",
                    "recommended_response": "internal task, no user experiment",
                    "stage_hints": ["skip_experience", "internal_risk_framing"],
                },
            ],
            explorer_findings_count=3,
            coverage_summary="10 files reviewed",
        )

        artifacts = pm.build_checkpoint_artifacts(result)
        brief = artifacts["briefs"][0]

        assert brief["opportunity_nature"] == "internal engineering: instrumentation gap"
        assert brief["recommended_response"] == "internal task, no user experiment"
        assert brief["stage_hints"] == ["skip_experience", "internal_risk_framing"]

    def test_filters_unknown_stage_hints(self):
        """Unknown hints are dropped with warning, only known hints pass through."""
        pm = OpportunityPM(openai_client=MagicMock())
        result = FramingResult(
            opportunities=[
                {
                    "problem_statement": "Some problem",
                    "evidence_conversation_ids": ["conv_001"],
                    "counterfactual": "Some change",
                    "affected_area": "Some area",
                    "confidence": "medium",
                    "source_findings": ["p1"],
                    "stage_hints": ["skip_experience", "invalid_hint", "internal_risk_framing", 42],
                },
            ],
            explorer_findings_count=1,
            coverage_summary="1 file",
        )

        artifacts = pm.build_checkpoint_artifacts(result)
        brief = artifacts["briefs"][0]

        assert brief["stage_hints"] == ["skip_experience", "internal_risk_framing"]

    def test_no_nature_fields_when_absent(self):
        """When LLM doesn't return nature fields, they're not in the brief dict."""
        pm = OpportunityPM(openai_client=MagicMock())
        result = FramingResult(
            opportunities=[
                {
                    "problem_statement": "Some problem",
                    "evidence_conversation_ids": ["conv_001"],
                    "counterfactual": "Some change",
                    "affected_area": "Some area",
                    "confidence": "medium",
                    "source_findings": ["p1"],
                },
            ],
            explorer_findings_count=1,
            coverage_summary="1 file",
        )

        artifacts = pm.build_checkpoint_artifacts(result)
        brief = artifacts["briefs"][0]

        assert "opportunity_nature" not in brief
        assert "recommended_response" not in brief
        assert "stage_hints" not in brief
