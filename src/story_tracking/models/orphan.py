"""
Orphan Models for Phase 5 Story Grouping

Orphans are conversation groups with <MIN_GROUP_SIZE conversations that
accumulate over time until they reach the threshold for graduation to stories.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Minimum conversations required for a group to become a story
MIN_GROUP_SIZE = 3

# Issue #200: Days within which a conversation is considered "recent" for story creation
RECENCY_WINDOW_DAYS = 30


class OrphanThemeData(BaseModel):
    """Theme data accumulated from conversations."""

    user_intent: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    product_area: Optional[str] = None
    component: Optional[str] = None
    affected_flow: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    excerpts: List[Dict[str, Any]] = Field(default_factory=list)


class OrphanCreate(BaseModel):
    """Fields for creating a new orphan."""

    signature: str
    original_signature: Optional[str] = None
    conversation_ids: List[str] = Field(default_factory=list)
    theme_data: Dict[str, Any] = Field(default_factory=dict)
    confidence_score: Optional[float] = None


class OrphanUpdate(BaseModel):
    """Fields for updating an orphan (all optional)."""

    conversation_ids: Optional[List[str]] = None
    theme_data: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None


class Orphan(BaseModel):
    """Full orphan response with all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    signature: str
    original_signature: Optional[str] = None
    conversation_ids: List[str] = Field(default_factory=list)
    theme_data: Dict[str, Any] = Field(default_factory=dict)
    confidence_score: Optional[float] = None
    first_seen_at: datetime
    last_updated_at: datetime
    graduated_at: Optional[datetime] = None
    story_id: Optional[UUID] = None

    @property
    def conversation_count(self) -> int:
        """Number of conversations in this orphan."""
        return len(self.conversation_ids)

    @property
    def is_active(self) -> bool:
        """Whether orphan is still active (not graduated)."""
        return self.graduated_at is None

    @property
    def can_graduate(self) -> bool:
        """Whether orphan has enough conversations to graduate."""
        return self.conversation_count >= MIN_GROUP_SIZE


class OrphanListResponse(BaseModel):
    """Response for listing orphans."""

    orphans: List[Orphan]
    total: int
    active_count: int  # Non-graduated count


class OrphanGraduationResult(BaseModel):
    """Result of graduating an orphan to a story."""

    orphan_id: UUID
    story_id: UUID
    signature: str
    conversation_count: int
    graduated_at: datetime
