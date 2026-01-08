# Story ID Tracking for Ground Truth Clustering

**Status**: ✅ Implemented (2026-01-07)
**Purpose**: Enable Shortcut ticket mapping analysis for categorization validation

## Overview

Story ID tracking enables powerful ground-truth clustering analysis by linking Intercom conversations to Shortcut stories/tickets. When multiple conversations share the same `story_id`, it represents human curation - support team members have decided "these conversations are all about the same issue."

This creates a rich dataset for:

1. **Categorization consistency validation** - Do we assign the same theme to conversations humans grouped together?
2. **Vocabulary gap detection** - High-volume stories without matching themes = missing patterns
3. **Signature specificity calibration** - Learn the right level of granularity from human decisions
4. **Ground truth for A/B testing** - Test prompt changes against human-curated clusters

## Database Schema

### conversations.story_id

```sql
ALTER TABLE conversations
ADD COLUMN story_id TEXT;

CREATE INDEX idx_conversations_story_id
ON conversations(story_id)
WHERE story_id IS NOT NULL;
```

**Type**: `TEXT` (nullable)
**Example**: `"sc-12345"`, `"story-67890"`
**Source**: Intercom API → `linked_objects.data.id` (Shortcut integration)

### conversation_clusters View

Automatically groups conversations by `story_id` for analysis:

```sql
SELECT * FROM conversation_clusters
WHERE conversation_count >= 5  -- High-volume stories
ORDER BY conversation_count DESC;
```

**Columns**:

- `story_id` - Shortcut story/ticket ID
- `conversation_count` - Number of conversations in cluster
- `conversation_ids` - Array of conversation IDs (ordered by time)
- `first_conversation_at` - When cluster started
- `last_conversation_at` - Most recent conversation
- `issue_types` - Array of distinct issue types assigned
- `product_areas` - Array of distinct product areas from themes
- `issue_signatures` - Array of distinct issue signatures from themes

## Usage

### 1. Storing Conversations with Story ID

```python
from db.classification_storage import store_classification_result

store_classification_result(
    conversation_id="215472586213019",
    created_at=datetime.utcnow(),
    source_body="I need help with scheduling pins",
    source_type="conversation",
    source_url="https://app.tailwindapp.com/schedule",
    contact_email="user@example.com",
    contact_id="abc123",
    stage1_result=stage1_data,
    stage2_result=stage2_data,
    story_id="sc-45678"  # ← Shortcut story ID
)
```

### 2. Analyzing Categorization Consistency

```python
from db.connection import get_connection

# Find stories with inconsistent categorization
with get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT
                story_id,
                conversation_count,
                ARRAY_LENGTH(product_areas, 1) as area_diversity,
                ARRAY_LENGTH(issue_signatures, 1) as signature_diversity,
                product_areas,
                issue_signatures
            FROM conversation_clusters
            WHERE conversation_count >= 3
              AND ARRAY_LENGTH(issue_signatures, 1) > 2  -- High variance
            ORDER BY signature_diversity DESC
        """)

        inconsistent = cursor.fetchall()

        for story in inconsistent:
            print(f"Story {story[0]}: {story[1]} convos, {story[3]} different signatures")
            print(f"  Signatures: {story[5]}")
```

**Expected output**:

```
Story sc-12345: 5 convos, 4 different signatures
  Signatures: ['scheduling_feature_question', 'pin_spacing_question',
               'smartschedule_inquiry', 'general_product_question']
```

**Interpretation**: These 5 conversations should probably all have the same signature. Use this to identify:

- Over-splitting (too specific)
- Generic fallbacks (LLM couldn't find common pattern)
- Missing vocabulary themes

### 3. Finding Vocabulary Gaps

```python
# High-volume stories without matching themes
cursor.execute("""
    SELECT
        c.story_id,
        COUNT(*) as conversation_count,
        ARRAY_AGG(DISTINCT t.issue_signature) as signatures,
        COUNT(DISTINCT t.issue_signature) as unique_signatures
    FROM conversations c
    LEFT JOIN themes t ON c.id = t.conversation_id
    WHERE c.story_id IS NOT NULL
    GROUP BY c.story_id
    HAVING COUNT(*) >= 5  -- High volume
       AND COUNT(DISTINCT t.issue_signature) > 3  -- High variance
    ORDER BY COUNT(*) DESC
    LIMIT 20
""")
```

**Use case**: These high-volume, high-variance stories indicate missing vocabulary themes. Create new themes based on Shortcut card titles/descriptions.

### 4. Signature Specificity Validation

```python
# Stories where all conversations have the same signature = good
cursor.execute("""
    SELECT
        story_id,
        conversation_count,
        issue_signatures[1] as consistent_signature
    FROM conversation_clusters
    WHERE ARRAY_LENGTH(issue_signatures, 1) = 1  -- Perfect consistency
      AND conversation_count >= 3
    ORDER BY conversation_count DESC
""")
```

**Interpretation**: These represent the "right" level of specificity. Use them to:

- Validate existing vocabulary themes
- Train prompt improvements
- Set quality benchmarks (target: >80% of stories with uniform signatures)

## Analysis Workflows

### Workflow 1: Categorization Consistency Report

```python
#!/usr/bin/env python3
"""
Generate categorization consistency report for stories.
Target: >80% of multi-conversation stories should have uniform categorization.
"""

from db.connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cursor:
        # Overall consistency score
        cursor.execute("""
            SELECT
                COUNT(*) as total_stories,
                COUNT(CASE WHEN ARRAY_LENGTH(issue_signatures, 1) = 1 THEN 1 END) as consistent_stories,
                ROUND(100.0 * COUNT(CASE WHEN ARRAY_LENGTH(issue_signatures, 1) = 1 THEN 1 END) / COUNT(*), 1) as consistency_pct
            FROM conversation_clusters
            WHERE conversation_count >= 2
        """)

        stats = cursor.fetchone()
        print(f"Consistency Score: {stats[2]}%")
        print(f"  Consistent: {stats[1]}/{stats[0]} stories")
```

### Workflow 2: Vocabulary Gap Prioritization

```python
#!/usr/bin/env python3
"""
Identify top 20 vocabulary gaps by conversation volume.
Create new themes for these high-impact patterns.
"""

from db.connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT
                story_id,
                conversation_count,
                issue_signatures,
                product_areas
            FROM conversation_clusters
            WHERE conversation_count >= 5
              AND (
                  ARRAY_LENGTH(issue_signatures, 1) > 2  -- High variance
                  OR issue_signatures && ARRAY['general_product_question', 'misdirected_inquiry']::text[]  -- Generic
              )
            ORDER BY conversation_count DESC
            LIMIT 20
        """)

        gaps = cursor.fetchall()

        print("Top 20 Vocabulary Gaps:\n")
        for i, gap in enumerate(gaps, 1):
            print(f"{i}. Story {gap[0]}: {gap[1]} conversations")
            print(f"   Signatures: {gap[2]}")
            print(f"   Areas: {gap[3]}")
            print(f"   → Action: Fetch Shortcut card details and create specific theme\n")
```

### Workflow 3: A/B Testing Validation

```python
#!/usr/bin/env python3
"""
Use story clusters as ground truth for testing prompt improvements.

Test: Does new prompt reduce signature variance within stories?
"""

from db.connection import get_connection

# Baseline: Current signature variance
cursor.execute("""
    SELECT AVG(ARRAY_LENGTH(issue_signatures, 1))
    FROM conversation_clusters
    WHERE conversation_count >= 3
""")
baseline_variance = cursor.fetchone()[0]

# After prompt change: Re-run theme extraction
# Compare new variance to baseline

print(f"Baseline signature variance: {baseline_variance:.2f}")
print(f"Target: <1.5 (most stories have 1-2 signatures max)")
```

## Fetching Story IDs from Intercom

### Option 1: Via Intercom API (Recommended)

**IMPORTANT**: In Intercom, Shortcut story IDs are stored in the `v2` field (not `id`).

```python
# When fetching conversation from Intercom
import requests

conversation_id = "215472586213019"
response = requests.get(
    f"https://api.intercom.io/conversations/{conversation_id}",
    headers={"Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}"}
)

data = response.json()

# Extract linked Shortcut story
# NOTE: Intercom uses "v2" field for Shortcut story IDs
story_id = None
if "linked_objects" in data and "data" in data["linked_objects"]:
    for linked_obj in data["linked_objects"]["data"]:
        if linked_obj.get("type") == "ticket":  # Shortcut ticket
            # IMPORTANT: Use "v2" field, not "id"
            story_id = linked_obj.get("v2")
            break

# Store with story_id
store_classification_result(
    conversation_id=conversation_id,
    # ... other fields ...
    story_id=story_id  # Will be Shortcut story ID (e.g., "sc-12345")
)
```

**Example Intercom Response**:

```json
{
  "type": "conversation",
  "id": "215472586213019",
  "linked_objects": {
    "type": "list",
    "data": [
      {
        "type": "ticket",
        "id": "intercom_ticket_id_123",
        "v2": "sc-12345" // ← This is the Shortcut story ID we want
      }
    ]
  }
}
```

### Option 2: Backfill Existing Conversations

```python
#!/usr/bin/env python3
"""
Backfill story_id for existing 535 conversations.
Fetches linked ticket data from Intercom API.
"""

from db.connection import get_connection
import requests
import time

with get_connection() as conn:
    with conn.cursor() as cursor:
        # Get all conversation IDs
        cursor.execute("SELECT id FROM conversations WHERE story_id IS NULL")
        conversation_ids = [row[0] for row in cursor.fetchall()]

        print(f"Backfilling {len(conversation_ids)} conversations...")

        for i, conv_id in enumerate(conversation_ids, 1):
            try:
                # Fetch from Intercom
                response = requests.get(
                    f"https://api.intercom.io/conversations/{conv_id}",
                    headers={"Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}"}
                )
                data = response.json()

                # Extract story_id
                story_id = None
                if "linked_objects" in data:
                    for obj in data["linked_objects"].get("data", []):
                        if obj.get("type") == "ticket":
                            story_id = obj.get("id")
                            break

                # Update database
                if story_id:
                    cursor.execute(
                        "UPDATE conversations SET story_id = %s WHERE id = %s",
                        (story_id, conv_id)
                    )
                    conn.commit()
                    print(f"[{i}/{len(conversation_ids)}] Updated {conv_id}: story_id={story_id}")

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"[{i}/{len(conversation_ids)}] Error for {conv_id}: {e}")

        print(f"\n✅ Backfill complete!")
```

## Success Metrics

Track story_id coverage and clustering quality:

```sql
-- Coverage
SELECT
    COUNT(*) as total_conversations,
    COUNT(story_id) as with_story_id,
    ROUND(100.0 * COUNT(story_id) / COUNT(*), 1) as coverage_pct
FROM conversations;

-- Clustering statistics
SELECT
    COUNT(DISTINCT story_id) as unique_stories,
    AVG(conversation_count) as avg_conversations_per_story,
    MAX(conversation_count) as max_conversations_per_story
FROM conversation_clusters;

-- Consistency score (target: >80%)
SELECT
    ROUND(100.0 * COUNT(CASE WHEN ARRAY_LENGTH(issue_signatures, 1) = 1 THEN 1 END) / COUNT(*), 1) as consistency_score
FROM conversation_clusters
WHERE conversation_count >= 2;
```

## Next Steps

1. ✅ **Schema implemented** - `story_id` column, index, and view created
2. ✅ **Storage updated** - `store_classification_result()` accepts `story_id` parameter
3. ✅ **Testing complete** - Verified clustering works with 3-conversation example
4. ⏭️ **Backfill data** - Populate `story_id` for existing 535 conversations
5. ⏭️ **Run analysis** - Generate categorization consistency report
6. ⏭️ **Identify gaps** - Find top 20 missing vocabulary themes
7. ⏭️ **Iterate** - Add new themes, re-test, measure improvement

## Impact Estimate

Based on categorization effectiveness evaluation:

**Current State**:

- "Other" category: 17.1% (44 conversations)
- Generic signatures: 32.3% (83 conversations)

**Expected Impact** (after Shortcut mapping analysis):

- **"Other" reduction**: -5-7% (find 10-15 new product area patterns)
- **Generic signature reduction**: -8-12% (identify 20-30 specific themes)
- **Categorization consistency**: 60% → 85% (uniform signatures within stories)

**Timeline**:

- Backfill: 2-3 hours
- Analysis: 1-2 hours
- Vocabulary updates: 2-3 hours
- **Total**: 5-8 hours for 12-19% combined improvement

## References

- Migration: `src/db/migrations/002_add_story_id.sql`
- Storage function: `src/db/classification_storage.py:store_classification_result()`
- View definition: `conversation_clusters`
- Intercom API docs: https://developers.intercom.com/docs/references/rest-api/api.intercom.io/Conversations/
