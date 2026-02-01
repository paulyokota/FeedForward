"""
Evidence Service

Evidence bundles, conversation links, and source statistics.
"""

import json
import logging
from typing import List, Optional, TYPE_CHECKING
from uuid import UUID

from ..models import (
    StoryEvidence,
    EvidenceExcerpt,
)

if TYPE_CHECKING:
    from src.research.unified_search import UnifiedSearchService
    from src.research.models import SuggestedEvidence

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

    def get_for_story(self, story_id: UUID) -> Optional[StoryEvidence]:
        """Get evidence bundle for a story."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, story_id, conversation_ids, theme_signatures,
                       source_stats, excerpts, created_at, updated_at
                FROM story_evidence
                WHERE story_id = %s
            """, (str(story_id),))
            row = cur.fetchone()

            if not row:
                return None

            return self._row_to_evidence(row)

    def create_or_update(
        self,
        story_id: UUID,
        conversation_ids: List[str],
        theme_signatures: List[str],
        source_stats: dict,
        excerpts: List[EvidenceExcerpt],
    ) -> StoryEvidence:
        """Create or update evidence bundle for a story."""
        # Issue #157: Include metadata fields in excerpt serialization
        excerpts_json = json.dumps([
            {
                "text": e.text,
                "source": e.source,
                "conversation_id": e.conversation_id,
                "email": e.email,
                "intercom_url": e.intercom_url,
                "org_id": e.org_id,
                "user_id": e.user_id,
                "contact_id": e.contact_id,
            }
            for e in excerpts
        ])

        with self.db.cursor() as cur:
            # Check if evidence exists
            cur.execute(
                "SELECT id FROM story_evidence WHERE story_id = %s",
                (str(story_id),)
            )
            existing = cur.fetchone()

            if existing:
                # Update existing
                cur.execute("""
                    UPDATE story_evidence
                    SET conversation_ids = %s,
                        theme_signatures = %s,
                        source_stats = %s,
                        excerpts = %s,
                        updated_at = NOW()
                    WHERE story_id = %s
                    RETURNING id, story_id, conversation_ids, theme_signatures,
                              source_stats, excerpts, created_at, updated_at
                """, (
                    conversation_ids,
                    theme_signatures,
                    json.dumps(source_stats),
                    excerpts_json,
                    str(story_id),
                ))
            else:
                # Create new
                cur.execute("""
                    INSERT INTO story_evidence (
                        story_id, conversation_ids, theme_signatures,
                        source_stats, excerpts
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, story_id, conversation_ids, theme_signatures,
                              source_stats, excerpts, created_at, updated_at
                """, (
                    str(story_id),
                    conversation_ids,
                    theme_signatures,
                    json.dumps(source_stats),
                    excerpts_json,
                ))

            row = cur.fetchone()

            # Update story counts
            self._update_story_counts(cur, story_id)

            return self._row_to_evidence(row)

    def add_conversation(
        self,
        story_id: UUID,
        conversation_id: str,
        source: str,
        excerpt: Optional[str] = None,
        theme_signature: Optional[str] = None,  # Issue #197: Populate theme_signatures
    ) -> StoryEvidence:
        """Add a single conversation to a story's evidence."""
        with self.db.cursor() as cur:
            # Get current evidence
            cur.execute("""
                SELECT id, conversation_ids, theme_signatures, source_stats, excerpts
                FROM story_evidence
                WHERE story_id = %s
            """, (str(story_id),))
            row = cur.fetchone()

            if row:
                # Update existing evidence
                conversation_ids = list(row["conversation_ids"] or [])
                if conversation_id not in conversation_ids:
                    conversation_ids.append(conversation_id)

                # Issue #197: Append theme_signature if provided and not already present
                theme_signatures = list(row["theme_signatures"] or [])
                if theme_signature and theme_signature not in theme_signatures:
                    theme_signatures.append(theme_signature)

                source_stats = row["source_stats"] or {}
                if isinstance(source_stats, str):
                    source_stats = json.loads(source_stats)
                source_stats[source] = source_stats.get(source, 0) + 1

                excerpts_data = row["excerpts"] or []
                if isinstance(excerpts_data, str):
                    excerpts_data = json.loads(excerpts_data)

                if excerpt:
                    excerpts_data.append({
                        "text": excerpt,
                        "source": source,
                        "conversation_id": conversation_id,
                    })

                cur.execute("""
                    UPDATE story_evidence
                    SET conversation_ids = %s,
                        theme_signatures = %s,
                        source_stats = %s,
                        excerpts = %s,
                        updated_at = NOW()
                    WHERE story_id = %s
                    RETURNING id, story_id, conversation_ids, theme_signatures,
                              source_stats, excerpts, created_at, updated_at
                """, (
                    conversation_ids,
                    theme_signatures,
                    json.dumps(source_stats),
                    json.dumps(excerpts_data),
                    str(story_id),
                ))
            else:
                # Create new evidence
                # Issue #197: Initialize theme_signatures with signature if provided
                theme_signatures = [theme_signature] if theme_signature else []
                source_stats = {source: 1}
                excerpts_data = []
                if excerpt:
                    excerpts_data.append({
                        "text": excerpt,
                        "source": source,
                        "conversation_id": conversation_id,
                    })

                cur.execute("""
                    INSERT INTO story_evidence (
                        story_id, conversation_ids, theme_signatures,
                        source_stats, excerpts
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, story_id, conversation_ids, theme_signatures,
                              source_stats, excerpts, created_at, updated_at
                """, (
                    str(story_id),
                    [conversation_id],
                    theme_signatures,
                    json.dumps(source_stats),
                    json.dumps(excerpts_data),
                ))

            row = cur.fetchone()
            self._update_story_counts(cur, story_id)
            return self._row_to_evidence(row)

    def add_theme(self, story_id: UUID, theme_signature: str) -> StoryEvidence:
        """Add a theme signature to a story's evidence."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, theme_signatures
                FROM story_evidence
                WHERE story_id = %s
            """, (str(story_id),))
            row = cur.fetchone()

            if row:
                themes = list(row["theme_signatures"] or [])
                if theme_signature not in themes:
                    themes.append(theme_signature)

                cur.execute("""
                    UPDATE story_evidence
                    SET theme_signatures = %s, updated_at = NOW()
                    WHERE story_id = %s
                    RETURNING id, story_id, conversation_ids, theme_signatures,
                              source_stats, excerpts, created_at, updated_at
                """, (themes, str(story_id)))
            else:
                cur.execute("""
                    INSERT INTO story_evidence (
                        story_id, conversation_ids, theme_signatures,
                        source_stats, excerpts
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, story_id, conversation_ids, theme_signatures,
                              source_stats, excerpts, created_at, updated_at
                """, (
                    str(story_id),
                    [],
                    [theme_signature],
                    json.dumps({}),
                    json.dumps([]),
                ))

            row = cur.fetchone()
            self._update_story_counts(cur, story_id)
            return self._row_to_evidence(row)

    def update_source_stats(
        self, story_id: UUID, source_stats: dict
    ) -> Optional[StoryEvidence]:
        """Update source statistics for a story."""
        with self.db.cursor() as cur:
            cur.execute("""
                UPDATE story_evidence
                SET source_stats = %s, updated_at = NOW()
                WHERE story_id = %s
                RETURNING id, story_id, conversation_ids, theme_signatures,
                          source_stats, excerpts, created_at, updated_at
            """, (json.dumps(source_stats), str(story_id)))
            row = cur.fetchone()

            if not row:
                return None

            return self._row_to_evidence(row)

    def get_by_conversation(self, conversation_id: str) -> List[StoryEvidence]:
        """Find all evidence bundles containing a conversation."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, story_id, conversation_ids, theme_signatures,
                       source_stats, excerpts, created_at, updated_at
                FROM story_evidence
                WHERE %s = ANY(conversation_ids)
            """, (conversation_id,))
            rows = cur.fetchall()
            return [self._row_to_evidence(row) for row in rows]

    def get_by_theme(self, theme_signature: str) -> List[StoryEvidence]:
        """Find all evidence bundles containing a theme."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, story_id, conversation_ids, theme_signatures,
                       source_stats, excerpts, created_at, updated_at
                FROM story_evidence
                WHERE %s = ANY(theme_signatures)
            """, (theme_signature,))
            rows = cur.fetchall()
            return [self._row_to_evidence(row) for row in rows]

    def _update_story_counts(self, cur, story_id: UUID) -> None:
        """Update story counts from evidence."""
        # Issue #197: Added excerpt_count with COALESCE safety for NULL/empty excerpts
        cur.execute("""
            UPDATE stories s
            SET
                evidence_count = COALESCE((
                    SELECT array_length(theme_signatures, 1)
                    FROM story_evidence se
                    WHERE se.story_id = s.id
                ), 0),
                conversation_count = COALESCE((
                    SELECT array_length(conversation_ids, 1)
                    FROM story_evidence se
                    WHERE se.story_id = s.id
                ), 0),
                excerpt_count = COALESCE((
                    SELECT jsonb_array_length(COALESCE(excerpts, '[]'::jsonb))
                    FROM story_evidence se
                    WHERE se.story_id = s.id
                ), 0)
            WHERE s.id = %s
        """, (str(story_id),))

    def _row_to_evidence(self, row: dict) -> StoryEvidence:
        """Convert database row to StoryEvidence model."""
        excerpts_data = row["excerpts"] or []
        if isinstance(excerpts_data, str):
            excerpts_data = json.loads(excerpts_data)

        # Issue #197: Include all metadata fields from EvidenceExcerpt model
        # Handle both dict format and legacy string format for backwards compatibility
        excerpts = []
        for e in excerpts_data:
            if isinstance(e, dict):
                excerpts.append(EvidenceExcerpt(
                    text=e.get("text", ""),
                    source=e.get("source", "unknown"),
                    conversation_id=e.get("conversation_id"),
                    email=e.get("email"),
                    intercom_url=e.get("intercom_url"),
                    org_id=e.get("org_id"),
                    user_id=e.get("user_id"),
                    contact_id=e.get("contact_id"),
                ))
            elif isinstance(e, str) and e.strip():
                # Legacy string format - convert to EvidenceExcerpt with minimal metadata
                excerpts.append(EvidenceExcerpt(
                    text=e,
                    source="unknown",
                ))

        source_stats = row["source_stats"] or {}
        if isinstance(source_stats, str):
            source_stats = json.loads(source_stats)

        return StoryEvidence(
            id=row["id"],
            story_id=row["story_id"],
            conversation_ids=row["conversation_ids"] or [],
            theme_signatures=row["theme_signatures"] or [],
            source_stats=source_stats,
            excerpts=excerpts,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def suggest_research_evidence(
        self,
        story_id: UUID,
        search_service: "UnifiedSearchService",
        min_similarity: float = 0.7,
        max_suggestions: int = 5,
    ) -> List["SuggestedEvidence"]:
        """
        Find research that supports this story's theme.

        Uses semantic search to find Coda research pages and themes
        that are relevant to the story's title and description.

        Args:
            story_id: The story to find evidence for
            search_service: UnifiedSearchService instance
            min_similarity: Minimum similarity threshold (default 0.7)
            max_suggestions: Maximum suggestions to return (default 5)

        Returns:
            List of SuggestedEvidence with research matches
        """
        from research.models import SuggestedEvidence

        # Get story title and description
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT title, description
                FROM stories
                WHERE id = %s
            """, (str(story_id),))
            row = cur.fetchone()

            if not row:
                logger.warning(f"Story {story_id} not found")
                return []

            title = row.get("title", "") or ""
            description = row.get("description", "") or ""

        # Build search query from story content
        query = f"{title} {description}".strip()
        if not query:
            logger.debug(f"Story {story_id} has no title or description for search")
            return []

        try:
            # Search for matching research (Coda only)
            results = search_service.suggest_evidence(
                query=query,
                min_similarity=min_similarity,
                max_suggestions=max_suggestions,
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

            logger.info(
                f"Found {len(suggestions)} research suggestions for story {story_id}"
            )
            return suggestions

        except Exception as e:
            logger.error(f"Failed to suggest research evidence for {story_id}: {e}")
            return []
