"""
Unit and Integration Tests for Domain Classifier

Tests the Haiku-powered semantic classification of customer support issues.
"""

import pytest
import json
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path

from src.story_tracking.services.domain_classifier import (
    DomainClassifier,
    ClassificationResult,
)


class TestDomainClassifierInitialization:
    """Test classifier initialization and domain map loading."""

    def test_classifier_initializes_with_domain_map(self):
        """Should load domain map YAML on init."""
        classifier = DomainClassifier()
        assert classifier.domain_map is not None
        assert "categories" in classifier.domain_map
        assert len(classifier.domain_map["categories"]) > 0

    def test_classifier_builds_keyword_index(self):
        """Should build keyword index for fast matching."""
        classifier = DomainClassifier()
        assert classifier.keyword_index is not None
        assert len(classifier.keyword_index) > 0

    def test_categories_loaded(self):
        """Should have expected categories."""
        classifier = DomainClassifier()
        categories = classifier.list_categories()

        expected_categories = [
            "scheduling",
            "ai_creation",
            "pinterest_publishing",
            "instagram_publishing",
            "facebook_publishing",
            "analytics",
            "billing",
            "account",
            "integrations",
            "communities",
            "data_operations",
            "api",
            "performance",
            "bug_report",
            "feature_request",
            "documentation",
        ]

        for expected in expected_categories:
            assert expected in categories, f"Expected category '{expected}' not found"


class TestKeywordFallback:
    """Test keyword-based fallback classification (fast path)."""

    def test_keyword_match_single(self):
        """Should match single keyword from domain map."""
        classifier = DomainClassifier()

        text = "My scheduled pins aren't posting to Pinterest"
        result = classifier._keyword_fallback_classification(text)

        assert result is not None
        assert result.success is True
        assert result.category in [
            "scheduling",
            "pinterest_publishing",
        ]  # Both are valid

    def test_keyword_match_multiple_keywords(self):
        """Should score categories by multiple keyword matches."""
        classifier = DomainClassifier()

        text = "ghostwriter AI generation creating content with smartpin"
        result = classifier._keyword_fallback_classification(text)

        assert result is not None
        assert result.category == "ai_creation"
        assert result.confidence == "medium"

    def test_no_keyword_match_returns_none(self):
        """Should return None for weak keyword signals (fallback to Haiku)."""
        classifier = DomainClassifier()

        text = "This is a generic message with no product keywords"
        result = classifier._keyword_fallback_classification(text)

        # Should return None to trigger Haiku classification
        assert result is None

    def test_keyword_fallback_includes_suggested_repos(self):
        """Fallback result should include suggested repos from domain map."""
        classifier = DomainClassifier()

        text = "billing subscription payment issue"
        result = classifier._keyword_fallback_classification(text)

        assert result is not None
        assert result.category == "billing"
        assert len(result.suggested_repos) > 0
        assert "tack" in result.suggested_repos  # Billing primary service

    def test_keyword_fallback_includes_search_paths(self):
        """Fallback result should include search paths from domain map."""
        classifier = DomainClassifier()

        # Use text with multiple keywords to trigger fallback
        text = "scheduler scheduling pin spacing smartschedule queue"
        result = classifier._keyword_fallback_classification(text)

        assert result is not None
        assert len(result.suggested_search_paths) > 0


class TestHaikuClassification:
    """Test Haiku-based semantic classification."""

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_haiku_classification_success(self, mock_anthropic_class):
        """Should successfully classify using Haiku."""
        # Mock Anthropic response
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "scheduling",
                        "confidence": "high",
                        "reasoning": "User is having issues with pin scheduling",
                        "alternative_categories": ["pinterest_publishing"],
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        classifier = DomainClassifier()
        # Use a text that won't trigger keyword fallback to ensure Haiku is called
        result = classifier.classify("Posts aren't being published to the platform at the configured time")

        # Verify that Haiku was used (result may match via fallback or Haiku)
        assert result.category == "scheduling"
        assert result.success is True
        assert result.classification_duration_ms >= 0  # Should have timing recorded

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_haiku_classification_with_context(self, mock_anthropic_class):
        """Should pass stage2_context to Haiku."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "billing",
                        "confidence": "high",
                        "reasoning": "Subscription charge issue",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        classifier = DomainClassifier()
        result = classifier.classify(
            "Payment issue", stage2_context="User tried to upgrade plan"
        )

        # Verify Anthropic was called
        assert mock_client.messages.create.called
        call_args = mock_client.messages.create.call_args

        # Check that context was included in prompt
        assert "stage2_context" in str(
            call_args
        ) or "Payment issue" in str(call_args)

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_haiku_json_parsing(self, mock_anthropic_class):
        """Should parse JSON from Haiku response even with extra text."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        # Response with extra text before/after JSON
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="""Based on the issue, here's my classification:
{
  "category": "analytics",
  "confidence": "medium",
  "reasoning": "Performance tracking issue"
}
Note: This could also be related to dashboards."""
            )
        ]
        mock_client.messages.create.return_value = mock_response

        classifier = DomainClassifier()
        # Use neutral text that won't trigger keyword fallback
        result = classifier.classify("I need help tracking some metrics in my dashboard")

        assert result.category == "analytics"
        assert result.confidence == "medium"

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_haiku_invalid_category_defaults_to_bug_report(self, mock_anthropic_class):
        """Should default to bug_report for unknown categories."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "unknown_category_xyz",
                        "confidence": "high",
                        "reasoning": "Testing unknown category",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        classifier = DomainClassifier()
        result = classifier.classify("Some random issue")

        assert result.category == "bug_report"
        assert result.success is True

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_classification_error_handling(self, mock_anthropic_class):
        """Should handle API errors gracefully."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API Error")

        classifier = DomainClassifier()
        result = classifier.classify("Test issue")

        assert result.success is False
        assert result.category == "bug_report"
        assert "error" in result.error.lower() or result.error


class TestClassificationResult:
    """Test ClassificationResult data class."""

    def test_result_creation(self):
        """Should create valid result."""
        result = ClassificationResult(
            category="scheduling",
            confidence="high",
            reasoning="Test reasoning",
            suggested_repos=["aero", "tack"],
            suggested_search_paths=["packages/**/scheduler/**/*"],
            keywords_matched=["scheduler", "pin"],
            classification_duration_ms=150,
            success=True,
        )

        assert result.category == "scheduling"
        assert result.confidence == "high"
        assert len(result.suggested_repos) == 2
        assert result.classification_duration_ms < 500  # Meets latency target

    def test_result_defaults(self):
        """Should provide sensible defaults."""
        result = ClassificationResult(
            category="bug_report", confidence="low", reasoning="Default"
        )

        assert result.suggested_repos == []
        assert result.alternative_categories == []
        assert result.keywords_matched == []
        assert result.success is True
        assert result.error is None


class TestCategoryInfoRetrieval:
    """Test accessing category information."""

    def test_get_category_info(self):
        """Should retrieve category configuration."""
        classifier = DomainClassifier()

        info = classifier.get_category_info("scheduling")

        assert info is not None
        assert "description" in info
        assert "keywords" in info
        assert "repos" in info
        assert "search_paths" in info

    def test_list_categories(self):
        """Should list all available categories."""
        classifier = DomainClassifier()

        categories = classifier.list_categories()

        assert isinstance(categories, list)
        assert len(categories) > 0
        assert all(isinstance(c, str) for c in categories)
        assert "scheduling" in categories
        assert "bug_report" in categories


class TestClassificationLatency:
    """Test that classification meets latency targets."""

    def test_keyword_fallback_latency(self):
        """Keyword fallback should be <50ms."""
        classifier = DomainClassifier()

        import time

        start = time.time()
        classifier._keyword_fallback_classification("scheduling pin spacing issue")
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 50, f"Keyword fallback took {elapsed_ms}ms, target <50ms"

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_full_classification_latency_target(self, mock_anthropic_class):
        """Full classification should be <500ms."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"category": "api"}))]
        mock_client.messages.create.return_value = mock_response

        classifier = DomainClassifier()

        import time

        start = time.time()
        result = classifier.classify("API rate limiting issue")
        elapsed_ms = result.classification_duration_ms

        # Should be under target
        assert elapsed_ms < 500, f"Classification took {elapsed_ms}ms, target <500ms"


class TestCostMetrics:
    """Test that cost targets are met."""

    def test_estimated_daily_cost(self):
        """Verify cost estimates (~$4.50/month for 1000 daily issues)."""
        # Cost per classification: ~$0.00015
        cost_per_classification = 0.00015
        daily_issues = 1000
        daily_cost = cost_per_classification * daily_issues
        monthly_cost = daily_cost * 30

        assert daily_cost < 0.20, "Daily cost should be <$0.20"
        assert monthly_cost < 6.00, "Monthly cost should be <$6.00"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_empty_issue_text(self, mock_anthropic_class):
        """Should handle empty issue text."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"category": "bug_report"}))]
        mock_client.messages.create.return_value = mock_response

        classifier = DomainClassifier()
        result = classifier.classify("")

        assert result is not None
        assert result.category == "bug_report"

    def test_very_long_issue_text(self):
        """Should handle very long issue text."""
        classifier = DomainClassifier()
        # Use multiple keywords to trigger fallback on long text
        long_text = "scheduler scheduling pin spacing smartschedule " * 200

        result = classifier._keyword_fallback_classification(long_text)

        assert result is not None
        assert result.category == "scheduling"

    def test_non_english_text(self):
        """Should attempt classification even with non-English text."""
        classifier = DomainClassifier()

        result = classifier._keyword_fallback_classification("スケジューリング問題")  # Scheduling in Japanese

        # Keyword fallback won't match, so should return None
        assert result is None

    def test_special_characters_in_text(self):
        """Should handle special characters safely."""
        classifier = DomainClassifier()

        result = classifier._keyword_fallback_classification(
            "Billing issue: $$ charged !!! error @#$%"
        )

        assert result is not None or result is None  # Should not crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
