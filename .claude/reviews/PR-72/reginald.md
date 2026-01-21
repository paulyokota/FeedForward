# PR #72 Review: Reginald (The Architect)

## Focus: Correctness and Performance

**PR**: feat(evidence): Implement suggested evidence accept/reject workflow
**Issue**: #55 - Suggested evidence accept/reject workflow
**Review Round**: 1

---

## Executive Summary

This PR implements the accept/reject workflow for suggested evidence in stories. Overall architecture is sound, but I've identified several issues ranging from correctness bugs to potential performance concerns.

**Verdict**: CHANGES REQUESTED - 3 issues requiring fixes before merge

---

## Files Reviewed

1. `src/api/routers/research.py` - Backend endpoints
2. `tests/test_research.py` - Backend tests
3. `webapp/src/lib/api.ts` - Frontend API client
4. `webapp/src/components/SuggestedEvidence.tsx` - React component
5. `webapp/src/components/__tests__/SuggestedEvidence.test.tsx` - Frontend tests

---

## Detailed Analysis

### R1: Missing Transaction Boundary Around Decision Recording (HIGH)

**File**: `src/api/routers/research.py` (lines 382-435)
**Severity**: High
**Type**: Correctness

**Issue**: The `_record_evidence_decision()` function performs database operations but does not commit the transaction. The function relies on FastAPI's dependency injection to commit, but there's no explicit commit call visible.

**SLOW THINKING Analysis**:

1. Looking at the database cursor usage in `_record_evidence_decision()` (lines 404-416)
2. The function calls `cur.execute()` for the INSERT...ON CONFLICT statement
3. No `db.commit()` call exists within the function
4. The comment at line 542-543 in tests says "Note: db.commit() is called by FastAPI dependency"

**Risk**: If the `get_db` dependency doesn't auto-commit (e.g., uses a connection pool that requires explicit commit), changes may not persist. Additionally, if the dependency yields before commit, the response could be sent before the commit succeeds, leading to data inconsistency.

**Evidence from code**:

```python
# _record_evidence_decision (lines 403-416)
try:
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO suggested_evidence_decisions
                (story_id, evidence_id, source_type, source_id, decision, similarity_score, decided_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (story_id, evidence_id)
            DO UPDATE SET
                decision = EXCLUDED.decision,
                decided_at = NOW()
            """,
            (str(story_id), evidence_id, source_type, source_id, decision, similarity_score)
        )
# No db.commit() visible
```

**Recommendation**: Verify `get_db` dependency implementation. If it doesn't auto-commit, add `db.commit()` after the execute statement. If it does auto-commit, add a comment clarifying this for maintainability.

---

### R2: Undo Button Semantically Uses Reject Instead of Proper Undo (MEDIUM)

**File**: `webapp/src/components/SuggestedEvidence.tsx` (lines 253-272)
**Severity**: Medium
**Type**: Logic/UX Correctness

**Issue**: When user clicks "Undo" on an accepted item, the frontend calls `handleReject()` which sends a `reject` API call. This is semantically incorrect - undoing an acceptance should return the item to "suggested" state, not "rejected" state.

**SLOW THINKING Analysis**:

1. User accepts evidence -> status becomes "accepted"
2. User clicks "Undo" button (line 254-272)
3. `handleReject(suggestion.id)` is called (line 257)
4. This sends POST to `/reject` endpoint
5. Item is removed from UI (line 70: `prev.filter(s => s.id !== evidenceId)`)
6. Server records `decision = "rejected"` in database

**Problem**: The user intent is to undo acceptance (return to suggested state), but the implementation records a rejection. This affects:

- Analytics: Rejection counts will include "undo" actions
- State: On next page load, item won't appear (filtered as rejected server-side)
- User experience: No way to truly "undo" - can only toggle between accept and reject

**Evidence from code**:

```tsx
// Line 253-272 in SuggestedEvidence.tsx
) : (
  <button
    className="action-undo"
    onClick={() => handleReject(suggestion.id)}  // <-- Calls reject!
    disabled={isProcessing}
    aria-label="Undo acceptance"
  >
```

**Recommendation**: Either:

1. Add a new `/undo` endpoint that deletes the decision record (returning to "suggested")
2. Or rename the button to "Reject" to accurately reflect the action
3. Or add frontend state that distinguishes "undo" from "reject" behavior

---

### R3: N+1 Query Pattern Potential in get_suggested_evidence (LOW)

**File**: `src/api/routers/research.py` (lines 226-322)
**Severity**: Low (currently mitigated by limit)
**Type**: Performance

**Issue**: The `get_suggested_evidence` endpoint performs 2 database queries per request (story lookup + decisions lookup), which is acceptable. However, the search results iteration (lines 294-317) runs in O(n) where n = number of search results, and creates SuggestedEvidence objects synchronously.

**SLOW THINKING Analysis**:

1. First query: Get story title/description (line 253-264) - 1 query
2. Search service call (line 278-282) - External/separate concern
3. Second query: Get all decisions for story (line 285-290) - 1 query
4. Loop through results (line 294-317) - O(n) iteration

Current pattern is acceptable because:

- Results are limited (default 5, max 20)
- Decision lookup is done once with batch query
- No additional queries per result

**However**, potential future risk if:

- Limit increases significantly
- Additional metadata lookups are added per-result

**Recommendation**: Document the batch query pattern in comments for future maintainers. Current implementation is efficient.

---

### R4: Frontend Error Handling Swallows All Errors Silently (LOW)

**File**: `webapp/src/components/SuggestedEvidence.tsx` (lines 29-36)
**Severity**: Low
**Type**: Error Handling

**Issue**: The `fetchSuggestions` function catches all errors and sets error to `null`, making it impossible to distinguish between "no suggestions" and "API failure."

**Evidence from code**:

```typescript
// Lines 29-36
} catch (err) {
  // API not ready yet - this is expected during development
  console.warn("Failed to fetch suggested evidence:", err);
  setError(null); // Don't show error, just show empty state  <-- Swallows error
  setSuggestions([]);
}
```

**Recommendation**: The comment says this is expected during development. Consider adding proper error state for production, at least for non-404 errors.

---

### R5: Missing Test for Database Foreign Key Violation Error Path (LOW)

**File**: `tests/test_research.py`
**Severity**: Low
**Type**: Test Coverage

**Issue**: The `_record_evidence_decision` function has error handling for foreign key violations (lines 417-424), but no test exercises this specific path. The tests mock `cursor.fetchone.return_value = None` which triggers the pre-check path, not the IntegrityError path.

**Evidence from code**:

```python
# Lines 417-424 in research.py
except IntegrityError as e:
    # Check for foreign key violation (story not found)
    error_str = str(e).lower()
    if "foreign key" in error_str or "fk_" in error_str:
        raise HTTPException(
            status_code=404,
            detail=f"Story {story_id} not found"
        )
```

**Recommendation**: Add a test that mocks `cursor.execute.side_effect = IntegrityError(...)` to ensure the error handling path is covered.

---

## Positive Observations

1. **Good test coverage**: 21 frontend tests covering loading, empty state, actions, and error handling
2. **Proper URL encoding**: `encodeURIComponent(evidenceId)` used in API client
3. **State transition tests**: Backend tests cover accepted->rejected and rejected->accepted transitions
4. **Idempotent UPSERT**: ON CONFLICT DO UPDATE allows repeated decisions without errors
5. **Type safety**: TypeScript types properly extend SearchResult interface

---

## Conclusion

| Issue                                       | Severity | Fix Required    |
| ------------------------------------------- | -------- | --------------- |
| R1: Missing transaction commit verification | High     | Yes             |
| R2: Undo semantics incorrect                | Medium   | Yes - UX impact |
| R3: N+1 potential (mitigated)               | Low      | No - document   |
| R4: Silent error swallowing                 | Low      | No - dev only   |
| R5: Missing IntegrityError test             | Low      | Recommended     |

**Overall Assessment**: The implementation is architecturally sound with good test coverage. The main concerns are R1 (verify commit behavior) and R2 (undo semantics). R2 is more of a product decision but should be consciously addressed.
