# Reginald Correctness Review - PR #86 Round 1

**Verdict**: BLOCK
**Date**: 2026-01-21

## Summary

This PR adds a startup cleanup hook to mark stale 'running' pipeline runs as 'failed', and removes legacy single-stage pipeline files. The cleanup function has 3 HIGH severity issues that could cause race conditions, data corruption, and incorrect status updates in production. The implementation does not consider the interaction between the in-memory `_active_runs` tracker in the pipeline router and the database state.

---

## R1: Race Condition Between Startup Cleanup and In-Memory State

**Severity**: HIGH | **Confidence**: High | **Scope**: Systemic

**File**: `src/api/main.py:68`

### The Problem

The `cleanup_stale_pipeline_runs()` function runs synchronously during FastAPI startup and updates the database, but it does not account for the in-memory `_active_runs` dictionary in `src/api/routers/pipeline.py`. This creates a race condition where:

1. Server restarts while a pipeline is actually running
2. `cleanup_stale_pipeline_runs()` marks it as 'failed' in the database
3. The background task (if it somehow survives the restart, or in a multi-worker setup) continues and eventually marks the run as 'completed' in `_active_runs`
4. The database and in-memory states are now inconsistent

### Execution Trace

**Scenario: Multi-worker deployment (Gunicorn + Uvicorn workers)**

```
Time T0: Worker 1 starts pipeline run #42
  → _active_runs[42] = "running" (Worker 1 memory)
  → DB: pipeline_runs.status = 'running' (row 42)

Time T1: Worker 2 restarts (deployment, crash, etc.)
  → cleanup_stale_pipeline_runs() runs in Worker 2 startup
  → Finds run #42 with status='running' in DB
  → Updates DB: status='failed', error_message='Process terminated...'
  
Time T2: Worker 1 pipeline completes
  → _active_runs[42] = "completed" (Worker 1 memory)
  → Calls _finalize_completed_run(42)
  → DB: status='completed' (overwrites 'failed')

Result: Database says 'completed', but the error message still says 'Process terminated unexpectedly'. Inconsistent state.
```

### Current Code

```python
def cleanup_stale_pipeline_runs() -> int:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = 'Process terminated unexpectedly (server restart)'
                    WHERE status = 'running'
                    RETURNING id
                    """
                )
                stale_ids = [row[0] for row in cur.fetchall()]
            conn.commit()
```

### Suggested Fix

The cleanup function needs to check if any runs are in `_active_runs` before marking them as failed. However, this is tricky because `_active_runs` is module-level state in the router.

**Option 1: Skip cleanup if any workers have active runs**
- Add a shared state mechanism (Redis, database flag) to track active runs across workers
- Only cleanup runs that are NOT in active state anywhere

**Option 2: Add reconciliation logic**
- When a background task starts, check if its run_id was marked as 'failed' by cleanup
- If so, update it back to 'running' and clear the error message
- This acknowledges the race but handles it gracefully

**Option 3: Use database as source of truth**
- Remove the in-memory `_active_runs` dictionary entirely
- Use database queries for status checks
- Add proper locking (FOR UPDATE) when updating status

**Immediate fix for single-worker deployment:**
```python
def cleanup_stale_pipeline_runs() -> int:
    """Only run cleanup if this is a true restart, not a multi-worker scenario."""
    # Import here to avoid circular dependency
    from src.api.routers.pipeline import _active_runs
    
    # If there are any active runs in memory, skip cleanup
    # This handles the case where one worker restarts but others are still running
    if _active_runs:
        logger.info("Active runs detected in memory, skipping cleanup")
        return 0
    
    # Rest of the existing logic...
```

### Edge Cases to Test

1. Multi-worker deployment where Worker A runs pipeline, Worker B restarts
2. True server restart where all workers stop, but database has stale 'running' status
3. Background task that takes longer than the lifespan startup timeout
4. Concurrent pipeline starts during server startup

---

## R2: Missing Cleanup of Error Message on Completion

**Severity**: HIGH | **Confidence**: High | **Scope**: Isolated

**File**: `src/api/main.py:45`

### The Problem

When `cleanup_stale_pipeline_runs()` marks a run as 'failed' and sets `error_message = 'Process terminated unexpectedly'`, but then the pipeline actually completes successfully later (see R1), the error message is NOT cleared. This leaves incorrect error messages in completed runs.

### Execution Trace

```
Time T0: Pipeline run #42 starts
  → DB: status='running', error_message=NULL

Time T1: Server restarts, cleanup runs
  → DB: status='failed', error_message='Process terminated unexpectedly (server restart)'

Time T2: Pipeline completes (race condition scenario)
  → DB: status='completed', error_message='Process terminated unexpectedly (server restart)'
  ⚠️ Error message persists even though run succeeded!
```

### Current Code

The `update_pipeline_run()` function in `src/db/connection.py` (line 155) only updates the error_message if provided:

```python
def update_pipeline_run(run: PipelineRun) -> None:
    sql = """
    UPDATE pipeline_runs SET
        completed_at = %s,
        conversations_fetched = %s,
        conversations_filtered = %s,
        conversations_classified = %s,
        conversations_stored = %s,
        status = %s,
        error_message = %s
    WHERE id = %s
    """
```

But when the pipeline completes successfully, `run.error_message` is likely None or not updated, so the stale error message remains.

### Suggested Fix

**Option 1: Explicitly clear error_message on completion**

In `src/api/routers/pipeline.py`, modify `_finalize_completed_run()` (around line 488):

```python
def _finalize_completed_run(run_id: int, result: dict, theme_result: dict, story_result: dict):
    run = PipelineRun(
        id=run_id,
        status="completed",
        completed_at=datetime.utcnow(),
        conversations_fetched=result["fetched"],
        conversations_classified=result["classified"],
        conversations_stored=result["stored"],
        themes_extracted=theme_result["themes_extracted"],
        themes_new=theme_result["themes_new"],
        stories_created=story_result["stories_created"],
        orphans_created=story_result["orphans_created"],
        error_message=None,  # ← ADD THIS to clear any stale error message
    )
    update_pipeline_run(run)
```

**Option 2: Make error_message update conditional in SQL**

Modify the UPDATE query to only set error_message if status is 'failed':

```sql
UPDATE pipeline_runs SET
    completed_at = %s,
    status = %s,
    error_message = CASE WHEN %s = 'failed' THEN %s ELSE NULL END
WHERE id = %s
```

### Edge Cases to Test

1. Run marked as 'failed' by cleanup, then completes → error_message should be NULL
2. Run that legitimately fails → error_message should persist
3. Run that completes without ever being marked as failed → error_message should be NULL

---

## R3: Database Commit Happens Inside Context Manager But After Cursor Close

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/api/main.py:38-51`

### The Problem

The code commits the transaction AFTER the cursor context manager exits, but INSIDE the connection context manager. While this isn't technically wrong (the commit will work), it's inconsistent with the pattern used elsewhere in the codebase.

### Execution Trace

```python
with get_connection() as conn:           # Line 38
    with conn.cursor() as cur:           # Line 39
        cur.execute(...)                 # Line 40-48
        stale_ids = [row[0] for row in cur.fetchall()]  # Line 50
    # cursor closed here
    conn.commit()                        # Line 51 - commit AFTER cursor closes
```

Compare to `get_connection()` in `src/db/connection.py` (lines 28-40):

```python
@contextmanager
def get_connection() -> Generator:
    conn = psycopg2.connect(get_connection_string())
    try:
        yield conn
        conn.commit()  # ← Automatic commit on exit
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

The `get_connection()` context manager ALREADY commits on successful exit! So the explicit `conn.commit()` on line 51 is redundant and creates a double-commit.

### Current Code

```python
try:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    completed_at = NOW(),
                    error_message = 'Process terminated unexpectedly (server restart)'
                WHERE status = 'running'
                RETURNING id
                """
            )
            stale_ids = [row[0] for row in cur.fetchall()]
        conn.commit()  # ← REDUNDANT: get_connection() already commits
```

### Suggested Fix

Remove the explicit `conn.commit()` call since `get_connection()` handles it automatically:

```python
try:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    completed_at = NOW(),
                    error_message = 'Process terminated unexpectedly (server restart)'
                WHERE status = 'running'
                RETURNING id
                """
            )
            stale_ids = [row[0] for row in cur.fetchall()]
        # No explicit commit needed - get_connection() handles it

    if stale_ids:
        logger.warning(...)
```

### Why This Matters

While double-commit doesn't break functionality in PostgreSQL (it's a no-op), it:
1. Creates inconsistency with the rest of the codebase
2. Suggests the developer didn't understand the context manager's behavior
3. Could cause confusion in future maintenance

### Edge Cases to Test

None - this is a code quality issue, not a functional bug.

---

## R4: Tests Don't Verify Transaction Behavior

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `tests/test_startup_cleanup.py`

### The Problem

The tests mock `get_connection()` but don't verify that the transaction is properly committed or rolled back on errors. The tests verify that `conn.commit()` is called (line 34), but they don't verify:
1. That commit is only called on success
2. That rollback happens on errors
3. That the connection is closed properly

### Current Code

```python
def test_cleans_up_stale_runs(self):
    """Test that stale 'running' runs are marked as 'failed'."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [(1,), (2,), (3,)]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

    with patch("src.api.main.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = Mock(return_value=False)

        result = cleanup_stale_pipeline_runs()

    assert result == 3
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()  # ← Verifies commit, but not rollback
```

### Suggested Fix

Add a test that verifies rollback behavior:

```python
def test_rolls_back_on_cursor_error(self):
    """Test that transaction is rolled back if cursor execution fails."""
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = psycopg2.Error("SQL error")

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

    with patch("src.api.main.get_connection") as mock_get_conn:
        mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = Mock(side_effect=Exception("Rollback"))

        result = cleanup_stale_pipeline_runs()

    assert result == 0
    mock_conn.commit.assert_not_called()
    # In real code, get_connection() would call rollback, but we're mocking it
```

Note: This test would need to be updated once R3 is fixed (removing explicit commit).

### Edge Cases to Test

1. SQL execution fails midway
2. fetchall() raises an exception
3. Database connection drops during execution

---

## R5: Missing Type Hint for Return Value

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `src/api/main.py:27`

### The Problem

The function signature has a return type hint of `int`, which is correct, but the docstring says "Number of stale runs cleaned up" without mentioning that 0 is returned on error. This creates ambiguity: does 0 mean "no stale runs" or "error occurred"?

### Current Code

```python
def cleanup_stale_pipeline_runs() -> int:
    """
    Mark any 'running' pipeline runs as 'failed' on startup.

    This handles the case where the server was restarted while a pipeline
    was running, leaving stale 'running' status in the database.

    Returns:
        Number of stale runs cleaned up.
    """
    try:
        # ... cleanup logic ...
        return len(stale_ids)
    except Exception as e:
        logger.error(f"Failed to cleanup stale pipeline runs: {e}")
        return 0  # ← Ambiguous: error or no stale runs?
```

### Suggested Fix

**Option 1: Use Optional[int] to distinguish error cases**

```python
def cleanup_stale_pipeline_runs() -> Optional[int]:
    """
    Mark any 'running' pipeline runs as 'failed' on startup.

    Returns:
        Number of stale runs cleaned up, or None if an error occurred.
    """
    try:
        # ... cleanup logic ...
        return len(stale_ids)
    except Exception as e:
        logger.error(f"Failed to cleanup stale pipeline runs: {e}")
        return None
```

**Option 2: Log differently and keep int**

```python
def cleanup_stale_pipeline_runs() -> int:
    """
    Mark any 'running' pipeline runs as 'failed' on startup.

    Returns:
        Number of stale runs cleaned up. Returns 0 if no stale runs found
        or if an error occurred (error logged separately).
    """
    try:
        # ... cleanup logic ...
        if stale_ids:
            logger.warning(f"Cleaned up {len(stale_ids)} stale pipeline run(s)")
        else:
            logger.info("No stale pipeline runs found")
        return len(stale_ids)
    except Exception as e:
        logger.error(f"Failed to cleanup stale pipeline runs: {e}")
        return 0
```

### Why This Matters

Callers of this function (currently only the lifespan hook) can't distinguish between:
- "No stale runs, everything is good"
- "Error occurred, we couldn't clean up"

In a monitoring/alerting context, these are very different outcomes.

### Edge Cases to Test

None - this is a documentation clarity issue.

---

## Summary of Issues

| ID | Severity | Category | File | Issue |
|----|----------|----------|------|-------|
| R1 | HIGH | integration | src/api/main.py:68 | Race condition between startup cleanup and in-memory `_active_runs` state |
| R2 | HIGH | logic | src/api/main.py:45 | Error message not cleared when run completes after cleanup marks it failed |
| R3 | MEDIUM | error-handling | src/api/main.py:51 | Redundant commit call (get_connection already commits) |
| R4 | LOW | testing | tests/test_startup_cleanup.py | Tests don't verify transaction rollback behavior |
| R5 | LOW | type-safety | src/api/main.py:27 | Ambiguous return value (0 could mean no stale runs OR error) |

## Recommendations

1. **CRITICAL**: Address R1 before merging. Choose one of the three options presented, or design a different solution. The current implementation will cause data inconsistency in multi-worker deployments.

2. **CRITICAL**: Address R2 to prevent stale error messages. The fix is simple (add `error_message=None` to the PipelineRun update).

3. **RECOMMENDED**: Fix R3 for code consistency. Remove the redundant `conn.commit()` call.

4. **OPTIONAL**: Address R4 and R5 for better test coverage and API clarity, but these are not blockers.

---

## Verdict: BLOCK

The race condition (R1) and error message persistence (R2) are HIGH severity issues that will cause problems in production. The PR should not be merged until these are resolved.
