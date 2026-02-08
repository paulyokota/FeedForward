"""Data access for explorer agents.

Reads raw conversation text from the database. Deliberately does NOT
return classification, theme, or other pipeline output — the explorer
must reason from scratch on the raw text.

MF3: Uses COALESCE(NULLIF(..., ''), source_body) so both NULL and empty
string in full_conversation trigger fallback to source_body.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class RawConversation:
    """A conversation as the explorer sees it — raw text only.

    No classification output, no theme data, no pipeline judgments.
    Just what the customer said and where they were.
    """

    conversation_id: str
    created_at: datetime
    source_body: str
    full_conversation: Optional[str]
    source_url: Optional[str]
    used_fallback: bool  # True if full_conversation was null/empty, fell back to source_body


class ConversationReader:
    """Reads raw conversations from Postgres for explorer agents.

    The SQL deliberately excludes all pipeline output (stage1_type,
    sentiment, themes, etc.). The explorer sees only raw text and
    source_url (which is raw input context, not pipeline output).
    """

    def __init__(self, db_connection):
        self.db = db_connection

    def fetch_conversations(
        self,
        days: int = 14,
        limit: Optional[int] = None,
    ) -> List[RawConversation]:
        """Fetch raw conversations from the last N days.

        Returns conversations ordered by created_at DESC.
        Falls back to source_body when full_conversation is null/empty.
        Skips conversations where both fields are null/empty.

        Args:
            days: How many days back to look.
            limit: Max conversations to return. None = no limit.

        Returns:
            List of RawConversation with raw text only.
        """
        query = """
            SELECT
                id AS conversation_id,
                created_at,
                source_body,
                support_insights->>'full_conversation' AS full_conversation,
                source_url,
                CASE
                    WHEN COALESCE(NULLIF(support_insights->>'full_conversation', ''), '') = ''
                    THEN true
                    ELSE false
                END AS used_fallback
            FROM conversations
            WHERE created_at >= NOW() - INTERVAL '%s days'
              AND COALESCE(
                    NULLIF(support_insights->>'full_conversation', ''),
                    NULLIF(source_body, '')
                  ) IS NOT NULL
            ORDER BY created_at DESC
        """

        params: list = [days]

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

        conversations = []
        fallback_count = 0
        for row in rows:
            used_fallback = row["used_fallback"]
            if used_fallback:
                fallback_count += 1

            conversations.append(
                RawConversation(
                    conversation_id=row["conversation_id"],
                    created_at=row["created_at"],
                    source_body=row["source_body"] or "",
                    full_conversation=row["full_conversation"],
                    source_url=row["source_url"],
                    used_fallback=used_fallback,
                )
            )

        if fallback_count > 0:
            logger.warning(
                "%d of %d conversations used source_body fallback "
                "(full_conversation was null/empty)",
                fallback_count,
                len(conversations),
            )

        return conversations

    def fetch_conversation_by_id(
        self, conversation_id: str
    ) -> Optional[RawConversation]:
        """Fetch a single conversation by ID (for re-query support)."""
        query = """
            SELECT
                id AS conversation_id,
                created_at,
                source_body,
                support_insights->>'full_conversation' AS full_conversation,
                source_url,
                CASE
                    WHEN COALESCE(NULLIF(support_insights->>'full_conversation', ''), '') = ''
                    THEN true
                    ELSE false
                END AS used_fallback
            FROM conversations
            WHERE id = %s
              AND COALESCE(
                    NULLIF(support_insights->>'full_conversation', ''),
                    NULLIF(source_body, '')
                  ) IS NOT NULL
        """
        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (conversation_id,))
            row = cur.fetchone()

        if not row:
            return None

        return RawConversation(
            conversation_id=row["conversation_id"],
            created_at=row["created_at"],
            source_body=row["source_body"] or "",
            full_conversation=row["full_conversation"],
            source_url=row["source_url"],
            used_fallback=row["used_fallback"],
        )

    def get_conversation_count(self, days: int = 14) -> int:
        """Get count of available conversations for coverage reporting.

        Counts all conversations in the time window, including those
        with null/empty text (so coverage metadata can report skipped).
        """
        query = """
            SELECT COUNT(*) AS cnt
            FROM conversations
            WHERE created_at >= NOW() - INTERVAL '%s days'
        """
        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (days,))
            row = cur.fetchone()
            return row["cnt"] if row else 0
