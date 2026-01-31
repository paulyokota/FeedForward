# Session: 2026-01-30 - Issue #185 BrokenPipe Fix

## Summary

Fixed pipeline crashes caused by `BrokenPipeError` when uvicorn reloads during execution.

## What Was Done

1. **Root Cause Analysis**: Pipeline run 98 crashed because `print()` statements fail when stdout closes during uvicorn reload

2. **Solution Implemented**:
   - Created `src/logging_utils.py` with `SafeStreamHandler` and `configure_safe_logging()`
   - Converted 83 `print()` calls in `classification_pipeline.py` to logging
   - Converted 10 `print()` calls in `embedding_pipeline.py` to logging
   - Updated `api/main.py` to use `SafeStreamHandler`

3. **Testing**:
   - Created `tests/test_logging_utils.py` with 9 test cases
   - Verified BrokenPipe simulation: `python -m src.classification_pipeline ... | head -n 1` no longer crashes
   - All pipeline tests pass

4. **Code Review**:
   - 5-personality review completed (2 rounds)
   - Fixed: Missing tests, redundant OSError handler, unused imports

## Key Decisions

| Decision                                               | Rationale                                         |
| ------------------------------------------------------ | ------------------------------------------------- |
| SafeStreamHandler catches BrokenPipeError + ValueError | Both can occur when stdout closes                 |
| Log level defaults to INFO for CLI                     | Some libraries (OpenAI) set WARNING during import |
| Per-conversation logs stay at INFO                     | Intentional for CLI progress visibility           |
| Decorative separators kept                             | Intentional for CLI readability                   |

## Commit

```
72c5b4b fix: Replace print() with logging to prevent BrokenPipe crashes (#185)
```

## Files Changed

- `src/logging_utils.py` (new)
- `tests/test_logging_utils.py` (new)
- `src/api/main.py`
- `src/classification_pipeline.py`
- `src/research/embedding_pipeline.py`
