#!/usr/bin/env python3
"""
Backfill Coda stories with rich formatting.

This script:
1. Queries stories with data_source='coda'
2. Regenerates descriptions using build_research_story_description()
3. Updates evidence with formatted excerpts

Usage:
    python scripts/backfill_coda_formatting.py --dry-run  # Preview changes
    python scripts/backfill_coda_formatting.py --apply    # Apply changes
"""
import argparse
import psycopg2
import psycopg2.extras
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from src.story_formatter import format_coda_excerpt, build_research_story_description

load_dotenv()


def fetch_coda_stories(conn, limit: int) -> List[Dict]:
    """
    Fetch Coda stories with their evidence.

    Identifies Coda stories by checking source_stats for 'coda' key.

    Args:
        conn: Database connection
        limit: Maximum stories to fetch

    Returns:
        List of story dicts with evidence
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                s.id,
                s.title,
                s.description,
                e.excerpts,
                e.source_stats
            FROM stories s
            INNER JOIN story_evidence e ON e.story_id = s.id
            WHERE e.source_stats ? 'coda'
            ORDER BY s.created_at DESC
            LIMIT %s
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]


def format_story_description(story: Dict) -> Optional[str]:
    """
    Generate new description using build_research_story_description().

    Args:
        story: Story dict with evidence

    Returns:
        Formatted description or None if cannot format
    """
    excerpts = story.get('excerpts') or []
    source_stats = story.get('source_stats') or {}

    if not excerpts:
        return None

    # Extract theme name from story title (remove count prefix)
    # Format: "[5] Theme Name - Review" -> "theme_name"
    name = story['title']
    if name.startswith('['):
        # Remove count: "[5] Theme Name - Review"
        name = name.split(']', 1)[1].strip()

    # Remove suffix: "Theme Name - Review"
    if ' - ' in name:
        name = name.split(' - ')[0].strip()

    # Convert to snake_case
    theme_name = name.lower().replace(' ', '_')

    # Determine theme type from excerpts
    theme_type = 'insight'  # Default
    for excerpt in excerpts:
        metadata = excerpt.get('source_metadata', {})
        if 'theme_type' in metadata:
            theme_type = metadata['theme_type']
            break

    # Count participants (unique conversation_ids)
    conversation_ids = {e.get('conversation_id') for e in excerpts if e.get('conversation_id')}
    participant_count = len(conversation_ids)

    # Build source breakdown
    source_breakdown = {}
    for source, count in source_stats.items():
        source_breakdown[source] = count

    return build_research_story_description(
        theme_name=theme_name,
        excerpts=excerpts,
        participant_count=participant_count,
        theme_type=theme_type,
        source_breakdown=source_breakdown,
    )


def is_already_formatted(text: str) -> bool:
    """
    Check if excerpt text is already formatted with markdown links.

    Idempotency check to prevent double-formatting if script runs twice.

    Args:
        text: Excerpt text to check

    Returns:
        True if text appears to already be formatted
    """
    # Formatted text starts with markdown link: [label](url)
    # and contains blockquote: > text
    return text.startswith('[') and '](http' in text and '\n>' in text


def format_story_evidence(evidence: List[Dict]) -> List[Dict]:
    """
    Update excerpts with formatted text using format_coda_excerpt().

    Args:
        evidence: List of excerpt dicts

    Returns:
        Updated evidence list with formatted text
    """
    formatted_evidence = []

    for excerpt in evidence:
        # Only format Coda excerpts
        if excerpt.get('source') != 'coda':
            formatted_evidence.append(excerpt)
            continue

        text = excerpt.get('text', '')

        # Idempotency: skip if already formatted
        if is_already_formatted(text):
            formatted_evidence.append(excerpt)
            continue
        metadata = excerpt.get('source_metadata', {})
        conversation_id = excerpt.get('conversation_id')

        # Extract row_id from conversation_id if available
        # Format: coda_row_{table}_{row_id}
        row_id = None
        if conversation_id and conversation_id.startswith('coda_row_'):
            parts = conversation_id.split('_')
            if len(parts) >= 3:
                row_id = parts[-1]

        # Format the excerpt text
        formatted_text = format_coda_excerpt(
            text=text,
            table_name=metadata.get('table_name'),
            participant=metadata.get('participant'),
            page_id=metadata.get('page_id'),
            row_id=row_id,
            coda_doc_id=metadata.get('coda_doc_id'),
        )

        # Update excerpt with formatted text
        updated_excerpt = excerpt.copy()
        updated_excerpt['text'] = formatted_text
        formatted_evidence.append(updated_excerpt)

    return formatted_evidence


def show_diff(story_name: str, old_desc: str, new_desc: str, old_evidence: List, new_evidence: List):
    """
    Show what would change.

    Args:
        story_name: Story name for display
        old_desc: Current description
        new_desc: New description
        old_evidence: Current evidence
        new_evidence: New evidence
    """
    print(f"\n{'=' * 80}")
    print(f"Story: {story_name}")
    print('=' * 80)

    # Description changes
    if old_desc != new_desc:
        print("\n📝 Description Changes:")
        print("\n--- OLD ---")
        print(old_desc[:500] + "..." if len(old_desc) > 500 else old_desc)
        print("\n--- NEW ---")
        print(new_desc[:500] + "..." if len(new_desc) > 500 else new_desc)
    else:
        print("\n✅ Description: No changes")

    # Evidence changes
    evidence_changed = json.dumps(old_evidence) != json.dumps(new_evidence)
    if evidence_changed:
        print(f"\n📊 Evidence: {len(old_evidence)} excerpts -> {len(new_evidence)} excerpts")
        if old_evidence and new_evidence:
            print("\nFirst excerpt comparison:")
            print("--- OLD ---")
            print(json.dumps(old_evidence[0], indent=2)[:300])
            print("\n--- NEW ---")
            print(json.dumps(new_evidence[0], indent=2)[:300])
    else:
        print("\n✅ Evidence: No changes")


def apply_updates(conn, story_id: str, new_desc: str, new_evidence: List[Dict]):
    """
    Write changes to database.

    Args:
        conn: Database connection
        story_id: Story UUID
        new_desc: New description
        new_evidence: New evidence list
    """
    with conn.cursor() as cur:
        # Update story description
        cur.execute("""
            UPDATE stories
            SET description = %s
            WHERE id = %s
        """, (new_desc, story_id))

        # Update evidence
        cur.execute("""
            UPDATE story_evidence
            SET excerpts = %s
            WHERE story_id = %s
        """, (json.dumps(new_evidence), story_id))


def main():
    parser = argparse.ArgumentParser(
        description='Backfill Coda stories with rich formatting'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview changes without writing (default)'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Apply changes to database'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Max stories to process (default: 10)'
    )
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    # Connect to database
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    conn.autocommit = False

    try:
        # Fetch Coda stories
        print(f"Fetching up to {args.limit} Coda stories...")
        stories = fetch_coda_stories(conn, args.limit)
        print(f"Found {len(stories)} Coda stories")

        if not stories:
            print("No Coda stories found to backfill")
            return 0

        # Process each story
        updated_count = 0
        skipped_count = 0

        for story in stories:
            story_id = story['id']
            story_name = story['title']
            old_desc = story['description'] or ''
            old_evidence = story.get('excerpts') or []

            # Generate new description
            new_desc = format_story_description(story)
            if not new_desc:
                print(f"\n⏭️  Skipping {story_name}: No excerpts to format")
                skipped_count += 1
                continue

            # Format evidence
            new_evidence = format_story_evidence(old_evidence)

            # Check if anything changed
            desc_changed = old_desc != new_desc
            evidence_changed = json.dumps(old_evidence) != json.dumps(new_evidence)

            if not desc_changed and not evidence_changed:
                print(f"\n⏭️  Skipping {story_name}: No changes needed")
                skipped_count += 1
                continue

            # Show diff
            if args.dry_run:
                show_diff(story_name, old_desc, new_desc, old_evidence, new_evidence)
            else:
                # Apply changes
                apply_updates(conn, story_id, new_desc, new_evidence)
                print(f"\n✅ Updated: {story_name}")

            updated_count += 1

        # Commit if applying
        if not args.dry_run:
            conn.commit()
            print(f"\n{'=' * 80}")
            print(f"✅ Successfully updated {updated_count} stories")
            print(f"⏭️  Skipped {skipped_count} stories")
        else:
            print(f"\n{'=' * 80}")
            print(f"DRY RUN: Would update {updated_count} stories")
            print(f"Skipped {skipped_count} stories")
            print("\nRun with --apply to make changes")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
