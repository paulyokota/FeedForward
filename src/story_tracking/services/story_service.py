"""
Story Service

Canonical story state and metadata management.
This is the system of record for stories.
"""

import json
import logging
import sys
from typing import List, Optional
from uuid import UUID

# Size limit for code_context JSONB to prevent storage bloat
MAX_CODE_CONTEXT_SIZE = 1_000_000  # 1MB
MAX_IMPLEMENTATION_CONTEXT_SIZE = 500_000  # 500KB

from ..models import (
    ClusterMetadata,
    CodeContext,
    CodeContextClassification,
    CodeContextFile,
    CodeContextSnippet,
    ImplementationContext,
    ImplementationContextFile,
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
        # Serialize code_context to JSON if present, with size validation
        code_context_json = None
        if story.code_context is not None:
            code_context_json = json.dumps(story.code_context)
            if sys.getsizeof(code_context_json) > MAX_CODE_CONTEXT_SIZE:
                logger.warning(
                    f"code_context exceeds size limit "
                    f"({sys.getsizeof(code_context_json)} bytes), truncating snippets"
                )
                # Truncate code_snippets to reduce size
                truncated_context = story.code_context.copy()
                truncated_context["code_snippets"] = []
                code_context_json = json.dumps(truncated_context)

        # Serialize implementation_context to JSON if present (#180)
        implementation_context_json = None
        if story.implementation_context is not None:
            implementation_context_json = json.dumps(story.implementation_context)
            if sys.getsizeof(implementation_context_json) > MAX_IMPLEMENTATION_CONTEXT_SIZE:
                logger.warning(
                    f"implementation_context exceeds size limit "
                    f"({sys.getsizeof(implementation_context_json)} bytes), truncating"
                )
                # Truncate by removing prior_art_references first
                truncated_context = story.implementation_context.copy()
                truncated_context["prior_art_references"] = []
                implementation_context_json = json.dumps(truncated_context)

        # Serialize cluster_metadata to JSON if present (#109)
        cluster_metadata_json = None
        if story.cluster_metadata is not None:
            cluster_metadata_json = json.dumps(story.cluster_metadata)

        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO stories (
                    title, description, labels, priority, severity,
                    product_area, technical_area, status, confidence_score,
                    code_context, implementation_context,
                    grouping_method, cluster_id, cluster_metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, description, labels, priority, severity,
                          product_area, technical_area, status, confidence_score,
                          code_context, implementation_context,
                          evidence_count, conversation_count,
                          grouping_method, cluster_id, cluster_metadata,
                          created_at, updated_at
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
                code_context_json,
                implementation_context_json,
                story.grouping_method,
                story.cluster_id,
                cluster_metadata_json,
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
                       code_context, implementation_context,
                       evidence_count, conversation_count,
                       grouping_method, cluster_id, cluster_metadata,
                       created_at, updated_at
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
        if updates.code_context is not None:
            code_context_json = json.dumps(updates.code_context)
            if sys.getsizeof(code_context_json) > MAX_CODE_CONTEXT_SIZE:
                logger.warning(
                    f"code_context update exceeds size limit "
                    f"({sys.getsizeof(code_context_json)} bytes), truncating snippets"
                )
                truncated_context = updates.code_context.copy()
                truncated_context["code_snippets"] = []
                code_context_json = json.dumps(truncated_context)
            update_fields.append("code_context = %s")
            values.append(code_context_json)
        # Implementation context (#180)
        if updates.implementation_context is not None:
            impl_context_json = json.dumps(updates.implementation_context)
            if sys.getsizeof(impl_context_json) > MAX_IMPLEMENTATION_CONTEXT_SIZE:
                logger.warning(
                    f"implementation_context update exceeds size limit "
                    f"({sys.getsizeof(impl_context_json)} bytes), truncating"
                )
                truncated_context = updates.implementation_context.copy()
                truncated_context["prior_art_references"] = []
                impl_context_json = json.dumps(truncated_context)
            update_fields.append("implementation_context = %s")
            values.append(impl_context_json)
        # Hybrid clustering fields (#109)
        if updates.grouping_method is not None:
            update_fields.append("grouping_method = %s")
            values.append(updates.grouping_method)
        if updates.cluster_id is not None:
            update_fields.append("cluster_id = %s")
            values.append(updates.cluster_id)
        if updates.cluster_metadata is not None:
            update_fields.append("cluster_metadata = %s")
            values.append(json.dumps(updates.cluster_metadata))

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
                          code_context, implementation_context,
                          evidence_count, conversation_count,
                          grouping_method, cluster_id, cluster_metadata,
                          created_at, updated_at
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
        created_since: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StoryListResponse:
        """List stories with optional filtering.

        Args:
            status: Filter by story status
            product_area: Filter by product area
            created_since: Filter to stories created at or after this ISO timestamp
            limit: Max stories to return
            offset: Pagination offset
        """
        conditions = []
        values = []

        if status:
            conditions.append("status = %s")
            values.append(status)
        if product_area:
            conditions.append("product_area = %s")
            values.append(product_area)
        if created_since:
            conditions.append("created_at >= %s")
            values.append(created_since)

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
                       code_context, implementation_context,
                       evidence_count, conversation_count,
                       grouping_method, cluster_id, cluster_metadata,
                       created_at, updated_at
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
                       code_context, implementation_context,
                       evidence_count, conversation_count,
                       grouping_method, cluster_id, cluster_metadata,
                       created_at, updated_at
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
                       code_context, implementation_context,
                       evidence_count, conversation_count,
                       grouping_method, cluster_id, cluster_metadata,
                       created_at, updated_at
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
                       code_context, implementation_context,
                       evidence_count, conversation_count,
                       grouping_method, cluster_id, cluster_metadata,
                       created_at, updated_at
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
                       code_context, implementation_context,
                       evidence_count, conversation_count,
                       grouping_method, cluster_id, cluster_metadata,
                       created_at, updated_at
                FROM stories
                WHERE id = %s
            """, (str(story_id),))
            row = cur.fetchone()
            return self._row_to_story(row) if row else None

    def _row_to_story(self, row: dict) -> Story:
        """Convert database row to Story model."""
        # Parse code_context JSONB
        code_context = self._parse_code_context(row.get("code_context"))

        # Parse implementation_context JSONB (#180)
        implementation_context = self._parse_implementation_context(
            row.get("implementation_context")
        )

        # Parse cluster_metadata JSONB (#109)
        cluster_metadata = self._parse_cluster_metadata(row.get("cluster_metadata"))

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
            code_context=code_context,
            implementation_context=implementation_context,
            evidence_count=row["evidence_count"],
            conversation_count=row["conversation_count"],
            grouping_method=row.get("grouping_method", "signature"),
            cluster_id=row.get("cluster_id"),
            cluster_metadata=cluster_metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _parse_cluster_metadata(self, raw_data) -> Optional[ClusterMetadata]:
        """
        Parse cluster_metadata JSONB from database into ClusterMetadata model.

        Args:
            raw_data: JSONB data from database (dict or str or None)

        Returns:
            ClusterMetadata model or None if no data
        """
        if raw_data is None:
            return None

        # Parse JSON string if needed
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning("Failed to parse cluster_metadata JSON string")
                return None

        if not isinstance(raw_data, dict):
            return None

        try:
            return ClusterMetadata(
                embedding_cluster=raw_data.get("embedding_cluster", 0),
                action_type=raw_data.get("action_type", "unknown"),
                direction=raw_data.get("direction", "neutral"),
                conversation_count=raw_data.get("conversation_count", 0),
            )
        except Exception as e:
            logger.warning(f"Failed to parse cluster_metadata: {e}")
            return None

    def _parse_implementation_context(
        self, raw_data
    ) -> Optional[ImplementationContext]:
        """
        Parse implementation_context JSONB from database into ImplementationContext model.

        Handles both dict (from psycopg JSONB) and str (edge case) formats.

        Args:
            raw_data: JSONB data from database (dict or str or None)

        Returns:
            ImplementationContext model or None if no data

        Issue: #180
        """
        if raw_data is None:
            return None

        # Parse JSON string if needed
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning("Failed to parse implementation_context JSON string")
                return None

        if not isinstance(raw_data, dict):
            return None

        try:
            # Parse relevant_files list
            relevant_files = []
            for file_data in raw_data.get("relevant_files", []):
                relevant_files.append(ImplementationContextFile(
                    path=file_data.get("path", ""),
                    rationale=file_data.get("rationale", ""),
                    priority=file_data.get("priority", "medium"),
                ))

            # Parse synthesized_at timestamp
            synthesized_at = None
            if raw_data.get("synthesized_at"):
                from datetime import datetime
                try:
                    synthesized_at = datetime.fromisoformat(
                        raw_data["synthesized_at"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            return ImplementationContext(
                summary=raw_data.get("summary", ""),
                relevant_files=relevant_files,
                next_steps=raw_data.get("next_steps", []),
                prior_art_references=raw_data.get("prior_art_references", []),
                candidates_retrieved=raw_data.get("candidates_retrieved", 0),
                top_k=raw_data.get("top_k", 10),
                retrieval_query=raw_data.get("retrieval_query", ""),
                retrieval_duration_ms=raw_data.get("retrieval_duration_ms", 0),
                model=raw_data.get("model", "gpt-4o-mini"),
                synthesis_duration_ms=raw_data.get("synthesis_duration_ms", 0),
                synthesized_at=synthesized_at,
                source=raw_data.get("source", "hybrid"),
                success=raw_data.get("success", True),
                error=raw_data.get("error"),
                schema_version=raw_data.get("schema_version", "1.0"),
            )

        except Exception as e:
            logger.warning(
                f"Failed to parse implementation_context: {type(e).__name__}: {e}",
                extra={
                    "raw_data_type": type(raw_data).__name__,
                    "raw_data_preview": str(raw_data)[:200] if raw_data else None,
                },
                exc_info=True,
            )
            return None

    def _parse_code_context(self, raw_data) -> Optional[CodeContext]:
        """
        Parse code_context JSONB from database into CodeContext model.

        Handles both dict (from psycopg JSONB) and str (edge case) formats.

        Args:
            raw_data: JSONB data from database (dict or str or None)

        Returns:
            CodeContext model or None if no data
        """
        if raw_data is None:
            return None

        # Parse JSON string if needed
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning("Failed to parse code_context JSON string")
                return None

        if not isinstance(raw_data, dict):
            return None

        try:
            # Parse classification sub-object
            classification = None
            if raw_data.get("classification"):
                classification = CodeContextClassification(
                    category=raw_data["classification"].get("category", "unknown"),
                    confidence=raw_data["classification"].get("confidence", "low"),
                    reasoning=raw_data["classification"].get("reasoning", ""),
                    keywords_matched=raw_data["classification"].get("keywords_matched", []),
                )

            # Parse relevant_files list
            relevant_files = []
            for file_data in raw_data.get("relevant_files", []):
                relevant_files.append(CodeContextFile(
                    path=file_data.get("path", ""),
                    line_start=file_data.get("line_start"),
                    line_end=file_data.get("line_end"),
                    relevance=file_data.get("relevance", ""),
                ))

            # Parse code_snippets list
            code_snippets = []
            for snippet_data in raw_data.get("code_snippets", []):
                code_snippets.append(CodeContextSnippet(
                    file_path=snippet_data.get("file_path", ""),
                    line_start=snippet_data.get("line_start", 0),
                    line_end=snippet_data.get("line_end", 0),
                    content=snippet_data.get("content", ""),
                    language=snippet_data.get("language", "text"),
                    context=snippet_data.get("context", ""),
                ))

            # Parse explored_at timestamp
            explored_at = None
            if raw_data.get("explored_at"):
                from datetime import datetime
                try:
                    explored_at = datetime.fromisoformat(
                        raw_data["explored_at"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            return CodeContext(
                classification=classification,
                relevant_files=relevant_files,
                code_snippets=code_snippets,
                exploration_duration_ms=raw_data.get("exploration_duration_ms", 0),
                classification_duration_ms=raw_data.get("classification_duration_ms", 0),
                explored_at=explored_at,
                success=raw_data.get("success", True),
                error=raw_data.get("error"),
            )

        except Exception as e:
            logger.warning(
                f"Failed to parse code_context: {type(e).__name__}: {e}",
                extra={
                    "raw_data_type": type(raw_data).__name__,
                    "raw_data_preview": str(raw_data)[:200] if raw_data else None,
                },
                exc_info=True,
            )
            return None

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
