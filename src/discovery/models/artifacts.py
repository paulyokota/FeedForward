"""Artifact contract models for the Discovery Engine.

These are output validation models — agents think freely, these check that
output includes required fields. Per #212: "The schemas are output validation,
not input constraints."

Models use extra='allow' because #212 says "additional fields will emerge from
Phase 1 experience" and "agents can (and should) include more when relevant."
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
    ExperimentOutcome,
    ExperimentRecommendation,
    FeasibilityAssessment,
    ReviewDecisionType,
    SourceType,
)

logger = logging.getLogger(__name__)


class EvidencePointer(BaseModel):
    """Typed evidence pointer used across all stages.

    Every claim must include typed evidence pointers, not free-form references.
    Phase 1: pointers are best-effort (not machine-validated against source systems).
    """

    model_config = {"extra": "allow"}

    source_type: SourceType
    source_id: str = Field(
        min_length=1,
        description="e.g., conv_8421, funnel_billing_upgrade, src/billing/form.py:42",
    )
    retrieved_at: datetime
    confidence: ConfidenceLevel


class OpportunityBrief(BaseModel):
    """Stage 1 checkpoint artifact.

    Contains problem + evidence + impact hypothesis + counterfactual.
    No solution direction — that emerges in Stage 2.

    Issue #261: Added opportunity_nature, recommended_response, stage_hints
    for adaptive pipeline routing. All Optional for backward compatibility.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    problem_statement: str = Field(min_length=1, description="What's wrong and who's affected")
    evidence: List[EvidencePointer] = Field(min_length=1)
    counterfactual: str = Field(
        min_length=1,
        description="'If we solved X, we would expect Y measurable change' — mandatory, quantitative where possible",
    )
    affected_area: str = Field(min_length=1, description="Product surface or system component")
    explorer_coverage: str = Field(
        min_length=1,
        description="What data the explorers reviewed (from Stage 0 coverage metadata)",
    )
    opportunity_nature: Optional[str] = Field(
        default=None,
        description="Free-text description of opportunity type (e.g., 'internal engineering: instrumentation gap', 'user-facing: checkout friction')",
    )
    recommended_response: Optional[str] = Field(
        default=None,
        description="Agent's recommendation for appropriate response (e.g., 'internal task, no user experiment needed')",
    )
    stage_hints: Optional[List[str]] = Field(
        default=None,
        description="Hints for downstream stages (e.g., ['skip_experience', 'internal_risk_framing'])",
    )

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("OpportunityBrief has extra fields: %s", extra_fields)


class FramingMetadata(BaseModel):
    """Stable metadata fields for OpportunityFramingCheckpoint.

    Documents what the Opportunity PM reviewed and produced, so downstream
    stages can assess coverage without parsing the briefs themselves.
    """

    model_config = {"extra": "allow"}

    explorer_findings_count: int = Field(ge=0)
    opportunities_identified: int = Field(ge=0)
    model: str = Field(min_length=1)


class OpportunityFramingCheckpoint(BaseModel):
    """Stage 1 checkpoint artifact wrapping multiple OpportunityBriefs.

    A single discovery run may identify multiple distinct opportunities.
    Each proceeds independently through Stages 2-5. Empty briefs list
    is valid when the explorer found nothing actionable.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    briefs: List[OpportunityBrief] = Field(default_factory=list)
    framing_metadata: FramingMetadata

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("OpportunityFramingCheckpoint has extra fields: %s", extra_fields)


class SolutionBrief(BaseModel):
    """Stage 2 checkpoint artifact.

    Solution hypothesis + experiment plan + Build/Experiment Decision.
    Extra fields (decision_rationale, validation_challenges,
    convergence_forced, convergence_note) are stored via extra='allow'.

    Issue #261: experiment_plan, build_experiment_decision, and
    experience_direction are now Optional. Internal engineering
    opportunities may skip experiment planning and UX evaluation.
    When fields are omitted, skip_rationale explains why.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    proposed_solution: str = Field(min_length=1, description="What to build or change")
    experiment_plan: Optional[str] = Field(
        default=None, description="What to test and how (None for internal engineering with no experiment)"
    )
    success_metrics: str = Field(
        min_length=1,
        description="Measurable outcomes with baseline and target",
    )
    build_experiment_decision: Optional[BuildExperimentDecision] = Field(
        default=None, description="Build/experiment gate decision (None when not applicable)"
    )
    evidence: List[EvidencePointer] = Field(min_length=1)
    experience_direction: Optional[Dict[str, Any]] = Field(
        default=None, description="UX direction from Experience Agent (None when experience was skipped)"
    )
    skip_rationale: Optional[str] = Field(
        default=None, description="Why Optional fields were omitted (populated when experiment_plan, build_experiment_decision, or experience_direction is None)"
    )

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("SolutionBrief has extra fields: %s", extra_fields)


class SolutionDesignMetadata(BaseModel):
    """Stable metadata fields for SolutionValidationCheckpoint.

    Documents what the SolutionDesigner reviewed and produced, so downstream
    stages can assess coverage without parsing the solutions themselves.
    """

    model_config = {"extra": "allow"}

    opportunity_briefs_processed: int = Field(ge=0)
    solutions_produced: int = Field(ge=0)
    total_dialogue_rounds: int = Field(ge=0)
    total_token_usage: Dict[str, int] = Field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    model: str = Field(min_length=1)


class SolutionValidationCheckpoint(BaseModel):
    """Stage 2 checkpoint artifact wrapping multiple SolutionBriefs.

    One SolutionBrief per OpportunityBrief from Stage 1. Empty solutions
    list is valid when all opportunity briefs were dropped or none existed.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    solutions: List[SolutionBrief] = Field(default_factory=list)
    design_metadata: SolutionDesignMetadata

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("SolutionValidationCheckpoint has extra fields: %s", extra_fields)


class RiskItem(BaseModel):
    """A single identified risk with severity and mitigation.

    Used by TechnicalSpec to capture structured risk information
    from the Risk/QA Agent.
    """

    model_config = {"extra": "allow"}

    description: str = Field(min_length=1, description="What the risk is")
    severity: str = Field(min_length=1, description="e.g. high, medium, low, critical")
    mitigation: str = Field(min_length=1, description="How to address or reduce this risk")


class TechnicalSpec(BaseModel):
    """Stage 3 inner artifact — one per feasible solution.

    Technical approach + effort + dependencies + risks + acceptance criteria.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    opportunity_id: str = Field(min_length=1, description="Links back to OpportunityBrief")
    approach: str = Field(min_length=1, description="How to implement")
    effort_estimate: str = Field(min_length=1, description="With confidence range")
    dependencies: str = Field(min_length=1, description="What this blocks or is blocked by")
    risks: List[RiskItem] = Field(min_length=1, description="Identified risks with severity and mitigation")
    acceptance_criteria: str = Field(min_length=1, description="How to verify completion")

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("TechnicalSpec has extra fields: %s", extra_fields)


class InfeasibleSolution(BaseModel):
    """Records a solution that was assessed as technically infeasible.

    Preserved in the checkpoint so Stage 2 can design around the constraint
    when the backward flow triggers.
    """

    model_config = {"extra": "allow"}

    opportunity_id: str = Field(min_length=1)
    solution_summary: str = Field(min_length=1, description="What was proposed")
    feasibility_assessment: FeasibilityAssessment
    infeasibility_reason: str = Field(min_length=1, description="Why it's not feasible")
    constraints_identified: List[str] = Field(
        default_factory=list,
        description="Specific technical constraints that prevent implementation",
    )

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("InfeasibleSolution has extra fields: %s", extra_fields)


class FeasibilityRiskMetadata(BaseModel):
    """Stable metadata fields for FeasibilityRiskCheckpoint."""

    model_config = {"extra": "allow"}

    solutions_assessed: int = Field(ge=0)
    feasible_count: int = Field(ge=0)
    infeasible_count: int = Field(ge=0)
    total_dialogue_rounds: int = Field(ge=0)
    total_token_usage: Dict[str, int] = Field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    model: str = Field(min_length=1)


class FeasibilityRiskCheckpoint(BaseModel):
    """Stage 3 checkpoint artifact wrapping feasible specs and infeasible records.

    Feasible solutions become TechnicalSpecs in `specs`. Infeasible solutions
    are recorded in `infeasible_solutions` with rationale for backward flow.
    Both lists can be empty (no solutions to assess, or all feasible/infeasible).
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    specs: List[TechnicalSpec] = Field(default_factory=list)
    infeasible_solutions: List[InfeasibleSolution] = Field(default_factory=list)
    feasibility_metadata: FeasibilityRiskMetadata

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("FeasibilityRiskCheckpoint has extra fields: %s", extra_fields)


# ============================================================================
# Explorer agent artifacts (Issue #215)
# ============================================================================


class ExplorerFinding(BaseModel):
    """A single finding from an explorer agent.

    Each finding names its own pattern (NOT from the existing theme
    vocabulary) and includes typed evidence pointers.
    """

    model_config = {"extra": "allow"}

    pattern_name: str = Field(min_length=1, description="Agent-chosen name for the pattern")
    description: str = Field(min_length=1, description="What was observed")
    evidence: List[EvidencePointer] = Field(min_length=1)
    confidence: ConfidenceLevel
    severity_assessment: str = Field(min_length=1)
    affected_users_estimate: str = Field(min_length=1)

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("ExplorerFinding has extra fields: %s", extra_fields)


class CoverageMetadata(BaseModel):
    """Coverage metadata from an exploration run.

    Tracks what data was reviewed so later stages know the scope.
    Invariant: conversations_reviewed + conversations_skipped should
    equal conversations_available (enforced by tests, not the model).
    """

    model_config = {"extra": "allow"}

    time_window_days: int = Field(ge=1)
    conversations_available: int = Field(ge=0)
    conversations_reviewed: int = Field(ge=0)
    conversations_skipped: int = Field(ge=0)
    model: str = Field(min_length=1)
    findings_count: int = Field(ge=0)


class ExplorerCheckpoint(BaseModel):
    """Formal EXPLORATION stage checkpoint artifact (MF1).

    Registered in STAGE_ARTIFACT_MODELS so the state machine validates
    explorer output before advancing to OPPORTUNITY_FRAMING.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    agent_name: str = Field(min_length=1)
    findings: List[ExplorerFinding] = Field(default_factory=list)
    coverage: CoverageMetadata


# ============================================================================
# Stage 4: Prioritization artifacts (Issue #235)
# ============================================================================


class PrioritizedOpportunity(BaseModel):
    """A single opportunity with its recommended priority ranking.

    The TPM Agent produces one of these per opportunity that made it
    through Stages 1-3.
    """

    model_config = {"extra": "allow"}

    opportunity_id: str = Field(min_length=1, description="Links back to OpportunityBrief")
    recommended_rank: int = Field(ge=1, description="1 = highest priority")
    rationale: str = Field(min_length=1, description="Why this ranking")
    dependencies: List[str] = Field(
        default_factory=list,
        description="Cross-item dependency notes",
    )
    flags: List[str] = Field(
        default_factory=list,
        description="Unusual items, warnings",
    )

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("PrioritizedOpportunity has extra fields: %s", extra_fields)


class PrioritizationMetadata(BaseModel):
    """Stable metadata fields for PrioritizationCheckpoint."""

    model_config = {"extra": "allow"}

    opportunities_ranked: int = Field(ge=0)
    model: str = Field(min_length=1)


class PrioritizationCheckpoint(BaseModel):
    """Stage 4 checkpoint artifact wrapping ranked opportunities.

    Empty rankings list is valid when earlier stages yielded nothing
    to prioritize. Mirrors Stage 1/2 empty-list pattern.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    rankings: List[PrioritizedOpportunity] = Field(default_factory=list)
    prioritization_metadata: PrioritizationMetadata

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("PrioritizationCheckpoint has extra fields: %s", extra_fields)


# ============================================================================
# Experiment Re-entry artifacts (Issue #224)
# ============================================================================


class ExperimentResult(BaseModel):
    """Structured experiment outcome for re-entry into Stage 2.

    Submitted by a human after an experiment_first or build_slice_and_experiment
    decision completes outside the discovery engine. Stored in the re-entry
    run's metadata.
    """

    model_config = {"extra": "allow"}

    opportunity_id: str = Field(min_length=1, description="Links back to original OpportunityBrief")
    experiment_plan_executed: str = Field(min_length=1, description="What was actually tested")
    success_criteria: str = Field(min_length=1, description="From the original SolutionBrief")
    measured_outcome: str = Field(min_length=1, description="What was observed")
    outcome_vs_criteria: ExperimentOutcome
    observations: str = Field(min_length=1, description="Qualitative learnings")
    recommendation: ExperimentRecommendation

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("ExperimentResult has extra fields: %s", extra_fields)


# ============================================================================
# Stage 5: Human Review artifacts (Issue #235)
# ============================================================================


class ReviewDecision(BaseModel):
    """A single review decision for one opportunity.

    Conditional fields: adjusted_priority is required IFF decision is
    PRIORITY_ADJUSTED, send_back_to_stage is required IFF decision is
    SENT_BACK.
    """

    model_config = {"extra": "allow"}

    opportunity_id: str = Field(min_length=1)
    decision: ReviewDecisionType
    reasoning: str = Field(min_length=1, description="Required for all decisions")
    adjusted_priority: Optional[int] = Field(
        default=None, ge=1, description="Required when decision is priority_adjusted"
    )
    send_back_to_stage: Optional[str] = Field(
        default=None, min_length=1, description="Required when decision is sent_back"
    )

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "ReviewDecision":
        if self.decision == ReviewDecisionType.PRIORITY_ADJUSTED and self.adjusted_priority is None:
            raise ValueError("adjusted_priority is required when decision is priority_adjusted")
        if self.decision == ReviewDecisionType.SENT_BACK and not self.send_back_to_stage:
            raise ValueError("send_back_to_stage is required when decision is sent_back")
        if self.decision != ReviewDecisionType.PRIORITY_ADJUSTED and self.adjusted_priority is not None:
            raise ValueError("adjusted_priority should only be set when decision is priority_adjusted")
        if self.decision != ReviewDecisionType.SENT_BACK and self.send_back_to_stage is not None:
            raise ValueError("send_back_to_stage should only be set when decision is sent_back")
        return self

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("ReviewDecision has extra fields: %s", extra_fields)


class ReviewMetadata(BaseModel):
    """Stable metadata fields for HumanReviewCheckpoint."""

    model_config = {"extra": "allow"}

    reviewer: str = Field(min_length=1, description="Who made the decisions")
    opportunities_reviewed: int = Field(ge=0)


class HumanReviewCheckpoint(BaseModel):
    """Stage 5 checkpoint artifact wrapping review decisions.

    Empty decisions list is valid when no opportunities reached review.
    This is the terminal stage — completing this completes the run.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    decisions: List[ReviewDecision] = Field(default_factory=list)
    review_metadata: ReviewMetadata

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("HumanReviewCheckpoint has extra fields: %s", extra_fields)
