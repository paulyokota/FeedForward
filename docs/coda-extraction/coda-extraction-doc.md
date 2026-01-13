# Coda Full Extraction Strategy

## Philosophy: Extract Everything, Decide Later

This extraction strategy captures **all** Coda content as raw data, preserving maximum flexibility for downstream use. The extracted data becomes a **peer source** alongside Intercom data in the FeedForward pipeline.

**Core Principles:**

- Extract all content types (pages, tables, hierarchy)
- Preserve original structure and metadata
- Store raw data for multiple potential uses
- Defer filtering/classification decisions to processing phase
- Treat Coda themes as equal weight to Intercom themes

## What Gets Extracted

| Content Type       | Method     | Output Format   | Value                          |
| ------------------ | ---------- | --------------- | ------------------------------ |
| **All Pages**      | Playwright | Markdown + JSON | Page content, hierarchy        |
| **All Tables**     | Coda API   | JSON            | Structured row data            |
| **Page Hierarchy** | Coda API   | JSON            | Navigation structure           |
| **Metadata**       | Both       | JSON            | Timestamps, IDs, relationships |

### Content Types in Detail

**Pages (via Playwright):**

- AI Summaries (researcher-curated interview insights)
- Discovery Learnings (synthesized product insights)
- Research Questions (priorities and open questions)
- Participant pages (interview session notes)
- Research Plans, Moderator Guides (methodology docs)
- Any other page with text content

**Tables (via Coda API):**

- All tables, not just "research" keyword matches
- Full row data with column names
- Preserves relationships between tables
- Captures timestamps for freshness tracking

**Hierarchy (via Coda API):**

- Page parent-child relationships
- Section/folder structure
- Navigation context for understanding content organization

## Extraction Methods

### Method 1: Playwright (Page Content)

- Opens Coda in browser for authentication
- Extracts rendered page content as Markdown
- Preserves heading hierarchy and formatting
- Captures content that may not be API-accessible
- See `coda-extraction-pmt.md` for workflow

### Method 2: Coda API (Structured Data)

- Uses `src/coda_client.py` for API access
- Extracts tables with full schema
- Gets page metadata and hierarchy
- Rate-limited but comprehensive
- See `src/adapters/coda_adapter.py` for implementation

### Recommended: Hybrid Approach

1. **API first**: Extract all tables and page metadata
2. **Playwright second**: Extract page content for rich text
3. **Merge**: Combine into unified raw dataset

## Output Structure

```
data/coda_raw/
├── extraction_manifest.json    # What was extracted, when, how
├── pages/
│   ├── page_{id}.md           # Rendered content
│   └── page_{id}.meta.json    # Page metadata
├── tables/
│   ├── table_{id}.json        # Full table data with rows
│   └── table_{id}.schema.json # Column definitions
├── hierarchy.json              # Page tree structure
└── README.md                   # Extraction notes
```

### Manifest Format

```json
{
  "extraction": {
    "timestamp": "2026-01-12T10:00:00Z",
    "doc_id": "c4RRJ_VLtW",
    "doc_name": "Tailwind Research Ops",
    "methods": ["playwright", "api"]
  },
  "content": {
    "pages": {
      "total": 72,
      "extracted": 72,
      "with_content": 45
    },
    "tables": {
      "total": 100,
      "extracted": 100,
      "with_rows": 67
    }
  },
  "files": {
    "pages_dir": "pages/",
    "tables_dir": "tables/",
    "total_size_bytes": 2456789
  }
}
```

## Integration with FeedForward

### As Peer Data Source

Coda data enters the pipeline alongside Intercom as an equal source:

```
Raw Data Sources          Normalization           Pipeline
     │                         │                     │
  Intercom ─────────────► NormalizedConversation ──┤
     │                         │                     │
  Coda Raw ─────────────► NormalizedConversation ──┼──► Classification
     │                         │                     │        │
     └── pages                 │                     │        ▼
     └── tables                │                     │   Theme Extraction
     └── hierarchy             │                     │        │
                               │                     │        ▼
                               │                     │   Story Grouping
                               │                     │        │
                               │                     └──► Stories (multi-source)
```

### Downstream Use Cases

From the same raw extraction, support:

1. **Theme/Story Source** - Coda insights become themes alongside Intercom
2. **Story Enrichment** - Link Coda research to Intercom-sourced stories
3. **Validation Signal** - Researcher insights validate user-reported issues
4. **Historical Context** - Archive of past research for reference
5. **Vocabulary Seeding** - Extract terminology for theme vocabulary

### Normalization Strategy

Raw Coda content normalizes to `NormalizedConversation` format:

- `id`: `coda_page_{page_id}` or `coda_row_{table_id}_{row_id}`
- `text`: Rendered content or concatenated row values
- `data_source`: `"coda"`
- `source_metadata`: Original structure, type, hierarchy position
- `url`: Deep link to Coda location

## Freshness & Staleness

**Coda research is point-in-time:**

- Interviews conducted months ago
- Synthesized insights reflect past state
- May describe problems already fixed

**Handling staleness:**

- Track `extraction_timestamp` in all outputs
- Compare against Intercom volume for same themes
- Mark themes with "last evidence date"
- Allow filtering by recency in pipeline

**Refresh cadence:**

- One-time extraction for historical archive
- Re-extract quarterly or when major research drops
- Git diff shows what changed between extractions

## Quality Considerations

### Signal Strength

- Coda = researcher-curated, high confidence, low volume
- Intercom = raw user voice, variable signal, high volume
- Combined = strongest evidence (validated + volume)

### Attribution

- Clear `data_source` tagging throughout pipeline
- Stories show which evidence came from which source
- "Researcher observed X" vs "User reported Y"

### Deduplication

- Same pain point may appear in both sources
- Use semantic similarity to detect overlap
- Merge evidence, don't double-count themes

## Files in This Directory

| File                     | Purpose                               |
| ------------------------ | ------------------------------------- |
| `coda-extraction-doc.md` | This strategy document                |
| `coda-extraction-pmt.md` | Playwright extraction workflow prompt |

## Related Code

| File                              | Purpose                              |
| --------------------------------- | ------------------------------------ |
| `scripts/coda_full_extract.js`    | **Standalone Playwright extraction** |
| `src/coda_client.py`              | Coda API client                      |
| `src/adapters/coda_adapter.py`    | Normalizes Coda data for pipeline    |
| `scripts/load_coda_json.py`       | Loads extracted JSON into DB         |
| `scripts/import_coda_research.py` | Research-specific import logic       |

## Standalone Extraction Script

For independent, resumable extraction without Claude Code token usage:

```bash
# Run the standalone extraction script
node scripts/coda_full_extract.js
```

**Features**:

- Launches Chromium with persistent profile (auth only needed once)
- Recursively discovers all pages from navigation and content links
- Extracts content with scroll-to-load for lazy content
- Resumable via manifest (skips already-extracted pages)
- Logs progress to console and `data/coda_raw/extraction.log`
- Saves pages to `data/coda_raw/pages/` with metadata

**Configuration** (in `scripts/coda_full_extract.js`):

- `LOGIN_TIMEOUT_MS`: Time to wait for authentication (default 3min)
- `PAGE_TIMEOUT_MS`: Navigation timeout per page (default 45s)
- `VIEWPORT`: Browser window size (default 1920x1080)
- `MIN_CONTENT_LENGTH`: Skip pages with less content (default 50 chars)

**Web UI**: A control panel is available in the Story Tracking webapp at `/tools/extraction`.

## Next Steps

1. **Run full extraction** - `node scripts/coda_full_extract.js`
2. **Store in `data/coda_raw/`** - Version controlled archive
3. **Review extraction quality** - Spot check content
4. **Update adapter** - Expand `coda_adapter.py` to handle all content types
5. **Pipeline integration** - Run through classification as peer source
