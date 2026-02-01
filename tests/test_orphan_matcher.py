"""
Orphan Matcher Tests

Tests for OrphanMatcher - matching conversations to orphans.
Run with: pytest tests/test_orphan_matcher.py -v
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from orphan_matcher import ExtractedTheme, MatchResult, OrphanMatcher
from signature_utils import SignatureRegistry
from story_tracking.models import (
    MIN_GROUP_SIZE,
    Orphan,
    OrphanGraduationResult,
    Story,
)
from story_tracking.services import OrphanService, StoryService


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_orphan_service():
    """Create a mock orphan service."""
    service = Mock(spec=OrphanService)
    return service


@pytest.fixture
def mock_story_service():
    """Create a mock story service."""
    service = Mock(spec=StoryService)
    return service


@pytest.fixture
def mock_signature_registry():
    """Create a mock signature registry."""
    registry = Mock(spec=SignatureRegistry)
    # By default, return the same signature (no equivalence)
    registry.get_canonical.side_effect = lambda sig: sig
    return registry


@pytest.fixture
def sample_orphan():
    """Sample orphan with 2 conversations (below MIN_GROUP_SIZE)."""
    return Orphan(
        id=uuid4(),
        signature="billing_cancellation",
        original_signature=None,
        conversation_ids=["conv1", "conv2"],
        theme_data={"user_intent": "Cancel subscription"},
        confidence_score=None,
        first_seen_at=datetime.now(),
        last_updated_at=datetime.now(),
        graduated_at=None,
        story_id=None,
    )


@pytest.fixture
def ready_orphan():
    """Sample orphan ready for graduation (at MIN_GROUP_SIZE)."""
    return Orphan(
        id=uuid4(),
        signature="billing_cancellation",
        original_signature=None,
        conversation_ids=["conv1", "conv2", "conv3"],
        theme_data={"user_intent": "Cancel subscription"},
        confidence_score=None,
        first_seen_at=datetime.now(),
        last_updated_at=datetime.now(),
        graduated_at=None,
        story_id=None,
    )


@pytest.fixture
def sample_story():
    """Sample story for graduation tests."""
    return Story(
        id=uuid4(),
        title="Billing Cancellation",
        description="Users wanting to cancel",
        labels=[],
        priority=None,
        severity=None,
        product_area="billing",
        technical_area="subscription",
        status="candidate",
        confidence_score=None,
        evidence_count=0,
        conversation_count=3,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_extracted_theme():
    """Sample extracted theme from a conversation."""
    return ExtractedTheme(
        signature="billing_cancellation",
        user_intent="Cancel subscription",
        symptoms=["wants to cancel", "billing issue"],
        product_area="billing",
        component="subscription",
        affected_flow="Billing → Cancellation",
        excerpt="I want to cancel my subscription",
    )


# -----------------------------------------------------------------------------
# ExtractedTheme Tests
# -----------------------------------------------------------------------------


class TestExtractedTheme:
    """Tests for ExtractedTheme dataclass."""

    def test_to_theme_data(self, sample_extracted_theme):
        """Test conversion to theme_data dict."""
        theme_data = sample_extracted_theme.to_theme_data()

        assert theme_data["user_intent"] == "Cancel subscription"
        assert "wants to cancel" in theme_data["symptoms"]
        assert theme_data["product_area"] == "billing"
        assert theme_data["component"] == "subscription"
        assert len(theme_data["excerpts"]) == 1

    def test_to_theme_data_minimal(self):
        """Test conversion with minimal data."""
        theme = ExtractedTheme(signature="test")
        theme_data = theme.to_theme_data()

        assert theme_data == {}

    def test_symptoms_default_to_empty_list(self):
        """Test that symptoms default to empty list."""
        theme = ExtractedTheme(signature="test")
        assert theme.symptoms == []


# -----------------------------------------------------------------------------
# OrphanMatcher Tests
# -----------------------------------------------------------------------------


class TestOrphanMatcherBasic:
    """Basic OrphanMatcher tests."""

    def test_create_new_orphan_when_no_match(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_extracted_theme,
    ):
        """Test creating new orphan when no existing orphan matches."""
        mock_orphan_service.get_by_signature.return_value = None
        new_orphan = Orphan(
            id=uuid4(),
            signature="billing_cancellation",
            original_signature=None,
            conversation_ids=["conv123"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )
        # Now uses create_or_get which returns (orphan, created) tuple
        mock_orphan_service.create_or_get.return_value = (new_orphan, True)

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        result = matcher.match_and_accumulate("conv123", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "created"
        mock_orphan_service.create_or_get.assert_called_once()

    def test_update_existing_orphan(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_orphan,
        sample_extracted_theme,
    ):
        """Test adding conversation to existing orphan."""
        mock_orphan_service.get_by_signature.return_value = sample_orphan
        mock_orphan_service.add_conversations.return_value = sample_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        result = matcher.match_and_accumulate("conv_new", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "updated"
        mock_orphan_service.add_conversations.assert_called_once()

    def test_skip_duplicate_conversation(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_orphan,
        sample_extracted_theme,
    ):
        """Test that duplicate conversations are not added again."""
        mock_orphan_service.get_by_signature.return_value = sample_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        # Try to add conv1 which already exists in sample_orphan
        result = matcher.match_and_accumulate("conv1", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "already_exists"
        mock_orphan_service.add_conversations.assert_not_called()


class TestOrphanMatcherGraduation:
    """Tests for orphan graduation in OrphanMatcher."""

    def test_auto_graduate_when_threshold_reached(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_orphan,
        ready_orphan,
        sample_extracted_theme,
        sample_story,
    ):
        """Test automatic graduation when MIN_GROUP_SIZE reached."""
        # Start with orphan that has 2 conversations
        mock_orphan_service.get_by_signature.return_value = sample_orphan
        # After adding, orphan has 3 conversations
        mock_orphan_service.add_conversations.return_value = ready_orphan
        # Graduation result
        mock_orphan_service.graduate.return_value = OrphanGraduationResult(
            orphan_id=ready_orphan.id,
            story_id=sample_story.id,
            signature="billing_cancellation",
            conversation_count=3,
            graduated_at=datetime.now(),
        )

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
            auto_graduate=True,
        )

        result = matcher.match_and_accumulate("conv3", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "graduated"
        assert result.story_id is not None
        mock_orphan_service.graduate.assert_called_once()

    def test_no_graduation_when_disabled(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_orphan,
        ready_orphan,
        sample_extracted_theme,
    ):
        """Test that graduation is skipped when auto_graduate=False."""
        mock_orphan_service.get_by_signature.return_value = sample_orphan
        mock_orphan_service.add_conversations.return_value = ready_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
            auto_graduate=False,
        )

        result = matcher.match_and_accumulate("conv3", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "updated"
        mock_orphan_service.graduate.assert_not_called()

    def test_graduate_all_ready(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
    ):
        """Test batch graduation of all ready orphans."""
        graduation_result = OrphanGraduationResult(
            orphan_id=uuid4(),
            story_id=uuid4(),
            signature="test",
            conversation_count=3,
            graduated_at=datetime.now(),
        )
        mock_orphan_service.check_and_graduate_ready.return_value = [graduation_result]

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        results = matcher.graduate_all_ready()

        assert len(results) == 1
        mock_orphan_service.check_and_graduate_ready.assert_called_once_with(
            mock_story_service
        )


class TestOrphanMatcherSignatureNormalization:
    """Tests for signature normalization in OrphanMatcher."""

    def test_uses_canonical_signature(
        self,
        mock_orphan_service,
        mock_story_service,
        sample_extracted_theme,
    ):
        """Test that canonical signature from registry is used."""
        registry = Mock(spec=SignatureRegistry)
        registry.get_canonical.return_value = "billing_cancellation_canonical"

        mock_orphan_service.get_by_signature.return_value = None
        new_orphan = Orphan(
            id=uuid4(),
            signature="billing_cancellation_canonical",
            original_signature="billing_cancellation",
            conversation_ids=["conv1"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )
        # Now uses create_or_get which returns (orphan, created) tuple
        mock_orphan_service.create_or_get.return_value = (new_orphan, True)

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            registry,
        )

        matcher.match_and_accumulate("conv1", sample_extracted_theme)

        # Should look up using canonical signature
        mock_orphan_service.get_by_signature.assert_called_with(
            "billing_cancellation_canonical"
        )


class TestOrphanMatcherBatch:
    """Tests for batch matching."""

    def test_batch_match(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
    ):
        """Test batch matching multiple conversations."""
        mock_orphan_service.get_by_signature.return_value = None
        new_orphan = Orphan(
            id=uuid4(),
            signature="test",
            original_signature=None,
            conversation_ids=["conv1"],
            theme_data={},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=None,
            story_id=None,
        )
        # Now uses create_or_get which returns (orphan, created) tuple
        mock_orphan_service.create_or_get.return_value = (new_orphan, True)

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        conversations = [
            {
                "id": "conv1",
                "issue_signature": "billing_issue",
                "user_intent": "Get refund",
                "symptoms": ["overcharged"],
            },
            {
                "id": "conv2",
                "issue_signature": "billing_issue",
                "user_intent": "Cancel subscription",
                "symptoms": ["want to cancel"],
            },
        ]

        results = matcher.batch_match(conversations)

        assert len(results) == 2
        assert all(r.matched for r in results)


class TestOrphanMatcherGraduatedFlow:
    """Tests for graduated orphan routing (Issue #176 fix)."""

    @pytest.fixture
    def graduated_orphan(self, sample_story):
        """Sample orphan that has already graduated to a story."""
        return Orphan(
            id=uuid4(),
            signature="billing_cancellation",
            original_signature=None,
            conversation_ids=["conv1", "conv2", "conv3"],
            theme_data={"user_intent": "Cancel subscription"},
            confidence_score=None,
            first_seen_at=datetime.now(),
            last_updated_at=datetime.now(),
            graduated_at=datetime.now(),
            story_id=sample_story.id,
        )

    @pytest.fixture
    def mock_evidence_service(self):
        """Create a mock evidence service."""
        from unittest.mock import Mock
        service = Mock()
        return service

    def test_match_adds_to_graduated_story(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        graduated_orphan,
        sample_extracted_theme,
        mock_evidence_service,
    ):
        """When orphan is graduated, conversation flows to story."""
        mock_orphan_service.get_by_signature.return_value = graduated_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
            evidence_service=mock_evidence_service,
        )

        result = matcher.match_and_accumulate("conv_new", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "added_to_story"
        assert result.story_id == str(graduated_orphan.story_id)
        # Issue #197: add_conversation now includes theme_signature
        mock_evidence_service.add_conversation.assert_called_once_with(
            story_id=graduated_orphan.story_id,
            conversation_id="conv_new",
            source="intercom",
            excerpt="I want to cancel my subscription"[:500],
            theme_signature=graduated_orphan.signature,
        )

    def test_match_returns_no_evidence_service_when_missing(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        graduated_orphan,
        sample_extracted_theme,
    ):
        """Without evidence_service, graduated orphan returns no_evidence_service action."""
        mock_orphan_service.get_by_signature.return_value = graduated_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
            evidence_service=None,  # No evidence service
        )

        result = matcher.match_and_accumulate("conv_new", sample_extracted_theme)

        assert result.matched is False
        assert result.action == "no_evidence_service"
        assert result.story_id == str(graduated_orphan.story_id)

    def test_create_handles_race_to_graduated(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        graduated_orphan,
        sample_extracted_theme,
        mock_evidence_service,
    ):
        """Race condition: create_or_get returns graduated orphan → flows to story."""
        # First get_by_signature returns None (no orphan)
        mock_orphan_service.get_by_signature.return_value = None
        # But create_or_get returns an existing graduated orphan (race condition)
        mock_orphan_service.create_or_get.return_value = (graduated_orphan, False)

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
            evidence_service=mock_evidence_service,
        )

        result = matcher.match_and_accumulate("conv_new", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "added_to_story"
        assert result.story_id == str(graduated_orphan.story_id)
        mock_evidence_service.add_conversation.assert_called_once()

    def test_create_handles_race_to_active(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_orphan,
        sample_extracted_theme,
    ):
        """Race condition: create_or_get returns active orphan → updates orphan."""
        # First get_by_signature returns None (no orphan)
        mock_orphan_service.get_by_signature.return_value = None
        # But create_or_get returns an existing active orphan (race condition)
        mock_orphan_service.create_or_get.return_value = (sample_orphan, False)
        mock_orphan_service.add_conversations.return_value = sample_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        result = matcher.match_and_accumulate("conv_new", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "updated"
        mock_orphan_service.add_conversations.assert_called_once()

    def test_match_updates_active_orphan(
        self,
        mock_orphan_service,
        mock_story_service,
        mock_signature_registry,
        sample_orphan,
        sample_extracted_theme,
    ):
        """When orphan is active, conversation added to orphan (not story)."""
        mock_orphan_service.get_by_signature.return_value = sample_orphan
        mock_orphan_service.add_conversations.return_value = sample_orphan

        matcher = OrphanMatcher(
            mock_orphan_service,
            mock_story_service,
            mock_signature_registry,
        )

        result = matcher.match_and_accumulate("conv_new", sample_extracted_theme)

        assert result.matched is True
        assert result.action == "updated"
        assert result.story_id is None
        mock_orphan_service.add_conversations.assert_called_once()


class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_match_result_creation(self):
        """Test MatchResult dataclass."""
        result = MatchResult(
            matched=True,
            orphan_id="123",
            orphan_signature="test_sig",
            action="created",
        )

        assert result.matched is True
        assert result.orphan_id == "123"
        assert result.story_id is None

    def test_match_result_with_graduation(self):
        """Test MatchResult with graduation."""
        result = MatchResult(
            matched=True,
            orphan_id="123",
            orphan_signature="test_sig",
            action="graduated",
            story_id="456",
        )

        assert result.action == "graduated"
        assert result.story_id == "456"
