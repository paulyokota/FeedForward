"""
Research Module Models

Pydantic models for search requests, responses, and data transfer.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SearchableContent(BaseModel):
    """Content extracted from any source for embedding."""

    source_type: str = Field(..., description="Source identifier: coda_page, coda_theme, intercom")
    source_id: str = Field(..., description="Unique ID within source")
    title: str = Field(..., description="Display title for results")
    content: str = Field(..., description="Text content to embed")
    url: str = Field(..., description="Link to original source")
    metadata: Dict = Field(default_factory=dict, description="Source-specific metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_type": "coda_page",
                "source_id": "page_abc123",
                "title": "User Research: Scheduling Pain Points",
                "content": "Users reported frustration with pin spacing...",
                "url": "https://coda.io/d/doc123/_/page_abc123",
                "metadata": {"participant": "user@example.com", "tags": ["scheduling"]},
            }
        }
    )


class UnifiedSearchResult(BaseModel):
    """Search result from unified search."""

    id: int = Field(..., description="Embedding table ID")
    source_type: str = Field(..., description="Source: coda_page, coda_theme, intercom")
    source_id: str = Field(..., description="Original source ID")
    title: str = Field(..., description="Result title")
    snippet: str = Field(..., description="~200 char excerpt")
    similarity: float = Field(..., ge=0, le=1, description="Cosine similarity 0-1")
    url: str = Field(..., description="Link to source")
    metadata: Dict = Field(default_factory=dict, description="Source-specific metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 42,
                "source_type": "coda_theme",
                "source_id": "theme_456",
                "title": "Pin Spacing Configuration Issues",
                "snippet": "Users frequently report confusion about how pin spacing...",
                "similarity": 0.87,
                "url": "https://coda.io/d/doc123#theme_456",
                "metadata": {"product_area": "scheduling", "occurrence_count": 15},
            }
        }
    )


class UnifiedSearchRequest(BaseModel):
    """Request for unified search."""

    query: str = Field(..., min_length=1, max_length=500, description="Search query text")
    limit: int = Field(default=20, ge=1, le=100, description="Max results to return")
    offset: int = Field(default=0, ge=0, description="Results to skip for pagination")
    source_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by source types: coda_page, coda_theme, intercom"
    )
    min_similarity: float = Field(
        default=0.5,
        ge=0.3,  # Server-enforced minimum
        le=1.0,
        description="Minimum similarity threshold"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "users frustrated with scheduling",
                "limit": 20,
                "source_types": ["coda_page", "coda_theme"],
                "min_similarity": 0.6,
            }
        }
    )


class SimilarContentRequest(BaseModel):
    """Request for 'more like this' similarity search."""

    source_type: str = Field(..., description="Source type of reference item")
    source_id: str = Field(..., description="ID of reference item")
    limit: int = Field(default=10, ge=1, le=50, description="Max similar items to return")
    exclude_same_source: bool = Field(
        default=False,
        description="Exclude items from same source type"
    )
    min_similarity: float = Field(
        default=0.5,
        ge=0.3,
        le=1.0,
        description="Minimum similarity threshold"
    )


class SuggestedEvidence(BaseModel):
    """Suggested research evidence for a story."""

    id: str = Field(..., description="Unique identifier (source_type:source_id)")
    source_type: str = Field(..., description="Source type: coda_page, coda_theme")
    source_id: str = Field(..., description="Source item ID")
    title: str = Field(..., description="Evidence title")
    snippet: str = Field(..., description="Relevant excerpt (~200 chars)")
    url: str = Field(..., description="Link to source")
    similarity: float = Field(..., ge=0, le=1, description="Relevance score")
    metadata: Dict = Field(default_factory=dict, description="Source-specific metadata")
    status: Literal["suggested", "accepted", "rejected"] = Field(
        default="suggested",
        description="PM acceptance status"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "coda_page:page_xyz",
                "source_type": "coda_page",
                "source_id": "page_xyz",
                "title": "Beta User Feedback on Scheduling",
                "snippet": "Multiple users mentioned difficulty understanding...",
                "url": "https://coda.io/d/doc123/_/page_xyz",
                "similarity": 0.82,
                "metadata": {"product_area": "scheduling"},
                "status": "suggested",
            }
        }
    )


class SearchErrorResponse(BaseModel):
    """Error response for search failures."""

    error: str = Field(..., description="Error message")
    code: Literal["EMBEDDING_UNAVAILABLE", "DATABASE_ERROR", "RATE_LIMITED", "VALIDATION_ERROR"] = Field(
        ..., description="Error code"
    )
    retry_after: Optional[int] = Field(
        default=None,
        description="Seconds to wait before retry (for rate limiting)"
    )


class EmbeddingStats(BaseModel):
    """Statistics about embeddings."""

    total_embeddings: int
    by_source_type: Dict[str, int]
    last_updated: Optional[datetime]
    embedding_model: str
    embedding_dimensions: int


class ReindexRequest(BaseModel):
    """Request to reindex embeddings."""

    source_types: Optional[List[str]] = Field(
        default=None,
        description="Source types to reindex (None = all)"
    )
    force: bool = Field(
        default=False,
        description="Force re-embed even if content unchanged"
    )


class ReindexResponse(BaseModel):
    """Response from reindex operation."""

    status: Literal["started", "completed", "failed"]
    source_types: List[str]
    items_processed: int = 0
    items_updated: int = 0
    items_failed: int = 0
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
