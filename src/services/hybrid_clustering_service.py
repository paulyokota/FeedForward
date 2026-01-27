"""
HybridClusteringService: Combine embeddings + facet sub-grouping for story clustering.

This service implements a two-stage clustering algorithm:

Stage 1 - Embedding Clustering:
    Group conversations by semantic similarity using agglomerative clustering
    on embeddings. Conversations about similar topics end up in the same cluster.

Stage 2 - Facet Sub-grouping:
    Within each embedding cluster, split by `action_type | direction`, or
    `direction | product_area` when theme data is available. This is critical for distinguishing:
    - "duplicate pins" (excess) vs "missing pins" (deficit)
    - "create smart pin" (creation) vs "remove smart pin" (deletion)

Output:
    Each hybrid sub-cluster becomes a candidate story group with:
    - Same semantic topic (from embedding cluster)
    - Same action type and direction (or direction + product_area when themes are available)

Dependencies:
    - #103: Run scoping (pipeline_run_id)
    - #105: Data model (conversation_embeddings, conversation_facet tables)
    - #106: Embedding generation
    - #107: Facet extraction
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from src.db.embedding_storage import get_embeddings_for_run
from src.db.facet_storage import get_facets_for_run

logger = logging.getLogger(__name__)


# Default clustering parameters (validated in prototype on 127 conversations)
DEFAULT_DISTANCE_THRESHOLD = 0.55
DEFAULT_LINKAGE = "complete"


@dataclass
class HybridCluster:
    """A hybrid sub-cluster: embedding cluster + facet sub-group."""

    cluster_id: str  # Format: "emb_{embedding_cluster}_facet_{direction}_pa_{product_area}" or legacy format
    embedding_cluster: int
    action_type: str
    direction: str
    conversation_ids: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.conversation_ids)


@dataclass
class ClusteringResult:
    """Result of hybrid clustering for a pipeline run."""

    pipeline_run_id: int
    total_conversations: int
    embedding_clusters_count: int
    hybrid_clusters_count: int
    clusters: List[HybridCluster] = field(default_factory=list)
    fallback_conversations: List[str] = field(default_factory=list)  # Missing embeddings/facets
    errors: List[str] = field(default_factory=list)

    # Distribution stats for logging/monitoring
    cluster_size_distribution: Dict[int, int] = field(default_factory=dict)  # size -> count

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.total_conversations > 0


class HybridClusteringService:
    """
    Service for hybrid clustering of conversations using embeddings and facets.

    Two-stage algorithm:
    1. Embedding clustering: Agglomerative clustering with cosine distance
    2. Facet sub-grouping: Split by action_type + direction (or direction + product_area when themes provided)
    """

    def __init__(
        self,
        distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
        linkage: str = DEFAULT_LINKAGE,
    ):
        """
        Initialize the hybrid clustering service.

        Args:
            distance_threshold: Distance threshold for agglomerative clustering.
                               Lower = more clusters, higher = fewer clusters.
                               Default 0.5 was validated on 127 conversations.
            linkage: Linkage method for clustering ("average", "complete", "single").
        """
        self.distance_threshold = distance_threshold
        self.linkage = linkage

    def cluster_for_run(
        self,
        pipeline_run_id: int,
    ) -> ClusteringResult:
        """
        Run hybrid clustering for a pipeline run.

        Loads embeddings and facets from DB, runs two-stage clustering,
        and returns clustered conversation groups.

        Args:
            pipeline_run_id: Pipeline run ID to cluster

        Returns:
            ClusteringResult with hybrid clusters and stats
        """
        result = ClusteringResult(
            pipeline_run_id=pipeline_run_id,
            total_conversations=0,
            embedding_clusters_count=0,
            hybrid_clusters_count=0,
        )

        # Load embeddings and facets from DB
        try:
            embeddings_data = get_embeddings_for_run(pipeline_run_id)
            facets_data = get_facets_for_run(pipeline_run_id)
        except Exception as e:
            result.errors.append(f"Database error: {e}")
            logger.error(f"Database error loading data for run {pipeline_run_id}: {e}", exc_info=True)
            return result

        if not embeddings_data:
            result.errors.append(f"No embeddings found for pipeline run {pipeline_run_id}")
            logger.warning(f"No embeddings found for pipeline run {pipeline_run_id}")
            return result

        # Build lookup maps
        embeddings_by_conv = {e["conversation_id"]: e["embedding"] for e in embeddings_data}
        facets_by_conv = {f["conversation_id"]: f for f in facets_data}

        # Find conversations with both embeddings and facets
        conv_ids_with_embeddings = set(embeddings_by_conv.keys())
        conv_ids_with_facets = set(facets_by_conv.keys())
        complete_conv_ids = list(conv_ids_with_embeddings & conv_ids_with_facets)

        # Track fallback conversations (missing data)
        missing_facets = conv_ids_with_embeddings - conv_ids_with_facets
        if missing_facets:
            result.fallback_conversations.extend(missing_facets)
            logger.warning(
                f"Pipeline run {pipeline_run_id}: {len(missing_facets)} conversations "
                "have embeddings but no facets - using fallback"
            )

        if not complete_conv_ids:
            result.errors.append("No conversations have both embeddings and facets")
            logger.error(f"Pipeline run {pipeline_run_id}: No complete data for clustering")
            return result

        result.total_conversations = len(complete_conv_ids)

        # Sort for deterministic ordering
        complete_conv_ids.sort()

        # Prepare embedding matrix (ordered by complete_conv_ids)
        embedding_matrix = np.array([
            embeddings_by_conv[cid] for cid in complete_conv_ids
        ])

        # Stage 1: Embedding clustering
        try:
            cluster_labels = self._cluster_embeddings(embedding_matrix)
        except Exception as e:
            result.errors.append(f"Embedding clustering failed: {e}")
            logger.error(f"Embedding clustering failed: {e}", exc_info=True)
            return result

        result.embedding_clusters_count = len(set(cluster_labels))

        # Stage 2: Facet sub-grouping
        hybrid_clusters = self._create_hybrid_subclusters(
            complete_conv_ids,
            cluster_labels,
            facets_by_conv,
        )

        result.hybrid_clusters_count = len(hybrid_clusters)
        result.clusters = hybrid_clusters

        # Calculate size distribution
        for cluster in hybrid_clusters:
            size = cluster.size
            result.cluster_size_distribution[size] = (
                result.cluster_size_distribution.get(size, 0) + 1
            )

        # Log results
        self._log_clustering_results(result)

        return result

    def _cluster_embeddings(
        self,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """
        Stage 1: Cluster embeddings using agglomerative clustering.

        Uses cosine distance which works well for text embeddings.

        Args:
            embeddings: Numpy array of shape (n_conversations, embedding_dim)

        Returns:
            Array of cluster labels (one per conversation)

        Performance Notes:
            - Memory: O(n²) due to precomputed distance matrix
            - 10k conversations: ~800 MB peak memory
            - 100k+ conversations: Consider batching or alternative algorithms
            - Validated on 127 conversations (prototype dataset)
        """
        if len(embeddings) < 2:
            # Single conversation gets its own cluster
            return np.array([0] * len(embeddings))

        # Compute cosine distance matrix (1 - similarity)
        similarity_matrix = cosine_similarity(embeddings)
        distance_matrix = 1 - similarity_matrix

        # Agglomerative clustering with precomputed distances
        clustering = AgglomerativeClustering(
            n_clusters=None,  # Let distance_threshold determine cluster count
            metric="precomputed",
            linkage=self.linkage,
            distance_threshold=self.distance_threshold,
        )

        labels = clustering.fit_predict(distance_matrix)

        logger.debug(
            f"Embedding clustering: {len(embeddings)} conversations -> "
            f"{len(set(labels))} clusters (threshold={self.distance_threshold})"
        )

        return labels

    def _create_hybrid_subclusters(
        self,
        conversation_ids: List[str],
        cluster_labels: np.ndarray,
        facets_by_conv: Dict[str, dict],
        themes_by_conv: Optional[Dict[str, dict]] = None,
    ) -> List[HybridCluster]:
        """
        Stage 2: Create sub-clusters within each embedding cluster based on facets.

        Groups conversations by embedding cluster, then splits each by
        action_type + direction, or direction + product_area when themes are provided.

        Args:
            conversation_ids: List of conversation IDs (ordered same as cluster_labels)
            cluster_labels: Embedding cluster assignment for each conversation
            facets_by_conv: Dict mapping conversation_id -> facet data
            themes_by_conv: Optional dict mapping conversation_id -> theme data

        Returns:
            List of HybridCluster objects
        """
        # Group conversations by embedding cluster
        cluster_groups: Dict[int, List[str]] = defaultdict(list)
        for conv_id, label in zip(conversation_ids, cluster_labels):
            cluster_groups[int(label)].append(conv_id)

        # Sub-cluster by action_type + direction, or direction + product_area when themes provided
        hybrid_clusters: List[HybridCluster] = []
        use_product_area = themes_by_conv is not None and len(themes_by_conv) > 0

        for embedding_cluster, conv_ids in cluster_groups.items():
            # Group by facet key within this embedding cluster
            subclusters: Dict[Tuple[str, str], List[str]] = defaultdict(list)

            for conv_id in conv_ids:
                facet = facets_by_conv.get(conv_id, {})
                direction = facet.get("direction", "neutral")
                if use_product_area:
                    theme = themes_by_conv.get(conv_id, {})
                    product_area = theme.get("product_area", "unknown")
                    subclusters[(direction, product_area)].append(conv_id)
                else:
                    action_type = facet.get("action_type", "unknown")
                    subclusters[(action_type, direction)].append(conv_id)

            # Create HybridCluster for each sub-cluster
            for key, subcluster_conv_ids in subclusters.items():
                if use_product_area:
                    direction, product_area = key
                    cluster_id = f"emb_{embedding_cluster}_facet_{direction}_pa_{product_area}"
                    action_counts: Dict[str, int] = defaultdict(int)
                    for cid in subcluster_conv_ids:
                        facet = facets_by_conv.get(cid, {})
                        action_counts[facet.get("action_type", "unknown")] += 1
                    action_type = max(action_counts.items(), key=lambda x: x[1])[0]
                else:
                    action_type, direction = key
                    cluster_id = f"emb_{embedding_cluster}_facet_{action_type}_{direction}"
                hybrid_clusters.append(
                    HybridCluster(
                        cluster_id=cluster_id,
                        embedding_cluster=embedding_cluster,
                        action_type=action_type,
                        direction=direction,
                        conversation_ids=subcluster_conv_ids,
                    )
                )

        # Sort by size descending for consistent ordering
        hybrid_clusters.sort(key=lambda c: (-c.size, c.cluster_id))

        return hybrid_clusters

    def _log_clustering_results(self, result: ClusteringResult) -> None:
        """Log clustering results for monitoring."""
        # Build size distribution summary
        size_dist = sorted(result.cluster_size_distribution.items())
        dist_summary = ", ".join(f"size {s}: {c}" for s, c in size_dist[:5])
        if len(size_dist) > 5:
            dist_summary += f", ... (+{len(size_dist) - 5} more sizes)"

        logger.info(
            f"Hybrid clustering for run {result.pipeline_run_id}: "
            f"{result.total_conversations} conversations -> "
            f"{result.embedding_clusters_count} embedding clusters -> "
            f"{result.hybrid_clusters_count} hybrid clusters"
        )
        logger.info(f"Cluster size distribution: {dist_summary}")

        if result.fallback_conversations:
            logger.warning(
                f"{len(result.fallback_conversations)} conversations missing facets, "
                "will fall back to signature-based grouping"
            )

    def cluster_with_data(
        self,
        embeddings: List[Dict[str, Any]],
        facets: List[Dict[str, Any]],
        themes: Optional[List[Dict[str, Any]]] = None,
    ) -> ClusteringResult:
        """
        Run hybrid clustering with provided data (for testing or batch processing).

        Args:
            embeddings: List of dicts with conversation_id and embedding
            facets: List of dicts with conversation_id, action_type, direction, etc.
            themes: Optional list of dicts with conversation_id, product_area, etc.

        Returns:
            ClusteringResult with hybrid clusters
        """
        result = ClusteringResult(
            pipeline_run_id=0,  # Not applicable for in-memory clustering
            total_conversations=0,
            embedding_clusters_count=0,
            hybrid_clusters_count=0,
        )

        if not embeddings:
            result.errors.append("No embeddings provided")
            return result

        # Build lookup maps
        embeddings_by_conv = {e["conversation_id"]: e["embedding"] for e in embeddings}
        facets_by_conv = {f["conversation_id"]: f for f in facets}

        # Find conversations with both embeddings and facets
        conv_ids_with_embeddings = set(embeddings_by_conv.keys())
        conv_ids_with_facets = set(facets_by_conv.keys())
        complete_conv_ids = list(conv_ids_with_embeddings & conv_ids_with_facets)

        # Track fallback conversations
        missing_facets = conv_ids_with_embeddings - conv_ids_with_facets
        if missing_facets:
            result.fallback_conversations.extend(missing_facets)

        if not complete_conv_ids:
            result.errors.append("No conversations have both embeddings and facets")
            return result

        result.total_conversations = len(complete_conv_ids)
        complete_conv_ids.sort()

        # Prepare embedding matrix
        embedding_matrix = np.array([
            embeddings_by_conv[cid] for cid in complete_conv_ids
        ])

        # Stage 1: Embedding clustering
        try:
            cluster_labels = self._cluster_embeddings(embedding_matrix)
        except Exception as e:
            result.errors.append(f"Embedding clustering failed: {e}")
            return result

        result.embedding_clusters_count = len(set(cluster_labels))

        # Stage 2: Facet sub-grouping (optionally with product_area)
        themes_by_conv: Optional[Dict[str, dict]] = None
        if themes:
            themes_by_conv = {str(t["conversation_id"]): t for t in themes}
        hybrid_clusters = self._create_hybrid_subclusters(
            complete_conv_ids,
            cluster_labels,
            facets_by_conv,
            themes_by_conv=themes_by_conv,
        )

        result.hybrid_clusters_count = len(hybrid_clusters)
        result.clusters = hybrid_clusters

        # Calculate size distribution
        for cluster in hybrid_clusters:
            size = cluster.size
            result.cluster_size_distribution[size] = (
                result.cluster_size_distribution.get(size, 0) + 1
            )

        return result
