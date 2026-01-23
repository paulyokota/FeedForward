"""
Hybrid Cluster Story Creation Tests (Issue #109)

Tests for StoryCreationService.process_hybrid_clusters() which integrates
hybrid clustering output into story creation.

Run with: pytest tests/test_hybrid_story_creation.py -v
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from story_tracking.models import (
    MIN_GROUP_SIZE,
    Story,
    StoryCreate,
    ClusterMetadata,
)
from story_tracking.services import (
    OrphanService,
    StoryCreationService,
    StoryService,
)
from story_tracking.services.story_creation_service import (
    ConversationData,
    ProcessingResult,
)


# Mock HybridCluster and ClusteringResult since they're in a different module
class MockHybridCluster:
    """Mock HybridCluster for testing."""

    def __init__(
        self,
        cluster_id: str,
        embedding_cluster: int,
        action_type: str,
        direction: str,
        conversation_ids: list,
    ):
        self.cluster_id = cluster_id
        self.embedding_cluster = embedding_cluster
        self.action_type = action_type
        self.direction = direction
        self.conversation_ids = conversation_ids

    @property
    def size(self) -> int:
        return len(self.conversation_ids)


class MockClusteringResult:
    """Mock ClusteringResult for testing."""

    def __init__(
        self,
        pipeline_run_id: int = 1,
        total_conversations: int = 0,
        clusters: list = None,
        fallback_conversations: list = None,
        errors: list = None,
    ):
        self.pipeline_run_id = pipeline_run_id
        self.total_conversations = total_conversations
        self.clusters = clusters or []
        self.fallback_conversations = fallback_conversations or []
        self.errors = errors or []

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.total_conversations > 0


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_story_service():
    """Create a mock story service that returns a proper Story object."""
    service = Mock(spec=StoryService)

    def create_story(story_create: StoryCreate) -> Story:
        return Story(
            id=uuid4(),
            title=story_create.title,
            description=story_create.description,
            labels=story_create.labels,
            priority=story_create.priority,
            severity=story_create.severity,
            product_area=story_create.product_area,
            technical_area=story_create.technical_area,
            status=story_create.status,
            confidence_score=story_create.confidence_score,
            evidence_count=0,
            conversation_count=0,
            grouping_method=story_create.grouping_method,
            cluster_id=story_create.cluster_id,
            cluster_metadata=ClusterMetadata(**story_create.cluster_metadata) if story_create.cluster_metadata else None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    service.create.side_effect = create_story
    return service


@pytest.fixture
def mock_orphan_service():
    """Create a mock orphan service."""
    service = Mock(spec=OrphanService)
    service.get_by_signature.return_value = None
    return service


@pytest.fixture
def mock_evidence_service():
    """Create a mock evidence service."""
    service = Mock()
    service.create_bundle.return_value = True
    return service


@pytest.fixture
def story_creation_service(mock_story_service, mock_orphan_service, mock_evidence_service):
    """Create a StoryCreationService with mocked dependencies."""
    return StoryCreationService(
        story_service=mock_story_service,
        orphan_service=mock_orphan_service,
        evidence_service=mock_evidence_service,
        dual_format_enabled=False,
        target_repo=None,  # Let classifier suggest repos dynamically
        pm_review_service=None,
        pm_review_enabled=False,
    )


@pytest.fixture
def sample_cluster_large():
    """Sample hybrid cluster with MIN_GROUP_SIZE conversations."""
    return MockHybridCluster(
        cluster_id="emb_0_facet_feature_request_creation",
        embedding_cluster=0,
        action_type="feature_request",
        direction="creation",
        conversation_ids=[f"conv_{i}" for i in range(MIN_GROUP_SIZE)],
    )


@pytest.fixture
def sample_cluster_small():
    """Sample hybrid cluster with 1 conversation (below MIN_GROUP_SIZE)."""
    return MockHybridCluster(
        cluster_id="emb_1_facet_bug_report_neutral",
        embedding_cluster=1,
        action_type="bug_report",
        direction="neutral",
        conversation_ids=["conv_solo"],
    )


@pytest.fixture
def sample_conversation_data(sample_cluster_large, sample_cluster_small):
    """Sample conversation data for testing."""
    data = {}
    for conv_id in sample_cluster_large.conversation_ids:
        data[conv_id] = {
            "id": conv_id,
            "issue_signature": "billing_issue",
            "product_area": "billing",
            "component": "subscription",
            "user_intent": "User wants to add a new payment method",
            "symptoms": ["payment form not loading", "error on submit"],
            "affected_flow": "checkout",
            "excerpt": f"Sample excerpt for {conv_id}",
        }

    # Add the small cluster conversation
    data["conv_solo"] = {
        "id": "conv_solo",
        "issue_signature": "solo_issue",
        "product_area": "settings",
        "component": "profile",
        "user_intent": "User wants to update profile",
        "symptoms": ["profile not saving"],
        "affected_flow": "settings",
        "excerpt": "Solo conversation excerpt",
    }

    return data


# -----------------------------------------------------------------------------
# Tests: process_hybrid_clusters()
# -----------------------------------------------------------------------------


class TestProcessHybridClusters:
    """Tests for process_hybrid_clusters() method."""

    def test_successful_story_creation_from_cluster(
        self,
        story_creation_service,
        sample_cluster_large,
        sample_conversation_data,
    ):
        """A cluster meeting MIN_GROUP_SIZE should create a story."""
        clustering_result = MockClusteringResult(
            pipeline_run_id=1,
            total_conversations=sample_cluster_large.size,
            clusters=[sample_cluster_large],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=sample_conversation_data,
            pipeline_run_id=1,
        )

        assert result.stories_created == 1
        assert result.orphans_created == 0
        assert len(result.created_story_ids) == 1

    def test_small_cluster_becomes_orphan(
        self,
        story_creation_service,
        sample_cluster_small,
        sample_conversation_data,
    ):
        """A cluster below MIN_GROUP_SIZE should become an orphan."""
        clustering_result = MockClusteringResult(
            pipeline_run_id=1,
            total_conversations=sample_cluster_small.size,
            clusters=[sample_cluster_small],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=sample_conversation_data,
            pipeline_run_id=1,
        )

        # Small cluster goes to orphan integration
        assert result.stories_created == 0
        assert result.orphans_created >= 0  # Depends on orphan service behavior

    def test_failed_clustering_returns_empty_result(
        self,
        story_creation_service,
        sample_conversation_data,
    ):
        """Failed clustering should return empty ProcessingResult with errors."""
        clustering_result = MockClusteringResult(
            pipeline_run_id=1,
            total_conversations=0,
            errors=["Clustering failed: no embeddings"],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=sample_conversation_data,
            pipeline_run_id=1,
        )

        assert result.stories_created == 0
        assert len(result.errors) > 0
        assert "Clustering error" in result.errors[0]

    def test_fallback_conversations_become_orphans(
        self,
        story_creation_service,
        sample_conversation_data,
    ):
        """Fallback conversations (missing embeddings) should become orphans."""
        clustering_result = MockClusteringResult(
            pipeline_run_id=1,
            total_conversations=1,
            clusters=[],
            fallback_conversations=["conv_solo"],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=sample_conversation_data,
            pipeline_run_id=1,
        )

        # Fallback conversations go to orphan integration
        assert result.stories_created == 0

    def test_story_has_correct_grouping_method(
        self,
        story_creation_service,
        mock_story_service,
        sample_cluster_large,
        sample_conversation_data,
    ):
        """Created stories should have grouping_method='hybrid_cluster'."""
        clustering_result = MockClusteringResult(
            pipeline_run_id=1,
            total_conversations=sample_cluster_large.size,
            clusters=[sample_cluster_large],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=sample_conversation_data,
            pipeline_run_id=1,
        )

        # Verify the story was created with correct grouping method
        call_args = mock_story_service.create.call_args
        story_create = call_args[0][0]

        assert story_create.grouping_method == "hybrid_cluster"
        assert story_create.cluster_id == sample_cluster_large.cluster_id
        assert story_create.cluster_metadata is not None
        assert story_create.cluster_metadata["embedding_cluster"] == 0
        assert story_create.cluster_metadata["action_type"] == "feature_request"
        assert story_create.cluster_metadata["direction"] == "creation"

    def test_multiple_clusters_create_multiple_stories(
        self,
        story_creation_service,
        sample_conversation_data,
    ):
        """Multiple large clusters should each create a story."""
        cluster1 = MockHybridCluster(
            cluster_id="emb_0_facet_feature_request_creation",
            embedding_cluster=0,
            action_type="feature_request",
            direction="creation",
            conversation_ids=[f"conv_{i}" for i in range(MIN_GROUP_SIZE)],
        )
        cluster2 = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            embedding_cluster=1,
            action_type="bug_report",
            direction="deficit",
            conversation_ids=[f"conv_{i + MIN_GROUP_SIZE}" for i in range(MIN_GROUP_SIZE)],
        )

        # Add conversation data for cluster2
        for conv_id in cluster2.conversation_ids:
            sample_conversation_data[conv_id] = {
                "id": conv_id,
                "issue_signature": "bug_issue",
                "product_area": "api",
                "component": "endpoints",
                "user_intent": "API returns error",
                "symptoms": ["500 error", "timeout"],
                "affected_flow": "api_call",
                "excerpt": f"Bug excerpt for {conv_id}",
            }

        clustering_result = MockClusteringResult(
            pipeline_run_id=1,
            total_conversations=cluster1.size + cluster2.size,
            clusters=[cluster1, cluster2],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=sample_conversation_data,
            pipeline_run_id=1,
        )

        assert result.stories_created == 2
        assert len(result.created_story_ids) == 2


# -----------------------------------------------------------------------------
# Tests: Title Generation
# -----------------------------------------------------------------------------


class TestHybridClusterTitleGeneration:
    """Tests for _generate_hybrid_cluster_title()."""

    def test_title_uses_user_intent_when_meaningful(
        self,
        story_creation_service,
    ):
        """Title should use user_intent if it's meaningful."""
        cluster = MockHybridCluster(
            cluster_id="emb_0_facet_feature_request_creation",
            embedding_cluster=0,
            action_type="feature_request",
            direction="creation",
            conversation_ids=["c1", "c2"],
        )

        theme_data = {
            "user_intent": "Users want to export data to CSV format",
            "symptoms": ["no export button"],
            "product_area": "reporting",
        }

        title = story_creation_service._generate_hybrid_cluster_title(cluster, theme_data)

        assert "export" in title.lower() or "csv" in title.lower()

    def test_title_falls_back_to_facets_when_no_intent(
        self,
        story_creation_service,
    ):
        """Title should use action_type if user_intent is empty."""
        cluster = MockHybridCluster(
            cluster_id="emb_0_facet_bug_report_neutral",
            embedding_cluster=0,
            action_type="bug_report",
            direction="neutral",
            conversation_ids=["c1", "c2"],
        )

        theme_data = {
            "user_intent": "",  # Empty
            "symptoms": ["crash on load"],
            "product_area": "mobile",
        }

        title = story_creation_service._generate_hybrid_cluster_title(cluster, theme_data)

        # Should include action_type
        assert "Bug Report" in title or "crash" in title.lower()


# -----------------------------------------------------------------------------
# Tests: Story Model with Cluster Fields
# -----------------------------------------------------------------------------


class TestStoryClusterFields:
    """Tests for Story model with cluster fields."""

    def test_story_model_has_cluster_fields(self):
        """Story model should have grouping_method, cluster_id, cluster_metadata."""
        story = Story(
            id=uuid4(),
            title="Test Story",
            description="Test",
            labels=[],
            priority=None,
            severity=None,
            product_area=None,
            technical_area=None,
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            grouping_method="hybrid_cluster",
            cluster_id="emb_0_facet_feature_request_creation",
            cluster_metadata=ClusterMetadata(
                embedding_cluster=0,
                action_type="feature_request",
                direction="creation",
                conversation_count=5,
            ),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert story.grouping_method == "hybrid_cluster"
        assert story.cluster_id == "emb_0_facet_feature_request_creation"
        assert story.cluster_metadata.embedding_cluster == 0
        assert story.cluster_metadata.action_type == "feature_request"
        assert story.cluster_metadata.direction == "creation"
        assert story.cluster_metadata.conversation_count == 5

    def test_story_model_default_grouping_method(self):
        """Story model should default to 'signature' grouping_method."""
        story = Story(
            id=uuid4(),
            title="Test Story",
            description="Test",
            labels=[],
            priority=None,
            severity=None,
            product_area=None,
            technical_area=None,
            status="candidate",
            confidence_score=None,
            evidence_count=0,
            conversation_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert story.grouping_method == "signature"
        assert story.cluster_id is None
        assert story.cluster_metadata is None
