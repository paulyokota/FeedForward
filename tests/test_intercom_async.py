"""
Intercom Client Async Methods Tests

Tests for the async Search API and related methods.
Run with: pytest tests/test_intercom_async.py -v
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import aiohttp

from src.intercom_client import IntercomClient, IntercomConversation

pytestmark = pytest.mark.medium


class TestSearchByDateRangeAsync:
    """Tests for search_by_date_range_async method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked token."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            return IntercomClient(max_retries=1)

    @pytest.fixture
    def mock_conversation(self):
        """Create a mock conversation dict."""
        return {
            "id": "123456",
            "created_at": 1705881600,  # 2024-01-22
            "source": {
                "delivered_as": "customer_initiated",
                "author": {"type": "user", "id": "user_1"},
                "body": "I need help with my account settings please",
            },
            "contacts": {"contacts": [{"external_id": "ext_123"}]},
        }

    @pytest.mark.asyncio
    async def test_search_returns_conversations_in_date_range(self, client, mock_conversation):
        """Test that search returns conversations within the date range."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "conversations": [mock_conversation],
            "pages": {}
        })

        @asynccontextmanager
        async def mock_post(*args, **kwargs):
            yield mock_response

        mock_session = AsyncMock()
        mock_session.post = mock_post

        @asynccontextmanager
        async def mock_session_ctx():
            yield mock_session

        with patch.object(client, "_get_aiohttp_session", mock_session_ctx):
            results = []
            async for conv in client.search_by_date_range_async(
                start_timestamp=1705800000,
                end_timestamp=1705900000,
            ):
                results.append(conv)

        assert len(results) == 1
        assert results[0]["id"] == "123456"

    @pytest.mark.asyncio
    async def test_search_constructs_correct_query(self, client):
        """Test that the search query has correct structure."""
        captured_json = None

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "conversations": [],
            "pages": {}
        })

        @asynccontextmanager
        async def mock_post(url, json=None):
            nonlocal captured_json
            captured_json = json
            yield mock_response

        mock_session = AsyncMock()
        mock_session.post = mock_post

        @asynccontextmanager
        async def mock_session_ctx():
            yield mock_session

        with patch.object(client, "_get_aiohttp_session", mock_session_ctx):
            async for _ in client.search_by_date_range_async(
                start_timestamp=1705800000,
                end_timestamp=1705900000,
                per_page=25,
            ):
                pass

        # Verify query structure
        assert captured_json is not None
        assert captured_json["query"]["operator"] == "AND"
        assert len(captured_json["query"]["value"]) == 2

        # Check start timestamp filter
        start_filter = captured_json["query"]["value"][0]
        assert start_filter["field"] == "created_at"
        assert start_filter["operator"] == ">"
        assert start_filter["value"] == 1705800000

        # Check end timestamp filter
        end_filter = captured_json["query"]["value"][1]
        assert end_filter["field"] == "created_at"
        assert end_filter["operator"] == "<"
        assert end_filter["value"] == 1705900000

        # Check pagination
        assert captured_json["pagination"]["per_page"] == 25

    @pytest.mark.asyncio
    async def test_search_handles_pagination(self, client, mock_conversation):
        """Test that search handles multiple pages correctly."""
        page1_conv = {**mock_conversation, "id": "page1_conv"}
        page2_conv = {**mock_conversation, "id": "page2_conv"}

        call_count = 0

        mock_response = AsyncMock()
        mock_response.status = 200

        async def mock_json():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "conversations": [page1_conv],
                    "pages": {"next": {"starting_after": "cursor_1"}}
                }
            else:
                return {
                    "conversations": [page2_conv],
                    "pages": {}
                }

        mock_response.json = mock_json

        @asynccontextmanager
        async def mock_post(*args, **kwargs):
            yield mock_response

        mock_session = AsyncMock()
        mock_session.post = mock_post

        @asynccontextmanager
        async def mock_session_ctx():
            yield mock_session

        with patch.object(client, "_get_aiohttp_session", mock_session_ctx):
            results = []
            async for conv in client.search_by_date_range_async(
                start_timestamp=1705800000,
                end_timestamp=1705900000,
            ):
                results.append(conv)

        assert len(results) == 2
        assert results[0]["id"] == "page1_conv"
        assert results[1]["id"] == "page2_conv"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client, mock_conversation):
        """Test that search stops at max_results."""
        conversations = [
            {**mock_conversation, "id": f"conv_{i}"}
            for i in range(10)
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "conversations": conversations,
            "pages": {"next": {"starting_after": "more_data"}}
        })

        @asynccontextmanager
        async def mock_post(*args, **kwargs):
            yield mock_response

        mock_session = AsyncMock()
        mock_session.post = mock_post

        @asynccontextmanager
        async def mock_session_ctx():
            yield mock_session

        with patch.object(client, "_get_aiohttp_session", mock_session_ctx):
            results = []
            async for conv in client.search_by_date_range_async(
                start_timestamp=1705800000,
                end_timestamp=1705900000,
                max_results=3,
            ):
                results.append(conv)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_handles_empty_results(self, client):
        """Test that search handles empty results gracefully."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "conversations": [],
            "pages": {}
        })

        @asynccontextmanager
        async def mock_post(*args, **kwargs):
            yield mock_response

        mock_session = AsyncMock()
        mock_session.post = mock_post

        @asynccontextmanager
        async def mock_session_ctx():
            yield mock_session

        with patch.object(client, "_get_aiohttp_session", mock_session_ctx):
            results = []
            async for conv in client.search_by_date_range_async(
                start_timestamp=1705800000,
                end_timestamp=1705900000,
            ):
                results.append(conv)

        assert len(results) == 0


class TestFetchQualityConversationsAsync:
    """Tests for fetch_quality_conversations_async method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked token."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            return IntercomClient(max_retries=1)

    @pytest.fixture
    def quality_conversation(self):
        """Create a conversation that passes quality filter."""
        return {
            "id": "quality_123",
            "created_at": 1705881600,
            "source": {
                "delivered_as": "customer_initiated",
                "author": {"type": "user", "id": "user_1"},
                "body": "I need help with my account settings and billing information please",
            },
            "contacts": {"contacts": [{"external_id": "ext_123"}]},
        }

    @pytest.fixture
    def filtered_conversation(self):
        """Create a conversation that fails quality filter (admin initiated)."""
        return {
            "id": "filtered_123",
            "created_at": 1705881600,
            "source": {
                "delivered_as": "admin_initiated",
                "author": {"type": "admin", "id": "admin_1"},
                "body": "Hello, how can I help you?",
            },
        }

    @pytest.mark.asyncio
    async def test_uses_search_api_with_date_range(self, client, quality_conversation):
        """Test that fetch_quality uses search API with correct date range."""
        since = datetime(2024, 1, 20, 0, 0, 0)

        captured_timestamps = None

        async def mock_search(start_ts, end_ts, per_page, max_results, **kwargs):
            nonlocal captured_timestamps
            captured_timestamps = (start_ts, end_ts)
            yield quality_conversation

        with patch.object(client, "search_by_date_range_async", mock_search):
            results = []
            async for parsed, raw in client.fetch_quality_conversations_async(since=since):
                results.append((parsed, raw))

        assert captured_timestamps is not None
        assert captured_timestamps[0] == int(since.timestamp())
        # end_ts should be close to now
        assert captured_timestamps[1] > captured_timestamps[0]

    @pytest.mark.asyncio
    async def test_filters_non_quality_conversations(self, client, quality_conversation, filtered_conversation):
        """Test that non-quality conversations are filtered out."""
        async def mock_search(start_ts, end_ts, per_page, max_results, **kwargs):
            yield quality_conversation
            yield filtered_conversation

        with patch.object(client, "search_by_date_range_async", mock_search):
            results = []
            async for parsed, raw in client.fetch_quality_conversations_async(
                since=datetime(2024, 1, 20)
            ):
                results.append((parsed, raw))

        # Only quality conversation should pass
        assert len(results) == 1
        assert results[0][1]["id"] == "quality_123"

    @pytest.mark.asyncio
    async def test_returns_parsed_and_raw_conversation(self, client, quality_conversation):
        """Test that both parsed and raw conversation are returned."""
        async def mock_search(start_ts, end_ts, per_page, max_results, **kwargs):
            yield quality_conversation

        with patch.object(client, "search_by_date_range_async", mock_search):
            results = []
            async for parsed, raw in client.fetch_quality_conversations_async(
                since=datetime(2024, 1, 20)
            ):
                results.append((parsed, raw))

        assert len(results) == 1
        parsed, raw = results[0]

        # Check parsed is IntercomConversation
        assert isinstance(parsed, IntercomConversation)
        assert parsed.id == "quality_123"

        # Check raw is original dict
        assert raw == quality_conversation

    @pytest.mark.asyncio
    async def test_handles_until_parameter(self, client, quality_conversation):
        """Test that until parameter is converted to timestamp."""
        since = datetime(2024, 1, 20, 0, 0, 0)
        until = datetime(2024, 1, 25, 0, 0, 0)

        captured_timestamps = None

        async def mock_search(start_ts, end_ts, per_page, max_results, **kwargs):
            nonlocal captured_timestamps
            captured_timestamps = (start_ts, end_ts)
            yield quality_conversation

        with patch.object(client, "search_by_date_range_async", mock_search):
            results = []
            async for parsed, raw in client.fetch_quality_conversations_async(
                since=since, until=until
            ):
                results.append((parsed, raw))

        assert captured_timestamps is not None
        assert captured_timestamps[0] == int(since.timestamp())
        assert captured_timestamps[1] == int(until.timestamp())


class TestAsyncRetryLogic:
    """Tests for _request_with_retry_async method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked token."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            return IntercomClient(max_retries=2)

    @pytest.mark.asyncio
    async def test_successful_request_no_retry(self, client):
        """Test that successful requests don't trigger retry."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": "success"})

        call_count = 0

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            yield mock_response

        mock_session = AsyncMock()
        mock_session.get = mock_get

        result = await client._request_with_retry_async(mock_session, "GET", "/test")

        assert result == {"data": "success"}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_500_error(self, client):
        """Test retry on 500 Internal Server Error."""
        call_count = 0

        mock_fail = AsyncMock()
        mock_fail.status = 500

        mock_success = AsyncMock()
        mock_success.status = 200
        mock_success.json = AsyncMock(return_value={"data": "recovered"})

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_fail
            else:
                yield mock_success

        mock_session = AsyncMock()
        mock_session.get = mock_get

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request_with_retry_async(mock_session, "GET", "/test")

        assert result == {"data": "recovered"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_502_error(self, client):
        """Test retry on 502 Bad Gateway."""
        call_count = 0

        mock_fail = AsyncMock()
        mock_fail.status = 502

        mock_success = AsyncMock()
        mock_success.status = 200
        mock_success.json = AsyncMock(return_value={"data": "recovered"})

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_fail
            else:
                yield mock_success

        mock_session = AsyncMock()
        mock_session.get = mock_get

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request_with_retry_async(mock_session, "GET", "/test")

        assert result == {"data": "recovered"}
        assert call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="BUG: Production code catches aiohttp.ClientError which includes ClientResponseError from raise_for_status(). "
               "4xx errors are incorrectly retried. Fix requires production code change.",
        strict=True,
    )
    async def test_no_retry_on_400_error(self, client):
        """Test that 4xx errors are not retried.

        NOTE: This test documents expected behavior, but production code has a bug
        where aiohttp.ClientResponseError (from raise_for_status) is caught by
        the ClientError handler and retried. This should be fixed in production.
        """
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.raise_for_status = Mock(side_effect=aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=400,
        ))

        call_count = 0

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            yield mock_response

        mock_session = AsyncMock()
        mock_session.get = mock_get

        with pytest.raises(aiohttp.ClientResponseError):
            await client._request_with_retry_async(mock_session, "GET", "/test")

        # 4xx errors should NOT be retried - only 1 attempt expected
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(self, client):
        """Test that after max retries, the error is raised."""
        mock_fail = AsyncMock()
        mock_fail.status = 500
        mock_fail.raise_for_status = Mock(side_effect=aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=500,
        ))

        call_count = 0

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            yield mock_fail

        mock_session = AsyncMock()
        mock_session.get = mock_get

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(aiohttp.ClientResponseError):
                await client._request_with_retry_async(mock_session, "GET", "/test")

        # 1 initial + 2 retries = 3 total attempts
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_post_request_with_retry(self, client):
        """Test that POST requests also use retry logic."""
        call_count = 0

        mock_fail = AsyncMock()
        mock_fail.status = 503

        mock_success = AsyncMock()
        mock_success.status = 200
        mock_success.json = AsyncMock(return_value={"result": "ok"})

        @asynccontextmanager
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_fail
            else:
                yield mock_success

        mock_session = AsyncMock()
        mock_session.post = mock_post

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request_with_retry_async(
                mock_session, "POST", "/search", json_data={"query": "test"}
            )

        assert result == {"result": "ok"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_client_error(self, client):
        """Test retry on aiohttp ClientError."""
        call_count = 0

        mock_success = AsyncMock()
        mock_success.status = 200
        mock_success.json = AsyncMock(return_value={"data": "recovered"})

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise aiohttp.ClientError("Connection failed")
            yield mock_success

        mock_session = AsyncMock()
        mock_session.get = mock_get

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request_with_retry_async(mock_session, "GET", "/test")

        assert result == {"data": "recovered"}
        assert call_count == 2


class TestGetConversationAsync:
    """Tests for get_conversation_async method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked token."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            return IntercomClient(max_retries=1)

    @pytest.mark.asyncio
    async def test_fetches_conversation_by_id(self, client):
        """Test that get_conversation_async fetches by ID."""
        expected_conv = {"id": "conv_123", "data": "full_conversation"}

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=expected_conv)

        @asynccontextmanager
        async def mock_get(url, params=None):
            assert "/conversations/conv_123" in url
            yield mock_response

        mock_session = AsyncMock()
        mock_session.get = mock_get

        result = await client.get_conversation_async(mock_session, "conv_123")

        assert result == expected_conv


class TestAiohttpSessionCreation:
    """Tests for _get_aiohttp_session method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked token."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            return IntercomClient()

    @pytest.mark.asyncio
    async def test_session_has_correct_headers(self, client):
        """Test that session is created with correct headers."""
        async with client._get_aiohttp_session() as session:
            headers = session._default_headers
            assert "Authorization" in headers
            assert headers["Authorization"] == f"Bearer {client.access_token}"
            assert headers["Accept"] == "application/json"
            assert headers["Content-Type"] == "application/json"
            assert "Intercom-Version" in headers

    @pytest.mark.asyncio
    async def test_session_has_timeout_configured(self, client):
        """Test that session has timeout configured."""
        async with client._get_aiohttp_session() as session:
            timeout = session._timeout
            assert timeout.connect == client.timeout[0]
