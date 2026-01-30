# Issue #163: Code Context Not Reflected in Story Descriptions - Investigation

**Date**: 2026-01-30
**Branch**: claude/investigate-issue-163-706yc
**Issue**: [#163](https://github.com/paulyokota/FeedForward/issues/163) - Dual-format story description should reflect code_context

---

## Problem Statement

Stories with successfully explored `code_context` (stored in DB) do not always include file/snippet references in their descriptions. The issue manifests as:

1. **Code context invisible in descriptions**: Even when `code_context` is successfully explored and stored, the description may show "Investigation needed to identify relevant files" instead of actual file references.

2. **Redundant exploration calls**: The codebase is explored twice per story - once for storage, once for description formatting.

---

## Technical Analysis

### Current Flow (`story_creation_service.py`)

The story creation process has a **decoupled exploration/description pattern**:

```
1. Build theme_data from conversations
2. Generate LLM-based story content (title, user story)
3. **Explore codebase** → code_context (for storage)
4. **Generate description** → calls explore AGAIN inside (for formatting)
5. Create story with description + code_context
```

### Code Paths Identified

**Path 1: Storage Exploration** (lines 1550-1552):
```python
code_context = None
if self.dual_format_enabled:
    code_context = self._explore_codebase_with_classification(theme_data)
```
- Uses `_explore_codebase_with_classification()`
- Calls `codebase_provider.explore_with_classification()` (Haiku-based classification)
- Result stored in `stories.code_context` (JSONB column)
- Works even when `target_repo` is None

**Path 2: Description Exploration** (lines 2147-2153):
```python
if self.target_repo and self.codebase_provider:
    exploration_result = self.codebase_provider.explore_for_theme(
        theme_data,
        self.target_repo,
    )
```
- Uses `explore_for_theme()` (different method!)
- **Only runs when `self.target_repo` is set**
- Passed to `DualStoryFormatter.format_story()`

### The Gap

| Condition | Storage (`code_context`) | Description (`exploration_result`) |
|-----------|-------------------------|-----------------------------------|
| `target_repo=None`, provider available | ✅ Explored | ❌ Not used |
| `target_repo=set`, provider available | ✅ Explored | ✅ Explored **AGAIN** |
| `target_repo=None`, no provider | ❌ None | ❌ None |

**Key finding**: When `target_repo` is None but `codebase_provider` is available:
- `code_context` IS populated in the database
- But the description shows placeholder text ("Investigation needed")
- The already-explored data is never used for formatting

---

## Data Structures

### `code_context` (JSONB, stored in DB)
```python
{
    "classification": {...},
    "relevant_files": [{"path": str, "line_start": int, "line_end": int, "relevance": str}],
    "code_snippets": [{"file_path": str, "line_start": int, "line_end": int, "content": str, "language": str, "context": str}],
    "exploration_duration_ms": int,
    "classification_duration_ms": int,
    "explored_at": str,
    "success": bool,
    "error": str | None
}
```

### `ExplorationResult` (dataclass, used by formatter)
```python
@dataclass
class ExplorationResult:
    relevant_files: List[FileReference]  # path, line_start, line_end, relevance
    code_snippets: List[CodeSnippet]      # file_path, line_start, line_end, content, language, context
    investigation_queries: List[str]
    exploration_duration_ms: int
    success: bool
    error: Optional[str]
```

**Compatibility**: The `code_context` dict can be reconstructed into an `ExplorationResult` - they have compatible structures.

---

## Proposed Solution (Refined)

**Key insight**: The formatter already serializes `ExplorationResult` back to a dict (`story_formatter.py:666-689`). Reconstructing the dataclass is unnecessary overhead - the formatter can consume `code_context` directly.

### Implementation Plan

**1. Add `code_context` parameter to `_generate_description()`:**
```python
def _generate_description(
    self,
    signature: str,
    theme_data: Dict[str, Any],
    reasoning: str,
    original_signature: Optional[str] = None,
    generated_content: Optional["GeneratedStoryContent"] = None,
    code_context: Optional[Dict[str, Any]] = None,  # NEW
) -> str:
```

**2. Skip exploration when code_context is valid:**
```python
# In _generate_description():
exploration_result = None

# Use stored code_context if available and successful
if code_context and code_context.get("success"):
    # Pass to formatter via new code_context param (see step 3)
    pass
elif self.target_repo and self.codebase_provider:
    # Only explore if code_context missing or failed
    exploration_result = self.codebase_provider.explore_for_theme(...)
```

**3. Add `code_context` parameter to `DualStoryFormatter.format_story()`:**
```python
def format_story(
    self,
    theme_data: Dict,
    exploration_result: Optional["ExplorationResult"] = None,
    evidence_data: Optional[Dict] = None,
    generated_content: Optional["GeneratedStoryContent"] = None,
    code_context: Optional[Dict] = None,  # NEW: direct dict input
) -> DualFormatOutput:
```

**4. Add `format_codebase_context_from_dict()` method:**
```python
def format_codebase_context_from_dict(
    self,
    code_context: Dict[str, Any],
) -> str:
    """Format codebase context directly from stored dict."""
    if not code_context or not code_context.get("success"):
        return """## Context & Architecture

### Architecture Notes:

- Codebase exploration unavailable
- Manual investigation required"""

    sections = ["## Context & Architecture"]

    # Relevant Files
    if code_context.get("relevant_files"):
        sections.append("### Relevant Files:\n")
        for ref in code_context["relevant_files"][:10]:
            line_info = ""
            if ref.get("line_start"):
                if ref.get("line_end"):
                    line_info = f" (lines {ref['line_start']}-{ref['line_end']})"
                else:
                    line_info = f" (line {ref['line_start']})"
            relevance = f" - {ref.get('relevance', '')}" if ref.get('relevance') else ""
            sections.append(f"- `{ref['path']}`{line_info}{relevance}")

    # Code Snippets
    if code_context.get("code_snippets"):
        sections.append("\n### Code Snippets:\n")
        for i, snippet in enumerate(code_context["code_snippets"][:3], 1):
            sections.append(f"**{i}. {snippet['file_path']}** (lines {snippet['line_start']}-{snippet['line_end']})")
            if snippet.get("context"):
                sections.append(f"Context: {snippet['context']}\n")
            sections.append(f"```{snippet.get('language', 'python')}\n{snippet['content']}\n```\n")

    return "\n".join(sections)
```

**5. Update `format_ai_section()` to prefer code_context:**
```python
# In format_ai_section():
if code_context and code_context.get("success"):
    architecture_section = self.format_codebase_context_from_dict(code_context)
elif exploration_result:
    architecture_section = self.format_codebase_context(exploration_result)
else:
    architecture_section = """## Context & Architecture
...placeholder text..."""
```

**6. Update call sites** (3 locations in `story_creation_service.py`):
```python
description = self._generate_description(
    signature,
    theme_data,
    reasoning,
    original_signature,
    generated_content,
    code_context,  # NEW: pass already-explored context
)
```

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| `code_context` present, `success=True` | Use stored context, skip exploration |
| `code_context` present, `success=False` | Run exploration if `target_repo` set |
| `code_context` missing | Run exploration if `target_repo` set |
| Both `code_context` and `exploration_result` | Prefer `code_context` (already done) |

### Why Not Reconstruct ExplorationResult?

1. **Unnecessary overhead**: Converting dict → dataclass → dict (formatter serializes it back)
2. **Lost data**: `investigation_queries` not stored in `code_context`
3. **Simpler code**: Direct dict access is more straightforward

---

## Success Criteria (from issue #163)

- [ ] Stories with code_context always include file/snippet references in description
- [ ] No duplicate exploration operations per story
- [ ] Target: ≥90% of stories with code context show it in descriptions

---

## Affected Files

| File | Changes Needed |
|------|----------------|
| `src/story_formatter.py` | Add `code_context` param to `format_story()`, add `format_codebase_context_from_dict()`, update `format_ai_section()` |
| `src/story_tracking/services/story_creation_service.py` | Add `code_context` param to `_generate_description()`, skip exploration when context available, update 3 call sites |
| `tests/test_story_formatter.py` | Add test for `format_codebase_context_from_dict()` |
| `tests/story_tracking/services/test_story_creation_service.py` | Add test for code_context → description integration |

---

## Risk Assessment

**Low risk**:
- Change is additive (new parameter with default None)
- Backward compatible - existing behavior preserved when code_context not passed
- No schema changes required
- No external API changes

**Testing approach**:
1. Unit test: `_reconstruct_exploration_result()` correctly converts dict → dataclass
2. Integration test: Story with code_context has file references in description
3. Functional test: Pipeline run produces stories with code context in descriptions

---

## Next Steps

1. Add `format_codebase_context_from_dict()` to `DualStoryFormatter`
2. Add `code_context` param to `format_story()` and update `format_ai_section()`
3. Add `code_context` param to `_generate_description()` with skip-exploration logic
4. Update 3 call sites in `story_creation_service.py`
5. Write unit tests for new formatter method
6. Write integration test for code_context → description flow
7. Run functional test with pipeline
8. Measure: % of stories with code_context that show it in descriptions (target: ≥90%)

---

_Investigation completed: 2026-01-30_
