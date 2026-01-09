# Story Tracking Web App - Session Kickoff

**Branch**: `feature/story-tracking-webapp`
**Architecture**: `docs/story-tracking-web-app-architecture.md`
**Status**: Scaffolding complete, ready for implementation

---

## What's Ready

### 1. Database Schema

`src/db/migrations/004_story_tracking_schema.sql`

Tables created:

- `stories` - Canonical work items (system of record)
- `story_comments` - Comments with source tracking
- `story_evidence` - Evidence bundles (conversations, themes, excerpts)
- `story_sync_metadata` - Bidirectional Shortcut sync state
- `label_registry` - Shortcut taxonomy + internal labels

**To apply migration:**

```bash
psql $DATABASE_URL -f src/db/migrations/004_story_tracking_schema.sql
```

### 2. Pydantic Models

`src/story_tracking/models/__init__.py`

- `Story`, `StoryCreate`, `StoryUpdate`
- `StoryEvidence`, `EvidenceExcerpt`
- `StoryComment`, `CommentCreate`
- `SyncMetadata`
- `StoryWithEvidence` (joined response)

### 3. Service Stubs

`src/story_tracking/services/`

- `StoryService` - CRUD, listing, search (stubs)
- `EvidenceService` - Evidence management (stubs)

All methods raise `NotImplementedError` with clear TODOs.

---

## Rollout Plan (from architecture doc)

| Phase | Description                              | Status   |
| ----- | ---------------------------------------- | -------- |
| 1     | Read-only UI with story + evidence views | **Next** |
| 2     | Editable story fields in UI              | Future   |
| 3     | Bidirectional Shortcut sync              | Future   |
| 4     | Analytics enhancements                   | Future   |

---

## Phase 1 Implementation Tasks

### 1. Apply Migration

```bash
psql $DATABASE_URL -f src/db/migrations/004_story_tracking_schema.sql
```

### 2. Implement StoryService

File: `src/story_tracking/services/story_service.py`

Priority order:

1. `list()` - For board/list view
2. `get()` - For detail view
3. `create()` - For pipeline integration
4. `get_by_status()` - For kanban columns

### 3. Implement EvidenceService

File: `src/story_tracking/services/evidence_service.py`

Priority order:

1. `get_for_story()` - Load evidence in detail view
2. `create_or_update()` - For pipeline integration
3. `add_conversation()` - Incremental updates

### 4. Add API Routes

Create: `src/api/routers/stories.py`

Endpoints needed:

- `GET /api/stories` - List with filters
- `GET /api/stories/{id}` - Detail with evidence
- `GET /api/stories/board` - Grouped by status (kanban)

### 5. Add UI Pages

Create: `frontend/pages/4_Stories.py`

Views needed:

- Board view (kanban by status)
- List view (sortable table)
- Detail view (story + evidence tabs)

---

## Integration Points

### From Existing Pipeline

The theme extraction pipeline can create candidate stories:

```python
from src.story_tracking import StoryService, EvidenceService

# After theme extraction
story = await story_service.create(StoryCreate(
    title=f"[{count}] {signature}",
    description=build_description(themes),
    product_area=themes[0].product_area,
    confidence_score=confidence,
    status="candidate",
))

await evidence_service.create_or_update(
    story_id=story.id,
    conversation_ids=[t.conversation_id for t in themes],
    theme_signatures=[signature],
    source_stats={"intercom": intercom_count, "coda": coda_count},
    excerpts=excerpts,
)
```

### From Multi-Source Data

The `source_stats` field maps directly to cross-source analytics:

- `{"intercom": N, "coda": M}` enables priority categorization
- High-confidence = both sources present

---

## Pre-Implementation Checklist

From architecture doc:

- [ ] **Shortcut taxonomy snapshot**: Export production labels/areas
- [ ] **Sync surface audit**: Confirm Shortcut field limits
- [ ] **Data ownership matrix**: Document canonical vs shared fields
- [ ] **Backfill strategy**: How to import existing Shortcut stories

---

## Quick Start Commands

```bash
# Switch to feature branch
git checkout feature/story-tracking-webapp

# Apply migration
psql $DATABASE_URL -f src/db/migrations/004_story_tracking_schema.sql

# Run existing operational dashboard (for reference)
uvicorn src.api.main:app --reload --port 8000
streamlit run frontend/app.py

# Run tests (once implemented)
pytest tests/test_story_tracking.py -v
```

---

## Files to Implement

| File                                              | Purpose             | Priority     |
| ------------------------------------------------- | ------------------- | ------------ |
| `src/story_tracking/services/story_service.py`    | Story CRUD          | P0           |
| `src/story_tracking/services/evidence_service.py` | Evidence management | P0           |
| `src/api/routers/stories.py`                      | REST endpoints      | P1           |
| `frontend/pages/4_Stories.py`                     | UI pages            | P1           |
| `tests/test_story_tracking.py`                    | Service tests       | P1           |
| `src/story_tracking/services/sync_service.py`     | Shortcut sync       | P2 (Phase 3) |
