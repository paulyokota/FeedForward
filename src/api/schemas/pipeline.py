"""
Pipeline API Schemas

Pydantic models for pipeline run requests and responses.
"""

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


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
    current_phase: str = "classification"  # classification, theme_extraction, pm_review, story_creation, completed

    # Progress/results - Classification phase
    conversations_fetched: int = 0
    conversations_filtered: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0

    # Progress/results - Theme extraction phase
    themes_extracted: int = 0
    themes_new: int = 0

    # Progress/results - Story creation phase
    stories_created: int = 0
    orphans_created: int = 0

    # Story creation readiness
    stories_ready: bool = False  # True when themes extracted, can create stories

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
    themes_extracted: int = 0
    stories_created: int = 0
    stories_ready: bool = False
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
