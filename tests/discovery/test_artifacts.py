"""Tests for Discovery Engine artifact contract models.

Tests that Pydantic models enforce required fields (output validation)
while allowing extra fields (agents can include more than required).
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.discovery.models.artifacts import (
    CoverageMetadata,
    EvidencePointer,
    ExplorerCheckpoint,
    ExplorerFinding,
    FeasibilityRiskCheckpoint,
    HumanReviewCheckpoint,
    InfeasibleSolution,
    OpportunityBrief,
    PrioritizationCheckpoint,
    PrioritizedOpportunity,
    ReviewDecision,
    RiskItem,
    SolutionBrief,
    TechnicalSpec,
)
from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
    FeasibilityAssessment,
    ReviewDecisionType,
    SourceType,
)


# ============================================================================
# Fixtures
# ============================================================================


def _make_evidence(**overrides) -> dict:
    """Create a valid evidence pointer dict."""
    base = {
        "source_type": "intercom",
        "source_id": "conv_8421",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "confidence": "high",
    }
    base.update(overrides)
    return base


def _make_opportunity_brief(**overrides) -> dict:
    """Create a valid opportunity brief dict."""
    base = {
        "problem_statement": "Users can't navigate the billing workflow effectively",
        "evidence": [_make_evidence()],
        "counterfactual": "If we resolved billing friction, we'd expect 15-20% fewer support contacts",
        "affected_area": "billing",
        "explorer_coverage": "Reviewed 200 Intercom conversations from last 2 weeks",
    }
    base.update(overrides)
    return base


def _make_solution_brief(**overrides) -> dict:
    """Create a valid solution brief dict."""
    base = {
        "proposed_solution": "Consolidate billing flow into step-by-step experience",
        "experiment_plan": "A/B test consolidated flow for enterprise segment",
        "success_metrics": "15% reduction in billing support contacts, 10% improvement in upgrade conversion",
        "build_experiment_decision": "build_slice_and_experiment",
        "evidence": [_make_evidence()],
    }
    base.update(overrides)
    return base


def _make_risk_item(**overrides) -> dict:
    """Create a valid risk item dict."""
    base = {
        "description": "Stripe webhook handling differs across implementations",
        "severity": "medium",
        "mitigation": "Add integration tests for all webhook paths before migration",
    }
    base.update(overrides)
    return base


def _make_technical_spec(**overrides) -> dict:
    """Create a valid technical spec dict."""
    base = {
        "opportunity_id": "opp_billing_friction",
        "approach": "Consolidate three billing form implementations into shared component",
        "effort_estimate": "2 weeks +/- 3 days",
        "dependencies": "Payment module test coverage must be added first",
        "risks": [_make_risk_item()],
        "acceptance_criteria": "All billing flows use single implementation, payment tests pass",
    }
    base.update(overrides)
    return base


# ============================================================================
# EvidencePointer tests
# ============================================================================


class TestEvidencePointer:
    def test_valid_evidence_pointer(self):
        ep = EvidencePointer(**_make_evidence())
        assert ep.source_type == SourceType.INTERCOM
        assert ep.source_id == "conv_8421"
        assert ep.confidence == ConfidenceLevel.HIGH

    def test_all_source_types(self):
        for source_type in SourceType:
            ep = EvidencePointer(**_make_evidence(source_type=source_type.value))
            assert ep.source_type == source_type

    def test_all_confidence_levels(self):
        for level in ConfidenceLevel:
            ep = EvidencePointer(**_make_evidence(confidence=level.value))
            assert ep.confidence == level

    def test_missing_source_type_rejected(self):
        data = _make_evidence()
        del data["source_type"]
        with pytest.raises(ValidationError):
            EvidencePointer(**data)

    def test_missing_source_id_rejected(self):
        data = _make_evidence()
        del data["source_id"]
        with pytest.raises(ValidationError):
            EvidencePointer(**data)

    def test_empty_source_id_rejected(self):
        with pytest.raises(ValidationError):
            EvidencePointer(**_make_evidence(source_id=""))

    def test_invalid_source_type_rejected(self):
        with pytest.raises(ValidationError):
            EvidencePointer(**_make_evidence(source_type="invalid_source"))

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValidationError):
            EvidencePointer(**_make_evidence(confidence="very_high"))

    def test_extra_fields_allowed(self):
        """Agents can include additional fields beyond required ones."""
        ep = EvidencePointer(
            **_make_evidence(),
            snippet="User said: billing is confusing",
            page_number=42,
        )
        assert ep.source_type == SourceType.INTERCOM
        assert ep.snippet == "User said: billing is confusing"  # type: ignore[attr-defined]


# ============================================================================
# OpportunityBrief tests
# ============================================================================


class TestOpportunityBrief:
    def test_valid_opportunity_brief(self):
        ob = OpportunityBrief(**_make_opportunity_brief())
        assert ob.schema_version == 1
        assert len(ob.evidence) == 1
        assert ob.evidence[0].source_type == SourceType.INTERCOM

    def test_missing_problem_statement_rejected(self):
        data = _make_opportunity_brief()
        del data["problem_statement"]
        with pytest.raises(ValidationError):
            OpportunityBrief(**data)

    def test_empty_problem_statement_rejected(self):
        with pytest.raises(ValidationError):
            OpportunityBrief(**_make_opportunity_brief(problem_statement=""))

    def test_missing_evidence_rejected(self):
        data = _make_opportunity_brief()
        del data["evidence"]
        with pytest.raises(ValidationError):
            OpportunityBrief(**data)

    def test_empty_evidence_list_rejected(self):
        with pytest.raises(ValidationError):
            OpportunityBrief(**_make_opportunity_brief(evidence=[]))

    def test_missing_counterfactual_rejected(self):
        data = _make_opportunity_brief()
        del data["counterfactual"]
        with pytest.raises(ValidationError):
            OpportunityBrief(**data)

    def test_missing_affected_area_rejected(self):
        data = _make_opportunity_brief()
        del data["affected_area"]
        with pytest.raises(ValidationError):
            OpportunityBrief(**data)

    def test_missing_explorer_coverage_rejected(self):
        data = _make_opportunity_brief()
        del data["explorer_coverage"]
        with pytest.raises(ValidationError):
            OpportunityBrief(**data)

    def test_extra_fields_allowed(self):
        """Agents can include additional fields."""
        ob = OpportunityBrief(
            **_make_opportunity_brief(),
            severity="high",
            user_segments=["enterprise", "small_business"],
        )
        assert ob.problem_statement.startswith("Users")
        assert ob.severity == "high"  # type: ignore[attr-defined]

    def test_schema_version_defaults_to_1(self):
        ob = OpportunityBrief(**_make_opportunity_brief())
        assert ob.schema_version == 1

    def test_multiple_evidence_pointers(self):
        data = _make_opportunity_brief(
            evidence=[
                _make_evidence(source_type="intercom", source_id="conv_1"),
                _make_evidence(source_type="posthog", source_id="funnel_billing"),
                _make_evidence(source_type="codebase", source_id="src/billing/form.py:42"),
            ]
        )
        ob = OpportunityBrief(**data)
        assert len(ob.evidence) == 3
        assert ob.evidence[1].source_type == SourceType.POSTHOG


# ============================================================================
# SolutionBrief tests
# ============================================================================


class TestSolutionBrief:
    def test_valid_solution_brief(self):
        sb = SolutionBrief(**_make_solution_brief())
        assert sb.build_experiment_decision == BuildExperimentDecision.BUILD_SLICE_AND_EXPERIMENT

    def test_all_build_experiment_decisions(self):
        for decision in BuildExperimentDecision:
            sb = SolutionBrief(
                **_make_solution_brief(build_experiment_decision=decision.value)
            )
            assert sb.build_experiment_decision == decision

    def test_missing_proposed_solution_rejected(self):
        data = _make_solution_brief()
        del data["proposed_solution"]
        with pytest.raises(ValidationError):
            SolutionBrief(**data)

    def test_missing_experiment_plan_allowed(self):
        """experiment_plan is Optional (Issue #261: internal engineering may skip experiments)."""
        data = _make_solution_brief()
        del data["experiment_plan"]
        brief = SolutionBrief(**data)
        assert brief.experiment_plan is None

    def test_missing_success_metrics_rejected(self):
        data = _make_solution_brief()
        del data["success_metrics"]
        with pytest.raises(ValidationError):
            SolutionBrief(**data)

    def test_missing_decision_allowed(self):
        """build_experiment_decision is Optional (Issue #261: internal engineering may skip)."""
        data = _make_solution_brief()
        del data["build_experiment_decision"]
        brief = SolutionBrief(**data)
        assert brief.build_experiment_decision is None

    def test_invalid_decision_rejected(self):
        with pytest.raises(ValidationError):
            SolutionBrief(**_make_solution_brief(build_experiment_decision="just_ship_it"))

    def test_extra_fields_allowed(self):
        sb = SolutionBrief(
            **_make_solution_brief(),
            design_mockup_url="https://figma.com/...",
        )
        assert sb.design_mockup_url == "https://figma.com/..."  # type: ignore[attr-defined]


# ============================================================================
# TechnicalSpec tests
# ============================================================================


class TestRiskItem:
    def test_valid_risk_item(self):
        ri = RiskItem(**_make_risk_item())
        assert ri.description == "Stripe webhook handling differs across implementations"
        assert ri.severity == "medium"
        assert ri.mitigation.startswith("Add integration")

    def test_missing_description_rejected(self):
        data = _make_risk_item()
        del data["description"]
        with pytest.raises(ValidationError):
            RiskItem(**data)

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            RiskItem(**_make_risk_item(description=""))

    def test_missing_severity_rejected(self):
        data = _make_risk_item()
        del data["severity"]
        with pytest.raises(ValidationError):
            RiskItem(**data)

    def test_empty_severity_rejected(self):
        with pytest.raises(ValidationError):
            RiskItem(**_make_risk_item(severity=""))

    def test_missing_mitigation_rejected(self):
        data = _make_risk_item()
        del data["mitigation"]
        with pytest.raises(ValidationError):
            RiskItem(**data)

    def test_empty_mitigation_rejected(self):
        with pytest.raises(ValidationError):
            RiskItem(**_make_risk_item(mitigation=""))

    def test_extra_fields_allowed(self):
        ri = RiskItem(
            **_make_risk_item(),
            likelihood="high",
        )
        assert ri.likelihood == "high"  # type: ignore[attr-defined]


class TestTechnicalSpec:
    def test_valid_technical_spec(self):
        ts = TechnicalSpec(**_make_technical_spec())
        assert len(ts.risks) == 1
        assert ts.schema_version == 1
        assert ts.opportunity_id == "opp_billing_friction"

    def test_missing_opportunity_id_rejected(self):
        data = _make_technical_spec()
        del data["opportunity_id"]
        with pytest.raises(ValidationError):
            TechnicalSpec(**data)

    def test_empty_opportunity_id_rejected(self):
        with pytest.raises(ValidationError):
            TechnicalSpec(**_make_technical_spec(opportunity_id=""))

    def test_missing_approach_rejected(self):
        data = _make_technical_spec()
        del data["approach"]
        with pytest.raises(ValidationError):
            TechnicalSpec(**data)

    def test_missing_effort_estimate_rejected(self):
        data = _make_technical_spec()
        del data["effort_estimate"]
        with pytest.raises(ValidationError):
            TechnicalSpec(**data)

    def test_missing_risks_rejected(self):
        data = _make_technical_spec()
        del data["risks"]
        with pytest.raises(ValidationError):
            TechnicalSpec(**data)

    def test_empty_risks_rejected(self):
        with pytest.raises(ValidationError):
            TechnicalSpec(**_make_technical_spec(risks=[]))

    def test_missing_acceptance_criteria_rejected(self):
        data = _make_technical_spec()
        del data["acceptance_criteria"]
        with pytest.raises(ValidationError):
            TechnicalSpec(**data)

    def test_multiple_risks(self):
        ts = TechnicalSpec(
            **_make_technical_spec(
                risks=[
                    _make_risk_item(description="Stripe webhook handling differs"),
                    _make_risk_item(description="No test coverage on payment module"),
                    _make_risk_item(description="Migration requires downtime window"),
                ]
            )
        )
        assert len(ts.risks) == 3

    def test_invalid_risk_item_rejected(self):
        """RiskItem with empty description inside TechnicalSpec is rejected."""
        with pytest.raises(ValidationError):
            TechnicalSpec(**_make_technical_spec(
                risks=[{"description": "", "severity": "high", "mitigation": "Fix it"}]
            ))

    def test_extra_fields_allowed(self):
        ts = TechnicalSpec(
            **_make_technical_spec(),
            suggested_reviewers=["backend-team"],
            estimated_lines_changed=500,
        )
        assert ts.suggested_reviewers == ["backend-team"]  # type: ignore[attr-defined]


# ============================================================================
# Stage 3: InfeasibleSolution helpers
# ============================================================================


def _make_infeasible_solution(**overrides) -> dict:
    """Create a valid infeasible solution dict."""
    base = {
        "opportunity_id": "opp_billing_friction",
        "solution_summary": "Rebuild billing system from scratch",
        "feasibility_assessment": "infeasible",
        "infeasibility_reason": "Would require 6+ months and full team reallocation",
        "constraints_identified": ["Team capacity", "Migration risk too high"],
    }
    base.update(overrides)
    return base


def _make_feasibility_risk_metadata(**overrides) -> dict:
    """Create a valid feasibility risk metadata dict."""
    base = {
        "solutions_assessed": 2,
        "feasible_count": 1,
        "infeasible_count": 1,
        "total_dialogue_rounds": 4,
        "total_token_usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800},
        "model": "gpt-4o-mini",
    }
    base.update(overrides)
    return base


def _make_feasibility_risk_checkpoint(**overrides) -> dict:
    """Create a valid feasibility risk checkpoint dict."""
    base = {
        "specs": [_make_technical_spec()],
        "infeasible_solutions": [_make_infeasible_solution()],
        "feasibility_metadata": _make_feasibility_risk_metadata(),
    }
    base.update(overrides)
    return base


# ============================================================================
# InfeasibleSolution tests
# ============================================================================


class TestInfeasibleSolution:
    def test_valid_infeasible_solution(self):
        inf = InfeasibleSolution(**_make_infeasible_solution())
        assert inf.opportunity_id == "opp_billing_friction"
        assert inf.feasibility_assessment == FeasibilityAssessment.INFEASIBLE
        assert len(inf.constraints_identified) == 2

    def test_missing_opportunity_id_rejected(self):
        data = _make_infeasible_solution()
        del data["opportunity_id"]
        with pytest.raises(ValidationError):
            InfeasibleSolution(**data)

    def test_empty_opportunity_id_rejected(self):
        with pytest.raises(ValidationError):
            InfeasibleSolution(**_make_infeasible_solution(opportunity_id=""))

    def test_missing_solution_summary_rejected(self):
        data = _make_infeasible_solution()
        del data["solution_summary"]
        with pytest.raises(ValidationError):
            InfeasibleSolution(**data)

    def test_empty_solution_summary_rejected(self):
        with pytest.raises(ValidationError):
            InfeasibleSolution(**_make_infeasible_solution(solution_summary=""))

    def test_missing_infeasibility_reason_rejected(self):
        data = _make_infeasible_solution()
        del data["infeasibility_reason"]
        with pytest.raises(ValidationError):
            InfeasibleSolution(**data)

    def test_empty_infeasibility_reason_rejected(self):
        with pytest.raises(ValidationError):
            InfeasibleSolution(**_make_infeasible_solution(infeasibility_reason=""))

    def test_constraints_default_empty(self):
        data = _make_infeasible_solution()
        del data["constraints_identified"]
        inf = InfeasibleSolution(**data)
        assert inf.constraints_identified == []

    def test_extra_fields_allowed(self):
        inf = InfeasibleSolution(
            **_make_infeasible_solution(),
            alternative_suggestions=["Try incremental migration"],
        )
        assert inf.alternative_suggestions == ["Try incremental migration"]  # type: ignore[attr-defined]


# ============================================================================
# FeasibilityRiskCheckpoint tests
# ============================================================================


class TestFeasibilityRiskCheckpoint:
    def test_valid_checkpoint(self):
        cp = FeasibilityRiskCheckpoint(**_make_feasibility_risk_checkpoint())
        assert cp.schema_version == 1
        assert len(cp.specs) == 1
        assert len(cp.infeasible_solutions) == 1
        assert cp.feasibility_metadata.solutions_assessed == 2

    def test_empty_specs_allowed(self):
        """All solutions infeasible — no specs."""
        cp = FeasibilityRiskCheckpoint(**_make_feasibility_risk_checkpoint(specs=[]))
        assert len(cp.specs) == 0

    def test_empty_infeasible_allowed(self):
        """All solutions feasible — no infeasible records."""
        cp = FeasibilityRiskCheckpoint(**_make_feasibility_risk_checkpoint(
            infeasible_solutions=[]
        ))
        assert len(cp.infeasible_solutions) == 0

    def test_default_specs_is_empty(self):
        data = _make_feasibility_risk_checkpoint()
        del data["specs"]
        cp = FeasibilityRiskCheckpoint(**data)
        assert cp.specs == []

    def test_default_infeasible_is_empty(self):
        data = _make_feasibility_risk_checkpoint()
        del data["infeasible_solutions"]
        cp = FeasibilityRiskCheckpoint(**data)
        assert cp.infeasible_solutions == []

    def test_missing_metadata_rejected(self):
        data = _make_feasibility_risk_checkpoint()
        del data["feasibility_metadata"]
        with pytest.raises(ValidationError):
            FeasibilityRiskCheckpoint(**data)

    def test_invalid_spec_inside_checkpoint_rejected(self):
        data = _make_feasibility_risk_checkpoint(
            specs=[{"opportunity_id": ""}]  # Empty opportunity_id
        )
        with pytest.raises(ValidationError):
            FeasibilityRiskCheckpoint(**data)

    def test_invalid_metadata_rejected(self):
        data = _make_feasibility_risk_checkpoint(
            feasibility_metadata={"solutions_assessed": -1, "feasible_count": 0, "infeasible_count": 0, "total_dialogue_rounds": 0, "model": "gpt-4o-mini"}
        )
        with pytest.raises(ValidationError):
            FeasibilityRiskCheckpoint(**data)

    def test_empty_model_in_metadata_rejected(self):
        data = _make_feasibility_risk_checkpoint(
            feasibility_metadata={"solutions_assessed": 0, "feasible_count": 0, "infeasible_count": 0, "total_dialogue_rounds": 0, "model": ""}
        )
        with pytest.raises(ValidationError):
            FeasibilityRiskCheckpoint(**data)

    def test_extra_fields_allowed(self):
        cp = FeasibilityRiskCheckpoint(
            **_make_feasibility_risk_checkpoint(),
            backward_flow_triggered=True,
        )
        assert cp.backward_flow_triggered is True  # type: ignore[attr-defined]

    def test_schema_version_defaults_to_1(self):
        cp = FeasibilityRiskCheckpoint(**_make_feasibility_risk_checkpoint())
        assert cp.schema_version == 1


# ============================================================================
# Explorer artifact helpers
# ============================================================================


def _make_explorer_finding(**overrides) -> dict:
    """Create a valid explorer finding dict."""
    base = {
        "pattern_name": "timezone-scheduling-confusion",
        "description": "Users schedule posts expecting local time but system uses UTC",
        "evidence": [_make_evidence()],
        "confidence": "high",
        "severity_assessment": "Medium-high: posts go out at wrong times",
        "affected_users_estimate": "~4% of conversations in sample",
    }
    base.update(overrides)
    return base


def _make_coverage_metadata(**overrides) -> dict:
    """Create a valid coverage metadata dict."""
    base = {
        "time_window_days": 14,
        "conversations_available": 450,
        "conversations_reviewed": 200,
        "conversations_skipped": 0,
        "model": "gpt-4o-mini",
        "findings_count": 3,
    }
    base.update(overrides)
    return base


def _make_explorer_checkpoint(**overrides) -> dict:
    """Create a valid explorer checkpoint dict."""
    base = {
        "agent_name": "customer_voice",
        "findings": [_make_explorer_finding()],
        "coverage": _make_coverage_metadata(),
    }
    base.update(overrides)
    return base


# ============================================================================
# ExplorerFinding tests
# ============================================================================


class TestExplorerFinding:
    def test_valid_finding(self):
        f = ExplorerFinding(**_make_explorer_finding())
        assert f.pattern_name == "timezone-scheduling-confusion"
        assert f.confidence == ConfidenceLevel.HIGH
        assert len(f.evidence) == 1

    def test_missing_pattern_name_rejected(self):
        data = _make_explorer_finding()
        del data["pattern_name"]
        with pytest.raises(ValidationError):
            ExplorerFinding(**data)

    def test_empty_pattern_name_rejected(self):
        with pytest.raises(ValidationError):
            ExplorerFinding(**_make_explorer_finding(pattern_name=""))

    def test_missing_description_rejected(self):
        data = _make_explorer_finding()
        del data["description"]
        with pytest.raises(ValidationError):
            ExplorerFinding(**data)

    def test_missing_evidence_rejected(self):
        data = _make_explorer_finding()
        del data["evidence"]
        with pytest.raises(ValidationError):
            ExplorerFinding(**data)

    def test_empty_evidence_rejected(self):
        with pytest.raises(ValidationError):
            ExplorerFinding(**_make_explorer_finding(evidence=[]))

    def test_missing_confidence_rejected(self):
        data = _make_explorer_finding()
        del data["confidence"]
        with pytest.raises(ValidationError):
            ExplorerFinding(**data)

    def test_missing_severity_rejected(self):
        data = _make_explorer_finding()
        del data["severity_assessment"]
        with pytest.raises(ValidationError):
            ExplorerFinding(**data)

    def test_missing_affected_users_rejected(self):
        data = _make_explorer_finding()
        del data["affected_users_estimate"]
        with pytest.raises(ValidationError):
            ExplorerFinding(**data)

    def test_extra_fields_allowed(self):
        f = ExplorerFinding(
            **_make_explorer_finding(),
            related_patterns=["calendar-display-mismatch"],
            reasoning="This is distinct from scheduling_failure...",
        )
        assert f.related_patterns == ["calendar-display-mismatch"]  # type: ignore[attr-defined]

    def test_multiple_evidence_pointers(self):
        data = _make_explorer_finding(
            evidence=[
                _make_evidence(source_id="conv_001"),
                _make_evidence(source_id="conv_002"),
                _make_evidence(source_id="conv_003"),
            ]
        )
        f = ExplorerFinding(**data)
        assert len(f.evidence) == 3


# ============================================================================
# CoverageMetadata tests
# ============================================================================


class TestCoverageMetadata:
    def test_valid_coverage(self):
        cm = CoverageMetadata(**_make_coverage_metadata())
        assert cm.time_window_days == 14
        assert cm.conversations_available == 450
        assert cm.model == "gpt-4o-mini"

    def test_missing_time_window_rejected(self):
        data = _make_coverage_metadata()
        del data["time_window_days"]
        with pytest.raises(ValidationError):
            CoverageMetadata(**data)

    def test_zero_time_window_rejected(self):
        with pytest.raises(ValidationError):
            CoverageMetadata(**_make_coverage_metadata(time_window_days=0))

    def test_negative_conversations_rejected(self):
        with pytest.raises(ValidationError):
            CoverageMetadata(**_make_coverage_metadata(conversations_available=-1))

    def test_missing_model_rejected(self):
        data = _make_coverage_metadata()
        del data["model"]
        with pytest.raises(ValidationError):
            CoverageMetadata(**data)

    def test_empty_model_rejected(self):
        with pytest.raises(ValidationError):
            CoverageMetadata(**_make_coverage_metadata(model=""))

    def test_extra_fields_allowed(self):
        cm = CoverageMetadata(
            **_make_coverage_metadata(),
            batches_processed=10,
        )
        assert cm.batches_processed == 10  # type: ignore[attr-defined]


# ============================================================================
# ExplorerCheckpoint tests
# ============================================================================


class TestExplorerCheckpoint:
    def test_valid_checkpoint(self):
        cp = ExplorerCheckpoint(**_make_explorer_checkpoint())
        assert cp.agent_name == "customer_voice"
        assert cp.schema_version == 1
        assert len(cp.findings) == 1
        assert cp.coverage.conversations_available == 450

    def test_missing_agent_name_rejected(self):
        data = _make_explorer_checkpoint()
        del data["agent_name"]
        with pytest.raises(ValidationError):
            ExplorerCheckpoint(**data)

    def test_empty_agent_name_rejected(self):
        with pytest.raises(ValidationError):
            ExplorerCheckpoint(**_make_explorer_checkpoint(agent_name=""))

    def test_missing_coverage_rejected(self):
        data = _make_explorer_checkpoint()
        del data["coverage"]
        with pytest.raises(ValidationError):
            ExplorerCheckpoint(**data)

    def test_empty_findings_allowed(self):
        """Explorer may find nothing — that's a valid result."""
        cp = ExplorerCheckpoint(**_make_explorer_checkpoint(findings=[]))
        assert len(cp.findings) == 0

    def test_default_findings_is_empty(self):
        data = _make_explorer_checkpoint()
        del data["findings"]
        cp = ExplorerCheckpoint(**data)
        assert cp.findings == []

    def test_invalid_finding_inside_checkpoint_rejected(self):
        data = _make_explorer_checkpoint(
            findings=[{"pattern_name": ""}]  # Empty pattern_name
        )
        with pytest.raises(ValidationError):
            ExplorerCheckpoint(**data)

    def test_invalid_coverage_inside_checkpoint_rejected(self):
        data = _make_explorer_checkpoint(
            coverage={"time_window_days": 0}  # Below minimum
        )
        with pytest.raises(ValidationError):
            ExplorerCheckpoint(**data)

    def test_extra_fields_allowed(self):
        cp = ExplorerCheckpoint(
            **_make_explorer_checkpoint(),
            run_duration_seconds=45.2,
        )
        assert cp.run_duration_seconds == 45.2  # type: ignore[attr-defined]

    def test_schema_version_defaults_to_1(self):
        cp = ExplorerCheckpoint(**_make_explorer_checkpoint())
        assert cp.schema_version == 1

    def test_multiple_findings(self):
        data = _make_explorer_checkpoint(
            findings=[
                _make_explorer_finding(pattern_name="pattern-1"),
                _make_explorer_finding(pattern_name="pattern-2"),
                _make_explorer_finding(pattern_name="pattern-3"),
            ]
        )
        cp = ExplorerCheckpoint(**data)
        assert len(cp.findings) == 3


# ============================================================================
# Stage 4: Prioritization artifact helpers
# ============================================================================


def _make_prioritized_opportunity(**overrides) -> dict:
    """Create a valid prioritized opportunity dict."""
    base = {
        "opportunity_id": "opp_billing_friction",
        "recommended_rank": 1,
        "rationale": "High impact, low effort, addresses top support driver",
        "dependencies": ["opp_payment_module"],
        "flags": ["touches payment system with known fragilities"],
    }
    base.update(overrides)
    return base


def _make_prioritization_metadata(**overrides) -> dict:
    """Create a valid prioritization metadata dict."""
    base = {
        "opportunities_ranked": 3,
        "model": "gpt-4o-mini",
    }
    base.update(overrides)
    return base


def _make_prioritization_checkpoint(**overrides) -> dict:
    """Create a valid prioritization checkpoint dict."""
    base = {
        "rankings": [_make_prioritized_opportunity()],
        "prioritization_metadata": _make_prioritization_metadata(),
    }
    base.update(overrides)
    return base


# ============================================================================
# PrioritizedOpportunity tests
# ============================================================================


class TestPrioritizedOpportunity:
    def test_valid_prioritized_opportunity(self):
        po = PrioritizedOpportunity(**_make_prioritized_opportunity())
        assert po.opportunity_id == "opp_billing_friction"
        assert po.recommended_rank == 1
        assert len(po.dependencies) == 1
        assert len(po.flags) == 1

    def test_missing_opportunity_id_rejected(self):
        data = _make_prioritized_opportunity()
        del data["opportunity_id"]
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**data)

    def test_empty_opportunity_id_rejected(self):
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**_make_prioritized_opportunity(opportunity_id=""))

    def test_missing_recommended_rank_rejected(self):
        data = _make_prioritized_opportunity()
        del data["recommended_rank"]
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**data)

    def test_zero_rank_rejected(self):
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**_make_prioritized_opportunity(recommended_rank=0))

    def test_negative_rank_rejected(self):
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**_make_prioritized_opportunity(recommended_rank=-1))

    def test_missing_rationale_rejected(self):
        data = _make_prioritized_opportunity()
        del data["rationale"]
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**data)

    def test_empty_rationale_rejected(self):
        with pytest.raises(ValidationError):
            PrioritizedOpportunity(**_make_prioritized_opportunity(rationale=""))

    def test_dependencies_default_empty(self):
        data = _make_prioritized_opportunity()
        del data["dependencies"]
        po = PrioritizedOpportunity(**data)
        assert po.dependencies == []

    def test_flags_default_empty(self):
        data = _make_prioritized_opportunity()
        del data["flags"]
        po = PrioritizedOpportunity(**data)
        assert po.flags == []

    def test_extra_fields_allowed(self):
        po = PrioritizedOpportunity(
            **_make_prioritized_opportunity(),
            strategic_alignment="high",
        )
        assert po.strategic_alignment == "high"  # type: ignore[attr-defined]


# ============================================================================
# PrioritizationCheckpoint tests
# ============================================================================


class TestPrioritizationCheckpoint:
    def test_valid_checkpoint(self):
        cp = PrioritizationCheckpoint(**_make_prioritization_checkpoint())
        assert cp.schema_version == 1
        assert len(cp.rankings) == 1
        assert cp.prioritization_metadata.opportunities_ranked == 3

    def test_empty_rankings_allowed(self):
        """Nothing to rank if earlier stages yielded no opportunities."""
        cp = PrioritizationCheckpoint(**_make_prioritization_checkpoint(rankings=[]))
        assert len(cp.rankings) == 0

    def test_default_rankings_is_empty(self):
        data = _make_prioritization_checkpoint()
        del data["rankings"]
        cp = PrioritizationCheckpoint(**data)
        assert cp.rankings == []

    def test_missing_metadata_rejected(self):
        data = _make_prioritization_checkpoint()
        del data["prioritization_metadata"]
        with pytest.raises(ValidationError):
            PrioritizationCheckpoint(**data)

    def test_invalid_ranking_inside_checkpoint_rejected(self):
        data = _make_prioritization_checkpoint(
            rankings=[{"opportunity_id": ""}]  # Empty opportunity_id
        )
        with pytest.raises(ValidationError):
            PrioritizationCheckpoint(**data)

    def test_invalid_metadata_rejected(self):
        data = _make_prioritization_checkpoint(
            prioritization_metadata={"opportunities_ranked": -1, "model": "gpt-4o-mini"}
        )
        with pytest.raises(ValidationError):
            PrioritizationCheckpoint(**data)

    def test_empty_model_in_metadata_rejected(self):
        data = _make_prioritization_checkpoint(
            prioritization_metadata={"opportunities_ranked": 0, "model": ""}
        )
        with pytest.raises(ValidationError):
            PrioritizationCheckpoint(**data)

    def test_multiple_rankings(self):
        data = _make_prioritization_checkpoint(
            rankings=[
                _make_prioritized_opportunity(opportunity_id="opp_1", recommended_rank=1),
                _make_prioritized_opportunity(opportunity_id="opp_2", recommended_rank=2),
                _make_prioritized_opportunity(opportunity_id="opp_3", recommended_rank=3),
            ]
        )
        cp = PrioritizationCheckpoint(**data)
        assert len(cp.rankings) == 3

    def test_extra_fields_allowed(self):
        cp = PrioritizationCheckpoint(
            **_make_prioritization_checkpoint(),
            ranking_algorithm="weighted_multi_factor",
        )
        assert cp.ranking_algorithm == "weighted_multi_factor"  # type: ignore[attr-defined]

    def test_schema_version_defaults_to_1(self):
        cp = PrioritizationCheckpoint(**_make_prioritization_checkpoint())
        assert cp.schema_version == 1


# ============================================================================
# Stage 5: Human Review artifact helpers
# ============================================================================


def _make_review_decision(**overrides) -> dict:
    """Create a valid review decision dict."""
    base = {
        "opportunity_id": "opp_billing_friction",
        "decision": "accepted",
        "reasoning": "High confidence in impact, team has bandwidth",
    }
    base.update(overrides)
    return base


def _make_review_metadata(**overrides) -> dict:
    """Create a valid review metadata dict."""
    base = {
        "reviewer": "paul",
        "opportunities_reviewed": 3,
    }
    base.update(overrides)
    return base


def _make_human_review_checkpoint(**overrides) -> dict:
    """Create a valid human review checkpoint dict."""
    base = {
        "decisions": [_make_review_decision()],
        "review_metadata": _make_review_metadata(),
    }
    base.update(overrides)
    return base


# ============================================================================
# ReviewDecision tests
# ============================================================================


class TestReviewDecision:
    def test_valid_accepted_decision(self):
        rd = ReviewDecision(**_make_review_decision())
        assert rd.decision == ReviewDecisionType.ACCEPTED
        assert rd.adjusted_priority is None
        assert rd.send_back_to_stage is None

    def test_all_simple_decision_types(self):
        """ACCEPTED, REJECTED, DEFERRED don't need conditional fields."""
        for decision_type in ["accepted", "rejected", "deferred"]:
            rd = ReviewDecision(**_make_review_decision(decision=decision_type))
            assert rd.decision == ReviewDecisionType(decision_type)

    def test_valid_priority_adjusted(self):
        rd = ReviewDecision(**_make_review_decision(
            decision="priority_adjusted",
            adjusted_priority=5,
        ))
        assert rd.decision == ReviewDecisionType.PRIORITY_ADJUSTED
        assert rd.adjusted_priority == 5

    def test_valid_sent_back(self):
        rd = ReviewDecision(**_make_review_decision(
            decision="sent_back",
            send_back_to_stage="solution_validation",
        ))
        assert rd.decision == ReviewDecisionType.SENT_BACK
        assert rd.send_back_to_stage == "solution_validation"

    def test_missing_opportunity_id_rejected(self):
        data = _make_review_decision()
        del data["opportunity_id"]
        with pytest.raises(ValidationError):
            ReviewDecision(**data)

    def test_empty_opportunity_id_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecision(**_make_review_decision(opportunity_id=""))

    def test_missing_decision_rejected(self):
        data = _make_review_decision()
        del data["decision"]
        with pytest.raises(ValidationError):
            ReviewDecision(**data)

    def test_invalid_decision_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecision(**_make_review_decision(decision="maybe_later"))

    def test_missing_reasoning_rejected(self):
        data = _make_review_decision()
        del data["reasoning"]
        with pytest.raises(ValidationError):
            ReviewDecision(**data)

    def test_empty_reasoning_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecision(**_make_review_decision(reasoning=""))

    # -- Conditional validation tests --

    def test_priority_adjusted_without_priority_rejected(self):
        with pytest.raises(ValidationError, match="adjusted_priority is required"):
            ReviewDecision(**_make_review_decision(decision="priority_adjusted"))

    def test_sent_back_without_stage_rejected(self):
        with pytest.raises(ValidationError, match="send_back_to_stage is required"):
            ReviewDecision(**_make_review_decision(decision="sent_back"))

    def test_accepted_with_adjusted_priority_rejected(self):
        with pytest.raises(ValidationError, match="adjusted_priority should only be set"):
            ReviewDecision(**_make_review_decision(
                decision="accepted",
                adjusted_priority=3,
            ))

    def test_rejected_with_send_back_to_stage_rejected(self):
        with pytest.raises(ValidationError, match="send_back_to_stage should only be set"):
            ReviewDecision(**_make_review_decision(
                decision="rejected",
                send_back_to_stage="exploration",
            ))

    def test_adjusted_priority_zero_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecision(**_make_review_decision(
                decision="priority_adjusted",
                adjusted_priority=0,
            ))

    def test_extra_fields_allowed(self):
        rd = ReviewDecision(
            **_make_review_decision(),
            reviewer_notes="Discussed with team",
        )
        assert rd.reviewer_notes == "Discussed with team"  # type: ignore[attr-defined]


# ============================================================================
# HumanReviewCheckpoint tests
# ============================================================================


class TestHumanReviewCheckpoint:
    def test_valid_checkpoint(self):
        cp = HumanReviewCheckpoint(**_make_human_review_checkpoint())
        assert cp.schema_version == 1
        assert len(cp.decisions) == 1
        assert cp.review_metadata.reviewer == "paul"

    def test_empty_decisions_allowed(self):
        """No opportunities reached review."""
        cp = HumanReviewCheckpoint(**_make_human_review_checkpoint(decisions=[]))
        assert len(cp.decisions) == 0

    def test_default_decisions_is_empty(self):
        data = _make_human_review_checkpoint()
        del data["decisions"]
        cp = HumanReviewCheckpoint(**data)
        assert cp.decisions == []

    def test_missing_metadata_rejected(self):
        data = _make_human_review_checkpoint()
        del data["review_metadata"]
        with pytest.raises(ValidationError):
            HumanReviewCheckpoint(**data)

    def test_invalid_decision_inside_checkpoint_rejected(self):
        data = _make_human_review_checkpoint(
            decisions=[{"opportunity_id": ""}]  # Empty opportunity_id
        )
        with pytest.raises(ValidationError):
            HumanReviewCheckpoint(**data)

    def test_empty_reviewer_rejected(self):
        data = _make_human_review_checkpoint(
            review_metadata={"reviewer": "", "opportunities_reviewed": 0}
        )
        with pytest.raises(ValidationError):
            HumanReviewCheckpoint(**data)

    def test_negative_opportunities_reviewed_rejected(self):
        data = _make_human_review_checkpoint(
            review_metadata={"reviewer": "paul", "opportunities_reviewed": -1}
        )
        with pytest.raises(ValidationError):
            HumanReviewCheckpoint(**data)

    def test_multiple_decisions(self):
        data = _make_human_review_checkpoint(
            decisions=[
                _make_review_decision(opportunity_id="opp_1", decision="accepted"),
                _make_review_decision(opportunity_id="opp_2", decision="rejected"),
                _make_review_decision(opportunity_id="opp_3", decision="deferred"),
            ]
        )
        cp = HumanReviewCheckpoint(**data)
        assert len(cp.decisions) == 3

    def test_extra_fields_allowed(self):
        cp = HumanReviewCheckpoint(
            **_make_human_review_checkpoint(),
            review_session_duration_minutes=45,
        )
        assert cp.review_session_duration_minutes == 45  # type: ignore[attr-defined]

    def test_schema_version_defaults_to_1(self):
        cp = HumanReviewCheckpoint(**_make_human_review_checkpoint())
        assert cp.schema_version == 1
