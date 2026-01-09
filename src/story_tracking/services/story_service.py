"""
Story Service

Canonical story state and metadata management.
This is the system of record for stories.
"""

import logging
from typing import List, Optional
from uuid import UUID

from ..models import (
    Story,
    StoryCreate,
    StoryUpdate,
    StoryWithEvidence,
    StoryListResponse,
)

logger = logging.getLogger(__name__)


class StoryService:
    """
    Manages canonical story state.

    Responsibilities:
    - CRUD operations on stories
    - Status transitions (lifecycle-agnostic)
    - Aggregation queries for board/list views
    """

    def __init__(self, db_connection):
        self.db = db_connection

    async def create(self, story: StoryCreate) -> Story:
        """Create a new story."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement create")

    async def get(self, story_id: UUID) -> Optional[StoryWithEvidence]:
        """Get story by ID with evidence and sync metadata."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement get")

    async def update(self, story_id: UUID, updates: StoryUpdate) -> Story:
        """Update story fields."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement update")

    async def delete(self, story_id: UUID) -> bool:
        """Delete a story and its related data."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement delete")

    async def list(
        self,
        status: Optional[str] = None,
        product_area: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StoryListResponse:
        """List stories with optional filtering."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement list")

    async def get_by_status(self, status: str) -> List[Story]:
        """Get all stories with a given status (for board view)."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement get_by_status")

    async def search(self, query: str, limit: int = 20) -> List[Story]:
        """Search stories by title/description."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement search")

    async def get_candidates(self, limit: int = 50) -> List[Story]:
        """Get candidate stories (not yet triaged)."""
        return await self.list(status="candidate", limit=limit)

    async def update_counts(self, story_id: UUID) -> None:
        """Recalculate evidence_count and conversation_count from evidence table."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement update_counts")
