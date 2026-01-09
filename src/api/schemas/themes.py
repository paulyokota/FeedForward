"""
Themes API Schemas

Pydantic models for theme analysis endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ThemeAggregate(BaseModel):
    """
    Aggregated theme data across conversations.

    Represents a grouped issue pattern with occurrence counts
    and sample data for context.
    """

    issue_signature: str = Field(description="Canonical theme identifier")
    product_area: str
    component: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime

    # Sample data from conversations
    sample_user_intent: Optional[str] = None
    sample_symptoms: List[str] = Field(default_factory=list)
    sample_affected_flow: Optional[str] = None
    sample_root_cause_hypothesis: Optional[str] = None

    # Ticket status
    ticket_created: bool = False
    ticket_id: Optional[str] = None

    class Config:
        from_attributes = True


class ThemeListResponse(BaseModel):
    """Response containing list of themes with pagination."""

    themes: List[ThemeAggregate]
    total: int
    limit: int
    offset: int


class TrendingThemesResponse(BaseModel):
    """Response for trending themes endpoint."""

    themes: List[ThemeAggregate]
    days: int
    min_occurrences: int
    total: int


class OrphanThemesResponse(BaseModel):
    """Response for orphan/singleton themes endpoint."""

    themes: List[ThemeAggregate]
    threshold: int = Field(description="Occurrence count threshold used")
    total: int


class ThemeDetail(BaseModel):
    """Detailed theme information including conversation IDs."""

    theme: ThemeAggregate
    conversation_ids: List[str] = Field(
        default_factory=list,
        description="IDs of conversations with this theme"
    )
