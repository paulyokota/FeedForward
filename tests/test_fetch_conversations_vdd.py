"""
Tests for VDD conversation fetcher.

Tests cover:
- Keyword-based classification logic
- Diversity sampling
- Issue summary extraction
- JSON output format
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add scripts dir to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "codebase-search-vdd"))

pytestmark = pytest.mark.medium

from fetch_conversations import (
    ConversationFetcher,
    FetchedConversation,
    ProductAreaClassification,
    ProductAreaClassifier,
)


@pytest.fixture
def sample_config():
    """Sample config for testing."""
    return {
        "product_areas": [
            {
                "name": "scheduling",
                "keywords": ["calendar", "schedule", "publish", "queue"],
            },
            {
                "name": "analytics",
                "keywords": ["metrics", "insights", "reports", "performance"],
            },
            {
                "name": "integrations",
                "keywords": ["connect", "disconnect", "oauth", "permissions"],
            },
        ]
    }


@pytest.fixture
def classifier(sample_config):
    """Create classifier with sample config."""
    return ProductAreaClassifier(sample_config["product_areas"])


class TestProductAreaClassifier:
    """Test keyword-based classification logic."""

    def test_classify_clear_match(self, classifier):
        """Test classification with clear keyword match."""
        text = "My posts aren't appearing in the schedule calendar"
        result = classifier.classify(text)

        assert result.product_area == "scheduling"
        assert result.confidence >= 0.4  # Threshold for non-uncertain
        assert "calendar" in result.matched_keywords
        assert "schedule" in result.matched_keywords

    def test_classify_multiple_areas(self, classifier):
        """Test classification when multiple areas match."""
        text = "How do I connect my analytics dashboard to see performance insights?"
        result = classifier.classify(text)

        # Should match both analytics (insights, performance) and integrations (connect)
        # Analytics should win with 2/4 = 0.5 confidence
        assert result.product_area == "analytics"
        assert result.confidence >= 0.4

    def test_classify_no_match(self, classifier):
        """Test classification with no keyword matches."""
        text = "I want to cancel my subscription"
        result = classifier.classify(text)

        assert result.product_area == "uncertain"
        assert result.confidence == 0.0
        assert len(result.matched_keywords) == 0

    def test_classify_low_confidence(self, classifier):
        """Test classification with low confidence match."""
        text = "I have a question about the queue feature"
        result = classifier.classify(text)

        # Only one keyword match out of 4
        assert result.confidence < 0.5
        # Should be tagged as uncertain due to low confidence
        assert result.product_area == "uncertain"

    def test_classify_case_insensitive(self, classifier):
        """Test that classification is case-insensitive."""
        text = "My SCHEDULE is broken and the CALENDAR won't load"
        result = classifier.classify(text)

        assert result.product_area == "scheduling"
        assert "calendar" in result.matched_keywords
        assert "schedule" in result.matched_keywords


class TestConversationFetcher:
    """Test conversation fetching and processing."""

    @pytest.fixture
    def mock_intercom_client(self):
        """Mock IntercomClient."""
        client = Mock()
        client.fetch_quality_conversations = Mock()
        return client

    @pytest.fixture
    def fetcher(self, sample_config, tmp_path):
        """Create fetcher with mock client."""
        # Write config to temp file
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(sample_config, f)

        with patch("fetch_conversations.IntercomClient") as mock_client_class:
            fetcher = ConversationFetcher(str(config_path))
            # Replace client with mock
            fetcher.client = Mock()
            return fetcher

    def test_extract_issue_summary_short(self, fetcher):
        """Test issue summary extraction for short text."""
        body = "My pins won't post"
        summary = fetcher.extract_issue_summary(body)

        assert summary == "My pins won't post"
        assert "..." not in summary

    def test_extract_issue_summary_long(self, fetcher):
        """Test issue summary extraction for long text."""
        body = "A" * 400  # Long text
        summary = fetcher.extract_issue_summary(body)

        assert len(summary) <= 305  # 300 + " ..."
        assert summary.endswith(" ...")

    def test_extract_issue_summary_word_boundary(self, fetcher):
        """Test that long summaries break at word boundaries."""
        body = "word " * 100  # Many words
        summary = fetcher.extract_issue_summary(body)

        # Should break at space, not mid-word
        assert summary.endswith(" ...")
        # Space before ellipsis
        assert summary[-4] == " "

    def test_fetch_recent_conversations_diversity(self, fetcher):
        """Test that fetcher samples diverse conversations."""
        # Create mock conversations - all scheduling related
        mock_conversations = []
        for i in range(50):
            mock_conv = Mock()
            mock_conv.id = f"conv_{i}"
            mock_conv.source_body = f"Issue {i} with schedule and calendar"
            mock_conv.created_at = datetime.utcnow() - timedelta(days=i)
            mock_conv.source_url = f"https://example.com/{i}"

            mock_conversations.append((mock_conv, {}))

        fetcher.client.fetch_quality_conversations = Mock(
            return_value=iter(mock_conversations)
        )

        # Fetch small batch
        result = fetcher.fetch_recent_conversations(batch_size=10, days_back=30)

        assert len(result) <= 10
        # All should be classified as scheduling
        assert all(c.product_area in ["scheduling", "uncertain"] for c in result)

    def test_fetch_recent_conversations_output_format(self, fetcher):
        """Test that fetched conversations have correct format."""
        # Create mock conversation with strong keywords
        mock_conv = Mock()
        mock_conv.id = "123"
        mock_conv.source_body = "My calendar and schedule and queue and publish are all broken"
        mock_conv.created_at = datetime.utcnow()
        mock_conv.source_url = "https://example.com/page"

        fetcher.client.fetch_quality_conversations = Mock(
            return_value=iter([(mock_conv, {})])
        )

        result = fetcher.fetch_recent_conversations(batch_size=1, days_back=30)

        assert len(result) == 1
        conv = result[0]

        # Check required fields
        assert conv.conversation_id == "123"
        assert "calendar" in conv.issue_summary
        assert conv.product_area == "scheduling"
        assert conv.classification_confidence >= 0.4
        assert conv.source_url == "https://example.com/page"
        assert isinstance(conv.matched_keywords, list)
        assert len(conv.matched_keywords) > 0


class TestJSONOutput:
    """Test JSON output format."""

    def test_fetched_conversation_serialization(self):
        """Test that FetchedConversation can be serialized to JSON."""
        conv = FetchedConversation(
            conversation_id="123",
            issue_summary="Test issue",
            product_area="scheduling",
            classification_confidence=0.75,
            created_at="2024-01-15T10:00:00",
            source_url="https://example.com",
            matched_keywords=["schedule", "calendar"],
        )

        # Convert to dict
        data = {
            "conversation_id": conv.conversation_id,
            "issue_summary": conv.issue_summary,
            "product_area": conv.product_area,
            "classification_confidence": conv.classification_confidence,
            "created_at": conv.created_at,
            "source_url": conv.source_url,
            "matched_keywords": conv.matched_keywords,
        }

        # Should be JSON serializable
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert parsed["conversation_id"] == "123"
        assert parsed["product_area"] == "scheduling"
        assert parsed["classification_confidence"] == 0.75


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_classifier_empty_keywords(self):
        """Test classifier with empty keyword list."""
        config = {"product_areas": [{"name": "test", "keywords": []}]}
        classifier = ProductAreaClassifier(config["product_areas"])

        result = classifier.classify("some text")

        # Should handle gracefully
        assert result.product_area == "uncertain"
        assert result.confidence == 0.0

    def test_classifier_no_areas(self):
        """Test classifier with no product areas."""
        classifier = ProductAreaClassifier([])

        result = classifier.classify("some text")

        # Should handle gracefully
        assert result.product_area == "uncertain"
        assert result.confidence == 0.0

    def test_extract_summary_empty(self):
        """Test issue summary extraction with empty text."""
        config = {"product_areas": []}
        with patch("fetch_conversations.IntercomClient"):
            fetcher = ConversationFetcher.__new__(ConversationFetcher)
            fetcher.config = config
            fetcher.classifier = ProductAreaClassifier([])

            summary = fetcher.extract_issue_summary("")
            assert summary == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
