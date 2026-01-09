"""
Evidence Service

Evidence bundles, conversation links, and source statistics.
"""

import logging
from typing import List, Optional
from uuid import UUID

from ..models import (
    StoryEvidence,
    EvidenceUpdate,
    EvidenceExcerpt,
)

logger = logging.getLogger(__name__)


class EvidenceService:
    """
    Manages evidence bundles for stories.

    Responsibilities:
    - Link conversations to stories
    - Track theme signatures
    - Manage source statistics (intercom/coda counts)
    - Store excerpts for display
    """

    def __init__(self, db_connection):
        self.db = db_connection

    async def get_for_story(self, story_id: UUID) -> Optional[StoryEvidence]:
        """Get evidence bundle for a story."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement get_for_story")

    async def create_or_update(
        self,
        story_id: UUID,
        conversation_ids: List[str],
        theme_signatures: List[str],
        source_stats: dict,
        excerpts: List[EvidenceExcerpt],
    ) -> StoryEvidence:
        """Create or update evidence bundle for a story."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement create_or_update")

    async def add_conversation(
        self,
        story_id: UUID,
        conversation_id: str,
        source: str,
        excerpt: Optional[str] = None,
    ) -> StoryEvidence:
        """Add a single conversation to a story's evidence."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement add_conversation")

    async def add_theme(self, story_id: UUID, theme_signature: str) -> StoryEvidence:
        """Add a theme signature to a story's evidence."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement add_theme")

    async def update_source_stats(
        self, story_id: UUID, source_stats: dict
    ) -> StoryEvidence:
        """Update source statistics for a story."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement update_source_stats")

    async def get_by_conversation(self, conversation_id: str) -> List[StoryEvidence]:
        """Find all evidence bundles containing a conversation."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement get_by_conversation")

    async def get_by_theme(self, theme_signature: str) -> List[StoryEvidence]:
        """Find all evidence bundles containing a theme."""
        # TODO: Implement
        raise NotImplementedError("Next session: implement get_by_theme")
