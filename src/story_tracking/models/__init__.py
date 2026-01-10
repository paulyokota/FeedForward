"""
Story Tracking Models

Pydantic models for the Story Tracking Web App.
Reference: docs/story-tracking-web-app-architecture.md
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Re-export orphan models
from .orphan import (
    MIN_GROUP_SIZE,
    Orphan,
    OrphanCreate,
    OrphanGraduationResult,
    OrphanListResponse,
    OrphanThemeData,
    OrphanUpdate,
)


class StoryBase(BaseModel):
    """Base story fields shared across create/update/response."""

    title: str
    description: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    priority: Optional[str] = None  # none, low, medium, high, urgent
    severity: Optional[str] = None  # none, minor, moderate, major, critical
    product_area: Optional[str] = None
    technical_area: Optional[str] = None
    status: str = "candidate"


class StoryCreate(StoryBase):
    """Fields for creating a new story."""

    confidence_score: Optional[float] = None


class StoryUpdate(BaseModel):
    """Fields for updating an existing story (all optional)."""

    title: Optional[str] = None
    description: Optional[str] = None
    labels: Optional[List[str]] = None
    priority: Optional[str] = None
    severity: Optional[str] = None
    product_area: Optional[str] = None
    technical_area: Optional[str] = None
    status: Optional[str] = None
    confidence_score: Optional[float] = None


class Story(StoryBase):
    """Full story response with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    confidence_score: Optional[float] = None
    evidence_count: int = 0
    conversation_count: int = 0
    created_at: datetime
    updated_at: datetime


class StoryComment(BaseModel):
    """Comment on a story."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    external_id: Optional[str] = None
    source: str  # 'internal' or 'shortcut'
    body: str
    author: Optional[str] = None
    created_at: datetime


class CommentCreate(BaseModel):
    """Fields for creating a comment."""

    body: str
    author: Optional[str] = None


class EvidenceExcerpt(BaseModel):
    """Single evidence excerpt."""

    text: str
    source: str  # 'intercom' or 'coda'
    conversation_id: Optional[str] = None


class StoryEvidence(BaseModel):
    """Evidence bundle for a story."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    story_id: UUID
    conversation_ids: List[str] = Field(default_factory=list)
    theme_signatures: List[str] = Field(default_factory=list)
    source_stats: Dict[str, int] = Field(default_factory=dict)
    excerpts: List[EvidenceExcerpt] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EvidenceUpdate(BaseModel):
    """Fields for updating evidence."""

    conversation_ids: Optional[List[str]] = None
    theme_signatures: Optional[List[str]] = None
    source_stats: Optional[Dict[str, int]] = None
    excerpts: Optional[List[EvidenceExcerpt]] = None


class SyncMetadata(BaseModel):
    """Sync state with Shortcut."""

    model_config = ConfigDict(from_attributes=True)

    story_id: UUID
    shortcut_story_id: Optional[str] = None
    last_internal_update_at: Optional[datetime] = None
    last_external_update_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_direction: Optional[str] = None


class LabelRegistryEntry(BaseModel):
    """Label in the registry."""

    model_config = ConfigDict(from_attributes=True)

    label_name: str
    source: str  # 'shortcut' or 'internal'
    category: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime


# Response models for API

class StoryWithEvidence(Story):
    """Story with evidence bundle attached."""

    evidence: Optional[StoryEvidence] = None
    sync: Optional[SyncMetadata] = None
    comments: List[StoryComment] = Field(default_factory=list)


class StoryListResponse(BaseModel):
    """Paginated list of stories."""

    stories: List[Story]
    total: int
    limit: int
    offset: int


class StoryDetailResponse(BaseModel):
    """Full story detail with all related data."""

    story: StoryWithEvidence
