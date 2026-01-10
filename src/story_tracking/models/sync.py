"""
Sync Models

Models for bidirectional Shortcut sync operations.
Reference: docs/story-tracking-web-app-architecture.md
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SyncMetadataCreate(BaseModel):
    """Fields for creating sync metadata."""

    story_id: UUID
    shortcut_story_id: str


class SyncMetadataUpdate(BaseModel):
    """Fields for updating sync metadata (all optional)."""

    shortcut_story_id: Optional[str] = None
    last_internal_update_at: Optional[datetime] = None
    last_external_update_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_direction: Optional[str] = None


class SyncResult(BaseModel):
    """Result of a sync operation."""

    success: bool
    direction: str  # "push" | "pull" | "none"
    story_id: UUID
    shortcut_story_id: Optional[str] = None
    error: Optional[str] = None
    synced_at: Optional[datetime] = None


class ShortcutWebhookEvent(BaseModel):
    """Shortcut webhook event payload."""

    shortcut_story_id: str
    event_type: str  # "story.updated" | "story.created" | "story.deleted"
    updated_at: datetime
    fields: Dict[str, Any] = Field(default_factory=dict)


class StorySnapshot(BaseModel):
    """Snapshot of story fields for sync operations."""

    title: str
    description: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    priority: Optional[str] = None
    severity: Optional[str] = None
    product_area: Optional[str] = None
    technical_area: Optional[str] = None


class PushRequest(BaseModel):
    """Request to push internal story to Shortcut."""

    story_id: UUID
    snapshot: Optional[StorySnapshot] = None
    last_internal_update_at: Optional[datetime] = None


class PushResponse(BaseModel):
    """Response from push operation."""

    shortcut_story_id: str
    last_synced_at: datetime
    sync_status: str


class PullRequest(BaseModel):
    """Request to pull Shortcut story to internal."""

    shortcut_story_id: str
    story_id: Optional[UUID] = None
    last_external_update_at: Optional[datetime] = None


class PullResponse(BaseModel):
    """Response from pull operation."""

    story_id: UUID
    snapshot: StorySnapshot
    last_synced_at: datetime
    sync_status: str


class SyncStatusResponse(BaseModel):
    """Sync status for a story."""

    model_config = ConfigDict(from_attributes=True)

    story_id: UUID
    shortcut_story_id: Optional[str] = None
    last_internal_update_at: Optional[datetime] = None
    last_external_update_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_direction: Optional[str] = None
    needs_sync: bool = False
    sync_direction_hint: Optional[str] = None
