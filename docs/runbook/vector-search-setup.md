# Vector Search Setup Runbook

Manual setup steps for FeedForward's vector search infrastructure.

## Prerequisites

- PostgreSQL 13+ with superuser access
- Python 3.10+
- OpenAI API key with embedding model access
- Database connection configured in `.env`

## Step 1: Install pgvector Extension

### Option A: Local Development (macOS)

```bash
# Install via Homebrew
brew install pgvector

# Connect to your database
psql -d feedforward

# Enable the extension
CREATE EXTENSION vector;
```

### Option B: Docker

```bash
# Use pgvector-enabled image
docker pull ankane/pgvector

# Or add to existing Postgres container
docker exec -it postgres psql -U postgres -d feedforward -c "CREATE EXTENSION vector;"
```

### Option C: Cloud (Supabase, Neon, etc.)

Most managed PostgreSQL services include pgvector. Enable via dashboard or:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Verify Installation

```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
-- Should return one row
```

## Step 2: Apply Database Migration

The migration creates the `research_embeddings` table with vector index.

```bash
# Apply migration
psql -d feedforward -f src/db/migrations/001_add_research_embeddings.sql
```

### Verify Table Exists

```sql
SELECT COUNT(*) FROM research_embeddings;
-- Should return 0 (empty table)
```

## Step 3: Configure Environment

Ensure `.env` contains:

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/feedforward

# OpenAI (for embedding generation)
OPENAI_API_KEY=sk-...
```

## Step 4: Run Initial Embeddings

Use the setup script:

```bash
# Full run (all sources)
python scripts/run_initial_embeddings.py

# Test with limited data first
python scripts/run_initial_embeddings.py --limit 10

# Verify setup only (no embedding generation)
python scripts/run_initial_embeddings.py --skip-embeddings
```

### Expected Output

```
Verifying pgvector extension...
✓ pgvector extension verified

Checking research_embeddings table...
✓ research_embeddings table exists

Running embedding pipeline...
  Status: completed
  Processed: 1250
  Updated: 1250
  Failed: 0
  Duration: 45.23s

Embedding Counts:
  coda_page: 500
  coda_theme: 250
  intercom: 500
  Total: 1250

Running 10 search queries...
  'pin not posting...' - 120ms
  'scheduling issues...' - 95ms
  ...

Performance Results:
  Queries: 10/10
  Average: 115ms
  P95: 180ms
  ✓ P95 within 500ms target

========================================
✓ Vector search setup complete!
========================================
```

## Step 5: Verify Search Works

Test via API:

```bash
curl -X GET "http://localhost:8000/api/research/search?q=pin+not+posting&limit=5"
```

Or via Python:

```python
from src.research.unified_search import UnifiedSearchService

service = UnifiedSearchService()
results = service.search(query="pin not posting", limit=5)
for r in results:
    print(f"{r.similarity:.2f} - {r.title}")
```

## Troubleshooting

### pgvector Extension Not Found

```
ERROR: extension "vector" is not available
```

**Fix**: Install pgvector binary (see Step 1).

### Migration Failed

```
ERROR: relation "research_embeddings" already exists
```

**Fix**: Table already created. Skip migration or drop and re-create:

```sql
DROP TABLE IF EXISTS research_embeddings;
```

### OpenAI API Error

```
ERROR: Batch embedding generation failed: AuthenticationError
```

**Fix**: Verify `OPENAI_API_KEY` in `.env` is valid.

### P95 Latency > 500ms

Possible causes:

1. **Cold cache**: Run 2-3 more query batches to warm up
2. **Index not built**: Check HNSW index exists:
   ```sql
   SELECT indexname FROM pg_indexes WHERE tablename = 'research_embeddings';
   ```
3. **Too many vectors**: Consider increasing `m` and `ef_construction` parameters

### No Embeddings Generated

```
Processed: 0, Updated: 0
```

Possible causes:

1. **Empty source data**: Check Coda and Intercom data exists in database
2. **Adapter error**: Run with `--verbose` flag for detailed logs
3. **Network issue**: Check OpenAI API connectivity

## Performance Targets

| Metric               | Target       | Action if Exceeded                    |
| -------------------- | ------------ | ------------------------------------- |
| P95 Search Latency   | < 500ms      | Check HNSW index, optimize parameters |
| Embedding Generation | < 100ms/item | Check OpenAI API tier limits          |
| Total Embeddings     | > 100        | Verify source data exists             |

## Maintenance

### Re-index Changed Content

```bash
# Only re-embed changed content (default)
python -m src.research.embedding_pipeline

# Force re-embed everything
python -m src.research.embedding_pipeline --force
```

### Monitor Embedding Counts

```sql
SELECT source_type, COUNT(*), MAX(updated_at)
FROM research_embeddings
GROUP BY source_type;
```

---

## Related Documentation

- [Architecture: Section 15 - Unified Research Search](../architecture.md#15-unified-research-search)
- [API: Research Endpoints](../api-reference.md#research)
- [Migration: 001_add_research_embeddings.sql](../../src/db/migrations/001_add_research_embeddings.sql)
