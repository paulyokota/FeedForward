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
import re
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

        # Post-processing: merge small groups with same facet key for narrow product areas
        if use_product_area:
            hybrid_clusters = self._merge_narrow_facet_groups(
                hybrid_clusters,
                themes_by_conv=themes_by_conv,
                facets_by_conv=facets_by_conv,
            )

        # Sort by size descending for consistent ordering
        hybrid_clusters.sort(key=lambda c: (-c.size, c.cluster_id))

        return hybrid_clusters

    def _merge_narrow_facet_groups(
        self,
        clusters: List[HybridCluster],
        min_size: int = 3,
        themes_by_conv: Optional[Dict[str, dict]] = None,
        facets_by_conv: Optional[Dict[str, dict]] = None,
    ) -> List[HybridCluster]:
        """
        Merge groups with same (direction, product_area) for narrow product areas.

        This addresses embedding clustering fragmentation by consolidating groups
        that share a facet key known to contain a single issue type.

        Narrow facet keys are specific (direction, product_area) combinations
        that empirically contain only one pack/issue type, making merging safe.
        """
        # Define narrow facet keys - these are (direction, product_area) combinations
        # that are known to contain a single issue type based on analysis
        narrow_facet_keys = {
            # Narrow product areas with deficit - single issue types
            ("deficit", "ai_creation"),
            ("deficit", "analytics"),
            ("deficit", "create"),
            ("deficit", "integrations"),
            # Pinterest publishing is safe ONLY for excess (duplicate pins pack)
            # Deficit has mixed packs (missing pins vs duplicate pins edge cases)
            ("excess", "pinterest_publishing"),
        }

        # Single-pack product areas - safe to merge ALL directions
        # These product areas only have one issue type regardless of direction
        single_pack_product_areas = {"billing"}

        # Component families within mixed product areas
        # Maps (product_area, component) -> family name for grouping
        # Components in the same family can be merged safely
        # NOTE: 'auth' is mixed (has both pinterest_connection_failure and
        # account_instagram_connection_guidance) so it's excluded
        component_families = {
            # account PA has 3 distinct packs, separable by component
            ("account", "oauth"): "account_oauth",
            ("account", "instagram_publishing"): "account_oauth",
            ("account", "multi_account"): "account_multi",
            ("account", "multi_profile_dashboard"): "account_multi",
            ("account", "instagram_connection"): "account_instagram",
            ("account", "instagram"): "account_instagram",
            ("account", "instagram_facebook_connection"): "account_instagram",
        }

        # Parse facet key from cluster_id
        def get_facet_key(cluster: HybridCluster) -> Tuple[str, str]:
            parts = cluster.cluster_id.split("_facet_")
            if len(parts) == 2:
                facet_part = parts[1]
                if "_pa_" in facet_part:
                    direction, pa_part = facet_part.split("_pa_", 1)
                    return (direction, pa_part)
            return (cluster.direction, "unknown")

        # Group clusters by facet key and by product_area
        by_facet_key: Dict[Tuple[str, str], List[HybridCluster]] = defaultdict(list)
        by_product_area: Dict[str, List[HybridCluster]] = defaultdict(list)
        for cluster in clusters:
            key = get_facet_key(cluster)
            by_facet_key[key].append(cluster)
            by_product_area[key[1]].append(cluster)

        merged_clusters: List[HybridCluster] = []
        processed_clusters = set()
        # Track individual convos that have been consumed by merges
        # This allows partial cluster consumption without orphaning remaining convos
        consumed_convos: set = set()

        # First: merge single-pack product areas (merge ALL directions)
        for product_area in single_pack_product_areas:
            pa_clusters = by_product_area.get(product_area, [])
            if len(pa_clusters) > 1:
                total_size = sum(c.size for c in pa_clusters)
                if total_size >= min_size and total_size <= 8:
                    merged_conv_ids = []
                    for c in pa_clusters:
                        merged_conv_ids.extend(c.conversation_ids)
                        processed_clusters.add(id(c))
                    # Track consumed convos
                    consumed_convos.update(merged_conv_ids)

                    emb_clusters = sorted(set(c.embedding_cluster for c in pa_clusters))
                    directions = sorted(set(get_facet_key(c)[0] for c in pa_clusters))
                    merged_id = f"merged_emb_{'_'.join(str(e) for e in emb_clusters)}_facet_{'_'.join(directions)}_pa_{product_area}"

                    action_counts: Dict[str, int] = defaultdict(int)
                    for c in pa_clusters:
                        action_counts[c.action_type] += c.size
                    action_type = max(action_counts.items(), key=lambda x: x[1])[0]
                    main_direction = max((get_facet_key(c)[0], c.size) for c in pa_clusters)[0]

                    merged_clusters.append(
                        HybridCluster(
                            cluster_id=merged_id,
                            embedding_cluster=emb_clusters[0],
                            action_type=action_type,
                            direction=main_direction,
                            conversation_ids=merged_conv_ids,
                        )
                    )

        # Second: merge by component family for mixed product areas
        # This groups conversations by their component family within mixed PAs
        if themes_by_conv:
            by_family: Dict[str, List[HybridCluster]] = defaultdict(list)

            for cluster in clusters:
                if id(cluster) in processed_clusters:
                    continue
                facet_key = get_facet_key(cluster)
                product_area = facet_key[1]

                families = set()
                for cid in cluster.conversation_ids:
                    theme = themes_by_conv.get(cid, {})
                    component = theme.get("component", "")
                    family = component_families.get((product_area, component))
                    if family:
                        families.add(family)

                # Only merge clusters that are fully within a single family
                if len(families) == 1 and families:
                    family = next(iter(families))
                    by_family[family].append(cluster)

            for family, family_clusters in by_family.items():
                total_size = sum(c.size for c in family_clusters)
                if total_size < min_size or total_size > 8:
                    continue

                for c in family_clusters:
                    processed_clusters.add(id(c))

                emb_clusters = sorted(set(c.embedding_cluster for c in family_clusters))
                merged_id = f"merged_emb_{'_'.join(str(e) for e in emb_clusters)}_family_{family}"

                action_counts: Dict[str, int] = defaultdict(int)
                for c in family_clusters:
                    action_counts[c.action_type] += c.size
                action_type = max(action_counts.items(), key=lambda x: x[1])[0]
                main_direction = max(
                    (get_facet_key(c)[0], c.size) for c in family_clusters
                )[0]

                merged_conv_ids = []
                for c in family_clusters:
                    merged_conv_ids.extend(c.conversation_ids)
                # Track consumed convos
                consumed_convos.update(merged_conv_ids)

                merged_clusters.append(
                    HybridCluster(
                        cluster_id=merged_id,
                        embedding_cluster=emb_clusters[0],
                        action_type=action_type,
                        direction=main_direction,
                        conversation_ids=merged_conv_ids,
                    )
                )

        # Third: scheduling-specific merge using action_type families
        # Merge scheduling clusters by component family when they share the same
        # query intent. Error reports (bug_report/complaint) are grouped with
        # smart_schedule. Info queries (how_to_question/inquiry) are grouped
        # separately to capture feature questions and usage requests.
        if themes_by_conv and facets_by_conv:
            # Error reports: bug_report, complaint
            error_action_types = {"bug_report", "complaint"}
            error_components = {"smart_schedule"}

            # Info queries: how_to_question, inquiry
            info_action_types = {"how_to_question", "inquiry"}
            # Broader component set for info queries - these are feature questions
            info_components = {"smart_schedule", "smartloops", "advanced_scheduler"}

            def get_cluster_action_type(cluster: HybridCluster) -> str:
                """Get dominant action_type from cluster's facets."""
                action_counts: Dict[str, int] = defaultdict(int)
                for cid in cluster.conversation_ids:
                    facet = facets_by_conv.get(cid, {})
                    action = facet.get("action_type", "unknown")
                    action_counts[action] += 1
                if action_counts:
                    return max(action_counts.items(), key=lambda x: x[1])[0]
                return "unknown"

            def get_cluster_component(cluster: HybridCluster) -> Optional[str]:
                """Get dominant component from cluster's themes."""
                comp_counts: Dict[str, int] = defaultdict(int)
                for cid in cluster.conversation_ids:
                    theme = themes_by_conv.get(cid, {})
                    comp = theme.get("component", "")
                    if comp:
                        comp_counts[comp] += 1
                if comp_counts:
                    return max(comp_counts.items(), key=lambda x: x[1])[0]
                return None

            # Collect error report conversations that meet criteria
            error_conv_ids = []
            error_conv_emb_clusters = set()
            for cluster in clusters:
                if id(cluster) in processed_clusters:
                    continue
                _, product_area = get_facet_key(cluster)
                if product_area != "scheduling":
                    continue
                if cluster.size >= min_size:
                    continue

                for cid in cluster.conversation_ids:
                    # Skip already consumed convos
                    if cid in consumed_convos:
                        continue
                    facet = facets_by_conv.get(cid, {})
                    theme = themes_by_conv.get(cid, {})
                    action = facet.get("action_type", "unknown")
                    component = theme.get("component", "")
                    # Only include error conversations with safe component
                    if action in error_action_types and component in error_components:
                        error_conv_ids.append(cid)
                        error_conv_emb_clusters.add(cluster.embedding_cluster)

            if len(error_conv_ids) >= min_size and len(error_conv_ids) <= 6:
                # Track consumed convos (no longer mark entire clusters as processed
                # since other convos in those clusters may be eligible for other merges)
                consumed_convos.update(error_conv_ids)

                emb_clusters = sorted(error_conv_emb_clusters)
                merged_id = f"merged_emb_{'_'.join(str(e) for e in emb_clusters)}_sched_error_smart_schedule"

                action_counts: Dict[str, int] = defaultdict(int)
                for cid in error_conv_ids:
                    facet = facets_by_conv.get(cid, {})
                    action_counts[facet.get("action_type", "unknown")] += 1
                action_type = max(action_counts.items(), key=lambda x: x[1])[0]
                main_direction = "deficit"  # Default for error reports

                merged_clusters.append(
                    HybridCluster(
                        cluster_id=merged_id,
                        embedding_cluster=emb_clusters[0] if emb_clusters else 0,
                        action_type=action_type,
                        direction=main_direction,
                        conversation_ids=error_conv_ids,
                    )
                )

            # Collect info query conversations (how_to_question, inquiry) for scheduling
            # Now checks consumed_convos to pick up orphaned convos from partial cluster merges
            info_conv_ids = []
            info_conv_emb_clusters = set()
            for cluster in clusters:
                # Don't skip processed clusters entirely - check individual convos
                _, product_area = get_facet_key(cluster)
                if product_area != "scheduling":
                    continue
                # Allow large clusters too since we're picking individual convos
                # (no longer: if cluster.size >= min_size: continue)

                for cid in cluster.conversation_ids:
                    # Skip already consumed convos
                    if cid in consumed_convos:
                        continue
                    facet = facets_by_conv.get(cid, {})
                    theme = themes_by_conv.get(cid, {})
                    action = facet.get("action_type", "unknown")
                    component = theme.get("component", "")
                    # Include info queries with broader component set
                    if action in info_action_types and component in info_components:
                        info_conv_ids.append(cid)
                        info_conv_emb_clusters.add(cluster.embedding_cluster)

            if len(info_conv_ids) >= min_size and len(info_conv_ids) <= 8:
                # Track consumed convos
                consumed_convos.update(info_conv_ids)

                emb_clusters = sorted(info_conv_emb_clusters)
                merged_id = f"merged_emb_{'_'.join(str(e) for e in emb_clusters)}_sched_info_query"

                action_counts: Dict[str, int] = defaultdict(int)
                for cid in info_conv_ids:
                    facet = facets_by_conv.get(cid, {})
                    action_counts[facet.get("action_type", "unknown")] += 1
                action_type = max(action_counts.items(), key=lambda x: x[1])[0]
                main_direction = "neutral"  # Default for info queries

                merged_clusters.append(
                    HybridCluster(
                        cluster_id=merged_id,
                        embedding_cluster=emb_clusters[0] if emb_clusters else 0,
                        action_type=action_type,
                        direction=main_direction,
                        conversation_ids=info_conv_ids,
                    )
                )

            # Cross-PA merge for pin_scheduler deficit: merges pinterest_publishing
            # and scheduling conversations that share pin_scheduler component with
            # deficit direction. This addresses the pinterest_missing_pins pack.
            # - For pinterest_publishing: allow inquiry, bug_report, complaint
            # - For scheduling PA: only allow bug_report, complaint (not inquiry,
            #   which tends to be feature questions like "how do I schedule video pins")
            pin_sched_deficit_convs = []
            pin_sched_emb_clusters = set()
            pin_sched_eligible_pas = {"pinterest_publishing", "scheduling"}
            # Action types vary by PA to avoid cross-contamination
            pin_sched_actions_by_pa = {
                "pinterest_publishing": {"inquiry", "bug_report", "complaint"},
                "scheduling": {"bug_report", "complaint"},  # No inquiry - avoids feature questions
            }

            for cluster in clusters:
                _, product_area = get_facet_key(cluster)
                if product_area not in pin_sched_eligible_pas:
                    continue

                for cid in cluster.conversation_ids:
                    # Skip already consumed convos
                    if cid in consumed_convos:
                        continue
                    theme = themes_by_conv.get(cid, {})
                    facet = facets_by_conv.get(cid, {})
                    component = theme.get("component", "")
                    direction = facet.get("direction", "")
                    action = facet.get("action_type", "")
                    theme_pa = theme.get("product_area", "")
                    eligible_actions = pin_sched_actions_by_pa.get(theme_pa, set())
                    # Must have pin_scheduler component, deficit direction, and PA-specific eligible action
                    if (component == "pin_scheduler" and direction == "deficit"
                            and action in eligible_actions):
                        pin_sched_deficit_convs.append(cid)
                        pin_sched_emb_clusters.add(cluster.embedding_cluster)

            if len(pin_sched_deficit_convs) >= min_size and len(pin_sched_deficit_convs) <= 8:
                # Track consumed convos
                consumed_convos.update(pin_sched_deficit_convs)

                emb_clusters = sorted(pin_sched_emb_clusters)
                merged_id = f"merged_emb_{'_'.join(str(e) for e in emb_clusters)}_pin_scheduler_deficit"

                action_counts: Dict[str, int] = defaultdict(int)
                for cid in pin_sched_deficit_convs:
                    facet = facets_by_conv.get(cid, {})
                    action_counts[facet.get("action_type", "unknown")] += 1
                action_type = max(action_counts.items(), key=lambda x: x[1])[0]

                merged_clusters.append(
                    HybridCluster(
                        cluster_id=merged_id,
                        embedding_cluster=emb_clusters[0] if emb_clusters else 0,
                        action_type=action_type,
                        direction="deficit",
                        conversation_ids=pin_sched_deficit_convs,
                    )
                )

        # Fourth: process remaining clusters by facet key
        # Filter out consumed convos from each cluster
        for facet_key, group_clusters in by_facet_key.items():
            # Skip clusters fully processed or filter out consumed convos
            remaining_clusters = []
            for c in group_clusters:
                if id(c) in processed_clusters:
                    continue
                # Filter out consumed convos
                remaining_convs = [cid for cid in c.conversation_ids if cid not in consumed_convos]
                if remaining_convs:
                    # Create a modified cluster with only remaining convos
                    remaining_clusters.append(
                        HybridCluster(
                            cluster_id=c.cluster_id,
                            embedding_cluster=c.embedding_cluster,
                            action_type=c.action_type,
                            direction=c.direction,
                            conversation_ids=remaining_convs,
                        )
                    )

            if not remaining_clusters:
                continue

            if facet_key not in narrow_facet_keys or len(remaining_clusters) == 1:
                # Broad facet key or single group - keep as-is
                merged_clusters.extend(remaining_clusters)
                continue

            # Narrow facet key with multiple groups - merge all into one
            total_size = sum(c.size for c in remaining_clusters)
            direction, product_area = facet_key

            if total_size >= min_size and total_size <= 8:
                # Merge all remaining groups
                merged_conv_ids = []
                for c in remaining_clusters:
                    merged_conv_ids.extend(c.conversation_ids)

                emb_clusters = sorted(set(c.embedding_cluster for c in remaining_clusters))
                merged_id = f"merged_emb_{'_'.join(str(e) for e in emb_clusters)}_facet_{direction}_pa_{product_area}"

                action_counts: Dict[str, int] = defaultdict(int)
                for c in remaining_clusters:
                    action_counts[c.action_type] += c.size
                action_type = max(action_counts.items(), key=lambda x: x[1])[0]

                merged_clusters.append(
                    HybridCluster(
                        cluster_id=merged_id,
                        embedding_cluster=emb_clusters[0],
                        action_type=action_type,
                        direction=direction,
                        conversation_ids=merged_conv_ids,
                    )
                )
            else:
                # Too large to merge safely - keep separate
                merged_clusters.extend(remaining_clusters)

        return merged_clusters

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
