"""Tests for Discovery Engine artifact contract models.

Tests that Pydantic models enforce required fields (output validation)
while allowing extra fields (agents can include more than required).
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.discovery.models.artifacts import (
    EvidencePointer,
    OpportunityBrief,
    SolutionBrief,
    TechnicalSpec,
)
from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
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


def _make_technical_spec(**overrides) -> dict:
    """Create a valid technical spec dict."""
    base = {
        "approach": "Consolidate three billing form implementations into shared component",
        "effort_estimate": "2 weeks +/- 3 days",
        "dependencies": "Payment module test coverage must be added first",
        "risks": ["Stripe webhook handling differs across implementations"],
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

    def test_missing_experiment_plan_rejected(self):
        data = _make_solution_brief()
        del data["experiment_plan"]
        with pytest.raises(ValidationError):
            SolutionBrief(**data)

    def test_missing_success_metrics_rejected(self):
        data = _make_solution_brief()
        del data["success_metrics"]
        with pytest.raises(ValidationError):
            SolutionBrief(**data)

    def test_missing_decision_rejected(self):
        data = _make_solution_brief()
        del data["build_experiment_decision"]
        with pytest.raises(ValidationError):
            SolutionBrief(**data)

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


class TestTechnicalSpec:
    def test_valid_technical_spec(self):
        ts = TechnicalSpec(**_make_technical_spec())
        assert len(ts.risks) == 1
        assert ts.schema_version == 1

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
                    "Stripe webhook handling differs",
                    "No test coverage on payment module",
                    "Migration requires downtime window",
                ]
            )
        )
        assert len(ts.risks) == 3

    def test_extra_fields_allowed(self):
        ts = TechnicalSpec(
            **_make_technical_spec(),
            suggested_reviewers=["backend-team"],
            estimated_lines_changed=500,
        )
        assert ts.suggested_reviewers == ["backend-team"]  # type: ignore[attr-defined]
