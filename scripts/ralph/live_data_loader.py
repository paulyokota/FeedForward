#!/usr/bin/env python3
"""
Live Data Loader for Ralph V2 Pipeline Testing

Pulls non-deterministic data from multiple sources:
1. Intercom - Live conversations via MCP/API
2. Coda Tables - Via Coda API
3. Coda Pages - From imported JSON (static but sampled randomly)

This enables testing the pipeline's ability to handle real, variable input data
rather than static test fixtures.
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Import Coda client
try:
    from src.coda_client import CodaClient
    CODA_AVAILABLE = True
except ImportError:
    CODA_AVAILABLE = False
    print("Warning: CodaClient not available")


# Intercom MCP is available via subprocess call to claude
INTERCOM_MCP_AVAILABLE = True  # Assume available if running in Claude context


def load_intercom_conversations(
    count: int = 3,
    days_back: int = 30,
    randomize: bool = True
) -> List[Dict[str, Any]]:
    """
    Load Intercom conversations for testing.

    Since MCP is only available in Claude context, this function
    queries the database for Intercom conversations that were
    previously imported.

    Args:
        count: Number of conversations to return
        days_back: How far back to look for conversations
        randomize: Whether to randomly sample or take most recent

    Returns:
        List of conversation dicts formatted for pipeline testing
    """
    import psycopg2
    import psycopg2.extras

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("  Warning: DATABASE_URL not set, skipping Intercom")
        return []

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get Intercom conversations from database
            since_date = datetime.now(timezone.utc) - timedelta(days=days_back)

            if randomize:
                # Random sample using TABLESAMPLE or ORDER BY RANDOM()
                cur.execute("""
                    SELECT id, source_body, source_subject, source_type,
                           issue_type, sentiment, created_at, source_metadata
                    FROM conversations
                    WHERE data_source = 'intercom'
                      AND created_at >= %s
                      AND source_body IS NOT NULL
                      AND LENGTH(source_body) > 100
                    ORDER BY RANDOM()
                    LIMIT %s
                """, (since_date, count * 2))  # Get more than needed for filtering
            else:
                cur.execute("""
                    SELECT id, source_body, source_subject, source_type,
                           issue_type, sentiment, created_at, source_metadata
                    FROM conversations
                    WHERE data_source = 'intercom'
                      AND created_at >= %s
                      AND source_body IS NOT NULL
                      AND LENGTH(source_body) > 100
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (since_date, count * 2))

            rows = cur.fetchall()

        # Format for pipeline
        conversations = []
        for row in rows[:count]:
            conversations.append({
                "id": f"live_intercom_{row['id']}",
                "type": "intercom",
                "source_type": "intercom",
                "description": row.get('source_subject', 'Intercom conversation'),
                "content": row['source_body'],
                "metadata": {
                    "original_id": row['id'],
                    "issue_type": row.get('issue_type'),
                    "sentiment": row.get('sentiment'),
                    "created_at": row['created_at'].isoformat() if row.get('created_at') else None,
                }
            })

        return conversations

    except Exception as e:
        print(f"  Warning: Could not load Intercom data: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def load_coda_table_data(
    count: int = 2,
    randomize: bool = True
) -> List[Dict[str, Any]]:
    """
    Load data from Coda synthesis tables via API.

    Args:
        count: Number of table entries to return
        randomize: Whether to randomly sample

    Returns:
        List of data dicts formatted for pipeline testing
    """
    if not CODA_AVAILABLE:
        print("  Warning: CodaClient not available, skipping Coda tables")
        return []

    if not os.getenv('CODA_API_KEY') or not os.getenv('CODA_DOC_ID'):
        print("  Warning: CODA_API_KEY or CODA_DOC_ID not set, skipping Coda tables")
        return []

    try:
        client = CodaClient()

        # Get synthesis tables
        synthesis_tables = client.get_synthesis_tables()
        if not synthesis_tables:
            print("  Warning: No synthesis tables found in Coda")
            return []

        # Collect rows from multiple tables
        all_rows = []
        for table in synthesis_tables[:5]:  # Check up to 5 tables
            try:
                rows = client.get_table_rows(table['id'], limit=50)
                columns = client.get_table_columns(table['id'])
                col_map = {c['id']: c.get('name', c['id']) for c in columns}

                for row in rows:
                    # Convert row values to readable format
                    values = row.get('values', {})
                    text_parts = []
                    for col_id, value in values.items():
                        col_name = col_map.get(col_id, col_id)
                        if value and str(value).strip():
                            text_parts.append(f"[{col_name}] {value}")

                    if text_parts:
                        all_rows.append({
                            "table_name": table.get('name', 'Unknown'),
                            "table_id": table['id'],
                            "row_id": row.get('id', 'unknown'),
                            "content": "\n".join(text_parts),
                        })
            except Exception as e:
                print(f"  Warning: Could not read table {table.get('name')}: {e}")
                continue

        if not all_rows:
            print("  Warning: No rows found in Coda tables")
            return []

        # Sample rows
        if randomize:
            selected = random.sample(all_rows, min(count, len(all_rows)))
        else:
            selected = all_rows[:count]

        # Format for pipeline
        result = []
        for row in selected:
            result.append({
                "id": f"live_coda_table_{row['table_id']}_{row['row_id']}",
                "type": "coda_table",
                "source_type": "coda_table",
                "description": f"Coda: {row['table_name']}",
                "content": row['content'],
                "metadata": {
                    "table_name": row['table_name'],
                    "table_id": row['table_id'],
                    "row_id": row['row_id'],
                }
            })

        return result

    except Exception as e:
        print(f"  Warning: Could not load Coda table data: {e}")
        return []


def load_coda_page_data(
    count: int = 2,
    randomize: bool = True,
    json_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Load data from imported Coda pages/docs JSON.

    The JSON contains themes extracted from Coda pages during a
    previous import. We sample from this to simulate page data.

    Args:
        count: Number of page entries to return
        randomize: Whether to randomly sample
        json_path: Path to the Coda themes JSON file

    Returns:
        List of data dicts formatted for pipeline testing
    """
    if json_path is None:
        # Find the most recent Coda themes JSON
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        json_files = list(reports_dir.glob("coda_themes_*.json"))
        if not json_files:
            print("  Warning: No coda_themes_*.json found in reports/")
            return []
        json_path = sorted(json_files)[-1]

    if not json_path.exists():
        print(f"  Warning: Coda themes file not found: {json_path}")
        return []

    try:
        # Load the JSON - it's large so we'll stream-read just what we need
        with open(json_path) as f:
            all_themes = json.load(f)

        # Group themes by source_row_id to get coherent "pages"
        pages = {}
        for theme in all_themes:
            row_id = theme.get('source_row_id', 'unknown')
            if row_id not in pages:
                pages[row_id] = {
                    "row_id": row_id,
                    "table": theme.get('table', 'Unknown'),
                    "themes": [],
                }
            pages[row_id]["themes"].append(theme)

        # Filter to pages with substantial content
        substantial_pages = [
            p for p in pages.values()
            if len(p["themes"]) >= 2  # At least 2 themes
        ]

        if not substantial_pages:
            print("  Warning: No substantial pages found in Coda themes")
            return []

        # Sample pages
        if randomize:
            selected = random.sample(substantial_pages, min(count, len(substantial_pages)))
        else:
            selected = substantial_pages[:count]

        # Format for pipeline
        result = []
        for page in selected:
            # Combine theme texts
            text_parts = []
            for theme in page["themes"]:
                field = theme.get('field', '')
                text = theme.get('text', '')
                if text:
                    if field:
                        text_parts.append(f"[{field}] {text}")
                    else:
                        text_parts.append(text)

            content = "\n\n".join(text_parts)
            if len(content) > 100:  # Only include if substantial
                result.append({
                    "id": f"live_coda_page_{page['row_id']}",
                    "type": "coda_page",
                    "source_type": "coda_page",
                    "description": f"Coda Page: {page['table']}",
                    "content": content,
                    "metadata": {
                        "table": page['table'],
                        "row_id": page['row_id'],
                        "theme_count": len(page["themes"]),
                    }
                })

        return result

    except Exception as e:
        print(f"  Warning: Could not load Coda page data: {e}")
        import traceback
        traceback.print_exc()
        return []


def load_live_test_data(
    intercom_count: int = 8,
    coda_table_count: int = 4,
    coda_page_count: int = 4,
    days_back: int = 60,
    randomize: bool = True,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Load live test data from all three sources.

    Args:
        intercom_count: Number of Intercom conversations
        coda_table_count: Number of Coda table entries
        coda_page_count: Number of Coda page entries
        days_back: How far back to look for Intercom data
        randomize: Whether to randomize selection
        verbose: Print progress messages

    Returns:
        Dict with sources list and metadata, compatible with manifest format
    """
    if verbose:
        print("\n[LOADING LIVE TEST DATA]")
        print(f"  Target: {intercom_count} Intercom, {coda_table_count} Coda tables, {coda_page_count} Coda pages")
        print(f"  Randomize: {randomize}, Days back: {days_back}")

    sources = []

    # Load from each source
    if verbose:
        print("\n  Loading Intercom conversations...", end=" ", flush=True)
    intercom_data = load_intercom_conversations(
        count=intercom_count,
        days_back=days_back,
        randomize=randomize
    )
    sources.extend(intercom_data)
    if verbose:
        print(f"got {len(intercom_data)}")

    if verbose:
        print("  Loading Coda table data...", end=" ", flush=True)
    coda_table_data = load_coda_table_data(
        count=coda_table_count,
        randomize=randomize
    )
    sources.extend(coda_table_data)
    if verbose:
        print(f"got {len(coda_table_data)}")

    if verbose:
        print("  Loading Coda page data...", end=" ", flush=True)
    coda_page_data = load_coda_page_data(
        count=coda_page_count,
        randomize=randomize
    )
    sources.extend(coda_page_data)
    if verbose:
        print(f"got {len(coda_page_data)}")

    # Build manifest-compatible result
    result = {
        "version": "2.0-live",
        "description": "Live test data loaded at runtime",
        "loaded_at": datetime.now().isoformat(),
        "randomized": randomize,
        "sources": sources,
        "source_counts": {
            "intercom": len(intercom_data),
            "coda_table": len(coda_table_data),
            "coda_page": len(coda_page_data),
            "total": len(sources),
        },
        "quality_thresholds": {
            "gestalt_min": 5.0,
            "per_source_gestalt_min": 5.0,
            "scoping_min": 5.0
        },
        "evaluation_config": {
            "gestalt_model": "gpt-4o-mini",
            "gold_standard_path": "docs/story_knowledge_base.md",
            "max_retries": 3
        }
    }

    if verbose:
        print(f"\n  Total sources loaded: {len(sources)}")
        by_type = {}
        for s in sources:
            t = s.get('type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1
        for t, c in by_type.items():
            print(f"    - {t}: {c}")

    return result


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load live test data for Ralph V2")
    parser.add_argument("--intercom", type=int, default=3, help="Number of Intercom conversations")
    parser.add_argument("--coda-tables", type=int, default=2, help="Number of Coda table entries")
    parser.add_argument("--coda-pages", type=int, default=2, help="Number of Coda page entries")
    parser.add_argument("--days", type=int, default=30, help="Days back for Intercom")
    parser.add_argument("--no-random", action="store_true", help="Don't randomize")
    parser.add_argument("--output", type=Path, help="Output JSON file")

    args = parser.parse_args()

    data = load_live_test_data(
        intercom_count=args.intercom,
        coda_table_count=args.coda_tables,
        coda_page_count=args.coda_pages,
        days_back=args.days,
        randomize=not args.no_random
    )

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"\nSaved to: {args.output}")
    else:
        print("\nSample source IDs:")
        for s in data["sources"][:5]:
            desc = s.get('description') or 'No description'
            print(f"  - {s['id']}: {desc[:50]}")
