"""
Tests for evidence validation - ensuring stories have actionable evidence.

This prevents the issue where stories are created with placeholder text like:
"This theme was identified during historical backfill. Sample conversations
were not captured during batch processing."
"""

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from evidence_validator import (
    validate_samples,
    validate_sample,
    build_evidence_report,
    EvidenceQuality,
    REQUIRED_FIELDS,
    RECOMMENDED_FIELDS,
)


class TestValidateSamples:
    """Test the main validation function."""

    def test_valid_samples_pass(self):
        """Samples with required fields should pass validation."""
        samples = [
            {
                "id": "123",
                "excerpt": "I'm having trouble connecting my Instagram account to Tailwind",
                "email": "user@example.com",
                "intercom_url": "https://app.intercom.com/...",
            },
        ]
        result = validate_samples(samples)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_empty_samples_fail(self):
        """Empty samples list should fail validation."""
        result = validate_samples([])
        assert not result.is_valid
        assert "No samples provided" in result.errors

    def test_missing_id_fails(self):
        """Samples missing 'id' should fail validation."""
        samples = [
            {"excerpt": "Some conversation text that's long enough"},
        ]
        result = validate_samples(samples)
        assert not result.is_valid
        assert any("id" in e for e in result.errors)

    def test_missing_excerpt_fails(self):
        """Samples missing 'excerpt' should fail validation."""
        samples = [
            {"id": "123"},
        ]
        result = validate_samples(samples)
        assert not result.is_valid
        assert any("excerpt" in e for e in result.errors)

    def test_placeholder_excerpt_fails(self):
        """Samples with placeholder excerpts should fail validation."""
        samples = [
            {
                "id": "123",
                "excerpt": "Note: This theme was identified during historical backfill. "
                          "Sample conversations were not captured during batch processing.",
            },
        ]
        result = validate_samples(samples)
        assert not result.is_valid
        assert any("placeholder" in e.lower() for e in result.errors)

    def test_missing_email_warns(self):
        """Missing email should warn but not fail."""
        samples = [
            {
                "id": "123",
                "excerpt": "I need help with my billing question about monthly payments",
            },
        ]
        result = validate_samples(samples)
        assert result.is_valid  # Still valid
        assert any("email" in w for w in result.warnings)

    def test_missing_intercom_url_warns(self):
        """Missing intercom_url should warn but not fail."""
        samples = [
            {
                "id": "123",
                "excerpt": "The scheduler is not working properly for my Pinterest pins",
                "email": "user@example.com",
            },
        ]
        result = validate_samples(samples)
        assert result.is_valid  # Still valid
        assert any("intercom_url" in w for w in result.warnings)

    def test_coverage_calculation(self):
        """Should correctly calculate field coverage percentages."""
        samples = [
            {"id": "1", "excerpt": "text 1", "email": "a@b.com"},
            {"id": "2", "excerpt": "text 2"},  # No email
        ]
        result = validate_samples(samples)

        assert result.coverage["id"] == 100.0
        assert result.coverage["excerpt"] == 100.0
        assert result.coverage["email"] == 50.0

    def test_multiple_samples(self):
        """Should handle multiple samples correctly."""
        samples = [
            {"id": "1", "excerpt": "First conversation about scheduling issues"},
            {"id": "2", "excerpt": "Second conversation about the same problem"},
            {"id": "3", "excerpt": "Third related conversation from another user"},
        ]
        result = validate_samples(samples)
        assert result.is_valid
        assert result.sample_count == 3


class TestValidateSample:
    """Test single sample validation."""

    def test_valid_sample(self):
        """Valid sample should pass."""
        sample = {
            "id": "123",
            "excerpt": "I need help with connecting my Instagram account",
        }
        is_valid, issues = validate_sample(sample)
        assert is_valid
        assert len(issues) == 0

    def test_missing_required_field(self):
        """Missing required field should be detected."""
        sample = {"excerpt": "Some text"}
        is_valid, issues = validate_sample(sample)
        assert not is_valid
        assert any("id" in i for i in issues)

    def test_short_excerpt(self):
        """Short excerpts should be flagged."""
        sample = {"id": "123", "excerpt": "Help"}
        is_valid, issues = validate_sample(sample)
        assert not is_valid
        assert any("too short" in i for i in issues)


class TestEvidenceQuality:
    """Test EvidenceQuality dataclass."""

    def test_str_representation(self):
        """Should have readable string representation."""
        quality = EvidenceQuality(
            is_valid=True,
            sample_count=5,
            errors=[],
            warnings=["email only 60% coverage"],
            coverage={"id": 100, "email": 60},
        )
        s = str(quality)
        assert "VALID" in s
        assert "5 samples" in s

    def test_invalid_representation(self):
        """Invalid quality should show INVALID."""
        quality = EvidenceQuality(
            is_valid=False,
            sample_count=2,
            errors=["Missing required field: id"],
        )
        s = str(quality)
        assert "INVALID" in s
        assert "Missing required field" in s


class TestBuildEvidenceReport:
    """Test the evidence report builder."""

    def test_report_contains_coverage(self):
        """Report should show field coverage."""
        samples = [
            {"id": "1", "excerpt": "text", "email": "a@b.com"},
        ]
        report = build_evidence_report(samples)
        assert "Field Coverage" in report
        assert "id:" in report
        assert "email:" in report

    def test_report_shows_errors(self):
        """Report should show errors for invalid samples."""
        samples = [{"excerpt": "text"}]  # Missing id
        report = build_evidence_report(samples)
        assert "ERRORS" in report
        assert "id" in report


class TestRequiredFieldsConstant:
    """Ensure required fields are documented."""

    def test_required_fields_defined(self):
        """Required fields should be defined."""
        assert "id" in REQUIRED_FIELDS
        assert "excerpt" in REQUIRED_FIELDS

    def test_recommended_fields_defined(self):
        """Recommended fields should be defined."""
        assert "email" in RECOMMENDED_FIELDS
        assert "intercom_url" in RECOMMENDED_FIELDS


class TestRealWorldScenarios:
    """Test scenarios based on actual issues encountered."""

    def test_historical_backfill_placeholder_detected(self):
        """
        Scenario: Historical backfill created stories with placeholder text.

        This was the bug that motivated this validator - stories said:
        "To gather evidence: Search Intercom for recent conversations..."
        """
        placeholder_samples = [
            {
                "id": "123",
                "excerpt": """Note: This theme was identified during historical backfill.
                Sample conversations were not captured during batch processing.

                To gather evidence:
                - Search Intercom for recent conversations matching this theme
                - Add representative samples to this ticket""",
            },
        ]

        result = validate_samples(placeholder_samples)
        assert not result.is_valid
        assert any("placeholder" in e.lower() for e in result.errors)

    def test_properly_enriched_samples_pass(self):
        """
        Scenario: Samples properly enriched with metadata.

        After the fix, samples should have email, intercom_url, org_id, etc.
        """
        enriched_samples = [
            {
                "id": "215472581229755",
                "excerpt": "I'm trying to connect my Instagram business account but getting an error",
                "email": "customer@example.com",
                "contact_id": "abc123",
                "user_id": "user_456",
                "org_id": "org_789",
                "intercom_url": "https://app.intercom.com/a/apps/2t3d8az2/inbox/inbox/conversation/215472581229755",
            },
            {
                "id": "215472581229756",
                "excerpt": "Same issue here - Instagram connection keeps failing with OAuth error",
                "email": "another@example.com",
                "contact_id": "def456",
                "user_id": "user_789",
                "org_id": "org_789",
                "intercom_url": "https://app.intercom.com/a/apps/2t3d8az2/inbox/inbox/conversation/215472581229756",
            },
        ]

        result = validate_samples(enriched_samples)
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert result.coverage["email"] == 100.0
        assert result.coverage["intercom_url"] == 100.0
        assert result.coverage["org_id"] == 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
