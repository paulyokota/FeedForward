"""
Story Service

Canonical story state and metadata management.
This is the system of record for stories.
"""

import json
import logging
from typing import List, Optional
from uuid import UUID

from ..models import (
    Story,
    StoryCreate,
    StoryUpdate,
    StoryWithEvidence,
    StoryListResponse,
    StoryEvidence,
    StoryComment,
    SyncMetadata,
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

    def create(self, story: StoryCreate) -> Story:
        """Create a new story."""
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO stories (
                    title, description, labels, priority, severity,
                    product_area, technical_area, status, confidence_score
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, description, labels, priority, severity,
                          product_area, technical_area, status, confidence_score,
                          evidence_count, conversation_count, created_at, updated_at
            """, (
                story.title,
                story.description,
                story.labels,
                story.priority,
                story.severity,
                story.product_area,
                story.technical_area,
                story.status,
                story.confidence_score,
            ))
            row = cur.fetchone()
            return self._row_to_story(row)

    def get(self, story_id: UUID) -> Optional[StoryWithEvidence]:
        """Get story by ID with evidence, comments, and sync metadata."""
        with self.db.cursor() as cur:
            # Get story
            cur.execute("""
                SELECT id, title, description, labels, priority, severity,
                       product_area, technical_area, status, confidence_score,
                       evidence_count, conversation_count, created_at, updated_at
                FROM stories
                WHERE id = %s
            """, (str(story_id),))
            row = cur.fetchone()

            if not row:
                return None

            story = self._row_to_story(row)

            # Get evidence
            cur.execute("""
                SELECT id, story_id, conversation_ids, theme_signatures,
                       source_stats, excerpts, created_at, updated_at
                FROM story_evidence
                WHERE story_id = %s
            """, (str(story_id),))
            evidence_row = cur.fetchone()
            evidence = self._row_to_evidence(evidence_row) if evidence_row else None

            # Get comments
            cur.execute("""
                SELECT id, story_id, external_id, source, body, author, created_at
                FROM story_comments
                WHERE story_id = %s
                ORDER BY created_at ASC
            """, (str(story_id),))
            comment_rows = cur.fetchall()
            comments = [self._row_to_comment(r) for r in comment_rows]

            # Get sync metadata
            cur.execute("""
                SELECT story_id, shortcut_story_id, last_internal_update_at,
                       last_external_update_at, last_synced_at, last_sync_status,
                       last_sync_error, last_sync_direction
                FROM story_sync_metadata
                WHERE story_id = %s
            """, (str(story_id),))
            sync_row = cur.fetchone()
            sync = self._row_to_sync(sync_row) if sync_row else None

            return StoryWithEvidence(
                **story.model_dump(),
                evidence=evidence,
                sync=sync,
                comments=comments,
            )

    def update(self, story_id: UUID, updates: StoryUpdate) -> Optional[Story]:
        """Update story fields."""
        # Build dynamic update query
        update_fields = []
        values = []

        if updates.title is not None:
            update_fields.append("title = %s")
            values.append(updates.title)
        if updates.description is not None:
            update_fields.append("description = %s")
            values.append(updates.description)
        if updates.labels is not None:
            update_fields.append("labels = %s")
            values.append(updates.labels)
        if updates.priority is not None:
            update_fields.append("priority = %s")
            values.append(updates.priority)
        if updates.severity is not None:
            update_fields.append("severity = %s")
            values.append(updates.severity)
        if updates.product_area is not None:
            update_fields.append("product_area = %s")
            values.append(updates.product_area)
        if updates.technical_area is not None:
            update_fields.append("technical_area = %s")
            values.append(updates.technical_area)
        if updates.status is not None:
            update_fields.append("status = %s")
            values.append(updates.status)
        if updates.confidence_score is not None:
            update_fields.append("confidence_score = %s")
            values.append(updates.confidence_score)

        if not update_fields:
            # No fields to update, just return current story
            return self._get_story_only(story_id)

        values.append(str(story_id))

        with self.db.cursor() as cur:
            cur.execute(f"""
                UPDATE stories
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, title, description, labels, priority, severity,
                          product_area, technical_area, status, confidence_score,
                          evidence_count, conversation_count, created_at, updated_at
            """, values)
            row = cur.fetchone()

            if not row:
                return None
            return self._row_to_story(row)

    def delete(self, story_id: UUID) -> bool:
        """Delete a story and its related data (cascades)."""
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM stories WHERE id = %s", (str(story_id),))
            return cur.rowcount > 0

    def list(
        self,
        status: Optional[str] = None,
        product_area: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StoryListResponse:
        """List stories with optional filtering."""
        conditions = []
        values = []

        if status:
            conditions.append("status = %s")
            values.append(status)
        if product_area:
            conditions.append("product_area = %s")
            values.append(product_area)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        with self.db.cursor() as cur:
            # Get total count
            cur.execute(f"SELECT COUNT(*) as count FROM stories {where_clause}", values)
            total = cur.fetchone()["count"]

            # Get stories
            cur.execute(f"""
                SELECT id, title, description, labels, priority, severity,
                       product_area, technical_area, status, confidence_score,
                       evidence_count, conversation_count, created_at, updated_at
                FROM stories
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
            """, values + [limit, offset])
            rows = cur.fetchall()

            stories = [self._row_to_story(row) for row in rows]

            return StoryListResponse(
                stories=stories,
                total=total,
                limit=limit,
                offset=offset,
            )

    def get_by_status(self, status: str) -> List[Story]:
        """Get all stories with a given status (for board view)."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, title, description, labels, priority, severity,
                       product_area, technical_area, status, confidence_score,
                       evidence_count, conversation_count, created_at, updated_at
                FROM stories
                WHERE status = %s
                ORDER BY confidence_score DESC NULLS LAST, updated_at DESC
            """, (status,))
            rows = cur.fetchall()
            return [self._row_to_story(row) for row in rows]

    def get_board_view(self) -> dict:
        """Get stories grouped by status for kanban board."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, title, description, labels, priority, severity,
                       product_area, technical_area, status, confidence_score,
                       evidence_count, conversation_count, created_at, updated_at
                FROM stories
                ORDER BY confidence_score DESC NULLS LAST, updated_at DESC
            """)
            rows = cur.fetchall()

            # Group by status
            board = {}
            for row in rows:
                story = self._row_to_story(row)
                status = story.status
                if status not in board:
                    board[status] = []
                board[status].append(story)

            return board

    def search(self, query: str, limit: int = 20) -> List[Story]:
        """Search stories by title/description."""
        with self.db.cursor() as cur:
            search_pattern = f"%{query}%"
            cur.execute("""
                SELECT id, title, description, labels, priority, severity,
                       product_area, technical_area, status, confidence_score,
                       evidence_count, conversation_count, created_at, updated_at
                FROM stories
                WHERE title ILIKE %s OR description ILIKE %s
                ORDER BY updated_at DESC
                LIMIT %s
            """, (search_pattern, search_pattern, limit))
            rows = cur.fetchall()
            return [self._row_to_story(row) for row in rows]

    def get_candidates(self, limit: int = 50) -> List[Story]:
        """Get candidate stories (not yet triaged)."""
        result = self.list(status="candidate", limit=limit)
        return result.stories

    def update_counts(self, story_id: UUID) -> None:
        """Recalculate evidence_count and conversation_count from evidence table."""
        with self.db.cursor() as cur:
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
                    ), 0)
                WHERE s.id = %s
            """, (str(story_id),))

    def add_comment(self, story_id: UUID, body: str, author: Optional[str] = None) -> StoryComment:
        """Add a comment to a story."""
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO story_comments (story_id, body, author, source)
                VALUES (%s, %s, %s, 'internal')
                RETURNING id, story_id, external_id, source, body, author, created_at
            """, (str(story_id), body, author))
            row = cur.fetchone()
            return self._row_to_comment(row)

    def _get_story_only(self, story_id: UUID) -> Optional[Story]:
        """Get story without related data."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, title, description, labels, priority, severity,
                       product_area, technical_area, status, confidence_score,
                       evidence_count, conversation_count, created_at, updated_at
                FROM stories
                WHERE id = %s
            """, (str(story_id),))
            row = cur.fetchone()
            return self._row_to_story(row) if row else None

    def _row_to_story(self, row: dict) -> Story:
        """Convert database row to Story model."""
        return Story(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            labels=row["labels"] or [],
            priority=row["priority"],
            severity=row["severity"],
            product_area=row["product_area"],
            technical_area=row["technical_area"],
            status=row["status"],
            confidence_score=float(row["confidence_score"]) if row["confidence_score"] else None,
            evidence_count=row["evidence_count"],
            conversation_count=row["conversation_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_evidence(self, row: dict) -> StoryEvidence:
        """Convert database row to StoryEvidence model."""
        from ..models import EvidenceExcerpt

        excerpts_data = row["excerpts"] or []
        if isinstance(excerpts_data, str):
            excerpts_data = json.loads(excerpts_data)

        excerpts = [
            EvidenceExcerpt(
                text=e.get("text", ""),
                source=e.get("source", "unknown"),
                conversation_id=e.get("conversation_id"),
            )
            for e in excerpts_data
        ]

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

    def _row_to_comment(self, row: dict) -> StoryComment:
        """Convert database row to StoryComment model."""
        return StoryComment(
            id=row["id"],
            story_id=row["story_id"],
            external_id=row["external_id"],
            source=row["source"],
            body=row["body"],
            author=row["author"],
            created_at=row["created_at"],
        )

    def _row_to_sync(self, row: dict) -> SyncMetadata:
        """Convert database row to SyncMetadata model."""
        return SyncMetadata(
            story_id=row["story_id"],
            shortcut_story_id=row["shortcut_story_id"],
            last_internal_update_at=row["last_internal_update_at"],
            last_external_update_at=row["last_external_update_at"],
            last_synced_at=row["last_synced_at"],
            last_sync_status=row["last_sync_status"],
            last_sync_error=row["last_sync_error"],
            last_sync_direction=row["last_sync_direction"],
        )
