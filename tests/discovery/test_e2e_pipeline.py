"""End-to-end integration test for the Discovery Engine pipeline.

Exercises all 6 stages (Stage 0→5) with mocked LLM responses, verifying:
- State machine transitions
- Checkpoint Pydantic validation via ConversationService
- Evidence traceability across stages
- Prior checkpoint accumulation
- Send-back (backward) flow

Uses InMemoryStorage and InMemoryTransport — no database or real APIs.

Issue #225.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
    FeasibilityAssessment,
    ReviewDecisionType,
    RunStatus,
    SourceType,
    StageStatus,
    StageType,
    STAGE_ORDER,
)
from src.discovery.models.artifacts import (
    ExplorerCheckpoint,
    FeasibilityRiskCheckpoint,
    HumanReviewCheckpoint,
    OpportunityFramingCheckpoint,
    PrioritizationCheckpoint,
    SolutionValidationCheckpoint,
)
from src.discovery.services.conversation import ConversationService
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import InMemoryTransport
from src.discovery.services.explorer_merge import merge_explorer_results
from src.discovery.agents.base import ExplorerResult

# Reuse InMemoryStorage from the conversation service tests
from tests.discovery.test_conversation_service import InMemoryStorage


# ============================================================================
# Helpers — valid artifact builders
# ============================================================================

NOW = datetime.now(timezone.utc).isoformat()


def _evidence(source_type: SourceType, source_id: str) -> Dict[str, Any]:
    """Build a valid EvidencePointer dict."""
    return {
        "source_type": source_type.value,
        "source_id": source_id,
        "retrieved_at": NOW,
        "confidence": ConfidenceLevel.HIGH.value,
    }


def _explorer_finding(
    source_type: SourceType,
    pattern_name: str,
    source_id: str,
) -> Dict[str, Any]:
    """Build a valid ExplorerFinding dict."""
    return {
        "pattern_name": pattern_name,
        "description": f"Finding from {source_type.value}: {pattern_name}",
        "evidence": [_evidence(source_type, source_id)],
        "confidence": ConfidenceLevel.HIGH.value,
        "severity_assessment": "medium",
        "affected_users_estimate": "~100 users",
    }


def _make_explorer_result(
    agent_name: str,
    source_type: SourceType,
    pattern_name: str,
    source_id: str,
) -> ExplorerResult:
    """Build an ExplorerResult with one finding."""
    return ExplorerResult(
        findings=[_explorer_finding(source_type, pattern_name, source_id)],
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        coverage={
            "time_window_days": 14,
            "conversations_available": 50,
            "conversations_reviewed": 45,
            "conversations_skipped": 5,
        },
    )


# ============================================================================
# E2E Pipeline Test
# ============================================================================


@pytest.mark.slow
class TestE2EPipeline:
    """Full Stage 0→5 pipeline exercise with checkpoint validation."""

    def _setup_pipeline(self):
        """Wire up storage, transport, state machine, and conversation service."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        state_machine = DiscoveryStateMachine(storage=storage)
        service = ConversationService(
            transport=transport,
            storage=storage,
            state_machine=state_machine,
        )
        return storage, transport, state_machine, service

    def test_full_stage_0_to_5_pipeline(self):
        """Happy path: 2 opportunities, 1 infeasible at Stage 3, pipeline completes."""
        storage, transport, state_machine, service = self._setup_pipeline()

        # ── Create and start run ──────────────────────────────────────
        run = state_machine.create_run()
        run_id = run.id
        assert run.status == RunStatus.PENDING

        run = state_machine.start_run(run_id)
        assert run.status == RunStatus.RUNNING
        assert run.current_stage == StageType.EXPLORATION

        # ── Stage 0: EXPLORATION ──────────────────────────────────────
        active = storage.get_active_stage(run_id)
        assert active is not None
        assert active.stage == StageType.EXPLORATION

        convo_0 = service.create_stage_conversation(run_id, active.id)

        # Build 4 explorer results (one per explorer)
        results = [
            ("customer_voice", _make_explorer_result(
                "customer_voice", SourceType.INTERCOM, "checkout_confusion", "conv_101"
            )),
            ("codebase_explorer", _make_explorer_result(
                "codebase_explorer", SourceType.CODEBASE, "nav_dead_code", "src/nav.py:42"
            )),
            ("analytics_explorer", _make_explorer_result(
                "analytics_explorer", SourceType.POSTHOG, "funnel_drop", "funnel_checkout_v2"
            )),
            ("research_explorer", _make_explorer_result(
                "research_explorer", SourceType.RESEARCH, "competitor_feature", "doc_ux_study_2024"
            )),
        ]

        merged = merge_explorer_results(results)

        # Validate merged checkpoint passes Pydantic
        ExplorerCheckpoint(**merged)

        assert len(merged["findings"]) == 4
        assert merged["coverage"]["conversations_reviewed"] == 180  # 45 * 4

        # Submit and advance
        new_stage = service.submit_checkpoint(convo_0, run_id, "merged", artifacts=merged)
        assert new_stage.stage == StageType.OPPORTUNITY_FRAMING

        # Prior checkpoints: 1 (exploration)
        priors = service.get_prior_checkpoints(run_id)
        prior_stages = [p["stage"] for p in priors if p["artifacts"]]
        assert StageType.EXPLORATION.value in prior_stages

        # ── Stage 1: OPPORTUNITY FRAMING ──────────────────────────────
        convo_1 = service.create_stage_conversation(run_id, new_stage.id)

        opp_framing = {
            "schema_version": 1,
            "briefs": [
                {
                    "problem_statement": "Checkout flow confuses users, causing cart abandonment",
                    "evidence": [
                        _evidence(SourceType.INTERCOM, "conv_101"),
                        _evidence(SourceType.POSTHOG, "funnel_checkout_v2"),
                    ],
                    "counterfactual": "If simplified, conversion rate increases 15%",
                    "affected_area": "checkout",
                    "explorer_coverage": "Intercom 14d + PostHog funnels",
                },
                {
                    "problem_statement": "Navigation dead code causes slow page loads",
                    "evidence": [
                        _evidence(SourceType.CODEBASE, "src/nav.py:42"),
                    ],
                    "counterfactual": "If cleaned, page load drops by 200ms",
                    "affected_area": "navigation",
                    "explorer_coverage": "Codebase analysis",
                },
            ],
            "framing_metadata": {
                "explorer_findings_count": 4,
                "opportunities_identified": 2,
                "model": "gpt-4o-mini",
            },
        }

        OpportunityFramingCheckpoint(**opp_framing)

        new_stage = service.submit_checkpoint(convo_1, run_id, "opportunity_pm", artifacts=opp_framing)
        assert new_stage.stage == StageType.SOLUTION_VALIDATION

        # Prior checkpoints: 2 (exploration, opportunity_framing)
        priors = service.get_prior_checkpoints(run_id)
        assert len([p for p in priors if p["artifacts"]]) >= 2

        # ── Stage 2: SOLUTION VALIDATION ──────────────────────────────
        convo_2 = service.create_stage_conversation(run_id, new_stage.id)

        sol_validation = {
            "schema_version": 1,
            "solutions": [
                {
                    "proposed_solution": "Simplify checkout to 2-step flow",
                    "experiment_plan": "A/B test with 10% of users for 2 weeks",
                    "success_metrics": "Cart abandonment drops from 68% to 55%",
                    "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                    "evidence": [
                        _evidence(SourceType.INTERCOM, "conv_101"),
                        _evidence(SourceType.POSTHOG, "funnel_checkout_v2"),
                    ],
                },
                {
                    "proposed_solution": "Remove dead navigation modules",
                    "experiment_plan": "Deploy to staging, measure load time",
                    "success_metrics": "Page load time decreases by 200ms",
                    "build_experiment_decision": BuildExperimentDecision.BUILD_WITH_METRICS.value,
                    "evidence": [
                        _evidence(SourceType.CODEBASE, "src/nav.py:42"),
                    ],
                },
            ],
            "design_metadata": {
                "opportunity_briefs_processed": 2,
                "solutions_produced": 2,
                "total_dialogue_rounds": 3,
                "total_token_usage": {
                    "prompt_tokens": 500,
                    "completion_tokens": 300,
                    "total_tokens": 800,
                },
                "model": "gpt-4o-mini",
            },
        }

        SolutionValidationCheckpoint(**sol_validation)

        new_stage = service.submit_checkpoint(convo_2, run_id, "solution_designer", artifacts=sol_validation)
        assert new_stage.stage == StageType.FEASIBILITY_RISK

        # ── Stage 3: FEASIBILITY + RISK ───────────────────────────────
        convo_3 = service.create_stage_conversation(run_id, new_stage.id)

        # checkout is feasible, navigation is infeasible
        feasibility = {
            "schema_version": 1,
            "specs": [
                {
                    "opportunity_id": "checkout",
                    "approach": "Refactor CheckoutForm into 2-step wizard component",
                    "effort_estimate": "5-8 days, high confidence",
                    "dependencies": "Design system button component update",
                    "risks": [
                        {
                            "description": "Payment integration might break during refactor",
                            "severity": "high",
                            "mitigation": "Feature flag rollout with fallback to old flow",
                        },
                    ],
                    "acceptance_criteria": "User completes checkout in <= 2 steps, no payment errors",
                },
            ],
            "infeasible_solutions": [
                {
                    "opportunity_id": "navigation",
                    "solution_summary": "Remove dead navigation modules",
                    "feasibility_assessment": FeasibilityAssessment.INFEASIBLE.value,
                    "infeasibility_reason": "Navigation modules are loaded dynamically by 3rd-party plugins — removal breaks plugin API contract",
                    "constraints_identified": [
                        "Plugin API v2 dependency",
                        "No migration path for existing plugins",
                    ],
                },
            ],
            "feasibility_metadata": {
                "solutions_assessed": 2,
                "feasible_count": 1,
                "infeasible_count": 1,
                "total_dialogue_rounds": 4,
                "total_token_usage": {
                    "prompt_tokens": 600,
                    "completion_tokens": 400,
                    "total_tokens": 1000,
                },
                "model": "gpt-4o-mini",
            },
        }

        FeasibilityRiskCheckpoint(**feasibility)

        new_stage = service.submit_checkpoint(convo_3, run_id, "feasibility_designer", artifacts=feasibility)
        assert new_stage.stage == StageType.PRIORITIZATION

        # ── Stage 4: PRIORITIZATION ───────────────────────────────────
        convo_4 = service.create_stage_conversation(run_id, new_stage.id)

        # Only checkout made it through — navigation was infeasible
        prioritization = {
            "schema_version": 1,
            "rankings": [
                {
                    "opportunity_id": "checkout",
                    "recommended_rank": 1,
                    "rationale": "High user impact, feasible within sprint, strong evidence from both Intercom and PostHog",
                    "dependencies": [],
                    "flags": [],
                },
            ],
            "prioritization_metadata": {
                "opportunities_ranked": 1,
                "model": "gpt-4o-mini",
            },
        }

        PrioritizationCheckpoint(**prioritization)

        new_stage = service.submit_checkpoint(convo_4, run_id, "tpm_agent", artifacts=prioritization)
        assert new_stage.stage == StageType.HUMAN_REVIEW

        # Prior checkpoints: 5 (stages 0-4)
        priors = service.get_prior_checkpoints(run_id)
        stages_with_artifacts = [p["stage"] for p in priors if p["artifacts"]]
        assert len(stages_with_artifacts) == 5

        # ── Stage 5: HUMAN REVIEW ─────────────────────────────────────
        convo_5 = service.create_stage_conversation(run_id, new_stage.id)

        human_review = {
            "schema_version": 1,
            "decisions": [
                {
                    "opportunity_id": "checkout",
                    "decision": ReviewDecisionType.ACCEPTED.value,
                    "reasoning": "Strong evidence, clear experiment plan, manageable risk with feature flag approach",
                },
            ],
            "review_metadata": {
                "reviewer": "test_pm",
                "opportunities_reviewed": 1,
            },
        }

        HumanReviewCheckpoint(**human_review)

        completed_run = service.complete_with_checkpoint(convo_5, run_id, "human_reviewer", artifacts=human_review)
        assert completed_run.status == RunStatus.COMPLETED
        assert completed_run.completed_at is not None

        # Final check: all 6 stages have artifacts
        priors = service.get_prior_checkpoints(run_id)
        stages_with_artifacts = [p["stage"] for p in priors if p["artifacts"]]
        assert len(stages_with_artifacts) == 6

        # Verify evidence source_type traceability through the chain
        # Stage 0 findings should carry source_type from each explorer
        exploration_cp = None
        for p in priors:
            if p["stage"] == StageType.EXPLORATION.value:
                exploration_cp = p["artifacts"]
                break
        assert exploration_cp is not None
        source_types_in_exploration = {
            f["evidence"][0]["source_type"] for f in exploration_cp["findings"]
        }
        assert source_types_in_exploration == {
            SourceType.INTERCOM.value,
            SourceType.CODEBASE.value,
            SourceType.POSTHOG.value,
            SourceType.RESEARCH.value,
        }

        # Stage 5 decision should reference checkout (the feasible one)
        hr_cp = None
        for p in priors:
            if p["stage"] == StageType.HUMAN_REVIEW.value:
                hr_cp = p["artifacts"]
                break
        assert hr_cp is not None
        assert len(hr_cp["decisions"]) == 1
        assert hr_cp["decisions"][0]["opportunity_id"] == "checkout"
        assert hr_cp["decisions"][0]["decision"] == ReviewDecisionType.ACCEPTED.value

    def test_send_back_from_feasibility(self):
        """Backward flow: Stage 3 sends back to Stage 2, then pipeline resumes forward."""
        storage, transport, state_machine, service = self._setup_pipeline()

        # Create and start run, advance through stages 0-2
        run = state_machine.create_run()
        run_id = run.id
        state_machine.start_run(run_id)

        # Stage 0: minimal valid exploration
        active = storage.get_active_stage(run_id)
        convo_0 = service.create_stage_conversation(run_id, active.id)

        explorer_cp = {
            "schema_version": 1,
            "agent_name": "test_explorer",
            "findings": [
                _explorer_finding(SourceType.INTERCOM, "auth_issue", "conv_200"),
            ],
            "coverage": {
                "time_window_days": 14,
                "conversations_available": 100,
                "conversations_reviewed": 90,
                "conversations_skipped": 10,
                "model": "gpt-4o-mini",
                "findings_count": 1,
            },
        }

        new_stage = service.submit_checkpoint(convo_0, run_id, "test_explorer", artifacts=explorer_cp)
        assert new_stage.stage == StageType.OPPORTUNITY_FRAMING

        # Stage 1: one opportunity
        convo_1 = service.create_stage_conversation(run_id, new_stage.id)
        opp_framing = {
            "schema_version": 1,
            "briefs": [
                {
                    "problem_statement": "Auth flow is confusing",
                    "evidence": [_evidence(SourceType.INTERCOM, "conv_200")],
                    "counterfactual": "If fixed, support tickets drop 30%",
                    "affected_area": "authentication",
                    "explorer_coverage": "Intercom 14d",
                },
            ],
            "framing_metadata": {
                "explorer_findings_count": 1,
                "opportunities_identified": 1,
                "model": "gpt-4o-mini",
            },
        }
        new_stage = service.submit_checkpoint(convo_1, run_id, "opportunity_pm", artifacts=opp_framing)
        assert new_stage.stage == StageType.SOLUTION_VALIDATION

        # Stage 2: first attempt
        convo_2 = service.create_stage_conversation(run_id, new_stage.id)
        sol_validation = {
            "schema_version": 1,
            "solutions": [
                {
                    "proposed_solution": "Add OAuth2 SSO integration",
                    "experiment_plan": "Deploy to 5% of enterprise accounts",
                    "success_metrics": "Auth-related tickets drop 30%",
                    "build_experiment_decision": BuildExperimentDecision.BUILD_WITH_METRICS.value,
                    "evidence": [_evidence(SourceType.INTERCOM, "conv_200")],
                },
            ],
            "design_metadata": {
                "opportunity_briefs_processed": 1,
                "solutions_produced": 1,
                "total_dialogue_rounds": 2,
                "total_token_usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
                "model": "gpt-4o-mini",
            },
        }
        new_stage = service.submit_checkpoint(convo_2, run_id, "solution_designer", artifacts=sol_validation)
        assert new_stage.stage == StageType.FEASIBILITY_RISK

        # Stage 3: feasibility assessment — but we send back instead of advancing
        convo_3 = service.create_stage_conversation(run_id, new_stage.id)

        # Send back to solution_validation
        sent_back_stage = state_machine.send_back(
            run_id,
            StageType.SOLUTION_VALIDATION,
            reason="OAuth2 requires enterprise IdP configuration we don't control — needs alternative approach",
        )

        assert sent_back_stage.stage == StageType.SOLUTION_VALIDATION
        assert sent_back_stage.attempt_number == 2
        assert sent_back_stage.sent_back_from == StageType.FEASIBILITY_RISK
        assert sent_back_stage.send_back_reason is not None
        assert "OAuth2" in sent_back_stage.send_back_reason

        # Stage 2 (attempt 2): revised solution
        convo_2b = service.create_stage_conversation(run_id, sent_back_stage.id)
        sol_validation_v2 = {
            "schema_version": 1,
            "solutions": [
                {
                    "proposed_solution": "Add magic-link passwordless auth",
                    "experiment_plan": "A/B test magic link vs current login for 2 weeks",
                    "success_metrics": "Auth-related tickets drop 30%, login success rate > 95%",
                    "build_experiment_decision": BuildExperimentDecision.EXPERIMENT_FIRST.value,
                    "evidence": [_evidence(SourceType.INTERCOM, "conv_200")],
                },
            ],
            "design_metadata": {
                "opportunity_briefs_processed": 1,
                "solutions_produced": 1,
                "total_dialogue_rounds": 2,
                "total_token_usage": {"prompt_tokens": 250, "completion_tokens": 120, "total_tokens": 370},
                "model": "gpt-4o-mini",
            },
        }
        new_stage = service.submit_checkpoint(convo_2b, run_id, "solution_designer", artifacts=sol_validation_v2)
        assert new_stage.stage == StageType.FEASIBILITY_RISK

        # Stage 3 (attempt 2): now feasible
        convo_3b = service.create_stage_conversation(run_id, new_stage.id)
        feasibility = {
            "schema_version": 1,
            "specs": [
                {
                    "opportunity_id": "authentication",
                    "approach": "Magic link via email with TOTP fallback",
                    "effort_estimate": "3-5 days",
                    "dependencies": "Email transactional service",
                    "risks": [
                        {
                            "description": "Email delivery latency",
                            "severity": "medium",
                            "mitigation": "Show countdown + resend option",
                        },
                    ],
                    "acceptance_criteria": "User logs in via magic link within 60 seconds",
                },
            ],
            "infeasible_solutions": [],
            "feasibility_metadata": {
                "solutions_assessed": 1,
                "feasible_count": 1,
                "infeasible_count": 0,
                "total_dialogue_rounds": 2,
                "total_token_usage": {"prompt_tokens": 300, "completion_tokens": 200, "total_tokens": 500},
                "model": "gpt-4o-mini",
            },
        }
        new_stage = service.submit_checkpoint(convo_3b, run_id, "feasibility_designer", artifacts=feasibility)
        assert new_stage.stage == StageType.PRIORITIZATION

        # Stage 4: prioritization
        convo_4 = service.create_stage_conversation(run_id, new_stage.id)
        prioritization = {
            "schema_version": 1,
            "rankings": [
                {
                    "opportunity_id": "authentication",
                    "recommended_rank": 1,
                    "rationale": "Clear user pain point with feasible solution",
                    "dependencies": [],
                    "flags": [],
                },
            ],
            "prioritization_metadata": {
                "opportunities_ranked": 1,
                "model": "gpt-4o-mini",
            },
        }
        new_stage = service.submit_checkpoint(convo_4, run_id, "tpm_agent", artifacts=prioritization)
        assert new_stage.stage == StageType.HUMAN_REVIEW

        # Stage 5: human review
        convo_5 = service.create_stage_conversation(run_id, new_stage.id)
        human_review = {
            "schema_version": 1,
            "decisions": [
                {
                    "opportunity_id": "authentication",
                    "decision": ReviewDecisionType.ACCEPTED.value,
                    "reasoning": "Revised approach is feasible and addresses original pain point",
                },
            ],
            "review_metadata": {
                "reviewer": "test_pm",
                "opportunities_reviewed": 1,
            },
        }
        completed_run = service.complete_with_checkpoint(convo_5, run_id, "human_reviewer", artifacts=human_review)
        assert completed_run.status == RunStatus.COMPLETED

        # Verify we have multiple solution_validation attempts
        sol_stages = storage.get_stage_executions_for_run(run_id, stage=StageType.SOLUTION_VALIDATION)
        assert len(sol_stages) == 2
        assert sol_stages[0].attempt_number == 1
        assert sol_stages[1].attempt_number == 2

        # Verify the sent_back feasibility stage
        feas_stages = storage.get_stage_executions_for_run(run_id, stage=StageType.FEASIBILITY_RISK)
        assert len(feas_stages) == 2
        sent_back_feas = [s for s in feas_stages if s.status == StageStatus.SENT_BACK]
        assert len(sent_back_feas) == 1


class TestMergeExplorerResults:
    """Unit tests for the merge helper itself."""

    def test_merge_combines_findings(self):
        r1 = _make_explorer_result("a", SourceType.INTERCOM, "pattern_a", "conv_1")
        r2 = _make_explorer_result("b", SourceType.CODEBASE, "pattern_b", "src/foo.py:10")

        merged = merge_explorer_results([("agent_a", r1), ("agent_b", r2)])

        assert len(merged["findings"]) == 2
        assert merged["agent_name"] == "agent_a,agent_b"
        assert merged["coverage"]["conversations_reviewed"] == 90  # 45 * 2
        assert merged["coverage"]["conversations_available"] == 100  # 50 * 2

        # Should pass checkpoint validation
        ExplorerCheckpoint(**merged)

    def test_merge_empty_list(self):
        merged = merge_explorer_results([])

        assert merged["findings"] == []
        assert merged["agent_name"] == "merged"
        assert merged["coverage"]["conversations_reviewed"] == 0

    def test_merge_preserves_source_types(self):
        results = [
            ("cv", _make_explorer_result("cv", SourceType.INTERCOM, "p1", "conv_1")),
            ("ce", _make_explorer_result("ce", SourceType.CODEBASE, "p2", "src/x.py:1")),
            ("ae", _make_explorer_result("ae", SourceType.POSTHOG, "p3", "funnel_1")),
            ("re", _make_explorer_result("re", SourceType.RESEARCH, "p4", "doc_1")),
        ]

        merged = merge_explorer_results(results)

        source_types = {
            f["evidence"][0]["source_type"] for f in merged["findings"]
        }
        assert source_types == {
            SourceType.INTERCOM.value,
            SourceType.CODEBASE.value,
            SourceType.POSTHOG.value,
            SourceType.RESEARCH.value,
        }

    def test_merge_aggregates_tokens(self):
        r1 = _make_explorer_result("a", SourceType.INTERCOM, "p1", "c1")
        r2 = _make_explorer_result("b", SourceType.CODEBASE, "p2", "s1")

        merged = merge_explorer_results([("a", r1), ("b", r2)])

        # Each result has 100 prompt, 50 completion, 150 total
        assert merged["coverage"]["findings_count"] == 2
