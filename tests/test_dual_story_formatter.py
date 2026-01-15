"""
Tests for DualStoryFormatter class (Phase 3.1).

Tests dual-format story output with human and AI sections,
including codebase context integration.
"""

import pytest
from datetime import datetime
from src.story_formatter import DualStoryFormatter, DualFormatOutput

# Mock the codebase context provider types for testing
try:
    from src.story_tracking.services.codebase_context_provider import (
        ExplorationResult,
        FileReference,
        CodeSnippet,
    )
except ImportError:
    # Create mock classes if the provider isn't available
    from dataclasses import dataclass, field
    from typing import List, Optional

    @dataclass
    class FileReference:
        path: str
        line_start: Optional[int] = None
        line_end: Optional[int] = None
        relevance: str = ""

    @dataclass
    class CodeSnippet:
        file_path: str
        line_start: int
        line_end: int
        content: str
        language: str = "python"
        context: str = ""

    @dataclass
    class ExplorationResult:
        relevant_files: List[FileReference] = field(default_factory=list)
        code_snippets: List[CodeSnippet] = field(default_factory=list)
        investigation_queries: List[str] = field(default_factory=list)
        exploration_duration_ms: int = 0
        success: bool = True
        error: Optional[str] = None


@pytest.fixture
def minimal_theme_data():
    """Minimal theme data for testing."""
    return {
        "issue_signature": "test_issue",
        "title": "Test Issue",
        "product_area": "Testing",
        "component": "test_component",
        "occurrences": 3,
        "first_seen": "2026-01-01",
        "last_seen": "2026-01-10",
    }


@pytest.fixture
def complete_theme_data():
    """Complete theme data with all optional fields."""
    return {
        "issue_signature": "community_pins_not_appearing",
        "title": "Fix Community Pins Not Appearing in Yours Tab",
        "product_area": "Communities",
        "component": "tailwind_communities",
        "user_type": "Tailwind user scheduling pins with community assignments",
        "user_intent": "my published pins to appear in the Communities 'Yours' tab",
        "benefit": "I can verify my community contributions",
        "symptoms": [
            "Pins scheduled with community assignment",
            "Pins publish successfully to Pinterest",
            "Pins do not appear in Communities 'Yours' tab",
            "DB records exist for submissions",
        ],
        "root_cause_hypothesis": "Synchronization issue between pin publishing and community visibility",
        "occurrences": 12,
        "first_seen": "2025-11-01",
        "last_seen": "2026-01-15",
        "user_journey_step": "Pin Scheduler → Tailwind Communities → Yours Tab Display",
        "dependencies": "Pinterest API, tribe_content_documents table",
        "vertical_slice": "Backend retrieval → Frontend display",
        "task_type": "bug-fix",
        "acceptance_criteria": [
            "Given a pin is scheduled with a community assignment when the pin publishes then it appears in Yours tab",
            "[Observability] Logging captures publish-to-visibility timing",
        ],
        "investigation_steps": [
            "Review tailwind_communities code for issues",
            "Check logs for errors in community flow",
            "Verify API responses",
        ],
        "implementation_steps": [
            "**Analyze** the Yours tab retrieval code",
            "**Reproduce** using test data",
            "**Fix** the retrieval logic",
        ],
        "success_criteria": [
            "Pins appear in Yours tab after publishing",
            "All existing tests pass",
        ],
        "do_not": [
            "Modify write path - it's working",
            "Change schema without migration",
        ],
        "always": [
            "Write tests with the fix",
            "Log key transitions",
        ],
    }


@pytest.fixture
def evidence_data():
    """Evidence data with customer messages."""
    return {
        "customer_messages": [
            {"text": "My pins are not being posted in the communities"},
            {"text": "Pins published via you have not been appearing in my tribes"},
            "The pins are published but aren't in the yours tab",  # String format
        ]
    }


@pytest.fixture
def exploration_result():
    """Mock exploration result with codebase context."""
    return ExplorationResult(
        relevant_files=[
            FileReference(
                path="tailwind_communities/views.py",
                line_start=45,
                line_end=67,
                relevance="3 matches: yours_tab, tribe_content",
            ),
            FileReference(
                path="tailwind_communities/models.py",
                line_start=120,
                relevance="2 matches: tribe_content_documents",
            ),
        ],
        code_snippets=[
            CodeSnippet(
                file_path="tailwind_communities/views.py",
                line_start=45,
                line_end=55,
                content='def get_yours_tab_content(user_id):\n    """Retrieve user\'s community content."""\n    return TribeContent.objects.filter(user=user_id)',
                language="python",
                context="Main retrieval function for Yours tab",
            )
        ],
        investigation_queries=[
            "SELECT * FROM tribe_content_documents WHERE user_id = 123 LIMIT 10;",
            "grep -r 'yours_tab' tailwind_communities/",
        ],
        exploration_duration_ms=1250,
        success=True,
    )


@pytest.fixture
def formatter():
    """Formatter instance."""
    return DualStoryFormatter()


class TestDualFormatOutput:
    """Test DualFormatOutput dataclass."""

    def test_dataclass_creation(self):
        """Test creating DualFormatOutput with required fields."""
        output = DualFormatOutput(
            human_section="Human content",
            ai_section="AI content",
            combined="Combined content",
        )

        assert output.human_section == "Human content"
        assert output.ai_section == "AI content"
        assert output.combined == "Combined content"
        assert output.format_version == "v2"
        assert output.codebase_context is None
        assert isinstance(output.generated_at, datetime)

    def test_with_codebase_context(self):
        """Test DualFormatOutput with codebase context."""
        context = {
            "relevant_files": [{"path": "test.py", "line_start": 1}],
            "code_snippets": [],
            "investigation_queries": [],
        }

        output = DualFormatOutput(
            human_section="Human",
            ai_section="AI",
            combined="Combined",
            codebase_context=context,
        )

        assert output.codebase_context == context


class TestFormatStory:
    """Test format_story method."""

    def test_minimal_story(self, formatter, minimal_theme_data):
        """Test formatting with minimal theme data."""
        result = formatter.format_story(minimal_theme_data)

        assert isinstance(result, DualFormatOutput)
        assert result.format_version == "v2"
        assert "Test Issue" in result.human_section
        assert "Test Issue" in result.ai_section
        assert "SECTION 1: Human-Facing Story" in result.human_section
        assert "SECTION 2: AI Agent Task Specification" in result.ai_section
        assert "---" in result.combined  # Section separator

    def test_complete_story(self, formatter, complete_theme_data, evidence_data):
        """Test formatting with complete theme data."""
        result = formatter.format_story(complete_theme_data, evidence_data=evidence_data)

        # Check human section content
        assert "Communities" in result.human_section
        assert "tailwind_communities" in result.human_section
        assert "Symptoms (Customer Reported)" in result.human_section
        assert "Root Cause Hypothesis" in result.human_section
        assert "INVEST Check" in result.human_section

        # Check AI section content
        assert "This card is for a **senior backend engineer**" in result.ai_section
        assert "tailwind-app" in result.ai_section
        assert "Instructions (Step-by-Step)" in result.ai_section
        assert "Guardrails & Constraints" in result.ai_section

    def test_with_exploration_result(self, formatter, complete_theme_data, exploration_result):
        """Test formatting with codebase exploration results."""
        result = formatter.format_story(complete_theme_data, exploration_result=exploration_result)

        # Check codebase context in AI section
        assert "Relevant Files:" in result.ai_section
        assert "tailwind_communities/views.py" in result.ai_section
        assert "Code Snippets:" in result.ai_section
        assert "get_yours_tab_content" in result.ai_section
        assert "Suggested Investigation:" in result.ai_section
        assert "SELECT * FROM tribe_content_documents" in result.ai_section

        # Check serialized codebase context
        assert result.codebase_context is not None
        assert len(result.codebase_context["relevant_files"]) == 2
        assert len(result.codebase_context["code_snippets"]) == 1
        assert len(result.codebase_context["investigation_queries"]) == 2

    def test_combined_output(self, formatter, minimal_theme_data):
        """Test that combined output joins sections correctly."""
        result = formatter.format_story(minimal_theme_data)

        # Check that combined contains both sections
        assert result.human_section in result.combined
        assert result.ai_section in result.combined

        # Check separator
        assert "\n\n---\n\n" in result.combined


class TestFormatHumanSection:
    """Test format_human_section method."""

    def test_basic_structure(self, formatter, minimal_theme_data):
        """Test basic human section structure."""
        section = formatter.format_human_section(minimal_theme_data)

        assert "## SECTION 1: Human-Facing Story" in section
        assert "# Story: Test Issue" in section
        assert "## User Story" in section
        assert "## Context" in section
        assert "## Acceptance Criteria" in section
        assert "## Technical Notes" in section
        assert "## INVEST Check" in section
        assert "## Suggested Investigation" in section

    def test_user_story_formatting(self, formatter, complete_theme_data):
        """Test user story As a/I want/So that format."""
        section = formatter.format_human_section(complete_theme_data)

        assert "As a **Tailwind user scheduling pins" in section
        assert "I want **my published pins to appear" in section
        assert "So that **I can verify my community contributions" in section

    def test_context_section(self, formatter, complete_theme_data):
        """Test context section content."""
        section = formatter.format_human_section(complete_theme_data)

        assert "**Product Area**: Communities" in section
        assert "**Component**: tailwind_communities" in section
        assert "**User Journey Step**:" in section
        assert "**Dependencies**:" in section
        assert "12 customer reports" in section

    def test_symptoms_formatting(self, formatter, complete_theme_data):
        """Test symptoms with checkmarks and crosses."""
        section = formatter.format_human_section(complete_theme_data)

        # Negative symptoms should have ✗
        assert "✗ Pins do not appear" in section

        # Positive symptoms should have ✓
        assert "✓ Pins publish successfully to Pinterest" in section

        # Neutral symptoms should have -
        assert "- Pins scheduled with community assignment" in section
        assert "- DB records exist for submissions" in section

    def test_root_cause_hypothesis(self, formatter, complete_theme_data):
        """Test root cause hypothesis inclusion."""
        section = formatter.format_human_section(complete_theme_data)

        assert "## Root Cause Hypothesis" in section
        assert "Synchronization issue" in section

    def test_missing_root_cause(self, formatter, minimal_theme_data):
        """Test that missing root cause doesn't break formatting."""
        section = formatter.format_human_section(minimal_theme_data)

        # Should not have root cause section
        assert "## Root Cause Hypothesis" not in section

    def test_invest_check(self, formatter, minimal_theme_data):
        """Test INVEST check formatting."""
        section = formatter.format_human_section(minimal_theme_data)

        assert "## INVEST Check" in section
        assert "- [x] **Independent**" in section
        assert "- [x] **Negotiable**" in section
        assert "- [x] **Valuable**" in section
        assert "- [ ] **Estimable**" in section
        assert "- [ ] **Small**" in section
        assert "- [x] **Testable**" in section

    def test_sample_messages(self, formatter, minimal_theme_data, evidence_data):
        """Test sample customer messages formatting."""
        section = formatter.format_human_section(minimal_theme_data, evidence_data)

        assert "## Sample Customer Messages" in section
        assert '> "My pins are not being posted' in section
        assert '> "Pins published via you' in section
        # String format message
        assert '> "The pins are published' in section

    def test_no_sample_messages(self, formatter, minimal_theme_data):
        """Test formatting without sample messages."""
        section = formatter.format_human_section(minimal_theme_data)

        # Should not have sample messages section
        assert "## Sample Customer Messages" not in section


class TestFormatAISection:
    """Test format_ai_section method."""

    def test_basic_structure(self, formatter, minimal_theme_data):
        """Test basic AI section structure."""
        section = formatter.format_ai_section(minimal_theme_data)

        assert "## SECTION 2: AI Agent Task Specification" in section
        assert "# Agent Task: Test Issue" in section
        assert "## Role & Context" in section
        assert "## Goal (Single Responsibility)" in section
        assert "## Context & Architecture" in section
        assert "## Instructions (Step-by-Step)" in section
        assert "## Success Criteria (Explicit & Observable)" in section
        assert "## Guardrails & Constraints" in section
        assert "## Extended Thinking Guidance" in section
        assert "## Metadata" in section

    def test_third_person_framing(self, formatter, minimal_theme_data):
        """Test that AI section uses third-person framing."""
        section = formatter.format_ai_section(minimal_theme_data)

        # Should use third-person
        assert "This card is for a **senior backend engineer**" in section

        # Should NOT use second-person
        assert "You are" not in section
        assert "Your task" not in section

    def test_role_context(self, formatter, complete_theme_data):
        """Test role and context section."""
        section = formatter.format_ai_section(complete_theme_data)

        assert "**Repository**: tailwind-app" in section
        assert "**Task Type**: bug-fix" in section
        assert "**Related Story**: See Human-Facing Section above" in section
        assert "**Priority**:" in section

    def test_priority_levels(self, formatter):
        """Test priority determination based on occurrences."""
        # High priority
        theme = {"issue_signature": "test", "occurrences": 15}
        section = formatter.format_ai_section(theme)
        assert "High (10+ customer reports)" in section

        # Medium priority
        theme = {"issue_signature": "test", "occurrences": 7}
        section = formatter.format_ai_section(theme)
        assert "Medium (5-9 customer reports)" in section

        # Low-Medium priority
        theme = {"issue_signature": "test", "occurrences": 3}
        section = formatter.format_ai_section(theme)
        assert "Low-Medium (2-4 customer reports)" in section

        # Low priority
        theme = {"issue_signature": "test", "occurrences": 1}
        section = formatter.format_ai_section(theme)
        assert "Low (1 customer report)" in section

    def test_instructions(self, formatter, complete_theme_data):
        """Test instructions formatting."""
        section = formatter.format_ai_section(complete_theme_data)

        assert "1. **Analyze** the Yours tab retrieval code" in section
        assert "2. **Reproduce** using test data" in section
        assert "3. **Fix** the retrieval logic" in section

    def test_success_criteria(self, formatter, complete_theme_data):
        """Test success criteria formatting."""
        section = formatter.format_ai_section(complete_theme_data)

        assert "- [ ] Pins appear in Yours tab after publishing" in section
        assert "- [ ] All existing tests pass" in section

    def test_guardrails(self, formatter, complete_theme_data):
        """Test guardrails formatting."""
        section = formatter.format_ai_section(complete_theme_data)

        assert "### DO NOT:" in section
        assert "- Modify write path - it's working" in section
        assert "- Change schema without migration" in section

        assert "### ALWAYS:" in section
        assert "- Write tests with the fix" in section
        assert "- Log key transitions" in section

    def test_extended_thinking(self, formatter, complete_theme_data):
        """Test extended thinking guidance."""
        section = formatter.format_ai_section(complete_theme_data)

        assert "## Extended Thinking Guidance" in section
        # High volume
        assert "**High volume** - 12 reports" in section
        # Duration > 30 days
        assert "persisted for" in section

    def test_metadata_footer(self, formatter, complete_theme_data):
        """Test metadata footer."""
        section = formatter.format_ai_section(complete_theme_data)

        assert "## Metadata" in section
        assert "**Issue Signature** | `community_pins_not_appearing`" in section
        assert "**Occurrences**     | 12" in section
        assert "**First Seen**      | 2025-11-01" in section
        assert "**Last Seen**       | 2026-01-15" in section
        assert "FeedForward Pipeline v2.0" in section


class TestFormatCodebaseContext:
    """Test format_codebase_context method."""

    def test_with_all_context(self, formatter, exploration_result):
        """Test formatting with complete exploration results."""
        section = formatter.format_codebase_context(exploration_result)

        # Relevant files
        assert "### Relevant Files:" in section
        assert "`tailwind_communities/views.py` (lines 45-67)" in section
        assert "3 matches: yours_tab, tribe_content" in section
        assert "`tailwind_communities/models.py` (line 120)" in section

        # Code snippets
        assert "### Code Snippets:" in section
        assert "**1. tailwind_communities/views.py**" in section
        assert "```python" in section
        assert "get_yours_tab_content" in section

        # Investigation queries
        assert "### Suggested Investigation:" in section
        assert "SELECT * FROM tribe_content_documents" in section

    def test_with_failed_exploration(self, formatter):
        """Test formatting with failed exploration."""
        failed_result = ExplorationResult(
            relevant_files=[],
            code_snippets=[],
            investigation_queries=[],
            success=False,
            error="Exploration failed",
        )

        section = formatter.format_codebase_context(failed_result)

        assert "Codebase exploration unavailable" in section
        assert "Manual investigation required" in section

    def test_with_no_exploration(self, formatter):
        """Test formatting with None exploration result."""
        section = formatter.format_codebase_context(None)

        assert "Codebase exploration unavailable" in section

    def test_relevant_files_only(self, formatter):
        """Test formatting with only relevant files."""
        result = ExplorationResult(
            relevant_files=[
                FileReference(path="test.py", line_start=10, relevance="test match")
            ],
            code_snippets=[],
            investigation_queries=[],
            success=True,
        )

        section = formatter.format_codebase_context(result)

        assert "### Relevant Files:" in section
        assert "`test.py` (line 10) - test match" in section
        assert "### Code Snippets:" not in section

    def test_top_n_limiting(self, formatter):
        """Test that only top N files and snippets are included."""
        # Create 15 files (should only show top 10)
        many_files = [
            FileReference(path=f"file{i}.py", line_start=i) for i in range(15)
        ]

        # Create 5 snippets (should only show top 3)
        many_snippets = [
            CodeSnippet(
                file_path=f"file{i}.py",
                line_start=1,
                line_end=10,
                content="code",
            )
            for i in range(5)
        ]

        result = ExplorationResult(
            relevant_files=many_files,
            code_snippets=many_snippets,
            investigation_queries=[],
            success=True,
        )

        section = formatter.format_codebase_context(result)

        # Should have 10 files
        assert section.count("`file") == 10

        # Should have 3 snippets
        assert section.count("**1.") == 1
        assert section.count("**2.") == 1
        assert section.count("**3.") == 1
        assert section.count("**4.") == 0


class TestHelperMethods:
    """Test helper/private methods."""

    def test_determine_priority(self, formatter):
        """Test priority determination logic."""
        assert formatter._determine_priority(15) == "High (10+ customer reports)"
        assert formatter._determine_priority(7) == "Medium (5-9 customer reports)"
        assert formatter._determine_priority(3) == "Low-Medium (2-4 customer reports)"
        assert formatter._determine_priority(1) == "Low (1 customer report)"

    def test_calculate_duration_days(self, formatter):
        """Test duration calculation."""
        # Valid ISO dates
        duration = formatter._calculate_duration_days("2026-01-01", "2026-01-10")
        assert duration == 9

        # Same day
        duration = formatter._calculate_duration_days("2026-01-01", "2026-01-01")
        assert duration == 0

        # Missing dates
        duration = formatter._calculate_duration_days(None, "2026-01-10")
        assert duration is None

        duration = formatter._calculate_duration_days("2026-01-01", None)
        assert duration is None

        # Invalid dates
        duration = formatter._calculate_duration_days("invalid", "2026-01-10")
        assert duration is None

    def test_format_user_story_defaults(self, formatter):
        """Test user story with default values."""
        theme = {}
        result = formatter._format_user_story(theme)

        assert "As a **Tailwind user**" in result
        assert "I want **use the product successfully**" in result
        assert "So that **achieve my goals without friction**" in result

    def test_format_acceptance_criteria_with_checkboxes(self, formatter):
        """Test acceptance criteria formatting."""
        # Criteria without checkboxes
        theme = {
            "acceptance_criteria": [
                "Test passes",
                "- [ ] Already has checkbox",
            ]
        }

        result = formatter._format_acceptance_criteria(theme)

        assert "- [ ] Test passes" in result
        assert "- [ ] Already has checkbox" in result

    def test_format_symptoms_markers(self, formatter):
        """Test symptom marker assignment."""
        symptoms = [
            "Feature works correctly",  # Should get ✓
            "Feature does not work",  # Should get ✗
            "Feature is slow",  # Should get -
        ]

        result = formatter._format_symptoms(symptoms)

        assert "✓ Feature works correctly" in result
        assert "✗ Feature does not work" in result
        assert "- Feature is slow" in result

    def test_format_sample_messages_mixed_types(self, formatter):
        """Test sample messages with mixed dict/string types."""
        evidence = {
            "customer_messages": [
                {"text": "Message from dict"},
                "Direct string message",
                {"text": "Another dict message"},
                "Another string",
            ]
        }

        result = formatter._format_sample_messages(evidence)

        # Should include first 3 messages
        assert '> "Message from dict"' in result
        assert '> "Direct string message"' in result
        assert '> "Another dict message"' in result
        # Should not include 4th message
        assert '> "Another string"' not in result


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_theme_data(self, formatter):
        """Test formatting with empty theme data."""
        result = formatter.format_story({})

        # Should still produce valid output with defaults
        assert isinstance(result, DualFormatOutput)
        assert "Untitled Story" in result.human_section
        assert "Untitled Task" in result.ai_section

    def test_missing_optional_fields(self, formatter):
        """Test that missing optional fields don't break formatting."""
        theme = {"issue_signature": "test"}

        # Should not raise exceptions
        result = formatter.format_story(theme)
        assert isinstance(result, DualFormatOutput)

    def test_title_vs_issue_signature(self, formatter):
        """Test that title takes precedence over issue_signature."""
        theme1 = {
            "title": "My Title",
            "issue_signature": "my_signature",
        }

        result1 = formatter.format_story(theme1)
        assert "My Title" in result1.human_section

        # Without title, should use issue_signature
        theme2 = {"issue_signature": "my_signature"}
        result2 = formatter.format_story(theme2)
        assert "My Signature" in result2.human_section

    def test_empty_lists(self, formatter):
        """Test handling of empty lists."""
        theme = {
            "issue_signature": "test",
            "symptoms": [],
            "acceptance_criteria": [],
            "investigation_steps": [],
        }

        result = formatter.format_story(theme, evidence_data={"customer_messages": []})

        # Should use defaults for empty lists
        assert isinstance(result, DualFormatOutput)

    def test_special_characters_in_text(self, formatter):
        """Test handling of special characters in markdown."""
        theme = {
            "title": "Fix `code` with *asterisks* and _underscores_",
            "issue_signature": "special_chars",
            "component": "test_component",
        }

        result = formatter.format_story(theme)

        # Should preserve markdown special characters
        # Note: .title() converts the title so case may change
        assert "`code`" in result.human_section.lower() or "`Code`" in result.human_section
        assert "*asterisks*" in result.human_section.lower() or "*Asterisks*" in result.human_section


class TestIntegrationWithCodebaseContextProvider:
    """Test integration with real codebase context provider types."""

    def test_real_exploration_result_type(self, formatter):
        """Test that formatter works with real ExplorationResult type."""
        # This test verifies the import and type compatibility
        try:
            from src.story_tracking.services.codebase_context_provider import (
                ExplorationResult as RealExplorationResult,
                FileReference as RealFileReference,
                CodeSnippet as RealCodeSnippet,
            )

            # Create real types
            real_result = RealExplorationResult(
                relevant_files=[
                    RealFileReference(path="test.py", line_start=1, relevance="test")
                ],
                code_snippets=[
                    RealCodeSnippet(
                        file_path="test.py",
                        line_start=1,
                        line_end=10,
                        content="def test():\n    pass",
                        language="python",
                    )
                ],
                investigation_queries=["SELECT * FROM test;"],
                success=True,
            )

            # Should work without errors
            theme = {"issue_signature": "test", "component": "test"}
            result = formatter.format_story(theme, exploration_result=real_result)

            assert "test.py" in result.ai_section
            assert "SELECT * FROM test" in result.ai_section

        except ImportError:
            pytest.skip("Codebase context provider not available")
