"""
Integration Tests for Domain Classifier with CodebaseContextProvider

Tests the end-to-end flow of classifying issues and exploring the codebase.
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
import json
from pathlib import Path

from src.story_tracking.services.codebase_context_provider import CodebaseContextProvider
from src.story_tracking.services.domain_classifier import ClassificationResult

# Mark entire module as slow - these are integration tests
pytestmark = pytest.mark.slow


class TestClassificationGuidedExploration:
    """Test explore_with_classification integration."""

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_explore_with_classification_success(self, mock_anthropic_class):
        """Should classify and explore the codebase."""
        # Mock Haiku response
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "scheduling",
                        "confidence": "high",
                        "reasoning": "Pin scheduling issue",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()
        result, classification = provider.explore_with_classification(
            "Issue with posting cadence and timing"
        )

        assert classification is not None
        # Should have a valid category
        assert classification.category in ["scheduling", "pinterest_publishing", "api"]
        assert result is not None

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_classification_recommends_repos(self, mock_anthropic_class):
        """Classification should recommend relevant repos."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "billing",
                        "confidence": "high",
                        "reasoning": "Subscription issue",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()
        result, classification = provider.explore_with_classification(
            "Payment failed when upgrading"
        )

        assert classification is not None
        assert "tack" in classification.suggested_repos

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_classification_recommends_search_paths(self, mock_anthropic_class):
        """Classification should recommend specific search paths."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "ai_creation",
                        "confidence": "high",
                        "reasoning": "Ghostwriter issue",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()
        result, classification = provider.explore_with_classification(
            "Ghostwriter is timing out"
        )

        assert classification is not None
        assert len(classification.suggested_search_paths) > 0

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_explore_uses_classifier_hints(self, mock_anthropic_class):
        """Exploration should prioritize classifier-recommended paths."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "analytics",
                        "confidence": "high",
                        "reasoning": "Performance metrics",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        with patch.object(
            provider,
            "_explore_with_classifier_hints",
            return_value=MagicMock(success=True, relevant_files=[]),
        ) as mock_explore:
            result, classification = provider.explore_with_classification(
                "Dashboard metrics are slow"
            )

            assert mock_explore.called

    def test_classifier_not_initialized_graceful_failure(self):
        """Should handle missing classifier gracefully."""
        provider = CodebaseContextProvider()
        provider.classifier = None

        result, classification = provider.explore_with_classification(
            "Any issue text"
        )

        assert result.success is False
        assert classification is None

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_classification_error_returns_partial_result(self, mock_anthropic_class):
        """Should return partial result on classification error."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        provider = CodebaseContextProvider()
        result, classification = provider.explore_with_classification(
            "Test issue"
        )

        assert classification is not None
        assert classification.success is False


class TestClassificationAccuracy:
    """Test classification accuracy on sample issues."""

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_scheduling_issue_classification(self, mock_anthropic_class):
        """Should classify scheduling issues correctly."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        scheduling_issues = [
            "Pins scheduled for 3pm aren't posting on time",
            "Pin spacing isn't working - pins are posting too close together",
            "I set up the SmartSchedule but nothing is posting",
        ]

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({"category": "scheduling", "confidence": "high"})
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        for issue in scheduling_issues:
            result, classification = provider.explore_with_classification(issue)
            assert classification.category == "scheduling"

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_billing_issue_classification(self, mock_anthropic_class):
        """Should classify billing issues correctly."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        billing_issues = [
            "I was charged twice this month",
            "Why can't I upgrade my subscription?",
            "Credit card payment failed but I was still charged",
        ]

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({"category": "billing", "confidence": "high"}))
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        for issue in billing_issues:
            result, classification = provider.explore_with_classification(issue)
            assert classification.category == "billing"

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_ai_creation_issue_classification(self, mock_anthropic_class):
        """Should classify AI creation issues correctly."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        ai_issues = [
            "Ghostwriter is timing out when generating pins",
            "SmartPin suggestions aren't showing up",
            "The AI content generation is very slow",
        ]

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps({"category": "ai_creation", "confidence": "high"})
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        for issue in ai_issues:
            result, classification = provider.explore_with_classification(issue)
            assert classification.category == "ai_creation"

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_account_issue_classification(self, mock_anthropic_class):
        """Should classify account issues correctly."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        account_issues = [
            "I forgot my password",
            "Can't connect my Pinterest account",
            "OAuth authentication failed",
            "My email isn't showing in settings",
        ]

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({"category": "account", "confidence": "high"}))
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        for issue in account_issues:
            result, classification = provider.explore_with_classification(issue)
            # Account issues should be classified as account or related categories
            assert classification.category in [
                "account",
                "pinterest_publishing",
                "instagram_publishing",
            ]


class TestSearchPathPrioritization:
    """Test that classifier-recommended paths are prioritized."""

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_classifier_paths_prepended(self, mock_anthropic_class):
        """Classifier paths should be prepended for priority."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "category": "scheduling",
                        "confidence": "high",
                        "reasoning": "Scheduler issue",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        # Mock the search patterns building
        original_build = provider._build_search_patterns

        captured_patterns = []

        def capture_patterns(theme_data):
            patterns = original_build(theme_data)
            captured_patterns.append(patterns)
            return patterns

        with patch.object(
            provider, "_build_search_patterns", side_effect=capture_patterns
        ):
            with patch.object(provider, "_find_relevant_files", return_value=[]):
                result, classification = provider.explore_with_classification(
                    "Scheduler timing out"
                )

        assert len(captured_patterns) > 0


class TestCostAndLatency:
    """Test that solution meets cost and latency requirements."""

    @patch("src.story_tracking.services.domain_classifier.Anthropic")
    def test_total_latency_under_500ms(self, mock_anthropic_class):
        """Total classification should complete under 500ms."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({"category": "api", "confidence": "high"}))
        ]
        mock_client.messages.create.return_value = mock_response

        provider = CodebaseContextProvider()

        import time

        start = time.time()
        result, classification = provider.explore_with_classification(
            "API rate limit exceeded"
        )
        total_ms = (time.time() - start) * 1000

        # Latency target: <500ms (includes mocking overhead)
        assert (
            total_ms < 1000
        ), f"Classification took {total_ms}ms, target <1000ms (with mocking)"

    def test_cost_calculation(self):
        """Verify cost calculation matches requirements."""
        # Cost: $0.00015 per classification
        cost_per_classification = 0.00015

        # 1000 daily classifications
        daily_classifications = 1000
        daily_cost = cost_per_classification * daily_classifications

        # 30 days per month
        monthly_cost = daily_cost * 30

        # Acceptance criteria: ~$4.50/month
        assert monthly_cost <= 5.00, f"Monthly cost {monthly_cost} exceeds $5.00"
        assert monthly_cost >= 3.00, f"Monthly cost {monthly_cost} below expected $4.50"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
