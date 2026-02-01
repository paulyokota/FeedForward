"""
Tests for Issue #200: 30-Day Recency Gate for Story Creation

Tests cover:
- A. Unit tests for _has_recent_conversation helper (FAST)
- B. Integration tests for story creation paths (@pytest.mark.slow)
- C. Orphan graduation tests
- D. Edge cases
"""

import logging
import pytest
from datetime import datetime, timezone, timedelta
from typing import List
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.story_tracking.services.story_creation_service import (
    ConversationData,
    RECENCY_WINDOW_DAYS,
    _has_recent_conversation,
)


# =============================================================================
# A. Unit Tests for _has_recent_conversation helper (FAST)
# =============================================================================

class TestHasRecentConversationHelper:
    """Unit tests for the _has_recent_conversation helper function."""

    def test_empty_list_returns_false(self):
        """Empty conversation list should return False."""
        assert _has_recent_conversation([]) is False

    def test_one_recent_today_returns_true(self):
        """Single conversation from today should return True."""
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=datetime.now(timezone.utc),
        )
        assert _has_recent_conversation([conv]) is True

    def test_one_old_31_days_returns_false(self):
        """Single conversation from 31 days ago should return False."""
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        assert _has_recent_conversation([conv]) is False

    def test_boundary_exactly_30_days_returns_true(self):
        """Conversation from exactly 30 days ago should return True (inclusive)."""
        # Use a small buffer to avoid microsecond boundary issues
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=datetime.now(timezone.utc) - timedelta(days=30) + timedelta(seconds=1),
        )
        assert _has_recent_conversation([conv]) is True

    def test_boundary_30_days_plus_1_second_returns_false(self):
        """Conversation from 30 days + 1 second ago should return False."""
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=datetime.now(timezone.utc) - timedelta(days=30, seconds=1),
        )
        assert _has_recent_conversation([conv]) is False

    def test_mixed_ages_returns_true(self):
        """Group with old and recent conversations should return True."""
        convs = [
            ConversationData(
                id="old1",
                issue_signature="test_signature",
                created_at=datetime.now(timezone.utc) - timedelta(days=60),
            ),
            ConversationData(
                id="old2",
                issue_signature="test_signature",
                created_at=datetime.now(timezone.utc) - timedelta(days=45),
            ),
            ConversationData(
                id="recent",
                issue_signature="test_signature",
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
            ),
        ]
        assert _has_recent_conversation(convs) is True

    def test_all_old_returns_false(self):
        """Group with all old conversations should return False."""
        convs = [
            ConversationData(
                id="old1",
                issue_signature="test_signature",
                created_at=datetime.now(timezone.utc) - timedelta(days=60),
            ),
            ConversationData(
                id="old2",
                issue_signature="test_signature",
                created_at=datetime.now(timezone.utc) - timedelta(days=45),
            ),
            ConversationData(
                id="old3",
                issue_signature="test_signature",
                created_at=datetime.now(timezone.utc) - timedelta(days=35),
            ),
        ]
        assert _has_recent_conversation(convs) is False

    def test_none_created_at_returns_false(self):
        """Conversation with None created_at should be treated as not recent."""
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=None,
        )
        assert _has_recent_conversation([conv]) is False

    def test_all_none_created_at_returns_false(self):
        """Group where all conversations have None created_at should return False."""
        convs = [
            ConversationData(id="conv1", issue_signature="sig", created_at=None),
            ConversationData(id="conv2", issue_signature="sig", created_at=None),
            ConversationData(id="conv3", issue_signature="sig", created_at=None),
        ]
        assert _has_recent_conversation(convs) is False

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime should be treated as UTC."""
        # Create a naive datetime that's recent
        naive_recent = datetime.now() - timedelta(days=5)
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=naive_recent,
        )
        assert _has_recent_conversation([conv]) is True

    def test_naive_datetime_old_returns_false(self):
        """Naive datetime that's old should return False."""
        naive_old = datetime.now() - timedelta(days=60)
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=naive_old,
        )
        assert _has_recent_conversation([conv]) is False

    def test_custom_days_parameter(self):
        """Custom days parameter should be respected."""
        conv = ConversationData(
            id="conv1",
            issue_signature="test_signature",
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        # Within 30 days
        assert _has_recent_conversation([conv], days=30) is True
        # Outside 7 days
        assert _has_recent_conversation([conv], days=7) is False

    def test_constant_value(self):
        """RECENCY_WINDOW_DAYS should be 30."""
        assert RECENCY_WINDOW_DAYS == 30


# =============================================================================
# B. Integration Tests for Story Creation Paths
# =============================================================================

@pytest.mark.slow
class TestStoryCreationRecencyGate:
    """Integration tests for recency gate in story creation paths."""

    def _create_conversation_data(
        self, conv_id: str, signature: str, days_ago: int = 0
    ) -> ConversationData:
        """Helper to create ConversationData with specified age."""
        return ConversationData(
            id=conv_id,
            issue_signature=signature,
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )

    @pytest.fixture
    def story_creation_service(self):
        """Create a StoryCreationService with mocked dependencies."""
        from src.story_tracking.services.story_creation_service import (
            StoryCreationService,
        )

        mock_story_service = MagicMock()
        mock_orphan_service = MagicMock()
        mock_evidence_service = MagicMock()

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            evidence_service=mock_evidence_service,
            pm_review_enabled=False,
            validation_enabled=False,  # Disable evidence validation for unit tests
        )
        return service

    def test_quality_gate_passes_with_recent_conversation(self, story_creation_service):
        """Group with recent conversation should pass quality gate (recency check)."""
        # Create conversations with one recent
        convs = [
            self._create_conversation_data("c1", "sig", days_ago=5),
            self._create_conversation_data("c2", "sig", days_ago=45),
            self._create_conversation_data("c3", "sig", days_ago=60),
        ]

        conv_dicts = [{"id": c.id} for c in convs]
        result = story_creation_service._apply_quality_gates("test_sig", convs, conv_dicts)

        # Should pass (has recent conversation)
        assert result.passed is True

    def test_quality_gate_fails_all_old_conversations(self, story_creation_service):
        """Group with all old conversations should fail quality gate."""
        # Create conversations all older than 30 days
        convs = [
            self._create_conversation_data("c1", "sig", days_ago=35),
            self._create_conversation_data("c2", "sig", days_ago=45),
            self._create_conversation_data("c3", "sig", days_ago=60),
        ]

        conv_dicts = [{"id": c.id} for c in convs]
        result = story_creation_service._apply_quality_gates("test_sig", convs, conv_dicts)

        # Should fail with recency reason
        assert result.passed is False
        assert result.failure_reason == "No recent conversations (last 30 days)"

    def test_small_group_fails_with_size_reason_not_recency(self, story_creation_service):
        """Group below MIN_GROUP_SIZE should fail with size reason, not recency."""
        from src.story_tracking.models import MIN_GROUP_SIZE

        # Create fewer than MIN_GROUP_SIZE conversations (but recent)
        convs = [
            self._create_conversation_data("c1", "sig", days_ago=5),
            self._create_conversation_data("c2", "sig", days_ago=10),
        ]
        assert len(convs) < MIN_GROUP_SIZE  # Verify test setup

        conv_dicts = [{"id": c.id} for c in convs]
        result = story_creation_service._apply_quality_gates("test_sig", convs, conv_dicts)

        # Should fail with size reason (not recency)
        assert result.passed is False
        assert "minimum is" in result.failure_reason
        assert "30 days" not in result.failure_reason


# =============================================================================
# C. Orphan Graduation Tests
# =============================================================================

@pytest.mark.slow
class TestOrphanGraduationRecency:
    """Tests for recency gate in orphan graduation."""

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_conn

    def test_check_conversation_recency_with_recent(self, mock_db_connection):
        """_check_conversation_recency returns True when recent conversation exists."""
        from src.story_tracking.services.orphan_service import OrphanService

        service = OrphanService(mock_db_connection)

        # Mock cursor to return True (recent conversation exists)
        # Use dict to match RealDictCursor behavior
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"has_recent": True}
        mock_db_connection.cursor.return_value.__enter__.return_value = mock_cursor

        result = service._check_conversation_recency(["conv1", "conv2"])
        assert result is True

        # Verify SQL was called with correct structure
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "conversations" in sql
        assert "created_at >=" in sql
        assert "ANY(%s)" in sql

    def test_check_conversation_recency_without_recent(self, mock_db_connection):
        """_check_conversation_recency returns False when no recent conversation."""
        from src.story_tracking.services.orphan_service import OrphanService

        service = OrphanService(mock_db_connection)

        # Mock cursor to return False (no recent conversation)
        # Use dict to match RealDictCursor behavior
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"has_recent": False}
        mock_db_connection.cursor.return_value.__enter__.return_value = mock_cursor

        result = service._check_conversation_recency(["conv1", "conv2"])
        assert result is False

    def test_check_conversation_recency_empty_list(self, mock_db_connection):
        """_check_conversation_recency returns False for empty list."""
        from src.story_tracking.services.orphan_service import OrphanService

        service = OrphanService(mock_db_connection)

        result = service._check_conversation_recency([])
        assert result is False

    def test_bulk_recency_check(self, mock_db_connection):
        """_get_conversation_recency_bulk returns correct mapping."""
        from src.story_tracking.services.orphan_service import OrphanService

        service = OrphanService(mock_db_connection)

        orphan_id_1 = uuid4()
        orphan_id_2 = uuid4()
        orphan_id_3 = uuid4()

        # Mock cursor to return bulk results
        # Use dicts to match RealDictCursor behavior
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"orphan_id": orphan_id_1, "has_recent": True},
            {"orphan_id": orphan_id_2, "has_recent": False},
            {"orphan_id": orphan_id_3, "has_recent": True},
        ]
        mock_db_connection.cursor.return_value.__enter__.return_value = mock_cursor

        result = service._get_conversation_recency_bulk([orphan_id_1, orphan_id_2, orphan_id_3])

        assert result[orphan_id_1] is True
        assert result[orphan_id_2] is False
        assert result[orphan_id_3] is True

    def test_bulk_recency_check_empty_list(self, mock_db_connection):
        """_get_conversation_recency_bulk returns empty dict for empty list."""
        from src.story_tracking.services.orphan_service import OrphanService

        service = OrphanService(mock_db_connection)

        result = service._get_conversation_recency_bulk([])
        assert result == {}

    def test_graduate_blocks_old_orphan(self, mock_db_connection, caplog):
        """graduate() should block orphan with all old conversations."""
        from src.story_tracking.services.orphan_service import OrphanService
        from src.story_tracking.models import Orphan, MIN_GROUP_SIZE

        service = OrphanService(mock_db_connection)

        # Create mock orphan that can graduate (meets MIN_GROUP_SIZE)
        orphan_id = uuid4()
        now = datetime.now(timezone.utc)
        mock_orphan = Orphan(
            id=orphan_id,
            signature="test_sig",
            conversation_ids=["c1", "c2", "c3"],
            theme_data={},
            first_seen_at=now - timedelta(days=60),
            last_updated_at=now,
        )
        assert mock_orphan.can_graduate  # Verify test setup

        # Mock get() to return the orphan
        with patch.object(service, 'get', return_value=mock_orphan):
            # Mock recency check to return False (all old)
            with patch.object(
                service, '_check_conversation_recency', return_value=False
            ):
                with caplog.at_level(logging.WARNING):
                    result = service.graduate(orphan_id, MagicMock())

        # Should return None (blocked by recency)
        assert result is None
        assert "No recent conversations" in caplog.text


# =============================================================================
# D. Edge Cases
# =============================================================================

class TestRecencyEdgeCases:
    """Edge case tests for recency gate."""

    @pytest.fixture
    def story_creation_service(self):
        """Create a StoryCreationService with mocked dependencies."""
        from src.story_tracking.services.story_creation_service import (
            StoryCreationService,
        )

        mock_story_service = MagicMock()
        mock_orphan_service = MagicMock()
        mock_evidence_service = MagicMock()

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            evidence_service=mock_evidence_service,
            pm_review_enabled=False,
        )
        return service

    def test_dict_to_conversation_data_extracts_created_at(self, story_creation_service):
        """_dict_to_conversation_data should extract and normalize created_at."""
        now = datetime.now(timezone.utc)
        conv_dict = {
            "id": "test_conv",
            "issue_signature": "test_sig",
            "created_at": now,
        }

        result = story_creation_service._dict_to_conversation_data(conv_dict, "test_sig")

        assert result.created_at == now

    def test_dict_to_conversation_data_naive_datetime(self, story_creation_service):
        """_dict_to_conversation_data should handle naive datetime."""
        naive_dt = datetime.now()  # No timezone
        conv_dict = {
            "id": "test_conv",
            "issue_signature": "test_sig",
            "created_at": naive_dt,
        }

        result = story_creation_service._dict_to_conversation_data(conv_dict, "test_sig")

        # Should be aware now (UTC)
        assert result.created_at is not None
        assert result.created_at.tzinfo == timezone.utc

    def test_dict_to_conversation_data_string_created_at_logs_warning(
        self, story_creation_service, caplog
    ):
        """_dict_to_conversation_data should log warning for string created_at."""
        # String instead of datetime
        conv_dict = {
            "id": "test_conv",
            "issue_signature": "test_sig",
            "created_at": "2024-01-15T10:30:00Z",
        }

        with caplog.at_level(logging.WARNING):
            result = story_creation_service._dict_to_conversation_data(conv_dict, "test_sig")

        # Should be None (not parsed) and warning logged
        assert result.created_at is None
        assert "Unexpected string created_at" in caplog.text

    def test_dict_to_conversation_data_none_created_at(self, story_creation_service):
        """_dict_to_conversation_data should handle None created_at."""
        conv_dict = {
            "id": "test_conv",
            "issue_signature": "test_sig",
            "created_at": None,
        }

        result = story_creation_service._dict_to_conversation_data(conv_dict, "test_sig")

        assert result.created_at is None

    def test_failure_reason_exact_text(self, story_creation_service):
        """Quality gate failure should have exact recency reason text."""
        # Create old conversations
        convs = [
            ConversationData(
                id="c1",
                issue_signature="sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=45),
            ),
            ConversationData(
                id="c2",
                issue_signature="sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=60),
            ),
            ConversationData(
                id="c3",
                issue_signature="sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=35),
            ),
        ]

        conv_dicts = [{"id": c.id} for c in convs]
        result = story_creation_service._apply_quality_gates("test_sig", convs, conv_dicts)

        # Exact failure reason text
        assert result.failure_reason == "No recent conversations (last 30 days)"


# =============================================================================
# PM Split Tests
# =============================================================================

@pytest.mark.slow
class TestPMSplitRecency:
    """Tests for recency gate in PM split handling."""

    @pytest.fixture
    def story_creation_service(self):
        """Create a StoryCreationService with mocked dependencies."""
        from src.story_tracking.services.story_creation_service import (
            StoryCreationService,
        )

        mock_story_service = MagicMock()
        mock_orphan_service = MagicMock()
        mock_evidence_service = MagicMock()

        service = StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
            evidence_service=mock_evidence_service,
            pm_review_enabled=True,
        )
        return service

    def test_pm_split_old_subgroup_routes_to_orphan(self, story_creation_service):
        """PM split sub-group with all old conversations should route to orphan."""
        from src.story_tracking.services.story_creation_service import ProcessingResult
        from dataclasses import dataclass
        from typing import List

        @dataclass
        class MockSubGroup:
            suggested_signature: str
            conversation_ids: List[str]
            rationale: str

        @dataclass
        class MockPMReviewResult:
            original_signature: str
            sub_groups: List[MockSubGroup]
            orphan_conversation_ids: List[str]

        # Create old conversations (> 30 days)
        old_convs = [
            ConversationData(
                id=f"old_{i}",
                issue_signature="old_sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=45),
            )
            for i in range(3)
        ]

        pm_result = MockPMReviewResult(
            original_signature="original_sig",
            sub_groups=[
                MockSubGroup(
                    suggested_signature="old_subgroup",
                    conversation_ids=[c.id for c in old_convs],
                    rationale="Test split",
                )
            ],
            orphan_conversation_ids=[],
        )

        result = ProcessingResult()

        # Mock orphan integration routing
        with patch.object(
            story_creation_service, '_route_to_orphan_integration'
        ) as mock_route_orphan, patch.object(
            story_creation_service, '_create_story_with_evidence'
        ) as mock_create_story:

            story_creation_service._handle_pm_split(
                pm_review_result=pm_result,
                conversations=old_convs,
                result=result,
            )

            # Should route to orphan (recency failure)
            mock_route_orphan.assert_called_once()
            call_kwargs = mock_route_orphan.call_args[1]
            assert call_kwargs["failure_reason"] == "No recent conversations (last 30 days)"

            # Should NOT create story
            mock_create_story.assert_not_called()

    def test_pm_split_recent_subgroup_creates_story(self, story_creation_service):
        """PM split sub-group with recent conversation should create story."""
        from src.story_tracking.services.story_creation_service import ProcessingResult
        from dataclasses import dataclass
        from typing import List

        @dataclass
        class MockSubGroup:
            suggested_signature: str
            conversation_ids: List[str]
            rationale: str

        @dataclass
        class MockPMReviewResult:
            original_signature: str
            sub_groups: List[MockSubGroup]
            orphan_conversation_ids: List[str]

        # Create conversations with one recent
        convs = [
            ConversationData(
                id="recent_1",
                issue_signature="sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
            ),
            ConversationData(
                id="old_1",
                issue_signature="sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=45),
            ),
            ConversationData(
                id="old_2",
                issue_signature="sig",
                created_at=datetime.now(timezone.utc) - timedelta(days=60),
            ),
        ]

        pm_result = MockPMReviewResult(
            original_signature="original_sig",
            sub_groups=[
                MockSubGroup(
                    suggested_signature="recent_subgroup",
                    conversation_ids=[c.id for c in convs],
                    rationale="Test split",
                )
            ],
            orphan_conversation_ids=[],
        )

        result = ProcessingResult()

        with patch.object(
            story_creation_service, '_route_to_orphan_integration'
        ) as mock_route_orphan, patch.object(
            story_creation_service, '_create_story_with_evidence'
        ) as mock_create_story:

            story_creation_service._handle_pm_split(
                pm_review_result=pm_result,
                conversations=convs,
                result=result,
            )

            # Should create story (has recent conversation)
            mock_create_story.assert_called_once()

            # Should NOT route to orphan
            mock_route_orphan.assert_not_called()
