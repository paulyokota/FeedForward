# Reginald's Review: PR #68 Pipeline Control + Graceful Stop

**Reviewer**: Reginald (The Architect)
**Focus**: Correctness, Performance, Type Safety
**Round**: 1
**Date**: 2026-01-20

---

## Executive Summary

This PR implements a webapp pipeline control page with graceful stop functionality. While the overall architecture is sound, I identified **5 issues** ranging from HIGH to LOW severity. The most critical finding is that the stop signal is ineffective during the classification phase, which is the longest-running part of the pipeline.

---

## Issues Found

### R1: Stop Signal Not Checked During Classification Phase (HIGH)

**Location**: `src/two_stage_pipeline.py` lines 419-427

**Problem**: The `stop_checker` callback is passed to `run_pipeline_async()` but is never checked during the classification phase. Once `asyncio.gather()` is called, all classification tasks run to completion regardless of stop requests.

**Code Analysis**:

```python
# Phase 2: Classify in parallel (lines 419-427)
print(f"\nPhase 2: Classifying {len(conversations)} conversations in parallel...")
start_time = datetime.now()

tasks = [
    classify_conversation_async(parsed, raw_conv, semaphore)
    for parsed, raw_conv in conversations
]
results = await asyncio.gather(*tasks)  # NO CANCELLATION POSSIBLE
```

The stop signal is only checked:

1. During fetch (line 391) - works correctly
2. Before classification (line 408) - works correctly
3. **NOT during classification** - this is the problem

**Impact**: For a pipeline processing 1000 conversations at 20 concurrency, a stop request during classification would require waiting for all 50 batches of LLM calls to complete, potentially several minutes of delay.

**Fix Required**: Either:

1. Batch the classification tasks and check stop between batches
2. Use `asyncio.wait()` with `FIRST_COMPLETED` instead of `gather()`
3. Pass `stop_checker` to individual classification functions and check before LLM call

---

### R2: Memory Leak in \_active_runs Dict (MEDIUM)

**Location**: `src/api/routers/pipeline.py` line 28 and all mutation sites

**Problem**: The `_active_runs` dictionary stores run statuses but entries are never removed. Over time, this dict grows unbounded.

**Evidence**:

```python
# Line 28: Declaration
_active_runs: dict[int, str] = {}  # run_id -> status

# Entries are added:
# Line 47: _active_runs[run_id] = "running"

# Entries are modified but NEVER deleted:
# Line 91: _active_runs[run_id] = "completed"
# Line 105: _active_runs[run_id] = "failed"
# Line 133: _active_runs[run_id] = "stopped"
# Line 326: _active_runs[run_id] = "stopping"
```

**Impact**:

- Memory grows linearly with pipeline runs
- Scanning for active runs becomes slower: `[rid for rid, status in _active_runs.items() if status == "running"]`
- After 10,000 runs, every stop/active check scans 10,000 entries

**Fix Required**: Remove entries after run completes, or implement a cleanup mechanism for entries older than N hours.

---

### R3: conversations_filtered Always Stored as 0 (MEDIUM-LOW)

**Location**: `src/api/routers/pipeline.py` lines 76, 119

**Problem**: The pipeline stats dictionary never includes a "filtered" key, so `result.get("filtered", 0)` always returns 0.

**Evidence in router**:

```python
# Lines 73-89: Storing completed run
cur.execute("""
    UPDATE pipeline_runs SET
        completed_at = %s,
        conversations_fetched = %s,
        conversations_filtered = %s,  # Always 0!
        conversations_classified = %s,
        conversations_stored = %s,
        status = 'completed'
    WHERE id = %s
""", (
    datetime.utcnow(),
    result.get("fetched", 0),
    result.get("filtered", 0),  # Pipeline never sets this
    result.get("classified", 0),
    result.get("stored", 0),
    run_id,
))
```

**Evidence in pipeline** (two_stage_pipeline.py lines 433-439):

```python
stats = {
    "fetched": len(conversations),
    "classified": len(results),
    "stored": 0,
    # Note: NO "filtered" key
}
```

**Impact**: Frontend displays 0 for "Filtered" count, which is misleading data.

**Fix Required**: Either:

1. Add "filtered" tracking to pipeline stats
2. Remove the field from schema and database if not needed

---

### R4: Inefficient Polling Interval Recreation (LOW)

**Location**: `webapp/src/app/pipeline/page.tsx` lines 119-130

**Problem**: The polling interval is recreated on every status update due to effect dependencies.

**Analysis**:

```typescript
// pollStatus depends on activeStatus via useCallback deps
const pollStatus = useCallback(async () => {
  // ...
}, [activeStatus, fetchData]); // activeStatus in deps

// Effect depends on pollStatus
useEffect(() => {
  if (activeStatus && ["running", "stopping"].includes(activeStatus.status)) {
    pollingRef.current = setInterval(pollStatus, STATUS_POLL_INTERVAL);
  }
  // ...
}, [activeStatus, pollStatus]); // pollStatus changes every time activeStatus changes
```

**Consequence**: Every 2 seconds:

1. pollStatus called
2. activeStatus updated
3. pollStatus callback recreated (new identity)
4. Effect re-runs, clears old interval, creates new interval
5. 2-second timer resets

This isn't incorrect, but it's inefficient and the polling frequency drifts.

**Suggested Fix**: Use a ref for activeStatus in pollStatus, or check terminal status inside the callback rather than in effect deps.

---

### R5: Final Run Status Cleared Immediately (LOW)

**Location**: `webapp/src/app/pipeline/page.tsx` lines 105-107

**Problem**: When a run completes, the final status is shown for a brief moment then immediately cleared.

**Code**:

```typescript
if (["completed", "failed", "stopped"].includes(status.status)) {
  setActiveStatus(null); // Clears immediately after setActiveStatus(status)
  fetchData(); // Refresh history
}
```

**Impact**: User sees a brief flash of final results before the status panel goes blank. Poor UX for users wanting to see final statistics.

**Suggested Fix**: Keep final status displayed for a few seconds, or until user dismisses, before clearing.

---

## What's Working Well

1. **Stop endpoint atomicity**: Database update and in-memory update are correctly coordinated
2. **Test coverage**: 15 unit tests cover the major scenarios including stopping states
3. **TypeScript types**: Pipeline types align well with backend schemas
4. **Error handling**: Both backend exceptions and frontend error states are handled

---

## Verdict

**NOT READY TO MERGE** - R1 (stop not working during classification) is a core functionality bug that violates the PR's stated goal of "graceful stop." R2 (memory leak) should also be addressed before production use.

---

## Files Reviewed

| File                               | Issues Found |
| ---------------------------------- | ------------ |
| `src/api/routers/pipeline.py`      | R2, R3       |
| `src/two_stage_pipeline.py`        | R1, R3       |
| `src/api/schemas/pipeline.py`      | None         |
| `tests/test_pipeline_router.py`    | None         |
| `webapp/src/app/pipeline/page.tsx` | R4, R5       |
| `webapp/src/lib/api.ts`            | None         |
| `webapp/src/lib/types.ts`          | None         |

---

_Reginald - The Architect_
_"Code that doesn't work correctly is infinitely slow."_
