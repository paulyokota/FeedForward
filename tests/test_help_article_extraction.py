"""
Tests for help article extraction (Phase 4a).

Tests the HelpArticleExtractor's ability to:
1. Extract article URLs from conversation messages
2. Fetch article metadata from Intercom API
3. Format article context for prompt injection
"""

import pytest
from unittest.mock import Mock, patch

from src.help_article_extractor import HelpArticle, HelpArticleExtractor


# Test fixtures

@pytest.fixture
def extractor():
    """Create a HelpArticleExtractor instance with mocked API."""
    with patch.dict('os.environ', {'INTERCOM_ACCESS_TOKEN': 'test_token'}):
        return HelpArticleExtractor()


@pytest.fixture
def sample_conversation_with_article():
    """Sample conversation that references a help article."""
    return {
        "id": "12345",
        "source": {
            "type": "conversation",
            "body": "I'm trying to connect Instagram but getting an error. I read this article https://help.tailwindapp.com/en/articles/123456 but it didn't help."
        },
        "conversation_parts": {
            "conversation_parts": [
                {
                    "part_type": "comment",
                    "body": "Let me help with that. Did you check https://help.tailwindapp.com/en/articles/789012 as well?"
                }
            ]
        }
    }


@pytest.fixture
def sample_conversation_without_article():
    """Sample conversation with no article references."""
    return {
        "id": "67890",
        "source": {
            "type": "conversation",
            "body": "My posts aren't scheduling correctly."
        },
        "conversation_parts": {
            "conversation_parts": []
        }
    }


@pytest.fixture
def sample_article_response():
    """Sample article response from Intercom API."""
    return {
        "id": "123456",
        "title": "How to connect Instagram Business accounts",
        "body": "<p>Instagram Business accounts require a linked Facebook Page. Here's how to connect them...</p>",
        "parent_id": "987",
        "tags": ["instagram", "setup"]
    }


# Tests

class TestArticleURLExtraction:
    """Test extraction of article URLs from conversations."""

    def test_extract_article_from_customer_message(self, extractor, sample_conversation_with_article):
        """Should extract article URL from customer's initial message."""
        urls = extractor.extract_article_urls(sample_conversation_with_article)

        assert len(urls) == 2
        assert "https://help.tailwindapp.com/en/articles/123456" in urls
        assert "https://help.tailwindapp.com/en/articles/789012" in urls

    def test_extract_no_articles(self, extractor, sample_conversation_without_article):
        """Should return empty list when no articles referenced."""
        urls = extractor.extract_article_urls(sample_conversation_without_article)

        assert urls == []

    def test_extract_intercom_help_url(self, extractor):
        """Should extract article from intercom.help subdomain."""
        conversation = {
            "id": "test",
            "source": {
                "body": "I found this https://intercom.help/tailwindapp/en/articles/999888 but confused"
            },
            "conversation_parts": {"conversation_parts": []}
        }

        urls = extractor.extract_article_urls(conversation)

        assert len(urls) == 1
        assert "https://help.tailwindapp.com/en/articles/999888" in urls

    def test_extract_intercom_protocol_url(self, extractor):
        """Should extract article from intercom:// protocol links."""
        conversation = {
            "id": "test",
            "source": {
                "body": "Check intercom://article/555666 for details"
            },
            "conversation_parts": {"conversation_parts": []}
        }

        urls = extractor.extract_article_urls(conversation)

        assert len(urls) == 1
        assert "https://help.tailwindapp.com/en/articles/555666" in urls

    def test_no_duplicate_articles(self, extractor):
        """Should deduplicate when same article mentioned multiple times."""
        conversation = {
            "id": "test",
            "source": {
                "body": "https://help.tailwindapp.com/en/articles/123 and https://help.tailwindapp.com/en/articles/123"
            },
            "conversation_parts": {"conversation_parts": []}
        }

        urls = extractor.extract_article_urls(conversation)

        assert len(urls) == 1
        assert "https://help.tailwindapp.com/en/articles/123" in urls


class TestArticleMetadataFetching:
    """Test fetching article metadata from Intercom API."""

    @patch('requests.Session.get')
    def test_fetch_article_metadata_success(self, mock_get, extractor, sample_article_response):
        """Should fetch and parse article metadata from API."""
        mock_response = Mock()
        mock_response.json.return_value = sample_article_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        article = extractor.fetch_article_metadata("https://help.tailwindapp.com/en/articles/123456")

        assert article is not None
        assert article.article_id == "123456"
        assert article.url == "https://help.tailwindapp.com/en/articles/123456"
        assert article.title == "How to connect Instagram Business accounts"
        assert "collection_987" in article.category
        assert article.summary is not None
        assert "Instagram Business accounts require" in article.summary

    @patch('requests.Session.get')
    def test_fetch_article_metadata_failure(self, mock_get, extractor):
        """Should return None when API fetch fails."""
        mock_get.side_effect = Exception("API error")

        article = extractor.fetch_article_metadata("https://help.tailwindapp.com/en/articles/123456")

        assert article is None

    def test_fetch_invalid_url(self, extractor):
        """Should return None for invalid article URLs."""
        article = extractor.fetch_article_metadata("https://example.com/not-an-article")

        assert article is None


class TestSummaryExtraction:
    """Test extraction of article summaries."""

    def test_extract_summary_strips_html(self, extractor):
        """Should strip HTML tags from article body."""
        article_data = {
            "body": "<p>This is a <strong>test</strong> article.</p><p>Second paragraph.</p>"
        }

        summary = extractor._extract_summary(article_data)

        assert "<p>" not in summary
        assert "<strong>" not in summary
        assert "This is a test article" in summary

    def test_extract_summary_truncates_long_text(self, extractor):
        """Should truncate summaries longer than 500 characters."""
        long_text = "A" * 600
        article_data = {"body": f"<p>{long_text}</p>"}

        summary = extractor._extract_summary(article_data)

        assert len(summary) <= 504  # 500 + "..."
        assert summary.endswith("...")

    def test_extract_summary_handles_empty_body(self, extractor):
        """Should return None for articles with no body."""
        article_data = {"body": ""}

        summary = extractor._extract_summary(article_data)

        assert summary is None


class TestPromptFormatting:
    """Test formatting of article context for LLM prompts."""

    def test_format_single_article(self, extractor):
        """Should format single article for prompt injection."""
        articles = [
            HelpArticle(
                article_id="123",
                url="https://help.tailwindapp.com/en/articles/123",
                title="Test Article",
                category="Setup",
                summary="This is a test summary"
            )
        ]

        formatted = extractor.format_for_prompt(articles)

        assert "The user referenced the following help articles:" in formatted
        assert "Title: Test Article" in formatted
        assert "Category: Setup" in formatted
        assert "Summary: This is a test summary" in formatted
        assert "This provides context about what the user was trying to do" in formatted

    def test_format_multiple_articles(self, extractor):
        """Should format multiple articles with bullets."""
        articles = [
            HelpArticle(article_id="1", url="url1", title="Article 1"),
            HelpArticle(article_id="2", url="url2", title="Article 2")
        ]

        formatted = extractor.format_for_prompt(articles)

        assert formatted.count("- Title:") == 2
        assert "Article 1" in formatted
        assert "Article 2" in formatted

    def test_format_empty_list(self, extractor):
        """Should return empty string when no articles."""
        formatted = extractor.format_for_prompt([])

        assert formatted == ""

    def test_format_article_without_optional_fields(self, extractor):
        """Should handle articles with missing optional fields."""
        articles = [
            HelpArticle(
                article_id="123",
                url="https://help.tailwindapp.com/en/articles/123",
                title=None,  # Missing title
                category=None,  # Missing category
                summary=None  # Missing summary
            )
        ]

        formatted = extractor.format_for_prompt(articles)

        assert "Title: Unknown" in formatted
        assert "Category:" not in formatted  # Should skip if None
        assert "Summary:" not in formatted  # Should skip if None


class TestEndToEndExtraction:
    """Test end-to-end extraction and formatting."""

    @patch('requests.Session.get')
    def test_extract_and_format(self, mock_get, extractor, sample_conversation_with_article, sample_article_response):
        """Should extract URLs, fetch metadata, and format in one step."""
        mock_response = Mock()
        mock_response.json.return_value = sample_article_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        formatted = extractor.extract_and_format(sample_conversation_with_article)

        # Should have fetched both articles (123456 and 789012)
        assert mock_get.call_count == 2

        # Should format for prompt
        assert "The user referenced the following help articles:" in formatted
        assert "How to connect Instagram Business accounts" in formatted

    def test_extract_and_format_no_articles(self, extractor, sample_conversation_without_article):
        """Should return empty string when no articles found."""
        formatted = extractor.extract_and_format(sample_conversation_without_article)

        assert formatted == ""


# Integration test markers
pytestmark = pytest.mark.unit
