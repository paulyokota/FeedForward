"""
Tests for story_formatter module.

Tests the Coda story formatting functions added in Phase 1.
"""
import os
import pytest
from src import story_formatter
from src.story_formatter import (
    format_coda_excerpt,
    format_excerpt_multi_source,
    build_research_story_description,
    format_excerpt,
)


@pytest.fixture
def mock_coda_doc_id(monkeypatch):
    """Set CODA_DOC_ID for tests."""
    monkeypatch.setattr(story_formatter, "CODA_DOC_ID", "test-doc-123")


class TestFormatCodaExcerpt:
    """Test format_coda_excerpt function."""

    def test_with_row_id(self, mock_coda_doc_id):
        """Test deep link to table row."""
        result = format_coda_excerpt(
            text="User mentioned slow performance",
            table_name="Research Synthesis",
            row_id="row-abc-123",
        )

        assert "[Research Synthesis](https://coda.io/d/test-doc-123#row-row-abc-123)" in result
        assert "> User mentioned slow performance" in result

    def test_with_page_id(self, mock_coda_doc_id):
        """Test link to page."""
        result = format_coda_excerpt(
            text="Feature request for bulk actions",
            participant="user@example.com",
            page_id="page-xyz-456",
        )

        assert "[user@example.com](https://coda.io/d/test-doc-123/_/page-xyz-456)" in result
        assert "> Feature request for bulk actions" in result

    def test_fallback_doc_root(self, mock_coda_doc_id):
        """Test fallback to doc root when no IDs provided."""
        result = format_coda_excerpt(
            text="General feedback",
            table_name="Beta Calls",
        )

        assert "[Beta Calls](https://coda.io/d/test-doc-123)" in result
        assert "> General feedback" in result

    def test_participant_display_priority(self, mock_coda_doc_id):
        """Test that participant takes priority over table_name."""
        result = format_coda_excerpt(
            text="Test excerpt",
            table_name="Table Name",
            participant="participant@example.com",
        )

        assert "[participant@example.com]" in result
        assert "[Table Name]" not in result

    def test_table_name_display(self, mock_coda_doc_id):
        """Test table_name display when no participant."""
        result = format_coda_excerpt(
            text="Test excerpt",
            table_name="P4 Synth",
        )

        assert "[P4 Synth]" in result

    def test_default_display(self, mock_coda_doc_id):
        """Test default 'Research' display when no labels."""
        result = format_coda_excerpt(text="Test excerpt")

        assert "[Research]" in result

    def test_text_truncation(self, mock_coda_doc_id):
        """Test that long text is truncated to 300 chars."""
        long_text = "x" * 500
        result = format_coda_excerpt(text=long_text)

        # Extract the quoted text
        quote_part = result.split("> ")[1]
        assert len(quote_part) == 300

    def test_custom_doc_id(self):
        """Test custom coda_doc_id parameter."""
        result = format_coda_excerpt(
            text="Test excerpt",
            coda_doc_id="custom-doc-456",
            row_id="row-123",
        )

        assert "https://coda.io/d/custom-doc-456#row-row-123" in result

    def test_no_doc_id_fallback(self, monkeypatch):
        """Test fallback to coda.io when no doc ID available."""
        monkeypatch.delenv("CODA_DOC_ID", raising=False)
        result = format_coda_excerpt(text="Test excerpt")

        assert "[Research](https://coda.io)" in result


class TestFormatExcerptMultiSource:
    """Test format_excerpt_multi_source routing function."""

    def test_routes_to_intercom(self):
        """Test routing to format_excerpt for Intercom."""
        result = format_excerpt_multi_source(
            source="intercom",
            text="Support ticket text",
            conversation_id="conv-123",
            source_metadata={
                "email": "customer@example.com",
                "org_id": "org-456",
                "user_id": "user-789",
            },
        )

        # Should contain Intercom URL structure
        assert "https://app.intercom.com" in result
        assert "customer@example.com" in result
        assert "Support ticket text" in result

    def test_routes_to_coda(self, mock_coda_doc_id):
        """Test routing to format_coda_excerpt for Coda."""
        result = format_excerpt_multi_source(
            source="coda",
            text="Research insight",
            source_metadata={
                "participant": "researcher@example.com",
                "row_id": "row-123",
            },
        )

        # Should contain Coda URL structure
        assert "https://coda.io/d/" in result
        assert "researcher@example.com" in result
        assert "Research insight" in result

    def test_unknown_source_fallback(self):
        """Test unknown source returns plain text."""
        result = format_excerpt_multi_source(
            source="unknown_source",
            text="Some text here",
        )

        assert result == "> Some text here"

    def test_missing_metadata(self):
        """Test handling of missing source_metadata."""
        result = format_excerpt_multi_source(
            source="intercom",
            text="Test text",
            conversation_id="conv-123",
        )

        # Should still work with defaults
        assert "Conversation conv-123" in result

    def test_intercom_with_all_metadata(self):
        """Test Intercom with complete metadata."""
        result = format_excerpt_multi_source(
            source="intercom",
            text="Customer complaint about bug",
            conversation_id="conv-abc",
            source_metadata={
                "email": "customer@example.com",
                "org_id": "org-123",
                "user_id": "user-456",
                "intercom_url": "https://custom.url",
                "jarvis_org_url": "https://jarvis.example/org/123",
                "jarvis_user_url": "https://jarvis.example/user/456",
            },
        )

        assert "customer@example.com" in result
        assert "[Org]" in result
        assert "[User]" in result

    def test_coda_with_all_metadata(self, mock_coda_doc_id):
        """Test Coda with complete metadata."""
        result = format_excerpt_multi_source(
            source="coda",
            text="Detailed research finding",
            source_metadata={
                "table_name": "Research Table",
                "participant": "participant@example.com",
                "page_id": "page-123",
                "row_id": "row-456",
                "coda_doc_id": "doc-789",
            },
        )

        assert "participant@example.com" in result
        assert "https://coda.io/d/doc-789#row-row-456" in result


class TestBuildResearchStoryDescription:
    """Test build_research_story_description function."""

    def test_structure_with_pain_point(self, mock_coda_doc_id):
        """Test description structure for pain_point theme."""
        excerpts = [
            {
                "source": "coda",
                "text": "Users struggle with the onboarding flow",
                "source_metadata": {
                    "participant": "user1@example.com",
                    "row_id": "row-1",
                },
            },
            {
                "source": "intercom",
                "text": "Onboarding is confusing",
                "conversation_id": "conv-1",
                "source_metadata": {"email": "user2@example.com"},
            },
        ]

        result = build_research_story_description(
            theme_name="onboarding_confusion",
            excerpts=excerpts,
            participant_count=15,
            theme_type="pain_point",
            source_breakdown={"coda": 10, "intercom": 5},
        )

        # Check header structure
        assert "## Theme Summary" in result
        assert "**Theme**: Onboarding Confusion" in result
        assert "**Type**: Pain Point" in result
        assert "**Participants**: 15" in result

        # Check source breakdown
        assert "### Source Breakdown" in result
        assert "- Coda: 10" in result
        assert "- Intercom: 5" in result

        # Check quotes section
        assert "## Representative Quotes" in result
        assert "### Quote 1" in result
        assert "### Quote 2" in result

        # Check investigation section
        assert "## Suggested Investigation" in result
        assert "What user needs does this theme reveal?" in result

        # Check acceptance criteria
        assert "## Acceptance Criteria" in result
        assert "Theme validated with additional user research" in result

        # Check footer
        assert "*Generated by FeedForward Research Pipeline*" in result

    def test_structure_with_feature_request(self, mock_coda_doc_id):
        """Test description structure for feature_request theme."""
        excerpts = [
            {
                "source": "coda",
                "text": "Would love to have bulk export",
                "source_metadata": {"participant": "user@example.com"},
            }
        ]

        result = build_research_story_description(
            theme_name="bulk_export",
            excerpts=excerpts,
            participant_count=8,
            theme_type="feature_request",
            source_breakdown={"coda": 8},
        )

        assert "**Type**: Feature Request" in result

    def test_excerpt_formatting_within_description(self, mock_coda_doc_id):
        """Test that excerpts are properly formatted."""
        excerpts = [
            {
                "source": "coda",
                "text": "This is a research finding",
                "source_metadata": {
                    "participant": "researcher@example.com",
                    "row_id": "row-123",
                },
            }
        ]

        result = build_research_story_description(
            theme_name="test_theme",
            excerpts=excerpts,
            participant_count=5,
            theme_type="insight",
            source_breakdown={"coda": 5},
        )

        # Should contain formatted Coda excerpt
        assert "[researcher@example.com]" in result
        assert "https://coda.io/d/test-doc-123#row-row-123" in result
        assert "> This is a research finding" in result

    def test_max_five_excerpts(self, mock_coda_doc_id):
        """Test that only first 5 excerpts are included."""
        excerpts = [
            {
                "source": "coda",
                "text": f"Excerpt {i}",
                "source_metadata": {},
            }
            for i in range(10)
        ]

        result = build_research_story_description(
            theme_name="test_theme",
            excerpts=excerpts,
            participant_count=10,
            theme_type="insight",
            source_breakdown={"coda": 10},
        )

        # Should have quotes 1-5
        assert "### Quote 1" in result
        assert "### Quote 5" in result
        # Should not have quote 6
        assert "### Quote 6" not in result

    def test_source_breakdown_display(self, mock_coda_doc_id):
        """Test source breakdown formatting."""
        excerpts = []

        result = build_research_story_description(
            theme_name="test_theme",
            excerpts=excerpts,
            participant_count=25,
            theme_type="pain_point",
            source_breakdown={"coda": 15, "intercom": 10},
        )

        assert "- Coda: 15" in result
        assert "- Intercom: 10" in result

    def test_mixed_source_excerpts(self, mock_coda_doc_id):
        """Test handling mixed Intercom and Coda excerpts."""
        excerpts = [
            {
                "source": "intercom",
                "text": "Support ticket feedback",
                "conversation_id": "conv-123",
                "source_metadata": {"email": "customer@example.com"},
            },
            {
                "source": "coda",
                "text": "Research participant insight",
                "source_metadata": {"participant": "researcher@example.com"},
            },
        ]

        result = build_research_story_description(
            theme_name="mixed_theme",
            excerpts=excerpts,
            participant_count=12,
            theme_type="feature_request",
            source_breakdown={"intercom": 7, "coda": 5},
        )

        # Should contain both Intercom and Coda formatted excerpts
        assert "customer@example.com" in result
        assert "researcher@example.com" in result
        assert "https://app.intercom.com" in result
        assert "https://coda.io" in result


class TestIntegrationWithExistingFunctions:
    """Test integration with existing format_excerpt function."""

    def test_format_excerpt_unchanged(self):
        """Verify format_excerpt still works as expected."""
        result = format_excerpt(
            conversation_id="conv-123",
            email="customer@example.com",
            excerpt="Test conversation text",
        )

        assert "customer@example.com" in result
        assert "https://app.intercom.com" in result
        assert "Test conversation text" in result

    def test_multi_source_calls_format_excerpt(self):
        """Verify format_excerpt_multi_source calls format_excerpt correctly."""
        result = format_excerpt_multi_source(
            source="intercom",
            text="Support text",
            conversation_id="conv-456",
            source_metadata={"email": "user@example.com"},
        )

        # Should produce same result as calling format_excerpt directly
        direct_result = format_excerpt(
            conversation_id="conv-456",
            email="user@example.com",
            excerpt="Support text",
        )

        assert result == direct_result


# -----------------------------------------------------------------------------
# Issue #133: DualStoryFormatter Tests for New Generated Content Fields
# -----------------------------------------------------------------------------


class TestDualStoryFormatterGeneratedContent:
    """Test DualStoryFormatter methods with generated content (issue #133)."""

    @pytest.fixture
    def formatter(self):
        """Create a DualStoryFormatter instance."""
        from src.story_formatter import DualStoryFormatter
        return DualStoryFormatter()

    @pytest.fixture
    def sample_theme_data(self):
        """Sample theme data for testing."""
        return {
            "title": "pin_upload_failure",
            "product_area": "publishing",
            "component": "pinterest",
            "symptoms": ["Server 0 error", "pins not saving"],
            "user_intent": "upload pins to drafts",
            "root_cause_hypothesis": "API timeout",
            "occurrences": 5,
            "first_seen": "2026-01-01",
            "last_seen": "2026-01-26",
        }

    @pytest.fixture
    def sample_generated_content(self):
        """Sample GeneratedStoryContent with all 9 fields."""
        from src.story_tracking.services.story_content_generator import GeneratedStoryContent
        return GeneratedStoryContent(
            title="Fix pin upload failures when saving to drafts",
            user_type="content creator managing Pinterest accounts",
            user_story_want="to upload pins to my drafts without errors",
            user_story_benefit="I can maintain my posting schedule",
            ai_agent_goal="Resolve pin upload failure. Success: pins save successfully.",
            acceptance_criteria=[
                "Given a user uploading a pin, When save is triggered, Then pin saves without error",
                "Given test data, When fix is applied, Then all existing tests pass",
            ],
            investigation_steps=[
                "Review `pinterest` error logs for Server 0 patterns",
                "Verify Pinterest API authentication during draft save",
                "Test with different image formats",
            ],
            success_criteria=[
                "Pin uploads complete without Server 0 errors",
                "All existing pinterest tests pass",
            ],
            technical_notes="**Testing**: API integration test. **Vertical Slice**: API -> pinterest -> Pinterest API.",
        )

    def test_acceptance_criteria_uses_generated_content(self, formatter, sample_theme_data, sample_generated_content):
        """Test _format_acceptance_criteria uses generated content when available."""
        result = formatter._format_acceptance_criteria(sample_theme_data, sample_generated_content)

        assert "Given a user uploading a pin" in result
        assert "Given the reported conditions" not in result  # Not fallback

    def test_acceptance_criteria_fallback_without_generated(self, formatter, sample_theme_data):
        """Test _format_acceptance_criteria falls back when no generated content."""
        result = formatter._format_acceptance_criteria(sample_theme_data, None)

        assert "Given the reported conditions" in result

    def test_investigation_steps_uses_generated_content(self, formatter, sample_theme_data, sample_generated_content):
        """Test _format_suggested_investigation uses generated content when available."""
        result = formatter._format_suggested_investigation(sample_theme_data, sample_generated_content)

        assert "Review `pinterest` error logs" in result
        assert "Verify API responses" not in result  # Not fallback

    def test_investigation_steps_fallback_without_generated(self, formatter, sample_theme_data):
        """Test _format_suggested_investigation falls back when no generated content."""
        result = formatter._format_suggested_investigation(sample_theme_data, None)

        # Should use component-based fallback
        assert "pinterest" in result.lower()

    def test_success_criteria_uses_generated_content(self, formatter, sample_theme_data, sample_generated_content):
        """Test _format_success_criteria uses generated content when available."""
        result = formatter._format_success_criteria(sample_theme_data, sample_generated_content)

        assert "Pin uploads complete without Server 0 errors" in result
        assert "Fix addresses root cause" not in result  # Not old fallback

    def test_success_criteria_fallback_without_generated(self, formatter, sample_theme_data):
        """Test _format_success_criteria falls back when no generated content."""
        result = formatter._format_success_criteria(sample_theme_data, None)

        assert "Issue is resolved" in result

    def test_technical_notes_uses_generated_content(self, formatter, sample_theme_data, sample_generated_content):
        """Test _format_technical_notes uses generated content when available."""
        result = formatter._format_technical_notes(sample_theme_data, sample_generated_content)

        assert "**Testing**: API integration test" in result
        assert "Integration test covering the relevant flow" not in result  # Not fallback

    def test_technical_notes_fallback_without_generated(self, formatter, sample_theme_data):
        """Test _format_technical_notes falls back when no generated content."""
        result = formatter._format_technical_notes(sample_theme_data, None)

        assert "**Target Components**:" in result
        assert "pinterest" in result.lower()

    def test_human_section_no_invest_check(self, formatter, sample_theme_data, sample_generated_content):
        """Test format_human_section does NOT include INVEST Check (issue #133 removal)."""
        result = formatter.format_human_section(sample_theme_data, None, sample_generated_content)

        assert "## INVEST Check" not in result
        assert "Independent" not in result
        assert "Negotiable" not in result

    def test_ai_section_no_instructions_or_guardrails(self, formatter, sample_theme_data, sample_generated_content):
        """Test format_ai_section does NOT include Instructions or Guardrails (issue #133 removal)."""
        result = formatter.format_ai_section(sample_theme_data, None, sample_generated_content)

        assert "## Instructions (Step-by-Step)" not in result
        assert "## Guardrails & Constraints" not in result
        assert "### DO NOT:" not in result
        assert "### ALWAYS:" not in result

    def test_human_section_passes_generated_content_to_helpers(self, formatter, sample_theme_data, sample_generated_content):
        """Test format_human_section passes generated_content to helper methods."""
        result = formatter.format_human_section(sample_theme_data, None, sample_generated_content)

        # Verify generated acceptance criteria appears (not fallback)
        assert "Given a user uploading a pin" in result
        # Verify generated investigation steps appear (not fallback)
        assert "Review `pinterest` error logs" in result

    def test_ai_section_passes_generated_content_to_helpers(self, formatter, sample_theme_data, sample_generated_content):
        """Test format_ai_section passes generated_content to success criteria."""
        result = formatter.format_ai_section(sample_theme_data, None, sample_generated_content)

        # Verify generated success criteria appears (not fallback)
        assert "Pin uploads complete without Server 0 errors" in result
