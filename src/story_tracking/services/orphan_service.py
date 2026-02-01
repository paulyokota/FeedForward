"""
Orphan Service

Manages sub-groups with <MIN_GROUP_SIZE conversations that accumulate
over time until they reach the threshold for graduation to stories.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..models import (
    MIN_GROUP_SIZE,
    RECENCY_WINDOW_DAYS,
    Orphan,
    OrphanCreate,
    OrphanGraduationResult,
    OrphanListResponse,
    OrphanUpdate,
    Story,
    StoryCreate,
)

logger = logging.getLogger(__name__)

# Constants for story generation from orphans
MAX_TITLE_LENGTH = 200
MIN_USER_INTENT_LENGTH = 10  # Minimum meaningful length for user_intent


def _truncate_at_word_boundary(text: str, max_length: int) -> str:
    """
    Truncate text at word boundary to avoid cutting words mid-way.

    Args:
        text: Text to truncate
        max_length: Maximum length of result

    Returns:
        Truncated text with ellipsis if truncated, or original if short enough
    """
    if len(text) <= max_length:
        return text

    # Find last space before max_length (leave room for ellipsis)
    truncated = text[:max_length - 3]
    last_space = truncated.rfind(" ")

    if last_space > max_length // 2:
        # Found a reasonable word boundary
        return truncated[:last_space] + "..."
    else:
        # No good boundary found, just truncate
        return truncated + "..."


class OrphanService:
    """
    Manages orphan lifecycle: creation, accumulation, and graduation.

    Responsibilities:
    - CRUD operations on orphans
    - Accumulating conversations into existing orphans
    - Graduating orphans to stories when they reach MIN_GROUP_SIZE
    """

    def __init__(self, db_connection):
        self.db = db_connection

    def create(self, orphan: OrphanCreate) -> Orphan:
        """Create a new orphan."""
        theme_data_json = json.dumps(orphan.theme_data) if orphan.theme_data else "{}"

        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO story_orphans (
                    signature, original_signature, conversation_ids,
                    theme_data, confidence_score
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING id, signature, original_signature, conversation_ids,
                          theme_data, confidence_score, first_seen_at,
                          last_updated_at, graduated_at, story_id
            """, (
                orphan.signature,
                orphan.original_signature,
                orphan.conversation_ids,
                theme_data_json,
                orphan.confidence_score,
            ))
            row = cur.fetchone()
            return self._row_to_orphan(row)

    def create_or_get(self, orphan: OrphanCreate) -> tuple[Orphan, bool]:
        """Create orphan or get existing if signature conflict.

        Uses INSERT ... ON CONFLICT DO NOTHING for idempotent creation.
        This prevents duplicate key violations from crashing transactions.

        Returns:
            (orphan, created): orphan object and whether it was newly created

        Note: Uses single cursor to ensure read consistency after ON CONFLICT.
        """
        theme_data_json = json.dumps(orphan.theme_data) if orphan.theme_data else "{}"

        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO story_orphans (
                    signature, original_signature, conversation_ids,
                    theme_data, confidence_score
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (signature) DO NOTHING
                RETURNING id, signature, original_signature, conversation_ids,
                          theme_data, confidence_score, first_seen_at,
                          last_updated_at, graduated_at, story_id
            """, (
                orphan.signature,
                orphan.original_signature,
                orphan.conversation_ids,
                theme_data_json,
                orphan.confidence_score,
            ))
            row = cur.fetchone()

            if row:
                # Insert succeeded
                return self._row_to_orphan(row), True
            else:
                # Conflict - get existing orphan (same cursor for read consistency)
                cur.execute("""
                    SELECT id, signature, original_signature, conversation_ids,
                           theme_data, confidence_score, first_seen_at,
                           last_updated_at, graduated_at, story_id
                    FROM story_orphans
                    WHERE signature = %s
                """, (orphan.signature,))
                existing_row = cur.fetchone()
                if not existing_row:
                    # Should never happen: conflict but no row found
                    logger.error(
                        f"ON CONFLICT but no orphan found for signature: {orphan.signature}"
                    )
                    raise RuntimeError(
                        f"Orphan conflict without existing row: {orphan.signature}"
                    )
                return self._row_to_orphan(existing_row), False

    def get(self, orphan_id: UUID) -> Optional[Orphan]:
        """Get orphan by ID."""
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, signature, original_signature, conversation_ids,
                       theme_data, confidence_score, first_seen_at,
                       last_updated_at, graduated_at, story_id
                FROM story_orphans
                WHERE id = %s
            """, (str(orphan_id),))
            row = cur.fetchone()
            return self._row_to_orphan(row) if row else None

    def get_by_signature(self, signature: str) -> Optional[Orphan]:
        """Find orphan by canonical signature (active OR graduated).

        Returns any orphan with this signature. Caller should check
        graduated_at/story_id to determine if it's active or graduated.

        Note (Issue #176): This intentionally returns graduated orphans to support
        post-graduation routing. When a conversation matches a graduated orphan's
        signature, it should flow to the story (not create a new orphan).
        Do NOT add `WHERE graduated_at IS NULL` - that would reintroduce cascade failures.
        """
        with self.db.cursor() as cur:
            cur.execute("""
                SELECT id, signature, original_signature, conversation_ids,
                       theme_data, confidence_score, first_seen_at,
                       last_updated_at, graduated_at, story_id
                FROM story_orphans
                WHERE signature = %s
            """, (signature,))
            row = cur.fetchone()
            return self._row_to_orphan(row) if row else None

    def list_active(self, limit: int = 100) -> OrphanListResponse:
        """List all active (non-graduated) orphans."""
        with self.db.cursor() as cur:
            # Get total count of all orphans
            cur.execute("SELECT COUNT(*) as count FROM story_orphans")
            total = cur.fetchone()["count"]

            # Get active count
            cur.execute(
                "SELECT COUNT(*) as count FROM story_orphans WHERE graduated_at IS NULL"
            )
            active_count = cur.fetchone()["count"]

            # Get active orphans
            cur.execute("""
                SELECT id, signature, original_signature, conversation_ids,
                       theme_data, confidence_score, first_seen_at,
                       last_updated_at, graduated_at, story_id
                FROM story_orphans
                WHERE graduated_at IS NULL
                ORDER BY first_seen_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()

            orphans = [self._row_to_orphan(row) for row in rows]

            return OrphanListResponse(
                orphans=orphans,
                total=total,
                active_count=active_count,
            )

    def update(self, orphan_id: UUID, updates: OrphanUpdate) -> Optional[Orphan]:
        """Update orphan fields."""
        update_fields = []
        values = []

        if updates.conversation_ids is not None:
            update_fields.append("conversation_ids = %s")
            values.append(updates.conversation_ids)
        if updates.theme_data is not None:
            update_fields.append("theme_data = %s")
            values.append(json.dumps(updates.theme_data))
        if updates.confidence_score is not None:
            update_fields.append("confidence_score = %s")
            values.append(updates.confidence_score)

        if not update_fields:
            return self.get(orphan_id)

        # Always update last_updated_at
        update_fields.append("last_updated_at = NOW()")
        values.append(str(orphan_id))

        with self.db.cursor() as cur:
            cur.execute(f"""
                UPDATE story_orphans
                SET {', '.join(update_fields)}
                WHERE id = %s
                RETURNING id, signature, original_signature, conversation_ids,
                          theme_data, confidence_score, first_seen_at,
                          last_updated_at, graduated_at, story_id
            """, values)
            row = cur.fetchone()
            return self._row_to_orphan(row) if row else None

    def add_conversations(
        self,
        orphan_id: UUID,
        conversation_ids: List[str],
        theme_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Orphan]:
        """
        Add conversations to an existing orphan.

        Merges new conversation IDs (avoiding duplicates) and optionally
        updates theme data.
        """
        orphan = self.get(orphan_id)
        if not orphan:
            return None

        # Merge conversation IDs (avoiding duplicates)
        existing_ids = set(orphan.conversation_ids)
        new_ids = [cid for cid in conversation_ids if cid not in existing_ids]
        merged_ids = orphan.conversation_ids + new_ids

        # Merge theme data if provided
        merged_theme_data = orphan.theme_data.copy()
        if theme_data:
            merged_theme_data = self._merge_theme_data(merged_theme_data, theme_data)

        return self.update(
            orphan_id,
            OrphanUpdate(
                conversation_ids=merged_ids,
                theme_data=merged_theme_data,
            ),
        )

    def graduate(
        self,
        orphan_id: UUID,
        story_service,
        skip_recency_check: bool = False,
    ) -> Optional[OrphanGraduationResult]:
        """
        Graduate an orphan to a full story.

        Creates a new story from the orphan's data, marks the orphan as graduated,
        and links them together.

        Args:
            orphan_id: The orphan to graduate
            story_service: StoryService instance for creating the story
            skip_recency_check: If True, skip recency validation (used by bulk
                graduation which already did a bulk recency check)

        Returns:
            OrphanGraduationResult if successful, None if orphan not found
            or doesn't meet graduation criteria
        """
        orphan = self.get(orphan_id)
        if not orphan:
            logger.warning(f"Cannot graduate orphan {orphan_id}: not found")
            return None

        if not orphan.can_graduate:
            logger.warning(
                f"Cannot graduate orphan {orphan_id}: only has "
                f"{orphan.conversation_count} conversations (need {MIN_GROUP_SIZE})"
            )
            return None

        if not orphan.is_active:
            logger.warning(f"Cannot graduate orphan {orphan_id}: already graduated")
            return None

        # Issue #200: Recency gate (skip if already checked via bulk path)
        if not skip_recency_check and not self._check_conversation_recency(orphan.conversation_ids):
            logger.warning(f"Cannot graduate orphan {orphan_id}: No recent conversations (last 30 days)")
            return None

        # Extract story data from orphan
        theme_data = orphan.theme_data or {}
        title = self._generate_story_title(orphan)
        description = self._generate_story_description(orphan)

        # Create the story
        story = story_service.create(StoryCreate(
            title=title,
            description=description,
            labels=[],
            priority=None,
            severity=None,
            product_area=theme_data.get("product_area"),
            technical_area=theme_data.get("component"),
            status="candidate",
            confidence_score=orphan.confidence_score,
        ))

        # Mark orphan as graduated
        graduated_at = datetime.utcnow()
        with self.db.cursor() as cur:
            cur.execute("""
                UPDATE story_orphans
                SET graduated_at = %s, story_id = %s, last_updated_at = NOW()
                WHERE id = %s
            """, (graduated_at, str(story.id), str(orphan_id)))

        logger.info(
            f"Graduated orphan {orphan_id} to story {story.id} "
            f"with {orphan.conversation_count} conversations"
        )

        return OrphanGraduationResult(
            orphan_id=orphan_id,
            story_id=story.id,
            signature=orphan.signature,
            conversation_count=orphan.conversation_count,
            graduated_at=graduated_at,
        )

    def delete(self, orphan_id: UUID) -> bool:
        """Delete an orphan."""
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM story_orphans WHERE id = %s", (str(orphan_id),))
            return cur.rowcount > 0

    def check_and_graduate_ready(self, story_service) -> List[OrphanGraduationResult]:
        """
        Find all orphans ready for graduation and graduate them.

        Issue #200: Uses bulk recency check to avoid N+1 queries.

        Returns list of graduation results.
        """
        results = []
        response = self.list_active(limit=1000)  # Get all active orphans

        # Issue #200: Bulk recency check to avoid N+1 queries
        eligible_orphan_ids = [o.id for o in response.orphans if o.can_graduate]
        recency_map = self._get_conversation_recency_bulk(eligible_orphan_ids)

        for orphan in response.orphans:
            if orphan.can_graduate and recency_map.get(orphan.id, False):
                # Pass skip_recency_check=True since we already did bulk recency check above
                result = self.graduate(orphan.id, story_service, skip_recency_check=True)
                if result:
                    results.append(result)

        return results

    def _check_conversation_recency(
        self,
        conversation_ids: List[str],
        days: int = RECENCY_WINDOW_DAYS
    ) -> bool:
        """
        Check if any conversation is within recency window.

        Issue #200: Orphans must have at least one recent conversation to graduate.

        Args:
            conversation_ids: List of conversation IDs to check
            days: Number of days for recency window

        Returns:
            True if at least one conversation is within the recency window
        """
        if not conversation_ids:
            return False

        # Defensive: warn if array is unexpectedly large
        if len(conversation_ids) > 100:
            logger.warning(
                f"Large conversation_ids array ({len(conversation_ids)} items) "
                "passed to _check_conversation_recency"
            )

        # Calculate cutoff in Python (safer than SQL INTERVAL interpolation)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM conversations
                    WHERE id = ANY(%s)
                      AND created_at >= %s
                ) AS has_recent
            """, (conversation_ids, cutoff))
            result = cur.fetchone()
            return result["has_recent"] if result else False

    def _get_conversation_recency_bulk(
        self,
        orphan_ids: List[UUID],
        days: int = RECENCY_WINDOW_DAYS
    ) -> Dict[UUID, bool]:
        """
        Bulk check recency for multiple orphans - avoids N+1 queries.

        Issue #200: Used by check_and_graduate_ready for efficient batch processing.

        Args:
            orphan_ids: List of orphan UUIDs to check
            days: Number of days for recency window

        Returns:
            Dict mapping orphan_id -> has_recent_conversation
        """
        if not orphan_ids:
            return {}

        # Defensive: warn if array is unexpectedly large
        if len(orphan_ids) > 100:
            logger.warning(
                f"Large orphan_ids array ({len(orphan_ids)} items) "
                "passed to _get_conversation_recency_bulk"
            )

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        with self.db.cursor() as cur:
            # Pass UUIDs directly (psycopg2 handles UUID type)
            cur.execute("""
                SELECT o.id AS orphan_id,
                       EXISTS(
                           SELECT 1 FROM conversations c
                           WHERE c.id = ANY(o.conversation_ids)
                             AND c.created_at >= %s
                       ) AS has_recent
                FROM story_orphans o
                WHERE o.id = ANY(%s)
            """, (cutoff, orphan_ids))
            return {row["orphan_id"]: row["has_recent"] for row in cur.fetchall()}

    def _generate_story_title(self, orphan: Orphan) -> str:
        """Generate a story title from orphan data."""
        theme_data = orphan.theme_data or {}

        # Use user_intent if available and has meaningful content
        user_intent = theme_data.get("user_intent")
        if user_intent:
            stripped = user_intent.strip()
            if len(stripped) > MIN_USER_INTENT_LENGTH:
                return _truncate_at_word_boundary(stripped, MAX_TITLE_LENGTH)

        # Fall back to signature-based title (formatted for readability)
        title = orphan.signature.replace("_", " ").title()
        return _truncate_at_word_boundary(f"Theme: {title}", MAX_TITLE_LENGTH)

    def _generate_story_description(self, orphan: Orphan) -> str:
        """Generate a story description from orphan data."""
        theme_data = orphan.theme_data or {}
        parts = []

        if user_intent := theme_data.get("user_intent"):
            parts.append(f"**User Intent**: {user_intent}")

        if symptoms := theme_data.get("symptoms"):
            if isinstance(symptoms, list):
                parts.append(f"**Symptoms**: {', '.join(symptoms)}")

        if product_area := theme_data.get("product_area"):
            parts.append(f"**Product Area**: {product_area}")

        if component := theme_data.get("component"):
            parts.append(f"**Component**: {component}")

        if affected_flow := theme_data.get("affected_flow"):
            parts.append(f"**Affected Flow**: {affected_flow}")

        if root_cause := theme_data.get("root_cause_hypothesis"):
            parts.append(f"**Root Cause Hypothesis**: {root_cause}")

        parts.append(f"\n*Graduated from orphan with {orphan.conversation_count} conversations*")
        parts.append(f"*Signature*: `{orphan.signature}`")

        return "\n\n".join(parts)

    def _merge_theme_data(
        self,
        existing: Dict[str, Any],
        new: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge theme data, combining lists and preferring newer scalars."""
        merged = existing.copy()

        for key, value in new.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, list) and isinstance(merged[key], list):
                # Merge lists, avoiding duplicates for simple values
                existing_set = set(
                    str(v) for v in merged[key] if not isinstance(v, dict)
                )
                for item in value:
                    if isinstance(item, dict):
                        merged[key].append(item)  # Always append dicts
                    elif str(item) not in existing_set:
                        merged[key].append(item)
            elif isinstance(value, dict) and isinstance(merged[key], dict):
                # Recursively merge dicts
                merged[key] = self._merge_theme_data(merged[key], value)
            else:
                # Prefer newer scalar value
                merged[key] = value

        return merged

    def _row_to_orphan(self, row: dict) -> Orphan:
        """Convert database row to Orphan model."""
        theme_data = row["theme_data"] or {}
        if isinstance(theme_data, str):
            theme_data = json.loads(theme_data)

        return Orphan(
            id=row["id"],
            signature=row["signature"],
            original_signature=row["original_signature"],
            conversation_ids=row["conversation_ids"] or [],
            theme_data=theme_data,
            confidence_score=(
                float(row["confidence_score"]) if row["confidence_score"] else None
            ),
            first_seen_at=row["first_seen_at"],
            last_updated_at=row["last_updated_at"],
            graduated_at=row["graduated_at"],
            story_id=row["story_id"],
        )
