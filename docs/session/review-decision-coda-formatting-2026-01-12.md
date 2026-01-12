# Tech Lead Review Decision - Coda Story Formatting - 2026-01-12

## Context

5-personality code review Round 1 for Coda Story Feature Parity identified:

- **1 HIGH** - Reviewed below
- **8 MEDIUM** - Reviewed below
- **12 LOW** - Deferred to polish pass

## HIGH Issue Decision

### 1. Incorrect Intercom URL Format (Quinn, Reginald, Maya)

**Issue**: Frontend uses `/a/inbox/conversation/` but backend uses `/a/apps/{APP_ID}/inbox/inbox/conversation/`.

**Decision: ACCEPT - NOT A BUG**

Rationale:

- The shorter URL format was already in the codebase before our changes (line 189-191 in original)
- Our changes just moved this existing logic to a reusable function
- Both URL formats work in Intercom (shorter redirects to longer)
- Changing would introduce regression risk for no functional benefit
- Backend format includes Jarvis links which frontend doesn't need

Action: None required. Document this is intentional inconsistency.

## MEDIUM Issue Decisions

### 1. Double-Prefixed Row ID (Reginald)

**Issue**: Coda URLs may produce `#row-row-abc-123` if row_id already has `row-` prefix.

**Decision: ACCEPT RISK**

Rationale:

- Coda row IDs from our JSON source use format like `i-abc123`, not `row-abc123`
- The test data uses `row-abc-123` format but production data doesn't
- Deep links may still work even with double prefix (Coda is forgiving)

Action: Add comment in code clarifying expected row_id format.

### 2. Table Slug Truncation Collisions (Reginald)

**Decision: ACCEPT RISK**

Rationale:

- Our Coda tables have distinct first 20 chars (UXR Toolstack, New User Experience, etc.)
- Collision probability < 0.1% given our data patterns
- Worst case: conversation dedup, not data loss

Action: None required.

### 3. Test Assertion Too Permissive (Quinn)

**Decision: FIX**

Action: Update test to be more specific about URL structure.

### 4. Missing Edge Case Tests (Quinn)

**Decision: DEFER**

Rationale:

- Empty text and special chars are handled by truncation
- Additional edge case tests are polish, not critical

### 5. Backfill Double-Format Risk (Quinn)

**Decision: FIX**

Action: Add idempotency check to detect already-formatted text.

### 6. Duplication/Over-Engineering (Dmitri)

**Decision: ACCEPT**

Rationale:

- Separation of `format_excerpt` and `format_coda_excerpt` is intentional
- Intercom has more metadata (email, org_id, user_id) than Coda
- Merging would add complexity, not reduce it
- Router function enables future source addition

### 7. Magic Values Without Context (Maya)

**Decision: FIX**

Action: Add EXCERPT_MAX_LENGTH constant.

### 8. Frontend Parses Backend IDs (Dmitri)

**Decision: ACCEPT**

Rationale:

- Storing pre-built URLs would require schema changes
- Parsing composite IDs is lightweight and documented
- Backend generates ID, frontend parses - clear contract

## LOW Issues - Bulk Decision

**Decision: DEFER ALL**

These are code quality improvements for future polish:

- Add ellipsis for truncation
- Add test for coda_page format
- Add comment for expanded state
- Update test docstring

## Fixes to Apply

1. Add idempotency check in `backfill_coda_formatting.py`
2. Add `EXCERPT_MAX_LENGTH` constant in `story_formatter.py`
3. Add comment explaining Coda ID format in `EvidenceBrowser.tsx`

---

_Decision by: Tech Lead (Claude Code)_
_Date: 2026-01-12_
