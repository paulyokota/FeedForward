# Issue #75: Dry Run Visibility Architecture

## Overview

**Problem**: When `dry_run=true`, classification results are logged to stdout but not accessible for preview. Users can't see what would have been stored.

**Goal**: Expose dry run results via API and UI so users can preview classification output before committing to production runs.

## Design Decision: Memory-Based Preview Storage

### Options Considered

| Option                      | Pros                            | Cons                                 |
| --------------------------- | ------------------------------- | ------------------------------------ |
| **A. In-memory dict**       | Simple, no DB changes, fast     | Lost on server restart, memory usage |
| **B. Temp table**           | Persists briefly, SQL queryable | Schema changes, cleanup complexity   |
| **C. Extend pipeline_runs** | Single source of truth          | Large JSONB column, schema migration |

**Chosen**: **Option A - In-memory dict** with automatic cleanup.

**Rationale**:

- Dry runs are ephemeral by design - users want to see results immediately, then decide
- Preview data is only needed for the duration of a user session (minutes, not hours)
- Memory overhead is bounded (max ~100 conversations \* ~1KB = ~100KB per run)
- No schema migration required
- Simplest implementation with lowest risk

### Implementation Details

1. **Storage**: Module-level dict in `pipeline.py`, keyed by `run_id`
2. **Lifecycle**: Stored on dry run completion, auto-cleaned when run limit exceeded (keep last 5)
3. **Cleanup**: Also cleaned when regular runs complete (cleanup_terminal_runs already exists)

## Interface Contract

### API Endpoint

```
GET /api/pipeline/status/{run_id}/preview
```

**Response Model** (add to `src/api/schemas/pipeline.py`):

```python
class DryRunSample(BaseModel):
    """A single classified conversation sample."""
    conversation_id: str
    snippet: str  # First 200 chars of source_body
    conversation_type: str  # From stage1 or stage2
    confidence: str  # high/medium/low
    themes: list[str] = []  # From stage1_result.themes if present
    has_support_response: bool = False

class DryRunClassificationBreakdown(BaseModel):
    """Classification type distribution."""
    by_type: dict[str, int]  # e.g., {"product_issue": 5, "how_to_question": 3}
    by_confidence: dict[str, int]  # e.g., {"high": 6, "medium": 2}

class DryRunPreview(BaseModel):
    """Complete dry run preview data."""
    run_id: int
    classification_breakdown: DryRunClassificationBreakdown
    samples: list[DryRunSample]  # 5-10 representative samples
    top_themes: list[tuple[str, int]]  # [(theme, count), ...] top 5
    total_classified: int
    timestamp: datetime
```

### Frontend Types (add to `webapp/src/lib/types.ts`)

```typescript
export interface DryRunSample {
  conversation_id: string;
  snippet: string;
  conversation_type: string;
  confidence: string;
  themes: string[];
  has_support_response: boolean;
}

export interface DryRunClassificationBreakdown {
  by_type: Record<string, number>;
  by_confidence: Record<string, number>;
}

export interface DryRunPreview {
  run_id: number;
  classification_breakdown: DryRunClassificationBreakdown;
  samples: DryRunSample[];
  top_themes: [string, number][];
  total_classified: number;
  timestamp: string;
}
```

## File Assignments

### Marcus (Backend)

**Creates:**

- `src/api/schemas/pipeline.py` - Add `DryRunSample`, `DryRunClassificationBreakdown`, `DryRunPreview` models

**Modifies:**

- `src/api/routers/pipeline.py`:
  - Add module-level `_dry_run_previews: dict[int, DryRunPreview] = {}`
  - Add `_store_dry_run_preview(run_id: int, results: list[dict])` helper
  - Modify `_run_pipeline_task()` to call `_store_dry_run_preview()` when `dry_run=True`
  - Add `GET /api/pipeline/status/{run_id}/preview` endpoint
  - Add cleanup logic (keep last 5 previews)

**Must NOT touch:**

- `webapp/` directory
- `frontend/` directory
- Database schema files

**Acceptance Criteria:**

- [ ] `GET /preview` returns 404 for non-dry-run runs
- [ ] `GET /preview` returns 404 for expired previews
- [ ] Preview includes correct breakdown counts
- [ ] Preview includes 5-10 sample conversations
- [ ] Memory cleanup works (>5 previews triggers cleanup)
- [ ] Tests pass: `pytest tests/api/test_pipeline.py -v`

### Sophia (Frontend)

**Modifies:**

- `webapp/src/lib/types.ts` - Add `DryRunSample`, `DryRunClassificationBreakdown`, `DryRunPreview` types
- `webapp/src/lib/api.ts` - Add `pipeline.preview(runId: number)` method
- `webapp/src/app/pipeline/page.tsx`:
  - Add preview panel in Run Results section
  - Show when `status=completed && conversations_stored=0 && dry_run=true`
  - Display classification breakdown as bar chart or table
  - Display samples as collapsible list
  - Display top themes

**Must NOT touch:**

- `src/` directory
- Database schema files
- `frontend/` (legacy Streamlit)

**Acceptance Criteria:**

- [ ] Preview panel shows only for completed dry runs
- [ ] Classification breakdown displays correctly
- [ ] Samples show snippet, type, confidence
- [ ] Top themes display with counts
- [ ] Loading state while fetching preview
- [ ] Error state if preview not found

## Data Flow

```
1. User starts pipeline with dry_run=true
   └─> POST /api/pipeline/run { dry_run: true }

2. Pipeline classifies conversations
   └─> Results stored in memory (not DB)

3. Pipeline completes
   └─> _store_dry_run_preview(run_id, results)
   └─> Returns { stored: 0 } in stats

4. Frontend polls status, sees completed+stored=0
   └─> GET /api/pipeline/status/{run_id}

5. Frontend fetches preview
   └─> GET /api/pipeline/status/{run_id}/preview
   └─> Renders preview panel

6. User reviews, decides to run for real (or not)
```

## Edge Cases

| Case                              | Handling                                                 |
| --------------------------------- | -------------------------------------------------------- |
| Preview requested for non-dry-run | Return 404 with clear message                            |
| Preview expired (server restart)  | Return 404, frontend shows "Preview no longer available" |
| Very large dry run (1000+ convos) | Sample 10 conversations, full breakdown still computed   |
| Dry run with 0 conversations      | Return valid preview with empty samples, zero counts     |

## Testing Strategy

**Backend Tests** (Marcus):

- Unit test `_store_dry_run_preview()` helper
- Unit test preview endpoint responses
- Test cleanup logic

**Frontend Tests** (Sophia):

- Test preview panel renders with mock data
- Test loading/error states
- Test "not available" message for 404

## Open Questions (None)

Design is complete and ready for implementation.

---

_Architecture by Priya (2026-01-21)_
