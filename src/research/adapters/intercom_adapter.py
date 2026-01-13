"""
Intercom Search Source Adapter

Extracts searchable content from Intercom conversations stored in PostgreSQL.
"""

import logging
import re
from typing import Iterator, Optional

from .base import SearchSourceAdapter
from ..models import SearchableContent

logger = logging.getLogger(__name__)


class IntercomSearchAdapter(SearchSourceAdapter):
    """
    Adapter for Intercom conversation data.

    Extracts customer conversations from the PostgreSQL conversations table.
    Only includes conversations with substantial content.
    """

    def __init__(self, min_content_length: int = 100):
        """
        Initialize the Intercom adapter.

        Args:
            min_content_length: Minimum content length to include
        """
        self._min_content_length = min_content_length

    def get_source_type(self) -> str:
        """Returns 'intercom'."""
        return "intercom"

    def extract_content(self, source_id: str) -> Optional[SearchableContent]:
        """Extract content for a specific conversation."""
        try:
            from src.db.connection import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, source_body, source_type, source_subject,
                               contact_email, created_at, stage1_type, stage2_type,
                               sentiment, churn_risk
                        FROM conversations
                        WHERE id = %s
                    """, (source_id,))
                    row = cur.fetchone()

                    if not row:
                        return None

                    return self._row_to_content(row)
        except Exception as e:
            logger.error(f"Failed to extract Intercom conversation {source_id}: {e}")
            return None

    def extract_all(self, limit: Optional[int] = None) -> Iterator[SearchableContent]:
        """Extract all conversations from Intercom."""
        try:
            from src.db.connection import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    query = f"""
                        SELECT id, source_body, source_type, source_subject,
                               contact_email, created_at, stage1_type, stage2_type,
                               sentiment, churn_risk
                        FROM conversations
                        WHERE source_body IS NOT NULL
                          AND LENGTH(source_body) > {self._min_content_length}
                        ORDER BY created_at DESC
                    """
                    if limit:
                        query += f" LIMIT {limit}"

                    cur.execute(query)
                    for row in cur.fetchall():
                        content = self._row_to_content(row)
                        if content:
                            yield content
        except Exception as e:
            logger.error(f"Failed to extract Intercom conversations: {e}")
            return

    def get_source_url(self, source_id: str) -> str:
        """Get Intercom URL for a conversation."""
        # Standard Intercom conversation URL format
        return f"https://app.intercom.com/a/inbox/_/inbox/conversation/{source_id}"

    def _row_to_content(self, row: tuple) -> Optional[SearchableContent]:
        """Convert database row to SearchableContent."""
        (conv_id, source_body, source_type, source_subject,
         contact_email, created_at, stage1_type, stage2_type,
         sentiment, churn_risk) = row

        if not source_body or len(source_body.strip()) < self._min_content_length:
            return None

        # Clean HTML from content
        clean_body = self._clean_html(source_body)

        # Build title from subject or first line
        title = source_subject or self._extract_title(clean_body)

        # Build searchable content
        content_parts = []
        if source_subject:
            content_parts.append(f"Subject: {source_subject}")
        content_parts.append(clean_body)

        return SearchableContent(
            source_type="intercom",
            source_id=conv_id,
            title=title,
            content="\n".join(content_parts),
            url=self.get_source_url(conv_id),
            metadata={
                "conversation_type": stage2_type or stage1_type,
                "sentiment": sentiment,
                "churn_risk": churn_risk,
                "contact_email": contact_email,
                "source_type": source_type,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )

    @staticmethod
    def _clean_html(text: str) -> str:
        """Remove HTML tags and normalize whitespace."""
        if not text:
            return ""

        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', ' ', text)
        # Normalize whitespace
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    @staticmethod
    def _extract_title(content: str, max_length: int = 60) -> str:
        """Extract a title from the first sentence of content."""
        if not content:
            return "Untitled Conversation"

        # Get first line or sentence
        first_line = content.split('\n')[0]
        first_sentence = first_line.split('.')[0]

        title = first_sentence[:max_length]
        if len(first_sentence) > max_length:
            # Find a good break point
            last_space = title.rfind(' ')
            if last_space > max_length * 0.5:
                title = title[:last_space] + '...'
            else:
                title = title + '...'

        return title or "Untitled Conversation"
