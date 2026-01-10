"""
Label Registry Service

Manages the label registry for Shortcut taxonomy and internal labels.
Reference: docs/story-tracking-web-app-architecture.md
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from ..models import (
    ImportResult,
    LabelCreate,
    LabelListResponse,
    LabelRegistryEntry,
    LabelUpdate,
)

logger = logging.getLogger(__name__)


class LabelRegistryService:
    """
    Manages the label registry.

    Responsibilities:
    - CRUD operations for labels
    - Import labels from Shortcut
    - Track label usage
    - Ensure internal labels exist in Shortcut when syncing
    """

    def __init__(self, db_connection, shortcut_client=None):
        """
        Initialize the label registry service.

        Args:
            db_connection: Database connection
            shortcut_client: Optional ShortcutClient for importing labels
        """
        self.db = db_connection
        self.shortcut_client = shortcut_client

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def list_labels(
        self, source: Optional[str] = None, limit: int = 100
    ) -> LabelListResponse:
        """
        List all labels in the registry.

        Args:
            source: Filter by source ("shortcut" or "internal")
            limit: Maximum number of labels to return

        Returns:
            LabelListResponse with labels and counts
        """
        with self.db.cursor() as cur:
            # Build query based on source filter
            if source:
                cur.execute(
                    """
                    SELECT label_name, source, category, created_at, last_seen_at
                    FROM label_registry
                    WHERE source = %s
                    ORDER BY label_name
                    LIMIT %s
                    """,
                    (source, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT label_name, source, category, created_at, last_seen_at
                    FROM label_registry
                    ORDER BY label_name
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = cur.fetchall()
            labels = [self._row_to_label(row) for row in rows]

            # Get counts
            cur.execute("SELECT COUNT(*) as count FROM label_registry")
            total = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) as count FROM label_registry WHERE source = 'shortcut'"
            )
            shortcut_count = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) as count FROM label_registry WHERE source = 'internal'"
            )
            internal_count = cur.fetchone()["count"]

        return LabelListResponse(
            labels=labels,
            total=total,
            shortcut_count=shortcut_count,
            internal_count=internal_count,
        )

    def get_label(self, label_name: str) -> Optional[LabelRegistryEntry]:
        """Get a label by name."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT label_name, source, category, created_at, last_seen_at
                FROM label_registry
                WHERE label_name = %s
                """,
                (label_name,),
            )
            row = cur.fetchone()
            return self._row_to_label(row) if row else None

    def create_label(self, label: LabelCreate) -> LabelRegistryEntry:
        """
        Create a new label in the registry.

        Args:
            label: Label to create

        Returns:
            Created label entry
        """
        now = datetime.now(timezone.utc)
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO label_registry (label_name, source, category, created_at, last_seen_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (label_name) DO UPDATE
                SET last_seen_at = EXCLUDED.last_seen_at
                RETURNING label_name, source, category, created_at, last_seen_at
                """,
                (label.label_name, label.source, label.category, now, now),
            )
            row = cur.fetchone()
            return self._row_to_label(row)

    def update_label(
        self, label_name: str, updates: LabelUpdate
    ) -> Optional[LabelRegistryEntry]:
        """Update a label."""
        update_fields = []
        values = []

        if updates.category is not None:
            update_fields.append("category = %s")
            values.append(updates.category)
        if updates.last_seen_at is not None:
            update_fields.append("last_seen_at = %s")
            values.append(updates.last_seen_at)

        if not update_fields:
            return self.get_label(label_name)

        values.append(label_name)

        with self.db.cursor() as cur:
            # SECURITY NOTE: update_fields contains only hardcoded column names
            # from the conditional blocks above (never user input). Values are
            # properly parameterized with %s placeholders.
            cur.execute(
                f"""
                UPDATE label_registry
                SET {', '.join(update_fields)}
                WHERE label_name = %s
                RETURNING label_name, source, category, created_at, last_seen_at
                """,
                values,
            )
            row = cur.fetchone()
            return self._row_to_label(row) if row else None

    def update_last_seen(self, label_name: str) -> Optional[LabelRegistryEntry]:
        """Update last_seen_at for a label."""
        return self.update_label(label_name, LabelUpdate(last_seen_at=datetime.now(timezone.utc)))

    def delete_label(self, label_name: str) -> bool:
        """Delete a label from the registry."""
        with self.db.cursor() as cur:
            cur.execute(
                "DELETE FROM label_registry WHERE label_name = %s",
                (label_name,),
            )
            return cur.rowcount > 0

    # -------------------------------------------------------------------------
    # Shortcut Integration
    # -------------------------------------------------------------------------

    def import_from_shortcut(self) -> ImportResult:
        """
        Import labels from Shortcut.

        Fetches all labels from Shortcut API and adds them to the registry.

        Returns:
            ImportResult with counts
        """
        result = ImportResult()

        if not self.shortcut_client:
            result.errors.append("No Shortcut client configured")
            return result

        try:
            # Fetch labels from Shortcut API
            labels_data = self._fetch_shortcut_labels()

            for label_data in labels_data:
                label_name = label_data.get("name", "")
                if not label_name:
                    continue

                existing = self.get_label(label_name)
                if existing:
                    # Update last_seen
                    self.update_last_seen(label_name)
                    result.updated_count += 1
                else:
                    # Create new
                    self.create_label(
                        LabelCreate(
                            label_name=label_name,
                            source="shortcut",
                            category=label_data.get("category"),
                        )
                    )
                    result.imported_count += 1

            logger.info(
                f"Imported labels from Shortcut: {result.imported_count} new, "
                f"{result.updated_count} updated"
            )

        except Exception as e:
            error_msg = f"Error importing labels: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

        return result

    def ensure_label_in_shortcut(self, label_name: str) -> bool:
        """
        Ensure a label exists in Shortcut.

        If the label is internal-only, creates it in Shortcut.

        Args:
            label_name: Label to ensure

        Returns:
            True if label exists or was created successfully
        """
        if not self.shortcut_client:
            logger.warning("No Shortcut client - cannot ensure label in Shortcut")
            return False

        label = self.get_label(label_name)

        # If already from Shortcut, it exists
        if label and label.source == "shortcut":
            return True

        # Try to create in Shortcut
        try:
            success = self._create_label_in_shortcut(label_name)
            if success:
                # Update registry to reflect it now exists in Shortcut
                if label:
                    # Can't change source, but update last_seen
                    self.update_last_seen(label_name)
                else:
                    self.create_label(
                        LabelCreate(label_name=label_name, source="shortcut")
                    )
                return True
        except Exception as e:
            logger.error(f"Error creating label in Shortcut: {e}")

        return False

    def get_labels_for_story(self, labels: List[str]) -> List[LabelRegistryEntry]:
        """
        Get registry entries for a list of label names.

        Also updates last_seen_at for each label found.

        Args:
            labels: List of label names

        Returns:
            List of matching label entries
        """
        if not labels:
            return []

        with self.db.cursor() as cur:
            # Batch query to fetch all labels at once (fixes N+1 query issue)
            placeholders = ",".join(["%s"] * len(labels))
            cur.execute(
                f"""
                SELECT label_name, source, category, created_at, last_seen_at
                FROM label_registry
                WHERE label_name IN ({placeholders})
                """,
                labels,
            )
            rows = cur.fetchall()

            if rows:
                # Batch update last_seen_at for all found labels
                now = datetime.now(timezone.utc)
                cur.execute(
                    f"""
                    UPDATE label_registry
                    SET last_seen_at = %s
                    WHERE label_name IN ({placeholders})
                    """,
                    [now] + labels,
                )

            return [self._row_to_label(row) for row in rows]

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _row_to_label(self, row: dict) -> LabelRegistryEntry:
        """Convert database row to LabelRegistryEntry model."""
        return LabelRegistryEntry(
            label_name=row["label_name"],
            source=row["source"],
            category=row.get("category"),
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
        )

    def _fetch_shortcut_labels(self) -> List[dict]:
        """Fetch all labels from Shortcut API."""
        if not self.shortcut_client:
            return []

        # Use the shortcut client's _get method to fetch labels
        result = self.shortcut_client._get("/labels")
        return result if result else []

    def _create_label_in_shortcut(self, label_name: str) -> bool:
        """Create a label in Shortcut."""
        if not self.shortcut_client:
            return False

        result = self.shortcut_client._post("/labels", {"name": label_name})
        return result is not None
