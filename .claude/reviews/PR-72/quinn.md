# Quinn's Quality Review - PR #72

**PR**: feat(evidence): Implement suggested evidence accept/reject workflow
**Issue**: #55 - Suggested evidence accept/reject workflow
**Round**: 1
**Date**: 2026-01-20

---

## PASS 1: Brain Dump (Raw Concerns)

As I reviewed this PR, here are all concerns that surfaced:

1. Undo behavior - the frontend "Undo" calls reject API, which means an accepted item becomes rejected, not back to suggested. Is this intentional?
2. No loading indicator during accept/reject actions beyond button disable state
3. Frontend optimistic update on accept, but no rollback on error
4. Silent error handling in frontend could hide real issues
5. State transitions are all via UPSERT - no explicit validation of valid transitions
6. Database migration creates table but does this PR include running it?
7. The GET suggested-evidence endpoint filters rejected server-side - good, but there's a race condition if user rejects something while viewing
8. No pagination for suggested evidence
9. API routes use encodeURIComponent for evidence_id - but backend expects specific format
10. The evidence_id composite format (source_type:source_id) contains colon - what if source_id contains a colon?
11. Similarity score is optional in \_record_evidence_decision but never passed from accept/reject endpoints
12. No user/actor tracking for who made the decision
13. Potential stale UI if another user makes decisions on same story
14. Frontend test has console.warn/error output showing expected behavior is logged errors

---

## PASS 2: Analysis & Findings

### Q1: Undo Semantics May Confuse Users (LOW)

**Location**: `webapp/src/components/SuggestedEvidence.tsx:255-272`

**Issue**: The "Undo" button calls `handleReject()` which sets status to "rejected". This means undoing an accepted item marks it as rejected and removes it from view, rather than returning it to "suggested" state.

**Impact**: Users may expect "Undo" to restore the item to its previous state, not permanently hide it.

**Evidence**:

```tsx
// Line 253-272
) : (
  <button
    className="action-undo"
    onClick={() => handleReject(suggestion.id)}
    disabled={isProcessing}
    aria-label="Undo acceptance"
  >
```

**Recommendation**: Either:

1. Add a `DELETE` endpoint to remove decision and restore to "suggested", OR
2. Rename button to "Remove" to clarify behavior

---

### Q2: Frontend Error Handling Silently Swallows Errors (LOW)

**Location**: `webapp/src/components/SuggestedEvidence.tsx:29-33, 55-57`

**Issue**: Errors on fetch and accept are logged but not displayed to user. For fetch errors, this is acceptable (silent degradation), but for accept/reject actions, users get no feedback when their action fails.

**Evidence**:

```tsx
// Line 29-33
} catch (err) {
  console.warn("Failed to fetch suggested evidence:", err);
  setError(null); // Don't show error, just show empty state
  setSuggestions([]);
}

// Line 55-57
} catch (err) {
  console.error("Failed to accept evidence:", err);
}
```

**Impact**: User clicks Accept, action fails, they see no error, and the UI doesn't change (item stays in "suggested" state). This is correct behavior but could be confusing.

**Recommendation**: Consider adding a toast notification or inline error state for action failures.

---

### Q3: Source ID with Colon Would Break Parsing (LOW - EDGE CASE)

**Location**: `src/api/routers/research.py:331-363`

**Issue**: The `_parse_evidence_id()` function uses `split(":", 1)` which handles multiple colons correctly by only splitting on the first. However, the schema doesn't document this limitation.

**Evidence**:

```python
parts = evidence_id.split(":", 1)  # Line 347
source_type = parts[0]
source_id = parts[1]  # Everything after first colon
```

**Assessment**: This is actually correctly implemented. The `split(":", 1)` ensures that `coda_page:page:with:colons` would parse as source_type=`coda_page` and source_id=`page:with:colons`. **No issue here.**

---

### Q4: Similarity Score Not Captured on Decision (INFO)

**Location**: `src/api/routers/research.py:469-476, 519-526`

**Issue**: The `_record_evidence_decision()` function accepts `similarity_score` parameter but the accept/reject endpoints don't pass it.

**Evidence**:

```python
# Line 388-390 in function signature
def _record_evidence_decision(
    ...
    similarity_score: float | None = None,
)

# Line 469-476 (accept endpoint)
_record_evidence_decision(
    db=db,
    story_id=story_id,
    evidence_id=evidence_id,
    source_type=source_type,
    source_id=source_id,
    decision="accepted",
    # similarity_score not passed
)
```

**Impact**: Loss of analytics capability - we can't track if users accept high vs low similarity suggestions.

**Recommendation**: Consider passing similarity score from frontend or looking it up server-side.

---

### Q5: No Audit Trail for User/Actor (INFO)

**Location**: `src/db/migrations/007_suggested_evidence_decisions.sql`

**Issue**: The `suggested_evidence_decisions` table has `decided_at` timestamp but no `decided_by` field to track which user made the decision.

**Impact**: For multi-user scenarios, no accountability for decisions. State changes can't be attributed.

**Recommendation**: This may be intentional for MVP. Consider adding `decided_by` in future iteration.

---

### Q6: Test Coverage is Comprehensive (POSITIVE)

**Assessment**: The test coverage is excellent:

- 16 backend tests covering happy paths, validation, state transitions, and error handling
- 3 backend tests for filtering behavior
- 21 frontend tests covering loading, display, actions, state transitions, and error handling

All tests pass. The test names clearly describe behavior. Contract tests verify response structure matches models.

---

## FUNCTIONAL_TEST_REQUIRED Assessment

This PR does NOT modify:

- LLM prompts
- Classification logic
- Pipeline processing
- Embedding generation

It only adds UI workflow for human decision-making on already-generated suggestions. The semantic search that generates suggestions is not modified.

**Verdict: FUNCTIONAL_TEST_REQUIRED = NO**

---

## Summary

| ID  | Severity | Category  | Description                                      |
| --- | -------- | --------- | ------------------------------------------------ |
| Q1  | LOW      | UX        | "Undo" rejects rather than restores to suggested |
| Q2  | LOW      | UX        | Silent error handling on action failures         |
| Q4  | INFO     | Analytics | Similarity score not captured on decision        |
| Q5  | INFO     | Audit     | No user tracking for decisions                   |

**Overall Assessment**: This is a well-implemented feature. The backend properly validates inputs, handles state transitions with UPSERT semantics, and filters rejected items from GET responses. The frontend handles all states correctly with good test coverage. The issues identified are minor UX considerations for future iteration.

**Recommendation**: APPROVE with minor notes

- Consider Q1 (undo semantics) for future UX improvement
- Q4 and Q5 are enhancement suggestions, not blockers

---

## Files Reviewed

1. `/Users/paulyokota/Documents/GitHub/FeedForward/src/api/routers/research.py` - Backend endpoints
2. `/Users/paulyokota/Documents/GitHub/FeedForward/tests/test_research.py` - Backend tests
3. `/Users/paulyokota/Documents/GitHub/FeedForward/webapp/src/lib/api.ts` - API client
4. `/Users/paulyokota/Documents/GitHub/FeedForward/webapp/src/components/SuggestedEvidence.tsx` - React component
5. `/Users/paulyokota/Documents/GitHub/FeedForward/webapp/src/components/__tests__/SuggestedEvidence.test.tsx` - Frontend tests
6. `/Users/paulyokota/Documents/GitHub/FeedForward/src/research/models.py` - Pydantic models
7. `/Users/paulyokota/Documents/GitHub/FeedForward/src/db/migrations/007_suggested_evidence_decisions.sql` - DB schema
8. `/Users/paulyokota/Documents/GitHub/FeedForward/webapp/src/lib/types.ts` - TypeScript types
