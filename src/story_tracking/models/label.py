"""
Label Models

Models for label registry and Shortcut taxonomy management.
Reference: docs/story-tracking-web-app-architecture.md
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LabelCreate(BaseModel):
    """Fields for creating a label in the registry."""

    label_name: str
    source: str = "internal"  # "shortcut" | "internal"
    category: Optional[str] = None


class LabelUpdate(BaseModel):
    """Fields for updating a label (all optional)."""

    category: Optional[str] = None
    last_seen_at: Optional[datetime] = None


class ImportResult(BaseModel):
    """Result of importing labels from Shortcut."""

    imported_count: int = 0
    skipped_count: int = 0
    updated_count: int = 0
    errors: List[str] = Field(default_factory=list)


class LabelListResponse(BaseModel):
    """Response for listing labels."""

    labels: List["LabelRegistryEntry"]
    total: int
    shortcut_count: int = 0
    internal_count: int = 0


class LabelRegistryEntry(BaseModel):
    """Label in the registry (duplicated here for self-reference in LabelListResponse)."""

    model_config = ConfigDict(from_attributes=True)

    label_name: str
    source: str  # "shortcut" | "internal"
    category: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime


# Update forward reference
LabelListResponse.model_rebuild()
