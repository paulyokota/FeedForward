# Issue #159 Investigation: Resolution Fields in Story Content

**Date**: 2026-01-30
**Investigator**: Claude (Tech Lead)
**Branch**: `claude/investigate-resolution-fields-Xu2J3`

## Problem Statement

`resolution_action` and `resolution_category` data are captured during theme extraction but never make it into generated story content, limiting the fix guidance provided to users.

## Investigation Summary

**Root Cause**: The Issue #146 implementation added `root_cause` and `solution_provided` to the story generation pipeline but **omitted** `resolution_action` and `resolution_category` in multiple locations.

## Data Flow Analysis

### Current State

| Stage | File | Location | Status |
|-------|------|----------|--------|
| 1. LLM Extraction | `src/theme_extractor.py` | Lines 1155-1230 | ✅ **Captured** |
| 2. DB Storage | `src/api/routers/pipeline.py` | Lines 707-749 | ✅ **Stored** |
| 3. ConversationData | `src/story_tracking/services/story_creation_service.py` | Lines 178-181 | ✅ **Fields exist** |
| 4. `_build_theme_data()` | `src/story_tracking/services/story_creation_service.py` | Lines 1970-1983 | ❌ **Missing** |
| 5. `StoryContentInput` | `src/prompts/story_content.py` | Lines 262-282 | ❌ **Missing** |
| 6. `format_optional_context()` | `src/prompts/story_content.py` | Lines 321-366 | ❌ **Missing** |

### Where Data is Lost

**`_build_theme_data()`** at `story_creation_service.py:1970-1983`:

```python
return {
    "user_intent": first_non_null("user_intent"),
    "symptoms": unique_symptoms[:MAX_SYMPTOMS_IN_THEME],
    "product_area": first_non_null("product_area"),
    "component": first_non_null("component"),
    "affected_flow": first_non_null("affected_flow"),
    "root_cause_hypothesis": first_non_null("root_cause_hypothesis"),
    "excerpts": excerpts[:MAX_EXCERPTS_IN_THEME],
    "classification_category": first_non_null("classification_category"),
    # Issue #146: LLM-extracted resolution context for story content
    "root_cause": first_non_null("root_cause"),
    "solution_provided": first_non_null("solution_provided"),
    # ❌ MISSING: resolution_action and resolution_category
}
```

## Fix Requirements

### Code Changes (5 locations)

1. **`_build_theme_data()`** in `story_creation_service.py` (~line 1982):
   - Add: `"resolution_action": first_non_null("resolution_action")`
   - Add: `"resolution_category": first_non_null("resolution_category")`

2. **`_build_story_content_input()`** in `story_creation_service.py` (~line 2075):
   - Pass `resolution_action` and `resolution_category` to `StoryContentInput`

3. **`StoryContentInput`** dataclass in `story_content.py` (~line 282):
   - Add: `resolution_action: Optional[str] = None`
   - Add: `resolution_category: Optional[str] = None`

4. **`format_optional_context()`** in `story_content.py` (~line 327):
   - Add parameters: `resolution_action` and `resolution_category`
   - Include in "Resolution Context" section

5. **`build_story_content_prompt()`** in `story_content.py` (~line 386):
   - Pass new fields when calling `format_optional_context()`

### Prompt Enhancement

The story generation prompt (`STORY_CONTENT_PROMPT`) should be enhanced to:
- Include resolution action in guidance for acceptance criteria
- Reference resolution category for story categorization
- Explicitly instruct LLM to incorporate resolution data when available

### Acceptance Criteria

Per issue: *"≥70% of stories with `resolution_action` should reflect it in their summary or acceptance criteria."*

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

**Approach**: Add the missing fields through all layers, then enhance prompt to utilize them.

**Estimated Scope**: 5 file changes, ~30 lines of code

**Testing Requirements**:
1. Unit tests for `_build_theme_data()` including new fields
2. Unit tests for `StoryContentInput` with new fields
3. Integration test verifying resolution fields flow through to prompt
4. Functional test validating stories reflect resolution_action

## Related Files

- `src/story_tracking/services/story_creation_service.py`
- `src/prompts/story_content.py`
- `src/theme_extractor.py` (reference only - captures correctly)
- `tests/test_issue_146_integration.py` (existing tests for resolution fields)
