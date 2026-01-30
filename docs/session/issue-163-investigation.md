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

## Proposed Solution

### Option A: Pass code_context to description generator (Recommended)

1. **Add `code_context` parameter** to `_generate_description()`:
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

2. **Reconstruct ExplorationResult** from code_context:
   ```python
   def _reconstruct_exploration_result(
       self,
       code_context: Dict[str, Any]
   ) -> Optional[ExplorationResult]:
       """Reconstruct ExplorationResult from stored code_context dict."""
       if not code_context or not code_context.get("success"):
           return None

       from .codebase_context_provider import (
           ExplorationResult, FileReference, CodeSnippet
       )

       relevant_files = [
           FileReference(
               path=f["path"],
               line_start=f.get("line_start"),
               line_end=f.get("line_end"),
               relevance=f.get("relevance", "")
           )
           for f in code_context.get("relevant_files", [])
       ]

       code_snippets = [
           CodeSnippet(
               file_path=s["file_path"],
               line_start=s["line_start"],
               line_end=s["line_end"],
               content=s["content"],
               language=s.get("language", "python"),
               context=s.get("context", "")
           )
           for s in code_context.get("code_snippets", [])
       ]

       return ExplorationResult(
           relevant_files=relevant_files,
           code_snippets=code_snippets,
           investigation_queries=[],  # Not stored in code_context
           exploration_duration_ms=code_context.get("exploration_duration_ms", 0),
           success=True,
           error=None
       )
   ```

3. **Skip redundant exploration** when code_context already exists:
   ```python
   # In _generate_description():
   exploration_result = None
   if code_context:
       exploration_result = self._reconstruct_exploration_result(code_context)
   elif self.target_repo and self.codebase_provider:
       # Only explore if no code_context provided
       exploration_result = self.codebase_provider.explore_for_theme(...)
   ```

4. **Update call sites** to pass code_context:
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

### Option B: Store exploration in formatter-compatible format

Store `ExplorationResult`-like dict instead of the current `code_context` format. Requires schema migration - not recommended.

---

## Success Criteria (from issue #163)

- [ ] Stories with code_context always include file/snippet references in description
- [ ] No duplicate exploration operations per story
- [ ] Target: ≥90% of stories with code context show it in descriptions

---

## Affected Files

| File | Changes Needed |
|------|----------------|
| `src/story_tracking/services/story_creation_service.py` | Add `_reconstruct_exploration_result()`, update `_generate_description()` signature and logic, update 3 call sites |
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

1. Implement `_reconstruct_exploration_result()` helper method
2. Update `_generate_description()` to accept and use code_context
3. Update call sites (3 locations in `story_creation_service.py`)
4. Write tests
5. Run functional test with pipeline
6. Measure: % of stories with code_context that show it in descriptions

---

_Investigation completed: 2026-01-30_
