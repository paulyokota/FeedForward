#!/usr/bin/env python3
"""
Hybrid Clustering Pipeline Integration Test Script

Manual test script for validating the hybrid clustering pipeline with live APIs.
Use this for functional testing before production rollout.

Usage:
    # Test with a recent pipeline run
    python scripts/test_hybrid_pipeline.py --run-id 42

    # Test with specific conversation IDs
    python scripts/test_hybrid_pipeline.py --conv-ids conv1,conv2,conv3

    # Dry run (no DB writes)
    python scripts/test_hybrid_pipeline.py --run-id 42 --dry-run

    # Verbose output with timing
    python scripts/test_hybrid_pipeline.py --run-id 42 --verbose

Requirements:
    - OPENAI_API_KEY environment variable set
    - PostgreSQL database accessible (for DB modes)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from services.embedding_service import EmbeddingService
from services.facet_service import FacetExtractionService
from services.hybrid_clustering_service import HybridClusteringService


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hybrid_pipeline_test")


@dataclass
class TestMetrics:
    """Metrics from a test run."""
    total_conversations: int = 0
    embeddings_generated: int = 0
    embeddings_failed: int = 0
    facets_extracted: int = 0
    facets_failed: int = 0
    embedding_clusters: int = 0
    hybrid_clusters: int = 0
    stories_created: int = 0
    orphans_created: int = 0

    # Timing (milliseconds)
    embedding_time_ms: float = 0.0
    facet_time_ms: float = 0.0
    clustering_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Per-conversation latency
    avg_embedding_latency_ms: float = 0.0
    avg_facet_latency_ms: float = 0.0

    # Cost estimates (approximate)
    embedding_cost_usd: float = 0.0
    facet_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # Quality
    direction_separation_validated: bool = False
    cluster_coherence_score: float = 0.0

    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_conversations": self.total_conversations,
            "embeddings": {
                "generated": self.embeddings_generated,
                "failed": self.embeddings_failed,
                "time_ms": self.embedding_time_ms,
                "avg_latency_ms": self.avg_embedding_latency_ms,
                "cost_usd": self.embedding_cost_usd,
            },
            "facets": {
                "extracted": self.facets_extracted,
                "failed": self.facets_failed,
                "time_ms": self.facet_time_ms,
                "avg_latency_ms": self.avg_facet_latency_ms,
                "cost_usd": self.facet_cost_usd,
            },
            "clustering": {
                "embedding_clusters": self.embedding_clusters,
                "hybrid_clusters": self.hybrid_clusters,
                "time_ms": self.clustering_time_ms,
            },
            "stories": {
                "created": self.stories_created,
                "orphans": self.orphans_created,
            },
            "total_time_ms": self.total_time_ms,
            "total_cost_usd": self.total_cost_usd,
            "quality": {
                "direction_separation_validated": self.direction_separation_validated,
                "cluster_coherence_score": self.cluster_coherence_score,
            },
            "errors": self.errors,
        }

    def print_summary(self):
        """Print a formatted summary of the metrics."""
        print("\n" + "=" * 60)
        print("HYBRID CLUSTERING PIPELINE TEST RESULTS")
        print("=" * 60)

        print(f"\n📊 CONVERSATIONS: {self.total_conversations}")

        print(f"\n🔢 EMBEDDINGS:")
        print(f"   Generated: {self.embeddings_generated}")
        print(f"   Failed: {self.embeddings_failed}")
        print(f"   Time: {self.embedding_time_ms:.1f}ms")
        print(f"   Avg latency: {self.avg_embedding_latency_ms:.1f}ms/conv")
        print(f"   Cost: ${self.embedding_cost_usd:.4f}")

        print(f"\n🏷️  FACETS:")
        print(f"   Extracted: {self.facets_extracted}")
        print(f"   Failed: {self.facets_failed}")
        print(f"   Time: {self.facet_time_ms:.1f}ms")
        print(f"   Avg latency: {self.avg_facet_latency_ms:.1f}ms/conv")
        print(f"   Cost: ${self.facet_cost_usd:.4f}")

        print(f"\n📦 CLUSTERING:")
        print(f"   Embedding clusters: {self.embedding_clusters}")
        print(f"   Hybrid clusters: {self.hybrid_clusters}")
        print(f"   Time: {self.clustering_time_ms:.1f}ms")

        print(f"\n📚 STORIES:")
        print(f"   Created: {self.stories_created}")
        print(f"   Orphans: {self.orphans_created}")

        print(f"\n⏱️  TOTAL TIME: {self.total_time_ms:.1f}ms")
        print(f"💰 TOTAL COST: ${self.total_cost_usd:.4f}")

        print(f"\n✅ QUALITY:")
        print(f"   Direction separation: {'PASS' if self.direction_separation_validated else 'NOT VALIDATED'}")
        print(f"   Cluster coherence: {self.cluster_coherence_score:.2f}")

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"   - {error}")

        print("\n" + "=" * 60)


class Timer:
    """Context manager for timing."""
    def __init__(self):
        self.start = 0.0
        self.end = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (self.end - self.start) * 1000


async def run_pipeline_test(
    conversations: List[Dict[str, Any]],
    dry_run: bool = False,
    verbose: bool = False,
) -> TestMetrics:
    """
    Run the hybrid clustering pipeline on conversations.

    Args:
        conversations: List of conversation dicts with id, source_body fields
        dry_run: If True, skip DB writes
        verbose: If True, print detailed progress

    Returns:
        TestMetrics with all results
    """
    metrics = TestMetrics(total_conversations=len(conversations))

    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f"Starting hybrid pipeline test with {len(conversations)} conversations")

    # --- Stage 1: Embedding Generation ---
    logger.info("Stage 1: Generating embeddings...")

    embedding_service = EmbeddingService(batch_size=50)

    with Timer() as emb_timer:
        emb_result = await embedding_service.generate_conversation_embeddings_async(
            conversations
        )

    metrics.embedding_time_ms = emb_timer.elapsed_ms
    metrics.embeddings_generated = emb_result.total_success
    metrics.embeddings_failed = emb_result.total_failed

    if emb_result.total_success > 0:
        metrics.avg_embedding_latency_ms = metrics.embedding_time_ms / emb_result.total_success

    # Estimate cost: $0.00002 per 1K tokens, avg ~500 tokens per conversation
    metrics.embedding_cost_usd = emb_result.total_success * 500 * 0.00002 / 1000

    logger.info(
        f"Embeddings: {emb_result.total_success} success, "
        f"{emb_result.total_failed} failed, "
        f"{metrics.embedding_time_ms:.1f}ms"
    )

    if emb_result.total_failed > 0:
        for failed in emb_result.failed[:3]:  # Log first 3 failures
            metrics.errors.append(f"Embedding failed for {failed.conversation_id}: {failed.error}")

    if emb_result.total_success == 0:
        metrics.errors.append("All embeddings failed - cannot continue")
        return metrics

    # Build embeddings data for clustering
    embeddings_data = [
        {"conversation_id": r.conversation_id, "embedding": r.embedding}
        for r in emb_result.successful
    ]

    # --- Stage 2: Facet Extraction ---
    logger.info("Stage 2: Extracting facets...")

    facet_service = FacetExtractionService()

    # Only process conversations that got embeddings
    successful_ids = {r.conversation_id for r in emb_result.successful}
    conversations_for_facets = [
        c for c in conversations if c["id"] in successful_ids
    ]

    with Timer() as facet_timer:
        facet_result = await facet_service.extract_facets_batch_async(
            conversations_for_facets
        )

    metrics.facet_time_ms = facet_timer.elapsed_ms
    metrics.facets_extracted = facet_result.total_success
    metrics.facets_failed = facet_result.total_failed

    if facet_result.total_success > 0:
        metrics.avg_facet_latency_ms = metrics.facet_time_ms / facet_result.total_success

    # Estimate cost: gpt-4o-mini ~$0.00015 per 1K input tokens, ~500 tokens per call
    metrics.facet_cost_usd = facet_result.total_success * 500 * 0.00015 / 1000

    logger.info(
        f"Facets: {facet_result.total_success} success, "
        f"{facet_result.total_failed} failed, "
        f"{metrics.facet_time_ms:.1f}ms"
    )

    if facet_result.total_failed > 0:
        for failed in facet_result.failed[:3]:
            metrics.errors.append(f"Facet failed for {failed.conversation_id}: {failed.error}")

    if facet_result.total_success == 0:
        metrics.errors.append("All facet extractions failed - cannot continue")
        return metrics

    # Build facets data for clustering
    facets_data = [
        {
            "conversation_id": r.conversation_id,
            "action_type": r.action_type,
            "direction": r.direction,
            "symptom": r.symptom,
            "user_goal": r.user_goal,
        }
        for r in facet_result.successful
    ]

    # --- Stage 3: Hybrid Clustering ---
    logger.info("Stage 3: Running hybrid clustering...")

    clustering_service = HybridClusteringService(distance_threshold=0.5)

    with Timer() as cluster_timer:
        cluster_result = clustering_service.cluster_with_data(embeddings_data, facets_data)

    metrics.clustering_time_ms = cluster_timer.elapsed_ms
    metrics.embedding_clusters = cluster_result.embedding_clusters_count
    metrics.hybrid_clusters = cluster_result.hybrid_clusters_count

    logger.info(
        f"Clustering: {metrics.embedding_clusters} embedding clusters -> "
        f"{metrics.hybrid_clusters} hybrid clusters, "
        f"{metrics.clustering_time_ms:.1f}ms"
    )

    if cluster_result.errors:
        for error in cluster_result.errors:
            metrics.errors.append(f"Clustering: {error}")

    # --- Quality Validation ---
    logger.info("Validating cluster quality...")

    # Check direction separation (T-006 critical)
    direction_counts: Dict[str, int] = {}
    for cluster in cluster_result.clusters:
        key = f"{cluster.action_type}_{cluster.direction}"
        direction_counts[key] = direction_counts.get(key, 0) + 1

    # If we have both excess and deficit for the same action_type, T-006 passes
    action_types_seen = set()
    for cluster in cluster_result.clusters:
        action_types_seen.add(cluster.action_type)

    for action_type in action_types_seen:
        has_excess = any(
            c.action_type == action_type and c.direction == "excess"
            for c in cluster_result.clusters
        )
        has_deficit = any(
            c.action_type == action_type and c.direction == "deficit"
            for c in cluster_result.clusters
        )
        if has_excess and has_deficit:
            metrics.direction_separation_validated = True
            logger.info(f"T-006 PASS: Direction separation validated for {action_type}")
            break

    # Cluster coherence score: ratio of clusters with >= MIN_GROUP_SIZE
    from story_tracking.models import MIN_GROUP_SIZE
    large_clusters = sum(1 for c in cluster_result.clusters if c.size >= MIN_GROUP_SIZE)
    if cluster_result.hybrid_clusters_count > 0:
        metrics.cluster_coherence_score = large_clusters / cluster_result.hybrid_clusters_count

    # --- Log Cluster Details ---
    if verbose:
        print("\n📊 CLUSTER DETAILS:")
        for cluster in cluster_result.clusters:
            print(f"  {cluster.cluster_id}: {cluster.size} conversations")
            print(f"    action_type: {cluster.action_type}, direction: {cluster.direction}")

    # --- Calculate totals ---
    metrics.total_time_ms = (
        metrics.embedding_time_ms +
        metrics.facet_time_ms +
        metrics.clustering_time_ms
    )
    metrics.total_cost_usd = metrics.embedding_cost_usd + metrics.facet_cost_usd

    return metrics


def get_conversations_from_db(run_id: int) -> List[Dict[str, Any]]:
    """Load conversations from a pipeline run."""
    from src.db.connection import get_connection
    from psycopg2.extras import RealDictCursor

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT c.id, c.source_body, c.source_subject
                FROM conversations c
                WHERE c.pipeline_run_id = %s
                AND c.actionable = true
            """, (run_id,))

            rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_sample_conversations() -> List[Dict[str, Any]]:
    """Return sample test conversations."""
    return [
        {
            "id": "test_1",
            "source_body": "I'm seeing duplicate pins on my board. Every time I save a pin, it appears twice.",
        },
        {
            "id": "test_2",
            "source_body": "My pins are not showing up on my board. I saved several pins but the board is empty.",
        },
        {
            "id": "test_3",
            "source_body": "How do I create a new board? I want to organize my pins better.",
        },
        {
            "id": "test_4",
            "source_body": "The app is very slow when loading my home feed. It takes 10 seconds to load.",
        },
        {
            "id": "test_5",
            "source_body": "I want to delete my account. Can you help me with that?",
        },
    ]


async def main():
    parser = argparse.ArgumentParser(
        description="Test the hybrid clustering pipeline"
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="Pipeline run ID to test with (loads conversations from DB)"
    )
    parser.add_argument(
        "--conv-ids",
        type=str,
        help="Comma-separated conversation IDs to test"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use built-in sample conversations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip DB writes"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        help="Output metrics to JSON file"
    )

    args = parser.parse_args()

    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    # Load conversations
    if args.run_id:
        logger.info(f"Loading conversations from pipeline run {args.run_id}")
        conversations = get_conversations_from_db(args.run_id)
    elif args.conv_ids:
        # Would need DB lookup by ID - simplified for now
        print("ERROR: --conv-ids not implemented yet, use --run-id or --sample")
        sys.exit(1)
    elif args.sample:
        logger.info("Using sample conversations")
        conversations = get_sample_conversations()
    else:
        print("ERROR: Must specify --run-id, --conv-ids, or --sample")
        sys.exit(1)

    if not conversations:
        print("ERROR: No conversations to process")
        sys.exit(1)

    # Run the pipeline
    metrics = await run_pipeline_test(
        conversations=conversations,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    # Print summary
    metrics.print_summary()

    # Output JSON if requested
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.write_text(json.dumps(metrics.to_dict(), indent=2))
        print(f"\nMetrics written to {output_path}")

    # Return exit code based on errors
    if metrics.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
