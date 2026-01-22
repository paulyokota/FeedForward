"""
Tests for theme quality gates (Issue #104).

Tests the quality gate validation for theme extraction.
"""

import pytest
from src.theme_quality import (
    check_theme_quality,
    filter_themes_by_quality,
    QualityCheckResult,
    QUALITY_THRESHOLD,
    CONFIDENCE_SCORES,
    VOCABULARY_MATCH_BONUS,
    FILTERED_SIGNATURES,
)


class TestCheckThemeQuality:
    """Unit tests for check_theme_quality function."""

    def test_high_confidence_vocabulary_match_passes(self):
        """Vocabulary match + high confidence = highest quality score."""
        result = check_theme_quality(
            issue_signature="pinterest_duplicate_pins",
            matched_existing=True,
            match_confidence="high",
        )
        assert result.passed is True
        assert result.quality_score == 1.0  # Capped at 1.0
        assert result.reason is None

    def test_medium_confidence_vocabulary_match_passes(self):
        """Vocabulary match + medium confidence passes."""
        result = check_theme_quality(
            issue_signature="csv_import_encoding_error",
            matched_existing=True,
            match_confidence="medium",
        )
        assert result.passed is True
        expected_score = CONFIDENCE_SCORES["medium"] + VOCABULARY_MATCH_BONUS
        assert result.quality_score == expected_score
        assert result.reason is None

    def test_low_confidence_vocabulary_match_passes(self):
        """Vocabulary match + low confidence still passes (above threshold)."""
        result = check_theme_quality(
            issue_signature="analytics_stats_accuracy",
            matched_existing=True,
            match_confidence="low",
        )
        # 0.2 + 0.2 = 0.4, which is above 0.3 threshold
        expected_score = CONFIDENCE_SCORES["low"] + VOCABULARY_MATCH_BONUS
        assert result.passed is True
        assert result.quality_score == expected_score

    def test_high_confidence_new_theme_passes(self):
        """New theme (not in vocabulary) + high confidence passes."""
        result = check_theme_quality(
            issue_signature="new_feature_specific_error",
            matched_existing=False,
            match_confidence="high",
        )
        assert result.passed is True
        assert result.quality_score == CONFIDENCE_SCORES["high"]

    def test_medium_confidence_new_theme_passes(self):
        """New theme + medium confidence passes."""
        result = check_theme_quality(
            issue_signature="smartschedule_timezone_mismatch",
            matched_existing=False,
            match_confidence="medium",
        )
        assert result.passed is True
        assert result.quality_score == CONFIDENCE_SCORES["medium"]

    def test_low_confidence_new_theme_fails(self):
        """New theme + low confidence fails (below threshold)."""
        result = check_theme_quality(
            issue_signature="vague_issue_description",
            matched_existing=False,
            match_confidence="low",
        )
        # 0.2 is below 0.3 threshold
        assert result.passed is False
        assert result.quality_score == CONFIDENCE_SCORES["low"]
        assert "Below threshold" in result.reason
        assert "not in vocabulary" in result.reason

    def test_filtered_signature_unclassified_fails(self):
        """Blocked signature 'unclassified_needs_review' always fails."""
        result = check_theme_quality(
            issue_signature="unclassified_needs_review",
            matched_existing=True,  # Even if matched
            match_confidence="high",  # Even if high confidence
        )
        assert result.passed is False
        assert result.quality_score == 0.0
        assert "Filtered signature" in result.reason

    def test_filtered_signature_unknown_issue_fails(self):
        """Blocked signature 'unknown_issue' always fails."""
        result = check_theme_quality(
            issue_signature="unknown_issue",
            matched_existing=False,
            match_confidence="high",
        )
        assert result.passed is False
        assert result.quality_score == 0.0

    def test_filtered_signature_other_issue_fails(self):
        """Blocked signature 'other_issue' always fails."""
        result = check_theme_quality(
            issue_signature="other_issue",
            matched_existing=True,
            match_confidence="medium",
        )
        assert result.passed is False
        assert result.quality_score == 0.0

    def test_quality_details_included(self):
        """Quality check result includes detailed breakdown."""
        result = check_theme_quality(
            issue_signature="specific_error_code",
            matched_existing=True,
            match_confidence="medium",
        )
        assert result.details is not None
        assert "confidence" in result.details
        assert "vocabulary_match" in result.details
        assert result.details["vocabulary_match"] is True

    def test_custom_threshold(self):
        """Can use custom threshold for filtering."""
        # With default threshold (0.3), this would pass
        result_default = check_theme_quality(
            issue_signature="new_theme",
            matched_existing=False,
            match_confidence="medium",  # Score: 0.6
        )
        assert result_default.passed is True

        # With stricter threshold (0.8), same theme fails
        result_strict = check_theme_quality(
            issue_signature="new_theme",
            matched_existing=False,
            match_confidence="medium",
            threshold=0.8,
        )
        assert result_strict.passed is False

    def test_unknown_confidence_treated_as_zero(self):
        """Unknown confidence level treated as 0."""
        result = check_theme_quality(
            issue_signature="some_theme",
            matched_existing=False,
            match_confidence="unknown_level",
        )
        assert result.quality_score == 0.0
        assert result.passed is False


class TestFilterThemesByQuality:
    """Tests for batch filtering of themes."""

    def _make_mock_theme(self, signature, matched, confidence):
        """Create a mock theme object for testing."""
        class MockTheme:
            def __init__(self):
                self.issue_signature = signature
                self.matched_existing = matched
                self.match_confidence = confidence
                self.conversation_id = "test_conv_123"
        return MockTheme()

    def test_all_themes_pass(self):
        """All high-quality themes pass filter."""
        themes = [
            self._make_mock_theme("good_theme_1", True, "high"),
            self._make_mock_theme("good_theme_2", True, "medium"),
            self._make_mock_theme("good_theme_3", False, "high"),
        ]
        passed, filtered, warnings = filter_themes_by_quality(themes)
        assert len(passed) == 3
        assert len(filtered) == 0
        assert len(warnings) == 0

    def test_some_themes_filtered(self):
        """Mix of passing and failing themes."""
        themes = [
            self._make_mock_theme("high_quality", True, "high"),
            self._make_mock_theme("low_quality", False, "low"),
            self._make_mock_theme("unclassified_needs_review", True, "high"),
        ]
        passed, filtered, warnings = filter_themes_by_quality(themes)
        assert len(passed) == 1
        assert len(filtered) == 2
        assert len(warnings) == 2
        assert passed[0].issue_signature == "high_quality"

    def test_all_themes_filtered(self):
        """All themes fail quality gates."""
        themes = [
            self._make_mock_theme("unclassified_needs_review", False, "low"),
            self._make_mock_theme("unknown_issue", False, "low"),
        ]
        passed, filtered, warnings = filter_themes_by_quality(themes)
        assert len(passed) == 0
        assert len(filtered) == 2
        assert len(warnings) == 2

    def test_empty_theme_list(self):
        """Empty input returns empty output."""
        passed, filtered, warnings = filter_themes_by_quality([])
        assert len(passed) == 0
        assert len(filtered) == 0
        assert len(warnings) == 0

    def test_custom_threshold_applied(self):
        """Custom threshold affects filtering."""
        themes = [
            self._make_mock_theme("theme_1", False, "medium"),  # Score: 0.6
            self._make_mock_theme("theme_2", True, "low"),      # Score: 0.4
        ]
        # With strict threshold, only vocabulary match passes
        passed, filtered, _ = filter_themes_by_quality(themes, threshold=0.5)
        assert len(passed) == 1
        assert passed[0].issue_signature == "theme_1"

    def test_warnings_include_reason(self):
        """Warnings include the filtering reason."""
        themes = [
            self._make_mock_theme("bad_theme", False, "low"),
        ]
        _, _, warnings = filter_themes_by_quality(themes)
        assert len(warnings) == 1
        assert "bad_theme" in warnings[0]
        assert "filtered" in warnings[0].lower()


class TestQualityConstants:
    """Tests for quality gate constants."""

    def test_confidence_scores_defined(self):
        """All confidence levels have scores."""
        assert "high" in CONFIDENCE_SCORES
        assert "medium" in CONFIDENCE_SCORES
        assert "low" in CONFIDENCE_SCORES

    def test_confidence_scores_ordered(self):
        """High > medium > low."""
        assert CONFIDENCE_SCORES["high"] > CONFIDENCE_SCORES["medium"]
        assert CONFIDENCE_SCORES["medium"] > CONFIDENCE_SCORES["low"]

    def test_threshold_reasonable(self):
        """Default threshold allows vocabulary matches with low confidence."""
        # vocab match + low = 0.2 + 0.2 = 0.4 should pass 0.3 threshold
        vocab_low_score = CONFIDENCE_SCORES["low"] + VOCABULARY_MATCH_BONUS
        assert vocab_low_score > QUALITY_THRESHOLD

    def test_filtered_signatures_include_unclassified(self):
        """Unclassified signatures are in blocked list."""
        assert "unclassified_needs_review" in FILTERED_SIGNATURES
        assert "unknown_issue" in FILTERED_SIGNATURES
