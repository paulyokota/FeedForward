#!/usr/bin/env python3
"""
Diagnose why a pipeline run produced unexpected results.

This script investigates why hybrid clustering might have returned None
and fallen back to signature-based grouping.

Usage:
    python scripts/diagnose_run.py 84
"""

import sys
from src.db.connection import get_connection
from src.db.embedding_storage import get_embeddings_for_run, count_embeddings_for_run
from src.db.facet_storage import get_facets_for_run, count_facets_for_run


def diagnose_run(run_id: int) -> None:
    """Diagnose a pipeline run's hybrid clustering status."""

    print(f"\n{'='*60}")
    print(f"Diagnosing Run {run_id}")
    print(f"{'='*60}\n")

    # 1. Check basic counts
    print("1. DATA COUNTS")
    print("-" * 40)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Conversations linked to this run
            cur.execute("""
                SELECT COUNT(*) FROM conversations WHERE pipeline_run_id = %s
            """, (run_id,))
            conv_count = cur.fetchone()[0]
            print(f"   Conversations linked to run: {conv_count}")

            # Conversations with themes (proxy for actionable)
            cur.execute("""
                SELECT COUNT(DISTINCT conversation_id) FROM themes
                WHERE pipeline_run_id = %s
            """, (run_id,))
            actionable_count = cur.fetchone()[0]
            print(f"   Conversations with themes: {actionable_count}")

    embedding_count = count_embeddings_for_run(run_id)
    facet_count = count_facets_for_run(run_id)

    print(f"   Embeddings for run: {embedding_count}")
    print(f"   Facets for run: {facet_count}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Themes for this run
            cur.execute("""
                SELECT COUNT(*) FROM themes WHERE pipeline_run_id = %s
            """, (run_id,))
            theme_count = cur.fetchone()[0]
            print(f"   Themes for run: {theme_count}")

            # Stories
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE grouping_method = 'hybrid_cluster'),
                       COUNT(*) FILTER (WHERE grouping_method = 'signature')
                FROM stories WHERE pipeline_run_id = %s
            """, (run_id,))
            row = cur.fetchone()
            print(f"   Stories: {row[0]} (hybrid: {row[1]}, signature: {row[2]})")

            # Orphans
            cur.execute("""
                SELECT COUNT(*) FROM story_orphans
                WHERE graduated_at IS NULL
            """)
            orphan_count = cur.fetchone()[0]
            print(f"   Orphans (ungraduated): {orphan_count}")

    # 2. Check data overlap
    print("\n2. DATA OVERLAP (embeddings ∩ facets)")
    print("-" * 40)

    embeddings_data = get_embeddings_for_run(run_id)
    facets_data = get_facets_for_run(run_id)

    embedding_conv_ids = {e["conversation_id"] for e in embeddings_data}
    facet_conv_ids = {f["conversation_id"] for f in facets_data}

    complete_ids = embedding_conv_ids & facet_conv_ids
    only_embeddings = embedding_conv_ids - facet_conv_ids
    only_facets = facet_conv_ids - embedding_conv_ids

    print(f"   Conversations with both: {len(complete_ids)}")
    print(f"   Only embeddings (missing facets): {len(only_embeddings)}")
    print(f"   Only facets (missing embeddings): {len(only_facets)}")

    if len(complete_ids) == 0:
        print("\n   ⚠️  NO CONVERSATIONS HAVE BOTH EMBEDDINGS AND FACETS!")
        print("   This would cause hybrid clustering to fail.")
        return

    # 3. Try hybrid clustering
    print("\n3. HYBRID CLUSTERING TEST")
    print("-" * 40)

    try:
        from src.services.hybrid_clustering_service import HybridClusteringService

        service = HybridClusteringService()
        result = service.cluster_for_run(run_id)

        print(f"   Success: {result.success}")
        print(f"   Errors: {result.errors}")
        print(f"   Total conversations: {result.total_conversations}")
        print(f"   Embedding clusters: {result.embedding_clusters_count}")
        print(f"   Hybrid clusters: {result.hybrid_clusters_count}")
        print(f"   Fallback conversations: {len(result.fallback_conversations)}")

        if result.cluster_size_distribution:
            print(f"   Size distribution: {dict(sorted(result.cluster_size_distribution.items()))}")

        if result.clusters:
            print(f"\n   Top 5 clusters by size:")
            for i, cluster in enumerate(result.clusters[:5]):
                print(f"      {i+1}. {cluster.cluster_id}: {cluster.size} conversations")
        else:
            print("\n   ⚠️  NO CLUSTERS PRODUCED!")
            print("   This is why hybrid clustering returned None.")

    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    # 4. Check orphan signatures
    print("\n4. ORPHAN ANALYSIS")
    print("-" * 40)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get orphan signatures and sizes
            cur.execute("""
                SELECT signature, array_length(conversation_ids, 1) as conv_count
                FROM story_orphans
                WHERE graduated_at IS NULL
                ORDER BY conv_count DESC
                LIMIT 10
            """)
            rows = cur.fetchall()

            print(f"   Top 10 orphans by size:")
            for sig, count in rows:
                short_sig = sig[:50] + "..." if len(sig) > 50 else sig
                print(f"      {count} convos: {short_sig}")

    print(f"\n{'='*60}")
    print("Diagnosis complete")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_run.py <run_id>")
        sys.exit(1)

    run_id = int(sys.argv[1])
    diagnose_run(run_id)
