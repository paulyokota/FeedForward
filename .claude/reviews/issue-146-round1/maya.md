# Maya's Maintainability Review - Issue #146 Round 1

**Reviewer**: Maya - The Maintainer (she/her)
**Branch**: `feature/146-llm-resolution-extraction`
**Review Date**: 2026-01-28

---

## Executive Summary

The Issue #146 implementation adds four new resolution fields to the theme extraction pipeline. Overall, the code is well-structured with good inline documentation. However, I identified several areas where future maintainers would benefit from clearer explanations, consolidated enum definitions, and improved traceability between components.

**Issues Found**: 4
**Severity**: 2 Medium, 2 Low

---

## Issues

### M1: Duplicated Enum Definitions Without Single Source of Truth (Medium)

**Location**: Multiple files

- `src/theme_extractor.py` (lines 1144-1150, 1157-1169)
- `src/db/migrations/018_llm_resolution_fields.sql` (comments)
- `src/prompts/pm_review.py` (lines 116-118)
- `docs/issue-146-architecture.md` (lines 110-114, 305-308)

**The Problem**: The valid values for `resolution_action` and `resolution_category` are defined in **four different places**:

1. Inline validation sets in `theme_extractor.py`
2. SQL comments in the migration
3. Implicit usage in `pm_review.py` templates
4. Documentation in `issue-146-architecture.md`

If someone adds a new resolution action (e.g., `redirected_to_docs`), they must update:

- The validation set in `theme_extractor.py`
- The SQL column comment
- The architecture docs
- The prompt template explanations

**The Maintainer's Test**:

- "Can I change this without fear?" - **NO**. Changing the enum requires hunting through multiple files.
- "If this breaks at 2am, can I debug it?" - Partially. The validation logs a warning but doesn't point to where the valid values are defined.

**Recommendation**: Create a single source of truth in a constants module or use Python Enums:

```python
# src/constants/resolution_types.py (or add to theme_extractor.py)
from enum import Enum

class ResolutionAction(str, Enum):
    ESCALATED = "escalated_to_engineering"
    WORKAROUND = "provided_workaround"
    EDUCATION = "user_education"
    MANUAL = "manual_intervention"
    UNRESOLVED = "no_resolution"

class ResolutionCategory(str, Enum):
    ESCALATION = "escalation"
    WORKAROUND = "workaround"
    EDUCATION = "education"
    SELF_SERVICE_GAP = "self_service_gap"
    UNRESOLVED = "unresolved"
```

Then reference these in validation, docs, and prompts.

---

### M2: Missing Docstrings on New Theme Fields (Medium)

**Location**: `src/theme_extractor.py`, lines 583-593

**The Problem**: The new resolution fields have inline comments but lack proper docstrings. The `Theme` dataclass is a critical data structure that flows through the entire pipeline, yet the new fields only have terse comments:

```python
# Issue #146: LLM-powered resolution extraction
# What action did support take to resolve this?
# Values: escalated_to_engineering | provided_workaround | user_education | manual_intervention | no_resolution
resolution_action: str = ""
# 1-sentence LLM hypothesis for WHY this happened
root_cause: str = ""
```

Compare this to the Smart Digest fields which have clear docstrings:

```python
# Smart Digest fields (Issue #144)
# 2-4 sentence summary optimized for developers debugging issues
diagnostic_summary: str = ""
```

**The Maintainer's Test**:

- "Can I understand this without the author?" - Mostly, but I had to read `docs/issue-146-architecture.md` to fully understand the semantic difference between `root_cause` (LLM hypothesis) and `root_cause_hypothesis` (the older field at line 563).

**Recommendation**: Add clearer docstrings explaining:

1. The difference between `root_cause` and `root_cause_hypothesis`
2. When each field is populated (during theme extraction)
3. How downstream consumers use these fields

```python
# Issue #146: LLM-powered resolution extraction
# These fields capture how support resolved the issue and are extracted
# by the LLM during theme extraction (replacing the old regex-based approach).
#
# Used by: PM Review (src/prompts/pm_review.py), Story Creation (src/prompts/story_content.py)

resolution_action: str = ""
"""What action support took to resolve this.
Values: escalated_to_engineering, provided_workaround, user_education, manual_intervention, no_resolution
Empty string if LLM couldn't determine or returned invalid value."""

root_cause: str = ""
"""LLM's 1-sentence hypothesis for WHY this issue happened.
Note: This is distinct from root_cause_hypothesis (line 563) which is the
original theme extraction field. This field comes from Issue #146's
resolution-focused extraction."""
```

---

### M3: Magic String "N/A" Used Inconsistently (Low)

**Location**: `src/prompts/pm_review.py`, lines 167-172

**The Problem**: The `_format_resolution_section` function uses `"N/A"` as a fallback for missing values, but this is a magic string that isn't documented:

```python
return "\n" + RESOLUTION_TEMPLATE.format(
    root_cause=root_cause or "N/A",
    resolution_action=resolution_action or "N/A",
    resolution_category=resolution_category or "N/A",
    solution_provided=solution_provided or "N/A",
)
```

A future maintainer might wonder:

- Should the LLM interpret "N/A" specially?
- Is "N/A" different from an empty string in the prompt context?
- Why not use a more descriptive fallback like "Not determined" or "Unknown"?

**The Maintainer's Test**:

- "Will someone understand this in 6 months?" - They might be confused about whether "N/A" has semantic meaning to the LLM.

**Recommendation**: Add a brief comment or use a named constant:

```python
# Fallback for missing resolution fields in prompt display
# LLM should treat "N/A" as "information not available/determined"
RESOLUTION_FIELD_FALLBACK = "N/A"
```

---

### M4: Architecture Doc Lists Field Numbers That Don't Match Code (Low)

**Location**: `docs/issue-146-architecture.md`, lines 119-142

**The Problem**: The architecture doc says:

```
13. **resolution_action**: ...
14. **root_cause**: ...
15. **solution_provided**: ...
16. **resolution_category**: ...
```

But in `theme_extractor.py`, the actual prompt template shows these as fields 15-18:

```
15. **resolution_action**: ...
16. **root_cause**: ...
17. **solution_provided**: ...
18. **resolution_category**: ...
```

This discrepancy suggests the docs were written before the implementation and not updated afterward.

**The Maintainer's Test**:

- "Can I understand this without the author?" - The discrepancy caused me to double-check whether I was reading the right version.

**Recommendation**: Update `docs/issue-146-architecture.md` to match the actual field numbering in the prompt, or remove the numbers entirely since they're implementation details.

---

## What's Working Well

1. **Migration file is exemplary** - `018_llm_resolution_fields.sql` has excellent comments explaining the purpose, valid values, and issue reference for each column. The `COMMENT ON COLUMN` statements are a great practice.

2. **Issue references throughout** - The `# Issue #146` markers make it easy to trace code back to its origin and understand the rationale.

3. **Validation with logging** - The invalid value handling in `theme_extractor.py` (lines 1151-1169) logs warnings and falls back gracefully, which will help debug LLM output issues in production.

4. **Template organization in prompts** - The separation of `RESOLUTION_TEMPLATE` and `_format_resolution_section` in `pm_review.py` makes the code modular and testable.

---

## Summary Table

| ID  | Severity | Location                          | Issue                                                      |
| --- | -------- | --------------------------------- | ---------------------------------------------------------- |
| M1  | Medium   | Multiple files                    | Duplicated enum definitions without single source of truth |
| M2  | Medium   | theme_extractor.py:583-593        | Missing docstrings on new Theme fields                     |
| M3  | Low      | pm_review.py:167-172              | Magic string "N/A" used without documentation              |
| M4  | Low      | issue-146-architecture.md:119-142 | Field numbers don't match actual prompt                    |

---

## Reviewer Sign-Off

As a maintainer who would inherit this code, I can understand the overall flow and purpose. The issues identified are primarily about reducing future maintenance burden and preventing drift between documentation and implementation.

**Verdict**: Approve with minor changes (address M1 and M2 before merge; M3 and M4 can be follow-up)

---

_Maya - The Maintainer_
_"Will someone understand this in 6 months?"_
