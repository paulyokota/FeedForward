# Session Notes: 2026-02-01

## Issue #200: 30-Day Recency Gate for Story Creation

### Summary

Implemented a hard-coded 30-day recency requirement for story creation. Groups must include at least one conversation created within the last 30 days. All-old groups route to orphan accumulation with reason "No recent conversations (last 30 days)".

### Key Decisions

| Decision                  | Choice                                       | Rationale                                      |
| ------------------------- | -------------------------------------------- | ---------------------------------------------- |
| Orphan graduation recency | Query conversations table at graduation time | Single source of truth                         |
| High-severity bypass      | NO bypass                                    | Recency is about staleness, not urgency        |
| Gate ordering             | Recency right after MIN_GROUP_SIZE           | Clearer failure reasons                        |
| Boundary condition        | `>=` (inclusive)                             | 30 days ago = recent                           |
| Missing created_at        | Treat as NOT recent                          | Conservative approach                          |
| Constant location         | `models/orphan.py`                           | Single source of truth, next to MIN_GROUP_SIZE |

### Implementation

**Files Changed (8 files, +1012/-89 lines):**

- `src/api/routers/pipeline.py` - Add `created_at` to SQL query
- `src/story_tracking/models/orphan.py` - Add `RECENCY_WINDOW_DAYS` constant
- `src/story_tracking/models/__init__.py` - Export `RECENCY_WINDOW_DAYS`
- `src/story_tracking/services/story_creation_service.py` - Add `_has_recent_conversation` helper, recency gates
- `src/story_tracking/services/orphan_service.py` - Add recency methods, `skip_recency_check` parameter
- `tests/test_recency_gate.py` - New test file (29 tests)
- `tests/test_story_creation_service.py` - Add `created_at` to test fixtures
- `tests/test_story_creation_service_pm_review.py` - Add `created_at` to test fixtures

### Review Feedback (Codex)

1. **BLOCKER - RealDictCursor compatibility**: Changed index-based access (`result[0]`) to dict-style access (`result["has_recent"]`) to match psycopg2 RealDictCursor behavior
2. **MAJOR - N+1 query elimination**: Added `skip_recency_check` parameter to `graduate()` so bulk graduation doesn't repeat per-orphan recency checks

### Tests

- 29 new recency gate tests
- 130 story creation service tests (22 required `created_at` fixture updates)
- All tests pass

### PR

- PR #203: https://github.com/paulyokota/FeedForward/pull/203
- Merged to main
- Issue #200: CLOSED
