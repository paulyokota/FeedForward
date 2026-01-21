# Quinn Quality Review - PR #86 Round 1

**Verdict**: REQUEST_CHANGES
**Date**: 2026-01-21

## Summary

This PR adds startup cleanup for stale pipeline runs and removes legacy code. The cleanup logic is sound but has two quality issues: (1) incomplete state coverage - only cleans up 'running' status but not 'stopping' which is equally stale after restart, and (2) user-facing error message could be clearer about next steps. These gaps could cause user confusion and leave some stale runs unresolved.

---

## Q1: Incomplete Stale State Detection - 'stopping' Status Ignored

**Severity**: HIGH | **Confidence**: High | **Scope**: Systemic

**File**: `src/api/main.py:46`

### The Problem

The cleanup query only targets `status = 'running'`, but the 'stopping' status is also a non-terminal in-progress state that becomes equally stale when the server restarts. According to the codebase, valid statuses are: running, stopping, stopped, completed, failed (from `src/db/models.py:168`). After a restart, both 'running' AND 'stopping' runs are orphaned because the process that was managing them is gone.

### Pass 1 Observation

Saw the WHERE clause only checks 'running' and wondered: what about other in-progress states?

### Pass 2 Analysis

**Traced implications:**
- User stops a pipeline run → status becomes 'stopping'
- Server crashes before graceful shutdown completes
- Startup cleanup runs → only marks 'running' as failed
- The 'stopping' run remains in DB as 'stopping' forever
- User sees stuck "stopping" status in UI with no way to recover

**Checked consistency:**
- `src/api/routers/pipeline.py:39-43` defines `_active_runs` states and `_TERMINAL_STATES = {"stopped", "completed", "failed"}`
- By exclusion, non-terminal states are: 'running', 'stopping'
- Both are in-progress states that require an active process to manage them

**Rated severity:**
- HIGH - Users will see stuck runs that can't be cleared without direct DB manipulation

### Impact if Not Fixed

After a server crash during graceful shutdown, users will have permanent "stopping" runs in the UI that never resolve. They can't restart the pipeline because active runs block new runs. They're stuck.

### Suggested Fix

Update the WHERE clause to clean up both 'running' AND 'stopping':

```sql
WHERE status IN ('running', 'stopping')
```

Update the docstring and error message to reflect this:

```python
error_message = 'Process terminated unexpectedly (server restart - in-progress run failed)'
```

### Related Files to Check

- Tests should verify both 'running' and 'stopping' are cleaned up
- Documentation should explain which states are considered stale

---

## Q2: User-Facing Error Message Lacks Actionable Guidance

**Severity**: MEDIUM | **Confidence**: Medium | **Scope**: Isolated

**File**: `src/api/main.py:45`

### The Problem

The error message "Process terminated unexpectedly (server restart)" tells users WHAT happened but not WHAT TO DO. Users viewing this in the UI (via `webapp/src/app/pipeline/page.tsx:635`) will see "Error: Process terminated unexpectedly (server restart)" and may wonder:
- Is this a bug they should report?
- Should they retry the pipeline?
- Is their data safe?

### Pass 1 Observation

Generic error message - noticed other error messages in the codebase include exception details or next steps (e.g., `src/api/routers/pipeline.py:448` uses `str(e)`).

### Pass 2 Analysis

**Traced implications:**
- User views pipeline history in UI
- Sees failed run with message "Process terminated unexpectedly (server restart)"
- Has questions but message provides no answers
- Might file support ticket or avoid using pipeline

**Checked consistency:**
- Other error messages: 
  - `src/services/repo_sync_service.py:153`: "Git pull failed: {stderr}" (actionable - shows actual error)
  - `src/api/routers/pipeline.py:448`: Uses `str(e)` (shows exception details)
- This message is less informative than the pattern

**Rated severity:**
- MEDIUM - Doesn't cause functional issues but degrades UX and could increase support burden

### Impact if Not Fixed

Users will see cryptic error messages and won't know if they should retry or report a bug. This creates friction and reduces confidence in the system.

### Suggested Fix

Make the message more helpful:

```python
error_message = 'Pipeline interrupted by server restart. You can safely start a new run.'
```

This:
- Explains what happened (restart)
- Reassures data safety ("interrupted" not "crashed")
- Suggests next step ("start a new run")
- Matches the conversational tone of other UI messages

### Related Files to Check

- Update test assertion in `tests/test_startup_cleanup.py:83` to match new message

---

## Q3: Silent Failure During Startup Could Hide Critical Issues

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/api/main.py:59-61`

### The Problem

If the database is unreachable or the cleanup SQL fails, the function catches the exception, logs an error, and returns 0. The FastAPI app continues to start normally. Users will then see stale "running" runs in the UI with no indication that cleanup failed or why they're seeing stuck runs.

### Pass 1 Observation

Broad exception catch with no re-raise - wondered if startup should fail instead of continuing.

### Pass 2 Analysis

**Traced implications:**
- Database connection fails (network issue, wrong credentials, etc.)
- Cleanup logs error but app starts
- User opens UI, sees stale "running" run
- Clicks to view details, sees no error explanation
- Wonders why pipeline appears stuck

**Evaluated tradeoffs:**
- **Option A**: Re-raise exception, fail startup
  - Pro: Forces operator to fix DB before app runs
  - Con: App becomes unavailable even for read-only operations
- **Option B**: Current behavior (continue)
  - Pro: App remains available for other features
  - Con: Silent failure confuses users

**Rated severity:**
- MEDIUM - The silent failure is problematic but failing startup is worse

### Impact if Not Fixed

Users will see stale runs with no explanation when DB connectivity issues occur during startup. They'll wonder if the system is broken.

### Suggested Fix

Keep the current behavior (don't fail startup) but improve observability:

1. **Add startup health indicator**: Create a `/health/startup` endpoint that reports cleanup status
2. **Log more context**: Include exception type and DB connection details in error log
3. **Consider retry**: Try cleanup with exponential backoff before giving up

Minimal fix (if full solution is out of scope):

```python
except Exception as e:
    logger.error(
        f"Failed to cleanup stale pipeline runs: {type(e).__name__}: {e}. "
        f"Stale runs may appear stuck in UI until database is accessible."
    )
    return 0
```

This at least explains the user-visible impact in the logs.

### Related Files to Check

- `src/api/routers/health.py` - could add startup diagnostics endpoint
- Tests should verify the error log message includes exception details

---
