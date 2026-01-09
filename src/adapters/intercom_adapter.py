"""
Intercom Source Adapter
Normalizes Intercom conversations into common conversation format.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from . import SourceAdapter, NormalizedConversation

logger = logging.getLogger(__name__)


class IntercomAdapter(SourceAdapter):
    """Adapter for Intercom support conversations."""

    def __init__(self, intercom_client=None):
        """
        Initialize adapter.

        Args:
            intercom_client: Optional Intercom client instance.
                             If not provided, uses existing fetch logic.
        """
        self._client = intercom_client

    @property
    def source_name(self) -> str:
        return "intercom"

    def fetch(
        self,
        days: int = 7,
        max_items: Optional[int] = None,
        **kwargs,
    ) -> List[Dict]:
        """
        Fetch conversations from Intercom.

        Uses existing Intercom fetching logic from the pipeline.

        Args:
            days: Number of days to look back
            max_items: Maximum conversations to fetch

        Returns:
            List of raw Intercom conversation dicts
        """
        # Import here to avoid circular dependency
        from ..intercom_client import fetch_conversations

        conversations = fetch_conversations(days=days, max_conversations=max_items)
        logger.info(f"Fetched {len(conversations)} conversations from Intercom")
        return conversations

    def normalize(self, raw_data: Dict) -> NormalizedConversation:
        """
        Normalize Intercom conversation to common format.

        Preserves existing conversation structure while adding
        explicit data_source field.
        """
        # Extract conversation ID
        conv_id = raw_data.get("id", "unknown")

        # Build text from conversation parts
        text = self._extract_conversation_text(raw_data)

        # Get URL from source
        source = raw_data.get("source", {})
        url = source.get("url") if isinstance(source, dict) else None

        # Parse timestamp
        created_at = self._parse_timestamp(raw_data.get("created_at"))

        # Build source metadata
        source_metadata = {
            "type": "conversation",
            "state": raw_data.get("state"),
            "open": raw_data.get("open"),
            "source_type": source.get("type") if isinstance(source, dict) else None,
            "source_url": url,
            "tags": [t.get("name") for t in raw_data.get("tags", {}).get("tags", [])],
        }

        # Include contact info if available
        contacts = raw_data.get("contacts", {}).get("contacts", [])
        if contacts:
            contact = contacts[0]
            source_metadata["contact_email"] = contact.get("email")
            source_metadata["contact_name"] = contact.get("name")

        return NormalizedConversation(
            id=f"intercom_{conv_id}",
            text=text,
            data_source="intercom",
            source_metadata=source_metadata,
            created_at=created_at,
            url=url,
        )

    def _extract_conversation_text(self, conversation: Dict) -> str:
        """Extract text content from conversation parts."""
        parts = []

        # Get initial message from source
        source = conversation.get("source", {})
        if isinstance(source, dict):
            body = source.get("body", "")
            if body:
                # Strip HTML tags
                import re
                clean_body = re.sub(r'<[^>]+>', ' ', body)
                clean_body = re.sub(r'\s+', ' ', clean_body).strip()
                if clean_body:
                    parts.append(clean_body)

        # Get conversation parts
        conv_parts = conversation.get("conversation_parts", {})
        if isinstance(conv_parts, dict):
            for part in conv_parts.get("conversation_parts", []):
                body = part.get("body", "")
                if body:
                    import re
                    clean_body = re.sub(r'<[^>]+>', ' ', body)
                    clean_body = re.sub(r'\s+', ' ', clean_body).strip()
                    if clean_body:
                        author_type = part.get("author", {}).get("type", "unknown")
                        parts.append(f"[{author_type}] {clean_body}")

        return "\n\n".join(parts)

    def _parse_timestamp(self, timestamp) -> datetime:
        """Parse timestamp (int or string) to datetime."""
        if not timestamp:
            return datetime.now()

        try:
            if isinstance(timestamp, int):
                return datetime.fromtimestamp(timestamp)
            elif isinstance(timestamp, str):
                if "T" in timestamp:
                    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return datetime.strptime(timestamp[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

        return datetime.now()
