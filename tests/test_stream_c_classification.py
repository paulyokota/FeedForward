"""
Stream C: Classification Stack Tests

Tests for Issues #165, #164, and #160:
- #165: Theme extraction scope expansion (account_issue, configuration_help)
- #164: Quality filter recovery for conversations with detailed follow-ups
- #160: Context provider for Stage 2 classification

Run with: pytest tests/test_stream_c_classification.py -v
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# =============================================================================
# Issue #165: Theme Extraction Scope Expansion Tests
# =============================================================================


class TestThemeExtractionTypeFiltering:
    """Tests for is_actionable_for_theme_extraction function."""

    def test_always_allowed_types_pass_unconditionally(self):
        """product_issue, feature_request, how_to_question always pass."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        for issue_type in ["product_issue", "feature_request", "how_to_question"]:
            result = is_actionable_for_theme_extraction(
                issue_type=issue_type,
                support_insights=None,
                source_body=None,
                full_conversation=None,
            )
            assert result is True, f"{issue_type} should always pass"

    def test_account_issue_with_oauth_in_features_passes(self):
        """account_issue passes when oauth is in features_mentioned."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="account_issue",
            support_insights={
                "products_mentioned": [],
                "features_mentioned": ["oauth", "login"],
            },
            source_body=None,
            full_conversation=None,
        )
        assert result is True

    def test_account_issue_with_token_in_products_passes(self):
        """account_issue passes when token is in products_mentioned."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="account_issue",
            support_insights={
                "products_mentioned": ["token refresh"],
                "features_mentioned": [],
            },
            source_body=None,
            full_conversation=None,
        )
        assert result is True

    def test_account_issue_without_keywords_filtered_out(self):
        """account_issue without actionable keywords is filtered."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="account_issue",
            support_insights={
                "products_mentioned": ["scheduling"],
                "features_mentioned": ["calendar"],
            },
            source_body="I need to reset my password",
            full_conversation="User wants password reset",
        )
        assert result is False

    def test_configuration_help_with_api_keyword_passes(self):
        """configuration_help passes when api keyword is present."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="configuration_help",
            support_insights={
                "products_mentioned": ["api integration"],
                "features_mentioned": [],
            },
            source_body=None,
            full_conversation=None,
        )
        assert result is True

    def test_fallback_to_source_body_when_insights_empty(self):
        """Falls back to scanning source_body when support_insights is empty."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="account_issue",
            support_insights={},
            source_body="My OAuth token expired and I can't refresh it",
            full_conversation=None,
        )
        assert result is True

    def test_fallback_to_full_conversation(self):
        """Falls back to scanning full_conversation when other sources empty."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="configuration_help",
            support_insights=None,
            source_body="Need help",
            full_conversation="Customer is having issues with webhook integration",
        )
        assert result is True

    def test_billing_question_always_filtered(self):
        """billing_question is not in allowed or conditional types."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="billing_question",
            support_insights={"features_mentioned": ["oauth"]},
            source_body="oauth issue",
            full_conversation="oauth problem",
        )
        assert result is False

    def test_spam_always_filtered(self):
        """spam is never allowed through."""
        from src.api.routers.pipeline import is_actionable_for_theme_extraction

        result = is_actionable_for_theme_extraction(
            issue_type="spam",
            support_insights=None,
            source_body=None,
            full_conversation=None,
        )
        assert result is False


# =============================================================================
# Issue #164: Quality Filter Recovery Tests
# =============================================================================


class TestQualityFilterRecovery:
    """Tests for should_recover_conversation method."""

    @pytest.fixture
    def client(self):
        """Create IntercomClient instance for testing."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            from src.intercom_client import IntercomClient
            return IntercomClient()

    def test_recovery_with_long_followup_message(self, client):
        """Conversation with 100+ char follow-up should be recovered."""
        messages = [
            {"author": {"type": "user"}, "body": "Hi"},  # Short opener
            {"author": {"type": "admin"}, "body": "Hello, how can I help?"},
            {"author": {"type": "user"}, "body": "A" * 150},  # Long follow-up
        ]
        result = client.should_recover_conversation(messages, had_template_opener=False)
        assert result is True

    def test_no_recovery_with_short_messages(self, client):
        """Conversation with only short messages should not be recovered."""
        messages = [
            {"author": {"type": "user"}, "body": "Hi"},
            {"author": {"type": "admin"}, "body": "Hello!"},
            {"author": {"type": "user"}, "body": "Thanks"},
        ]
        result = client.should_recover_conversation(messages, had_template_opener=False)
        assert result is False

    def test_recovery_with_cumulative_total(self, client):
        """Conversation with 200+ total chars across messages should be recovered."""
        messages = [
            {"author": {"type": "user"}, "body": "A" * 80},  # 80 chars
            {"author": {"type": "admin"}, "body": "Let me help"},
            {"author": {"type": "user"}, "body": "B" * 80},  # 80 chars
            {"author": {"type": "user"}, "body": "C" * 50},  # 50 chars = 210 total
        ]
        result = client.should_recover_conversation(messages, had_template_opener=False)
        assert result is True

    def test_template_opener_skipped_in_recovery(self, client):
        """Template opener should be skipped, recovery based on follow-ups."""
        messages = [
            {"author": {"type": "user"}, "body": "i have a product question"},  # Template
            {"author": {"type": "admin"}, "body": "Sure, what's your question?"},
            {"author": {"type": "user"}, "body": "A" * 150},  # Real follow-up
        ]
        result = client.should_recover_conversation(messages, had_template_opener=True)
        assert result is True

    def test_template_only_not_recovered(self, client):
        """Conversation with only template opener should not be recovered."""
        messages = [
            {"author": {"type": "user"}, "body": "i have a billing question"},
        ]
        result = client.should_recover_conversation(messages, had_template_opener=True)
        assert result is False

    def test_no_user_messages_not_recovered(self, client):
        """Conversation with no user messages should not be recovered."""
        messages = [
            {"author": {"type": "admin"}, "body": "Automated message"},
        ]
        result = client.should_recover_conversation(messages, had_template_opener=False)
        assert result is False

    def test_empty_messages_not_recovered(self, client):
        """Empty message list should not be recovered."""
        result = client.should_recover_conversation([], had_template_opener=False)
        assert result is False

    def test_html_stripped_in_recovery_check(self, client):
        """HTML tags should be stripped when counting characters."""
        messages = [
            {"author": {"type": "user"}, "body": "<p>" + "A" * 100 + "</p>"},
        ]
        result = client.should_recover_conversation(messages, had_template_opener=False)
        # After stripping HTML, should still have 100 chars
        assert result is True


class TestRecoveryCandidatesTracking:
    """Tests for recovery_candidates parameter in fetch_quality_conversations_async."""

    @pytest.fixture
    def client(self):
        """Create IntercomClient instance for testing."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            from src.intercom_client import IntercomClient
            return IntercomClient()

    @pytest.mark.asyncio
    async def test_short_body_added_to_recovery_candidates(self, client):
        """Conversations filtered for 'body too short' are tracked for recovery."""
        recovery_candidates = []

        # Mock the search to return a conversation with short body
        short_conv = {
            "id": "123",
            "created_at": 1704067200,
            "source": {
                "delivered_as": "customer_initiated",
                "author": {"type": "user"},
                "body": "Hi",  # Too short
            },
        }

        with patch.object(
            client,
            "search_by_date_range_async",
            return_value=self._async_gen([short_conv]),
        ):
            async for _ in client.fetch_quality_conversations_async(
                recovery_candidates=recovery_candidates
            ):
                pass

        assert len(recovery_candidates) == 1
        assert recovery_candidates[0][2] is False  # had_template=False

    @pytest.mark.asyncio
    async def test_template_message_added_to_recovery_candidates(self, client):
        """Conversations filtered for 'template message' are tracked with flag."""
        recovery_candidates = []

        template_conv = {
            "id": "456",
            "created_at": 1704067200,
            "source": {
                "delivered_as": "customer_initiated",
                "author": {"type": "user"},
                "body": "i have a product question or feedback",
            },
        }

        with patch.object(
            client,
            "search_by_date_range_async",
            return_value=self._async_gen([template_conv]),
        ):
            async for _ in client.fetch_quality_conversations_async(
                recovery_candidates=recovery_candidates
            ):
                pass

        assert len(recovery_candidates) == 1
        assert recovery_candidates[0][2] is True  # had_template=True

    @pytest.mark.asyncio
    async def test_admin_initiated_not_tracked_for_recovery(self, client):
        """Admin-initiated conversations are not tracked for recovery."""
        recovery_candidates = []

        admin_conv = {
            "id": "789",
            "created_at": 1704067200,
            "source": {
                "delivered_as": "admin_initiated",
                "author": {"type": "admin"},
                "body": "Hi there!",
            },
        }

        with patch.object(
            client,
            "search_by_date_range_async",
            return_value=self._async_gen([admin_conv]),
        ):
            async for _ in client.fetch_quality_conversations_async(
                recovery_candidates=recovery_candidates
            ):
                pass

        assert len(recovery_candidates) == 0

    async def _async_gen(self, items):
        """Helper to create async generator from list."""
        for item in items:
            yield item


# =============================================================================
# Issue #160: Context Provider Tests
# =============================================================================


class TestContextProvider:
    """Tests for ContextProvider class."""

    def test_timeout_returns_empty_string(self):
        """Provider returns empty string on timeout."""
        from src.context_provider import ContextProvider

        async def slow_search(query):
            await asyncio.sleep(2)  # Longer than timeout
            return "should not return this"

        provider = ContextProvider(timeout_ms=100)  # Very short timeout

        async def run_test():
            with patch.object(provider, "_search_help_articles", slow_search):
                result = await provider.get_help_article_context("test query")
                return result

        result = asyncio.run(run_test())
        assert result == ""

    def test_exception_returns_empty_string(self):
        """Provider returns empty string on exception."""
        from src.context_provider import ContextProvider

        async def failing_search(query):
            raise ValueError("Search failed")

        provider = ContextProvider()

        async def run_test():
            with patch.object(provider, "_search_help_articles", failing_search):
                result = await provider.get_help_article_context("test query")
                return result

        result = asyncio.run(run_test())
        assert result == ""

    def test_get_all_context_runs_parallel(self):
        """get_all_context runs both searches in parallel."""
        from src.context_provider import ContextProvider

        call_times = []

        async def mock_help_search(query):
            call_times.append(("help", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)
            return "help context"

        async def mock_shortcut_search(query):
            call_times.append(("shortcut", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)
            return "shortcut context"

        provider = ContextProvider()

        async def run_test():
            with patch.object(provider, "_search_help_articles", mock_help_search):
                with patch.object(provider, "_search_shortcut_stories", mock_shortcut_search):
                    start = asyncio.get_event_loop().time()
                    help_ctx, shortcut_ctx = await provider.get_all_context("test")
                    elapsed = asyncio.get_event_loop().time() - start
                    return help_ctx, shortcut_ctx, elapsed

        help_ctx, shortcut_ctx, elapsed = asyncio.run(run_test())

        assert help_ctx == "help context"
        assert shortcut_ctx == "shortcut context"
        # If run in parallel, total time should be ~0.1s, not ~0.2s
        assert elapsed < 0.15, "Searches should run in parallel"

    def test_stub_implementations_return_empty(self):
        """Stub implementations return empty strings."""
        from src.context_provider import ContextProvider

        provider = ContextProvider()

        async def run_test():
            help_ctx = await provider._search_help_articles("test")
            shortcut_ctx = await provider._search_shortcut_stories("test")
            return help_ctx, shortcut_ctx

        help_ctx, shortcut_ctx = asyncio.run(run_test())
        assert help_ctx == ""
        assert shortcut_ctx == ""

    def test_get_context_provider_singleton(self):
        """get_context_provider returns singleton instance."""
        from src.context_provider import get_context_provider

        provider1 = get_context_provider()
        provider2 = get_context_provider()
        assert provider1 is provider2


class TestContextProviderIntegration:
    """Integration tests for context provider in classification pipeline."""

    @pytest.mark.asyncio
    async def test_classify_stage2_async_uses_context(self):
        """classify_stage2_async should call context provider."""
        from src.classification_pipeline import classify_stage2_async

        # Mock the context provider
        mock_provider = Mock()
        mock_provider.get_all_context = AsyncMock(
            return_value=("help article info", "shortcut story info")
        )

        # Mock the OpenAI client
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content='{"conversation_type": "product_issue", "confidence": "high"}'))
        ]

        with patch("src.classification_pipeline.get_context_provider", return_value=mock_provider):
            with patch("src.classification_pipeline.async_client") as mock_client:
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

                result = await classify_stage2_async(
                    customer_message="Test message",
                    support_messages=["Support response"],
                    stage1_type="general_inquiry",
                    semaphore=asyncio.Semaphore(1),
                )

        # Verify context provider was called
        mock_provider.get_all_context.assert_called_once_with("Test message")


# =============================================================================
# Test Constants
# =============================================================================


class TestConstants:
    """Tests for configuration constants."""

    def test_recovery_thresholds_defined(self):
        """Recovery threshold constants should be defined."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            from src.intercom_client import IntercomClient

            assert hasattr(IntercomClient, "RECOVERY_MIN_MESSAGE_CHARS")
            assert hasattr(IntercomClient, "RECOVERY_MIN_TOTAL_CHARS")
            assert IntercomClient.RECOVERY_MIN_MESSAGE_CHARS == 100
            assert IntercomClient.RECOVERY_MIN_TOTAL_CHARS == 200

    def test_context_timeout_defined(self):
        """Context timeout constant should be defined."""
        from src.context_provider import CONTEXT_TIMEOUT_MS

        assert CONTEXT_TIMEOUT_MS == 500

    def test_actionable_keywords_defined(self):
        """Actionable keywords set should be defined."""
        from src.api.routers.pipeline import ACTIONABLE_KEYWORDS

        assert "oauth" in ACTIONABLE_KEYWORDS
        assert "token" in ACTIONABLE_KEYWORDS
        assert "api" in ACTIONABLE_KEYWORDS
        assert "integration" in ACTIONABLE_KEYWORDS
