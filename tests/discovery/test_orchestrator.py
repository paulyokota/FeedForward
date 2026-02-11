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
        token_usage={"prompt_tokens": 300, "completion_tokens": 200, "total_tokens": 500},
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
        token_usage={"prompt_tokens": 250, "completion_tokens": 150, "total_tokens": 400},
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

        # Stage 0: Mock all explorers to return findings + checkpoint dicts
        for mock_cls, source, pattern, sid in [
            (mock_customer_cls, SourceType.INTERCOM, "customer_pain", "conv-1"),
            (mock_analytics_cls, SourceType.POSTHOG, "drop_off", "event-1"),
            (mock_codebase_cls, SourceType.CODEBASE, "tech_debt", "file-1"),
            (mock_research_cls, SourceType.RESEARCH, "industry_trend", "doc-1"),
        ]:
            instance = mock_cls.return_value
            instance.explore.return_value = _mock_explorer_result(source, pattern, sid)
            instance.build_checkpoint_artifacts.return_value = {
                "schema_version": 1,
                "agent_name": mock_cls.__name__ if hasattr(mock_cls, '__name__') else "mock_explorer",
                "findings": [_explorer_finding(source, pattern, sid)],
                "coverage": {
                    "time_window_days": 14,
                    "conversations_available": 10,
                    "conversations_reviewed": 10,
                    "conversations_skipped": 0,
                    "model": "gpt-4o-mini",
                    "findings_count": 1,
                },
            }

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
        sol_instance.validate_input.return_value = _mock_validation_result(accepted=["checkout"])
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
        feas_instance.validate_input.return_value = _mock_validation_result(accepted=["checkout"])
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
        tpm_instance.validate_input.return_value = _mock_validation_result(accepted=["checkout"])
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
            mock_cls.return_value.build_checkpoint_artifacts.return_value = {
                "schema_version": 1,
                "agent_name": "mock_explorer",
                "findings": [_explorer_finding(source, pattern, sid)],
                "coverage": {
                    "time_window_days": 14,
                    "conversations_available": 10,
                    "conversations_reviewed": 10,
                    "conversations_skipped": 0,
                    "model": "gpt-4o-mini",
                    "findings_count": 1,
                },
            }

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
    def test_agent_invocations_recorded(
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
        """Agent invocations are recorded with token usage for all stages."""
        orchestrator, storage, mock_client = self._create_orchestrator()

        # Stage 0: Mock all explorers
        for mock_cls, source, pattern, sid in [
            (mock_customer_cls, SourceType.INTERCOM, "customer_pain", "conv-1"),
            (mock_analytics_cls, SourceType.POSTHOG, "drop_off", "event-1"),
            (mock_codebase_cls, SourceType.CODEBASE, "tech_debt", "file-1"),
            (mock_research_cls, SourceType.RESEARCH, "industry_trend", "doc-1"),
        ]:
            instance = mock_cls.return_value
            instance.explore.return_value = _mock_explorer_result(source, pattern, sid)
            instance.build_checkpoint_artifacts.return_value = {
                "schema_version": 1,
                "agent_name": "mock_explorer",
                "findings": [_explorer_finding(source, pattern, sid)],
                "coverage": {
                    "time_window_days": 14,
                    "conversations_available": 10,
                    "conversations_reviewed": 10,
                    "conversations_skipped": 0,
                    "model": "gpt-4o-mini",
                    "findings_count": 1,
                },
            }

        # Stage 1
        pm_instance = mock_opp_pm_cls.return_value
        pm_instance.frame_opportunities.return_value = _mock_framing_result()
        pm_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "briefs": [
                {
                    "affected_area": "checkout",
                    "problem_statement": "Checkout flow has friction",
                    "evidence": [_evidence(SourceType.INTERCOM, "conv-1")],
                    "counterfactual": "Users would complete purchases faster",
                    "explorer_coverage": "Reviewed conversations",
                }
            ],
            "framing_metadata": {
                "model": "gpt-4o-mini",
                "explorer_findings_count": 4,
                "opportunities_identified": 1,
            },
        }

        # Stage 2
        sol_instance = mock_solution_cls.return_value
        sol_instance.design_solution.return_value = _mock_solution_design_result()
        sol_instance.validate_input.return_value = _mock_validation_result(accepted=["checkout"])
        sol_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "solutions": [
                {
                    "proposed_solution": "Simplify checkout",
                    "experiment_plan": "A/B test",
                    "success_metrics": "20% increase",
                    "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                    "decision_rationale": "Low risk",
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

        # Stage 3
        feas_instance = mock_feasibility_cls.return_value
        feas_instance.assess_feasibility.return_value = _mock_feasibility_result()
        feas_instance.validate_input.return_value = _mock_validation_result(accepted=["checkout"])
        feas_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "specs": [
                {
                    "opportunity_id": "checkout",
                    "approach": "React refactor",
                    "effort_estimate": "2 weeks",
                    "dependencies": "None",
                    "risks": [{"description": "Browser compat", "severity": "low", "mitigation": "Polyfills"}],
                    "acceptance_criteria": "Checkout > 80%",
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

        # Stage 4
        tpm_instance = mock_tpm_cls.return_value
        tpm_instance.rank_opportunities.return_value = _mock_ranking_result()
        tpm_instance.validate_input.return_value = _mock_validation_result(accepted=["checkout"])
        tpm_instance.build_checkpoint_artifacts.return_value = {
            "schema_version": 1,
            "rankings": [
                {
                    "opportunity_id": "checkout",
                    "recommended_rank": 1,
                    "rationale": "High impact",
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

        run = orchestrator.run(config=RunConfig(time_window_days=7))

        # Verify agent invocations were recorded
        invocations = storage.agent_invocations
        agent_names = [inv.agent_name for inv in invocations]

        # 4 explorers + opportunity_pm + solution_designer_validate + solution_designer
        # + feasibility_designer_validate + feasibility_designer + tpm_validate + tpm_agent = 11
        assert len(invocations) == 11, f"Expected 11 invocations, got {len(invocations)}: {agent_names}"

        # Check explorer invocations
        assert "customer_voice" in agent_names
        assert "analytics" in agent_names
        assert "codebase" in agent_names
        assert "research" in agent_names

        # Check stage agent invocations
        assert "opportunity_pm" in agent_names
        assert "solution_designer" in agent_names
        assert "feasibility_designer" in agent_names
        assert "tpm_agent" in agent_names

        # Verify token_usage is populated
        for inv in invocations:
            assert inv.token_usage is not None
            assert inv.token_usage.total_tokens > 0

        # Verify participating_agents set on stage executions
        stages = storage.get_stage_executions_for_run(run.id)
        exploration_stage = [s for s in stages if s.stage == StageType.EXPLORATION][0]
        assert set(exploration_stage.participating_agents) == {
            "customer_voice", "analytics", "codebase", "research"
        }

        opp_stage = [s for s in stages if s.stage == StageType.OPPORTUNITY_FRAMING][0]
        assert "opportunity_pm" in opp_stage.participating_agents

        sol_stage = [s for s in stages if s.stage == StageType.SOLUTION_VALIDATION][0]
        assert "solution_designer" in sol_stage.participating_agents

        feas_stage = [s for s in stages if s.stage == StageType.FEASIBILITY_RISK][0]
        assert "feasibility_designer" in feas_stage.participating_agents

        pri_stage = [s for s in stages if s.stage == StageType.PRIORITIZATION][0]
        assert "tpm_agent" in pri_stage.participating_agents


# ============================================================================
# Validation-retry-process loop tests (#278)
# ============================================================================


def _mock_validation_result(accepted=None, rejected=None):
    """Build an InputValidationResult for testing."""
    from src.discovery.models.artifacts import InputRejection, InputValidationResult

    return InputValidationResult(
        accepted_items=accepted or [],
        rejected_items=[
            InputRejection(
                item_id=r["item_id"],
                rejection_reason=r.get("reason", "too vague"),
                rejecting_agent=r.get("agent", "test_agent"),
                suggested_improvement=r.get("suggestion"),
            )
            for r in (rejected or [])
        ],
        token_usage={"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    )


@pytest.mark.slow
class TestValidationRetryBriefs:
    """Tests for _validate_retry_briefs (Stage 2 input validation)."""

    def _create_orchestrator(self, storage=None, transport=None):
        storage = storage or InMemoryStorage()
        transport = transport or InMemoryTransport()
        mock_client = MagicMock()
        orchestrator = DiscoveryOrchestrator(
            db_connection=MagicMock(),
            transport=transport,
            openai_client=mock_client,
            posthog_data={},
            repo_root="/tmp/fake-repo",
        )
        orchestrator.storage = storage
        orchestrator.state_machine.storage = storage
        orchestrator.service.storage = storage
        orchestrator.service.state_machine.storage = storage
        return orchestrator, storage, mock_client

    def _make_briefs(self, count=3):
        return [
            {
                "affected_area": f"area_{i}",
                "problem_statement": f"Problem {i}",
                "evidence": [_evidence()],
                "counterfactual": f"Counter {i}",
                "explorer_coverage": "Reviewed data",
            }
            for i in range(count)
        ]

    def test_all_accepted_passes_through(self):
        """When all briefs are accepted, they pass through unchanged."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(3)
        designer = MagicMock()
        designer.validate_input.return_value = _mock_validation_result(
            accepted=["area_0", "area_1", "area_2"],
        )
        pm = MagicMock()

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        assert len(result) == 3
        assert [b["affected_area"] for b in result] == ["area_0", "area_1", "area_2"]
        pm.reframe_rejected.assert_not_called()

    def test_partial_reject_retry_succeeds(self):
        """Rejected briefs are revised and re-validated."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(3)
        designer = MagicMock()
        # First call: area_1 rejected
        designer.validate_input.side_effect = [
            _mock_validation_result(
                accepted=["area_0", "area_2"],
                rejected=[{"item_id": "area_1", "reason": "too vague"}],
            ),
            # Re-validation of revised brief: accepted
            _mock_validation_result(accepted=["area_1"]),
        ]

        pm = MagicMock()
        pm.reframe_rejected.return_value = _mock_framing_result()
        pm.build_checkpoint_artifacts.return_value = {
            "briefs": [
                {
                    "affected_area": "area_1",
                    "problem_statement": "Revised problem",
                    "evidence": [_evidence()],
                    "counterfactual": "Revised counter",
                    "explorer_coverage": "Reviewed data",
                }
            ]
        }

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        assert len(result) == 3
        pm.reframe_rejected.assert_called_once()
        assert designer.validate_input.call_count == 2

    def test_retry_exhausted_adds_warnings(self):
        """After MAX_VALIDATION_RETRIES, rejected items get validation_warnings."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(3)
        designer = MagicMock()
        # Always reject area_1
        designer.validate_input.return_value = _mock_validation_result(
            accepted=["area_0", "area_2"],
            rejected=[{"item_id": "area_1", "reason": "persistently vague"}],
        )

        pm = MagicMock()
        pm.reframe_rejected.return_value = _mock_framing_result()
        pm.build_checkpoint_artifacts.return_value = {
            "briefs": [
                {
                    "affected_area": "area_1",
                    "problem_statement": "Still vague",
                    "evidence": [_evidence()],
                    "counterfactual": "Counter",
                    "explorer_coverage": "Reviewed data",
                }
            ]
        }

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        # All 3 should be returned: 2 accepted + 1 warned
        assert len(result) == 3
        # Warned item should be at the end
        warned = [b for b in result if b.get("validation_warnings")]
        assert len(warned) == 1
        assert warned[0]["affected_area"] == "area_1"
        assert "persistently vague" in warned[0]["validation_warnings"][0]

    def test_all_rejected_all_warned(self):
        """When all briefs are rejected and stay rejected, all get warnings."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(2)
        designer = MagicMock()
        designer.validate_input.return_value = _mock_validation_result(
            rejected=[
                {"item_id": "area_0", "reason": "vague"},
                {"item_id": "area_1", "reason": "vague"},
            ],
        )

        pm = MagicMock()
        pm.reframe_rejected.return_value = _mock_framing_result()
        pm.build_checkpoint_artifacts.return_value = {
            "briefs": [
                {"affected_area": "area_0", "problem_statement": "P0", "evidence": [], "counterfactual": "C0", "explorer_coverage": "R"},
                {"affected_area": "area_1", "problem_statement": "P1", "evidence": [], "counterfactual": "C1", "explorer_coverage": "R"},
            ]
        }

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        assert len(result) == 2
        assert all(b.get("validation_warnings") for b in result)

    def test_validate_input_exception_accepts_all(self):
        """When validate_input raises, all briefs are accepted (graceful degradation)."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(3)
        designer = MagicMock()
        designer.validate_input.side_effect = RuntimeError("LLM timeout")
        pm = MagicMock()

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        assert len(result) == 3
        assert result == briefs
        pm.reframe_rejected.assert_not_called()

    def test_ordering_accepted_first_warned_last(self):
        """Accepted items preserve original order, warned items appended at end."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(4)  # area_0, area_1, area_2, area_3
        designer = MagicMock()
        # area_1 rejected always
        designer.validate_input.return_value = _mock_validation_result(
            accepted=["area_0", "area_2", "area_3"],
            rejected=[{"item_id": "area_1", "reason": "vague"}],
        )

        pm = MagicMock()
        pm.reframe_rejected.return_value = _mock_framing_result()
        pm.build_checkpoint_artifacts.return_value = {
            "briefs": [{"affected_area": "area_1", "problem_statement": "P", "evidence": [], "counterfactual": "C", "explorer_coverage": "R"}]
        }

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        areas = [b["affected_area"] for b in result]
        # Accepted in original order, warned at end
        assert areas == ["area_0", "area_2", "area_3", "area_1"]

    def test_revised_brief_with_changed_id_replaces_original(self):
        """When reframe_rejected changes affected_area, the old brief is replaced."""
        orchestrator, storage, _ = self._create_orchestrator()

        briefs = self._make_briefs(3)  # area_0, area_1, area_2
        designer = MagicMock()
        # area_1 rejected on first pass, accepted with new ID on second
        designer.validate_input.side_effect = [
            _mock_validation_result(
                accepted=["area_0", "area_2"],
                rejected=[{"item_id": "area_1", "reason": "too broad"}],
            ),
            _mock_validation_result(accepted=["area_1_specific"]),
        ]

        pm = MagicMock()
        pm.reframe_rejected.return_value = _mock_framing_result()
        pm.build_checkpoint_artifacts.return_value = {
            "briefs": [
                {
                    "affected_area": "area_1_specific",
                    "problem_statement": "Revised and specific",
                    "evidence": [_evidence()],
                    "counterfactual": "C",
                    "explorer_coverage": "R",
                }
            ]
        }

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        areas = [b["affected_area"] for b in result]
        # No duplicates: area_1 should be replaced by area_1_specific
        assert "area_1" not in areas
        assert "area_1_specific" in areas
        assert len(result) == 3

    def test_empty_briefs_passes_through(self):
        """Empty briefs list returns empty without calling validate_input."""
        orchestrator, storage, _ = self._create_orchestrator()
        designer = MagicMock()
        pm = MagicMock()

        result = orchestrator._validate_retry_briefs(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=[], explorer_checkpoint={},
        )

        assert result == []
        designer.validate_input.assert_not_called()


@pytest.mark.slow
class TestValidationRetrySolutions:
    """Tests for _validate_retry_solutions (Stage 3 input validation)."""

    def _create_orchestrator(self, storage=None, transport=None):
        storage = storage or InMemoryStorage()
        transport = transport or InMemoryTransport()
        mock_client = MagicMock()
        orchestrator = DiscoveryOrchestrator(
            db_connection=MagicMock(),
            transport=transport,
            openai_client=mock_client,
            posthog_data={},
            repo_root="/tmp/fake-repo",
        )
        orchestrator.storage = storage
        orchestrator.state_machine.storage = storage
        orchestrator.service.storage = storage
        orchestrator.service.state_machine.storage = storage
        return orchestrator, storage, mock_client

    def _make_pairs(self, count=3):
        briefs = [
            {
                "affected_area": f"area_{i}",
                "problem_statement": f"Problem {i}",
                "evidence": [_evidence()],
            }
            for i in range(count)
        ]
        solutions = [
            {
                "proposed_solution": f"Solution {i}",
                "experiment_plan": f"Plan {i}",
                "success_metrics": f"Metric {i}",
                "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                "decision_rationale": f"Rationale {i}",
                "evidence": [_evidence()],
            }
            for i in range(count)
        ]
        return briefs, solutions

    def test_all_accepted(self):
        orchestrator, _, _ = self._create_orchestrator()
        briefs, solutions = self._make_pairs(3)

        feas_designer = MagicMock()
        feas_designer.validate_input.return_value = _mock_validation_result(
            accepted=["area_0", "area_1", "area_2"],
        )
        sol_designer = MagicMock()

        final_b, final_s = orchestrator._validate_retry_solutions(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            feas_designer=feas_designer, sol_designer=sol_designer,
            briefs=briefs, solutions=solutions,
        )

        assert len(final_b) == 3
        assert len(final_s) == 3
        sol_designer.revise_rejected.assert_not_called()

    def test_partial_reject_retry(self):
        orchestrator, _, _ = self._create_orchestrator()
        briefs, solutions = self._make_pairs(3)

        feas_designer = MagicMock()
        feas_designer.validate_input.side_effect = [
            _mock_validation_result(
                accepted=["area_0", "area_2"],
                rejected=[{"item_id": "area_1", "reason": "missing metrics"}],
            ),
            _mock_validation_result(accepted=["area_1"]),
        ]

        sol_designer = MagicMock()
        sol_designer.revise_rejected.return_value = [_mock_solution_design_result()]
        sol_designer.build_checkpoint_artifacts.return_value = {
            "solutions": [
                {
                    "proposed_solution": "Revised solution",
                    "experiment_plan": "Revised plan",
                    "success_metrics": "Better metric",
                    "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                    "decision_rationale": "Revised rationale",
                    "evidence": [_evidence()],
                }
            ]
        }

        final_b, final_s = orchestrator._validate_retry_solutions(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            feas_designer=feas_designer, sol_designer=sol_designer,
            briefs=briefs, solutions=solutions,
        )

        assert len(final_b) == 3
        assert len(final_s) == 3
        sol_designer.revise_rejected.assert_called_once()

    def test_validate_input_exception_accepts_all(self):
        orchestrator, _, _ = self._create_orchestrator()
        briefs, solutions = self._make_pairs(3)

        feas_designer = MagicMock()
        feas_designer.validate_input.side_effect = RuntimeError("Boom")
        sol_designer = MagicMock()

        final_b, final_s = orchestrator._validate_retry_solutions(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            feas_designer=feas_designer, sol_designer=sol_designer,
            briefs=briefs, solutions=solutions,
        )

        assert final_b == briefs
        assert final_s == solutions

    def test_fewer_solutions_than_briefs_preserves_all_briefs(self):
        """Regression: briefs without matching solutions must not be dropped."""
        orchestrator, _, _ = self._create_orchestrator()
        briefs = [
            {"affected_area": f"area_{i}", "problem_statement": f"P{i}", "evidence": [_evidence()]}
            for i in range(5)
        ]
        solutions = [
            {
                "proposed_solution": f"Sol {i}",
                "experiment_plan": f"Plan {i}",
                "success_metrics": f"Metric {i}",
                "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                "decision_rationale": f"Rationale {i}",
                "evidence": [_evidence()],
            }
            for i in range(3)  # only 3 solutions for 5 briefs
        ]

        feas_designer = MagicMock()
        feas_designer.validate_input.return_value = _mock_validation_result(
            accepted=["area_0", "area_1", "area_2", "area_3", "area_4"],
        )
        sol_designer = MagicMock()

        final_b, final_s = orchestrator._validate_retry_solutions(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            feas_designer=feas_designer, sol_designer=sol_designer,
            briefs=briefs, solutions=solutions,
        )

        assert len(final_b) == 5, f"Expected 5 briefs, got {len(final_b)}"
        assert len(final_s) == 5, f"Expected 5 solutions, got {len(final_s)}"
        # Briefs beyond solutions should get empty solution dicts
        assert final_s[3] == {}
        assert final_s[4] == {}
        assert final_b[3]["affected_area"] == "area_3"
        assert final_b[4]["affected_area"] == "area_4"


@pytest.mark.slow
class TestValidationRetryPackages:
    """Tests for _validate_retry_packages (Stage 4 input validation)."""

    def _create_orchestrator(self, storage=None, transport=None):
        storage = storage or InMemoryStorage()
        transport = transport or InMemoryTransport()
        mock_client = MagicMock()
        orchestrator = DiscoveryOrchestrator(
            db_connection=MagicMock(),
            transport=transport,
            openai_client=mock_client,
            posthog_data={},
            repo_root="/tmp/fake-repo",
        )
        orchestrator.storage = storage
        orchestrator.state_machine.storage = storage
        orchestrator.service.storage = storage
        orchestrator.service.state_machine.storage = storage
        return orchestrator, storage, mock_client

    def _make_packages(self, count=3):
        return [
            {
                "opportunity_id": f"opp_{i}",
                "opportunity_brief": {"affected_area": f"opp_{i}", "problem_statement": f"P{i}"},
                "solution_brief": {"proposed_solution": f"S{i}"},
                "technical_spec": {
                    "opportunity_id": f"opp_{i}",
                    "approach": f"Approach {i}",
                    "effort_estimate": "1 week",
                    "dependencies": "None",
                    "risks": [],
                    "acceptance_criteria": f"Criteria {i}",
                },
            }
            for i in range(count)
        ]

    def test_all_accepted(self):
        orchestrator, _, _ = self._create_orchestrator()
        packages = self._make_packages(3)

        tpm = MagicMock()
        tpm.validate_input.return_value = _mock_validation_result(
            accepted=["opp_0", "opp_1", "opp_2"],
        )
        feas_designer = MagicMock()

        result = orchestrator._validate_retry_packages(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            tpm=tpm, feas_designer=feas_designer,
            packages=packages, solution_map={},
        )

        assert len(result) == 3
        feas_designer.revise_rejected.assert_not_called()

    def test_partial_reject_retry(self):
        orchestrator, _, _ = self._create_orchestrator()
        packages = self._make_packages(3)

        tpm = MagicMock()
        tpm.validate_input.side_effect = [
            _mock_validation_result(
                accepted=["opp_0", "opp_2"],
                rejected=[{"item_id": "opp_1", "reason": "incomplete spec"}],
            ),
            _mock_validation_result(accepted=["opp_1"]),
        ]

        feas_designer = MagicMock()
        feas_designer.revise_rejected.return_value = [_mock_feasibility_result()]
        feas_designer.build_checkpoint_artifacts.return_value = {
            "specs": [
                {
                    "opportunity_id": "opp_1",
                    "approach": "Revised approach",
                    "effort_estimate": "2 weeks",
                    "dependencies": "None",
                    "risks": [],
                    "acceptance_criteria": "Better criteria",
                }
            ],
            "infeasible_solutions": [],
        }

        result = orchestrator._validate_retry_packages(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            tpm=tpm, feas_designer=feas_designer,
            packages=packages, solution_map={},
        )

        assert len(result) == 3
        feas_designer.revise_rejected.assert_called_once()

    def test_validate_input_exception_accepts_all(self):
        orchestrator, _, _ = self._create_orchestrator()
        packages = self._make_packages(3)

        tpm = MagicMock()
        tpm.validate_input.side_effect = RuntimeError("Crash")
        feas_designer = MagicMock()

        result = orchestrator._validate_retry_packages(
            run_id=UUID("00000000-0000-0000-0000-000000000001"), convo_id="test-convo", stage_execution_id=1,
            tpm=tpm, feas_designer=feas_designer,
            packages=packages, solution_map={},
        )

        assert result == packages


@pytest.mark.slow
class TestValidationGeneral:
    """General validation tests: constant, events, invocations."""

    def test_max_validation_retries_is_two(self):
        from src.discovery.orchestrator import MAX_VALIDATION_RETRIES
        assert MAX_VALIDATION_RETRIES == 2

    def test_post_validation_event_called(self):
        """INPUT_VALIDATION events are posted during validation."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        mock_client = MagicMock()
        orchestrator = DiscoveryOrchestrator(
            db_connection=MagicMock(),
            transport=transport,
            openai_client=mock_client,
            posthog_data={},
            repo_root="/tmp/fake-repo",
        )
        orchestrator.storage = storage
        orchestrator.state_machine.storage = storage
        orchestrator.service.storage = storage
        orchestrator.service.state_machine.storage = storage

        validation = _mock_validation_result(
            accepted=["a", "b"],
            rejected=[{"item_id": "c", "reason": "bad"}],
        )

        # post_event won't fail — InMemoryTransport handles it
        orchestrator._post_validation_event("test-convo", "test_agent", 0, validation)

        # Verify event was posted via transport
        turns = transport.read_turns("test-convo")
        assert len(turns) == 1
        assert "input:validation" in turns[0]["text"]

    def test_record_invocation_for_validation(self):
        """_record_invocation is called for validation LLM calls."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        mock_client = MagicMock()
        orchestrator = DiscoveryOrchestrator(
            db_connection=MagicMock(),
            transport=transport,
            openai_client=mock_client,
            posthog_data={},
            repo_root="/tmp/fake-repo",
        )
        orchestrator.storage = storage
        orchestrator.state_machine.storage = storage
        orchestrator.service.storage = storage
        orchestrator.service.state_machine.storage = storage

        briefs = [
            {"affected_area": "a", "problem_statement": "P", "evidence": [], "counterfactual": "C", "explorer_coverage": "R"},
        ]
        designer = MagicMock()
        designer.validate_input.return_value = _mock_validation_result(accepted=["a"])
        pm = MagicMock()

        # Create a mock run + stage execution for invocation recording
        from uuid import uuid4
        run_id = uuid4()

        orchestrator._validate_retry_briefs(
            run_id=run_id, convo_id="test-convo", stage_execution_id=1,
            designer=designer, pm=pm, briefs=briefs, explorer_checkpoint={},
        )

        # Should have recorded 1 invocation (the validate_input call)
        invocations = [inv for inv in storage.agent_invocations
                       if inv.agent_name == "solution_designer_validate"]
        assert len(invocations) == 1
