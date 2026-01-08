"""
Tests for Shortcut story extraction (Phase 4b).

Tests the ShortcutStoryExtractor's ability to:
1. Extract Story ID v2 from conversation custom attributes
2. Fetch story metadata from Shortcut API
3. Format story context for prompt injection
"""

import pytest
from unittest.mock import Mock, patch

from src.shortcut_story_extractor import ShortcutStory, ShortcutStoryExtractor


# Test fixtures

@pytest.fixture
def extractor():
    """Create a ShortcutStoryExtractor instance with mocked API."""
    with patch.dict('os.environ', {'SHORTCUT_API_TOKEN': 'test_token'}):
        return ShortcutStoryExtractor()


@pytest.fixture
def sample_conversation_with_story():
    """Sample conversation that has Story ID v2."""
    return {
        "id": "12345",
        "custom_attributes": {
            "story_id_v2": "sc-98765"
        },
        "source": {
            "type": "conversation",
            "body": "My posts aren't scheduling correctly."
        }
    }


@pytest.fixture
def sample_conversation_without_story():
    """Sample conversation with no Story ID v2."""
    return {
        "id": "67890",
        "custom_attributes": {},
        "source": {
            "type": "conversation",
            "body": "How do I use the scheduler?"
        }
    }


@pytest.fixture
def sample_story_response():
    """Sample story response from Shortcut API."""
    return {
        "id": 98765,
        "name": "Instagram posts not scheduling at correct times",
        "description": "Users report that scheduled Instagram posts are posting 1-2 hours late...",
        "labels": [
            {"id": 1, "name": "Instagram"},
            {"id": 2, "name": "Scheduling"},
            {"id": 3, "name": "Bug"}
        ],
        "epic_id": 42,
        "workflow_state_id": 500000123,
        "story_type": "bug"
    }


# Tests

class TestStoryIDExtraction:
    """Test extraction of Story ID v2 from conversations."""

    def test_extract_story_id_with_prefix(self, extractor, sample_conversation_with_story):
        """Should extract story ID and strip 'sc-' prefix."""
        story_id = extractor.get_story_id_from_conversation(sample_conversation_with_story)

        assert story_id == "98765"

    def test_extract_story_id_without_prefix(self, extractor):
        """Should handle story ID without prefix."""
        conversation = {
            "id": "test",
            "custom_attributes": {
                "story_id_v2": "12345"
            }
        }

        story_id = extractor.get_story_id_from_conversation(conversation)

        assert story_id == "12345"

    def test_extract_no_story_id(self, extractor, sample_conversation_without_story):
        """Should return None when no Story ID v2."""
        story_id = extractor.get_story_id_from_conversation(sample_conversation_without_story)

        assert story_id is None

    def test_extract_story_id_whitespace(self, extractor):
        """Should strip whitespace from story ID."""
        conversation = {
            "id": "test",
            "custom_attributes": {
                "story_id_v2": "  sc-999  "
            }
        }

        story_id = extractor.get_story_id_from_conversation(conversation)

        assert story_id == "999"

    def test_extract_story_id_missing_custom_attributes(self, extractor):
        """Should handle missing custom_attributes gracefully."""
        conversation = {
            "id": "test",
            "source": {"body": "Test"}
        }

        story_id = extractor.get_story_id_from_conversation(conversation)

        assert story_id is None


class TestStoryMetadataFetching:
    """Test fetching story metadata from Shortcut API."""

    @patch('requests.get')
    def test_fetch_story_metadata_success(self, mock_get, extractor, sample_story_response):
        """Should fetch and parse story metadata from API."""
        mock_response = Mock()
        mock_response.json.return_value = sample_story_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        story = extractor.fetch_story_metadata("98765")

        assert story is not None
        assert story.story_id == "98765"
        assert story.name == "Instagram posts not scheduling at correct times"
        assert "Instagram" in story.labels
        assert "Scheduling" in story.labels
        assert "Bug" in story.labels
        assert story.epic_name == "Epic 42"  # Placeholder format
        assert story.description is not None

    @patch('requests.get')
    def test_fetch_story_metadata_failure(self, mock_get, extractor):
        """Should return None when API fetch fails."""
        mock_get.side_effect = Exception("API error")

        story = extractor.fetch_story_metadata("12345")

        assert story is None


class TestLabelExtraction:
    """Test extraction of labels from story data."""

    def test_extract_labels_from_objects(self, extractor):
        """Should extract label names from label objects."""
        story_data = {
            "labels": [
                {"id": 1, "name": "Instagram"},
                {"id": 2, "name": "Bug"}
            ]
        }

        labels = extractor._extract_labels(story_data)

        assert labels == ["Instagram", "Bug"]

    def test_extract_labels_from_strings(self, extractor):
        """Should handle labels as strings."""
        story_data = {
            "labels": ["Instagram", "Bug"]
        }

        labels = extractor._extract_labels(story_data)

        assert labels == ["Instagram", "Bug"]

    def test_extract_labels_empty(self, extractor):
        """Should return empty list when no labels."""
        story_data = {"labels": []}

        labels = extractor._extract_labels(story_data)

        assert labels == []

    def test_extract_labels_missing(self, extractor):
        """Should return empty list when labels field missing."""
        story_data = {}

        labels = extractor._extract_labels(story_data)

        assert labels == []


class TestEpicExtraction:
    """Test extraction of epic information."""

    def test_extract_epic_name_present(self, extractor):
        """Should extract epic ID when present."""
        story_data = {"epic_id": 42}

        epic_name = extractor._extract_epic_name(story_data)

        assert epic_name == "Epic 42"

    def test_extract_epic_name_missing(self, extractor):
        """Should return None when no epic."""
        story_data = {}

        epic_name = extractor._extract_epic_name(story_data)

        assert epic_name is None


class TestPromptFormatting:
    """Test formatting of story context for LLM prompts."""

    def test_format_complete_story(self, extractor):
        """Should format complete story with all fields."""
        story = ShortcutStory(
            story_id="98765",
            name="Instagram posts not scheduling",
            description="Users report posts scheduling late...",
            labels=["Instagram", "Scheduling", "Bug"],
            epic_name="Publisher Improvements",
            workflow_state_name="In Development"
        )

        formatted = extractor.format_for_prompt(story)

        assert "The support team has already categorized this conversation:" in formatted
        assert "Linked Shortcut Story: 98765" in formatted
        assert "Labels: Instagram, Scheduling, Bug" in formatted
        assert "Epic: Publisher Improvements" in formatted
        assert "Name: \"Instagram posts not scheduling\"" in formatted
        assert "Description: \"Users report posts scheduling late...\"" in formatted
        assert "State: In Development" in formatted
        assert "This provides validated product area context." in formatted

    def test_format_minimal_story(self, extractor):
        """Should format story with only required fields."""
        story = ShortcutStory(
            story_id="12345",
            name="Test story"
        )

        formatted = extractor.format_for_prompt(story)

        assert "Linked Shortcut Story: 12345" in formatted
        assert "Name: \"Test story\"" in formatted
        # Should not include optional fields
        assert "Labels:" not in formatted
        assert "Epic:" not in formatted
        assert "Description:" not in formatted

    def test_format_story_long_description(self, extractor):
        """Should truncate long descriptions to 500 chars."""
        long_desc = "A" * 600
        story = ShortcutStory(
            story_id="999",
            name="Test",
            description=long_desc
        )

        formatted = extractor.format_for_prompt(story)

        # Description should be truncated
        assert "..." in formatted
        # Should not exceed 500 + "..." = 503 chars in description line
        desc_line = [line for line in formatted.split("\n") if "Description:" in line][0]
        assert len(desc_line) < 530  # 500 + formatting overhead ("  - Description: " + quotes + "...")

    def test_format_none_story(self, extractor):
        """Should return empty string for None story."""
        formatted = extractor.format_for_prompt(None)

        assert formatted == ""


class TestEndToEndExtraction:
    """Test end-to-end extraction and formatting."""

    @patch('requests.get')
    def test_extract_and_format(self, mock_get, extractor, sample_conversation_with_story, sample_story_response):
        """Should extract Story ID, fetch metadata, and format in one step."""
        mock_response = Mock()
        mock_response.json.return_value = sample_story_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        formatted = extractor.extract_and_format(sample_conversation_with_story)

        # Should have called API
        assert mock_get.called

        # Should format for prompt
        assert "The support team has already categorized this conversation:" in formatted
        assert "Instagram posts not scheduling at correct times" in formatted
        assert "Instagram" in formatted

    def test_extract_and_format_no_story(self, extractor, sample_conversation_without_story):
        """Should return empty string when no Story ID v2."""
        formatted = extractor.extract_and_format(sample_conversation_without_story)

        assert formatted == ""

    @patch('requests.get')
    def test_extract_and_format_api_failure(self, mock_get, extractor, sample_conversation_with_story):
        """Should return empty string when API fetch fails."""
        mock_get.side_effect = Exception("API error")

        formatted = extractor.extract_and_format(sample_conversation_with_story)

        assert formatted == ""


# Integration test markers
pytestmark = pytest.mark.unit
