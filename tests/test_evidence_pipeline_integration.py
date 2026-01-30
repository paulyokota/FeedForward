"""
Evidence Pipeline Integration Tests: Issues #156, #157, #158

Tests for verifying the complete evidence creation data flow end-to-end.
These tests ensure that evidence bundles are created correctly with:
- Issue #156: diagnostic_summary + key_excerpts over raw excerpt
- Issue #157: metadata completeness (email, intercom_url, org/user IDs)
- Issue #158: signal-based ranking instead of arbitrary first-N selection

The flow being tested:
1. Pipeline query fetches themes with diagnostic_summary, key_excerpts, and metadata
2. StoryCreationService ranks conversations by signal quality
3. Evidence excerpts use diagnostic_summary when available, fall back to excerpt
4. key_excerpts are appended (deduped against diagnostic_summary)
5. Metadata (email, intercom_url, IDs) is included in each excerpt
6. EvidenceService stores the complete evidence bundle

Owner: Kenji (Testing)
Run: pytest tests/test_evidence_pipeline_integration.py -v
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Import the modules we're testing
from story_tracking.services.story_creation_service import (
    ConversationData,
    StoryCreationService,
    _rank_conversations_by_signal,
    _build_intercom_url,
    _text_similarity,
    MAX_EXCERPTS_IN_THEME,
    INTERCOM_APP_ID,
)
from story_tracking.services import StoryService, OrphanService
from story_tracking.models import Story, EvidenceExcerpt

# Mark entire module as slow - these are integration tests
pytestmark = [pytest.mark.slow, pytest.mark.integration]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_story_service():
    """Create a mock story service with DB cursor support."""
    service = Mock(spec=StoryService)
    service.db = Mock()
    mock_cursor = Mock()
    service.db.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    service.db.cursor.return_value.__exit__ = Mock(return_value=False)
    service.create.return_value = Story(
        id=uuid4(),
        title="Test Story",
        description="Test description",
        labels=[],
        priority=None,
        severity=None,
        product_area="test",
        technical_area="test",
        status="candidate",
        confidence_score=None,
        evidence_count=0,
        conversation_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    return service


@pytest.fixture
def mock_orphan_service():
    """Create a mock orphan service."""
    service = Mock(spec=OrphanService)
    service.get_by_signature.return_value = None
    return service


@pytest.fixture
def mock_evidence_service():
    """Create mock EvidenceService that captures calls."""
    service = Mock()
    service.create_or_update.return_value = Mock(id=uuid4())
    return service


@pytest.fixture
def sample_theme_groups_with_all_features():
    """
    Sample theme groups with all evidence features:
    - diagnostic_summary and key_excerpts (Issue #156)
    - metadata fields (Issue #157)
    - varying signal levels for ranking (Issue #158)
    """
    return {
        "test_signature": [
            # High-signal conversation (should rank first)
            {
                "id": "conv_high_signal",
                "issue_signature": "test_signature",
                "excerpt": "fallback excerpt for high signal",
                "diagnostic_summary": "Error 500 occurred during upload. Connection timeout after 30 seconds.",
                "key_excerpts": [
                    {"text": "Connection refused by server", "relevance": "Root cause indicator"},
                    {"text": "Retry failed three times", "relevance": "Persistence of issue"},
                ],
                "contact_email": "high@example.com",
                "contact_id": "contact_high",
                "user_id": "user_high",
                "org_id": "org_high",
                "symptoms": ["timeout", "error"],
            },
            # Medium-signal conversation
            {
                "id": "conv_medium_signal",
                "issue_signature": "test_signature",
                "excerpt": "medium signal excerpt",
                "diagnostic_summary": "User reported slow performance",
                "key_excerpts": [],
                "contact_email": "medium@example.com",
                "contact_id": "contact_medium",
                "user_id": "user_medium",
                "org_id": "org_medium",
            },
            # Low-signal conversation (no diagnostic_summary, no key_excerpts)
            {
                "id": "conv_low_signal",
                "issue_signature": "test_signature",
                "excerpt": "simple question about feature",
                "contact_email": "low@example.com",
            },
        ],
    }


# =============================================================================
# Test: Full Evidence Pipeline Integration
# =============================================================================


class TestEvidencePipelineIntegration:
    """
    Integration test covering the full evidence pipeline.

    Verifies all three issues (#156, #157, #158) work together correctly.
    """

    def test_full_evidence_flow(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_evidence_service,
        sample_theme_groups_with_all_features,
    ):
        """
        Test complete evidence creation flow:
        - Diagnostic summary chosen over excerpt (#156)
        - key_excerpts appended (#156)
        - Metadata fields present (#157)
        - intercom_url constructed correctly (#157)
        - Higher-signal conversation selected first (#158)
        """
        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        # Process the theme groups
        result = service.process_theme_groups(sample_theme_groups_with_all_features)

        # Verify story was created
        assert result.stories_created >= 1

        # Get the evidence that was created
        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Verify we have excerpts
        assert len(excerpts) >= 2

        # --- Issue #158: Verify signal-based ranking ---
        # The high-signal conversation should be first
        assert excerpts[0].conversation_id == "conv_high_signal"

        # --- Issue #156: Verify diagnostic_summary is used ---
        # The first excerpt should use diagnostic_summary, not raw excerpt
        assert "Error 500" in excerpts[0].text or "Connection timeout" in excerpts[0].text
        assert "fallback excerpt for high signal" not in excerpts[0].text

        # --- Issue #157: Verify metadata is present ---
        assert excerpts[0].email == "high@example.com"
        assert excerpts[0].org_id == "org_high"
        assert excerpts[0].user_id == "user_high"
        assert excerpts[0].contact_id == "contact_high"

        # --- Issue #157: Verify intercom_url is constructed correctly ---
        assert excerpts[0].intercom_url is not None
        expected_url = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/conv_high_signal"
        assert excerpts[0].intercom_url == expected_url

        # --- Issue #156: Verify key_excerpts are appended ---
        # Find the key_excerpts in the evidence
        texts = [e.text for e in excerpts]
        key_excerpt_found = any(
            "Connection refused" in t or "Retry failed" in t
            for t in texts
        )
        assert key_excerpt_found, "key_excerpts should be appended to evidence"

    def test_fallback_to_excerpt_when_diagnostic_missing(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_evidence_service,
    ):
        """Test that excerpt is used when diagnostic_summary is missing/empty."""
        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "This is the fallback excerpt text",
                    "diagnostic_summary": "",  # Empty
                },
                {
                    "id": "conv2",
                    "excerpt": "Another fallback",
                    # No diagnostic_summary field
                },
                {"id": "conv3", "excerpt": "Third one"},
            ],
        }

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]
        texts = [e.text for e in excerpts]

        # All should use fallback excerpt
        assert "fallback excerpt text" in texts or "Another fallback" in texts

    def test_metadata_optional_when_not_in_db(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_evidence_service,
    ):
        """Test that evidence is created even when metadata is missing from DB."""
        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "text",
                    # No metadata fields at all
                },
                {"id": "conv2", "excerpt": "text2"},
                {"id": "conv3", "excerpt": "text3"},
            ],
        }

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        # Should not raise
        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]

        # Evidence should be created
        assert len(excerpts) == 3

        # intercom_url should still be constructed from ID
        assert all(e.intercom_url is not None for e in excerpts)

        # Other metadata should be None
        assert all(e.email is None for e in excerpts)

    def test_dedupe_key_excerpts_against_diagnostic(
        self,
        mock_story_service,
        mock_orphan_service,
        mock_evidence_service,
    ):
        """Test that similar key_excerpts are deduped against diagnostic_summary."""
        theme_groups = {
            "test_sig": [
                {
                    "id": "conv1",
                    "excerpt": "raw",
                    "diagnostic_summary": "The server returned error 500 internal server error",
                    "key_excerpts": [
                        # Very similar to diagnostic_summary - should be deduped
                        {"text": "server returned error 500 internal server error response"},
                        # Different - should be kept
                        {"text": "User was on mobile device using Chrome browser"},
                    ],
                },
                {"id": "conv2", "excerpt": "other"},
                {"id": "conv3", "excerpt": "another"},
            ],
        }

        service = StoryCreationService(
            mock_story_service,
            mock_orphan_service,
            evidence_service=mock_evidence_service,
            validation_enabled=False,
        )

        service.process_theme_groups(theme_groups)

        call_kwargs = mock_evidence_service.create_or_update.call_args[1]
        excerpts = call_kwargs["excerpts"]
        texts = [e.text for e in excerpts]

        # The similar key_excerpt should be deduped (won't appear)
        assert not any("error 500 internal server error response" in t.lower() for t in texts)

        # The different key_excerpt should be kept
        assert any("mobile device" in t.lower() or "Chrome browser" in t.lower() for t in texts)


# =============================================================================
# Test: ConversationData Field Mapping
# =============================================================================


class TestConversationDataMapping:
    """Test that ConversationData correctly maps all fields from pipeline dict."""

    def test_conversation_data_has_all_metadata_fields(self):
        """Verify ConversationData dataclass has all Issue #157 fields."""
        conv = ConversationData(
            id="test",
            issue_signature="sig",
            contact_email="email@test.com",
            contact_id="contact_123",
            user_id="user_456",
            org_id="org_789",
        )

        assert conv.contact_email == "email@test.com"
        assert conv.contact_id == "contact_123"
        assert conv.user_id == "user_456"
        assert conv.org_id == "org_789"

    def test_conversation_data_has_smart_digest_fields(self):
        """Verify ConversationData dataclass has Issue #144/156 fields."""
        conv = ConversationData(
            id="test",
            issue_signature="sig",
            diagnostic_summary="diagnostic text",
            key_excerpts=[{"text": "key", "relevance": "why"}],
        )

        assert conv.diagnostic_summary == "diagnostic text"
        assert len(conv.key_excerpts) == 1
        assert conv.key_excerpts[0]["text"] == "key"


# =============================================================================
# Test: EvidenceExcerpt Field Mapping
# =============================================================================


class TestEvidenceExcerptMapping:
    """Test that EvidenceExcerpt model has all required fields."""

    def test_evidence_excerpt_has_metadata_fields(self):
        """Verify EvidenceExcerpt model has all Issue #157 fields."""
        excerpt = EvidenceExcerpt(
            text="test",
            source="intercom",
            conversation_id="conv1",
            email="test@example.com",
            intercom_url="https://app.intercom.com/...",
            org_id="org_123",
            user_id="user_456",
            contact_id="contact_789",
        )

        assert excerpt.email == "test@example.com"
        assert excerpt.intercom_url == "https://app.intercom.com/..."
        assert excerpt.org_id == "org_123"
        assert excerpt.user_id == "user_456"
        assert excerpt.contact_id == "contact_789"


# =============================================================================
# Test: URL Construction
# =============================================================================


class TestIntercomUrlConstruction:
    """Test that intercom_url is constructed correctly."""

    def test_url_matches_story_formatter_pattern(self):
        """Verify URL format matches story_formatter.py pattern."""
        url = _build_intercom_url("test_conv_123")

        expected = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/test_conv_123"
        assert url == expected

    def test_url_includes_app_id(self):
        """Verify INTERCOM_APP_ID is included in URL."""
        url = _build_intercom_url("any_conv")

        assert INTERCOM_APP_ID in url


# =============================================================================
# Test: Signal-Based Ranking Integration
# =============================================================================


class TestSignalRankingIntegration:
    """Test that signal-based ranking works correctly in full flow."""

    def test_high_signal_conversation_ranked_first(self):
        """Verify conversations with key_excerpts rank higher."""
        convs = [
            ConversationData(
                id="low_signal",
                issue_signature="test",
                excerpt="simple text",
            ),
            ConversationData(
                id="high_signal",
                issue_signature="test",
                diagnostic_summary="Error analysis",
                key_excerpts=[{"text": "important"}],
            ),
        ]

        ranked = _rank_conversations_by_signal(convs)

        assert ranked[0].id == "high_signal"

    def test_ranking_is_deterministic(self):
        """Verify ranking produces consistent results."""
        convs = [
            ConversationData(id=f"conv_{i}", issue_signature="test", excerpt=f"text {i}")
            for i in range(10)
        ]

        # Run multiple times
        results = [_rank_conversations_by_signal(convs.copy()) for _ in range(5)]

        # All results should be identical
        for result in results[1:]:
            assert [c.id for c in result] == [c.id for c in results[0]]
