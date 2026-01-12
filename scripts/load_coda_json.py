#!/usr/bin/env python3
"""
Load Coda themes from JSON into the database as conversations.

This script:
1. Reads the extracted themes from reports/coda_themes_*.json
2. Groups them by source_row_id
3. Inserts as pseudo-conversations with data_source='coda'
"""
import json
import psycopg2
import psycopg2.extras
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def main():
    # Find the JSON file
    reports_dir = Path(__file__).parent.parent / "reports"
    json_files = list(reports_dir.glob("coda_themes_*.json"))

    if not json_files:
        print("No coda_themes_*.json file found in reports/")
        return 1

    json_file = sorted(json_files)[-1]  # Most recent
    print(f"Loading from: {json_file}")

    with open(json_file) as f:
        data = json.load(f)

    print(f"Loaded {len(data)} themes from Coda JSON...")

    # Group by source_row_id to create pseudo-conversations
    rows = defaultdict(list)
    row_metadata = {}

    for theme in data:
        row_id = theme.get('source_row_id', 'unknown')
        rows[row_id].append(theme)
        if row_id not in row_metadata:
            row_metadata[row_id] = {
                'table': theme.get('table', 'unknown'),
                'source': theme.get('source', 'coda'),
            }

    print(f"Grouped into {len(rows)} unique rows")

    # Connect to database
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    conn.autocommit = False

    inserted = 0
    skipped = 0

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for row_id, themes in rows.items():
                metadata = row_metadata[row_id]

                # Build conversation ID with proper composite format
                # Format: coda_row_{table_slug}_{row_id}
                table_slug = metadata['table'].lower().replace(' ', '_')[:20]
                conv_id = f"coda_row_{table_slug}_{row_id}"

                # Check if already exists
                cur.execute("SELECT id FROM conversations WHERE id = %s", (conv_id,))
                if cur.fetchone():
                    skipped += 1
                    continue

                # Combine text from all themes for this row
                text_parts = []
                theme_types = set()
                for t in themes:
                    if t.get('text'):
                        field = t.get('field', '')
                        text = t['text']
                        if field:
                            text_parts.append(f"[{field}] {text}")
                        else:
                            text_parts.append(text)
                    theme_types.add(t.get('type', 'unknown'))

                combined_text = "\n\n".join(text_parts)
                if not combined_text.strip():
                    skipped += 1
                    continue

                # Get participant info from first theme (if available)
                participant = themes[0].get('participant', 'Research participant')

                # Insert as conversation
                cur.execute("""
                    INSERT INTO conversations (
                        id, created_at, source_body, source_type, source_subject,
                        issue_type, sentiment, churn_risk, priority, data_source, source_metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                """, (
                    conv_id,
                    datetime.now(timezone.utc),
                    combined_text[:50000],  # Truncate if too long
                    'coda_research',
                    f"Coda: {metadata['table']}",
                    'feedback',  # Default type
                    'neutral',   # Default sentiment
                    False,       # churn_risk
                    'normal',    # priority
                    'coda',
                    json.dumps({
                        'table': metadata['table'],
                        'row_id': row_id,
                        'theme_types': list(theme_types),
                        'theme_count': len(themes),
                        'participant': participant,
                    })
                ))
                inserted += 1

                if inserted % 500 == 0:
                    print(f"  Inserted {inserted} conversations...")

            conn.commit()
            print(f"\nDone! Inserted {inserted} conversations, skipped {skipped} (empty or existing)")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
