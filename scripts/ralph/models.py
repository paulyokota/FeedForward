"""
Pydantic models for Ralph V2 dual-mode evaluation.

These models define the interface contracts between components:
- Pattern formats (v1 legacy, v2 for cheap mode)
- Story input structure
- Evaluation results (cheap, expensive, dual)
- Iteration metrics and logging
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- Pattern Models ---


class PatternV1(BaseModel):
    """
    Legacy pattern format (existing 471 patterns in learned_patterns.json).

    DEPRECATED: Use PatternV2 for new patterns. This format is read-only.
    To migrate, use pattern_migrator.migrate_patterns_file().
    """

    type: Literal["good_pattern", "bad_pattern"]
    description: str
    example: str
    discovered_at: datetime
    source: str = "scoping_validation"


class PatternV2(BaseModel):
    """
    New pattern format for cheap mode evaluation.

    Example:
        pattern = PatternV2(
            id="p_0001",
            type="good",
            description="Keep OAuth flow for a single platform",
            keywords=["oauth", "single", "platform"],
            source="migration",
            discovered_at=datetime.now(),
        )

    Note: accuracy and times_fired are updated during Phase 3/4 calibration loop.
    """

    id: str = Field(..., description="Unique pattern ID, e.g., 'p_001'")
    type: Literal["good", "bad"]
    description: str
    keywords: list[str] = Field(..., description="Extracted keywords for matching")
    weight: float = Field(default=1.0, ge=0.0, le=2.0)
    source: str
    discovered_at: datetime
    # Phase 3/4: These fields are updated during calibration loop
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Updated during calibration")
    times_fired: int = Field(default=0, ge=0, description="Updated during calibration")
    status: Literal["active", "provisional", "rejected", "pruned"] = "active"


class LearnedPatternsV1(BaseModel):
    """Schema for existing learned_patterns.json file."""

    version: str
    last_updated: datetime
    patterns: list[PatternV1]
    service_insights: dict = Field(default_factory=dict)
    scoping_rules: dict = Field(default_factory=dict)


class LearnedPatternsV2(BaseModel):
    """Schema for new v2 patterns file."""

    version: str = "2.0"
    last_updated: datetime
    patterns: list[PatternV2]
    calibration_history: list[dict] = Field(default_factory=list)


# --- Story Models ---


class Story(BaseModel):
    """
    Input story structure for evaluation.

    Example:
        story = Story(
            id="story_001",
            title="Add Pinterest OAuth refresh",
            description="Enable automatic token refresh for Pinterest integration",
            acceptance_criteria=["Token refreshes automatically", "No user action needed"],
            technical_area="aero/services/oauth/pinterest.py",
        )
    """

    id: str = Field(..., max_length=100)
    title: str = Field(..., max_length=200)
    description: str = Field(..., max_length=10000)
    acceptance_criteria: list[str] = Field(..., max_length=50)
    technical_area: str | None = Field(default=None, max_length=500)
    services: list[str] = Field(default_factory=list, max_length=20)
    source_conversations: list[str] = Field(default_factory=list, max_length=100)


# --- Result Models ---


class CheapModeResult(BaseModel):
    """Output from cheap mode evaluation of a single story."""

    story_id: str
    gestalt: float = Field(..., ge=1.0, le=5.0)
    raw_score: float = Field(..., ge=0.0, le=5.0)
    reasons: list[str]
    patterns_matched: list[str] = Field(
        ..., description="Pattern IDs that fired (positive signal)"
    )
    patterns_violated: list[str] = Field(
        default_factory=list, description="Bad pattern IDs that fired (negative signal)"
    )


class ExpensiveModeResult(BaseModel):
    """Output from expensive (LLM) mode evaluation of a single story."""

    story_id: str
    gestalt: float = Field(..., ge=1.0, le=5.0)
    reasoning: str
    strengths: list[str]
    weaknesses: list[str]


class DualModeResult(BaseModel):
    """Combined result from dual-mode evaluation."""

    story_id: str
    expensive: ExpensiveModeResult
    cheap: CheapModeResult
    gap: float = Field(..., description="expensive.gestalt - cheap.gestalt")


# --- Iteration Models ---


class IterationMetrics(BaseModel):
    """Metrics for a single iteration."""

    iteration: int
    timestamp: datetime
    expensive_avg: float
    cheap_avg: float
    gap: float
    gap_delta: float = Field(..., description="Change from previous iteration")
    pattern_count: int
    provisional_patterns: int
    patterns_committed: int
    patterns_rejected: int
    story_ids: list[str] = Field(default_factory=list)


class ComponentHealthStatus(BaseModel):
    """Health status for a single component."""

    healthy: bool
    flags: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class DivergenceCheck(BaseModel):
    """Result of divergence detection."""

    diverging: bool
    reason: str | None = None
    diagnosis: str | None = None
    action: str | None = None


class ConvergenceCheck(BaseModel):
    """Result of convergence check."""

    converged: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    proof: dict = Field(default_factory=dict)


class IterationLog(BaseModel):
    """Complete log for a single iteration."""

    iteration: int
    timestamp: datetime
    component_health: dict[str, ComponentHealthStatus]
    metrics: IterationMetrics
    divergence_check: DivergenceCheck
    per_story_results: list[DualModeResult]
    actions_taken: list[dict]
    convergence_check: ConvergenceCheck


# --- Pattern Proposal Models ---


class PatternProposal(BaseModel):
    """A proposed pattern that must prove itself before becoming permanent."""

    id: str
    status: Literal["provisional", "validated", "rejected"] = "provisional"
    pattern: PatternV2
    proposed_at: int  # iteration number
    stories_tested: int = 0
    correct_predictions: int = 0

    @property
    def accuracy(self) -> float:
        if self.stories_tested == 0:
            return 0.0
        # Defensive: clamp to [0, 1] range
        return min(1.0, self.correct_predictions / self.stories_tested)

    def should_commit(self) -> bool:
        """Commit only if pattern proves accurate over N stories."""
        return self.stories_tested >= 10 and self.accuracy >= 0.7

    def should_reject(self) -> bool:
        """Reject if pattern is clearly not helping."""
        return self.stories_tested >= 5 and self.accuracy < 0.3
