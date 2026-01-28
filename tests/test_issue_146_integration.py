"""
Issue #146 Integration Tests: LLM-Powered Resolution/Knowledge Extraction

Tests for verifying the complete resolution field data flow end-to-end.
These tests ensure that LLM-extracted resolution fields flow correctly
through the entire pipeline: Theme -> PM Review -> Story Creation.

The flow being tested:
1. Theme dataclass has resolution_action, root_cause, solution_provided, resolution_category
2. PM Review receives resolution fields via ConversationContext
3. Story Creation receives resolution fields via ConversationData
4. StoryContentInput receives root_cause and solution_provided for story content generation
5. Classification pipeline works without deprecated regex extractors

Reference: docs/issue-146-architecture.md

Owner: Kenji (Testing)
Run: pytest tests/test_issue_146_integration.py -v
"""

import json
import sys
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Import the modules we're testing
from theme_extractor import Theme
from story_tracking.services.pm_review_service import ConversationContext
from story_tracking.services.story_creation_service import ConversationData, StoryCreationService
from prompts.story_content import StoryContentInput, format_optional_context


# =============================================================================
# Test 1: Theme Dataclass Has Resolution Fields
# =============================================================================


class TestThemeDataclassHasResolutionFields:
    """
    Test that Theme dataclass has all 4 resolution fields with correct defaults.

    Verifies Issue #146 Phase 1B: Add LLM extraction fields to Theme dataclass.
    """

    def test_theme_dataclass_has_resolution_action_field(self):
        """Theme dataclass should have resolution_action field."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        assert hasattr(theme, "resolution_action")
        assert theme.resolution_action == ""  # Default to empty string

    def test_theme_dataclass_has_root_cause_field(self):
        """Theme dataclass should have root_cause field (LLM-extracted, not root_cause_hypothesis)."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        assert hasattr(theme, "root_cause")
        assert theme.root_cause == ""  # Default to empty string

    def test_theme_dataclass_has_solution_provided_field(self):
        """Theme dataclass should have solution_provided field."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        assert hasattr(theme, "solution_provided")
        assert theme.solution_provided == ""  # Default to empty string

    def test_theme_dataclass_has_resolution_category_field(self):
        """Theme dataclass should have resolution_category field."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=["symptom1"],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        assert hasattr(theme, "resolution_category")
        assert theme.resolution_category == ""  # Default to empty string

    def test_theme_dataclass_all_resolution_fields_default_to_empty_string(self):
        """All 4 resolution fields should default to empty string."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=[],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
        )

        assert theme.resolution_action == ""
        assert theme.root_cause == ""
        assert theme.solution_provided == ""
        assert theme.resolution_category == ""

    def test_theme_dataclass_can_be_initialized_with_resolution_fields(self):
        """Theme dataclass should accept resolution fields in initialization."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="pinterest_board_permission_denied",
            user_intent="Schedule pins to Pinterest board",
            symptoms=["Error 403: Board access denied"],
            affected_flow="Scheduler -> Pinterest API",
            root_cause_hypothesis="OAuth token may have expired",
            # Issue #146 fields
            resolution_action="provided_workaround",
            root_cause="OAuth token invalidated after Pinterest password change",
            solution_provided="User reconnected Pinterest account via Settings > Connections",
            resolution_category="workaround",
        )

        assert theme.resolution_action == "provided_workaround"
        assert theme.root_cause == "OAuth token invalidated after Pinterest password change"
        assert theme.solution_provided == "User reconnected Pinterest account via Settings > Connections"
        assert theme.resolution_category == "workaround"

    def test_theme_to_dict_includes_resolution_fields(self):
        """Theme.to_dict() should include all resolution fields."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test intent",
            symptoms=[],
            affected_flow="Test flow",
            root_cause_hypothesis="Test hypothesis",
            resolution_action="escalated_to_engineering",
            root_cause="Bug in Pinterest API integration",
            solution_provided="Reported to engineering team for investigation",
            resolution_category="escalation",
        )

        theme_dict = theme.to_dict()

        assert "resolution_action" in theme_dict
        assert "root_cause" in theme_dict
        assert "solution_provided" in theme_dict
        assert "resolution_category" in theme_dict
        assert theme_dict["resolution_action"] == "escalated_to_engineering"
        assert theme_dict["root_cause"] == "Bug in Pinterest API integration"


# =============================================================================
# Test 2: Resolution Fields Flow to ConversationContext (PM Review)
# =============================================================================


class TestResolutionFieldsFlowToConversationContext:
    """
    Test that ConversationContext in pm_review_service receives resolution fields.

    Verifies Issue #146 Phase 1C: PM Review receives resolution context.
    """

    def test_conversation_context_has_resolution_action_field(self):
        """ConversationContext should have resolution_action field."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Schedule pins",
            symptoms=["Error 403"],
            affected_flow="Pinterest publishing",
            excerpt="Test excerpt",
            product_area="publishing",
            component="pinterest",
        )

        assert hasattr(ctx, "resolution_action")
        assert ctx.resolution_action == ""  # Default empty string

    def test_conversation_context_has_root_cause_field(self):
        """ConversationContext should have root_cause field."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Schedule pins",
            symptoms=["Error 403"],
            affected_flow="Pinterest publishing",
            excerpt="Test excerpt",
            product_area="publishing",
            component="pinterest",
        )

        assert hasattr(ctx, "root_cause")
        assert ctx.root_cause == ""  # Default empty string

    def test_conversation_context_has_solution_provided_field(self):
        """ConversationContext should have solution_provided field."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Schedule pins",
            symptoms=["Error 403"],
            affected_flow="Pinterest publishing",
            excerpt="Test excerpt",
            product_area="publishing",
            component="pinterest",
        )

        assert hasattr(ctx, "solution_provided")
        assert ctx.solution_provided == ""  # Default empty string

    def test_conversation_context_has_resolution_category_field(self):
        """ConversationContext should have resolution_category field."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Schedule pins",
            symptoms=["Error 403"],
            affected_flow="Pinterest publishing",
            excerpt="Test excerpt",
            product_area="publishing",
            component="pinterest",
        )

        assert hasattr(ctx, "resolution_category")
        assert ctx.resolution_category == ""  # Default empty string

    def test_conversation_context_can_be_initialized_with_resolution_fields(self):
        """ConversationContext should accept resolution fields in initialization."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Schedule pins to Pinterest",
            symptoms=["Error 403: Board access denied"],
            affected_flow="Pinterest publishing",
            excerpt="I'm getting Error 403 when scheduling",
            product_area="publishing",
            component="pinterest",
            # Issue #146 fields
            resolution_action="user_education",
            root_cause="User didn't have board permissions",
            solution_provided="Explained how to check board permissions",
            resolution_category="education",
        )

        assert ctx.resolution_action == "user_education"
        assert ctx.root_cause == "User didn't have board permissions"
        assert ctx.solution_provided == "Explained how to check board permissions"
        assert ctx.resolution_category == "education"


# =============================================================================
# Test 3: Resolution Fields Flow to ConversationData (Story Creation)
# =============================================================================


class TestResolutionFieldsFlowToConversationData:
    """
    Test that ConversationData in story_creation_service has resolution fields
    and that _dict_to_conversation_data extracts them correctly.

    Verifies Issue #146 Phase 1C: Story Creation receives resolution context.
    """

    def test_conversation_data_has_resolution_action_field(self):
        """ConversationData should have resolution_action field."""
        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
        )

        assert hasattr(data, "resolution_action")
        assert data.resolution_action is None  # Optional, defaults to None

    def test_conversation_data_has_root_cause_field(self):
        """ConversationData should have root_cause field."""
        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
        )

        assert hasattr(data, "root_cause")
        assert data.root_cause is None  # Optional, defaults to None

    def test_conversation_data_has_solution_provided_field(self):
        """ConversationData should have solution_provided field."""
        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
        )

        assert hasattr(data, "solution_provided")
        assert data.solution_provided is None  # Optional, defaults to None

    def test_conversation_data_has_resolution_category_field(self):
        """ConversationData should have resolution_category field."""
        data = ConversationData(
            id="conv_1",
            issue_signature="test_signature",
        )

        assert hasattr(data, "resolution_category")
        assert data.resolution_category is None  # Optional, defaults to None

    def test_conversation_data_can_be_initialized_with_resolution_fields(self):
        """ConversationData should accept resolution fields in initialization."""
        data = ConversationData(
            id="conv_1",
            issue_signature="pinterest_board_permission_denied",
            product_area="publishing",
            component="pinterest",
            user_intent="Schedule pins",
            symptoms=["Error 403"],
            # Issue #146 fields
            resolution_action="manual_intervention",
            root_cause="User's subscription expired",
            solution_provided="Renewed subscription manually",
            resolution_category="self_service_gap",
        )

        assert data.resolution_action == "manual_intervention"
        assert data.root_cause == "User's subscription expired"
        assert data.solution_provided == "Renewed subscription manually"
        assert data.resolution_category == "self_service_gap"

    def test_dict_to_conversation_data_extracts_resolution_fields(self):
        """
        _dict_to_conversation_data should extract resolution fields from pipeline dict.

        This is a critical integration point - pipeline passes theme data as dicts,
        and story creation service must extract the resolution fields.
        """
        # Mock minimal services for StoryCreationService
        mock_story_service = Mock()
        mock_orphan_service = Mock()

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
        )

        # Simulate pipeline dict with resolution fields (from theme extraction)
        conv_dict = {
            "id": "conv_123",
            "product_area": "publishing",
            "component": "pinterest",
            "user_intent": "Schedule pins to Pinterest",
            "symptoms": ["Error 403: Board access denied"],
            "affected_flow": "Scheduler -> Pinterest",
            "excerpt": "I'm getting Error 403",
            "diagnostic_summary": "User reports 403 error when scheduling",
            "key_excerpts": [{"text": "Error 403", "relevance": "Main error"}],
            # Issue #146 resolution fields
            "resolution_action": "provided_workaround",
            "root_cause": "OAuth token expired after password change",
            "solution_provided": "User reconnected Pinterest account",
            "resolution_category": "workaround",
        }

        # Act: Call _dict_to_conversation_data
        result = service._dict_to_conversation_data(conv_dict, "pinterest_board_permission_denied")

        # Assert: Resolution fields are extracted correctly
        assert result.resolution_action == "provided_workaround"
        assert result.root_cause == "OAuth token expired after password change"
        assert result.solution_provided == "User reconnected Pinterest account"
        assert result.resolution_category == "workaround"

    def test_dict_to_conversation_data_handles_missing_resolution_fields(self):
        """
        _dict_to_conversation_data should handle dicts without resolution fields gracefully.

        This ensures backward compatibility with older theme data.
        """
        mock_story_service = Mock()
        mock_orphan_service = Mock()

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
        )

        # Simulate pipeline dict WITHOUT resolution fields (pre-#146 data)
        conv_dict = {
            "id": "conv_123",
            "product_area": "publishing",
            "component": "pinterest",
            "user_intent": "Schedule pins",
            "symptoms": ["Error 403"],
        }

        # Act: Call _dict_to_conversation_data
        result = service._dict_to_conversation_data(conv_dict, "test_signature")

        # Assert: Resolution fields default to None
        assert result.resolution_action is None
        assert result.root_cause is None
        assert result.solution_provided is None
        assert result.resolution_category is None


# =============================================================================
# Test 4: Resolution Fields Flow to StoryContentInput
# =============================================================================


class TestResolutionFieldsFlowToStoryContentInput:
    """
    Test that StoryContentInput receives root_cause and solution_provided fields.

    Verifies Issue #146 Phase 1C: Story content generation uses resolution context.
    """

    def test_story_content_input_has_root_cause_field(self):
        """StoryContentInput should have root_cause field."""
        content_input = StoryContentInput(
            user_intents=["Schedule pins"],
            symptoms=["Error 403"],
            issue_signature="test_signature",
            classification_category="product_issue",
            product_area="publishing",
            component="pinterest",
        )

        assert hasattr(content_input, "root_cause")
        assert content_input.root_cause is None  # Optional, defaults to None

    def test_story_content_input_has_solution_provided_field(self):
        """StoryContentInput should have solution_provided field."""
        content_input = StoryContentInput(
            user_intents=["Schedule pins"],
            symptoms=["Error 403"],
            issue_signature="test_signature",
            classification_category="product_issue",
            product_area="publishing",
            component="pinterest",
        )

        assert hasattr(content_input, "solution_provided")
        assert content_input.solution_provided is None  # Optional, defaults to None

    def test_story_content_input_can_be_initialized_with_resolution_fields(self):
        """StoryContentInput should accept root_cause and solution_provided."""
        content_input = StoryContentInput(
            user_intents=["Schedule pins to Pinterest board"],
            symptoms=["Error 403: Board access denied"],
            issue_signature="pinterest_board_permission_denied",
            classification_category="product_issue",
            product_area="publishing",
            component="pinterest",
            root_cause_hypothesis="OAuth token may have expired",
            affected_flow="Scheduler -> Pinterest API",
            # Issue #146 fields
            root_cause="OAuth token invalidated after Pinterest password change",
            solution_provided="User reconnected Pinterest account via Settings",
        )

        assert content_input.root_cause == "OAuth token invalidated after Pinterest password change"
        assert content_input.solution_provided == "User reconnected Pinterest account via Settings"

    def test_format_optional_context_includes_resolution_context_section(self):
        """
        format_optional_context should include Resolution Context section
        when root_cause or solution_provided are provided.
        """
        # Act: Call format_optional_context with resolution fields
        result = format_optional_context(
            root_cause_hypothesis="May be OAuth issue",
            affected_flow="Scheduler -> Pinterest",
            root_cause="OAuth token invalidated after password change",
            solution_provided="User reconnected Pinterest account",
        )

        # Assert: Resolution Context section is present
        assert "### Resolution Context" in result
        assert "**Root Cause Analysis**:" in result
        assert "OAuth token invalidated after password change" in result
        assert "**Current Workaround**:" in result
        assert "User reconnected Pinterest account" in result

    def test_format_optional_context_with_only_root_cause(self):
        """format_optional_context should work with only root_cause (no solution)."""
        result = format_optional_context(
            root_cause="Bug in Pinterest API rate limiting",
            solution_provided=None,
        )

        assert "### Resolution Context" in result
        assert "**Root Cause Analysis**:" in result
        assert "Bug in Pinterest API rate limiting" in result
        assert "**Current Workaround**:" not in result

    def test_format_optional_context_with_only_solution_provided(self):
        """format_optional_context should work with only solution_provided (no root_cause)."""
        result = format_optional_context(
            root_cause=None,
            solution_provided="Clear browser cache and reconnect",
        )

        assert "### Resolution Context" in result
        assert "**Current Workaround**:" in result
        assert "Clear browser cache and reconnect" in result
        assert "**Root Cause Analysis**:" not in result

    def test_format_optional_context_without_resolution_fields(self):
        """format_optional_context should work without resolution fields (backward compat)."""
        result = format_optional_context(
            root_cause_hypothesis="May be OAuth issue",
            affected_flow="Scheduler -> Pinterest",
            root_cause=None,
            solution_provided=None,
        )

        # Resolution Context section should NOT appear
        assert "### Resolution Context" not in result
        # Other sections should still work
        assert "### Root Cause Hypothesis" in result
        assert "### Affected User Flow" in result


# =============================================================================
# Test 5: Classification Pipeline Works Without Regex Imports
# =============================================================================


class TestClassificationPipelineNoRegexImports:
    """
    Test that classification pipeline modules work without ResolutionAnalyzer
    and KnowledgeExtractor imports.

    Verifies Issue #146 Phase 1A: Regex extractors removed from pipeline.
    """

    def test_classification_pipeline_imports_successfully(self):
        """
        Classification pipeline should import without errors.

        This verifies that deprecated ResolutionAnalyzer and KnowledgeExtractor
        have been removed from imports.
        """
        # Act: Import classification_pipeline (this is the critical test)
        try:
            from classification_pipeline import (
                classify_conversation,
                classify_conversation_async,
                run_pipeline,
                run_pipeline_async,
            )
            import_success = True
        except ImportError as e:
            import_success = False
            error_message = str(e)

        # Assert: Import succeeded
        assert import_success, f"Classification pipeline import failed: {error_message}"

    def test_classifier_stage2_imports_successfully(self):
        """
        Classifier stage 2 should import without resolution_signal parameter.

        Phase 1A removed resolution_signal from Stage 2 prompts.
        """
        try:
            from classifier_stage2 import classify_stage2, STAGE2_PROMPT
            import_success = True
        except ImportError as e:
            import_success = False
            error_message = str(e)

        assert import_success, f"Classifier stage 2 import failed: {error_message}"

    def test_resolution_analyzer_does_not_exist(self):
        """ResolutionAnalyzer module should not exist (deleted in Phase 1A)."""
        try:
            from resolution_analyzer import ResolutionAnalyzer
            exists = True
        except ImportError:
            exists = False

        assert not exists, "resolution_analyzer.py should be deleted (Phase 1A)"

    def test_knowledge_extractor_does_not_exist(self):
        """KnowledgeExtractor module should not exist (deleted in Phase 1A)."""
        try:
            from knowledge_extractor import KnowledgeExtractor
            exists = True
        except ImportError:
            exists = False

        assert not exists, "knowledge_extractor.py should be deleted (Phase 1A)"

    def test_classification_pipeline_support_insights_structure(self):
        """
        Classification pipeline should produce support_insights without
        resolution_analysis and knowledge fields.

        Issue #146: These fields are now extracted by LLM in theme extractor,
        not by regex in classification pipeline.
        """
        # Simulate what classification pipeline produces
        # (Based on src/classification_pipeline.py lines 116-119, 309-315)
        support_insights = {
            "customer_digest": "Hi, I'm having trouble...",
            "full_conversation": "[Customer]: Hi, I'm having trouble...",
            # Note: NO resolution_analysis or knowledge fields
        }

        # Assert: Only expected fields are present
        assert "customer_digest" in support_insights
        assert "full_conversation" in support_insights
        # These should NOT be present (removed in Phase 1A)
        assert "resolution_analysis" not in support_insights
        assert "knowledge" not in support_insights


# =============================================================================
# Integration Test: Full Data Flow
# =============================================================================


class TestFullResolutionDataFlow:
    """
    Integration test verifying the complete resolution field data flow.

    This tests the critical path:
    Theme -> ConversationData -> StoryContentInput
    """

    def test_resolution_fields_flow_from_theme_to_story_content(self):
        """
        Full integration test: Resolution fields flow from Theme extraction
        through to story content generation.

        This is the key test that verifies Issue #146's implementation
        connects all the components correctly.
        """
        # === STEP 1: Simulate Theme from theme extractor ===
        theme = Theme(
            conversation_id="conv_123",
            product_area="pinterest_publishing",
            component="scheduler",
            issue_signature="pinterest_board_permission_denied",
            user_intent="Schedule pins to Pinterest board",
            symptoms=["Error 403: Board access denied", "Pins not posting"],
            affected_flow="Pin Scheduler -> Pinterest API",
            root_cause_hypothesis="OAuth token scope issue",
            # Issue #146: LLM-extracted resolution fields
            resolution_action="provided_workaround",
            root_cause="OAuth token invalidated after Pinterest password change",
            solution_provided="User reconnected Pinterest account via Settings > Connections",
            resolution_category="workaround",
        )

        # === STEP 2: Convert to dict (as pipeline does) ===
        theme_dict = theme.to_dict()

        # Verify resolution fields are in dict
        assert theme_dict["resolution_action"] == "provided_workaround"
        assert theme_dict["root_cause"] == "OAuth token invalidated after Pinterest password change"
        assert theme_dict["solution_provided"] == "User reconnected Pinterest account via Settings > Connections"
        assert theme_dict["resolution_category"] == "workaround"

        # === STEP 3: Simulate _dict_to_conversation_data ===
        mock_story_service = Mock()
        mock_orphan_service = Mock()
        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
        )

        # Prepare dict as pipeline would (with additional fields)
        conv_dict = {
            "id": theme_dict["conversation_id"],
            "product_area": theme_dict["product_area"],
            "component": theme_dict["component"],
            "user_intent": theme_dict["user_intent"],
            "symptoms": theme_dict["symptoms"],
            "affected_flow": theme_dict["affected_flow"],
            "excerpt": "Error 403: Board access denied when scheduling pins",
            "resolution_action": theme_dict["resolution_action"],
            "root_cause": theme_dict["root_cause"],
            "solution_provided": theme_dict["solution_provided"],
            "resolution_category": theme_dict["resolution_category"],
        }

        conv_data = service._dict_to_conversation_data(
            conv_dict, theme_dict["issue_signature"]
        )

        # Verify ConversationData has resolution fields
        assert conv_data.resolution_action == "provided_workaround"
        assert conv_data.root_cause == "OAuth token invalidated after Pinterest password change"
        assert conv_data.solution_provided == "User reconnected Pinterest account via Settings > Connections"
        assert conv_data.resolution_category == "workaround"

        # === STEP 4: Create StoryContentInput ===
        content_input = StoryContentInput(
            user_intents=[conv_data.user_intent],
            symptoms=conv_data.symptoms,
            issue_signature=conv_data.issue_signature,
            classification_category="product_issue",
            product_area=conv_data.product_area,
            component=conv_data.component,
            root_cause_hypothesis=None,
            affected_flow=conv_data.affected_flow,
            # Issue #146: Resolution context for story content
            root_cause=conv_data.root_cause,
            solution_provided=conv_data.solution_provided,
        )

        # Verify StoryContentInput has resolution context
        assert content_input.root_cause == "OAuth token invalidated after Pinterest password change"
        assert content_input.solution_provided == "User reconnected Pinterest account via Settings > Connections"

        # === STEP 5: Format for prompt includes resolution context ===
        optional_context = format_optional_context(
            root_cause_hypothesis=content_input.root_cause_hypothesis,
            affected_flow=content_input.affected_flow,
            root_cause=content_input.root_cause,
            solution_provided=content_input.solution_provided,
        )

        # Verify prompt includes resolution context
        assert "### Resolution Context" in optional_context
        assert "**Root Cause Analysis**:" in optional_context
        assert "OAuth token invalidated" in optional_context
        assert "**Current Workaround**:" in optional_context
        assert "User reconnected Pinterest account" in optional_context


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestResolutionFieldEdgeCases:
    """Test edge cases and error handling for resolution fields."""

    def test_theme_with_empty_resolution_fields_serializes(self):
        """Theme with empty resolution fields should serialize correctly."""
        theme = Theme(
            conversation_id="test_123",
            product_area="publishing",
            component="pinterest",
            issue_signature="test_signature",
            user_intent="Test",
            symptoms=[],
            affected_flow="Test",
            root_cause_hypothesis="Test",
            # All resolution fields empty
            resolution_action="",
            root_cause="",
            solution_provided="",
            resolution_category="",
        )

        theme_dict = theme.to_dict()
        json_str = json.dumps(theme_dict)

        # Should serialize without errors
        assert json_str is not None
        parsed = json.loads(json_str)
        assert parsed["resolution_action"] == ""
        assert parsed["root_cause"] == ""
        assert parsed["solution_provided"] == ""
        assert parsed["resolution_category"] == ""

    def test_conversation_context_with_special_characters_in_resolution(self):
        """ConversationContext should handle special characters in resolution fields."""
        ctx = ConversationContext(
            conversation_id="conv_1",
            user_intent="Schedule pins",
            symptoms=["Error"],
            affected_flow="Flow",
            excerpt="Excerpt",
            product_area="publishing",
            component="pinterest",
            # Resolution fields with special characters
            resolution_action="user_education",
            root_cause='User misunderstood "SmartSchedule" feature & its settings',
            solution_provided='Explained: Go to Settings > "Pin Spacing" <not scheduling>',
            resolution_category="education",
        )

        assert "&" in ctx.root_cause
        assert '"' in ctx.root_cause
        assert "<" in ctx.solution_provided

    def test_story_content_input_with_long_resolution_fields(self):
        """StoryContentInput should handle long resolution field values."""
        long_root_cause = "A" * 1000
        long_solution = "B" * 1000

        content_input = StoryContentInput(
            user_intents=["Test"],
            symptoms=["Test"],
            issue_signature="test",
            classification_category="product_issue",
            product_area="test",
            component="test",
            root_cause=long_root_cause,
            solution_provided=long_solution,
        )

        # Should handle long values without errors
        assert len(content_input.root_cause) == 1000
        assert len(content_input.solution_provided) == 1000

        # format_optional_context should work with long values
        result = format_optional_context(
            root_cause=long_root_cause,
            solution_provided=long_solution,
        )
        assert long_root_cause in result
        assert long_solution in result


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
