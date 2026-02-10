#!/usr/bin/env python3
"""Run the Discovery Engine against real data.

Standalone script for discovery runs. Uses InMemoryTransport
(no Agenterminal needed) and loads PostHog data from a
pre-fetched JSON snapshot.

Usage:
    # Run against a target product repo (recommended):
    python scripts/run_discovery.py --target-repo ../aero --scope-dirs packages/ --doc-paths tmp/

    # Run against FeedForward itself (default):
    python scripts/run_discovery.py --days 14

    # Other options:
    python scripts/run_discovery.py --days 7   # smaller window, faster/cheaper
    python scripts/run_discovery.py --dry-run   # validate config without running
    python scripts/run_discovery.py --target-repo ../aero --no-auto-pull  # skip git pull
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(Path(project_root) / ".env")

from src.discovery.models.run import RunConfig
from src.discovery.orchestrator import DiscoveryOrchestrator
from src.discovery.services.transport import InMemoryTransport


def get_db_connection():
    """Create a psycopg2 connection from DATABASE_URL."""
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    return conn


def load_posthog_data(path: str) -> dict:
    """Load PostHog snapshot from JSON file."""
    with open(path) as f:
        data = json.load(f)

    # Strip metadata key if present — PostHogReader doesn't expect it
    data.pop("metadata", None)

    print(f"PostHog snapshot loaded:")
    print(f"  Event definitions: {len(data.get('event_definitions', []))}")
    print(f"  Dashboards:        {len(data.get('dashboards', []))}")
    print(f"  Insights:          {len(data.get('insights', []))}")
    print(f"  Errors:            {len(data.get('errors', []))}")
    return data


def main():
    parser = argparse.ArgumentParser(description="Run Discovery Engine")
    parser.add_argument(
        "--days", type=int, default=14,
        help="Time window in days for conversation fetch (default: 14)",
    )
    parser.add_argument(
        "--posthog-data", type=str, default="data/posthog_snapshot.json",
        help="Path to PostHog JSON snapshot (default: data/posthog_snapshot.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate config and connections without running",
    )
    parser.add_argument(
        "--target-repo", type=str, default=None,
        help="Path to the product repo for codebase/research exploration. "
        "If not set, explorers scan the FeedForward repo itself.",
    )
    parser.add_argument(
        "--scope-dirs", type=str, nargs="+", default=None,
        help="Codebase explorer scope directories (relative to target repo). "
        "e.g. --scope-dirs packages/ src/",
    )
    parser.add_argument(
        "--doc-paths", type=str, nargs="+", default=None,
        help="Research explorer doc directories (relative to target repo). "
        "e.g. --doc-paths docs/ tmp/",
    )
    parser.add_argument(
        "--no-auto-pull", action="store_true",
        help="Skip auto-pull of target repo before exploration",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # Resolve target repo path
    target_repo = None
    if args.target_repo:
        target_repo = str(Path(args.target_repo).resolve())
        if not Path(target_repo).is_dir():
            print(f"ERROR: Target repo not found: {target_repo}")
            sys.exit(1)

    print("=" * 60)
    print("Discovery Engine Run")
    print("=" * 60)
    print(f"Time window:  {args.days} days")
    print(f"PostHog data: {args.posthog_data}")
    if target_repo:
        print(f"Target repo:  {target_repo}")
        print(f"Scope dirs:   {args.scope_dirs or ['(auto)']}")
        print(f"Doc paths:    {args.doc_paths or ['(auto)']}")
        print(f"Auto-pull:    {not args.no_auto_pull}")
    else:
        print(f"Target repo:  (self — FeedForward)")
    print()

    # Load PostHog data
    posthog_path = Path(project_root) / args.posthog_data
    if not posthog_path.exists():
        print(f"ERROR: PostHog snapshot not found at {posthog_path}")
        sys.exit(1)
    posthog_data = load_posthog_data(str(posthog_path))

    # Check OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        sys.exit(1)
    print(f"OpenAI key:   ...{api_key[-4:]}")

    # Database
    print("Connecting to database...")
    conn = get_db_connection()
    print("Connected.")

    # Quick sanity: check discovery tables exist
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('discovery_runs', 'stage_executions', 'agent_invocations')
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]
        if len(tables) < 3:
            print(f"ERROR: Missing discovery tables. Found: {tables}")
            print("Run migrations 023-025 first.")
            conn.close()
            sys.exit(1)
        print(f"Discovery tables: {', '.join(tables)}")

    # Quick sanity: check conversation count
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM conversations
            WHERE created_at >= NOW() - make_interval(days => %s)
        """, (args.days,))
        conv_count = cur.fetchone()[0]
        print(f"Conversations in last {args.days} days: {conv_count}")

    if args.dry_run:
        print("\n--- DRY RUN: config validated, exiting ---")
        conn.close()
        return

    print()
    print("=" * 60)
    print("Starting discovery run...")
    print("=" * 60)
    print()

    transport = InMemoryTransport()
    orchestrator = DiscoveryOrchestrator(
        db_connection=conn,
        transport=transport,
        posthog_data=posthog_data,
        repo_root=project_root,
    )

    config = RunConfig(
        time_window_days=args.days,
        target_repo_path=target_repo,
        scope_dirs=args.scope_dirs,
        doc_paths=args.doc_paths,
        auto_pull=not args.no_auto_pull,
    )

    start_time = time.time()
    run = None
    try:
        run = orchestrator.run(config=config)
        conn.commit()
        print("Committed discovery run data to Postgres.")
    except Exception as e:
        elapsed = time.time() - start_time
        conn.rollback()
        print(f"\nRun FAILED after {elapsed:.1f}s (rolled back): {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        sys.exit(1)

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("Run complete!")
    print("=" * 60)
    print(f"Run ID:        {run.id}")
    print(f"Status:        {run.status}")
    print(f"Current stage: {run.current_stage}")
    print(f"Elapsed:       {elapsed:.1f}s")

    # Fetch stage details (data is now committed)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT stage, status,
                   jsonb_array_length(COALESCE(artifacts->'findings', '[]'::jsonb)) as finding_count,
                   jsonb_array_length(COALESCE(artifacts->'briefs', '[]'::jsonb)) as brief_count,
                   jsonb_array_length(COALESCE(artifacts->'solutions', '[]'::jsonb)) as solution_count,
                   jsonb_array_length(COALESCE(artifacts->'specs', '[]'::jsonb)) as spec_count,
                   jsonb_array_length(COALESCE(artifacts->'rankings', '[]'::jsonb)) as ranking_count
            FROM stage_executions
            WHERE run_id = %s
            ORDER BY started_at
        """, (str(run.id),))

        print("\nStage breakdown:")
        for row in cur.fetchall():
            stage, status, findings, briefs, solutions, specs, rankings = row
            counts = []
            if findings: counts.append(f"{findings} findings")
            if briefs: counts.append(f"{briefs} briefs")
            if solutions: counts.append(f"{solutions} solutions")
            if specs: counts.append(f"{specs} specs")
            if rankings: counts.append(f"{rankings} rankings")
            count_str = ", ".join(counts) if counts else "no artifacts"
            print(f"  {stage:25s} {status:20s} {count_str}")

    # Token usage from agent invocations
    with conn.cursor() as cur:
        cur.execute("""
            SELECT agent_name,
                   SUM((token_usage->>'total_tokens')::int) as total_tokens
            FROM agent_invocations
            WHERE run_id = %s AND token_usage IS NOT NULL
            GROUP BY agent_name
            ORDER BY total_tokens DESC
        """, (str(run.id),))
        rows = cur.fetchall()
        if rows:
            print("\nToken usage by agent:")
            total = 0
            for agent_name, tokens in rows:
                print(f"  {agent_name:25s} {tokens:>8,} tokens")
                total += tokens
            print(f"  {'TOTAL':25s} {total:>8,} tokens")

    if run.errors:
        print("\nErrors:")
        for err in run.errors:
            print(f"  {err}")

    conn.close()
    print(f"\nDone. Run ID: {run.id}")


if __name__ == "__main__":
    main()
