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

from pydantic import BaseModel, Field

from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
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
    Extra fields (decision_rationale, validation_challenges, experience_direction,
    convergence_forced, convergence_note) are stored via extra='allow'.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    proposed_solution: str = Field(min_length=1, description="What to build or change")
    experiment_plan: str = Field(min_length=1, description="What to test and how")
    success_metrics: str = Field(
        min_length=1,
        description="Measurable outcomes with baseline and target",
    )
    build_experiment_decision: BuildExperimentDecision
    evidence: List[EvidencePointer] = Field(min_length=1)

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


class TechnicalSpec(BaseModel):
    """Stage 3 checkpoint artifact.

    Technical approach + effort + dependencies + risks + acceptance criteria.
    """

    model_config = {"extra": "allow"}

    schema_version: int = 1
    approach: str = Field(min_length=1, description="How to implement")
    effort_estimate: str = Field(min_length=1, description="With confidence range")
    dependencies: str = Field(min_length=1, description="What this blocks or is blocked by")
    risks: List[str] = Field(min_length=1, description="Identified risks with severity")
    acceptance_criteria: str = Field(min_length=1, description="How to verify completion")

    def model_post_init(self, __context) -> None:
        extra_fields = set(self.model_fields_set) - set(self.__class__.model_fields.keys())
        if extra_fields:
            logger.info("TechnicalSpec has extra fields: %s", extra_fields)


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
