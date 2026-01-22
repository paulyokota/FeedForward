"""
Signature specificity validation tests.

Tests the validate_signature_specificity() function and SAME_FIX test guidance.
Ensures signatures are specific enough for one code change to fix all instances.

Owner: Kai (Prompt Engineering)
Run: pytest tests/test_theme_extractor_specificity.py -v
"""

import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from theme_extractor import validate_signature_specificity


class TestValidateSignatureSpecificity:
    """Tests for validate_signature_specificity() function."""

    # ==========================================================================
    # Broad signatures that SHOULD FAIL validation
    # ==========================================================================

    def test_broad_publishing_failure_rejected(self):
        """pinterest_publishing_failure is too broad - fails SAME_FIX test."""
        is_valid, suggestion = validate_signature_specificity("pinterest_publishing_failure")
        assert is_valid is False
        assert suggestion is not None
        assert "specific_symptom" in suggestion

    def test_broad_scheduling_issue_rejected(self):
        """scheduling_issue is too broad - fails SAME_FIX test."""
        is_valid, suggestion = validate_signature_specificity("scheduling_issue")
        assert is_valid is False
        assert suggestion is not None

    def test_broad_api_error_rejected(self):
        """api_error is too broad without specific qualifier."""
        is_valid, suggestion = validate_signature_specificity("api_error")
        assert is_valid is False

    def test_broad_oauth_problem_rejected(self):
        """oauth_problem is too broad without specific qualifier."""
        is_valid, suggestion = validate_signature_specificity("oauth_problem")
        assert is_valid is False

    def test_broad_general_failure_rejected(self):
        """general_failure should be rejected."""
        is_valid, suggestion = validate_signature_specificity("general_failure")
        assert is_valid is False

    def test_broad_account_issue_rejected(self):
        """account_issue is too broad."""
        is_valid, suggestion = validate_signature_specificity("account_issue")
        assert is_valid is False

    # ==========================================================================
    # Specific signatures that SHOULD PASS validation
    # ==========================================================================

    def test_specific_duplicate_pins_accepted(self):
        """pinterest_duplicate_pins is specific - passes SAME_FIX test."""
        is_valid, suggestion = validate_signature_specificity("pinterest_duplicate_pins")
        assert is_valid is True
        assert suggestion is None

    def test_specific_missing_pins_accepted(self):
        """pinterest_missing_pins is specific - passes SAME_FIX test."""
        is_valid, suggestion = validate_signature_specificity("pinterest_missing_pins")
        assert is_valid is True
        assert suggestion is None

    def test_specific_timeout_error_accepted(self):
        """ghostwriter_timeout_error has specific qualifier - passes."""
        is_valid, suggestion = validate_signature_specificity("ghostwriter_timeout_error")
        assert is_valid is True
        assert suggestion is None

    def test_specific_permission_denied_accepted(self):
        """pinterest_board_permission_denied is specific - passes."""
        is_valid, suggestion = validate_signature_specificity("pinterest_board_permission_denied")
        assert is_valid is True
        assert suggestion is None

    def test_specific_encoding_error_accepted(self):
        """csv_import_encoding_error is specific - passes."""
        is_valid, suggestion = validate_signature_specificity("csv_import_encoding_error")
        assert is_valid is True
        assert suggestion is None

    def test_specific_sync_failure_accepted(self):
        """ghostwriter_sync_failure has specific qualifier - passes."""
        is_valid, suggestion = validate_signature_specificity("ghostwriter_sync_failure")
        assert is_valid is True
        assert suggestion is None

    def test_specific_oauth_failure_accepted(self):
        """instagram_oauth_failure has specific qualifier - passes."""
        is_valid, suggestion = validate_signature_specificity("instagram_oauth_failure")
        assert is_valid is True
        assert suggestion is None

    def test_specific_connection_failure_accepted(self):
        """pinterest_connection_failure has specific qualifier - passes."""
        is_valid, suggestion = validate_signature_specificity("pinterest_connection_failure")
        assert is_valid is True
        assert suggestion is None

    def test_specific_video_upload_failure_accepted(self):
        """pinterest_video_upload_failure has specific qualifier - passes."""
        is_valid, suggestion = validate_signature_specificity("pinterest_video_upload_failure")
        assert is_valid is True
        assert suggestion is None

    def test_specific_image_loading_failure_accepted(self):
        """create_image_loading_failure has specific qualifier - passes."""
        is_valid, suggestion = validate_signature_specificity("create_image_loading_failure")
        assert is_valid is True
        assert suggestion is None

    # ==========================================================================
    # Signatures without broad suffixes should pass
    # ==========================================================================

    def test_cancellation_request_accepted(self):
        """billing_cancellation_request has no broad suffix - passes."""
        is_valid, suggestion = validate_signature_specificity("billing_cancellation_request")
        assert is_valid is True
        assert suggestion is None

    def test_feature_question_accepted(self):
        """scheduling_feature_question has no broad suffix - passes."""
        is_valid, suggestion = validate_signature_specificity("scheduling_feature_question")
        assert is_valid is True
        assert suggestion is None

    def test_dashboard_loading_accepted(self):
        """dashboard_loading has no broad suffix - passes."""
        is_valid, suggestion = validate_signature_specificity("dashboard_loading")
        assert is_valid is True
        assert suggestion is None

    # ==========================================================================
    # Edge cases
    # ==========================================================================

    def test_empty_signature_accepted(self):
        """Empty signature passes (no broad suffix)."""
        is_valid, suggestion = validate_signature_specificity("")
        assert is_valid is True

    def test_single_word_failure_passes(self):
        """Just 'failure' passes - the validation targets compound signatures
        like 'pinterest_publishing_failure' not single words."""
        is_valid, suggestion = validate_signature_specificity("failure")
        # Single word 'failure' ends with '_failure' suffix technically,
        # but has no base to suggest improvements for - this is an edge case
        # The function is designed to catch "platform_broad_failure" patterns
        assert is_valid is True

    def test_symptoms_parameter_is_optional(self):
        """symptoms parameter is optional and doesn't affect validation."""
        is_valid, _ = validate_signature_specificity(
            "pinterest_publishing_failure",
            symptoms=["pins not posting", "stuck in queue"]
        )
        assert is_valid is False

        is_valid, _ = validate_signature_specificity(
            "pinterest_duplicate_pins",
            symptoms=["pins appearing twice"]
        )
        assert is_valid is True


class TestSignatureSpecificitySuggestions:
    """Tests for suggestion quality in validation."""

    def test_suggestion_contains_base_signature(self):
        """Suggestion should help user create more specific signature."""
        _, suggestion = validate_signature_specificity("pinterest_publishing_failure")
        assert suggestion is not None
        assert "pinterest_publishing" in suggestion

    def test_suggestion_indicates_symptom_needed(self):
        """Suggestion should indicate a symptom is needed."""
        _, suggestion = validate_signature_specificity("scheduling_issue")
        assert suggestion is not None
        assert "specific_symptom" in suggestion.lower() or "scheduling" in suggestion


class TestSameFIXTestConcepts:
    """
    Conceptual tests for the SAME_FIX test principle.

    These test the reasoning behind the validation rules.
    """

    def test_different_symptoms_need_different_signatures(self):
        """
        Validates the core SAME_FIX principle:
        Different symptoms require different fixes, so need different signatures.
        """
        # These represent DIFFERENT issues that would need different fixes
        duplicate_symptom = "pinterest_duplicate_pins"  # Fix: idempotency
        missing_symptom = "pinterest_missing_pins"      # Fix: data sync
        timeout_symptom = "pinterest_upload_timeout_error"  # Fix: retry logic

        # All specific signatures should pass
        assert validate_signature_specificity(duplicate_symptom)[0] is True
        assert validate_signature_specificity(missing_symptom)[0] is True
        assert validate_signature_specificity(timeout_symptom)[0] is True

        # A broad signature grouping all three should fail
        broad_signature = "pinterest_publishing_failure"
        assert validate_signature_specificity(broad_signature)[0] is False

    def test_one_code_change_principle(self):
        """
        If one code change fixes ALL instances, signature is specific enough.
        """
        # These all have specific patterns - one fix could address each
        specific_signatures = [
            "csv_import_encoding_error",       # Fix: encoding handling
            "ghostwriter_timeout_error",       # Fix: timeout configuration
            "pinterest_board_permission_denied",  # Fix: permission check
            "instagram_oauth_multi_account",   # Fix: account selection
        ]

        for sig in specific_signatures:
            is_valid, _ = validate_signature_specificity(sig)
            assert is_valid is True, f"Expected {sig} to be valid"


class TestRealWorldSignatures:
    """Tests using actual signatures from the theme vocabulary."""

    def test_vocabulary_good_examples_pass(self):
        """Signatures from vocabulary good_examples should pass."""
        good_signatures = [
            "billing_cancellation_request",
            "csv_import_encoding_error",
            "pinterest_board_permission_denied",
            "ghostwriter_timeout_error",
        ]

        for sig in good_signatures:
            is_valid, suggestion = validate_signature_specificity(sig)
            assert is_valid is True, f"Expected {sig} to pass, got suggestion: {suggestion}"

    def test_common_broad_patterns_rejected(self):
        """Common overly-broad patterns should be rejected."""
        broad_signatures = [
            "api_failure",
            "system_error",
            "data_issue",
            "sync_problem",
            "auth_failure",
        ]

        for sig in broad_signatures:
            is_valid, _ = validate_signature_specificity(sig)
            assert is_valid is False, f"Expected {sig} to be rejected as too broad"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
