"""
Story Tracking API Endpoints

CRUD operations and views for the Story Tracking Web App.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db


def validate_iso_timestamp(timestamp: str) -> datetime:
    """
    Validate and parse an ISO 8601 timestamp string.

    Args:
        timestamp: String in ISO 8601 format (e.g., "2024-01-15T10:30:00Z")

    Returns:
        Parsed datetime object

    Raises:
        HTTPException: If timestamp is malformed
    """
    try:
        # Try parsing with timezone
        if timestamp.endswith("Z"):
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return datetime.fromisoformat(timestamp)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timestamp format. Expected ISO 8601 (e.g., 2024-01-15T10:30:00Z). Error: {str(e)}",
        )
from src.story_tracking.models import (
    Story,
    StoryCreate,
    StoryUpdate,
    StoryWithEvidence,
    StoryListResponse,
    StoryEvidence,
    EvidenceExcerpt,
    StoryComment,
    CommentCreate,
)
from src.story_tracking.services import StoryService, EvidenceService


router = APIRouter(prefix="/api/stories", tags=["stories"])


def get_story_service(db=Depends(get_db)) -> StoryService:
    """Dependency for StoryService."""
    return StoryService(db)


def get_evidence_service(db=Depends(get_db)) -> EvidenceService:
    """Dependency for EvidenceService."""
    return EvidenceService(db)


@router.get("", response_model=StoryListResponse)
def list_stories(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    product_area: Optional[str] = Query(default=None, description="Filter by product area"),
    created_since: Optional[str] = Query(
        default=None,
        description="Filter to stories created at or after this ISO timestamp (e.g., 2024-01-15T10:30:00Z)",
    ),
    sort_by: str = Query(
        default="updated_at",
        description="Sort by column: updated_at, created_at, confidence_score, actionability_score, fix_size_score, severity_score, churn_risk_score",
    ),
    sort_dir: str = Query(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort direction: asc or desc",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: StoryService = Depends(get_story_service),
):
    """
    List stories with optional filtering and sorting.

    Returns paginated list of stories. Sorting supports multi-factor scores (Issue #188).
    """
    # Validate and normalize timestamp format (S1 security fix)
    validated_timestamp = None
    if created_since:
        validated_dt = validate_iso_timestamp(created_since)
        validated_timestamp = validated_dt.isoformat()

    return service.list(
        status=status,
        product_area=product_area,
        created_since=validated_timestamp,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/board", response_model=Dict[str, List[Story]])
def get_board_view(
    service: StoryService = Depends(get_story_service),
):
    """
    Get stories grouped by status for kanban board view.

    Returns dict mapping status -> list of stories.
    """
    return service.get_board_view()


@router.get("/search", response_model=List[Story])
def search_stories(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    service: StoryService = Depends(get_story_service),
):
    """
    Search stories by title and description.
    """
    return service.search(query=q, limit=limit)


@router.get("/candidates", response_model=List[Story])
def get_candidates(
    limit: int = Query(default=50, ge=1, le=200),
    service: StoryService = Depends(get_story_service),
):
    """
    Get candidate stories (status='candidate').

    These are stories awaiting triage/review.
    """
    return service.get_candidates(limit=limit)


@router.get("/status/{status}", response_model=List[Story])
def get_by_status(
    status: str,
    service: StoryService = Depends(get_story_service),
):
    """
    Get all stories with a specific status.
    """
    return service.get_by_status(status)


@router.get("/{story_id}", response_model=StoryWithEvidence)
def get_story(
    story_id: UUID,
    service: StoryService = Depends(get_story_service),
):
    """
    Get story by ID with full details.

    Returns story with evidence, comments, and sync metadata.
    """
    story = service.get(story_id)
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {story_id} not found")
    return story


@router.post("", response_model=Story, status_code=201)
def create_story(
    story: StoryCreate,
    service: StoryService = Depends(get_story_service),
):
    """
    Create a new story.
    """
    return service.create(story)


@router.patch("/{story_id}", response_model=Story)
def update_story(
    story_id: UUID,
    updates: StoryUpdate,
    service: StoryService = Depends(get_story_service),
):
    """
    Update story fields.

    Only provided fields will be updated.
    """
    story = service.update(story_id, updates)
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {story_id} not found")
    return story


@router.delete("/{story_id}", status_code=204)
def delete_story(
    story_id: UUID,
    service: StoryService = Depends(get_story_service),
):
    """
    Delete a story and all related data.
    """
    deleted = service.delete(story_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Story {story_id} not found")


# Evidence endpoints


@router.get("/{story_id}/evidence", response_model=Optional[StoryEvidence])
def get_evidence(
    story_id: UUID,
    service: EvidenceService = Depends(get_evidence_service),
):
    """
    Get evidence bundle for a story.
    """
    return service.get_for_story(story_id)


@router.post("/{story_id}/evidence", response_model=StoryEvidence)
def update_evidence(
    story_id: UUID,
    conversation_ids: List[str],
    theme_signatures: List[str],
    source_stats: Dict[str, int],
    excerpts: List[EvidenceExcerpt],
    service: EvidenceService = Depends(get_evidence_service),
):
    """
    Create or update evidence bundle for a story.
    """
    return service.create_or_update(
        story_id=story_id,
        conversation_ids=conversation_ids,
        theme_signatures=theme_signatures,
        source_stats=source_stats,
        excerpts=excerpts,
    )


@router.post("/{story_id}/evidence/conversation", response_model=StoryEvidence)
def add_conversation_to_evidence(
    story_id: UUID,
    conversation_id: str = Query(..., description="Conversation ID to add"),
    source: str = Query(..., description="Source (intercom, coda)"),
    excerpt: Optional[str] = Query(default=None, description="Optional excerpt text"),
    service: EvidenceService = Depends(get_evidence_service),
):
    """
    Add a single conversation to a story's evidence.
    """
    return service.add_conversation(
        story_id=story_id,
        conversation_id=conversation_id,
        source=source,
        excerpt=excerpt,
    )


@router.post("/{story_id}/evidence/theme", response_model=StoryEvidence)
def add_theme_to_evidence(
    story_id: UUID,
    theme_signature: str = Query(..., description="Theme signature to add"),
    service: EvidenceService = Depends(get_evidence_service),
):
    """
    Add a theme signature to a story's evidence.
    """
    return service.add_theme(story_id=story_id, theme_signature=theme_signature)


# Comment endpoints


@router.post("/{story_id}/comments", response_model=StoryComment, status_code=201)
def add_comment(
    story_id: UUID,
    comment: CommentCreate,
    service: StoryService = Depends(get_story_service),
):
    """
    Add a comment to a story.
    """
    # Verify story exists
    story = service.get(story_id)
    if not story:
        raise HTTPException(status_code=404, detail=f"Story {story_id} not found")
    return service.add_comment(story_id, comment.body, comment.author)
