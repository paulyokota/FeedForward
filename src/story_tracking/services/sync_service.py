"""
Sync Service

Handles bidirectional synchronization between internal stories and Shortcut.
Implements last-write-wins conflict resolution.
Reference: docs/story-tracking-web-app-architecture.md
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

# Sentinel UUID for webhook events with no linked internal story
# Used only in error responses, never persisted
UNKNOWN_STORY_UUID = UUID("00000000-0000-0000-0000-000000000000")

from ..models import (
    ShortcutWebhookEvent,
    StorySnapshot,
    SyncMetadataCreate,
    SyncMetadataUpdate,
    SyncResult,
    SyncStatusResponse,
    SyncMetadata,
    Story,
    StoryUpdate,
)
from .story_service import StoryService

logger = logging.getLogger(__name__)


class SyncService:
    """
    Manages bidirectional sync between internal stories and Shortcut.

    Responsibilities:
    - Track sync metadata for each story
    - Push internal changes to Shortcut
    - Pull Shortcut changes to internal
    - Handle Shortcut webhooks
    - Implement last-write-wins conflict resolution
    """

    def __init__(self, db_connection, shortcut_client, story_service: StoryService):
        """
        Initialize the sync service.

        Args:
            db_connection: Database connection
            shortcut_client: ShortcutClient instance for API calls
            story_service: StoryService for internal story operations
        """
        self.db = db_connection
        self.shortcut_client = shortcut_client
        self.story_service = story_service

    # -------------------------------------------------------------------------
    # Sync Metadata CRUD
    # -------------------------------------------------------------------------

    def get_sync_metadata(self, story_id: UUID) -> Optional[SyncMetadata]:
        """Get sync metadata for a story."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT story_id, shortcut_story_id, last_internal_update_at,
                       last_external_update_at, last_synced_at, last_sync_status,
                       last_sync_error, last_sync_direction
                FROM story_sync_metadata
                WHERE story_id = %s
                """,
                (str(story_id),),
            )
            row = cur.fetchone()
            return self._row_to_sync_metadata(row) if row else None

    def create_sync_metadata(
        self, story_id: UUID, shortcut_story_id: str
    ) -> SyncMetadata:
        """Create sync metadata for a story."""
        now = datetime.now(timezone.utc)
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO story_sync_metadata (
                    story_id, shortcut_story_id, last_synced_at,
                    last_sync_status, last_sync_direction
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING story_id, shortcut_story_id, last_internal_update_at,
                          last_external_update_at, last_synced_at, last_sync_status,
                          last_sync_error, last_sync_direction
                """,
                (str(story_id), shortcut_story_id, now, "created", "push"),
            )
            row = cur.fetchone()
            return self._row_to_sync_metadata(row)

    def update_sync_metadata(
        self, story_id: UUID, updates: SyncMetadataUpdate
    ) -> Optional[SyncMetadata]:
        """Update sync metadata."""
        update_fields = []
        values = []

        if updates.shortcut_story_id is not None:
            update_fields.append("shortcut_story_id = %s")
            values.append(updates.shortcut_story_id)
        if updates.last_internal_update_at is not None:
            update_fields.append("last_internal_update_at = %s")
            values.append(updates.last_internal_update_at)
        if updates.last_external_update_at is not None:
            update_fields.append("last_external_update_at = %s")
            values.append(updates.last_external_update_at)
        if updates.last_synced_at is not None:
            update_fields.append("last_synced_at = %s")
            values.append(updates.last_synced_at)
        if updates.last_sync_status is not None:
            update_fields.append("last_sync_status = %s")
            values.append(updates.last_sync_status)
        if updates.last_sync_error is not None:
            update_fields.append("last_sync_error = %s")
            values.append(updates.last_sync_error)
        if updates.last_sync_direction is not None:
            update_fields.append("last_sync_direction = %s")
            values.append(updates.last_sync_direction)

        if not update_fields:
            return self.get_sync_metadata(story_id)

        values.append(str(story_id))

        with self.db.cursor() as cur:
            # SECURITY NOTE: update_fields contains only hardcoded column names
            # from the conditional blocks above (never user input). Values are
            # properly parameterized with %s placeholders.
            cur.execute(
                f"""
                UPDATE story_sync_metadata
                SET {', '.join(update_fields)}
                WHERE story_id = %s
                RETURNING story_id, shortcut_story_id, last_internal_update_at,
                          last_external_update_at, last_synced_at, last_sync_status,
                          last_sync_error, last_sync_direction
                """,
                values,
            )
            row = cur.fetchone()
            return self._row_to_sync_metadata(row) if row else None

    def get_or_create_sync_metadata(
        self, story_id: UUID, shortcut_story_id: Optional[str] = None
    ) -> SyncMetadata:
        """Get existing sync metadata or create if not exists."""
        metadata = self.get_sync_metadata(story_id)
        if metadata:
            return metadata

        # Create with placeholder if no shortcut_story_id provided
        if shortcut_story_id is None:
            shortcut_story_id = ""

        return self.create_sync_metadata(story_id, shortcut_story_id)

    # -------------------------------------------------------------------------
    # Core Sync Operations
    # -------------------------------------------------------------------------

    def _format_shortcut_description(self, story: Story) -> str:
        """
        Format a story description for Shortcut with metadata.

        Builds a markdown-formatted description including the story content
        and metadata (labels, priority, severity, product area, evidence stats).
        """
        parts = []

        # Main description
        if story.description:
            parts.append(story.description)

        parts.append("")
        parts.append("---")
        parts.append("## Metadata")

        # Labels
        if story.labels:
            labels_str = ", ".join(f"`{label}`" for label in story.labels)
            parts.append(f"**Labels:** {labels_str}")

        # Priority/Severity
        if story.priority:
            parts.append(f"**Priority:** {story.priority}")
        if story.severity:
            parts.append(f"**Severity:** {story.severity}")

        # Product area
        if story.product_area:
            parts.append(f"**Product Area:** {story.product_area}")

        # Evidence stats
        evidence_count = getattr(story, "evidence_count", 0) or 0
        conversation_count = getattr(story, "conversation_count", 0) or 0
        if evidence_count or conversation_count:
            parts.append(
                f"**Evidence:** {evidence_count} records from {conversation_count} conversations"
            )

        confidence = getattr(story, "confidence_score", None)
        if confidence:
            parts.append(f"**Confidence:** {confidence:.0%}")

        parts.append("")
        parts.append("---")
        parts.append("*Generated by FeedForward pipeline*")

        return "\n".join(parts)

    def push_to_shortcut(
        self, story_id: UUID, snapshot: Optional[StorySnapshot] = None
    ) -> SyncResult:
        """
        Push internal story to Shortcut.

        Args:
            story_id: Internal story ID
            snapshot: Optional snapshot of fields to push. If provided, uses these
                      values directly instead of fetching from database. Useful
                      when caller already has the story data.

        Returns:
            SyncResult with operation outcome
        """
        # Get current story to verify it exists
        story = self.story_service.get(story_id)
        if not story:
            return SyncResult(
                success=False,
                direction="push",
                story_id=story_id,
                error="Story not found",
            )

        # Use snapshot title if provided, otherwise use story title
        title = snapshot.title if snapshot else story.title

        # Always format description with metadata from the full story
        description = self._format_shortcut_description(story)

        # Get or create sync metadata
        metadata = self.get_or_create_sync_metadata(story_id)

        try:
            if metadata.shortcut_story_id:
                # Update existing Shortcut story
                success = self.shortcut_client.update_story(
                    story_id=metadata.shortcut_story_id,
                    name=title,
                    description=description,
                )
                if not success:
                    return self._record_sync_error(
                        story_id, "push", "Failed to update Shortcut story"
                    )
            else:
                # Create new Shortcut story
                shortcut_id = self.shortcut_client.create_story(
                    name=title,
                    description=description or "",
                    story_type="bug",
                )
                if not shortcut_id:
                    return self._record_sync_error(
                        story_id, "push", "Failed to create Shortcut story"
                    )

                # Update metadata with new shortcut ID
                self.update_sync_metadata(
                    story_id,
                    SyncMetadataUpdate(shortcut_story_id=shortcut_id),
                )
                metadata = self.get_sync_metadata(story_id)

            # Record successful sync
            now = datetime.now(timezone.utc)
            self.update_sync_metadata(
                story_id,
                SyncMetadataUpdate(
                    last_synced_at=now,
                    last_sync_status="success",
                    last_sync_direction="push",
                    last_sync_error=None,
                    last_internal_update_at=story.updated_at,
                ),
            )

            logger.info(
                f"Pushed story {story_id} to Shortcut {metadata.shortcut_story_id}"
            )

            return SyncResult(
                success=True,
                direction="push",
                story_id=story_id,
                shortcut_story_id=metadata.shortcut_story_id,
                synced_at=now,
            )

        except Exception as e:
            logger.error(f"Error pushing story {story_id}: {e}")
            return self._record_sync_error(story_id, "push", str(e))

    def find_story_by_shortcut_id(self, shortcut_story_id: str) -> Optional[UUID]:
        """
        Find internal story ID by Shortcut story ID.

        Args:
            shortcut_story_id: The Shortcut story ID to look up

        Returns:
            The internal story UUID if found, None otherwise
        """
        return self._find_story_by_shortcut_id(shortcut_story_id)

    def pull_from_shortcut(self, story_id: UUID) -> SyncResult:
        """
        Pull Shortcut story to internal.

        Args:
            story_id: Internal story ID (must have sync metadata with shortcut_story_id)

        Returns:
            SyncResult with operation outcome
        """
        metadata = self.get_sync_metadata(story_id)
        if not metadata or not metadata.shortcut_story_id:
            return SyncResult(
                success=False,
                direction="pull",
                story_id=story_id,
                error="No Shortcut story linked",
            )

        try:
            # Fetch from Shortcut
            shortcut_story = self.shortcut_client.get_story(metadata.shortcut_story_id)
            if not shortcut_story:
                return self._record_sync_error(
                    story_id, "pull", "Shortcut story not found"
                )

            # Update internal story
            self.story_service.update(
                story_id,
                StoryUpdate(
                    title=shortcut_story.name,
                    description=shortcut_story.description,
                ),
            )

            # Record successful sync
            now = datetime.now(timezone.utc)
            self.update_sync_metadata(
                story_id,
                SyncMetadataUpdate(
                    last_synced_at=now,
                    last_sync_status="success",
                    last_sync_direction="pull",
                    last_sync_error=None,
                    last_external_update_at=now,
                ),
            )

            logger.info(
                f"Pulled Shortcut {metadata.shortcut_story_id} to story {story_id}"
            )

            return SyncResult(
                success=True,
                direction="pull",
                story_id=story_id,
                shortcut_story_id=metadata.shortcut_story_id,
                synced_at=now,
            )

        except Exception as e:
            logger.error(f"Error pulling story {story_id}: {e}")
            return self._record_sync_error(story_id, "pull", str(e))

    def sync_story(self, story_id: UUID) -> SyncResult:
        """
        Auto-sync a story using last-write-wins.

        Compares timestamps to determine sync direction.

        Args:
            story_id: Story to sync

        Returns:
            SyncResult with direction chosen and outcome
        """
        metadata = self.get_sync_metadata(story_id)
        story = self.story_service.get(story_id)

        if not story:
            return SyncResult(
                success=False,
                direction="none",
                story_id=story_id,
                error="Story not found",
            )

        # No sync metadata means new story - push to Shortcut
        if not metadata or not metadata.shortcut_story_id:
            return self.push_to_shortcut(story_id)

        # Determine direction based on timestamps (last-write-wins)
        internal_update = metadata.last_internal_update_at or story.updated_at
        external_update = metadata.last_external_update_at

        if external_update is None:
            # No external updates tracked, push internal
            return self.push_to_shortcut(story_id)

        if internal_update > external_update:
            return self.push_to_shortcut(story_id)
        else:
            return self.pull_from_shortcut(story_id)

    # -------------------------------------------------------------------------
    # Webhook Handling
    # -------------------------------------------------------------------------

    def handle_webhook(self, event: ShortcutWebhookEvent) -> SyncResult:
        """
        Handle a Shortcut webhook event.

        Args:
            event: Webhook event from Shortcut

        Returns:
            SyncResult with operation outcome
        """
        # Find story by shortcut_story_id
        story_id = self._find_story_by_shortcut_id(event.shortcut_story_id)

        if not story_id:
            logger.warning(
                f"Webhook for unknown Shortcut story: {event.shortcut_story_id}"
            )
            return SyncResult(
                success=False,
                direction="pull",
                story_id=UNKNOWN_STORY_UUID,
                shortcut_story_id=event.shortcut_story_id,
                error="No linked internal story",
            )

        # Update external timestamp
        self.update_sync_metadata(
            story_id,
            SyncMetadataUpdate(last_external_update_at=event.updated_at),
        )

        # Handle based on event type
        if event.event_type == "story.deleted":
            logger.info(
                f"Shortcut story {event.shortcut_story_id} was deleted"
            )
            # Clear shortcut link but keep internal story
            self.update_sync_metadata(
                story_id,
                SyncMetadataUpdate(
                    shortcut_story_id=None,
                    last_sync_status="unlinked",
                ),
            )
            return SyncResult(
                success=True,
                direction="none",
                story_id=story_id,
                shortcut_story_id=event.shortcut_story_id,
            )

        # For updates, pull the changes
        return self.pull_from_shortcut(story_id)

    # -------------------------------------------------------------------------
    # Batch Operations
    # -------------------------------------------------------------------------

    def sync_all_pending(self) -> List[SyncResult]:
        """
        Sync all stories that need sync.

        Returns:
            List of sync results
        """
        results = []

        # Find stories with sync metadata that need updating
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT s.id
                FROM stories s
                LEFT JOIN story_sync_metadata sm ON s.id = sm.story_id
                WHERE sm.story_id IS NULL
                   OR sm.last_synced_at IS NULL
                   OR s.updated_at > sm.last_synced_at
                LIMIT 100
                """
            )
            rows = cur.fetchall()

        for row in rows:
            story_id = UUID(str(row["id"]))
            result = self.sync_story(story_id)
            results.append(result)

        logger.info(f"Batch sync complete: {len(results)} stories processed")
        return results

    def get_sync_status(self, story_id: UUID) -> SyncStatusResponse:
        """
        Get detailed sync status for a story.

        Returns:
            SyncStatusResponse with current status and hints
        """
        metadata = self.get_sync_metadata(story_id)
        story = self.story_service.get(story_id)

        if not metadata:
            return SyncStatusResponse(
                story_id=story_id,
                needs_sync=True,
                sync_direction_hint="push",
            )

        # Determine if sync is needed
        needs_sync = False
        sync_hint = None

        if story:
            internal_update = story.updated_at
            last_synced = metadata.last_synced_at

            if last_synced is None or internal_update > last_synced:
                needs_sync = True
                sync_hint = "push"
            elif (
                metadata.last_external_update_at
                and metadata.last_external_update_at > last_synced
            ):
                needs_sync = True
                sync_hint = "pull"

        return SyncStatusResponse(
            story_id=story_id,
            shortcut_story_id=metadata.shortcut_story_id,
            last_internal_update_at=metadata.last_internal_update_at,
            last_external_update_at=metadata.last_external_update_at,
            last_synced_at=metadata.last_synced_at,
            last_sync_status=metadata.last_sync_status,
            last_sync_error=metadata.last_sync_error,
            last_sync_direction=metadata.last_sync_direction,
            needs_sync=needs_sync,
            sync_direction_hint=sync_hint,
        )

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _row_to_sync_metadata(self, row: dict) -> SyncMetadata:
        """Convert database row to SyncMetadata model."""
        return SyncMetadata(
            story_id=UUID(str(row["story_id"])),
            shortcut_story_id=row.get("shortcut_story_id"),
            last_internal_update_at=row.get("last_internal_update_at"),
            last_external_update_at=row.get("last_external_update_at"),
            last_synced_at=row.get("last_synced_at"),
            last_sync_status=row.get("last_sync_status"),
            last_sync_error=row.get("last_sync_error"),
            last_sync_direction=row.get("last_sync_direction"),
        )

    def _record_sync_error(
        self, story_id: UUID, direction: str, error: str
    ) -> SyncResult:
        """Record a sync error and return failure result."""
        self.update_sync_metadata(
            story_id,
            SyncMetadataUpdate(
                last_sync_status="error",
                last_sync_error=error,
                last_sync_direction=direction,
            ),
        )
        return SyncResult(
            success=False,
            direction=direction,
            story_id=story_id,
            error=error,
        )

    def _find_story_by_shortcut_id(self, shortcut_story_id: str) -> Optional[UUID]:
        """Find internal story ID by Shortcut story ID."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT story_id FROM story_sync_metadata
                WHERE shortcut_story_id = %s
                """,
                (shortcut_story_id,),
            )
            row = cur.fetchone()
            return UUID(str(row["story_id"])) if row else None
