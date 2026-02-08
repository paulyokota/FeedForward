"""Artifact contract models for the Discovery Engine.

These are output validation models — agents think freely, these check that
output includes required fields. Per #212: "The schemas are output validation,
not input constraints."

Models use extra='allow' because #212 says "additional fields will emerge from
Phase 1 experience" and "agents can (and should) include more when relevant."
"""

import logging
from datetime import datetime
from typing import List, Optional

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


class SolutionBrief(BaseModel):
    """Stage 2 checkpoint artifact.

    Solution hypothesis + experiment plan + Build/Experiment Decision.
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
