"""
Pipeline API Schemas

Pydantic models for pipeline run requests and responses.
"""

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class PipelineError(BaseModel):
    """Structured error from pipeline phase."""

    phase: str  # "classification", "theme_extraction", "story_creation"
    message: str
    details: Optional[dict] = None


class PipelineRunRequest(BaseModel):
    """Request to start a pipeline run."""

    days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Number of days to look back for conversations"
    )
    max_conversations: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum conversations to process (None for unlimited)"
    )
    dry_run: bool = Field(
        default=False,
        description="If True, don't store results to database"
    )
    concurrency: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Number of parallel API calls"
    )
    auto_create_stories: bool = Field(
        default=False,
        description="If True, automatically run PM review and create stories after theme extraction"
    )


class PipelineRunResponse(BaseModel):
    """Response when starting a pipeline run."""

    run_id: int
    status: Literal["started", "queued"]
    message: str


class PipelineStatus(BaseModel):
    """Current status of a pipeline run."""

    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["running", "stopping", "stopped", "completed", "failed"]
    error_message: Optional[str] = None

    # Configuration
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    auto_create_stories: bool = False

    # Phase tracking
    current_phase: str = "classification"  # classification, embedding_generation, facet_extraction, theme_extraction, pm_review, story_creation, completed

    # Progress/results - Classification phase
    conversations_fetched: int = 0
    conversations_filtered: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0

    # Progress/results - Embedding generation phase (#106)
    embeddings_generated: int = 0
    embeddings_failed: int = 0

    # Progress/results - Facet extraction phase (#107)
    facets_extracted: int = 0
    facets_failed: int = 0

    # Progress/results - Theme extraction phase
    themes_extracted: int = 0
    themes_new: int = 0
    themes_filtered: int = 0  # Themes filtered by quality gates (#104)

    # Progress/results - Story creation phase
    stories_created: int = 0
    orphans_created: int = 0

    # Story creation readiness
    # True only when themes_extracted > 0 (Fix #104: was incorrectly set True even with 0 themes)
    stories_ready: bool = False

    # Error tracking (#104: Structured error propagation)
    errors: List[PipelineError] = []
    warnings: List[str] = []

    # Computed
    duration_seconds: Optional[float] = None

    class Config:
        from_attributes = True


class PipelineRunListItem(BaseModel):
    """Summary item for pipeline run list."""

    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["running", "stopping", "stopped", "completed", "failed"]
    current_phase: str = "classification"
    conversations_fetched: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0
    embeddings_generated: int = 0  # #106
    facets_extracted: int = 0  # #107
    themes_extracted: int = 0
    stories_created: int = 0
    stories_ready: bool = False
    error_count: int = 0  # Number of errors (#104)
    duration_seconds: Optional[float] = None

    class Config:
        from_attributes = True


class PipelineStopResponse(BaseModel):
    """Response when stopping a pipeline run."""

    run_id: int
    status: Literal["stopping", "stopped", "not_running"]
    message: str


class CreateStoriesResponse(BaseModel):
    """Response when creating stories from a pipeline run."""

    run_id: int
    stories_created: int = 0
    orphans_created: int = 0
    message: str


# ============================================================================
# Dry Run Preview Models
# ============================================================================


class DryRunSample(BaseModel):
    """A single classified conversation sample for dry run preview."""

    conversation_id: str
    snippet: str  # First 200 chars of source_body
    conversation_type: str  # From stage1 or stage2
    confidence: str  # high/medium/low
    themes: list[str] = []  # From stage1_result.themes if present
    has_support_response: bool = False


class DryRunClassificationBreakdown(BaseModel):
    """Classification type distribution for dry run preview."""

    by_type: dict[str, int]  # e.g., {"product_issue": 5, "how_to_question": 3}
    by_confidence: dict[str, int]  # e.g., {"high": 6, "medium": 2}


class DryRunPreview(BaseModel):
    """Complete dry run preview data."""

    run_id: int
    classification_breakdown: DryRunClassificationBreakdown
    samples: list[DryRunSample]  # 5-10 representative samples
    top_themes: list[tuple[str, int]]  # [(theme, count), ...] top 5
    total_classified: int
    timestamp: datetime
