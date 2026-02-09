"""Tests for the Discovery Engine Orchestrator.

Verifies that DiscoveryOrchestrator correctly wires all agents together,
handles errors gracefully, and returns accurate run status.

Uses InMemoryStorage + InMemoryTransport with mocked agent methods.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.discovery.agents.base import ExplorerResult
from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
    FeasibilityAssessment,
    RunStatus,
    SourceType,
    StageType,
)
from src.discovery.models.run import RunConfig
from src.discovery.orchestrator import DiscoveryOrchestrator
from src.discovery.services.transport import InMemoryTransport

from tests.discovery.test_conversation_service import InMemoryStorage


NOW = datetime.now(timezone.utc).isoformat()


# ============================================================================
# Test data builders
# ============================================================================


def _evidence(source_type=SourceType.INTERCOM, source_id="conv-1"):
    return {
        "source_type": source_type.value,
        "source_id": source_id,
        "retrieved_at": NOW,
        "confidence": ConfidenceLevel.HIGH.value,
    }


def _explorer_finding(source_type, pattern_name, source_id):
    return {
        "pattern_name": pattern_name,
        "description": f"Finding: {pattern_name}",
        "evidence": [_evidence(source_type, source_id)],
        "confidence": ConfidenceLevel.HIGH.value,
        "severity_assessment": "medium",
        "affected_users_estimate": "~50 users",
    }


def _mock_explorer_result(source_type, pattern_name, source_id):
    """Create a mock ExplorerResult."""
    return ExplorerResult(
        findings=[_explorer_finding(source_type, pattern_name, source_id)],
        coverage={
            "time_window_days": 14,
            "conversations_available": 10,
            "conversations_reviewed": 10,
            "conversations_skipped": 0,
            "model": "gpt-4o-mini",
            "findings_count": 1,
        },
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )


def _mock_framing_result():
    """Return what OpportunityPM.frame_opportunities returns."""
    from src.discovery.agents.opportunity_pm import FramingResult

    return FramingResult(
        opportunities=[
            {
                "affected_area": "checkout",
                "problem_statement": "Checkout flow has friction",
                "evidence": [_evidence(SourceType.INTERCOM, "conv-1")],
                "counterfactual": "Users would complete purchases faster",
                "severity": "high",
                "confidence": ConfidenceLevel.HIGH.value,
            }
        ],
        framing_notes="Mock framing notes",
        explorer_findings_count=4,
        coverage_summary="Covered all explorers",
        token_usage={"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
    )


def _mock_solution_design_result():
    """Return what SolutionDesigner.design_solution returns."""
    from src.discovery.agents.solution_designer import SolutionDesignResult

    return SolutionDesignResult(
        proposed_solution="Simplify checkout to 2 steps",
        experiment_plan="A/B test with 1000 users",
        success_metrics="20% increase in completion rate",
        build_experiment_decision=BuildExperimentDecision.EXPERIMENT_FIRST.value,
        decision_rationale="Low risk, high potential impact",
        evidence=[_evidence(SourceType.INTERCOM, "conv-1")],
        dialogue_rounds=2,
        validation_challenges=[{"challenge": "Edge cases", "response": "Handled"}],
        experience_direction={"engagement_depth": "medium", "friction_reduction": "high"},
        convergence_forced=False,
        convergence_note="",
    )


def _mock_feasibility_result():
    """Return what FeasibilityDesigner.assess_feasibility returns."""
    from src.discovery.agents.feasibility_designer import FeasibilityResult

    return FeasibilityResult(
        opportunity_id="checkout",
        is_feasible=True,
        assessment={
            "opportunity_id": "checkout",
            "feasibility": FeasibilityAssessment.FEASIBLE.value,
            "approach": "React component refactor",
            "effort_estimate": "2 weeks",
            "dependencies": [],
            "risks": [{"risk": "Browser compat", "severity": "low", "mitigation": "Polyfills"}],
            "evidence": [_evidence(SourceType.INTERCOM, "conv-1")],
        },
        risk_evaluation={
            "overall_risk": "low",
            "risks": [{"risk": "Browser compat", "severity": "low", "mitigation": "Polyfills"}],
        },
        total_rounds=1,
    )


def _mock_ranking_result():
    """Return what TPMAgent.rank_opportunities returns."""
    return {
        "rankings": [
            {
                "opportunity_id": "checkout",
                "recommended_rank": 1,
                "rationale": "High impact, low effort",
                "impact_score": 0.9,
                "effort_score": 0.3,
                "risk_score": 0.2,
                "strategic_alignment_score": 0.8,
                "composite_score": 0.85,
            }
        ],
        "token_usage": {"prompt_tokens": 150, "completion_tokens": 80, "total_tokens": 230},
    }


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.slow
class TestDiscoveryOrchestrator:
    """Tests for the orchestrator wiring all stages together."""

    def _create_orchestrator(self, storage=None, transport=None):
        """Create orchestrator with in-memory backends and a mock db."""
        storage = storage or InMemoryStorage()
        transport = transport or InMemoryTransport()
        mock_client = MagicMock()

        orchestrator = DiscoveryOrchestrator(
            db_connection=MagicMock(),  # mock db — ConversationReader won't be called
            transport=transport,
            openai_client=mock_client,
            posthog_data={},
            repo_root="/tmp/fake-repo",
        )
        # Replace internally-created storage with our InMemoryStorage
        orchestrator.storage = storage
        orchestrator.state_machine.storage = storage
        orchestrator.service.storage = storage
        orchestrator.service.state_machine.storage = storage

        return orchestrator, storage, mock_client

    @patch("src.discovery.orchestrator.CustomerVoiceExplorer")
    @patch("src.discovery.orchestrator.AnalyticsExplorer")
    @patch("src.discovery.orchestrator.CodebaseExplorer")
    @patch("src.discovery.orchestrator.ResearchExplorer")
    @patch("src.discovery.orchestrator.OpportunityPM")
    @patch("src.discovery.orchestrator.SolutionDesigner")
    @patch("src.discovery.orchestrator.FeasibilityDesigner")
    @patch("src.discovery.orchestrator.TPMAgent")
    @patch("src.discovery.orchestrator.ConversationReader")
    @patch("src.discovery.orchestrator.CodebaseReader")
    @patch("src.discovery.orchestrator.ResearchReader")
    @patch("src.discovery.orchestrator.PostHogReader")
    def test_orchestrator_runs_stages_0_to_4(
        self,
        mock_posthog_reader_cls,
        mock_research_reader_cls,
        mock_codebase_reader_cls,
        mock_conversation_reader_cls,
        mock_tpm_cls,
        mock_feasibility_cls,
        mock_solution_cls,
        mock_opp_pm_cls,
        mock_research_cls,
        mock_codebase_cls,
        mock_analytics_cls,
        mock_customer_cls,
    ):
        """Full pipeline: Stages 0-4 run, result is RUNNING at human_review."""
        orchestrator, storage, mock_client = self._create_orchestrator()

        # Stage 0: Mock all explorers to return findings
        for mock_cls, source, pattern, sid in [
            (mock_customer_cls, SourceType.INTERCOM, "customer_pain", "conv-1"),
            (mock_analytics_cls, SourceType.POSTHOG, "drop_off", "event-1"),
            (mock_codebase_cls, SourceType.CODEBASE, "tech_debt", "file-1"),
            (mock_research_cls, SourceType.RESEARCH, "industry_trend", "doc-1"),
        ]:
            instance = mock_cls.return_value
            instance.explore.return_value = _mock_explorer_result(source, pattern, sid)

        # Stage 1: Mock OpportunityPM
        pm_instance = mock_opp_pm_cls.return_value
        pm_instance.frame_opportunities.return_value = _mock_framing_result()
        # build_checkpoint_artifacts needs to return a valid OpportunityFramingCheckpoint dict
        pm_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "briefs": [
                {
                    "affected_area": "checkout",
                    "problem_statement": "Checkout flow has friction",
                    "evidence": [_evidence(SourceType.INTERCOM, "conv-1")],
                    "counterfactual": "Users would complete purchases faster",
                    "explorer_coverage": "Reviewed 10 Intercom conversations, 5 PostHog events, 3 code files, 2 docs",
                    "severity": "high",
                    "confidence": ConfidenceLevel.HIGH.value,
                }
            ],
            "framing_metadata": {
                "model": "gpt-4o-mini",
                "explorer_findings_count": 4,
                "opportunities_identified": 1,
                "token_usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            },
        }

        # Stage 2: Mock SolutionDesigner
        sol_instance = mock_solution_cls.return_value
        sol_instance.design_solution.return_value = _mock_solution_design_result()
        sol_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "solutions": [
                {
                    "proposed_solution": "Simplify checkout to 2 steps",
                    "experiment_plan": "A/B test with 1000 users",
                    "success_metrics": "20% increase in completion rate",
                    "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                    "decision_rationale": "Low risk, high potential impact",
                    "evidence": [_evidence(SourceType.INTERCOM, "conv-1")],
                }
            ],
            "design_metadata": {
                "model": "gpt-4o-mini",
                "opportunity_briefs_processed": 1,
                "solutions_produced": 1,
                "total_dialogue_rounds": 2,
                "total_token_usage": {"prompt_tokens": 300, "completion_tokens": 200, "total_tokens": 500},
            },
        }

        # Stage 3: Mock FeasibilityDesigner
        feas_instance = mock_feasibility_cls.return_value
        feas_instance.assess_feasibility.return_value = _mock_feasibility_result()
        feas_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "specs": [
                {
                    "opportunity_id": "checkout",
                    "approach": "React component refactor",
                    "effort_estimate": "2 weeks with high confidence",
                    "dependencies": "None — self-contained component change",
                    "risks": [{"description": "Browser compat", "severity": "low", "mitigation": "Polyfills"}],
                    "acceptance_criteria": "Checkout completion rate > 80%",
                }
            ],
            "infeasible_solutions": [],
            "feasibility_metadata": {
                "model": "gpt-4o-mini",
                "solutions_assessed": 1,
                "feasible_count": 1,
                "infeasible_count": 0,
                "total_dialogue_rounds": 1,
                "total_token_usage": {"prompt_tokens": 250, "completion_tokens": 150, "total_tokens": 400},
            },
        }

        # Stage 4: Mock TPMAgent
        tpm_instance = mock_tpm_cls.return_value
        tpm_instance.rank_opportunities.return_value = _mock_ranking_result()
        tpm_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "rankings": [
                {
                    "opportunity_id": "checkout",
                    "recommended_rank": 1,
                    "rationale": "High impact, low effort",
                    "impact_score": 0.9,
                    "effort_score": 0.3,
                    "risk_score": 0.2,
                    "strategic_alignment_score": 0.8,
                    "composite_score": 0.85,
                }
            ],
            "prioritization_metadata": {
                "model": "gpt-4o-mini",
                "opportunities_ranked": 1,
            },
        }

        # Run the orchestrator
        run = orchestrator.run(config=RunConfig(time_window_days=7))

        # Verify final state
        assert run.status == RunStatus.RUNNING
        assert run.current_stage == StageType.HUMAN_REVIEW

        # Verify all stages completed
        stages = storage.get_stage_executions_for_run(run.id)
        completed_stages = [s for s in stages if s.artifacts is not None]
        # 5 completed stages (exploration through prioritization) + 1 in-progress (human_review)
        assert len(completed_stages) == 5

        # Verify Stage 4 checkpoint has rankings
        pri_stage = [s for s in stages if s.stage == StageType.PRIORITIZATION][0]
        assert "rankings" in pri_stage.artifacts
        assert pri_stage.artifacts["rankings"][0]["opportunity_id"] == "checkout"

    @patch("src.discovery.orchestrator.CustomerVoiceExplorer")
    @patch("src.discovery.orchestrator.AnalyticsExplorer")
    @patch("src.discovery.orchestrator.CodebaseExplorer")
    @patch("src.discovery.orchestrator.ResearchExplorer")
    @patch("src.discovery.orchestrator.ConversationReader")
    @patch("src.discovery.orchestrator.CodebaseReader")
    @patch("src.discovery.orchestrator.ResearchReader")
    @patch("src.discovery.orchestrator.PostHogReader")
    def test_orchestrator_fails_gracefully(
        self,
        mock_posthog_reader_cls,
        mock_research_reader_cls,
        mock_codebase_reader_cls,
        mock_conversation_reader_cls,
        mock_research_cls,
        mock_codebase_cls,
        mock_analytics_cls,
        mock_customer_cls,
    ):
        """When an explorer raises, run is marked FAILED with error details."""
        orchestrator, storage, _ = self._create_orchestrator()

        # First explorer succeeds, second raises
        mock_customer_cls.return_value.explore.return_value = _mock_explorer_result(
            SourceType.INTERCOM, "pain", "conv-1"
        )
        mock_analytics_cls.return_value.explore.side_effect = RuntimeError(
            "PostHog API timeout"
        )

        run = orchestrator.run()

        assert run.status == RunStatus.FAILED
        assert len(run.errors) == 1
        assert run.errors[0]["stage"] == "exploration"
        assert "PostHog API timeout" in run.errors[0]["message"]

    @patch("src.discovery.orchestrator.CustomerVoiceExplorer")
    @patch("src.discovery.orchestrator.AnalyticsExplorer")
    @patch("src.discovery.orchestrator.CodebaseExplorer")
    @patch("src.discovery.orchestrator.ResearchExplorer")
    @patch("src.discovery.orchestrator.OpportunityPM")
    @patch("src.discovery.orchestrator.ConversationReader")
    @patch("src.discovery.orchestrator.CodebaseReader")
    @patch("src.discovery.orchestrator.ResearchReader")
    @patch("src.discovery.orchestrator.PostHogReader")
    def test_stage1_failure_marks_run_failed(
        self,
        mock_posthog_reader_cls,
        mock_research_reader_cls,
        mock_codebase_reader_cls,
        mock_conversation_reader_cls,
        mock_opp_pm_cls,
        mock_research_cls,
        mock_codebase_cls,
        mock_analytics_cls,
        mock_customer_cls,
    ):
        """When Stage 1 fails, run is marked FAILED at opportunity_framing."""
        orchestrator, storage, _ = self._create_orchestrator()

        # All explorers succeed
        for mock_cls, source, pattern, sid in [
            (mock_customer_cls, SourceType.INTERCOM, "pain", "conv-1"),
            (mock_analytics_cls, SourceType.POSTHOG, "drop", "event-1"),
            (mock_codebase_cls, SourceType.CODEBASE, "debt", "file-1"),
            (mock_research_cls, SourceType.RESEARCH, "trend", "doc-1"),
        ]:
            mock_cls.return_value.explore.return_value = _mock_explorer_result(
                source, pattern, sid
            )

        # OpportunityPM raises
        mock_opp_pm_cls.return_value.frame_opportunities.side_effect = ValueError(
            "LLM returned invalid JSON"
        )

        run = orchestrator.run()

        assert run.status == RunStatus.FAILED
        assert run.errors[0]["stage"] == "opportunity_framing"
        assert "invalid JSON" in run.errors[0]["message"]

    def test_orchestrator_with_config(self):
        """RunConfig propagates to the created run."""
        orchestrator, storage, _ = self._create_orchestrator()

        config = RunConfig(target_domain="billing", time_window_days=7)

        # We can't run the full pipeline without mocking, but we can verify
        # the run is created with the right config by catching the explorer error
        with patch("src.discovery.orchestrator.ConversationReader"):
            with patch("src.discovery.orchestrator.CodebaseReader"):
                with patch("src.discovery.orchestrator.ResearchReader"):
                    with patch("src.discovery.orchestrator.PostHogReader"):
                        with patch("src.discovery.orchestrator.CustomerVoiceExplorer") as mock_cv:
                            mock_cv.return_value.explore.side_effect = RuntimeError("stop")
                            with patch("src.discovery.orchestrator.AnalyticsExplorer"):
                                with patch("src.discovery.orchestrator.CodebaseExplorer"):
                                    with patch("src.discovery.orchestrator.ResearchExplorer"):
                                        run = orchestrator.run(config=config)

        # Run was created (then failed), but config should be stored
        assert run.config.target_domain == "billing"
        assert run.config.time_window_days == 7
