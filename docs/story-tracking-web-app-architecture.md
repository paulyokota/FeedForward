# Story Tracking Web App Architecture (System of Record)

## Summary

This document defines the full architecture for the story tracking web app that becomes the **system of record**, while maintaining **bidirectional Shortcut sync**. The system remains **lifecycle-agnostic** for now, treats Shortcut as a downstream/upstream sync target, and supports richer internal metadata (e.g., evidence, conversation counts).

### Decisions captured

- **Lifecycle:** agnostic (no hardcoded workflow state machine).
- **Sync fields:** title, description, comments, labels, priority, severity, product area, technical area.
- **Conflict policy:** last-write-wins (across all bidirectional fields).
- **Labels:** must include production Shortcut taxonomy; may expand internally.
- **Product/technical area:** stored as Shortcut enum values for clean mapping.

---

## Goals & non-goals

### Goals

- Internal web app is the canonical system of record for stories, evidence, and tracking.
- Shortcut stays in sync bidirectionally for shared fields.
- UI can support richer internal metadata than Shortcut can represent.

### Non-goals (for now)

- No role-based UI/permissions.
- No enforced lifecycle/state machine.

---

## Architecture overview

```
Pipeline -> Candidate Stories -> Story Service (canonical)
                                   |     |
                                   |     v
                                   |  Evidence Service
                                   v
                           Shortcut Sync Service <-> Shortcut API
```

### Key services (logical)

1. **Story Service**: canonical story state and metadata.
2. **Evidence Service**: evidence bundles, conversation links, source stats.
3. **Sync Service**: bidirectional sync with Shortcut, conflict resolution.
4. **Label Registry**: Shortcut taxonomy + internal extensions.
5. **Analytics Service**: aggregate metrics and trends.

---

## Canonical data model

### 1) `stories`

Canonical work items stored internally. All Shortcut-shared fields are stored with Shortcut-compatible values.

**Fields**

- `id` (pk)
- `title`
- `description`
- `comments` (JSON array of objects with `id`, `source`, `body`, `created_at`)
- `labels` (array of strings)
- `priority` (Shortcut enum value)
- `severity` (Shortcut enum value)
- `product_area` (Shortcut enum value)
- `technical_area` (Shortcut enum value)
- `status` (free-form string)
- `confidence_score`
- `evidence_count`
- `conversation_count`
- `created_at`, `updated_at`

**Notes**

- `priority`, `severity`, `product_area`, `technical_area` store Shortcut enum values directly.
- `labels` must include production Shortcut taxonomy values, plus internal extensions.

### 2) `story_evidence`

Evidence bundles that ground a story in sources and themes.

**Fields**

- `story_id` (fk)
- `conversation_ids` (array)
- `theme_signatures` (array)
- `source_stats` (JSON)
- `excerpts` (array)
- `last_updated`

### 3) `story_sync_metadata`

Sync bookkeeping for Shortcut.

**Fields**

- `story_id` (fk)
- `shortcut_story_id`
- `last_internal_update_at`
- `last_external_update_at`
- `last_synced_at`
- `last_sync_status`
- `last_sync_error`

### 4) `label_registry`

Tracks Shortcut taxonomy labels and internal extensions.

**Fields**

- `label_name`
- `source` (shortcut/internal)
- `created_at`
- `last_seen_at`

---

## UI surface (mapped to the data model)

### Board view (Kanban-like)

- Backed by `stories.status`.
- Quick metadata: `conversation_count`, `evidence_count`, `confidence_score`, `labels`, `priority`.

### Story detail view

- Story fields + evidence bundle.
- Tabs: Evidence, Themes, Sync, History.

### Analytics view

- Aggregates on `stories` and `story_evidence` (top stories by evidence, source distribution, trends).

---

## Bidirectional Shortcut sync

### Shared fields (bidirectional)

- Title
- Description
- Comments
- Labels
- Priority
- Severity
- Product Area
- Technical Area

### Conflict policy

**Last-write-wins** across all bidirectional fields.

### Sync metadata

- Track `last_internal_update_at`, `last_external_update_at`, `last_synced_at` for comparisons.

### Comments behavior

- Store comments with `(comment_id, source)` to avoid duplicates.

### Labels behavior

- Maintain a label registry seeded from Shortcut.
- Internal labels can be added and must be created in Shortcut during sync.

---

## Sync algorithm (last-write-wins)

```
if last_internal_update_at > last_external_update_at:
    push internal -> Shortcut
else:
    pull Shortcut -> internal
```

- On success, update `last_synced_at` and `last_sync_status`.
- On failure, record `last_sync_error` and retry with backoff.

---

## Sync API (draft)

### 1) Push internal -> Shortcut

`POST /sync/shortcut/push`

**Request**

```
{
  "story_id": "...",
  "snapshot": {
    "title": "...",
    "description": "...",
    "comments": [ ... ],
    "labels": ["..."] ,
    "priority": "...",
    "severity": "...",
    "product_area": "...",
    "technical_area": "..."
  },
  "last_internal_update_at": "..."
}
```

**Response**

```
{
  "shortcut_story_id": "...",
  "last_synced_at": "...",
  "sync_status": "success"
}
```

### 2) Pull Shortcut -> internal

`POST /sync/shortcut/pull`

**Request**

```
{
  "shortcut_story_id": "...",
  "last_external_update_at": "..."
}
```

**Response**

```
{
  "story_id": "...",
  "snapshot": { ... },
  "last_synced_at": "...",
  "sync_status": "success"
}
```

### 3) Shortcut webhook (optional)

`POST /sync/shortcut/webhook`

**Payload**

```
{
  "shortcut_story_id": "...",
  "event_type": "story.updated",
  "updated_at": "...",
  "fields": { ... }
}
```

### 4) Sync status

`GET /sync/shortcut/status/:story_id`

**Response**

```
{
  "story_id": "...",
  "shortcut_story_id": "...",
  "last_internal_update_at": "...",
  "last_external_update_at": "...",
  "last_synced_at": "...",
  "last_sync_status": "...",
  "last_sync_error": "..."
}
```

---

## Label taxonomy import

- A one-time import job pulls the production Shortcut label taxonomy into `label_registry`.
- A periodic refresh (or on-demand action) keeps the registry aligned with Shortcut.
- New internal labels are created in Shortcut during sync.

---

## Pre-implementation planning checklist

- **Shortcut taxonomy snapshot:** export the production labels/product areas/technical areas, store a vetted snapshot for local dev and tests, and define how often it is refreshed.
- **Sync surface audit:** confirm Shortcut field limits (label count, comment sizes) and decide how to handle overflows or truncation.
- **Event sourcing vs. polling:** decide whether to rely on Shortcut webhooks, scheduled polling, or a hybrid (including expected latency targets).
- **Data ownership matrix:** document which internal fields are canonical and which are Shortcut-shared, even under last-write-wins.
- **Backfill strategy:** define how existing Shortcut stories will be imported into the new schema and how duplicates will be detected.
- **Operational SLIs/SLOs:** outline metrics to track sync freshness, error rates, and drift between systems.
- **Security/credential handling:** decide where Shortcut API credentials live and how access is audited/rotated.

---

## Open implementation questions

- Where the sync event queue lives (DB, task queue, or worker service).
- Whether we need a hard limit on free-form label creation.
- How to store `comments` (JSON in `stories` vs. separate `story_comments` table).

---

## Rollout plan (MVP -> full)

1. ✅ **Read-only UI** with story + evidence views (Phase 1 - 2026-01-09)
2. ✅ **Editable story fields** in UI (Phase 2 - 2026-01-09)
3. **Bidirectional Shortcut sync** with last-write-wins (Phase 3 - next)
4. **Analytics enhancements** and reliability hardening (Phase 4)

---

## Implementation Notes (Phase 2)

### Edit Mode Implementation

- Edit mode toggle button in story detail page header
- Form fields auto-populate from current story state when entering edit mode
- Save/Cancel buttons with loading states to prevent double-submission
- PATCH API call to `/api/stories/{id}` with only changed fields
- Optimistic UI update on successful save
- Error handling displays validation messages to user

### Label Management

- Chip-based UI for viewing and removing labels
- Input field for adding new labels
- Enter key or Add button commits new label
- Prevents duplicate labels in the UI
- Labels stored as string array in database

### Pipeline Integration Service

- `ValidatedGroup` dataclass defines the contract between PM review pipeline and story creation
- Signature-based deduplication checks existing stories before creating new ones
- Evidence bundle automatically created with conversation links and excerpts
- Source stats calculated from conversation metadata
- Bulk creation supports batch processing of validated groups with progress logging
- Service is fully tested with 14 unit tests covering all edge cases

### Design Decisions

- **Comments storage**: Used separate `story_comments` table (not JSON in stories) for better queryability and normalization
- **Label limits**: No hard limit enforced in Phase 2; will revisit if needed in Phase 3
- **Conflict resolution**: Not yet implemented; Phase 3 will add last-write-wins sync with Shortcut
