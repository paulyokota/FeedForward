"""
Context Provider for Stage 2 Classification (Issue #160).

Provides disambiguation context for Stage 2 classification by searching
help articles and Shortcut stories for relevant information.

Currently stubbed - implementations will be added when integrations are available.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Hard timeout cap for context providers (milliseconds)
# Returns empty string if provider takes longer than this
CONTEXT_TIMEOUT_MS = 500


class ContextProvider:
    """
    Provides disambiguation context for Stage 2 classification.

    Searches help articles and Shortcut stories for relevant context
    that can help disambiguate customer messages.

    All methods return empty string on timeout or failure to ensure
    classification can proceed without context.
    """

    def __init__(self, timeout_ms: int = CONTEXT_TIMEOUT_MS):
        """
        Initialize context provider.

        Args:
            timeout_ms: Timeout in milliseconds for each provider (default 500ms)
        """
        self.timeout_seconds = timeout_ms / 1000

    async def get_all_context(
        self,
        customer_message: str,
    ) -> tuple[str, str]:
        """
        Get all context in parallel for efficiency.

        Issue #160: Runs help article and Shortcut searches concurrently
        to minimize added latency.

        Args:
            customer_message: The customer's message to search against

        Returns:
            Tuple of (help_article_context, shortcut_story_context)
            Both will be empty strings if providers fail or timeout.
        """
        try:
            help_context, shortcut_context = await asyncio.gather(
                self.get_help_article_context(customer_message),
                self.get_shortcut_context(customer_message),
            )
            return help_context, shortcut_context
        except Exception as e:
            logger.warning(f"Context provider gather failed: {e}")
            return "", ""

    async def get_help_article_context(self, customer_message: str) -> str:
        """
        Search help articles for relevant context.

        Args:
            customer_message: The customer's message to search against

        Returns:
            Formatted help article context, or empty string on timeout/failure
        """
        try:
            return await asyncio.wait_for(
                self._search_help_articles(customer_message),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.debug("Help article search timed out")
            return ""
        except Exception as e:
            logger.warning(f"Help article search failed: {e}")
            return ""

    async def get_shortcut_context(self, customer_message: str) -> str:
        """
        Search Shortcut stories for related issues.

        Args:
            customer_message: The customer's message to search against

        Returns:
            Formatted Shortcut story context, or empty string on timeout/failure
        """
        try:
            return await asyncio.wait_for(
                self._search_shortcut_stories(customer_message),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.debug("Shortcut search timed out")
            return ""
        except Exception as e:
            logger.warning(f"Shortcut search failed: {e}")
            return ""

    async def _search_help_articles(self, query: str) -> str:
        """
        Search help articles for relevant context.

        TODO: Implement Intercom help center search when integration is available.
        Possible approaches:
        - Intercom Help Center API (if available)
        - Local corpus search
        - External search service

        Args:
            query: Search query (customer message)

        Returns:
            Formatted context string or empty string
        """
        # Stub implementation - return empty until integration exists
        return ""

    async def _search_shortcut_stories(self, query: str) -> str:
        """
        Search Shortcut stories for related issues.

        TODO: Implement Shortcut API search when integration is available.
        The Shortcut API supports search via:
        - POST /api/v3/search/stories with text query
        - Filtering by workflow state, labels, etc.

        Args:
            query: Search query (customer message)

        Returns:
            Formatted context string or empty string
        """
        # Stub implementation - return empty until integration exists
        return ""


# Singleton instance for convenience
_default_provider: Optional[ContextProvider] = None


def get_context_provider() -> ContextProvider:
    """Get the default context provider instance."""
    global _default_provider
    if _default_provider is None:
        _default_provider = ContextProvider()
    return _default_provider
