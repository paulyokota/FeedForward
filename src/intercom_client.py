"""
Intercom API client with quality filtering.

Fetches conversations and filters to only quality customer messages.
Based on patterns discovered in Phase 1 (see docs/intercom-data-patterns.md).
"""

import os
import re
from datetime import datetime, timedelta
from typing import Generator, Optional

import requests
from pydantic import BaseModel


class IntercomConversation(BaseModel):
    """Parsed Intercom conversation ready for classification."""

    id: str
    created_at: datetime
    source_body: str
    source_type: Optional[str] = None
    source_subject: Optional[str] = None
    contact_email: Optional[str] = None
    contact_id: Optional[str] = None


class QualityFilterResult(BaseModel):
    """Result of quality filtering."""

    passed: bool
    reason: Optional[str] = None


class IntercomClient:
    """Client for fetching and filtering Intercom conversations."""

    BASE_URL = "https://api.intercom.io"
    API_VERSION = "2.11"

    # Template messages to skip
    TEMPLATE_MESSAGES = [
        "i have a product question or feedback",
        "i have a billing question",
        "hi",
        "hello",
    ]

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("INTERCOM_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("INTERCOM_ACCESS_TOKEN not set")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Intercom-Version": self.API_VERSION,
        })

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to Intercom API."""
        url = f"{self.BASE_URL}{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, json: dict) -> dict:
        """Make a POST request to Intercom API."""
        url = f"{self.BASE_URL}{endpoint}"
        response = self.session.post(url, json=json)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def strip_html(html: str) -> str:
        """Remove HTML tags and decode entities."""
        if not html:
            return ""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Decode common entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def quality_filter(self, conv: dict) -> QualityFilterResult:
        """
        Check if a conversation is suitable for classification.

        Based on Phase 1 analysis, ~50% of conversations are filtered out:
        - Admin-initiated messages
        - Bot/automated messages
        - Template clicks
        - Messages too short to classify
        """
        source = conv.get("source", {})

        # Must be customer-initiated
        delivered_as = source.get("delivered_as", "")
        if delivered_as != "customer_initiated":
            return QualityFilterResult(
                passed=False,
                reason=f"not customer_initiated ({delivered_as})"
            )

        # Author must be user (not admin, bot, lead)
        author = source.get("author", {})
        author_type = author.get("type", "")
        if author_type != "user":
            return QualityFilterResult(
                passed=False,
                reason=f"author is {author_type}"
            )

        # Must have body content
        body = self.strip_html(source.get("body", ""))
        if len(body) < 20:
            return QualityFilterResult(
                passed=False,
                reason=f"body too short ({len(body)} chars)"
            )

        # Skip template clicks
        body_lower = body.lower().strip()
        if body_lower in self.TEMPLATE_MESSAGES:
            return QualityFilterResult(
                passed=False,
                reason="template message"
            )

        return QualityFilterResult(passed=True)

    def parse_conversation(self, conv: dict) -> IntercomConversation:
        """Parse raw Intercom conversation to our model."""
        source = conv.get("source", {})
        author = source.get("author", {})

        created_at = datetime.fromtimestamp(conv.get("created_at", 0))

        return IntercomConversation(
            id=str(conv.get("id")),
            created_at=created_at,
            source_body=self.strip_html(source.get("body", "")),
            source_type=source.get("type"),
            source_subject=source.get("subject"),
            contact_email=author.get("email"),
            contact_id=author.get("id"),
        )

    def fetch_conversations(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        per_page: int = 50,
        max_pages: Optional[int] = None,
    ) -> Generator[dict, None, None]:
        """
        Fetch raw conversations from Intercom.

        Yields raw conversation dicts for further processing.
        Handles pagination automatically.
        """
        params = {"per_page": per_page}
        endpoint = "/conversations"
        page_count = 0

        while True:
            data = self._get(endpoint, params)
            conversations = data.get("conversations", [])

            for conv in conversations:
                # Filter by date if specified
                created_at = conv.get("created_at", 0)
                conv_time = datetime.fromtimestamp(created_at)

                if since and conv_time < since:
                    continue
                if until and conv_time > until:
                    continue

                yield conv

            # Check for next page
            pages = data.get("pages", {})
            next_page = pages.get("next")

            if not next_page:
                break

            page_count += 1
            if max_pages and page_count >= max_pages:
                break

            # Use cursor for next page
            starting_after = next_page.get("starting_after")
            if starting_after:
                params["starting_after"] = starting_after
            else:
                break

    def fetch_quality_conversations(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        per_page: int = 50,
        max_pages: Optional[int] = None,
    ) -> Generator[tuple[IntercomConversation, dict], None, None]:
        """
        Fetch and filter conversations, returning only quality ones.

        Yields (parsed_conversation, raw_conversation) tuples.
        """
        for raw_conv in self.fetch_conversations(since, until, per_page, max_pages):
            filter_result = self.quality_filter(raw_conv)
            if filter_result.passed:
                parsed = self.parse_conversation(raw_conv)
                yield parsed, raw_conv

    def get_conversation(self, conv_id: str) -> dict:
        """Fetch a single conversation by ID."""
        return self._get(f"/conversations/{conv_id}")

    def search_conversations(
        self,
        query: str,
        per_page: int = 20,
    ) -> Generator[dict, None, None]:
        """
        Search conversations by body content.

        Useful for finding specific types of conversations.
        """
        search_query = {
            "query": {
                "field": "source.body",
                "operator": "~",
                "value": query,
            },
            "pagination": {"per_page": per_page},
        }

        data = self._post("/conversations/search", search_query)
        for conv in data.get("conversations", []):
            yield conv


# Convenience function
def fetch_recent_conversations(
    days: int = 7,
    max_conversations: Optional[int] = None,
) -> list[IntercomConversation]:
    """
    Fetch quality conversations from the last N days.

    Convenience wrapper for common use case.
    """
    client = IntercomClient()
    since = datetime.utcnow() - timedelta(days=days)

    conversations = []
    for parsed, _ in client.fetch_quality_conversations(since=since):
        conversations.append(parsed)
        if max_conversations and len(conversations) >= max_conversations:
            break

    return conversations
