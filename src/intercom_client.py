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
import random
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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

    # Retry configuration for transient errors (429 rate limit, 5xx server errors)
    # 3 retries with 2s base delay = max 14s total wait (2+4+8), reasonable for API ops
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # seconds, exponential backoff: 2s, 4s, 8s
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}  # Issue #205: Added 429 for rate limit handling

    # Runtime configuration knobs (Issue #205: Backfill tuning)
    # Validated to prevent misconfiguration causing resource exhaustion
    FETCH_CONCURRENCY = max(1, min(100, int(os.getenv("INTERCOM_FETCH_CONCURRENCY", "10"))))
    PER_PAGE = max(1, min(150, int(os.getenv("INTERCOM_PER_PAGE", "50"))))  # Intercom max is 150
    MAX_RPS = max(0.0, min(100.0, float(os.getenv("INTERCOM_MAX_RPS", "0"))))  # 0 = no limit

    # Template messages to skip
    TEMPLATE_MESSAGES = [
        "i have a product question or feedback",
        "i have a billing question",
        "hi",
        "hello",
    ]

    # Issue #164: Recovery thresholds for quality-filtered conversations
    # If any single user message meets this threshold, recover the conversation
    RECOVERY_MIN_MESSAGE_CHARS = 100
    # If total user content meets this threshold, recover the conversation
    RECOVERY_MIN_TOTAL_CHARS = 200


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

    @staticmethod
    def _parse_retry_after(header_value: str) -> int:
        """
        Parse Retry-After header value.

        The header can be either:
        - An integer (seconds to wait)
        - An HTTP-date (absolute time to retry after)

        Args:
            header_value: The Retry-After header value

        Returns:
            Number of seconds to wait (minimum 1)
        """
        try:
            # Try parsing as integer (seconds)
            return max(1, int(header_value))
        except ValueError:
            # Try parsing as HTTP-date format
            try:
                retry_at = parsedate_to_datetime(header_value)
                # Ensure timezone-aware comparison (RFC 7231 requires GMT but handle edge cases)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delta = (retry_at - datetime.now(timezone.utc)).total_seconds()
                return max(1, int(delta))
            except (ValueError, TypeError):
                # If parsing fails, return a safe default (10s is typical rate limit window)
                return 10

    @staticmethod
    def _add_jitter(base_delay: float) -> float:
        """
        Add jitter to a delay to prevent thundering herd.

        When multiple concurrent requests hit rate limits simultaneously,
        synchronized retries can repeatedly collide. Jitter randomizes
        retry timing to spread load and increase success rate.

        Adds 0-50% of base delay, so total delay is 100-150% of base.

        Args:
            base_delay: The base delay in seconds

        Returns:
            Delay with jitter added
        """
        jitter = random.uniform(0, 0.5 * base_delay)
        return base_delay + jitter

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
        - 429 rate limit (with Retry-After header support)
        - 5xx server errors (500, 502, 503, 504)
        - Connection errors (network issues, timeouts)

        Does NOT retry on:
        - 4xx client errors (except 429, these indicate a problem with the request)
        """
        url = f"{self.BASE_URL}{endpoint}"
        last_exception = None

        # Issue #205: Enforce MAX_RPS rate limiting
        if self.MAX_RPS > 0:
            time.sleep(1.0 / self.MAX_RPS)

        for attempt in range(self.max_retries + 1):
            try:
                if method == "GET":
                    response = self.session.get(url, params=params, timeout=self.timeout)
                else:
                    response = self.session.post(url, json=json, timeout=self.timeout)

                # Issue #205: Log rate limit headers for observability
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    try:
                        remaining_int = int(remaining)
                        if remaining_int < 100:
                            logger.warning(
                                f"Rate limit low: {remaining_int} requests remaining on {endpoint}"
                            )
                        else:
                            logger.debug(f"Rate limit remaining: {remaining_int} on {endpoint}")
                    except (ValueError, TypeError):
                        pass  # Ignore invalid header values

                # Check if we should retry on retryable status codes
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    if attempt < self.max_retries:
                        # Issue #205: Handle 429 with Retry-After header
                        if response.status_code == 429:
                            retry_after = response.headers.get("Retry-After")
                            if retry_after:
                                base_delay = self._parse_retry_after(retry_after)
                            else:
                                base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                            delay = self._add_jitter(base_delay)
                            logger.warning(
                                f"Rate limited (429) on {endpoint}, waiting {delay:.1f}s "
                                f"(retry-after={retry_after}, attempt {attempt + 1}/{self.max_retries + 1})"
                            )
                        else:
                            # 5xx errors: exponential backoff with jitter
                            base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                            delay = self._add_jitter(base_delay)
                            logger.warning(
                                f"Intercom API error {response.status_code} on {endpoint}, "
                                f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                            )
                        time.sleep(delay)
                        continue
                    else:
                        # Last attempt failed, raise the error
                        response.raise_for_status()

                # For non-retryable errors (4xx except 429), raise immediately without retry
                response.raise_for_status()
                return response.json()

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                # Retry on connection-level errors
                last_exception = e
                if attempt < self.max_retries:
                    base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    delay = self._add_jitter(base_delay)
                    logger.warning(
                        f"Intercom API connection error: {e}, "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
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

        Retries on 429 (rate limit) and 5xx (server errors) with exponential backoff.
        Same retry logic as sync version but using aiohttp.

        Args:
            session: aiohttp ClientSession with auth headers
            method: HTTP method (GET or POST)
            endpoint: API endpoint path
            params: Query parameters for GET requests
            json_data: JSON body for POST requests

        Returns:
            Parsed JSON response

        Raises:
            aiohttp.ClientError: On non-retryable errors or after max retries
        """
        url = f"{self.BASE_URL}{endpoint}"

        # Issue #205: Enforce MAX_RPS rate limiting
        if self.MAX_RPS > 0:
            await asyncio.sleep(1.0 / self.MAX_RPS)

        for attempt in range(self.max_retries + 1):
            try:
                if method == "GET":
                    async with session.get(url, params=params) as response:
                        # Issue #205: Log rate limit headers for observability
                        remaining = response.headers.get("X-RateLimit-Remaining")
                        if remaining is not None:
                            try:
                                remaining_int = int(remaining)
                                if remaining_int < 100:
                                    logger.warning(
                                        f"Rate limit low: {remaining_int} requests remaining on {endpoint}"
                                    )
                                else:
                                    logger.debug(f"Rate limit remaining: {remaining_int} on {endpoint}")
                            except (ValueError, TypeError):
                                pass  # Ignore invalid header values

                        if response.status in self.RETRYABLE_STATUS_CODES:
                            if attempt < self.max_retries:
                                # Issue #205: Handle 429 with Retry-After header
                                if response.status == 429:
                                    retry_after = response.headers.get("Retry-After")
                                    if retry_after:
                                        base_delay = self._parse_retry_after(retry_after)
                                    else:
                                        base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                                    delay = self._add_jitter(base_delay)
                                    logger.warning(
                                        f"Rate limited (429) on {endpoint}, waiting {delay:.1f}s "
                                        f"(retry-after={retry_after}, attempt {attempt + 1}/{self.max_retries + 1})"
                                    )
                                else:
                                    # 5xx errors: exponential backoff with jitter
                                    base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                                    delay = self._add_jitter(base_delay)
                                    logger.warning(
                                        f"Intercom API error {response.status} on {endpoint}, "
                                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                                    )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                response.raise_for_status()
                        response.raise_for_status()
                        return await response.json()
                else:
                    async with session.post(url, json=json_data) as response:
                        # Issue #205: Log rate limit headers for observability
                        remaining = response.headers.get("X-RateLimit-Remaining")
                        if remaining is not None:
                            try:
                                remaining_int = int(remaining)
                                if remaining_int < 100:
                                    logger.warning(
                                        f"Rate limit low: {remaining_int} requests remaining on {endpoint}"
                                    )
                                else:
                                    logger.debug(f"Rate limit remaining: {remaining_int} on {endpoint}")
                            except (ValueError, TypeError):
                                pass  # Ignore invalid header values

                        if response.status in self.RETRYABLE_STATUS_CODES:
                            if attempt < self.max_retries:
                                # Issue #205: Handle 429 with Retry-After header
                                if response.status == 429:
                                    retry_after = response.headers.get("Retry-After")
                                    if retry_after:
                                        base_delay = self._parse_retry_after(retry_after)
                                    else:
                                        base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                                    delay = self._add_jitter(base_delay)
                                    logger.warning(
                                        f"Rate limited (429) on {endpoint}, waiting {delay:.1f}s "
                                        f"(retry-after={retry_after}, attempt {attempt + 1}/{self.max_retries + 1})"
                                    )
                                else:
                                    # 5xx errors: exponential backoff with jitter
                                    base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                                    delay = self._add_jitter(base_delay)
                                    logger.warning(
                                        f"Intercom API error {response.status} on {endpoint}, "
                                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                                    )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                response.raise_for_status()
                        response.raise_for_status()
                        return await response.json()

            except aiohttp.ClientError as e:
                if attempt < self.max_retries:
                    base_delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    delay = self._add_jitter(base_delay)
                    logger.warning(
                        f"Intercom API connection error: {e}, "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise RuntimeError("Unexpected retry loop exit")

    def _get_aiohttp_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session with proper headers and timeout.

        Timeout configuration matches sync version:
        - connect: Connection establishment timeout (default 10s)
        - sock_read: Per-read operation timeout (default 30s)
        - total: Overall request timeout
        """
        timeout = aiohttp.ClientTimeout(
            connect=self.timeout[0],
            sock_read=self.timeout[1],
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
        per_page: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Fetch raw conversations from Intercom (async version).

        Uses the List API with client-side date filtering.
        NOTE: For date-bounded queries, prefer search_by_date_range_async
        which uses server-side filtering and is much more efficient.

        Yields raw conversation dicts for further processing.
        Handles pagination automatically.
        """
        # Issue #205: Use runtime knob for per_page default
        effective_per_page = per_page if per_page is not None else self.PER_PAGE
        params = {"per_page": effective_per_page}
        endpoint = "/conversations"
        page_count = 0

        async with self._get_aiohttp_session() as session:
            while True:
                data = await self._request_with_retry_async(session, "GET", endpoint, params=params)
                conversations = data.get("conversations", [])

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

                if not next_page:
                    break

                page_count += 1
                if max_pages and page_count >= max_pages:
                    break

                starting_after = next_page.get("starting_after")
                if starting_after:
                    params["starting_after"] = starting_after
                else:
                    break

    async def fetch_quality_conversations_async(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        per_page: Optional[int] = None,
        max_results: Optional[int] = None,
        recovery_candidates: Optional[list] = None,
        initial_cursor: Optional[str] = None,
        cursor_callback: Optional[callable] = None,
        on_cursor_fallback: Optional[callable] = None,
    ) -> AsyncGenerator[tuple["IntercomConversation", dict], None]:
        """
        Fetch and filter conversations, returning only quality ones (async version).

        Uses the Search API for server-side date filtering, which is MUCH more
        efficient than the List API (avoids fetching all 338k+ conversations).

        Args:
            since: Start of date range (inclusive)
            until: End of date range (exclusive), defaults to now
            per_page: Results per API page (default: PER_PAGE from env)
            max_results: Maximum conversations to return
            recovery_candidates: Issue #164 - If provided, filtered conversations
                that are potentially recoverable (short body, not template) are
                appended to this list for later recovery evaluation.
            initial_cursor: Issue #202 - Optional cursor to resume from. If provided,
                starts fetching from this cursor position instead of the beginning.
            cursor_callback: Issue #202 - Optional callback(cursor: str) called after
                each page with the cursor for the NEXT page. Used for checkpoint persistence.
            on_cursor_fallback: Issue #202 - Optional callback() called if initial_cursor
                was invalid and we restarted from beginning. For observability.

        Yields:
            (parsed_conversation, raw_conversation) tuples for quality conversations
        """
        from datetime import timezone

        # Convert datetime to unix timestamps for Search API
        start_ts = int(since.timestamp()) if since else 0
        end_ts = int(until.timestamp()) if until else int(datetime.now(timezone.utc).timestamp())

        async for raw_conv in self.search_by_date_range_async(
            start_ts, end_ts, per_page, max_results,
            initial_cursor=initial_cursor, cursor_callback=cursor_callback,
            on_cursor_fallback=on_cursor_fallback
        ):
            filter_result = self.quality_filter(raw_conv)
            if filter_result.passed:
                parsed = self.parse_conversation(raw_conv)
                yield parsed, raw_conv
            elif recovery_candidates is not None:
                # Issue #164: Track potentially recoverable conversations
                # Only track if filtered for "body too short" - not for template/author issues
                if filter_result.reason and "body too short" in filter_result.reason:
                    parsed = self.parse_conversation(raw_conv)
                    recovery_candidates.append((parsed, raw_conv, False))  # (parsed, raw, had_template)
                elif filter_result.reason == "template message":
                    # Template openers might have real follow-ups
                    parsed = self.parse_conversation(raw_conv)
                    recovery_candidates.append((parsed, raw_conv, True))  # had_template=True

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
        per_page: Optional[int] = None,
        max_results: Optional[int] = None,
        initial_cursor: Optional[str] = None,
        cursor_callback: Optional[callable] = None,
        on_cursor_fallback: Optional[callable] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Search conversations within a date range using Intercom Search API (async).

        Uses server-side filtering via POST /conversations/search, which is MUCH
        more efficient than the LIST API for date-bounded queries.

        Args:
            start_timestamp: Unix timestamp for start of range (exclusive: >)
            end_timestamp: Unix timestamp for end of range (exclusive: <)
            per_page: Results per page (default: PER_PAGE from env)
            max_results: Maximum conversations to return
            initial_cursor: Optional cursor to resume pagination from (Issue #202).
                           If provided, starts pagination from this cursor instead of the beginning.
            cursor_callback: Optional callback(cursor: str) called after each page with
                           the cursor for the NEXT page. Used for checkpoint persistence.
            on_cursor_fallback: Optional callback() called when cursor is invalid and we restart
                           from beginning. Use for observability (Issue #202).

        Yields:
            Raw conversation dicts from Intercom API
        """
        # Issue #205: Use runtime knob for per_page default
        effective_per_page = per_page if per_page is not None else self.PER_PAGE

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
            "pagination": {"per_page": effective_per_page},
        }

        count = 0
        # Issue #202: Support resuming from a cursor
        starting_after = initial_cursor
        cursor_fallback_attempted = False  # Retry guard for invalid cursor

        async with self._get_aiohttp_session() as session:
            while True:
                if starting_after:
                    search_query["pagination"]["starting_after"] = starting_after
                elif "starting_after" in search_query.get("pagination", {}):
                    # Clear cursor if we're restarting from beginning
                    del search_query["pagination"]["starting_after"]

                try:
                    data = await self._request_with_retry_async(
                        session, "POST", "/conversations/search", json_data=search_query
                    )
                except aiohttp.ClientResponseError as e:
                    # Issue #205: Handle invalid cursor gracefully
                    # Cursor can become invalid if it expires or API state changes.
                    #
                    # Retry WITHOUT cursor for: 4xx client errors (except 429)
                    #   - 400/422: Invalid/expired cursor → restart from beginning
                    #   - Other 4xx: Request malformed → likely cursor issue
                    #
                    # DO NOT retry for:
                    #   - 429 (rate limit): Not a cursor issue, normal retry with same cursor
                    #   - 5xx (server error): Not a cursor issue, normal retry with same cursor
                    if initial_cursor and not cursor_fallback_attempted and e.status < 500 and e.status != 429:
                        logger.warning(
                            "Search failed with cursor <present>, HTTP %d, restarting from beginning: %s",
                            e.status, e
                        )
                        cursor_fallback_attempted = True
                        starting_after = None
                        initial_cursor = None  # Clear so we don't loop
                        # Issue #202: Notify caller about fallback for observability
                        if on_cursor_fallback:
                            on_cursor_fallback()
                        continue  # Retry without cursor
                    raise  # Re-raise if fallback already attempted, no cursor, or non-cursor error

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

                # Issue #202: Notify caller of cursor position for checkpointing
                if cursor_callback and starting_after:
                    cursor_callback(starting_after)

                if not starting_after:
                    break

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

    def should_recover_conversation(
        self,
        full_messages: list[dict],
        had_template_opener: bool = False,
    ) -> bool:
        """
        Check if a quality-filtered conversation should be recovered based on follow-ups.

        Issue #164: Short initial messages can later include high-signal details.
        This method evaluates the full conversation thread to determine if
        subsequent messages contain enough content to warrant classification.

        Args:
            full_messages: List of message dicts from the full conversation
            had_template_opener: If True, the opener was a template message;
                                 skip it when evaluating user content

        Returns:
            True if the conversation should be recovered for classification
        """
        # Extract user messages only
        user_messages = []
        for msg in full_messages:
            author = msg.get("author", {})
            if author.get("type") == "user":
                user_messages.append(msg)

        # Skip if no user messages
        if not user_messages:
            return False

        # Review fix: Filter out template messages by text content, not position
        # This handles cases where messages may not be in chronological order
        if had_template_opener:
            non_template_messages = []
            for msg in user_messages:
                body = self.strip_html(msg.get("body", "")).lower().strip()
                if body not in self.TEMPLATE_MESSAGES:
                    non_template_messages.append(msg)
            user_messages = non_template_messages

            # If only template messages, no real follow-up
            if not user_messages:
                return False

        # Check if any single message meets threshold
        for msg in user_messages:
            body = self.strip_html(msg.get("body", ""))
            if len(body) >= self.RECOVERY_MIN_MESSAGE_CHARS:
                return True

        # Check total user content
        total_chars = sum(
            len(self.strip_html(msg.get("body", "")))
            for msg in user_messages
        )
        return total_chars >= self.RECOVERY_MIN_TOTAL_CHARS

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
        concurrency: Optional[int] = None,
    ) -> dict[str, Optional[str]]:
        """
        Fetch org_ids for multiple contacts in parallel.

        ~50x faster than sequential fetch_contact_org_id calls.

        Args:
            contact_ids: List of Intercom contact IDs
            concurrency: Max parallel requests (default: FETCH_CONCURRENCY from env)

        Returns:
            Dict mapping contact_id -> org_id (or None if not found)
        """
        import asyncio
        import aiohttp

        # Deduplicate
        unique_ids = list(set(cid for cid in contact_ids if cid))
        if not unique_ids:
            return {}

        # Issue #205: Use runtime knob for concurrency default
        effective_concurrency = concurrency if concurrency is not None else self.FETCH_CONCURRENCY

        results = {}
        semaphore = asyncio.Semaphore(effective_concurrency)

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
        concurrency: Optional[int] = None,
    ) -> dict[str, Optional[str]]:
        """
        Sync wrapper for fetch_contact_org_ids_batch.

        Usage:
            org_ids = client.fetch_contact_org_ids_batch_sync(contact_ids)
            for conv in conversations:
                org_id = org_ids.get(conv.contact_id)
        """
        import asyncio
        # Issue #205: Pass through concurrency (async method uses FETCH_CONCURRENCY default)
        return asyncio.run(self.fetch_contact_org_ids_batch(contact_ids, concurrency))

    def fetch_conversations(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        per_page: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Generator[dict, None, None]:
        """
        Fetch raw conversations from Intercom.

        Yields raw conversation dicts for further processing.
        Handles pagination automatically.
        """
        # Issue #205: Use runtime knob for per_page default
        effective_per_page = per_page if per_page is not None else self.PER_PAGE
        params = {"per_page": effective_per_page}
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
        per_page: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Generator[tuple[IntercomConversation, dict], None, None]:
        """
        Fetch and filter conversations, returning only quality ones.

        Yields (parsed_conversation, raw_conversation) tuples.
        """
        # Issue #205: per_page default is handled by fetch_conversations
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
        per_page: Optional[int] = None,
    ) -> Generator[dict, None, None]:
        """
        Search conversations by body content.

        Useful for finding specific types of conversations.
        """
        # Issue #205: Use runtime knob for per_page default
        effective_per_page = per_page if per_page is not None else self.PER_PAGE
        search_query = {
            "query": {
                "field": "source.body",
                "operator": "~",
                "value": query,
            },
            "pagination": {"per_page": effective_per_page},
        }

        data = self._post("/conversations/search", search_query)
        for conv in data.get("conversations", []):
            yield conv

    def search_by_date_range(
        self,
        start_timestamp: int,
        end_timestamp: int,
        per_page: Optional[int] = None,
        max_results: Optional[int] = None,
    ) -> Generator[dict, None, None]:
        """
        Search conversations within a date range using Intercom search API.

        Args:
            start_timestamp: Unix timestamp for start of range
            end_timestamp: Unix timestamp for end of range
            per_page: Results per page (default: PER_PAGE from env)
            max_results: Maximum conversations to return

        Yields raw conversation dicts.
        """
        # Issue #205: Use runtime knob for per_page default
        effective_per_page = per_page if per_page is not None else self.PER_PAGE
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
            "pagination": {"per_page": effective_per_page},
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
