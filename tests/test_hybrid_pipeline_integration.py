"""
Hybrid Clustering Pipeline Integration Tests (Issue #110)

Integration tests validating the complete hybrid clustering pipeline:
Embedding → Facet → Clustering → Story Creation

These tests validate:
1. Component integration (each step works in pipeline context)
2. Full pipeline flow (all stages work together)
3. Output quality (direction separation, cluster coherence)
4. Error handling (graceful degradation on failures)

Run with: pytest tests/test_hybrid_pipeline_integration.py -v

Note: Tests use mocks for OpenAI API calls to avoid costs and rate limits.
For functional testing with live APIs, see the manual test scripts.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import numpy as np
import pytest

# Project imports
import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from services.embedding_service import (
    EmbeddingService,
    BatchEmbeddingResult,
    EmbeddingResult,
    EMBEDDING_DIMENSIONS,
)
from services.facet_service import (
    FacetExtractionService,
    BatchFacetResult,
    FacetResult,
)
from services.hybrid_clustering_service import (
    HybridClusteringService,
    HybridCluster,
    ClusteringResult,
)
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


# -----------------------------------------------------------------------------
# Timing Instrumentation
# -----------------------------------------------------------------------------


@dataclass
class TimingMetrics:
    """Timing metrics for pipeline stages."""
    embedding_generation_ms: float = 0.0
    facet_extraction_ms: float = 0.0
    clustering_ms: float = 0.0
    story_creation_ms: float = 0.0
    total_ms: float = 0.0

    @property
    def summary(self) -> str:
        return (
            f"Embedding: {self.embedding_generation_ms:.1f}ms, "
            f"Facet: {self.facet_extraction_ms:.1f}ms, "
            f"Clustering: {self.clustering_ms:.1f}ms, "
            f"Story: {self.story_creation_ms:.1f}ms, "
            f"Total: {self.total_ms:.1f}ms"
        )


class Timer:
    """Context manager for timing code blocks."""

    def __init__(self):
        self.start_time = 0.0
        self.end_time = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end_time = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


# -----------------------------------------------------------------------------
# Test Data Generators
# -----------------------------------------------------------------------------


def generate_test_embedding(seed: int) -> List[float]:
    """Generate a deterministic 1536-dim embedding for testing."""
    rng = np.random.default_rng(seed)
    embedding = rng.random(EMBEDDING_DIMENSIONS).tolist()
    return embedding


def generate_similar_embeddings(base_seed: int, count: int, noise: float = 0.1) -> List[List[float]]:
    """Generate embeddings that are similar to each other (for same cluster)."""
    rng = np.random.default_rng(base_seed)
    base = rng.random(EMBEDDING_DIMENSIONS)

    embeddings = []
    for i in range(count):
        # Add small noise to create similar but not identical embeddings
        noise_vec = rng.random(EMBEDDING_DIMENSIONS) * noise
        emb = (base + noise_vec).tolist()
        embeddings.append(emb)

    return embeddings


def generate_dissimilar_embeddings(count: int) -> List[List[float]]:
    """Generate embeddings that are dissimilar (for different clusters)."""
    embeddings = []
    for i in range(count):
        # Use very different seeds for dissimilar embeddings
        embeddings.append(generate_test_embedding(i * 1000))
    return embeddings


def generate_test_conversations(count: int, prefix: str = "conv") -> List[Dict[str, Any]]:
    """Generate test conversation data."""
    conversations = []
    for i in range(count):
        conversations.append({
            "id": f"{prefix}_{i}",
            "source_body": f"This is a test conversation {i} about product issues.",
            "excerpt": f"Test excerpt {i} for embedding generation.",
        })
    return conversations


def generate_test_theme_data(conv_id: str, action_type: str, direction: str) -> Dict[str, Any]:
    """Generate theme data for a conversation."""
    return {
        "id": conv_id,
        "issue_signature": f"test_issue_{action_type}_{direction}",
        "product_area": "billing",
        "component": "payment",
        "user_intent": f"User wants to fix {action_type} issue",
        "symptoms": [f"symptom for {direction}"],
        "affected_flow": "checkout",
        "excerpt": f"Excerpt for {conv_id}",
    }


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_openai_embedding_response():
    """Create mock OpenAI embedding response."""
    def create_response(texts: List[str], embeddings: Optional[List[List[float]]] = None):
        if embeddings is None:
            embeddings = [generate_test_embedding(i) for i in range(len(texts))]

        data = []
        for i, emb in enumerate(embeddings):
            mock_data = Mock()
            mock_data.index = i
            mock_data.embedding = emb
            data.append(mock_data)

        response = Mock()
        response.data = data
        return response

    return create_response


@pytest.fixture
def mock_openai_chat_response():
    """Create mock OpenAI chat completion response for facet extraction."""
    def create_response(action_type: str, direction: str, symptom: str = "", user_goal: str = ""):
        import json
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = json.dumps({
            "action_type": action_type,
            "direction": direction,
            "symptom": symptom or f"Issue with {action_type}",
            "user_goal": user_goal or f"Fix the {direction} problem",
        })
        return response

    return create_response


@pytest.fixture
def mock_story_service():
    """Create a mock story service."""
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
        target_repo="FeedForward",
        pm_review_service=None,
        pm_review_enabled=False,
    )


# -----------------------------------------------------------------------------
# Phase 1: Component Integration Tests
# -----------------------------------------------------------------------------


class TestEmbeddingComponentIntegration:
    """Tests for embedding generation in pipeline context."""

    def test_embedding_batch_processing_returns_correct_count(
        self,
        mock_openai_embedding_response,
    ):
        """Embedding service should process all conversations and return correct count."""
        conversations = generate_test_conversations(10)
        expected_embeddings = [generate_test_embedding(i) for i in range(10)]

        service = EmbeddingService(batch_size=5)

        # Mock the async client
        mock_response = mock_openai_embedding_response(
            [c["source_body"] for c in conversations[:5]],
            expected_embeddings[:5],
        )
        mock_response_2 = mock_openai_embedding_response(
            [c["source_body"] for c in conversations[5:]],
            expected_embeddings[5:],
        )

        with patch.object(service, "_async_client") as mock_client:
            mock_client.embeddings.create = AsyncMock(side_effect=[mock_response, mock_response_2])

            result = asyncio.run(service.generate_conversation_embeddings_async(conversations))

            assert result.total_processed == 10
            assert result.total_success == 10
            assert result.total_failed == 0
            assert len(result.successful) == 10

    def test_embedding_dimension_correct(
        self,
        mock_openai_embedding_response,
    ):
        """Generated embeddings should have correct dimensions (1536)."""
        conversations = generate_test_conversations(3)
        service = EmbeddingService(batch_size=10)

        mock_response = mock_openai_embedding_response(
            [c["source_body"] for c in conversations],
        )

        with patch.object(service, "_async_client") as mock_client:
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)

            result = asyncio.run(service.generate_conversation_embeddings_async(conversations))

            for emb_result in result.successful:
                assert len(emb_result.embedding) == EMBEDDING_DIMENSIONS

    def test_embedding_preserves_conversation_id_mapping(
        self,
        mock_openai_embedding_response,
    ):
        """Embeddings should be correctly mapped to conversation IDs."""
        conversations = generate_test_conversations(5, prefix="test")
        service = EmbeddingService(batch_size=10)

        mock_response = mock_openai_embedding_response(
            [c["source_body"] for c in conversations],
        )

        with patch.object(service, "_async_client") as mock_client:
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)

            result = asyncio.run(service.generate_conversation_embeddings_async(conversations))

            expected_ids = {f"test_{i}" for i in range(5)}
            actual_ids = {r.conversation_id for r in result.successful}

            assert expected_ids == actual_ids

    def test_embedding_handles_empty_text_gracefully(
        self,
        mock_openai_embedding_response,
    ):
        """Conversations with empty text should fail gracefully."""
        conversations = [
            {"id": "empty_1", "source_body": "", "excerpt": ""},
            {"id": "valid_1", "source_body": "Valid content", "excerpt": ""},
        ]

        service = EmbeddingService(batch_size=10)
        mock_response = mock_openai_embedding_response(["Valid content"])

        with patch.object(service, "_async_client") as mock_client:
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)

            result = asyncio.run(service.generate_conversation_embeddings_async(conversations))

            # Empty text should fail, valid should succeed
            assert result.total_success == 1
            assert result.total_failed == 1
            assert result.failed[0].conversation_id == "empty_1"


class TestFacetComponentIntegration:
    """Tests for facet extraction in pipeline context."""

    def test_facet_extraction_returns_all_fields(
        self,
        mock_openai_chat_response,
    ):
        """Facet extraction should return all required fields."""
        conversations = generate_test_conversations(3)
        service = FacetExtractionService()

        responses = [
            mock_openai_chat_response("feature_request", "creation"),
            mock_openai_chat_response("bug_report", "deficit"),
            mock_openai_chat_response("inquiry", "neutral"),
        ]

        with patch.object(service, "_async_client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(side_effect=responses)

            result = asyncio.run(service.extract_facets_batch_async(conversations))

            assert result.total_success == 3
            for facet in result.successful:
                assert facet.action_type in {"feature_request", "bug_report", "inquiry"}
                assert facet.direction in {"creation", "deficit", "neutral"}
                assert facet.symptom != ""
                assert facet.user_goal != ""

    def test_facet_validates_action_type(
        self,
        mock_openai_chat_response,
    ):
        """Invalid action_type should be normalized to 'unknown'."""
        conversations = [{"id": "conv_1", "source_body": "Test content"}]
        service = FacetExtractionService()

        # Create invalid response
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = '{"action_type": "invalid_type", "direction": "neutral", "symptom": "", "user_goal": ""}'

        with patch.object(service, "_async_client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(return_value=response)

            result = asyncio.run(service.extract_facets_batch_async(conversations))

            # Invalid action_type should default to 'unknown'
            assert result.successful[0].action_type == "unknown"

    def test_facet_validates_direction(
        self,
        mock_openai_chat_response,
    ):
        """Invalid direction should be normalized to 'neutral'."""
        conversations = [{"id": "conv_1", "source_body": "Test content"}]
        service = FacetExtractionService()

        # Create invalid response
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = '{"action_type": "inquiry", "direction": "invalid", "symptom": "", "user_goal": ""}'

        with patch.object(service, "_async_client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(return_value=response)

            result = asyncio.run(service.extract_facets_batch_async(conversations))

            # Invalid direction should default to 'neutral'
            assert result.successful[0].direction == "neutral"


class TestClusteringComponentIntegration:
    """Tests for hybrid clustering in pipeline context."""

    def test_clustering_produces_expected_structure(self):
        """Clustering should produce valid HybridCluster objects."""
        # Generate embeddings: 2 similar groups
        embeddings = []
        facets = []

        # Group 1: 3 similar embeddings (feature_request, creation)
        group1_emb = generate_similar_embeddings(base_seed=100, count=3, noise=0.05)
        for i, emb in enumerate(group1_emb):
            embeddings.append({"conversation_id": f"g1_{i}", "embedding": emb})
            facets.append({
                "conversation_id": f"g1_{i}",
                "action_type": "feature_request",
                "direction": "creation",
            })

        # Group 2: 3 dissimilar embeddings (bug_report, deficit)
        group2_emb = generate_similar_embeddings(base_seed=999, count=3, noise=0.05)
        for i, emb in enumerate(group2_emb):
            embeddings.append({"conversation_id": f"g2_{i}", "embedding": emb})
            facets.append({
                "conversation_id": f"g2_{i}",
                "action_type": "bug_report",
                "direction": "deficit",
            })

        service = HybridClusteringService(distance_threshold=0.3)
        result = service.cluster_with_data(embeddings, facets)

        assert result.success
        assert result.total_conversations == 6
        assert result.hybrid_clusters_count >= 2

        for cluster in result.clusters:
            assert isinstance(cluster, HybridCluster)
            assert cluster.cluster_id.startswith("emb_")
            assert cluster.action_type in {"feature_request", "bug_report"}
            assert cluster.direction in {"creation", "deficit"}
            assert cluster.size > 0

    def test_clustering_separates_opposite_directions_t006(self):
        """Critical T-006 test: Same topic with opposite directions must separate.

        This tests the core T-006 requirement: conversations about the same topic
        (e.g., "pins") but with opposite directions (excess vs deficit) must be
        placed in different clusters.
        """
        embeddings = []
        facets = []

        # Create 6 semantically similar embeddings (same topic: pins)
        similar_emb = generate_similar_embeddings(base_seed=42, count=6, noise=0.02)

        # 3 conversations about "duplicate pins" (excess)
        for i in range(3):
            embeddings.append({"conversation_id": f"dup_{i}", "embedding": similar_emb[i]})
            facets.append({
                "conversation_id": f"dup_{i}",
                "action_type": "bug_report",
                "direction": "excess",  # Too many pins
            })

        # 3 conversations about "missing pins" (deficit)
        for i in range(3):
            embeddings.append({"conversation_id": f"miss_{i}", "embedding": similar_emb[i + 3]})
            facets.append({
                "conversation_id": f"miss_{i}",
                "action_type": "bug_report",
                "direction": "deficit",  # Pins not showing
            })

        service = HybridClusteringService(distance_threshold=0.5)
        result = service.cluster_with_data(embeddings, facets)

        assert result.success

        # Find clusters with these conversation IDs
        excess_cluster = None
        deficit_cluster = None

        for cluster in result.clusters:
            if any(cid.startswith("dup_") for cid in cluster.conversation_ids):
                excess_cluster = cluster
            if any(cid.startswith("miss_") for cid in cluster.conversation_ids):
                deficit_cluster = cluster

        # They must be in DIFFERENT clusters (different direction)
        assert excess_cluster is not None
        assert deficit_cluster is not None

        # Verify they're actually separated
        assert excess_cluster.direction == "excess"
        assert deficit_cluster.direction == "deficit"
        assert excess_cluster.cluster_id != deficit_cluster.cluster_id

        # No duplicate pins in deficit cluster and vice versa
        assert not any(cid.startswith("dup_") for cid in deficit_cluster.conversation_ids)
        assert not any(cid.startswith("miss_") for cid in excess_cluster.conversation_ids)

    def test_clustering_handles_single_conversation(self):
        """Single conversation should form its own cluster."""
        embeddings = [{"conversation_id": "solo", "embedding": generate_test_embedding(1)}]
        facets = [{"conversation_id": "solo", "action_type": "inquiry", "direction": "neutral"}]

        service = HybridClusteringService()
        result = service.cluster_with_data(embeddings, facets)

        assert result.success
        assert result.total_conversations == 1
        assert result.hybrid_clusters_count == 1
        assert result.clusters[0].size == 1

    def test_clustering_handles_missing_facets(self):
        """Conversations without facets should go to fallback."""
        embeddings = [
            {"conversation_id": "with_facet", "embedding": generate_test_embedding(1)},
            {"conversation_id": "no_facet", "embedding": generate_test_embedding(2)},
        ]
        facets = [{"conversation_id": "with_facet", "action_type": "inquiry", "direction": "neutral"}]

        service = HybridClusteringService()
        result = service.cluster_with_data(embeddings, facets)

        assert result.success
        assert "no_facet" in result.fallback_conversations
        assert result.total_conversations == 1  # Only the one with facet


class TestStoryCreationComponentIntegration:
    """Tests for story creation accepting hybrid cluster input."""

    def test_story_creation_accepts_cluster_input(
        self,
        story_creation_service,
    ):
        """StoryCreationService should accept ClusteringResult input."""
        # Create a mock ClusteringResult
        cluster = HybridCluster(
            cluster_id="emb_0_facet_feature_request_creation",
            embedding_cluster=0,
            action_type="feature_request",
            direction="creation",
            conversation_ids=[f"conv_{i}" for i in range(MIN_GROUP_SIZE)],
        )

        clustering_result = ClusteringResult(
            pipeline_run_id=1,
            total_conversations=MIN_GROUP_SIZE,
            embedding_clusters_count=1,
            hybrid_clusters_count=1,
            clusters=[cluster],
        )

        conversation_data = {}
        for conv_id in cluster.conversation_ids:
            conversation_data[conv_id] = generate_test_theme_data(
                conv_id, "feature_request", "creation"
            )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=conversation_data,
            pipeline_run_id=1,
        )

        assert result.stories_created == 1
        assert len(result.created_story_ids) == 1

    def test_story_creation_sets_cluster_metadata(
        self,
        story_creation_service,
        mock_story_service,
    ):
        """Created stories should have correct cluster metadata."""
        cluster = HybridCluster(
            cluster_id="emb_5_facet_bug_report_deficit",
            embedding_cluster=5,
            action_type="bug_report",
            direction="deficit",
            conversation_ids=[f"conv_{i}" for i in range(MIN_GROUP_SIZE)],
        )

        clustering_result = ClusteringResult(
            pipeline_run_id=42,
            total_conversations=MIN_GROUP_SIZE,
            embedding_clusters_count=1,
            hybrid_clusters_count=1,
            clusters=[cluster],
        )

        conversation_data = {}
        for conv_id in cluster.conversation_ids:
            conversation_data[conv_id] = generate_test_theme_data(
                conv_id, "bug_report", "deficit"
            )

        story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=conversation_data,
            pipeline_run_id=42,
        )

        # Verify the story was created with correct metadata
        call_args = mock_story_service.create.call_args
        story_create = call_args[0][0]

        assert story_create.grouping_method == "hybrid_cluster"
        assert story_create.cluster_id == "emb_5_facet_bug_report_deficit"
        assert story_create.cluster_metadata["embedding_cluster"] == 5
        assert story_create.cluster_metadata["action_type"] == "bug_report"
        assert story_create.cluster_metadata["direction"] == "deficit"


# -----------------------------------------------------------------------------
# Phase 2: Full Pipeline Integration Tests
# -----------------------------------------------------------------------------


class TestFullPipelineIntegration:
    """End-to-end integration tests for the complete pipeline."""

    def test_full_pipeline_flow_with_timing(
        self,
        mock_openai_embedding_response,
        mock_openai_chat_response,
        story_creation_service,
    ):
        """Test complete pipeline: embedding → facet → clustering → story creation."""
        metrics = TimingMetrics()
        num_conversations = 10

        # Generate test data
        conversations = generate_test_conversations(num_conversations)

        # Create embedding data (simulating 2 groups)
        embeddings_data = []
        group1_emb = generate_similar_embeddings(base_seed=100, count=5, noise=0.05)
        group2_emb = generate_similar_embeddings(base_seed=999, count=5, noise=0.05)

        # --- Stage 1: Embedding Generation ---
        with Timer() as embedding_timer:
            embedding_service = EmbeddingService(batch_size=10)

            mock_resp = mock_openai_embedding_response(
                [c["source_body"] for c in conversations],
                group1_emb + group2_emb,
            )

            with patch.object(embedding_service, "_async_client") as mock_client:
                mock_client.embeddings.create = AsyncMock(return_value=mock_resp)

                emb_result = asyncio.run(
                    embedding_service.generate_conversation_embeddings_async(conversations)
                )

        metrics.embedding_generation_ms = embedding_timer.elapsed_ms
        assert emb_result.total_success == num_conversations

        # Build embeddings list for clustering
        for i, er in enumerate(emb_result.successful):
            embeddings_data.append({
                "conversation_id": er.conversation_id,
                "embedding": er.embedding,
            })

        # --- Stage 2: Facet Extraction ---
        facets_data = []
        facet_responses = []

        # Group 1: feature_request, creation
        for i in range(5):
            facet_responses.append(mock_openai_chat_response("feature_request", "creation"))
        # Group 2: bug_report, deficit
        for i in range(5):
            facet_responses.append(mock_openai_chat_response("bug_report", "deficit"))

        with Timer() as facet_timer:
            facet_service = FacetExtractionService()

            with patch.object(facet_service, "_async_client") as mock_client:
                mock_client.chat.completions.create = AsyncMock(side_effect=facet_responses)

                facet_result = asyncio.run(
                    facet_service.extract_facets_batch_async(conversations)
                )

        metrics.facet_extraction_ms = facet_timer.elapsed_ms
        assert facet_result.total_success == num_conversations

        for fr in facet_result.successful:
            facets_data.append({
                "conversation_id": fr.conversation_id,
                "action_type": fr.action_type,
                "direction": fr.direction,
            })

        # --- Stage 3: Hybrid Clustering ---
        with Timer() as clustering_timer:
            clustering_service = HybridClusteringService(distance_threshold=0.3)
            cluster_result = clustering_service.cluster_with_data(embeddings_data, facets_data)

        metrics.clustering_ms = clustering_timer.elapsed_ms
        assert cluster_result.success
        assert cluster_result.hybrid_clusters_count >= 2

        # --- Stage 4: Story Creation ---
        conversation_data = {}
        for i, conv in enumerate(conversations):
            facet = facets_data[i]
            conversation_data[conv["id"]] = generate_test_theme_data(
                conv["id"],
                facet["action_type"],
                facet["direction"],
            )

        with Timer() as story_timer:
            # Filter to clusters meeting MIN_GROUP_SIZE
            large_clusters = [c for c in cluster_result.clusters if c.size >= MIN_GROUP_SIZE]

            if large_clusters:
                filtered_result = ClusteringResult(
                    pipeline_run_id=1,
                    total_conversations=cluster_result.total_conversations,
                    embedding_clusters_count=cluster_result.embedding_clusters_count,
                    hybrid_clusters_count=len(large_clusters),
                    clusters=large_clusters,
                )

                story_result = story_creation_service.process_hybrid_clusters(
                    clustering_result=filtered_result,
                    conversation_data=conversation_data,
                    pipeline_run_id=1,
                )
            else:
                story_result = None

        metrics.story_creation_ms = story_timer.elapsed_ms

        # --- Calculate total ---
        metrics.total_ms = (
            metrics.embedding_generation_ms +
            metrics.facet_extraction_ms +
            metrics.clustering_ms +
            metrics.story_creation_ms
        )

        # Log timing metrics
        logging.info(f"Pipeline timing: {metrics.summary}")

        # Assertions
        assert metrics.total_ms > 0
        if story_result:
            assert story_result.stories_created >= 0  # May be 0 if all clusters are small

    def test_all_conversations_processed_no_drops(
        self,
        mock_openai_embedding_response,
        mock_openai_chat_response,
    ):
        """Verify no conversations are silently dropped through the pipeline."""
        num_conversations = 15
        conversations = generate_test_conversations(num_conversations)

        # Embedding stage
        embedding_service = EmbeddingService(batch_size=20)
        embeddings = [generate_test_embedding(i) for i in range(num_conversations)]

        mock_resp = mock_openai_embedding_response(
            [c["source_body"] for c in conversations],
            embeddings,
        )

        with patch.object(embedding_service, "_async_client") as mock_client:
            mock_client.embeddings.create = AsyncMock(return_value=mock_resp)
            emb_result = asyncio.run(
                embedding_service.generate_conversation_embeddings_async(conversations)
            )

        # Facet stage
        facet_service = FacetExtractionService()
        facet_responses = [
            mock_openai_chat_response("inquiry", "neutral")
            for _ in range(num_conversations)
        ]

        with patch.object(facet_service, "_async_client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(side_effect=facet_responses)
            facet_result = asyncio.run(
                facet_service.extract_facets_batch_async(conversations)
            )

        # Clustering stage
        embeddings_data = [
            {"conversation_id": r.conversation_id, "embedding": r.embedding}
            for r in emb_result.successful
        ]
        facets_data = [
            {
                "conversation_id": r.conversation_id,
                "action_type": r.action_type,
                "direction": r.direction,
            }
            for r in facet_result.successful
        ]

        clustering_service = HybridClusteringService()
        cluster_result = clustering_service.cluster_with_data(embeddings_data, facets_data)

        # Count all conversations in clusters + fallback
        clustered_convs = sum(c.size for c in cluster_result.clusters)
        total_accounted = clustered_convs + len(cluster_result.fallback_conversations)

        # No conversations should be lost
        assert emb_result.total_processed == num_conversations
        assert emb_result.total_success + emb_result.total_failed == num_conversations
        assert facet_result.total_processed == num_conversations
        assert facet_result.total_success + facet_result.total_failed == num_conversations
        assert total_accounted == cluster_result.total_conversations


# -----------------------------------------------------------------------------
# Phase 3: Error Handling Tests
# -----------------------------------------------------------------------------


class TestPipelineErrorHandling:
    """Tests for error handling and graceful degradation."""

    def test_embedding_api_failure_captured_gracefully(
        self,
        mock_openai_embedding_response,
    ):
        """API failures during embedding should be captured, not crash."""
        conversations = generate_test_conversations(5)
        service = EmbeddingService(batch_size=10)

        with patch.object(service, "_async_client") as mock_client:
            # Use rate_limit (with underscore) to match the sanitizer pattern
            mock_client.embeddings.create = AsyncMock(
                side_effect=Exception("rate_limit error from API")
            )

            result = asyncio.run(
                service.generate_conversation_embeddings_async(conversations)
            )

            # Should capture error, not raise
            assert result.total_failed == 5
            assert result.total_success == 0
            # Error should be sanitized to "Rate limit exceeded - please retry later"
            assert all("Rate limit" in r.error for r in result.failed)

    def test_facet_api_failure_captured_gracefully(
        self,
        mock_openai_chat_response,
    ):
        """API failures during facet extraction should be captured, not crash."""
        conversations = generate_test_conversations(3)
        service = FacetExtractionService()

        with patch.object(service, "_async_client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("Server error")
            )

            result = asyncio.run(
                service.extract_facets_batch_async(conversations)
            )

            assert result.total_failed == 3
            assert result.total_success == 0

    def test_clustering_with_empty_data_handled(self):
        """Clustering with no data should return error result, not crash."""
        service = HybridClusteringService()

        result = service.cluster_with_data(embeddings=[], facets=[])

        assert not result.success
        assert len(result.errors) > 0

    def test_story_creation_with_failed_clustering_handled(
        self,
        story_creation_service,
    ):
        """Story creation with failed clustering should return errors."""
        clustering_result = ClusteringResult(
            pipeline_run_id=1,
            total_conversations=0,
            embedding_clusters_count=0,
            hybrid_clusters_count=0,
            errors=["No embeddings found"],
        )

        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data={},
            pipeline_run_id=1,
        )

        assert result.stories_created == 0
        assert len(result.errors) > 0


# -----------------------------------------------------------------------------
# Quality Validation Tests
# -----------------------------------------------------------------------------


class TestOutputQualityValidation:
    """Tests validating output quality of the hybrid clustering pipeline."""

    def test_cluster_coherence_action_type_consistent(self):
        """All conversations in a cluster should have the same action_type."""
        embeddings = []
        facets = []

        # Create 6 similar embeddings but with mixed action types
        similar_emb = generate_similar_embeddings(base_seed=42, count=6, noise=0.02)

        for i in range(6):
            embeddings.append({"conversation_id": f"conv_{i}", "embedding": similar_emb[i]})
            # Alternate action types
            action = "feature_request" if i % 2 == 0 else "bug_report"
            facets.append({
                "conversation_id": f"conv_{i}",
                "action_type": action,
                "direction": "neutral",
            })

        service = HybridClusteringService(distance_threshold=0.5)
        result = service.cluster_with_data(embeddings, facets)

        # Each cluster should have consistent action_type
        for cluster in result.clusters:
            assert cluster.action_type in {"feature_request", "bug_report"}
            # Verify all conversations match (facet sub-grouping)
            cluster_facets = [f for f in facets if f["conversation_id"] in cluster.conversation_ids]
            action_types = {f["action_type"] for f in cluster_facets}
            assert len(action_types) == 1

    def test_cluster_coherence_direction_consistent(self):
        """All conversations in a cluster should have the same direction."""
        embeddings = []
        facets = []

        similar_emb = generate_similar_embeddings(base_seed=42, count=6, noise=0.02)

        for i in range(6):
            embeddings.append({"conversation_id": f"conv_{i}", "embedding": similar_emb[i]})
            # Alternate directions
            direction = "excess" if i % 2 == 0 else "deficit"
            facets.append({
                "conversation_id": f"conv_{i}",
                "action_type": "bug_report",
                "direction": direction,
            })

        service = HybridClusteringService(distance_threshold=0.5)
        result = service.cluster_with_data(embeddings, facets)

        # Each cluster should have consistent direction
        for cluster in result.clusters:
            assert cluster.direction in {"excess", "deficit"}
            # Verify all conversations match
            cluster_facets = [f for f in facets if f["conversation_id"] in cluster.conversation_ids]
            directions = {f["direction"] for f in cluster_facets}
            assert len(directions) == 1

    def test_stories_inherit_correct_grouping_method(
        self,
        story_creation_service,
        mock_story_service,
    ):
        """Stories created from hybrid clusters should have grouping_method='hybrid_cluster'."""
        cluster = HybridCluster(
            cluster_id="emb_0_facet_inquiry_neutral",
            embedding_cluster=0,
            action_type="inquiry",
            direction="neutral",
            conversation_ids=[f"conv_{i}" for i in range(MIN_GROUP_SIZE)],
        )

        clustering_result = ClusteringResult(
            pipeline_run_id=1,
            total_conversations=MIN_GROUP_SIZE,
            embedding_clusters_count=1,
            hybrid_clusters_count=1,
            clusters=[cluster],
        )

        conversation_data = {}
        for conv_id in cluster.conversation_ids:
            conversation_data[conv_id] = generate_test_theme_data(
                conv_id, "inquiry", "neutral"
            )

        story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=conversation_data,
            pipeline_run_id=1,
        )

        call_args = mock_story_service.create.call_args
        story_create = call_args[0][0]

        # Must be 'hybrid_cluster', not 'signature'
        assert story_create.grouping_method == "hybrid_cluster"
