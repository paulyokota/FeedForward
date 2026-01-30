"""
Orphan Integration Tests

Tests for OrphanIntegrationService - Issue #176 fix.
Run with: pytest tests/test_orphan_integration.py -v
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.services.orphan_integration import (
    OrphanIntegrationResult,
    OrphanIntegrationService,
)


# -----------------------------------------------------------------------------
# OrphanIntegrationResult Tests
# -----------------------------------------------------------------------------


class TestOrphanIntegrationResult:
    """Tests for OrphanIntegrationResult dataclass."""

    def test_stories_appended_counter_exists(self):
        """stories_appended field should exist and default to 0."""
        result = OrphanIntegrationResult()

        assert hasattr(result, "stories_appended")
        assert result.stories_appended == 0

    def test_stories_appended_increments_independently(self):
        """stories_appended should be distinct from stories_graduated."""
        result = OrphanIntegrationResult(
            total_processed=5,
            orphans_created=1,
            orphans_updated=2,
            stories_graduated=1,
            stories_appended=1,
        )

        assert result.stories_graduated == 1
        assert result.stories_appended == 1
        assert result.total_processed == 5

    def test_errors_default_to_empty_list(self):
        """errors field should default to empty list."""
        result = OrphanIntegrationResult()

        assert result.errors == []


class TestOrphanIntegrationServiceInit:
    """Tests for OrphanIntegrationService initialization."""

    def test_init_creates_evidence_service(self):
        """Should create EvidenceService and pass to matcher."""
        mock_db = Mock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        # Patch at the location where it's imported (inside __init__)
        with patch("orphan_matcher.OrphanMatcher") as MockMatcher:
            with patch("signature_utils.get_registry"):
                service = OrphanIntegrationService(mock_db)

                # Verify EvidenceService was created and passed to matcher
                call_kwargs = MockMatcher.call_args.kwargs
                assert "evidence_service" in call_kwargs
                assert call_kwargs["evidence_service"] is not None


class TestProcessThemesWithStoriesAppended:
    """Tests for process_themes counting stories_appended action."""

    @pytest.fixture
    def mock_integration_service(self):
        """Create a mock-based integration service for testing."""
        mock_db = Mock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        # Patch at the location where it's imported (inside __init__)
        with patch("orphan_matcher.OrphanMatcher") as MockMatcher:
            with patch("signature_utils.get_registry"):
                service = OrphanIntegrationService(mock_db)
                # Return the service with the mock matcher attached
                yield service

    def test_process_themes_counts_added_to_story(self, mock_integration_service):
        """stories_appended should increment for added_to_story action."""
        from orphan_matcher import MatchResult

        # Mock matcher to return added_to_story action
        mock_integration_service.matcher.match_and_accumulate.return_value = MatchResult(
            matched=True,
            orphan_id="123",
            orphan_signature="test_sig",
            action="added_to_story",
            story_id="456",
        )

        themes = [
            {"conversation_id": "conv1", "issue_signature": "test_sig"},
            {"conversation_id": "conv2", "issue_signature": "test_sig"},
        ]

        result = mock_integration_service.process_themes(themes)

        assert result.total_processed == 2
        assert result.stories_appended == 2
        assert result.stories_graduated == 0
        assert result.orphans_created == 0

    def test_process_themes_counts_graduated_separately(self, mock_integration_service):
        """stories_graduated and stories_appended should be counted separately."""
        from orphan_matcher import MatchResult

        # First theme graduates, second appends to story
        mock_integration_service.matcher.match_and_accumulate.side_effect = [
            MatchResult(
                matched=True,
                action="graduated",
                story_id="story1",
            ),
            MatchResult(
                matched=True,
                action="added_to_story",
                story_id="story2",
            ),
        ]

        themes = [
            {"conversation_id": "conv1", "issue_signature": "sig1"},
            {"conversation_id": "conv2", "issue_signature": "sig2"},
        ]

        result = mock_integration_service.process_themes(themes)

        assert result.total_processed == 2
        assert result.stories_graduated == 1
        assert result.stories_appended == 1
