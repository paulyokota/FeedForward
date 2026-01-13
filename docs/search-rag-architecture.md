# Search/RAG Integration Architecture

## Overview

This document presents architectural options for leveraging FeedForward's Coda research data through search and RAG (Retrieval-Augmented Generation) capabilities.

**Goal**: Enable PMs and product teams to discover research insights AND integrate them into the FeedForward pipeline for theme extraction, story creation, and evidence enrichment.

**Existing Assets**:

- SQLite database (20MB) with FTS5 full-text search: `data/coda_raw/coda_content.db`
- 1,271 indexed pages (~12MB of text content)
- 4,682 Coda conversations loaded into PostgreSQL with `data_source='coda'`
- 14,769 extracted themes from Coda tables
- Markdown files (15MB) suitable for embedding

---

## Option A: FTS5 Search Service (Lightweight) - NOT RECOMMENDED

> **Note**: This option was evaluated but rejected. Multi-source requirement (Intercom + Coda + future sources) requires unified embedding approach. Retained for reference.

**Approach**: Expose the existing SQLite FTS5 database through a dedicated search API endpoint.

### Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Webapp (Next.js)  │────►│   FastAPI Backend   │────►│   SQLite FTS5       │
│                     │     │   /api/research/*   │     │   coda_content.db   │
│  - Search bar       │     │                     │     │                     │
│  - Results view     │     │  - /search          │     │  - pages_fts table  │
│  - Snippet display  │     │  - /page/{id}       │     │  - Full-text index  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### Components

| Component               | Purpose             | Location                                         |
| ----------------------- | ------------------- | ------------------------------------------------ |
| `ResearchSearchService` | SQLite FTS5 wrapper | `src/research/search_service.py` (NEW)           |
| Research API router     | REST endpoints      | `src/api/routers/research.py` (NEW)              |
| Search UI component     | Frontend search     | `webapp/src/components/ResearchSearch.tsx` (NEW) |

### API Endpoints

```python
# New endpoints in src/api/routers/research.py
GET /api/research/search?q={query}&limit=20
    # Returns: [{ id, title, snippet, score, url }]

GET /api/research/page/{canvas_id}
    # Returns: { id, title, content, metadata }

GET /api/research/stats
    # Returns: { total_pages, total_chars, last_indexed }
```

### Implementation Complexity: **Low**

| Factor         | Assessment                               |
| -------------- | ---------------------------------------- |
| New code       | ~200 lines Python, ~150 lines TypeScript |
| Dependencies   | None (SQLite is built-in)                |
| Infrastructure | No new services required                 |
| Data pipeline  | Already complete                         |
| Maintenance    | Minimal - static dataset                 |

### Value Delivered: **Medium-High**

- **PM Search**: "What did users say about scheduling?" returns relevant research quotes
- **Instant Results**: FTS5 provides sub-100ms queries
- **No API costs**: No embedding generation or LLM inference needed
- **Existing Data**: Uses already-extracted content

### Tradeoffs

| Pro                               | Con                                            |
| --------------------------------- | ---------------------------------------------- |
| Very fast to implement (1-2 days) | Keyword-based only - no semantic understanding |
| No additional costs               | Won't find conceptually similar content        |
| Reliable and simple               | Limited ranking sophistication                 |
| Works offline                     | Single data source (Coda only)                 |

---

## Option B: Vector Search with Embeddings (Medium)

**Approach**: Generate embeddings for Coda content and enable semantic search via pgvector.

### Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Webapp (Next.js)  │────►│   FastAPI Backend   │────►│   PostgreSQL        │
│                     │     │   /api/research/*   │     │   + pgvector        │
│  - Semantic search  │     │                     │     │                     │
│  - Similar themes   │     │  - /search          │     │  - embeddings table │
│  - "More like this" │     │  - /similar/{id}    │     │  - 1536-dim vectors │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │   OpenAI API        │
                            │   text-embedding-3  │
                            │   (one-time batch)  │
                            └─────────────────────┘
```

### Components

| Component             | Purpose          | Location                                         |
| --------------------- | ---------------- | ------------------------------------------------ |
| Embedding pipeline    | Generate vectors | `src/research/embedding_pipeline.py` (NEW)       |
| `VectorSearchService` | pgvector queries | `src/research/vector_service.py` (NEW)           |
| Research API router   | REST endpoints   | `src/api/routers/research.py` (NEW)              |
| Search UI             | Frontend         | `webapp/src/components/ResearchSearch.tsx` (NEW) |

### Database Schema

```sql
-- New table for research embeddings
CREATE TABLE research_embeddings (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,         -- 'coda_page', 'coda_theme', etc.
    source_id TEXT NOT NULL,           -- canvas_id or theme_id
    content_hash TEXT NOT NULL,        -- For dedup/update detection
    title TEXT,
    content TEXT NOT NULL,
    embedding vector(1536),            -- OpenAI text-embedding-3-small
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(source_type, source_id)
);

-- HNSW index: better for <100k rows, no training required
CREATE INDEX ON research_embeddings USING hnsw (embedding vector_cosine_ops);

-- Source type index for filtered queries
CREATE INDEX idx_research_source_type ON research_embeddings(source_type);
```

### API Endpoints

```python
GET /api/research/search?q={query}&limit=20&mode=semantic
    # Uses embedding similarity search

GET /api/research/similar/{source_type}/{source_id}?limit=10
    # "More like this" - finds related research

POST /api/research/embed
    # Admin: Trigger embedding generation for new content
```

### Implementation Complexity: **Medium**

| Factor         | Assessment                                       |
| -------------- | ------------------------------------------------ |
| New code       | ~400 lines Python, ~200 lines TypeScript         |
| Dependencies   | pgvector extension, OpenAI embeddings            |
| Infrastructure | PostgreSQL with pgvector                         |
| Data pipeline  | One-time embedding batch (~$0.50 for 1.2k pages) |
| Maintenance    | Re-embed when content changes                    |

### Value Delivered: **High**

- **Semantic Search**: "users frustrated with posting workflow" finds related content even without exact keywords
- **Cross-Reference**: Find support tickets related to research insights
- **"Similar Research"**: Click any theme to see related research
- **Future-Proof**: Embeddings enable RAG context augmentation

### Tradeoffs

| Pro                            | Con                              |
| ------------------------------ | -------------------------------- |
| Semantic understanding         | Requires pgvector setup          |
| "More like this" functionality | One-time embedding cost (~$0.50) |
| Enables RAG integration        | Query latency (~100-300ms)       |
| Works across data sources      | More complex to maintain         |

---

## Option C: Full RAG Pipeline (High Investment)

**Approach**: LLM-powered research assistant that answers questions using Coda research as context.

### Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Webapp (Next.js)  │────►│   FastAPI Backend   │────►│   RAG Pipeline      │
│                     │     │   /api/research/*   │     │                     │
│  - Chat interface   │     │                     │     │  1. Embed query     │
│  - Q&A with sources │     │  - /ask             │     │  2. Retrieve top-k  │
│  - Evidence links   │     │  - /search          │     │  3. LLM synthesis   │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                       │                          │
                                       │                          ▼
                                       │               ┌─────────────────────┐
                                       │               │   OpenAI API        │
                                       │               │   - embeddings      │
                                       └──────────────►│   - gpt-4o-mini     │
                                                       └─────────────────────┘
```

### Components

| Component           | Purpose              | Location                                   |
| ------------------- | -------------------- | ------------------------------------------ |
| Embedding pipeline  | Generate vectors     | `src/research/embedding_pipeline.py` (NEW) |
| Retriever           | Find relevant chunks | `src/research/retriever.py` (NEW)          |
| RAG orchestrator    | Query → Answer       | `src/research/rag_service.py` (NEW)        |
| Research API router | REST endpoints       | `src/api/routers/research.py` (NEW)        |
| Chat UI             | Frontend             | `webapp/src/app/research/page.tsx` (NEW)   |

### API Endpoints

```python
POST /api/research/ask
    # Body: { question: str, max_sources: int }
    # Returns: { answer: str, sources: [{ title, excerpt, url, score }] }

GET /api/research/search?q={query}&mode=hybrid
    # Combines FTS + semantic search

POST /api/research/contextualize
    # Enrich theme extraction with research context
```

### Implementation Complexity: **High**

| Factor         | Assessment                               |
| -------------- | ---------------------------------------- |
| New code       | ~800 lines Python, ~400 lines TypeScript |
| Dependencies   | pgvector, OpenAI embeddings + chat       |
| Infrastructure | PostgreSQL + pgvector + OpenAI           |
| Data pipeline  | Chunking, embedding, retrieval tuning    |
| Maintenance    | Ongoing: rerank tuning, prompt iteration |

### Value Delivered: **Very High**

- **Natural Language Q&A**: "What do users think about the scheduling UX?" gets synthesized answer with citations
- **Context Augmentation**: Theme extraction prompts enriched with relevant research
- **Evidence Discovery**: Auto-suggest research quotes when creating stories
- **Research Dashboard**: Analytics on research coverage by product area

### Tradeoffs

| Pro                           | Con                           |
| ----------------------------- | ----------------------------- |
| Most powerful user experience | Highest implementation effort |
| Enables context augmentation  | Ongoing API costs (per query) |
| Natural language interface    | Requires prompt tuning        |
| Synthesized answers           | Latency (~2-5s per query)     |

---

## Recommendation

### Revised: Start with Phase 2 (Vector Search)

**Rationale**: Multi-source requirement (Intercom + Coda + future sources) means FTS5-only won't work:

- Coda data is in SQLite
- Intercom data is in PostgreSQL
- Need unified search across heterogeneous sources
- Embedding-based approach provides source-agnostic abstraction

**Cost**: ~$0.78 one-time for embeddings (negligible)

### Architecture: Source-Agnostic Search

```
┌─────────────────────────────────────────────────────────────────┐
│                     Unified Search Service                       │
│                  src/research/unified_search.py                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 research_embeddings (PostgreSQL)                 │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │ source_type │ source_id   │ content     │ embedding   │      │
│  ├─────────────┼─────────────┼─────────────┼─────────────┤      │
│  │ coda_page   │ canvas_123  │ "User said  │ [0.12, ...] │      │
│  │ coda_theme  │ theme_456   │ "Pain point │ [0.34, ...] │      │
│  │ intercom    │ conv_789    │ "Customer:  │ [0.56, ...] │      │
│  │ {future}    │ {id}        │ {content}   │ {vector}    │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### Source Adapter Pattern

```python
# src/research/adapters/base.py
class SearchSourceAdapter(ABC):
    """Base class for search source adapters"""

    @abstractmethod
    def get_source_type(self) -> str:
        """Returns source identifier (e.g., 'coda_page', 'intercom')"""
        pass

    @abstractmethod
    def extract_content(self, source_id: str) -> SearchableContent:
        """Extract content for embedding from source"""
        pass

    @abstractmethod
    def get_source_url(self, source_id: str) -> str:
        """Returns URL to view original source"""
        pass

# Implementations:
# - src/research/adapters/coda_adapter.py
# - src/research/adapters/intercom_adapter.py
# - src/research/adapters/{future}_adapter.py
```

### Phase 2 Deliverables (Revised)

1. **Unified embeddings table** in PostgreSQL with pgvector
2. **Source adapter pattern** for Coda, Intercom, future sources
3. **Embedding pipeline** that processes all sources
4. **Dedicated search page** at `/research` in webapp
5. **API endpoints** for search, similar, and source filtering

### Phase 3: RAG Pipeline - **Future**

**Trigger**: When users request:

- "Summarize what users think about X"
- Context augmentation for theme extraction
- Automated evidence attachment to stories

**Prerequisites**:

- Phase 2 embeddings in place
- Clear use cases validated
- Budget approval for ongoing LLM costs (~$0.50-1/week)

---

## Pipeline Integration Design

The embedding infrastructure serves three pipeline use cases beyond search:

### Use Case 1: Theme Extraction Context Augmentation

**When**: Extracting themes from new Intercom conversations

**How**: Before calling the LLM for theme extraction, retrieve relevant research context

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  New Intercom       │────►│  Embedding Lookup   │────►│  Theme Extractor    │
│  Conversation       │     │  (find similar      │     │  (with research     │
│                     │     │   research)         │     │   context in prompt)│
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

**Implementation**:

```python
# src/theme_extractor.py (enhanced)
class ThemeExtractor:
    def __init__(self, search_service: UnifiedSearchService):
        self.search_service = search_service

    def extract_with_context(self, conversation: Conversation) -> ThemeResult:
        # 1. Find relevant research (Coda only, exclude Intercom to avoid circular)
        research_context = self.search_service.search(
            query=conversation.customer_text[:500],
            source_types=["coda_page", "coda_theme"],
            limit=3
        )

        # 2. Build enriched prompt with research context
        prompt = self._build_prompt(conversation, research_context)

        # 3. Extract theme with richer context
        return self._call_llm(prompt)
```

**Value**: Themes extracted with awareness of known research insights. If users mentioned "scheduling confusion" in research, the extractor can recognize similar patterns in support tickets.

### Use Case 2: Story Evidence Enrichment

**When**: Creating or viewing stories

**How**: Automatically suggest relevant research as supporting evidence

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Story Created      │────►│  Embedding Lookup   │────►│  Evidence Suggested │
│  (from theme group) │     │  (find matching     │     │  (research quotes   │
│                     │     │   research)         │     │   auto-attached)    │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

**Implementation**:

```python
# src/story_tracking/services/evidence_service.py (enhanced)
class EvidenceService:
    def suggest_research_evidence(self, story: Story) -> List[SuggestedEvidence]:
        """Find research that supports this story's theme"""
        # Embed story description + existing evidence
        query = f"{story.title} {story.description}"

        # Search Coda research only
        matches = self.search_service.search(
            query=query,
            source_types=["coda_page", "coda_theme"],
            limit=5,
            min_similarity=0.7  # High threshold for relevance
        )

        return [
            SuggestedEvidence(
                source_type=m.source_type,
                source_id=m.source_id,
                title=m.title,
                excerpt=m.snippet,
                url=m.url,
                similarity=m.similarity,
                status="suggested"  # PM can accept/reject
            )
            for m in matches
        ]
```

**Value**: Stories automatically enriched with research quotes. PMs see "3 research insights support this" and can one-click attach them.

### Pipeline Integration Summary

| Use Case             | Trigger             | Input                     | Output                      | Phase   |
| -------------------- | ------------------- | ------------------------- | --------------------------- | ------- |
| Context Augmentation | Theme extraction    | Conversation text         | Research context for prompt | Phase 2 |
| Evidence Enrichment  | Story creation/view | Story title + description | Suggested research evidence | Phase 2 |

_Note: Cross-source signal detection deferred - will implement if PMs request after Phase 2 ships._

### Integration Points (Files to Modify)

| File                                              | Change                            | Purpose              |
| ------------------------------------------------- | --------------------------------- | -------------------- |
| `src/theme_extractor.py`                          | Add `search_service` dependency   | Context augmentation |
| `src/story_tracking/services/evidence_service.py` | Add `suggest_research_evidence()` | Evidence enrichment  |
| `src/story_formatter.py`                          | Format suggested evidence         | Display in stories   |
| `webapp/src/app/story/[id]/page.tsx`              | Show suggested evidence           | PM acceptance UI     |

---

## Interface Contracts

### SearchableContent (Source Adapter Output)

```python
class SearchableContent(BaseModel):
    """Content extracted from any source for embedding"""
    source_type: str           # 'coda_page', 'coda_theme', 'intercom', etc.
    source_id: str             # Unique ID within source
    title: str
    content: str               # Text to embed
    url: str                   # Link to original
    metadata: dict = {}        # Source-specific metadata
```

### UnifiedSearchResult (Phase 2)

```python
class UnifiedSearchResult(BaseModel):
    id: str                    # embedding table ID
    source_type: str           # 'coda_page', 'coda_theme', 'intercom'
    source_id: str             # Original source ID
    title: str
    snippet: str               # ~200 char excerpt
    similarity: float          # Cosine similarity 0-1
    url: str                   # Link to source
    metadata: dict             # Source-specific (participant, conversation_id, etc.)
```

### UnifiedSearchRequest (Phase 2)

```python
class UnifiedSearchRequest(BaseModel):
    query: str
    limit: int = 20
    offset: int = 0
    source_types: Optional[List[str]] = None  # Filter: ['coda_page', 'intercom']
    min_similarity: float = 0.5               # Threshold for relevance
```

### SimilarContentRequest (Phase 2)

```python
class SimilarContentRequest(BaseModel):
    source_type: str           # Source of the reference item
    source_id: str             # ID of the reference item
    limit: int = 10
    exclude_same_source: bool = False  # Cross-source discovery
```

---

## Security Considerations

### Authentication & Authorization

| Endpoint                                | Auth Required  | Role                         |
| --------------------------------------- | -------------- | ---------------------------- |
| `GET /api/research/search`              | Yes (any user) | Read access to search        |
| `GET /api/research/similar/*`           | Yes (any user) | Read access to search        |
| `GET /api/stories/*/suggested-evidence` | Yes (any user) | Read access to stories       |
| `POST /api/research/reindex`            | Yes (admin)    | Triggers embedding API calls |

**Implementation**: Use existing FastAPI authentication middleware. Admin endpoints check `user.is_admin` before processing.

### Input Validation

| Parameter        | Validation                            | Rationale                                |
| ---------------- | ------------------------------------- | ---------------------------------------- |
| `query`          | Max 500 chars, sanitize special chars | Prevent injection, limit embedding costs |
| `limit`          | Max 100, default 20                   | Prevent memory exhaustion                |
| `min_similarity` | Server-enforced minimum 0.3           | Prevent data exposure via similarity=0   |
| `source_types`   | Validate against known types          | Prevent injection                        |

### Rate Limiting

- Search endpoints: 60 requests/minute per user
- Admin endpoints: 5 requests/minute per user

---

## Configuration

All tunable parameters should be defined in `config/research_search.yaml`:

```yaml
# config/research_search.yaml
search:
  default_limit: 20
  max_limit: 100
  default_min_similarity: 0.5
  server_min_similarity: 0.3 # Cannot be overridden by client

context_augmentation:
  max_results: 3 # Research results to inject into theme extraction
  max_tokens: 500 # Token budget for research context in prompts

evidence_suggestion:
  min_similarity: 0.7 # Threshold for suggesting evidence
  max_suggestions: 5 # Max suggestions per story

embedding:
  model: "text-embedding-3-large"
  dimensions: 1536
  batch_size: 100 # Records per embedding API call
```

---

## Error Handling

### Graceful Degradation

The search service should fail gracefully without breaking dependent features:

```python
# src/research/unified_search.py
class UnifiedSearchService:
    def search(self, query: str, **kwargs) -> List[UnifiedSearchResult]:
        try:
            embedding = self._get_embedding(query)
            return self._vector_search(embedding, **kwargs)
        except EmbeddingServiceError as e:
            logger.warning(f"Embedding service unavailable: {e}")
            return []  # Return empty, don't crash caller
        except DatabaseError as e:
            logger.error(f"Database error in search: {e}")
            return []
```

### Context Augmentation Fallback

Theme extraction must work even if search service is down:

```python
# src/theme_extractor.py
def extract_with_context(self, conversation: Conversation) -> ThemeResult:
    research_context = []
    if self.search_service:
        try:
            research_context = self.search_service.search(...)
        except Exception as e:
            logger.warning(f"Research context unavailable: {e}")
            # Continue without context - extraction still works

    return self._extract(conversation, research_context)
```

### Error Response Contract

```python
class SearchErrorResponse(BaseModel):
    error: str
    code: Literal["EMBEDDING_UNAVAILABLE", "DATABASE_ERROR", "RATE_LIMITED"]
    retry_after: Optional[int] = None  # Seconds, for rate limiting
```

---

## Agent Assignments (Phase 2: Multi-Source Vector Search)

### Marcus (Backend)

**Owns**:

- `src/research/unified_search.py` (NEW) - Core search service
- `src/research/embedding_pipeline.py` (NEW) - Batch embedding generation
- `src/research/adapters/` (NEW) - Source adapter implementations
- `src/api/routers/research.py` (NEW) - REST endpoints
- Database migration for `research_embeddings` table
- Integration hooks into existing pipeline

**Must not touch**: `webapp/` files

**Acceptance Criteria**:

Search Infrastructure:

- [ ] pgvector extension enabled in PostgreSQL
- [ ] `research_embeddings` table with source abstraction
- [ ] Adapters for `coda_page`, `coda_theme`, `intercom` sources
- [ ] `GET /api/research/search` with source filtering
- [ ] `GET /api/research/similar/{source_type}/{id}` endpoint
- [ ] `POST /api/research/reindex` for admin re-embedding
- [ ] Query latency <300ms for semantic search

Pipeline Integration:

- [ ] `ThemeExtractor` accepts optional `search_service` for context augmentation
- [ ] `EvidenceService.suggest_research_evidence()` method
- [ ] `GET /api/stories/{id}/suggested-evidence` endpoint

Testing:

- [ ] Tests for each adapter and search service
- [ ] Tests for pipeline integration (context augmentation, evidence suggestion)

### Sophia (Frontend)

**Owns**:

- `webapp/src/app/research/page.tsx` (NEW) - Dedicated search page
- `webapp/src/components/ResearchSearch.tsx` (NEW) - Search input
- `webapp/src/components/SearchResults.tsx` (NEW) - Results display
- `webapp/src/components/SourceFilter.tsx` (NEW) - Filter by source
- `webapp/src/components/SuggestedEvidence.tsx` (NEW) - Evidence suggestions on story page

**Must not touch**: `src/` Python files

**Acceptance Criteria**:

Search Page:

- [ ] Dedicated `/research` page in webapp navigation
- [ ] Search input with debounced queries (300ms)
- [ ] Source type filter chips (All, Coda Research, Intercom Support)
- [ ] Results display with title, snippet, source badge, link
- [ ] "More like this" button on each result
- [ ] Loading and empty states
- [ ] Keyboard navigation support

Story Page Integration:

- [ ] "Suggested Research" section on story detail page
- [ ] Shows suggested evidence with similarity scores
- [ ] Accept/Reject buttons for each suggestion

---

## Open Questions

1. **Where should search live in the UI?**
   - Global search bar? Dedicated page? Both?

2. **Should search span Intercom + Coda?**
   - Phase 1: Coda only
   - Future: Unified search across all sources

3. **Embedding model choice (Phase 2)**
   - OpenAI text-embedding-3-small (1536 dim) - recommended
   - OpenAI text-embedding-3-large (3072 dim) - higher quality
   - Open source alternatives (if cost-sensitive)

4. **Chunking strategy (Phase 2/3)**
   - Page-level (current) vs paragraph-level
   - Overlap strategy for long documents

---

## Alternatives Considered

### Alternative: External Search Service (Algolia, Typesense)

**Why Rejected**:

- Additional infrastructure and cost
- Dataset is small (20MB) - FTS5 handles this easily
- No clear advantage over built-in solutions

### Alternative: Embedding-First (Skip FTS5)

**Why Rejected**:

- Higher upfront cost
- Slower initial delivery
- FTS5 validates the need before investing

### Alternative: LangChain/LlamaIndex

**Why Rejected**:

- Overkill for our use case
- Adds framework dependency
- Custom implementation is simpler and more controllable

---

## Success Criteria

| Phase   | Metric              | Target                |
| ------- | ------------------- | --------------------- |
| Phase 1 | Search queries/week | >10 (proves adoption) |
| Phase 1 | Query latency       | <100ms p95            |
| Phase 2 | Semantic match rate | >80% relevant top-3   |
| Phase 3 | RAG answer quality  | >4/5 user rating      |
