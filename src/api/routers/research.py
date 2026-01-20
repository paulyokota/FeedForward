"""
Research API Router

Endpoints for unified search and RAG capabilities.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from psycopg2 import IntegrityError
from pydantic import BaseModel, Field

from src.api.deps import get_db
from src.research.models import (
    UnifiedSearchResult,
    UnifiedSearchRequest,
    SuggestedEvidence,
    EmbeddingStats,
    ReindexRequest,
    ReindexResponse,
    EvidenceDecisionResponse,
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

    # Get previously rejected evidence IDs for this story
    with db.cursor() as cur:
        cur.execute("""
            SELECT evidence_id FROM suggested_evidence_decisions
            WHERE story_id = %s AND decision = 'rejected'
        """, (str(story_id),))
        rejected_ids = {row["evidence_id"] for row in cur.fetchall()}

    # Filter out rejected suggestions
    results = [r for r in results if f"{r.source_type}:{r.source_id}" not in rejected_ids]

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


# --- Evidence Decision Endpoints ---

# Valid source types for evidence
VALID_SOURCE_TYPES = {"coda_page", "coda_theme", "intercom"}


def _parse_evidence_id(evidence_id: str) -> tuple[str, str]:
    """
    Parse evidence_id in format 'source_type:source_id'.

    Returns:
        Tuple of (source_type, source_id)

    Raises:
        HTTPException: If format is invalid or source_type is unknown
    """
    if ":" not in evidence_id:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid evidence_id format: '{evidence_id}'. Expected 'source_type:source_id'"
        )

    parts = evidence_id.split(":", 1)
    source_type = parts[0]
    source_id = parts[1]

    if not source_type or not source_id:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid evidence_id format: '{evidence_id}'. Both source_type and source_id are required"
        )

    if source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type: '{source_type}'. Valid types: {VALID_SOURCE_TYPES}"
        )

    return source_type, source_id


def _validate_story_exists(db, story_id: UUID) -> None:
    """
    Validate that a story exists.

    Raises:
        HTTPException: 404 if story not found
    """
    with db.cursor() as cur:
        cur.execute("SELECT id FROM stories WHERE id = %s", (str(story_id),))
        if not cur.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"Story {story_id} not found"
            )


def _record_evidence_decision(
    db,
    story_id: UUID,
    evidence_id: str,
    source_type: str,
    source_id: str,
    decision: str,
    similarity_score: float | None = None,
) -> None:
    """
    Record an evidence decision in the database.

    Raises:
        HTTPException: 404 if story not found, 409 if decision already exists
    """
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO suggested_evidence_decisions
                    (story_id, evidence_id, source_type, source_id, decision, similarity_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (str(story_id), evidence_id, source_type, source_id, decision, similarity_score)
            )
    except IntegrityError as e:
        # Check for unique constraint violation (duplicate decision)
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=409,
                detail=f"Decision already exists for evidence '{evidence_id}' on story {story_id}"
            )
        # Check for foreign key violation (story not found)
        if "foreign key" in error_str or "fk_" in error_str:
            raise HTTPException(
                status_code=404,
                detail=f"Story {story_id} not found"
            )
        logger.error("Database integrity error while recording evidence decision", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to record evidence decision"
        )
    except Exception as e:
        logger.error("Failed to record evidence decision", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to record evidence decision"
        )


@router.post("/stories/{story_id}/suggested-evidence/{evidence_id}/accept", response_model=EvidenceDecisionResponse)
def accept_evidence(
    story_id: UUID,
    evidence_id: str,
    db=Depends(get_db),
):
    """
    Accept suggested evidence for a story.

    Persists the PM's decision to accept this evidence as relevant
    to the story. Accepted evidence will be shown as linked research.

    **Path Parameters:**
    - `story_id`: UUID of the story
    - `evidence_id`: Evidence identifier in format 'source_type:source_id'

    **Returns:**
    - Success response with decision details

    **Errors:**
    - 400: Invalid evidence_id format or source_type
    - 404: Story not found
    - 409: Decision already exists for this evidence
    """
    # Parse and validate evidence_id
    source_type, source_id = _parse_evidence_id(evidence_id)

    # Validate story exists
    _validate_story_exists(db, story_id)

    # Record the decision
    _record_evidence_decision(
        db=db,
        story_id=story_id,
        evidence_id=evidence_id,
        source_type=source_type,
        source_id=source_id,
        decision="accepted",
    )

    logger.info(f"Evidence accepted: story={story_id}, evidence={evidence_id}")

    return EvidenceDecisionResponse(
        success=True,
        story_id=str(story_id),
        evidence_id=evidence_id,
        decision="accepted",
    )


@router.post("/stories/{story_id}/suggested-evidence/{evidence_id}/reject", response_model=EvidenceDecisionResponse)
def reject_evidence(
    story_id: UUID,
    evidence_id: str,
    db=Depends(get_db),
):
    """
    Reject suggested evidence for a story.

    Persists the PM's decision to reject this evidence as not relevant.
    Rejected evidence will be hidden from future suggestions for this story.

    **Path Parameters:**
    - `story_id`: UUID of the story
    - `evidence_id`: Evidence identifier in format 'source_type:source_id'

    **Returns:**
    - Success response with decision details

    **Errors:**
    - 400: Invalid evidence_id format or source_type
    - 404: Story not found
    - 409: Decision already exists for this evidence
    """
    # Parse and validate evidence_id
    source_type, source_id = _parse_evidence_id(evidence_id)

    # Validate story exists
    _validate_story_exists(db, story_id)

    # Record the decision
    _record_evidence_decision(
        db=db,
        story_id=story_id,
        evidence_id=evidence_id,
        source_type=source_type,
        source_id=source_id,
        decision="rejected",
    )

    logger.info(f"Evidence rejected: story={story_id}, evidence={evidence_id}")

    return EvidenceDecisionResponse(
        success=True,
        story_id=str(story_id),
        evidence_id=evidence_id,
        decision="rejected",
    )
