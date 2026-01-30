"""
Issue #159: Resolution Fields in Story Content

Tests that resolution_action and resolution_category flow through
the story creation pipeline to be included in generated story content.

Data flow under test:
1. pipeline.py SELECT query → includes resolution fields
2. pipeline.py conv_dict → includes resolution fields
3. _build_theme_data() → includes resolution fields
4. StoryContentInput → has resolution fields
5. format_optional_context() → formats resolution fields
6. build_story_content_prompt() → passes resolution fields

Run with: pytest tests/test_issue_159_resolution_fields_in_stories.py -v
"""

import inspect
import pytest
from dataclasses import fields
from typing import Optional
from unittest.mock import Mock

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# =============================================================================
# Test 1: Pipeline SELECT query includes resolution fields
# =============================================================================


class TestPipelineSelectIncludesResolutionFields:
    """
    Verify the SELECT query in _run_pm_review_and_story_creation()
    fetches resolution fields from the themes table.

    Uses file inspection to avoid import dependency issues.
    """

    @pytest.fixture
    def pipeline_source(self):
        """Read pipeline.py source file."""
        pipeline_path = PROJECT_ROOT / "src" / "api" / "routers" / "pipeline.py"
        return pipeline_path.read_text()

    def test_select_includes_resolution_action(self, pipeline_source):
        """SELECT query should include t.resolution_action."""
        # The SELECT should fetch resolution_action from themes table
        assert "t.resolution_action" in pipeline_source, (
            "SELECT in _run_pm_review_and_story_creation missing t.resolution_action"
        )

    def test_select_includes_root_cause(self, pipeline_source):
        """SELECT query should include t.root_cause."""
        assert "t.root_cause" in pipeline_source, (
            "SELECT in _run_pm_review_and_story_creation missing t.root_cause"
        )

    def test_select_includes_solution_provided(self, pipeline_source):
        """SELECT query should include t.solution_provided."""
        assert "t.solution_provided" in pipeline_source, (
            "SELECT in _run_pm_review_and_story_creation missing t.solution_provided"
        )

    def test_select_includes_resolution_category(self, pipeline_source):
        """SELECT query should include t.resolution_category."""
        assert "t.resolution_category" in pipeline_source, (
            "SELECT in _run_pm_review_and_story_creation missing t.resolution_category"
        )


# =============================================================================
# Test 2: conv_dict construction includes resolution fields
# =============================================================================


class TestConvDictIncludesResolutionFields:
    """
    Verify conv_dict in _run_pm_review_and_story_creation()
    includes resolution fields from the query result.

    Uses file inspection to avoid import dependency issues.
    """

    @pytest.fixture
    def pipeline_source(self):
        """Read pipeline.py source file."""
        pipeline_path = PROJECT_ROOT / "src" / "api" / "routers" / "pipeline.py"
        return pipeline_path.read_text()

    def test_conv_dict_construction_has_resolution_action(self, pipeline_source):
        """conv_dict should include resolution_action key."""
        # Look for resolution_action being added to conv_dict
        assert '"resolution_action"' in pipeline_source, (
            "conv_dict construction missing resolution_action key"
        )

    def test_conv_dict_construction_has_root_cause(self, pipeline_source):
        """conv_dict should include root_cause key."""
        assert '"root_cause"' in pipeline_source, (
            "conv_dict construction missing root_cause key"
        )

    def test_conv_dict_construction_has_solution_provided(self, pipeline_source):
        """conv_dict should include solution_provided key."""
        assert '"solution_provided"' in pipeline_source, (
            "conv_dict construction missing solution_provided key"
        )

    def test_conv_dict_construction_has_resolution_category(self, pipeline_source):
        """conv_dict should include resolution_category key."""
        assert '"resolution_category"' in pipeline_source, (
            "conv_dict construction missing resolution_category key"
        )


# =============================================================================
# Test 3: _build_theme_data() includes resolution fields
# =============================================================================


class TestBuildThemeDataIncludesResolutionFields:
    """
    Verify _build_theme_data() in StoryCreationService
    includes resolution fields in the returned dict.

    Uses file inspection to avoid pydantic import dependency issues.
    """

    @pytest.fixture
    def service_source(self):
        """Read story_creation_service.py source file."""
        service_path = PROJECT_ROOT / "src" / "story_tracking" / "services" / "story_creation_service.py"
        return service_path.read_text()

    def test_build_theme_data_returns_resolution_action(self, service_source):
        """_build_theme_data() should return resolution_action in dict."""
        # Check that the _build_theme_data method includes resolution_action
        # Look for the pattern in the return dict
        assert '"resolution_action": first_non_null("resolution_action")' in service_source, (
            "_build_theme_data missing resolution_action in return dict"
        )

    def test_build_theme_data_returns_resolution_category(self, service_source):
        """_build_theme_data() should return resolution_category in dict."""
        assert '"resolution_category": first_non_null("resolution_category")' in service_source, (
            "_build_theme_data missing resolution_category in return dict"
        )

    def test_build_story_content_input_passes_resolution_action(self, service_source):
        """_build_story_content_input() should pass resolution_action to StoryContentInput."""
        assert 'resolution_action=theme_data.get("resolution_action")' in service_source, (
            "_build_story_content_input missing resolution_action parameter"
        )

    def test_build_story_content_input_passes_resolution_category(self, service_source):
        """_build_story_content_input() should pass resolution_category to StoryContentInput."""
        assert 'resolution_category=theme_data.get("resolution_category")' in service_source, (
            "_build_story_content_input missing resolution_category parameter"
        )


# =============================================================================
# Test 4: StoryContentInput has resolution fields
# =============================================================================


class TestStoryContentInputHasResolutionFields:
    """
    Verify StoryContentInput dataclass includes resolution_action
    and resolution_category optional fields.
    """

    def test_story_content_input_has_resolution_action_field(self):
        """StoryContentInput should have resolution_action field."""
        from src.prompts.story_content import StoryContentInput

        field_names = {f.name for f in fields(StoryContentInput)}

        assert "resolution_action" in field_names, (
            "StoryContentInput missing resolution_action field"
        )

    def test_story_content_input_has_resolution_category_field(self):
        """StoryContentInput should have resolution_category field."""
        from src.prompts.story_content import StoryContentInput

        field_names = {f.name for f in fields(StoryContentInput)}

        assert "resolution_category" in field_names, (
            "StoryContentInput missing resolution_category field"
        )

    def test_story_content_input_resolution_fields_are_optional(self):
        """Resolution fields should be optional (default to None)."""
        from src.prompts.story_content import StoryContentInput

        # Should be able to create without resolution fields
        content_input = StoryContentInput(
            user_intents=["test intent"],
            symptoms=["test symptom"],
            issue_signature="test-sig",
            classification_category="product_issue",
            product_area="billing",
            component="subscription",
        )

        # Fields should default to None
        assert content_input.resolution_action is None
        assert content_input.resolution_category is None

    def test_story_content_input_accepts_resolution_values(self):
        """StoryContentInput should accept resolution field values."""
        from src.prompts.story_content import StoryContentInput

        content_input = StoryContentInput(
            user_intents=["test intent"],
            symptoms=["test symptom"],
            issue_signature="test-sig",
            classification_category="product_issue",
            product_area="billing",
            component="subscription",
            resolution_action="provided_workaround",
            resolution_category="workaround",
        )

        assert content_input.resolution_action == "provided_workaround"
        assert content_input.resolution_category == "workaround"


# =============================================================================
# Test 5: format_optional_context() handles resolution fields
# =============================================================================


class TestFormatOptionalContextHandlesResolutionFields:
    """
    Verify format_optional_context() accepts and formats
    resolution_action and resolution_category.
    """

    def test_format_optional_context_accepts_resolution_action(self):
        """format_optional_context() should accept resolution_action param."""
        from src.prompts.story_content import format_optional_context

        # Should not raise TypeError for unknown kwarg
        result = format_optional_context(
            resolution_action="provided_workaround",
        )

        assert isinstance(result, str)

    def test_format_optional_context_accepts_resolution_category(self):
        """format_optional_context() should accept resolution_category param."""
        from src.prompts.story_content import format_optional_context

        result = format_optional_context(
            resolution_category="workaround",
        )

        assert isinstance(result, str)

    def test_format_optional_context_includes_resolution_action_in_output(self):
        """format_optional_context() should include resolution_action in output."""
        from src.prompts.story_content import format_optional_context

        result = format_optional_context(
            resolution_action="escalated_to_engineering",
        )

        # The output should contain the resolution action value
        assert "escalated_to_engineering" in result, (
            "format_optional_context should include resolution_action value in output"
        )

    def test_format_optional_context_includes_resolution_category_in_output(self):
        """format_optional_context() should include resolution_category in output."""
        from src.prompts.story_content import format_optional_context

        result = format_optional_context(
            resolution_category="escalation",
        )

        assert "escalation" in result, (
            "format_optional_context should include resolution_category value in output"
        )


# =============================================================================
# Test 6: build_story_content_prompt() passes resolution fields
# =============================================================================


class TestBuildStoryContentPromptPassesResolutionFields:
    """
    Verify build_story_content_prompt() passes resolution fields
    to format_optional_context().
    """

    def test_build_prompt_includes_resolution_action_in_output(self):
        """build_story_content_prompt() should include resolution_action."""
        from src.prompts.story_content import (
            build_story_content_prompt,
            StoryContentInput,
        )

        content_input = StoryContentInput(
            user_intents=["cancel subscription"],
            symptoms=["Unable to find cancel button"],
            issue_signature="billing_cancellation_ui",
            classification_category="product_issue",
            product_area="billing",
            component="subscription",
            resolution_action="provided_workaround",
            resolution_category="workaround",
        )

        prompt = build_story_content_prompt(content_input)

        assert "provided_workaround" in prompt, (
            "build_story_content_prompt should include resolution_action in prompt"
        )

    def test_build_prompt_includes_resolution_category_in_output(self):
        """build_story_content_prompt() should include resolution_category."""
        from src.prompts.story_content import (
            build_story_content_prompt,
            StoryContentInput,
        )

        content_input = StoryContentInput(
            user_intents=["cancel subscription"],
            symptoms=["Unable to find cancel button"],
            issue_signature="billing_cancellation_ui",
            classification_category="product_issue",
            product_area="billing",
            component="subscription",
            resolution_action="provided_workaround",
            resolution_category="workaround",
        )

        prompt = build_story_content_prompt(content_input)

        assert "workaround" in prompt, (
            "build_story_content_prompt should include resolution_category in prompt"
        )


# =============================================================================
# Test 7: End-to-end data flow verification
# =============================================================================


class TestEndToEndResolutionFieldsFlow:
    """
    Integration test verifying resolution fields flow through
    all layers from pipeline.py to prompt generation.

    Uses file inspection to verify the complete data path.
    """

    def test_complete_data_path_from_query_to_prompt(self):
        """
        Verify resolution fields appear in all layers of the pipeline:
        1. SELECT query in pipeline.py
        2. conv_dict in pipeline.py
        3. _build_theme_data() in story_creation_service.py
        4. StoryContentInput in story_content.py
        5. format_optional_context() in story_content.py
        6. build_story_content_prompt() in story_content.py
        """
        # 1. Pipeline SELECT
        pipeline_path = PROJECT_ROOT / "src" / "api" / "routers" / "pipeline.py"
        pipeline_source = pipeline_path.read_text()
        assert "t.resolution_action" in pipeline_source
        assert "t.resolution_category" in pipeline_source

        # 2. Pipeline conv_dict
        assert '"resolution_action"' in pipeline_source
        assert '"resolution_category"' in pipeline_source

        # 3. story_creation_service _build_theme_data
        service_path = PROJECT_ROOT / "src" / "story_tracking" / "services" / "story_creation_service.py"
        service_source = service_path.read_text()
        assert '"resolution_action": first_non_null("resolution_action")' in service_source
        assert '"resolution_category": first_non_null("resolution_category")' in service_source

        # 4. StoryContentInput dataclass
        story_content_path = PROJECT_ROOT / "src" / "prompts" / "story_content.py"
        story_content_source = story_content_path.read_text()
        assert "resolution_action: Optional[str]" in story_content_source
        assert "resolution_category: Optional[str]" in story_content_source

        # 5. format_optional_context parameters
        assert "resolution_action: Optional[str] = None," in story_content_source
        assert "resolution_category: Optional[str] = None," in story_content_source

        # 6. build_story_content_prompt passes fields
        assert "resolution_action=content_input.resolution_action" in story_content_source
        assert "resolution_category=content_input.resolution_category" in story_content_source


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
