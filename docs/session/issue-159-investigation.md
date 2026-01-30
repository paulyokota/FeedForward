# Issue #159 Investigation: Resolution Fields in Story Content

**Date**: 2026-01-30
**Investigator**: Claude (Tech Lead)
**Branch**: `claude/investigate-resolution-fields-Xu2J3`
**Status**: Root cause corrected after review feedback

## Problem Statement

`resolution_action` and `resolution_category` data are captured during theme extraction but never make it into generated story content, limiting the fix guidance provided to users.

## Investigation Summary

**Root Cause**: The resolution fields are lost **at the database query level** in `_run_pm_review_and_story_creation()`. The SELECT query only fetches `diagnostic_summary` and `key_excerpts`, never retrieving `resolution_action`, `root_cause`, `solution_provided`, or `resolution_category` from the themes table.

## Data Flow Analysis

### Current State

| Stage | File | Location | Status |
|-------|------|----------|--------|
| 1. LLM Extraction | `src/theme_extractor.py` | Lines 1155-1230 | ✅ **Captured** |
| 2. DB Storage | `src/api/routers/pipeline.py` | Lines 707-749 | ✅ **Stored** |
| 3. **Story Creation Query** | `src/api/routers/pipeline.py` | Lines 843-853 | ❌ **NOT FETCHED** |
| 4. `conv_dict` construction | `src/api/routers/pipeline.py` | Lines 870-884 | ❌ **NOT INCLUDED** |
| 5. ConversationData | `src/story_tracking/services/story_creation_service.py` | Lines 178-181 | ✅ Fields exist (but never populated) |
| 6. `_build_theme_data()` | `src/story_tracking/services/story_creation_service.py` | Lines 1970-1983 | ❌ **Missing** |
| 7. `StoryContentInput` | `src/prompts/story_content.py` | Lines 262-282 | ❌ **Missing** |
| 8. `format_optional_context()` | `src/prompts/story_content.py` | Lines 321-366 | ❌ **Missing** |

### Primary Gap: Story Creation Query

**`_run_pm_review_and_story_creation()`** at `src/api/routers/pipeline.py:843-853`:

```sql
SELECT t.issue_signature, t.product_area, t.component,
       t.conversation_id, t.user_intent, t.symptoms,
       t.affected_flow, c.source_body, c.issue_type,
       t.diagnostic_summary, t.key_excerpts
       -- ❌ MISSING: t.resolution_action, t.root_cause,
       --            t.solution_provided, t.resolution_category
FROM themes t
JOIN conversations c ON t.conversation_id = c.id
WHERE t.pipeline_run_id = %s
```

**`conv_dict` construction** at `src/api/routers/pipeline.py:870-884`:

```python
conv_dict = {
    "id": row["conversation_id"],
    # ... other fields ...
    "diagnostic_summary": diagnostic_summary,
    "key_excerpts": key_excerpts,
    # ❌ MISSING: resolution_action, root_cause,
    #            solution_provided, resolution_category
}
```

## Fix Requirements

### Code Changes (5 locations)

1. **`src/api/routers/pipeline.py`** - `_run_pm_review_and_story_creation()`:
   - Add to SELECT (line ~847): `t.resolution_action, t.root_cause, t.solution_provided, t.resolution_category`
   - Add to `conv_dict` (line ~884): Include all four fields

2. **`src/story_tracking/services/story_creation_service.py`** - `_build_theme_data()` (~line 1982):
   - Add: `"resolution_action": first_non_null("resolution_action")`
   - Add: `"resolution_category": first_non_null("resolution_category")`
   - Confirm `root_cause` and `solution_provided` still pass through

3. **`src/prompts/story_content.py`** - `StoryContentInput` dataclass (~line 282):
   - Add: `resolution_action: Optional[str] = None`
   - Add: `resolution_category: Optional[str] = None`

4. **`src/prompts/story_content.py`** - `format_optional_context()` (~line 327):
   - Add parameters: `resolution_action` and `resolution_category`
   - Include in "Resolution Context" section

5. **`src/prompts/story_content.py`** - `build_story_content_prompt()` (~line 386):
   - Pass new fields when calling `format_optional_context()`

### Prompt Enhancement

The story generation prompt (`STORY_CONTENT_PROMPT`) should guide the LLM to:
- Include resolution action in acceptance criteria when available
- Reference resolution category for story prioritization hints
- Explicitly use fix guidance from `resolution_action` values

### Acceptance Criteria

Per issue: *"≥70% of stories with `resolution_action` should reflect it in their summary or acceptance criteria."*

**Validation approach**:
- Plumbing fix: Automated tests verify fields flow through
- Behavioral: Manual verification on at least one story with `resolution_action` populated

## Resolution Field Values

### `resolution_action` (from theme_extractor.py)
- `escalated_to_engineering`
- `provided_workaround`
- `user_education`
- `manual_intervention`
- `no_resolution`

### `resolution_category` (from theme_extractor.py)
- `escalation`
- `workaround`
- `education`
- `self_service_gap`
- `unresolved`

## Implementation Recommendation

**Approach**: Fix the data plumbing from query → story content, then enhance prompt.

**Estimated Scope**: ~40 lines of code across 3 files, plus tests

**Testing Requirements**:
1. Unit test for SELECT query including resolution fields
2. Unit test for `conv_dict` including resolution fields
3. Unit test for `_build_theme_data()` including new fields
4. Integration test verifying resolution fields flow through to prompt
5. Manual functional test: verify one generated story reflects `resolution_action`

## Related Files

- `src/api/routers/pipeline.py` - Primary gap (query + conv_dict)
- `src/story_tracking/services/story_creation_service.py` - Secondary gap (_build_theme_data)
- `src/prompts/story_content.py` - Tertiary gaps (dataclass + formatter)
- `src/theme_extractor.py` (reference only - captures correctly)
- `tests/test_issue_146_integration.py` (existing tests for resolution fields)

## Revision History

| Date | Change |
|------|--------|
| 2026-01-30 | Initial investigation - identified _build_theme_data() as root cause |
| 2026-01-30 | **Corrected**: Primary gap is at SELECT query in pipeline.py, not _build_theme_data() |
