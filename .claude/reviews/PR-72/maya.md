# Maya's Review - PR #72: Evidence Accept/Reject Workflow

**Reviewer**: Maya - The Maintainer
**PR**: #72 - feat(evidence): Implement suggested evidence accept/reject workflow
**Issue**: #55
**Round**: 1
**Date**: 2026-01-20

---

## The Maintainer's Test

I reviewed this code through the lens of future maintainability, asking:

1. Can I understand this code without the original author?
2. Could I debug this at 2am during an incident?
3. Can I change this code without fear of breaking something?

---

## Issues Found

### M1: Missing Documentation for State Machine (Severity: Medium)

**File**: `src/api/routers/research.py`
**Lines**: 382-399

The `_record_evidence_decision` function documents allowed state transitions in a comment, but this is a critical domain concept that deserves more prominent documentation. The state machine (suggested -> accepted/rejected, accepted <-> rejected) is implicit and spread across the codebase.

**Current state documentation (lines 393-398)**:

```python
"""
State transitions allowed:
- suggested -> accepted
- suggested -> rejected
- accepted -> rejected (audit trail via decided_at update)
- rejected -> accepted (audit trail via decided_at update)
"""
```

**Issue**:

- "suggested" isn't stored in DB - it's the absence of a decision record
- A future developer might not understand that "suggested" is a virtual state
- No diagram or central documentation explaining the full evidence lifecycle

**Recommendation**:
Create a docstring or module-level constant explaining that:

- `suggested` = no record exists in `suggested_evidence_decisions` table
- `accepted`/`rejected` = record exists with that decision value
- State transitions are allowed via UPSERT (ON CONFLICT DO UPDATE)

---

### M2: Magic String "accepted"/"rejected" Without Constants (Severity: Low)

**Files**:

- `src/api/routers/research.py` (lines 299, 303, 475, 526)
- `webapp/src/components/SuggestedEvidence.tsx` (line 51)

Decision values "accepted" and "rejected" are used as string literals throughout the codebase without centralized constants.

**Example from research.py**:

```python
if decision == "rejected":
    continue
status = "accepted" if decision == "accepted" else "suggested"
```

**Issue**:

- Typo in any location would cause silent bugs
- No single source of truth for valid decision states
- Frontend and backend both hardcode these strings

**Recommendation**:
Define an enum or constants:

```python
# In models or a shared constants module
class EvidenceDecision:
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUGGESTED = "suggested"  # Virtual state - no DB record
```

---

### M3: Silent Error Swallowing in Frontend (Severity: Medium)

**File**: `webapp/src/components/SuggestedEvidence.tsx`
**Lines**: 29-36, 55-57, 72-73

Errors are caught and logged to console but no user feedback is provided.

```typescript
} catch (err) {
  console.error("Failed to accept evidence:", err);
}
```

**Issue**:

- User clicks "Accept" and nothing visible happens if API fails
- No toast, no retry option, no indication of failure
- Debugging at 2am: User says "it didn't work" but UI shows no error

**Recommendation**:
Add visible error feedback, even if temporary:

```typescript
setError("Failed to accept evidence. Please try again.");
// Or show a toast notification
```

---

### M4: evidence_id Format Implicit Coupling (Severity: Medium)

**File**: `src/api/routers/research.py`
**Lines**: 331-363

The `evidence_id` format `source_type:source_id` is constructed in one place and parsed in another, creating tight coupling without explicit documentation.

**Construction** (line 295):

```python
evidence_id = f"{r.source_type}:{r.source_id}"
```

**Parsing** (lines 341-349):

```python
if ":" not in evidence_id:
    raise HTTPException(...)
parts = evidence_id.split(":", 1)
```

**Issue**:

- Format is not documented anywhere except in error messages
- If source_id contains a colon, parsing will work (split with maxsplit=1) but this edge case isn't explicitly tested
- Frontend must "just know" this format

**Recommendation**:
Add explicit format documentation at module level:

```python
# Evidence ID Format: "{source_type}:{source_id}"
# Example: "coda_page:page_123", "intercom:conv_456"
# Note: source_id may contain colons (split uses maxsplit=1)
EVIDENCE_ID_FORMAT = "{source_type}:{source_id}"
```

---

### M5: Incomplete Test for source_id with Colons (Severity: Low)

**File**: `tests/test_research.py`

No test exists for `source_id` values that contain colons (e.g., `coda_page:page:with:colons`). The parsing logic handles this correctly with `split(":", 1)`, but there's no test to prevent regression.

**Recommendation**:
Add a test case:

```python
def test_accept_evidence_source_id_with_colons(self, client, mock_db, sample_story_id):
    """Test source_id containing colons is handled correctly."""
    evidence_id = "coda_page:page:with:colons"
    # ... verify it parses to source_type="coda_page", source_id="page:with:colons"
```

---

### M6: Undo Button UX is Confusing (Severity: Low)

**File**: `webapp/src/components/SuggestedEvidence.tsx`
**Lines**: 254-272

The "Undo" button for accepted items calls `handleReject`, which removes the item from the UI. This is semantically confusing - "Undo" implies reverting to the previous state (suggested), but it actually rejects the evidence.

```typescript
<button
  className="action-undo"
  onClick={() => handleReject(suggestion.id)}
  aria-label="Undo acceptance"
>
```

**Issue**:

- UX expectation: "Undo" should return to suggested state, showing Accept/Reject buttons again
- Actual behavior: Item disappears (treated as rejected)
- This is a design decision that may be intentional but needs clarification

**Recommendation**:
Either:

1. Rename to "Remove" with aria-label "Remove from accepted evidence"
2. Or implement true undo that returns to suggested state (requires backend change)

---

### M7: VALID_SOURCE_TYPES Duplicated Definition (Severity: Low)

**File**: `src/api/routers/research.py`
**Lines**: 99-100, 151-152, 328

The valid source types set `{"coda_page", "coda_theme", "intercom"}` is defined in multiple places:

```python
# Line 99-100
valid_types = {"coda_page", "coda_theme", "intercom"}

# Line 151-152
valid_types = {"coda_page", "coda_theme", "intercom"}

# Line 328
VALID_SOURCE_TYPES = {"coda_page", "coda_theme", "intercom"}
```

**Issue**:

- Adding a new source type requires finding and updating multiple locations
- DRY violation

**Recommendation**:
Use the module-level constant everywhere:

```python
VALID_SOURCE_TYPES = {"coda_page", "coda_theme", "intercom"}

# Then use VALID_SOURCE_TYPES throughout the file
```

---

### M8: CSS Variable Fallbacks with Hardcoded Values (Severity: Low)

**File**: `webapp/src/components/SuggestedEvidence.tsx`
**Lines**: 491-493

```css
.action-undo:hover:not(:disabled) {
  background: var(--accent-amber-dim, hsla(45, 93%, 47%, 0.15));
  color: var(--accent-amber, hsl(45, 93%, 47%));
```

**Issue**:

- `--accent-amber` and `--accent-amber-dim` might not be defined in the design system
- Hardcoded fallbacks create a "works for now" situation that might diverge from the design system later

**Recommendation**:
Either define these variables in the global CSS or use existing variables that are already defined.

---

## Positive Observations

### What Works Well

1. **Comprehensive Test Coverage**: 21 frontend tests covering loading, empty state, actions, processing state, and error handling. Backend tests cover state transitions, validation, and response structure.

2. **Clear API Contract**: The `EvidenceDecisionResponse` model and OpenAPI documentation make the API contract explicit.

3. **Good Error Messages**: The `_parse_evidence_id` function provides helpful error messages that include the invalid value and expected format.

4. **Accessibility**: Frontend buttons have `aria-label` attributes, and focus states are styled.

5. **Idempotent Operations**: The UPSERT behavior means repeated accept/reject calls don't fail, which is good for network retry scenarios.

---

## Summary

| ID  | Severity | Issue                                        |
| --- | -------- | -------------------------------------------- |
| M1  | Medium   | Missing state machine documentation          |
| M2  | Low      | Magic strings without constants              |
| M3  | Medium   | Silent error swallowing in frontend          |
| M4  | Medium   | evidence_id format implicit coupling         |
| M5  | Low      | Missing test for source_id with colons       |
| M6  | Low      | Undo button UX confusion                     |
| M7  | Low      | Duplicated VALID_SOURCE_TYPES definition     |
| M8  | Low      | CSS variable fallbacks with hardcoded values |

**Total Issues**: 8 (3 Medium, 5 Low)

---

## Verdict

**NEEDS MINOR IMPROVEMENTS**

The code is well-structured and well-tested. The main concerns are around documentation clarity (M1, M4), error feedback to users (M3), and some DRY violations (M2, M7). None of these are blockers, but addressing M1, M3, and M4 would significantly improve maintainability for future developers.

The implementation correctly handles the core workflow and edge cases. A developer inheriting this code in 6 months would be able to understand and modify it, especially with the test suite as documentation. However, adding explicit state machine documentation and error feedback would reduce the cognitive load during debugging.
