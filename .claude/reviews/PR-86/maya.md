# Maya Maintainability Review - PR #86 Round 1

**Verdict**: APPROVE
**Date**: 2026-01-21

## Summary

This PR adds startup cleanup logic for stale pipeline runs and removes legacy code. The new cleanup function is well-documented and tested. However, there are 3 maintainability improvements that would help future developers: the cleanup function silently swallows errors (making debugging harder), the error message could be more actionable, and the logging output lacks operational context about what happens next. None of these are blocking, but they would improve the 2am debugging experience.

---

## M1: Silent Error Handling Makes Debugging Hard

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/api/main.py:59-61`

### The Problem

The cleanup function catches all exceptions and returns 0, making it impossible to distinguish between "no stale runs" and "database completely failed". The error is logged but the caller (lifespan hook) has no way to know cleanup failed.

### The Maintainer's Test

- Can I understand without author? Yes - but unclear if silent failure is intentional
- Can I debug at 2am? NO - if cleanup fails, nothing alerts me and stale runs stay forever
- Can I change without fear? No - unclear if returning 0 on error is relied upon elsewhere
- Will this make sense in 6 months? Partially - but future dev won't know if error swallowing was intentional

### Current Code

```python
except Exception as e:
    logger.error(f"Failed to cleanup stale pipeline runs: {e}")
    return 0
```

### Suggested Improvement

**Option 1** (Better observability): Return distinct signal for errors vs. empty:

```python
def cleanup_stale_pipeline_runs() -> dict:
    """
    Mark any 'running' pipeline runs as 'failed' on startup.
    
    Returns:
        dict with keys:
            - 'cleaned': int (number of runs cleaned)
            - 'error': str | None (error message if cleanup failed)
    """
    try:
        # ... existing logic ...
        return {'cleaned': len(stale_ids), 'error': None}
    except Exception as e:
        logger.error(f"Failed to cleanup stale pipeline runs: {e}")
        return {'cleaned': 0, 'error': str(e)}
```

**Option 2** (Fail fast): Let the exception propagate so FastAPI startup fails loudly:

```python
except Exception as e:
    logger.error(f"CRITICAL: Failed to cleanup stale pipeline runs: {e}")
    logger.error("Server may show stale pipeline state in UI")
    raise  # Fail fast - database issues need immediate attention
```

### Why This Matters

If the database is down or has a schema issue, the server starts successfully but stale runs are never cleaned. The frontend then shows stale "running" state forever. A future maintainer debugging "why is this run stuck?" won't see any startup errors because they're swallowed.

---

## M2: Error Message Lacks Actionable Context

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `src/api/main.py:45`

### The Problem

The error message "Process terminated unexpectedly (server restart)" tells the user WHAT happened but not what to DO about it. A user seeing this in the UI won't know if they need to re-run the pipeline or if data was partially written.

### The Maintainer's Test

- Can I understand without author? Yes
- Can I debug at 2am? Partially - I know WHY it failed but not WHAT to do
- Can I change without fear? Yes
- Will this make sense in 6 months? Yes, but not helpful enough

### Current Code

```python
error_message = 'Process terminated unexpectedly (server restart)'
```

### Suggested Improvement

```python
error_message = (
    'Pipeline interrupted by server restart. '
    'No data was committed. Please re-run the pipeline to complete this analysis.'
)
```

### Why This Matters

Error messages are user documentation. A product manager seeing this in the UI should immediately know their next action without needing to ask engineering. The current message leaves them wondering if data is corrupted or if the run needs to be retried.

---

## M3: Missing Operational Context in Log Output

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `src/api/main.py:54-56`

### The Problem

The log message tells us stale runs were cleaned up but doesn't indicate what happens next or what impact this has on the system. An operator seeing this in production logs won't know if this is expected behavior or a sign of a deeper problem.

### The Maintainer's Test

- Can I understand without author? Partially - I know WHAT happened but not WHY it matters
- Can I debug at 2am? Partially - missing context about expected vs. unexpected cleanup
- Can I change without fear? Yes
- Will this make sense in 6 months? Needs more context about normal vs. abnormal patterns

### Current Code

```python
if stale_ids:
    logger.warning(
        f"Cleaned up {len(stale_ids)} stale pipeline run(s) from previous session: {stale_ids}"
    )
```

### Suggested Improvement

```python
if stale_ids:
    logger.warning(
        f"Cleaned up {len(stale_ids)} stale pipeline run(s) from previous session: {stale_ids}. "
        f"These runs were marked 'failed' because the server restarted while they were in progress. "
        f"Users can re-run these pipelines from the UI if needed."
    )
```

### Why This Matters

Production logs should tell operators not just WHAT happened but also:
1. Is this normal? (yes - server restarts happen)
2. Is user action required? (no - just awareness)
3. What was the impact? (those runs are now marked failed)

The current message requires the operator to have context about how the system works. A new on-call engineer won't have that context at 2am.

---

## Additional Observations (Non-Issues)

### Strengths

1. **Excellent test coverage**: 5 tests covering happy path, edge cases, and error handling
2. **Clear function documentation**: Docstring explains the why, not just the what
3. **Appropriate logging levels**: Uses warning for expected-but-notable events, error for failures
4. **Good SQL hygiene**: Uses RETURNING clause to get affected IDs atomically

### Legacy Code Removal

The removal of `src/pipeline.py`, `src/classifier.py`, and associated tests is clean and complete. No orphaned imports or references remain. This is the right way to remove deprecated code - all at once with clear documentation in the PR body.

