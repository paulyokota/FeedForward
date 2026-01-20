#!/usr/bin/env python3
"""
Setup and validation script for GitHub Issue #51.

Verifies pgvector setup and runs initial embedding pipeline.
Includes performance benchmarking for search queries.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def verify_pgvector() -> bool:
    """Check pgvector extension is installed."""
    from src.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
                if not cur.fetchone():
                    print("❌ pgvector extension not installed")
                    print("   Run: CREATE EXTENSION vector;")
                    return False
        print("✓ pgvector extension verified")
        return True
    except Exception as e:
        print(f"❌ Failed to verify pgvector: {e}")
        return False


def check_migration_applied() -> bool:
    """Check if research_embeddings table exists."""
    from src.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'research_embeddings'
                    )
                """)
                exists = cur.fetchone()[0]
                if not exists:
                    print("❌ research_embeddings table not found")
                    print("   Apply migration: src/db/migrations/001_add_research_embeddings.sql")
                    return False
        print("✓ research_embeddings table exists")
        return True
    except Exception as e:
        print(f"❌ Failed to check migration: {e}")
        return False


def run_embeddings(limit=None) -> bool:
    """Run embedding pipeline with progress."""
    from src.research.embedding_pipeline import run_embedding_pipeline

    try:
        print(f"\nRunning embedding pipeline{' (limit=' + str(limit) + ')' if limit else ''}...")
        result = run_embedding_pipeline(limit=limit)

        print(f"  Status: {result.status}")
        print(f"  Sources: {', '.join(result.source_types)}")
        print(f"  Processed: {result.items_processed}")
        print(f"  Updated: {result.items_updated}")
        print(f"  Failed: {result.items_failed}")
        if result.duration_seconds:
            print(f"  Duration: {result.duration_seconds:.2f}s")
        if result.error:
            print(f"  Error: {result.error}")
            return False

        if result.status == "completed":
            print("✓ Embedding pipeline completed")
            return True
        else:
            print(f"❌ Embedding pipeline failed: {result.status}")
            return False
    except Exception as e:
        print(f"❌ Failed to run embeddings: {e}")
        logging.exception("Embedding pipeline error")
        return False


def count_embeddings() -> int:
    """Count embeddings by source type."""
    from src.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT source_type, COUNT(*)
                    FROM research_embeddings
                    GROUP BY source_type
                    ORDER BY source_type
                """)
                rows = cur.fetchall()

        print("\nEmbedding Counts:")
        total = 0
        if rows:
            for source_type, count in rows:
                print(f"  {source_type}: {count}")
                total += count
            print(f"  Total: {total}")
        else:
            print("  No embeddings found")

        return total
    except Exception as e:
        print(f"❌ Failed to count embeddings: {e}")
        return 0


def measure_performance() -> bool:
    """Run 10 search queries and report P95 latency."""
    from src.research.unified_search import UnifiedSearchService

    test_queries = [
        "pin not posting",
        "scheduling issues",
        "account migration",
        "payment failed",
        "media upload error",
        "timezone problems",
        "hashtag suggestions",
        "analytics dashboard",
        "profile visibility",
        "content moderation",
    ]

    try:
        service = UnifiedSearchService()
        latencies = []

        print("\nRunning 10 search queries...")
        for query in test_queries:
            start = time.time()
            try:
                results = service.search(query=query, limit=5)
                latency = (time.time() - start) * 1000  # ms
                latencies.append(latency)
                print(f"  '{query[:30]:<30}' - {latency:>6.0f}ms ({len(results)} results)")
            except Exception as e:
                print(f"  '{query[:30]:<30}' - FAILED: {e}")

        if latencies:
            latencies.sort()
            p95_index = int(len(latencies) * 0.95)
            p95 = latencies[min(p95_index, len(latencies) - 1)]
            avg = sum(latencies) / len(latencies)
            median = latencies[len(latencies) // 2]

            print(f"\nPerformance Results:")
            print(f"  Queries: {len(latencies)}/10 successful")
            print(f"  Average: {avg:.0f}ms")
            print(f"  Median:  {median:.0f}ms")
            print(f"  P95:     {p95:.0f}ms")

            if p95 > 500:
                print(f"  ⚠️  P95 exceeds 500ms target (actual: {p95:.0f}ms)")
                return False
            else:
                print(f"  ✓ P95 within 500ms target")
                return True
        else:
            print("❌ No successful queries")
            return False
    except Exception as e:
        print(f"❌ Failed to measure performance: {e}")
        logging.exception("Performance measurement error")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify pgvector setup and run initial embedding pipeline"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit items per source (for testing)",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip running embeddings (just verify setup)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    print("=" * 60)
    print("pgvector Setup Validation & Initial Embedding Pipeline")
    print("=" * 60)

    # Step 1: Verify pgvector
    print("\n[1/5] Verifying pgvector extension...")
    if not verify_pgvector():
        sys.exit(1)

    # Step 2: Check migration
    print("\n[2/5] Checking research_embeddings migration...")
    if not check_migration_applied():
        sys.exit(1)

    # Step 3: Run embeddings (unless skipped)
    if args.skip_embeddings:
        print("\n[3/5] Skipping embedding pipeline (--skip-embeddings)")
    else:
        print("\n[3/5] Running embedding pipeline...")
        if not run_embeddings(limit=args.limit):
            sys.exit(1)

    # Step 4: Count embeddings
    print("\n[4/5] Counting embeddings...")
    total = count_embeddings()
    if total == 0:
        print("⚠️  No embeddings found - did the pipeline run?")
        if not args.skip_embeddings:
            sys.exit(1)

    # Step 5: Performance test
    if total > 0:
        print("\n[5/5] Measuring search performance...")
        if not measure_performance():
            print("⚠️  Performance test had issues, but setup is complete")
    else:
        print("\n[5/5] Skipping performance test (no embeddings)")

    print("\n" + "=" * 60)
    print("✓ Setup validation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
