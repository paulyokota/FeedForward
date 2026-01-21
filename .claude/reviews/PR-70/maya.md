# Maya's Maintainability Review - PR #70

**Reviewer**: Maya, The Maintainer
**PR**: #70 - feat(pipeline): Add run summary with new stories panel
**Focus**: Naming clarity, documentation, code organization, type safety

---

## Summary

Reviewed 6 changed files implementing `created_since` filtering and a new stories panel in the pipeline page. Found **4 maintainability issues** that could confuse future developers or make the code harder to modify.

**Verdict**: REQUEST CHANGES - The feature works, but naming and documentation issues will create confusion for future maintainers.

---

## Issues Found

### M1: Ambiguous parameter name `created_since` lacks clarity about timezone handling (Confidence: 85%)

**Location**: `src/api/routers/stories.py:44-46`, `src/story_tracking/services/story_service.py:225`

**Issue**: The parameter name `created_since` doesn't make it clear whether timezone handling is required. The description says "ISO timestamp" but doesn't specify if naive timestamps are acceptable or if timezone conversion happens automatically.

**Why it matters**: Future developers might pass timestamps in different formats (naive vs aware, different timezones). PostgreSQL's timestamp comparison behavior differs between `timestamp` and `timestamptz` columns. Without clear documentation, this could lead to off-by-hours bugs in production.

**Evidence**:
```python
created_since: Optional[str] = Query(
    default=None,
    description="Filter to stories created at or after this ISO timestamp (e.g., 2024-01-15T10:30:00Z)",
),
```

The example shows a UTC timestamp (`Z` suffix), but the code doesn't validate this or document what happens with other formats.

**Recommendation**:
1. Rename to `created_since_utc` to make timezone expectations explicit
2. Add validation that rejects timestamps without timezone information
3. Document in the docstring: "Must be UTC ISO 8601 timestamp with 'Z' suffix or +00:00 offset"

---

### M2: Magic number 50 appears without named constant (Confidence: 82%)

**Location**: `webapp/src/app/pipeline/page.tsx:78`

**Issue**: The limit value `50` is hardcoded in the `fetchNewStories` function without explanation or named constant.

**Why it matters**: If product requirements change and we need to show more/fewer stories, a future developer has to search the entire codebase to find all instances of this magic number. It's also unclear if 50 is a business requirement, performance limit, or arbitrary choice.

**Evidence**:
```typescript
const response = await api.stories.list({
  created_since: sinceTimestamp,
  limit: 50,  // <- Magic number, no explanation
});
```

**Recommendation**:
```typescript
const NEW_STORIES_DISPLAY_LIMIT = 50; // Max stories to show per pipeline run

const fetchNewStories = useCallback(async (sinceTimestamp: string) => {
  try {
    const response = await api.stories.list({
      created_since: sinceTimestamp,
      limit: NEW_STORIES_DISPLAY_LIMIT,
    });
    // ...
```

---

### M3: Function name `fetchNewStories` doesn't convey the filtering behavior (Confidence: 78%)

**Location**: `webapp/src/app/pipeline/page.tsx:74`

**Issue**: The function name `fetchNewStories` sounds like it retrieves all new stories in the system, but it actually filters by a specific timestamp. A developer might call this expecting different results.

**Why it matters**: Generic names like "fetchNewStories" hide important behavior (timestamp filtering). When debugging production issues or adding features, maintainers won't understand what "new" means without reading the implementation.

**Evidence**:
```typescript
// Function name suggests "all new stories"
const fetchNewStories = useCallback(async (sinceTimestamp: string) => {
  // But actually filters by timestamp
  const response = await api.stories.list({
    created_since: sinceTimestamp,
    limit: 50,
  });
```

Later called as:
```typescript
await fetchNewStories(latestRun.started_at);  // "new" relative to what?
```

**Recommendation**: Rename to `fetchStoriesCreatedSince` or `fetchStoriesForRun` to clarify the filtering behavior.

---

### M4: Missing docstring for complex state interaction logic (Confidence: 90%)

**Location**: `webapp/src/app/pipeline/page.tsx:104-112`

**Issue**: The auto-selection logic for completed runs is complex (filters history, checks if already selected, fetches stories) but has no comment explaining the business logic or why it's needed.

**Why it matters**: This code interacts with 3 state variables (`history`, `selectedRunId`, `newStories`) and has side effects (API call). Future developers modifying the history display or selection logic might break this auto-selection behavior without understanding its purpose.

**Evidence**:
```typescript
// Auto-select the most recent completed run to show its new stories
const completedRuns = historyResponse.filter(
  (run) => run.status === "completed",
);
if (completedRuns.length > 0 && !selectedRunId) {
  const latestRun = completedRuns[0];
  setSelectedRunId(latestRun.id);
  await fetchNewStories(latestRun.started_at);
}
```

The comment is good but doesn't explain:
- Why only completed runs?
- Why check `!selectedRunId`?
- What happens if the API call fails?

**Recommendation**: Add a more detailed comment block:
```typescript
// Auto-select initial run on page load:
// - Only completed runs have stories (running/failed don't)
// - Check !selectedRunId to avoid overriding user's manual selection on re-fetch
// - Failures are caught and logged; user sees empty state
const completedRuns = historyResponse.filter(/* ... */);
```

---

## Minor Observations (Not blocking, confidence < 80%)

### Documentation could be more specific about SQL behavior
In `story_service.py:234`, the docstring says "Filter to stories created at or after this ISO timestamp" but doesn't mention that PostgreSQL interprets ISO strings according to the column type (`timestamp` vs `timestamptz`). This could matter for deployments in different timezones.

### Test naming uses "created_since" terminology inconsistently
Tests in `test_story_tracking.py:629-686` use "created_since" but the class is named `TestCreatedSinceFilter` (singular "Filter" when there are 3 filter tests). Minor inconsistency.

---

## Positive Observations

1. Excellent test coverage for the new filter (3 backend tests, 9 frontend tests)
2. Good use of optional parameter pattern (backwards compatible)
3. Frontend properly handles loading, error, and empty states
4. Accessibility attributes (role, tabIndex, onKeyDown) on clickable rows

---

## Files Reviewed

- `src/api/routers/stories.py` - API endpoint changes
- `src/story_tracking/services/story_service.py` - Database filtering logic
- `tests/test_story_tracking.py` - Backend tests
- `webapp/src/app/pipeline/page.tsx` - Frontend component
- `webapp/src/lib/api.ts` - API client
- `webapp/src/app/pipeline/__tests__/PipelinePage.test.tsx` - Frontend tests

---

## Recommendation

**REQUEST CHANGES**

While the implementation is functionally correct and well-tested, the maintainability issues (especially M1 and M4) will cause problems as the codebase grows. Fixing these now prevents:

1. Timezone bugs in production (M1)
2. Copy-paste errors with magic numbers (M2)  
3. Confusion when debugging filtering logic (M3)
4. Accidental breakage of auto-selection (M4)

Estimated fix time: 30 minutes
