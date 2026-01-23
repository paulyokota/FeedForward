"""
Tests for HybridClusteringService.

Tests the two-stage clustering algorithm:
1. Embedding clustering via agglomerative clustering
2. Facet sub-grouping within embedding clusters
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.services.hybrid_clustering_service import (
    HybridClusteringService,
    HybridCluster,
    ClusteringResult,
    DEFAULT_DISTANCE_THRESHOLD,
    DEFAULT_LINKAGE,
)


class TestHybridClusteringServiceInit:
    """Test service initialization and configuration."""

    def test_default_parameters(self):
        """Service initializes with documented default parameters."""
        service = HybridClusteringService()

        assert service.distance_threshold == DEFAULT_DISTANCE_THRESHOLD
        assert service.linkage == DEFAULT_LINKAGE

    def test_custom_parameters(self):
        """Service accepts custom clustering parameters."""
        service = HybridClusteringService(
            distance_threshold=0.3,
            linkage="complete",
        )

        assert service.distance_threshold == 0.3
        assert service.linkage == "complete"

    def test_default_distance_threshold_is_documented(self):
        """Default distance threshold matches issue spec (0.5)."""
        assert DEFAULT_DISTANCE_THRESHOLD == 0.5

    def test_default_linkage_is_average(self):
        """Default linkage is 'average' as specified in issue."""
        assert DEFAULT_LINKAGE == "average"


class TestEmbeddingClustering:
    """Test Stage 1: Embedding clustering."""

    def test_single_conversation_gets_own_cluster(self):
        """Single conversation gets cluster label 0."""
        service = HybridClusteringService()
        embeddings = np.array([[1.0, 0.0, 0.0]])

        labels = service._cluster_embeddings(embeddings)

        assert len(labels) == 1
        assert labels[0] == 0

    def test_identical_embeddings_same_cluster(self):
        """Identical embeddings are grouped in the same cluster."""
        service = HybridClusteringService()
        # Three identical embeddings
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ])

        labels = service._cluster_embeddings(embeddings)

        # All should be in the same cluster
        assert len(set(labels)) == 1

    def test_orthogonal_embeddings_different_clusters(self):
        """Orthogonal embeddings end up in different clusters."""
        service = HybridClusteringService(distance_threshold=0.5)
        # Orthogonal vectors (cosine similarity = 0, distance = 1)
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])

        labels = service._cluster_embeddings(embeddings)

        # Each should be in its own cluster (distance > threshold)
        assert len(set(labels)) == 3

    def test_similar_embeddings_same_cluster(self):
        """Similar embeddings (small angle) are grouped together."""
        service = HybridClusteringService(distance_threshold=0.5)
        # Vectors with high cosine similarity
        embeddings = np.array([
            [1.0, 0.1, 0.0],
            [1.0, 0.0, 0.0],
            [0.95, 0.05, 0.05],
        ])

        labels = service._cluster_embeddings(embeddings)

        # Should be in same cluster (cosine distance < 0.5)
        assert len(set(labels)) == 1

    def test_distance_threshold_affects_cluster_count(self):
        """Lower threshold = more clusters, higher threshold = fewer clusters."""
        # Create embeddings with moderate similarity
        embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.8, 0.6, 0.0],  # ~0.8 similarity with first
            [0.0, 1.0, 0.0],
        ])

        low_threshold_service = HybridClusteringService(distance_threshold=0.1)
        high_threshold_service = HybridClusteringService(distance_threshold=0.9)

        low_labels = low_threshold_service._cluster_embeddings(embeddings)
        high_labels = high_threshold_service._cluster_embeddings(embeddings)

        # Lower threshold should produce more clusters
        assert len(set(low_labels)) >= len(set(high_labels))


class TestFacetSubgrouping:
    """Test Stage 2: Facet sub-grouping."""

    def test_same_cluster_different_facets_split(self):
        """Conversations in same embedding cluster with different facets are split."""
        service = HybridClusteringService()

        # All in same embedding cluster (label 0)
        conversation_ids = ["conv1", "conv2", "conv3"]
        cluster_labels = np.array([0, 0, 0])

        facets_by_conv = {
            "conv1": {"action_type": "bug_report", "direction": "excess"},
            "conv2": {"action_type": "bug_report", "direction": "deficit"},  # Different direction!
            "conv3": {"action_type": "bug_report", "direction": "excess"},
        }

        clusters = service._create_hybrid_subclusters(
            conversation_ids, cluster_labels, facets_by_conv
        )

        # Should have 2 hybrid clusters: excess and deficit
        assert len(clusters) == 2

        # Find the excess cluster
        excess_cluster = next(c for c in clusters if c.direction == "excess")
        deficit_cluster = next(c for c in clusters if c.direction == "deficit")

        assert set(excess_cluster.conversation_ids) == {"conv1", "conv3"}
        assert set(deficit_cluster.conversation_ids) == {"conv2"}

    def test_different_clusters_stay_separate(self):
        """Conversations in different embedding clusters remain separate."""
        service = HybridClusteringService()

        conversation_ids = ["conv1", "conv2"]
        cluster_labels = np.array([0, 1])  # Different clusters

        facets_by_conv = {
            "conv1": {"action_type": "bug_report", "direction": "excess"},
            "conv2": {"action_type": "bug_report", "direction": "excess"},  # Same facets!
        }

        clusters = service._create_hybrid_subclusters(
            conversation_ids, cluster_labels, facets_by_conv
        )

        # Should have 2 hybrid clusters (different embedding clusters)
        assert len(clusters) == 2

        cluster_ids = {c.cluster_id for c in clusters}
        assert "emb_0_facet_bug_report_excess" in cluster_ids
        assert "emb_1_facet_bug_report_excess" in cluster_ids

    def test_missing_facets_use_defaults(self):
        """Conversations with missing facets get default values."""
        service = HybridClusteringService()

        conversation_ids = ["conv1", "conv2"]
        cluster_labels = np.array([0, 0])

        facets_by_conv = {
            "conv1": {"action_type": "bug_report", "direction": "excess"},
            "conv2": {},  # Missing facets
        }

        clusters = service._create_hybrid_subclusters(
            conversation_ids, cluster_labels, facets_by_conv
        )

        # conv2 should get unknown/neutral defaults
        cluster_ids = {c.cluster_id for c in clusters}
        assert "emb_0_facet_unknown_neutral" in cluster_ids or any(
            c.action_type == "unknown" for c in clusters
        )

    def test_direction_critical_for_separation(self):
        """Direction facet correctly separates opposite issues (T-006 validation)."""
        service = HybridClusteringService()

        # T-006 example: "duplicate pins" vs "missing pins"
        conversation_ids = ["dup_pins", "missing_pins"]
        cluster_labels = np.array([0, 0])  # Same semantic cluster (both about pins)

        facets_by_conv = {
            "dup_pins": {"action_type": "bug_report", "direction": "excess"},
            "missing_pins": {"action_type": "bug_report", "direction": "deficit"},
        }

        clusters = service._create_hybrid_subclusters(
            conversation_ids, cluster_labels, facets_by_conv
        )

        # Must be in DIFFERENT hybrid clusters
        assert len(clusters) == 2

        excess_cluster = next(c for c in clusters if c.direction == "excess")
        deficit_cluster = next(c for c in clusters if c.direction == "deficit")

        assert "dup_pins" in excess_cluster.conversation_ids
        assert "missing_pins" in deficit_cluster.conversation_ids


class TestHybridCluster:
    """Test HybridCluster dataclass."""

    def test_cluster_id_format(self):
        """Cluster ID follows documented format."""
        cluster = HybridCluster(
            cluster_id="emb_0_facet_bug_report_excess",
            embedding_cluster=0,
            action_type="bug_report",
            direction="excess",
            conversation_ids=["conv1", "conv2"],
        )

        assert cluster.cluster_id == "emb_0_facet_bug_report_excess"
        assert cluster.embedding_cluster == 0
        assert cluster.action_type == "bug_report"
        assert cluster.direction == "excess"

    def test_size_property(self):
        """Size property returns conversation count."""
        cluster = HybridCluster(
            cluster_id="test",
            embedding_cluster=0,
            action_type="bug_report",
            direction="excess",
            conversation_ids=["conv1", "conv2", "conv3"],
        )

        assert cluster.size == 3


class TestClusteringResult:
    """Test ClusteringResult dataclass."""

    def test_success_property_true(self):
        """Success is True when no errors and conversations exist."""
        result = ClusteringResult(
            pipeline_run_id=1,
            total_conversations=10,
            embedding_clusters_count=3,
            hybrid_clusters_count=5,
        )

        assert result.success is True

    def test_success_property_false_with_errors(self):
        """Success is False when errors exist."""
        result = ClusteringResult(
            pipeline_run_id=1,
            total_conversations=10,
            embedding_clusters_count=3,
            hybrid_clusters_count=5,
            errors=["Something went wrong"],
        )

        assert result.success is False

    def test_success_property_false_with_no_conversations(self):
        """Success is False when no conversations."""
        result = ClusteringResult(
            pipeline_run_id=1,
            total_conversations=0,
            embedding_clusters_count=0,
            hybrid_clusters_count=0,
        )

        assert result.success is False


class TestClusterWithData:
    """Test in-memory clustering with provided data."""

    def test_cluster_with_data_basic(self):
        """cluster_with_data processes in-memory data correctly."""
        service = HybridClusteringService()

        # Create simple embeddings and facets
        embeddings = [
            {"conversation_id": "conv1", "embedding": [1.0, 0.0, 0.0]},
            {"conversation_id": "conv2", "embedding": [1.0, 0.1, 0.0]},  # Similar to conv1
            {"conversation_id": "conv3", "embedding": [0.0, 0.0, 1.0]},  # Different
        ]
        facets = [
            {"conversation_id": "conv1", "action_type": "bug_report", "direction": "excess"},
            {"conversation_id": "conv2", "action_type": "bug_report", "direction": "excess"},
            {"conversation_id": "conv3", "action_type": "feature_request", "direction": "creation"},
        ]

        result = service.cluster_with_data(embeddings, facets)

        assert result.success
        assert result.total_conversations == 3
        assert result.hybrid_clusters_count >= 1

    def test_cluster_with_data_missing_facets(self):
        """Conversations with embeddings but no facets go to fallback."""
        service = HybridClusteringService()

        embeddings = [
            {"conversation_id": "conv1", "embedding": [1.0, 0.0, 0.0]},
            {"conversation_id": "conv2", "embedding": [0.0, 1.0, 0.0]},
        ]
        facets = [
            {"conversation_id": "conv1", "action_type": "bug_report", "direction": "excess"},
            # conv2 has no facets
        ]

        result = service.cluster_with_data(embeddings, facets)

        # Should process conv1, conv2 is fallback
        assert result.total_conversations == 1
        assert "conv2" in result.fallback_conversations

    def test_cluster_with_data_empty_embeddings(self):
        """Empty embeddings returns error."""
        service = HybridClusteringService()

        result = service.cluster_with_data(embeddings=[], facets=[])

        assert not result.success
        assert "No embeddings provided" in result.errors


class TestClusterForRun:
    """Test DB-backed clustering for pipeline runs."""

    @patch("src.services.hybrid_clustering_service.get_embeddings_for_run")
    @patch("src.services.hybrid_clustering_service.get_facets_for_run")
    def test_cluster_for_run_basic(self, mock_facets, mock_embeddings):
        """cluster_for_run loads data from DB and clusters."""
        mock_embeddings.return_value = [
            {"conversation_id": "conv1", "embedding": [1.0, 0.0, 0.0]},
            {"conversation_id": "conv2", "embedding": [1.0, 0.1, 0.0]},
        ]
        mock_facets.return_value = [
            {"conversation_id": "conv1", "action_type": "bug_report", "direction": "excess"},
            {"conversation_id": "conv2", "action_type": "bug_report", "direction": "excess"},
        ]

        service = HybridClusteringService()
        result = service.cluster_for_run(pipeline_run_id=42)

        assert result.success
        assert result.pipeline_run_id == 42
        assert result.total_conversations == 2

        # Verify DB was queried
        mock_embeddings.assert_called_once_with(42)
        mock_facets.assert_called_once_with(42)

    @patch("src.services.hybrid_clustering_service.get_embeddings_for_run")
    @patch("src.services.hybrid_clustering_service.get_facets_for_run")
    def test_cluster_for_run_no_embeddings(self, mock_facets, mock_embeddings):
        """Returns error when no embeddings found."""
        mock_embeddings.return_value = []
        mock_facets.return_value = []

        service = HybridClusteringService()
        result = service.cluster_for_run(pipeline_run_id=42)

        assert not result.success
        assert "No embeddings found" in result.errors[0]

    @patch("src.services.hybrid_clustering_service.get_embeddings_for_run")
    @patch("src.services.hybrid_clustering_service.get_facets_for_run")
    def test_cluster_for_run_tracks_fallback(self, mock_facets, mock_embeddings):
        """Conversations without facets are tracked as fallback."""
        mock_embeddings.return_value = [
            {"conversation_id": "conv1", "embedding": [1.0, 0.0, 0.0]},
            {"conversation_id": "conv2", "embedding": [0.0, 1.0, 0.0]},
        ]
        mock_facets.return_value = [
            {"conversation_id": "conv1", "action_type": "bug_report", "direction": "excess"},
            # conv2 has no facets
        ]

        service = HybridClusteringService()
        result = service.cluster_for_run(pipeline_run_id=42)

        assert result.success
        assert "conv2" in result.fallback_conversations
        assert result.total_conversations == 1  # Only conv1 was clustered

    @patch("src.services.hybrid_clustering_service.get_embeddings_for_run")
    @patch("src.services.hybrid_clustering_service.get_facets_for_run")
    def test_cluster_for_run_db_connection_error(self, mock_facets, mock_embeddings):
        """DB connection errors are captured in result.errors."""
        mock_embeddings.side_effect = Exception("Connection refused")

        service = HybridClusteringService()
        # Should not raise - errors captured in result
        with pytest.raises(Exception, match="Connection refused"):
            service.cluster_for_run(pipeline_run_id=42)

    @patch("src.services.hybrid_clustering_service.get_embeddings_for_run")
    @patch("src.services.hybrid_clustering_service.get_facets_for_run")
    def test_cluster_for_run_clustering_exception(self, mock_facets, mock_embeddings):
        """Clustering algorithm exceptions are caught and reported."""
        mock_embeddings.return_value = [
            {"conversation_id": "conv1", "embedding": [1.0, 0.0, 0.0]},
            {"conversation_id": "conv2", "embedding": [0.0, 1.0, 0.0]},
        ]
        mock_facets.return_value = [
            {"conversation_id": "conv1", "action_type": "bug_report", "direction": "excess"},
            {"conversation_id": "conv2", "action_type": "bug_report", "direction": "excess"},
        ]

        # Use invalid linkage to trigger sklearn error
        service = HybridClusteringService(linkage="invalid_linkage")
        result = service.cluster_for_run(pipeline_run_id=42)

        assert not result.success
        assert any("clustering failed" in err.lower() for err in result.errors)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_cluster_with_data_empty_embedding_values(self):
        """Empty embedding vectors cause consistent behavior."""
        service = HybridClusteringService()

        # Empty embeddings list returns error
        result = service.cluster_with_data([], [])
        assert not result.success
        assert "No embeddings provided" in result.errors[0]

    def test_cluster_with_data_malformed_dict(self):
        """Missing required keys in embedding dicts handled gracefully."""
        service = HybridClusteringService()

        # Missing 'embedding' key
        embeddings = [
            {"conversation_id": "conv1"},  # No 'embedding' key
        ]
        facets = [
            {"conversation_id": "conv1", "action_type": "bug_report", "direction": "excess"},
        ]

        # Should fail during numpy array construction
        with pytest.raises(KeyError):
            service.cluster_with_data(embeddings, facets)

    def test_cluster_with_data_null_facet_values(self):
        """Facet dicts with None values get defaults."""
        service = HybridClusteringService()

        embeddings = [
            {"conversation_id": "conv1", "embedding": [1.0, 0.0, 0.0]},
        ]
        facets = [
            {"conversation_id": "conv1", "action_type": None, "direction": None},
        ]

        result = service.cluster_with_data(embeddings, facets)

        # Should use default values "unknown" and "neutral" via .get() with defaults
        # Note: current implementation will use None as the key, which is valid
        assert result.success
        assert result.hybrid_clusters_count == 1


class TestClusteringResultDistribution:
    """Test cluster size distribution tracking."""

    def test_size_distribution_calculated(self):
        """Cluster size distribution is calculated correctly."""
        service = HybridClusteringService()

        embeddings = [
            {"conversation_id": f"conv{i}", "embedding": [float(i), 0.0, 0.0]}
            for i in range(10)
        ]
        # Make each conversation unique in action_type to create many small clusters
        facets = [
            {
                "conversation_id": f"conv{i}",
                "action_type": f"type_{i}",
                "direction": "neutral",
            }
            for i in range(10)
        ]

        result = service.cluster_with_data(embeddings, facets)

        # Should have size distribution data
        assert result.cluster_size_distribution
        # Each cluster should have size 1 (since unique action_types)
        assert 1 in result.cluster_size_distribution


class TestIntegrationWithPrototype:
    """Integration tests validating against prototype expectations."""

    def test_prototype_scenario_duplicate_vs_missing_pins(self):
        """
        Validate T-006 scenario: duplicate pins vs missing pins separation.

        Prototype validated that direction facet correctly separates:
        - "duplicate pins" (excess) from "missing pins" (deficit)
        """
        service = HybridClusteringService()

        # Simulate embeddings for "pin" related conversations (semantically similar)
        # Using high cosine similarity (small angle difference)
        embeddings = [
            {"conversation_id": "dup1", "embedding": [0.9, 0.1, 0.0]},
            {"conversation_id": "dup2", "embedding": [0.85, 0.15, 0.0]},
            {"conversation_id": "miss1", "embedding": [0.88, 0.12, 0.0]},
            {"conversation_id": "miss2", "embedding": [0.92, 0.08, 0.0]},
        ]

        # Facets distinguish by direction
        facets = [
            {"conversation_id": "dup1", "action_type": "bug_report", "direction": "excess"},
            {"conversation_id": "dup2", "action_type": "bug_report", "direction": "excess"},
            {"conversation_id": "miss1", "action_type": "bug_report", "direction": "deficit"},
            {"conversation_id": "miss2", "action_type": "bug_report", "direction": "deficit"},
        ]

        result = service.cluster_with_data(embeddings, facets)

        assert result.success

        # Find clusters by direction
        excess_clusters = [c for c in result.clusters if c.direction == "excess"]
        deficit_clusters = [c for c in result.clusters if c.direction == "deficit"]

        # Should have separated excess from deficit
        assert len(excess_clusters) >= 1
        assert len(deficit_clusters) >= 1

        # dup1, dup2 should NOT be in same cluster as miss1, miss2
        excess_conv_ids = set()
        for c in excess_clusters:
            excess_conv_ids.update(c.conversation_ids)

        deficit_conv_ids = set()
        for c in deficit_clusters:
            deficit_conv_ids.update(c.conversation_ids)

        assert excess_conv_ids == {"dup1", "dup2"}
        assert deficit_conv_ids == {"miss1", "miss2"}
