"""
Research API Router

Endpoints for unified search and RAG capabilities.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from src.api.deps import get_db
from src.research.models import (
    UnifiedSearchResult,
    UnifiedSearchRequest,
    SuggestedEvidence,
    EmbeddingStats,
    ReindexRequest,
    ReindexResponse,
)
from src.research.unified_search import UnifiedSearchService
from src.research.embedding_pipeline import EmbeddingPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


# Dependency for search service
def get_search_service() -> UnifiedSearchService:
    """Get the unified search service."""
    return UnifiedSearchService()


# Response models
class SearchResponse(BaseModel):
    """Search endpoint response."""
    results: List[UnifiedSearchResult]
    total: int
    query: str


class SimilarResponse(BaseModel):
    """Similar content endpoint response."""
    results: List[UnifiedSearchResult]
    reference: dict  # source_type, source_id


class SuggestedEvidenceResponse(BaseModel):
    """Suggested evidence endpoint response."""
    story_id: str
    suggestions: List[SuggestedEvidence]


# --- Search Endpoints ---


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Results to skip"),
    source_types: Optional[str] = Query(
        default=None,
        description="Comma-separated source types: coda_page,coda_theme,intercom"
    ),
    min_similarity: float = Query(
        default=0.5,
        ge=0.3,
        le=1.0,
        description="Minimum similarity threshold"
    ),
    service: UnifiedSearchService = Depends(get_search_service),
):
    """
    Search across all research sources.

    Returns semantically similar content to the query, ranked by similarity.
    Supports filtering by source type.

    **Source Types:**
    - `coda_page`: Coda research pages and AI summaries
    - `coda_theme`: Extracted themes from synthesis tables
    - `intercom`: Support conversation content

    **Examples:**
    - `/api/research/search?q=scheduling+confusion`
    - `/api/research/search?q=pin+not+posting&source_types=coda_page,coda_theme`
    """
    # Parse source types
    parsed_sources = None
    if source_types:
        parsed_sources = [s.strip() for s in source_types.split(",") if s.strip()]
        # Validate source types
        valid_types = {"coda_page", "coda_theme", "intercom"}
        invalid = set(parsed_sources) - valid_types
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source types: {invalid}. Valid types: {valid_types}"
            )

    results = service.search(
        query=q,
        limit=limit,
        offset=offset,
        source_types=parsed_sources,
        min_similarity=min_similarity,
    )

    return SearchResponse(
        results=results,
        total=len(results),
        query=q,
    )


@router.get("/similar/{source_type}/{source_id}", response_model=SimilarResponse)
def find_similar(
    source_type: str,
    source_id: str,
    limit: int = Query(default=10, ge=1, le=50, description="Max results"),
    exclude_same_source: bool = Query(
        default=False,
        description="Exclude items from same source type"
    ),
    min_similarity: float = Query(
        default=0.5,
        ge=0.3,
        le=1.0,
        description="Minimum similarity threshold"
    ),
    service: UnifiedSearchService = Depends(get_search_service),
):
    """
    Find content similar to a specific item ("more like this").

    **Path Parameters:**
    - `source_type`: Type of reference item (coda_page, coda_theme, intercom)
    - `source_id`: ID of reference item

    **Examples:**
    - `/api/research/similar/coda_page/page_abc123`
    - `/api/research/similar/coda_theme/pin_spacing_confusion`
    """
    # Validate source type
    valid_types = {"coda_page", "coda_theme", "intercom"}
    if source_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source type: {source_type}. Valid types: {valid_types}"
        )

    results = service.search_similar(
        source_type=source_type,
        source_id=source_id,
        limit=limit,
        exclude_same_source=exclude_same_source,
        min_similarity=min_similarity,
    )

    return SimilarResponse(
        results=results,
        reference={"source_type": source_type, "source_id": source_id},
    )


# --- Stats Endpoint ---


@router.get("/stats", response_model=EmbeddingStats)
def get_stats(
    service: UnifiedSearchService = Depends(get_search_service),
):
    """
    Get embedding statistics.

    Returns counts by source type, last update time, and model info.
    """
    return service.get_stats()


# --- Reindex Endpoint (Admin) ---


@router.post("/reindex", response_model=ReindexResponse)
def trigger_reindex(
    request: ReindexRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger re-embedding of content.

    **Admin endpoint** - triggers embedding regeneration.

    By default, only re-embeds content that has changed (based on content hash).
    Use `force=true` to re-embed everything.

    **Request Body:**
    - `source_types`: Optional list of sources to reindex (null = all)
    - `force`: Force re-embed even if content unchanged

    **Note:** This is an async operation. Returns immediately with status.
    """
    # TODO: Add authentication check for admin
    # For now, this endpoint is available to all users

    pipeline = EmbeddingPipeline()

    # Run synchronously for now (can move to background for large datasets)
    result = pipeline.run(
        source_types=request.source_types,
        force=request.force,
    )

    return result


# --- Story Evidence Suggestion Endpoint ---


@router.get("/stories/{story_id}/suggested-evidence", response_model=SuggestedEvidenceResponse)
def get_suggested_evidence(
    story_id: UUID,
    limit: int = Query(default=5, ge=1, le=20, description="Max suggestions"),
    min_similarity: float = Query(
        default=0.7,
        ge=0.5,
        le=1.0,
        description="Minimum similarity threshold"
    ),
    service: UnifiedSearchService = Depends(get_search_service),
    db=Depends(get_db),
):
    """
    Get suggested research evidence for a story.

    Finds Coda research that semantically matches the story's
    title and description.

    **Returns:**
    - List of suggested evidence with similarity scores
    - PM can accept/reject each suggestion

    **Note:** Only searches Coda sources, not Intercom.
    """
    # Get story title and description
    with db.cursor() as cur:
        cur.execute("""
            SELECT title, description
            FROM stories
            WHERE id = %s
        """, (str(story_id),))
        row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Story {story_id} not found"
            )

        title = row["title"] or ""
        description = row["description"] or ""

    # Build search query from story content
    query = f"{title} {description}".strip()
    if not query:
        return SuggestedEvidenceResponse(
            story_id=str(story_id),
            suggestions=[],
        )

    # Search for matching research
    results = service.suggest_evidence(
        query=query,
        min_similarity=min_similarity,
        max_suggestions=limit,
    )

    # Convert to SuggestedEvidence format
    suggestions = [
        SuggestedEvidence(
            id=f"{r.source_type}:{r.source_id}",
            source_type=r.source_type,
            source_id=r.source_id,
            title=r.title,
            snippet=r.snippet,
            url=r.url,
            similarity=r.similarity,
            metadata=r.metadata,
            status="suggested",
        )
        for r in results
    ]

    return SuggestedEvidenceResponse(
        story_id=str(story_id),
        suggestions=suggestions,
    )
