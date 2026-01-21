"""
Intercom API client with quality filtering.

Fetches conversations and filters to only quality customer messages.
Based on patterns discovered in Phase 1 (see docs/intercom-data-patterns.md).

Supports both sync and async modes:
- Sync: Uses requests.Session (for CLI, simple scripts)
- Async: Uses aiohttp (for pipeline, FastAPI integration)
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator, Optional

import aiohttp
import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class IntercomConversation(BaseModel):
    """Parsed Intercom conversation ready for classification."""

    id: str
    created_at: datetime
    source_body: str
    source_type: Optional[str] = None
    source_subject: Optional[str] = None
    source_url: Optional[str] = None      # URL of the page user was on when starting conversation
    contact_email: Optional[str] = None
    contact_id: Optional[str] = None      # Intercom contact ID
    user_id: Optional[str] = None         # Tailwind user ID (from external_id)
    org_id: Optional[str] = None          # Tailwind org ID (from custom_attributes.account_id)


class QualityFilterResult(BaseModel):
    """Result of quality filtering."""

    passed: bool
    reason: Optional[str] = None


class IntercomClient:
    """Client for fetching and filtering Intercom conversations."""

    BASE_URL = "https://api.intercom.io"
    API_VERSION = "2.11"

    # HTTP timeout: (connect_timeout, read_timeout) in seconds
    # - connect: time to establish connection (10s is generous)
    # - read: time to receive response (30s allows for slow API responses)
    DEFAULT_TIMEOUT = (10, 30)

    # Retry configuration for transient errors (5xx)
    # 3 retries with 2s base delay = max 14s total wait (2+4+8), reasonable for API ops
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # seconds, exponential backoff: 2s, 4s, 8s
    RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

    # Template messages to skip
    TEMPLATE_MESSAGES = [
        "i have a product question or feedback",
        "i have a billing question",
        "hi",
        "hello",
    ]


    def __init__(self, access_token: Optional[str] = None, timeout: tuple = None, max_retries: int = None):
        self.access_token = access_token or os.getenv("INTERCOM_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("INTERCOM_ACCESS_TOKEN not set")

        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else self.MAX_RETRIES

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Intercom-Version": self.API_VERSION,
        })

    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        """
        Make an HTTP request with retry on transient errors.

        Retries on:
        - 5xx server errors (500, 502, 503, 504)
        - Connection errors (network issues, timeouts)

        Does NOT retry on:
        - 4xx client errors (these indicate a problem with the request)
        """
        url = f"{self.BASE_URL}{endpoint}"
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                if method == "GET":
                    response = self.session.get(url, params=params, timeout=self.timeout)
                else:
                    response = self.session.post(url, json=json, timeout=self.timeout)

                # Check if we should retry on 5xx
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    if attempt < self.max_retries:
                        delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                        logger.warning(
                            f"Intercom API error {response.status_code} on {endpoint}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Last attempt failed, raise the error
                        response.raise_for_status()

                # For non-5xx errors (including 4xx), raise immediately without retry
                response.raise_for_status()
                return response.json()

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                # Retry on connection-level errors
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"Intercom API connection error: {e}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    time.sleep(delay)
                else:
                    raise

        # All paths above either return or raise; this is unreachable but
        # satisfies type checker that function returns a dict
        raise RuntimeError("Unexpected retry loop exit")

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to Intercom API with retry."""
        return self._request_with_retry("GET", endpoint, params=params)

    def _post(self, endpoint: str, json: dict) -> dict:
        """Make a POST request to Intercom API with retry."""
        return self._request_with_retry("POST", endpoint, json=json)

    # ==================== ASYNC METHODS ====================
    # These methods use aiohttp for true async operation.
    # Use these in async contexts (FastAPI, pipeline) to avoid
    # thread + event loop conflicts.

    async def _request_with_retry_async(
        self,
        session: aiohttp.ClientSession,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """
        Make an async HTTP request with retry on transient errors.

        Same retry logic as sync version but using aiohttp.
        """
        import time as time_module
        url = f"{self.BASE_URL}{endpoint}"

        print(f"[ASYNC] Starting {method} request to {endpoint}, params={params}", flush=True)
        request_start = time_module.time()

        for attempt in range(self.max_retries + 1):
            try:
                print(f"[ASYNC] Attempt {attempt + 1}/{self.max_retries + 1} for {endpoint}", flush=True)
                if method == "GET":
                    print(f"[ASYNC] About to call session.get({url})", flush=True)
                    async with session.get(url, params=params) as response:
                        print(f"[ASYNC] Got response status {response.status} for {endpoint}", flush=True)
                        if response.status in self.RETRYABLE_STATUS_CODES:
                            if attempt < self.max_retries:
                                delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                                logger.warning(
                                    f"Intercom API error {response.status} on {endpoint}, "
                                    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                                )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                response.raise_for_status()
                        response.raise_for_status()
                        print(f"[ASYNC] About to read response body for {endpoint}", flush=True)
                        result = await response.json()
                        elapsed = time_module.time() - request_start
                        print(f"[ASYNC] Completed {method} {endpoint} in {elapsed:.2f}s", flush=True)
                        return result
                else:
                    async with session.post(url, json=json_data) as response:
                        if response.status in self.RETRYABLE_STATUS_CODES:
                            if attempt < self.max_retries:
                                delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                                logger.warning(
                                    f"Intercom API error {response.status} on {endpoint}, "
                                    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                                )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                response.raise_for_status()
                        response.raise_for_status()
                        return await response.json()

            except aiohttp.ClientError as e:
                if attempt < self.max_retries:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"Intercom API connection error: {e}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise RuntimeError("Unexpected retry loop exit")

    def _get_aiohttp_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session with proper headers and timeout."""
        timeout = aiohttp.ClientTimeout(
            connect=self.timeout[0],
            total=self.timeout[0] + self.timeout[1]
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Intercom-Version": self.API_VERSION,
        }
        return aiohttp.ClientSession(timeout=timeout, headers=headers)

    async def fetch_conversations_async(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        per_page: int = 50,
        max_pages: Optional[int] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Fetch raw conversations from Intercom (async version).

        Yields raw conversation dicts for further processing.
        Handles pagination automatically.
        """
        params = {"per_page": per_page}
        endpoint = "/conversations"
        page_count = 0

        print(f"[ASYNC FETCH] Starting fetch_conversations_async, since={since}, max_pages={max_pages}", flush=True)
        print(f"[ASYNC FETCH] Creating aiohttp session...", flush=True)

        async with self._get_aiohttp_session() as session:
            print(f"[ASYNC FETCH] Session created, starting pagination loop", flush=True)
            while True:
                print(f"[ASYNC FETCH] Fetching page {page_count + 1}, params={params}", flush=True)
                data = await self._request_with_retry_async(session, "GET", endpoint, params=params)
                conversations = data.get("conversations", [])
                print(f"[ASYNC FETCH] Page {page_count + 1} returned {len(conversations)} conversations", flush=True)

                for conv in conversations:
                    created_at = conv.get("created_at", 0)
                    conv_time = datetime.fromtimestamp(created_at)

                    # Skip conversations outside date range
                    # NOTE: Intercom sorts by updated_at, NOT created_at
                    if since and conv_time < since:
                        continue
                    if until and conv_time > until:
                        continue

                    yield conv

                # Check for next page
                pages = data.get("pages", {})
                next_page = pages.get("next")
                print(f"[ASYNC FETCH] Page {page_count + 1} pagination: next_page={next_page is not None}", flush=True)

                if not next_page:
                    print(f"[ASYNC FETCH] No next page, ending pagination", flush=True)
                    break

                page_count += 1
                if max_pages and page_count >= max_pages:
                    print(f"[ASYNC FETCH] Reached max_pages={max_pages}, ending pagination", flush=True)
                    break

                starting_after = next_page.get("starting_after")
                if starting_after:
                    print(f"[ASYNC FETCH] Moving to page {page_count + 1}, starting_after={starting_after[:20]}...", flush=True)
                    params["starting_after"] = starting_after
                else:
                    print(f"[ASYNC FETCH] No starting_after cursor, ending pagination", flush=True)
                    break

        print(f"[ASYNC FETCH] Exiting fetch_conversations_async, total pages={page_count + 1}", flush=True)

    async def fetch_quality_conversations_async(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        per_page: int = 50,
        max_results: Optional[int] = None,
    ) -> AsyncGenerator[tuple["IntercomConversation", dict], None]:
        """
        Fetch and filter conversations, returning only quality ones (async version).

        Uses the Search API for server-side date filtering, which is MUCH more
        efficient than the List API (avoids fetching all 338k+ conversations).

        Yields (parsed_conversation, raw_conversation) tuples.
        """
        print(f"[ASYNC QUALITY] Starting fetch_quality_conversations_async", flush=True)
        print(f"[ASYNC QUALITY] Using Search API for server-side date filtering", flush=True)

        # Convert datetime to unix timestamps for Search API
        start_ts = int(since.timestamp()) if since else 0
        end_ts = int(until.timestamp()) if until else int(datetime.utcnow().timestamp())

        print(f"[ASYNC QUALITY] Date range: {since} ({start_ts}) to {until} ({end_ts})", flush=True)

        yielded_count = 0
        filtered_count = 0

        async for raw_conv in self.search_by_date_range_async(start_ts, end_ts, per_page, max_results):
            filter_result = self.quality_filter(raw_conv)
            if filter_result.passed:
                parsed = self.parse_conversation(raw_conv)
                yielded_count += 1
                if yielded_count % 10 == 0:
                    print(f"[ASYNC QUALITY] Yielded {yielded_count} quality conversations so far", flush=True)
                yield parsed, raw_conv
            else:
                filtered_count += 1

        print(f"[ASYNC QUALITY] Completed: {yielded_count} yielded, {filtered_count} filtered", flush=True)

    async def get_conversation_async(self, session: aiohttp.ClientSession, conv_id: str) -> dict:
        """Fetch a single conversation by ID (async version).

        Note: Requires an existing session to be passed in for efficiency
        when fetching multiple conversations.
        """
        return await self._request_with_retry_async(session, "GET", f"/conversations/{conv_id}")

    async def search_by_date_range_async(
        self,
        start_timestamp: int,
        end_timestamp: int,
        per_page: int = 50,
        max_results: Optional[int] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Search conversations within a date range using Intercom Search API (async).

        Uses server-side filtering via POST /conversations/search, which is MUCH
        more efficient than the LIST API for date-bounded queries.

        Args:
            start_timestamp: Unix timestamp for start of range
            end_timestamp: Unix timestamp for end of range
            per_page: Results per page
            max_results: Maximum conversations to return

        Yields raw conversation dicts.
        """
        search_query = {
            "query": {
                "operator": "AND",
                "value": [
                    {
                        "field": "created_at",
                        "operator": ">",
                        "value": start_timestamp,
                    },
                    {
                        "field": "created_at",
                        "operator": "<",
                        "value": end_timestamp,
                    },
                ],
            },
            "pagination": {"per_page": per_page},
        }

        count = 0
        page_count = 0
        starting_after = None

        print(f"[SEARCH API] Starting search_by_date_range_async", flush=True)
        print(f"[SEARCH API] Date range: {start_timestamp} to {end_timestamp}", flush=True)

        async with self._get_aiohttp_session() as session:
            while True:
                if starting_after:
                    search_query["pagination"]["starting_after"] = starting_after

                print(f"[SEARCH API] Fetching page {page_count + 1}", flush=True)
                data = await self._request_with_retry_async(
                    session, "POST", "/conversations/search", json_data=search_query
                )
                conversations = data.get("conversations", [])
                print(f"[SEARCH API] Page {page_count + 1} returned {len(conversations)} conversations", flush=True)

                if not conversations:
                    print(f"[SEARCH API] No conversations returned, ending search", flush=True)
                    break

                for conv in conversations:
                    yield conv
                    count += 1
                    if max_results and count >= max_results:
                        print(f"[SEARCH API] Reached max_results={max_results}", flush=True)
                        return

                # Check for next page
                pages = data.get("pages", {})
                next_page = pages.get("next", {})
                starting_after = next_page.get("starting_after")
                page_count += 1

                if not starting_after:
                    print(f"[SEARCH API] No more pages, search complete", flush=True)
                    break

        print(f"[SEARCH API] Total: {count} conversations from {page_count} pages", flush=True)

    # ==================== END ASYNC METHODS ====================

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

        # Extract user_id from contacts[].external_id (Tailwind user ID)
        user_id = None
        contacts_data = conv.get("contacts", {})
        contacts_list = contacts_data.get("contacts", []) if isinstance(contacts_data, dict) else []
        if contacts_list:
            user_id = contacts_list[0].get("external_id")

        return IntercomConversation(
            id=str(conv.get("id")),
            created_at=created_at,
            source_body=self.strip_html(source.get("body", "")),
            source_type=source.get("type"),
            source_subject=source.get("subject"),
            source_url=source.get("url"),
            contact_email=author.get("email"),
            contact_id=author.get("id"),
            user_id=user_id,
            # org_id requires fetching the contact separately
        )

    def fetch_contact_org_id(self, contact_id: str) -> Optional[str]:
        """Fetch org_id from contact's custom_attributes.account_id."""
        if not contact_id:
            return None

        try:
            contact = self._get(f"/contacts/{contact_id}")
            custom_attrs = contact.get("custom_attributes", {})
            return custom_attrs.get("account_id")
        except requests.RequestException:
            return None

    async def fetch_contact_org_ids_batch(
        self,
        contact_ids: list[str],
        concurrency: int = 20,
    ) -> dict[str, Optional[str]]:
        """
        Fetch org_ids for multiple contacts in parallel.

        ~50x faster than sequential fetch_contact_org_id calls.

        Args:
            contact_ids: List of Intercom contact IDs
            concurrency: Max parallel requests (default 20)

        Returns:
            Dict mapping contact_id -> org_id (or None if not found)
        """
        import asyncio
        import aiohttp

        # Deduplicate
        unique_ids = list(set(cid for cid in contact_ids if cid))
        if not unique_ids:
            return {}

        results = {}
        semaphore = asyncio.Semaphore(concurrency)

        # Use same timeout as sync client (connect, read)
        timeout = aiohttp.ClientTimeout(
            connect=self.timeout[0],
            total=self.timeout[0] + self.timeout[1]
        )

        async def fetch_one(session: aiohttp.ClientSession, contact_id: str):
            async with semaphore:
                try:
                    url = f"{self.BASE_URL}/contacts/{contact_id}"
                    headers = {
                        "Authorization": f"Bearer {self.access_token}",
                        "Accept": "application/json",
                        "Intercom-Version": self.API_VERSION,
                    }
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            custom_attrs = data.get("custom_attributes", {})
                            results[contact_id] = custom_attrs.get("account_id")
                        else:
                            results[contact_id] = None
                except Exception:
                    results[contact_id] = None

        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [fetch_one(session, cid) for cid in unique_ids]
            await asyncio.gather(*tasks)

        return results

    def fetch_contact_org_ids_batch_sync(
        self,
        contact_ids: list[str],
        concurrency: int = 20,
    ) -> dict[str, Optional[str]]:
        """
        Sync wrapper for fetch_contact_org_ids_batch.

        Usage:
            org_ids = client.fetch_contact_org_ids_batch_sync(contact_ids)
            for conv in conversations:
                org_id = org_ids.get(conv.contact_id)
        """
        import asyncio
        return asyncio.run(self.fetch_contact_org_ids_batch(contact_ids, concurrency))

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

                # Skip conversations outside date range
                # NOTE: Intercom sorts by updated_at, NOT created_at, so old
                # conversations can appear on any page. We must paginate through
                # all pages and filter by date, not assume sorted order.
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

    def search_by_date_range(
        self,
        start_timestamp: int,
        end_timestamp: int,
        per_page: int = 50,
        max_results: Optional[int] = None,
    ) -> Generator[dict, None, None]:
        """
        Search conversations within a date range using Intercom search API.

        Args:
            start_timestamp: Unix timestamp for start of range
            end_timestamp: Unix timestamp for end of range
            per_page: Results per page
            max_results: Maximum conversations to return

        Yields raw conversation dicts.
        """
        search_query = {
            "query": {
                "operator": "AND",
                "value": [
                    {
                        "field": "created_at",
                        "operator": ">",
                        "value": start_timestamp,
                    },
                    {
                        "field": "created_at",
                        "operator": "<",
                        "value": end_timestamp,
                    },
                ],
            },
            "pagination": {"per_page": per_page},
        }

        count = 0
        starting_after = None

        while True:
            if starting_after:
                search_query["pagination"]["starting_after"] = starting_after

            data = self._post("/conversations/search", search_query)
            conversations = data.get("conversations", [])

            if not conversations:
                break

            for conv in conversations:
                yield conv
                count += 1
                if max_results and count >= max_results:
                    return

            # Check for next page
            pages = data.get("pages", {})
            next_page = pages.get("next", {})
            starting_after = next_page.get("starting_after")

            if not starting_after:
                break


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
