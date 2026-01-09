# Multi-Source Theme Architecture: Phase 0-6 Implementation

**STATUS: PHASE_0_PENDING**
**CODA_CONTENT_IMPORTED: 0**
**THEMES_EXTRACTED: 0**
**ITERATIONS: 0**

## CONTEXT & GOAL

You are extending FeedForward to ingest research data from a Coda repository alongside existing Intercom support conversations. This creates a **multi-source theme extraction system** where research insights and support tickets complement each other.

**Key Insight**: Research and support are complementary data sources:

- **Research (Coda)**: Small sample, deep insights, proactive, "What should we build?"
- **Support (Intercom)**: Large volume, shallow depth, reactive, "What's broken now?"

**YOUR GOAL**:

1. Import all existing Coda research data (100 pages, multiple tables)
2. Build a source-agnostic architecture that normalizes both data sources
3. Extract themes from research content using existing LLM pipeline
4. Create unified theme storage with source tracking
5. Enable cross-source prioritization (themes in BOTH sources = high confidence)

**SUCCESS METRIC**:

- Successfully import 50-100 themes from Coda research data
- Extend database schema to track data sources
- Build source adapters that normalize Coda + Intercom into common format
- Create cross-source analytics showing theme overlap
- Generate Shortcut stories with evidence from both sources

---

## GROUND TRUTH REQUIREMENT

The ONLY valid sources for theme extraction in this project are:

- **Intercom conversations**: Existing support data pipeline (already working)
- **Coda research repository**: Doc ID `c4RRJ_VLtW` (Tailwind Research Ops)

For Coda content:

- AI Summary pages (27 total, 5-10 populated with real research)
- Synthesis tables (Participant Research Synthesis, P4 Synth, Beta Call Synthesis)
- Discovery Learnings page (JTBD framework, MVP priorities)

If you do not find sufficient Coda content:

- You MUST use the Coda API to fetch page content via `/pages/{id}/content` endpoint
- It is NOT acceptable to:
  - Infer synthetic research data
  - Skip pages that appear empty without checking content
  - Quietly proceed with inadequate data

**DO NOT give up on pages without checking their content. Many pages have metadata but rich text content requires the content endpoint.**

---

## PHASE 0: BULK CODA DATA IMPORT & ANALYSIS

**Goal**: Import all existing research data from Coda before building ongoing sync architecture.

### Step 1: Set Up Coda Client

**Create** `src/coda_client.py`:

```python
"""
Coda API Client
Wrapper for Coda REST API to fetch research content.
"""
import os
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

class CodaClient:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("CODA_API_KEY")
        self.doc_id = os.getenv("CODA_DOC_ID")
        self.base_url = "https://coda.io/apis/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

    def list_pages(self) -> List[Dict]:
        \"\"\"List all pages in the doc\"\"\"
        # Implementation based on exploration

    def get_page_content(self, page_id: str) -> Dict:
        \"\"\"Get rich text content from a page\"\"\"
        # Use /pages/{page_id}/content endpoint

    def list_tables(self) -> List[Dict]:
        \"\"\"List all tables in the doc\"\"\"
        # API call

    def get_table_rows(self, table_id: str) -> List[Dict]:
        \"\"\"Get all rows from a table\"\"\"
        # API call with pagination
```

**Verify**:

```bash
python -c "from src.coda_client import CodaClient; c = CodaClient(); print(f'Connected: {len(c.list_pages())} pages')"
```

### Step 2: Import AI Summary Pages

**Create** `scripts/import_coda_ai_summaries.py`:

AI Summary pages contain the highest-value research insights:

- User quotes with specific pain points
- Proto-personas with characteristics
- Feature requests framed as problems
- Workflow analysis showing friction points

**What to extract from each AI Summary page**:

1. Participant email (page name)
2. "Loves" section → positive feedback themes
3. "Pain Points" section → problem themes
4. "Feature Requests" section → feature themes
5. Direct quotes (in quotation marks)
6. Workflow metrics (e.g., "20 tab switches per minute")

**Expected output**: 5-10 populated AI summaries with 20-40 total themes

### Step 3: Import Synthesis Tables

**Tables to import**:

- Participant: Research Synthesis (takeaways, WTP, user feedback)
- P4 Synth (goals, themes, takeaways)
- Beta Call Synthesis (shockers, wishlist, confusion points)

**What to extract**:

- Each row represents one research session or takeaway
- Extract: goals, shocking moments, takeaways, willingness-to-pay signals
- Link to participant if metadata exists

**Expected output**: 50-100 synthesis rows

### Step 4: Import Discovery Learnings

The Discovery Learnings page contains JTBD (Jobs to Be Done) framework analysis and MVP priorities.

**What to extract**:

- Jobs users are trying to accomplish
- MVP feature priorities
- User needs mapped to product areas

**Expected output**: 10-20 strategic themes

### Step 5: Analyze and Generate Import Report

**Create** `reports/coda_import_YYYY-MM-DD.md`:

```markdown
# Coda Research Import Report

## Summary

- AI Summaries imported: X pages
- Synthesis rows imported: Y rows
- Discovery learnings imported: Z items
- Total themes extracted: N

## Theme Breakdown by Type

| Theme Type      | Count | Source       |
| --------------- | ----- | ------------ |
| Pain Point      | X     | AI Summaries |
| Feature Request | Y     | AI Summaries |
| Workflow Issue  | Z     | Synthesis    |
| JTBD            | W     | Discovery    |

## High-Value Themes (with quotes)

[List top 10 themes with example user quotes]

## Comparison to Intercom Themes

- Themes unique to research: X
- Themes also in support data: Y (HIGH CONFIDENCE)
- New vocabulary candidates: Z

## Recommendations

[What this research data suggests for product roadmap]
```

**OUTPUT**:

- `reports/coda_import_YYYY-MM-DD.md`
- All Coda content stored in database with `data_source='coda'`

---

## PHASE 1: DATABASE SCHEMA UPDATES

**Goal**: Extend schema to support multi-source theme tracking.

**Create** `src/db/migrations/003_add_data_source.sql`:

```sql
-- Add source tracking to conversations
ALTER TABLE conversations
ADD COLUMN data_source VARCHAR(50) DEFAULT 'intercom',
ADD COLUMN source_metadata JSONB;

-- Add source tracking to themes
ALTER TABLE themes
ADD COLUMN data_source VARCHAR(50) DEFAULT 'intercom';

-- Add source breakdown to aggregates
ALTER TABLE theme_aggregates
ADD COLUMN source_counts JSONB DEFAULT '{}';
-- Example: {"intercom": 45, "coda": 3}

-- Indexes for source filtering
CREATE INDEX idx_themes_data_source ON themes(data_source);
CREATE INDEX idx_conversations_data_source ON conversations(data_source);
```

**Verify**:

```bash
psql $DATABASE_URL -c "\d conversations" | grep data_source
psql $DATABASE_URL -c "\d themes" | grep data_source
psql $DATABASE_URL -c "\d theme_aggregates" | grep source_counts
```

**OUTPUT**: Migration applied, all tables updated

---

## PHASE 2: SOURCE ADAPTER LAYER

**Goal**: Normalize Coda and Intercom into common "conversation" format.

**Create** `src/adapters/__init__.py`:

```python
"""
Source Adapters
Normalize different data sources into common conversation format.
"""
from abc import ABC, abstractmethod
from typing import Dict, List

class SourceAdapter(ABC):
    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict]:
        \"\"\"Fetch raw data from source\"\"\"
        pass

    @abstractmethod
    def normalize(self, raw_data: Dict) -> Dict:
        \"\"\"Normalize to common conversation format\"\"\"
        pass
```

**Create** `src/adapters/coda_adapter.py`:

```python
class CodaAdapter(SourceAdapter):
    def normalize(self, ai_summary_page: Dict) -> Dict:
        \"\"\"
        Normalize Coda AI Summary to conversation format.

        Returns:
        {
            "id": "coda_ai_summary_{page_id}",
            "text": "{combined_text_from_sections}",
            "data_source": "coda",
            "source_metadata": {
                "page_id": "{id}",
                "participant": "{email}",
                "page_type": "ai_summary",
                "sections": ["loves", "pain_points", "feature_requests"]
            },
            "created_at": "{research_date}"
        }
        \"\"\"
        # Parse AI Summary sections
        # Combine into single text blob for theme extraction
        # Preserve structure in metadata
```

**Create** `src/adapters/intercom_adapter.py`:

```python
class IntercomAdapter(SourceAdapter):
    def normalize(self, conversation: Dict) -> Dict:
        \"\"\"
        Normalize Intercom conversation (existing format).
        Just adds explicit data_source field.
        \"\"\"
        # Existing logic + data_source='intercom'
```

**OUTPUT**: Adapters that produce identical output format regardless of source

---

## PHASE 3: UNIFIED INGESTION PIPELINE

**Goal**: Modify existing pipeline to support multiple sources.

**Update** `src/two_stage_pipeline.py`:

Add source-aware processing:

```python
async def run_pipeline_async(
    days: int = 7,
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
    data_source: str = "intercom"  # NEW PARAMETER
):
    \"\"\"
    Run two-stage classification pipeline.
    Now supports multiple data sources via adapters.
    \"\"\"

    # Load appropriate adapter
    if data_source == "intercom":
        adapter = IntercomAdapter()
    elif data_source == "coda":
        adapter = CodaAdapter()
    else:
        raise ValueError(f"Unknown data source: {data_source}")

    # Fetch and normalize
    raw_data = adapter.fetch(days=days, max_items=max_conversations)
    conversations = [adapter.normalize(item) for item in raw_data]

    # Rest of pipeline remains identical
    # Theme extraction, storage, aggregation work the same
```

**Verify backward compatibility**:

```bash
# Existing Intercom pipeline still works
python -m src.pipeline --days 1 --max 10 --dry-run

# New Coda pipeline works
python -m src.pipeline --days 1 --source coda --dry-run
```

**OUTPUT**: Unified pipeline that handles both sources

---

## PHASE 4: THEME AGGREGATION UPDATES

**Goal**: Track source breakdown in theme aggregates.

**Update** `src/theme_tracker.py`:

```python
def update_aggregate(theme_signature: str, conversation_id: str, data_source: str):
    \"\"\"Update theme aggregate with source tracking\"\"\"

    # Existing logic PLUS:

    # Update source_counts JSONB
    cursor.execute(\"\"\"
        UPDATE theme_aggregates
        SET source_counts = COALESCE(source_counts, '{}'::jsonb)
            || jsonb_build_object(%s,
                COALESCE((source_counts->%s)::int, 0) + 1
            )
        WHERE signature = %s
    \"\"\", (data_source, data_source, theme_signature))
```

**OUTPUT**: Aggregates track theme counts per source

---

## PHASE 5: CROSS-SOURCE ANALYTICS

**Goal**: Create queries that identify themes in both sources.

**Create** `src/analytics/cross_source.py`:

```python
def get_cross_source_themes() -> List[Dict]:
    \"\"\"
    Find themes that appear in BOTH research and support.
    These are high-confidence priorities.
    \"\"\"
    cursor.execute(\"\"\"
        SELECT
            signature,
            product_area,
            issue_type,
            total_conversations,
            source_counts,
            CASE
                WHEN source_counts ? 'coda' AND source_counts ? 'intercom'
                THEN 'high_confidence'
                WHEN source_counts ? 'coda' ONLY
                THEN 'strategic'
                WHEN source_counts ? 'intercom' ONLY
                THEN 'tactical'
            END as priority_category
        FROM theme_aggregates
        WHERE total_conversations >= 2
        ORDER BY
            (COALESCE((source_counts->>'coda')::int, 0) > 0)::int DESC,
            (COALESCE((source_counts->>'intercom')::int, 0)) DESC
    \"\"\")
```

**OUTPUT**: Priority-ranked themes with source breakdown

---

## PHASE 6: SHORTCUT STORY ENRICHMENT

**Goal**: Include evidence from both sources in story descriptions.

**Update** `src/story_formatter.py` (not `escalation.py` - formatting belongs with the formatter module):

When creating Shortcut stories, include source-specific context:

```markdown
## Evidence

### From Support (Intercom) - 12 conversations

- "I have to pick the board manually for every single pin" (jfahey, 2025-11-03)
- [More support quotes...]

### From Research (Coda) - 2 interviews

- **Pain Point**: "20 tab switches per minute between Pinterest and Tailwind"
- **Willingness to Pay**: "Would pay $10/mo extra for bulk board selector"
- From: AI Summary - jfahey.cpc@gmail.com (2025-10-15)

### Priority Signal

✅ **High Confidence** - Theme confirmed in both research interviews and support volume
```

**OUTPUT**: Shortcut stories with rich, source-attributed evidence

---

## PHASE 7: ONGOING SYNC STRATEGY (FUTURE)

**Not in MVP, but plan for:**

- Weekly Coda sync: Check for new AI Summaries and synthesis rows
- Incremental import: Only fetch pages modified since last sync
- Webhook option: If Coda supports webhooks for page updates
- Manual trigger: API endpoint to re-sync specific research studies

---

## SUCCESS CRITERIA

✓ Phase 0: Imported 50-100 themes from Coda with user quotes
✓ Phase 1: Database schema extended with data_source fields
✓ Phase 2: Source adapters normalize Coda + Intercom to common format
✓ Phase 3: Unified pipeline runs for both sources
✓ Phase 4: Theme aggregates track source_counts
✓ Phase 5: Cross-source analytics identify high-confidence themes
✓ Phase 6: Shortcut stories include evidence from both sources
✓ All changes backward compatible (existing Intercom pipeline unaffected)

---

## IF YOU GET STUCK

**Coda API Issues**:

- If page content returns empty, check if using `/content` endpoint (not just page metadata)
- If rate limited, add delays between requests
- If 404 errors, verify CODA_DOC_ID in .env is correct

**Schema Migration Issues**:

- If migration fails, check existing column names don't conflict
- Backup database before running migration
- Test migration on local dev database first

**Theme Extraction Low Quality**:

- If themes from Coda are too vague, parse AI Summary sections more granularly
- Extract user quotes separately from pain points
- Use section headers as theme type hints

**Source Counts Not Updating**:

- Verify JSONB syntax in SQL is correct
- Check that data_source parameter is being passed through pipeline
- Test JSONB operations in psql directly

---

## WHEN COMPLETE

**Verify ALL of these are true:**

- Coda import report generated with 50-100 themes
- Database schema updated with source tracking
- Both pipelines work: `--source intercom` and `--source coda`
- Theme aggregates show source_counts: `{"intercom": 45, "coda": 3}`
- Cross-source query identifies themes in both sources
- Shortcut story has evidence from both research and support
- No regression: Existing Intercom pipeline still works identically

**Then output**: <promise>MULTI_SOURCE_ARCHITECTURE_COMPLETE</promise>

---

## ITERATIVE REFINEMENT (IF NEEDED)

If any phase fails or produces low-quality results:

1. **Analyze the failure**:
   - What specific step failed?
   - What was the error or unexpected output?
   - Does the existing code need modification?

2. **Implement targeted fix**:
   - Update only the failing component
   - Document what changed and why
   - Re-run verification for that phase

3. **Re-test downstream phases**:
   - Ensure fix didn't break dependent phases
   - Update **ITERATIONS** counter in file header
   - Document progress

4. **Repeat** until all phases pass OR 5 refinement attempts completed

**If stuck after 5 attempts**: Output <promise>ARCHITECTURE_PLATEAU_REACHED</promise> and document:

- Which phase is blocking
- What was tried
- What specific help is needed (data access, schema design, API limits)
