"""
Orphan Graduation Evidence Integration Tests

Issue #197: Raise story evidence quality

Tests the full flow from orphan graduation to evidence bundle creation:
1. Create themes with diagnostic_summary for test conversations
2. Create orphan with those conversation_ids
3. Graduate orphan via OrphanIntegrationService
4. Verify story_evidence bundle is created with excerpts
5. Verify story.excerpt_count > 0

Run with: pytest tests/story_tracking/test_orphan_graduation_evidence.py -v
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.services.orphan_integration import (
    OrphanIntegrationService,
    INTERCOM_APP_ID,
    INTERCOM_URL_TEMPLATE,
)
from story_tracking.models import EvidenceExcerpt


class TestIntercomUrlGeneration:
    """Tests for Intercom URL generation."""

    def test_build_intercom_url(self):
        """Should build correct Intercom URL from conversation ID."""
        mock_db = Mock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("orphan_matcher.OrphanMatcher"):
            with patch("signature_utils.get_registry"):
                service = OrphanIntegrationService(mock_db)

        url = service._build_intercom_url("conv_123")

        expected = INTERCOM_URL_TEMPLATE.format(
            app_id=INTERCOM_APP_ID,
            conversation_id="conv_123",
        )
        assert url == expected
        assert "conv_123" in url


class TestCreateEvidenceForGraduatedStory:
    """Tests for _create_evidence_for_graduated_story method."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock-based integration service for testing."""
        mock_db = Mock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("orphan_matcher.OrphanMatcher"):
            with patch("signature_utils.get_registry"):
                service = OrphanIntegrationService(mock_db)
                service._mock_cursor = mock_cursor
                yield service

    def test_returns_false_when_no_conversation_ids(self, mock_service):
        """Should return False when conversation_ids is empty."""
        result = mock_service._create_evidence_for_graduated_story(
            story_id=uuid4(),
            orphan_signature="test_sig",
            conversation_ids=[],
        )
        assert result is False

    def test_returns_false_when_no_theme_data(self, mock_service):
        """Should return False when no theme data found."""
        mock_service._mock_cursor.fetchall.return_value = []

        result = mock_service._create_evidence_for_graduated_story(
            story_id=uuid4(),
            orphan_signature="test_sig",
            conversation_ids=["conv1", "conv2"],
        )
        assert result is False

    def test_creates_evidence_with_diagnostic_summary(self, mock_service):
        """Should create evidence excerpts from diagnostic_summary with all metadata."""
        story_id = uuid4()
        # Mock theme data from DB
        mock_service._mock_cursor.fetchall.return_value = [
            {
                "issue_signature": "test_sig",
                "conversation_id": "conv1",
                "diagnostic_summary": "User cannot access billing page",
                "key_excerpts": [],
                "source_body": "...",
                "contact_email": "test@example.com",
                "contact_id": "contact_1",
                "user_id": "user_1",
                "org_id": "org_1",
            }
        ]

        # Mock the evidence_service.create_or_update
        mock_service.evidence_service = Mock()

        result = mock_service._create_evidence_for_graduated_story(
            story_id=story_id,
            orphan_signature="test_sig",
            conversation_ids=["conv1"],
        )

        assert result is True

        # Verify create_or_update was called with correct args
        mock_service.evidence_service.create_or_update.assert_called_once()
        call_kwargs = mock_service.evidence_service.create_or_update.call_args.kwargs

        assert call_kwargs["story_id"] == story_id
        assert call_kwargs["conversation_ids"] == ["conv1"]
        assert "test_sig" in call_kwargs["theme_signatures"]
        assert call_kwargs["source_stats"] == {"intercom": 1}

        # Check excerpts - verify ALL metadata fields are populated (Issue #197 fix)
        excerpts = call_kwargs["excerpts"]
        assert len(excerpts) == 1
        assert excerpts[0].text == "User cannot access billing page"
        assert excerpts[0].source == "intercom"
        assert excerpts[0].conversation_id == "conv1"
        assert excerpts[0].email == "test@example.com"
        assert excerpts[0].org_id == "org_1"
        assert excerpts[0].user_id == "user_1"
        assert excerpts[0].contact_id == "contact_1"
        # Verify intercom_url is built
        assert excerpts[0].intercom_url is not None
        assert "conv1" in excerpts[0].intercom_url

    def test_creates_evidence_with_key_excerpts(self, mock_service):
        """Should create evidence excerpts from key_excerpts."""
        story_id = uuid4()
        mock_service._mock_cursor.fetchall.return_value = [
            {
                "issue_signature": "test_sig",
                "conversation_id": "conv1",
                "diagnostic_summary": "Main summary",
                "key_excerpts": [
                    {"text": "First excerpt"},
                    {"text": "Second excerpt"},
                ],
                "source_body": "...",
                "contact_email": "test@example.com",
                "contact_id": None,
                "user_id": None,
                "org_id": None,
            }
        ]

        mock_service.evidence_service = Mock()

        result = mock_service._create_evidence_for_graduated_story(
            story_id=story_id,
            orphan_signature="test_sig",
            conversation_ids=["conv1"],
        )

        assert result is True

        call_kwargs = mock_service.evidence_service.create_or_update.call_args.kwargs
        excerpts = call_kwargs["excerpts"]

        # Should have 1 diagnostic_summary + 2 key_excerpts = 3 total
        assert len(excerpts) == 3
        assert excerpts[0].text == "Main summary"
        assert excerpts[1].text == "First excerpt"
        assert excerpts[2].text == "Second excerpt"

    def test_collects_multiple_theme_signatures(self, mock_service):
        """Should collect all unique theme signatures."""
        story_id = uuid4()
        mock_service._mock_cursor.fetchall.return_value = [
            {
                "issue_signature": "sig_from_conv1",
                "conversation_id": "conv1",
                "diagnostic_summary": "Summary 1",
                "key_excerpts": [],
                "source_body": "...",
                "contact_email": None,
                "contact_id": None,
                "user_id": None,
                "org_id": None,
            },
            {
                "issue_signature": "sig_from_conv2",
                "conversation_id": "conv2",
                "diagnostic_summary": "Summary 2",
                "key_excerpts": [],
                "source_body": "...",
                "contact_email": None,
                "contact_id": None,
                "user_id": None,
                "org_id": None,
            },
        ]

        mock_service.evidence_service = Mock()

        mock_service._create_evidence_for_graduated_story(
            story_id=story_id,
            orphan_signature="orphan_sig",
            conversation_ids=["conv1", "conv2"],
        )

        call_kwargs = mock_service.evidence_service.create_or_update.call_args.kwargs
        theme_sigs = set(call_kwargs["theme_signatures"])

        # Should have orphan_sig + both conversation signatures
        assert "orphan_sig" in theme_sigs
        assert "sig_from_conv1" in theme_sigs
        assert "sig_from_conv2" in theme_sigs


class TestProcessThemeWithGraduation:
    """Tests for process_theme calling _create_evidence_for_graduated_story."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock-based integration service for testing."""
        mock_db = Mock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        with patch("orphan_matcher.OrphanMatcher") as MockMatcher:
            with patch("signature_utils.get_registry"):
                service = OrphanIntegrationService(mock_db)
                service._mock_cursor = mock_cursor
                yield service

    def test_creates_evidence_on_graduation(self, mock_service):
        """Should call _create_evidence_for_graduated_story when action is graduated."""
        from orphan_matcher import MatchResult

        story_id = str(uuid4())

        # Mock matcher to return graduated action
        mock_service.matcher.match_and_accumulate.return_value = MatchResult(
            matched=True,
            orphan_id="orphan_123",
            orphan_signature="test_sig",
            action="graduated",
            story_id=story_id,
            conversation_ids=["conv1", "conv2"],
        )

        # Mock _create_evidence_for_graduated_story
        mock_service._create_evidence_for_graduated_story = Mock(return_value=True)

        result = mock_service.process_theme(
            conversation_id="conv_trigger",
            theme_data={
                "issue_signature": "test_sig",
                "user_intent": "access billing",
            },
        )

        assert result.action == "graduated"
        assert result.story_id == story_id

        # Verify evidence creation was called
        mock_service._create_evidence_for_graduated_story.assert_called_once()
        call_args = mock_service._create_evidence_for_graduated_story.call_args
        assert str(call_args.kwargs["story_id"]) == story_id
        assert call_args.kwargs["orphan_signature"] == "test_sig"
        assert call_args.kwargs["conversation_ids"] == ["conv1", "conv2"]

    def test_does_not_create_evidence_on_non_graduation(self, mock_service):
        """Should NOT call _create_evidence when action is not graduated."""
        from orphan_matcher import MatchResult

        # Mock matcher to return created action (not graduated)
        mock_service.matcher.match_and_accumulate.return_value = MatchResult(
            matched=True,
            orphan_id="orphan_123",
            orphan_signature="test_sig",
            action="created",
        )

        mock_service._create_evidence_for_graduated_story = Mock()

        mock_service.process_theme(
            conversation_id="conv1",
            theme_data={"issue_signature": "test_sig"},
        )

        # Should NOT be called for non-graduation
        mock_service._create_evidence_for_graduated_story.assert_not_called()


class TestEvidenceServiceAddConversationSignature:
    """Tests for add_conversation populating theme_signatures."""

    def test_add_conversation_with_theme_signature(self):
        """Should populate theme_signatures when signature is provided."""
        from story_tracking.services.evidence_service import EvidenceService

        mock_db = Mock()
        mock_cursor = MagicMock()

        # First fetchone returns None (no existing evidence)
        # Second fetchone returns the new evidence after INSERT
        story_id = uuid4()
        mock_cursor.fetchone.side_effect = [
            None,  # First check for existing evidence
            {  # After INSERT RETURNING
                "id": uuid4(),
                "story_id": story_id,
                "conversation_ids": ["conv1"],
                "theme_signatures": ["test_sig"],
                "source_stats": {"intercom": 1},
                "excerpts": [],
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            },
        ]
        mock_db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = Mock(return_value=False)

        service = EvidenceService(mock_db)

        result = service.add_conversation(
            story_id=story_id,
            conversation_id="conv1",
            source="intercom",
            excerpt="Test excerpt",
            theme_signature="test_sig",
        )

        # Verify INSERT was called with theme_signature in the array
        insert_call = None
        for call_obj in mock_cursor.execute.call_args_list:
            sql = call_obj[0][0]
            if "INSERT INTO story_evidence" in sql:
                insert_call = call_obj
                break

        assert insert_call is not None, "INSERT INTO story_evidence not found in SQL calls"
        # The theme_signatures should be ["test_sig"]
        args = insert_call[0][1]
        assert ["test_sig"] in args, f"theme_signatures not found in args: {args}"


class TestExcerptCountInStoryService:
    """Tests for excerpt_count field in story_service."""

    def test_row_to_story_includes_excerpt_count(self):
        """_row_to_story should map excerpt_count from DB row."""
        from story_tracking.services.story_service import StoryService

        mock_db = Mock()
        service = StoryService(mock_db)

        # Create a mock row with excerpt_count
        mock_row = {
            "id": uuid4(),
            "title": "Test Story",
            "description": "Description",
            "labels": [],
            "priority": None,
            "severity": None,
            "product_area": None,
            "technical_area": None,
            "status": "candidate",
            "confidence_score": None,
            "actionability_score": None,
            "fix_size_score": None,
            "severity_score": None,
            "churn_risk_score": None,
            "score_metadata": None,
            "code_context": None,
            "implementation_context": None,
            "evidence_count": 2,
            "conversation_count": 5,
            "excerpt_count": 7,  # The new field
            "grouping_method": "signature",
            "cluster_id": None,
            "cluster_metadata": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        story = service._row_to_story(mock_row)

        assert story.excerpt_count == 7

    def test_row_to_story_defaults_excerpt_count_to_zero(self):
        """_row_to_story should default excerpt_count to 0 if missing."""
        from story_tracking.services.story_service import StoryService

        mock_db = Mock()
        service = StoryService(mock_db)

        # Create a mock row WITHOUT excerpt_count (legacy data)
        mock_row = {
            "id": uuid4(),
            "title": "Test Story",
            "description": "Description",
            "labels": [],
            "priority": None,
            "severity": None,
            "product_area": None,
            "technical_area": None,
            "status": "candidate",
            "confidence_score": None,
            "actionability_score": None,
            "fix_size_score": None,
            "severity_score": None,
            "churn_risk_score": None,
            "score_metadata": None,
            "code_context": None,
            "implementation_context": None,
            "evidence_count": 2,
            "conversation_count": 5,
            # excerpt_count missing
            "grouping_method": "signature",
            "cluster_id": None,
            "cluster_metadata": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        story = service._row_to_story(mock_row)

        # Should default to 0
        assert story.excerpt_count == 0


class TestEvidenceExcerptMetadataPreservation:
    """Tests that evidence excerpt metadata is preserved through read/write cycle."""

    def test_row_to_evidence_preserves_all_metadata(self):
        """_row_to_evidence should deserialize all metadata fields."""
        from story_tracking.services.evidence_service import EvidenceService

        mock_db = Mock()
        service = EvidenceService(mock_db)

        # Create a mock row with full excerpt metadata
        mock_row = {
            "id": uuid4(),
            "story_id": uuid4(),
            "conversation_ids": ["conv1"],
            "theme_signatures": ["test_sig"],
            "source_stats": {"intercom": 1},
            "excerpts": [
                {
                    "text": "Test excerpt",
                    "source": "intercom",
                    "conversation_id": "conv1",
                    "email": "user@example.com",
                    "intercom_url": "https://app.intercom.com/...",
                    "org_id": "org_123",
                    "user_id": "user_456",
                    "contact_id": "contact_789",
                }
            ],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        evidence = service._row_to_evidence(mock_row)

        # Verify all metadata fields are preserved
        assert len(evidence.excerpts) == 1
        excerpt = evidence.excerpts[0]
        assert excerpt.text == "Test excerpt"
        assert excerpt.source == "intercom"
        assert excerpt.conversation_id == "conv1"
        assert excerpt.email == "user@example.com"
        assert excerpt.intercom_url == "https://app.intercom.com/..."
        assert excerpt.org_id == "org_123"
        assert excerpt.user_id == "user_456"
        assert excerpt.contact_id == "contact_789"

    def test_row_to_evidence_handles_empty_excerpts(self):
        """_row_to_evidence should handle empty or NULL excerpts gracefully."""
        from story_tracking.services.evidence_service import EvidenceService

        mock_db = Mock()
        service = EvidenceService(mock_db)

        # Test with empty list
        mock_row = {
            "id": uuid4(),
            "story_id": uuid4(),
            "conversation_ids": ["conv1"],
            "theme_signatures": ["test_sig"],
            "source_stats": {"intercom": 1},
            "excerpts": [],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        evidence = service._row_to_evidence(mock_row)
        assert evidence.excerpts == []

        # Test with None
        mock_row["excerpts"] = None
        evidence = service._row_to_evidence(mock_row)
        assert evidence.excerpts == []

    def test_row_to_evidence_handles_string_excerpts(self):
        """_row_to_evidence should handle legacy string format excerpts."""
        from story_tracking.services.evidence_service import EvidenceService

        mock_db = Mock()
        service = EvidenceService(mock_db)

        # Test with mixed dict and string excerpts (legacy data)
        mock_row = {
            "id": uuid4(),
            "story_id": uuid4(),
            "conversation_ids": ["conv1"],
            "theme_signatures": ["test_sig"],
            "source_stats": {"intercom": 1},
            "excerpts": [
                {"text": "Dict excerpt", "source": "intercom"},
                "String excerpt from legacy data",
                {"text": "Another dict", "source": "coda"},
                "  ",  # Whitespace-only should be skipped
            ],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        evidence = service._row_to_evidence(mock_row)

        # Should have 3 excerpts (2 dicts + 1 non-empty string)
        assert len(evidence.excerpts) == 3
        assert evidence.excerpts[0].text == "Dict excerpt"
        assert evidence.excerpts[0].source == "intercom"
        assert evidence.excerpts[1].text == "String excerpt from legacy data"
        assert evidence.excerpts[1].source == "unknown"  # Legacy strings get "unknown" source
        assert evidence.excerpts[2].text == "Another dict"
