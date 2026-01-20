# Vector Integration Architecture Plan

## Overview

Goal: maximize analyst UX value first, then improve pipeline accuracy and story grouping using the existing pgvector-backed research index. This plan is architecture-only; no implementation changes are included.

## Objectives

- Analyst UX: fast, trustworthy semantic search and evidence discovery in the webapp.
- RAG: ground theme extraction and story grouping with retrieved evidence.
- Pipeline lift: measurable accuracy improvements on a 30-day Intercom sample.

## Non-Goals (for this phase)

- Replacing the current classification or theme extraction stack.
- Building a new vector store outside PostgreSQL/pgvector.
- External sharing or privacy-hardening (internal tool; PII allowed).

## Current Capabilities (baseline)

- Embedding pipeline: `src/research/embedding_pipeline.py`
- Vector search service: `src/research/unified_search.py`
- API endpoints: `src/api/routers/research.py` (`/search`, `/similar`, `/stats`, `/reindex`)
- Storage: `research_embeddings` with HNSW index in `src/db/migrations/001_add_research_embeddings.sql`

## Proposed Architecture

### Data Sources and Indexing

Embed and index both Intercom and Coda content in the unified `research_embeddings` table:

- Intercom: cleaned conversation text + metadata (id, created_at, product area hints, source URL).
- Coda: pages and themes via existing adapters.

Optional extension:

- Theme-level embeddings: store derived theme summaries for theme-to-theme similarity and grouping.

Indexing cadence:

- Nightly batch with change detection using `content_hash`.
- Manual admin reindex via `POST /api/research/reindex`.

### Retrieval Layer

Core retrieval functions:

- Semantic search by query (`/api/research/search`).
- "More like this" by source reference (`/api/research/similar/{source_type}/{source_id}`).

Retrieval parameters (initial defaults):

- `top_k`: 8 (display 5, reserve 3 for prompt use)
- `min_similarity`: 0.5 (hard floor at 0.3)
- `max_tokens`: 800 combined for retrieved snippets
- `source_types`: default to both `intercom` + `coda_*`, user-filterable

### RAG Integration Points

1) Theme extraction (primary)
- Use vector retrieval to fetch top-K related items for each conversation.
- Inject summaries/snippets into the extraction prompt with citations.
- Gate by similarity: only include retrieved items if at least 2 results exceed 0.6.

2) Story grouping (secondary)
- Use similarity to propose candidate clusters before LLM grouping.
- Provide "related stories" suggestions for PM review.

### Webapp UX (analyst-first)

1) Global Search Page
- Search bar with filters: source type, date range, product area.
- Results list with similarity score, snippet, and metadata.
- Action buttons: "open source", "copy evidence", "add to story".

2) Story Evidence Panel
- On story detail page, show "Suggested Evidence" from vector search.
- Provide quick accept/reject to capture relevance signal.

3) "More Like This"
- From any result, open similar items (same or cross-source).

## API Additions (minimal)

Use existing endpoints first. If UX requires aggregation, add a thin endpoint:

- `GET /api/research/evidence?story_id=...`
  - Returns curated, de-duplicated results across sources.
  - Uses `UnifiedSearchService` under the hood.

## Prompt Shapes (RAG)

Embedding-retrieved evidence format (example):

```
Evidence:
1) [intercom:123] Similarity 0.78
   Snippet: "Scheduler shows success but pins never post..."
2) [coda_page:abc] Similarity 0.71
   Snippet: "Known issue: scheduler posts not firing..."
```

Rules:

- Keep evidence short (1-3 sentences).
- Include source and similarity for traceability.
- Do not include if <0.6 similarity unless explicitly requested.

## Evaluation Plan (30-day Intercom sample)

Sample:

- 30-day Intercom data window.
- 100 conversation sample for theme extraction evaluation.

Metrics:

- Evidence relevance@5 >= 70% (analyst labeling).
- Theme match precision +10% vs baseline extraction (aspirational but achievable).
- PM acceptance rate for suggested evidence +15%.

Labeling:

- Analysts label relevance and theme correctness.
- Store labels for future active learning (optional).

## Cost & Performance Estimates

Embedding cost (one-time, estimate):

- 2,000 convs * 1,200 tokens = 2.4M tokens
- $0.25 to $0.50 (range depends on embedding price)

Latency:

- Embedding query latency dominated by OpenAI call (tens to hundreds of ms).
- Vector search in pgvector HNSW: low tens of ms per query.

## Rollout Plan

Phase 1: Analyst UX
- Webapp global search + story evidence panel.
- Use existing endpoints; validate evidence relevance@5.

Phase 2: RAG for theme extraction
- Add retrieval context to prompts.
- Compare precision vs baseline on 30-day sample.

Phase 3: Story grouping suggestions
- Similarity-based cluster hints for PM review.
- Track acceptance rate improvements.

Go/No-Go Gates:

- Evidence relevance@5 >= 70%
- Theme match precision +10% or no regression with better analyst UX

## Risks & Mitigations

- Prompt bloat: cap tokens and gate by similarity.
- Retrieval noise: enforce minimum similarity and source filters.
- Index drift: nightly reindex with content_hash to keep embeddings fresh.

## Operational Checklist

- Ensure pgvector extension enabled in production DB.
- Monitor `/api/research/stats` for embedding coverage and staleness.
- Track search latency and error rates in logs.
