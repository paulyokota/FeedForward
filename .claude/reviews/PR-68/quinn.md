# Quinn's Quality Review - PR #68

**PR**: feat(pipeline): Add webapp pipeline control page + graceful stop
**Round**: 1
**Date**: 2026-01-20
**Reviewer**: Quinn (The Quality Champion)

---

## PASS 1: Brain Dump (Raw Concerns)

Every potential concern, no self-censoring:

1. **Stop checker only checked at two points** - The pipeline has stop_checker called only during fetch loop and once before classification. What happens if a 1000-conversation classification is in progress?

2. **No stop check during classification phase** - `asyncio.gather(*tasks)` runs all classification tasks but there's no check DURING this phase - only before it starts.

3. **In-memory state is process-local** - `_active_runs` dict is in-memory. Multi-worker deployment would cause state inconsistency.

4. **Status "filtered" in return dict but "conversations_filtered" in schema** - The pipeline returns `"filtered": 0` but the database column is `conversations_filtered`. Are these always 0?

5. **2-second polling interval** - Is this too aggressive? Too passive? For long-running pipeline, could create load.

6. **PipelineRunListItem.status is `str` not `Literal`** - The backend schema uses `str` for history items while PipelineStatus uses `Literal`. Type inconsistency.

7. **Frontend clears activeStatus on terminal states** - When status reaches completed/failed/stopped, frontend sets `activeStatus(null)` then fetches data. Brief flash possible?

8. **No real-time progress during classification** - Once classification starts, counts don't update until completion. UI shows stale numbers.

9. **Lambda closure captures run_id** - `stop_checker=lambda: _is_stopping(run_id)` - is this correctly capturing the variable?

10. **Coda pipeline has stop_checker passed but not used** - `_run_coda_pipeline_async` receives `stop_checker` but only defines `should_stop()` - never calls it during normalize/classify phases.

11. **asyncio.gather doesn't support cancellation mid-flight** - Once gather starts, all tasks run to completion. Stop signal won't interrupt in-flight LLM calls.

12. **Background task exception handling** - If exception occurs in `_run_pipeline_task`, it re-raises after updating state. Is FastAPI handling this correctly?

13. **History table doesn't show "stopping" status** - The history displays all statuses but users might see "stopping" briefly.

14. **No rate limiting on stop endpoint** - Multiple rapid clicks could cause issues.

15. **Frontend isRunning includes "stopping"** - So stop button becomes disabled, which is correct, but the UI label changes might be confusing.

16. **PipelineStopResponse includes "not_found" in schema** - But the code never returns "not_found" - only "not_running", "stopping", or "stopped".

---

## PASS 2: Quality Analysis

### Q1: Graceful Stop Has Limited Effectiveness (HIGH)

**Concern**: Stop signal only checked at 2 points - during fetch loop and before classification starts.

**Trace**:

```python
# In run_pipeline_async():
# Check 1: During fetch
for parsed, raw_conv in client.fetch_quality_conversations(...):
    if should_stop():  # <-- Checked here
        break

# Check 2: Before classification
if should_stop():  # <-- Checked here
    return {"fetched": len(conversations), ...}

# NO CHECK DURING:
tasks = [classify_conversation_async(...) for ...]
results = await asyncio.gather(*tasks)  # <-- All tasks run to completion
```

**Impact**: If user clicks stop AFTER fetch completes but DURING classification of 500 conversations, all 500 classifications will run to completion (potentially 30+ seconds of LLM calls) before stop takes effect.

**Severity**: MEDIUM-HIGH - This is more about user expectation mismatch than data quality, but it affects system resource consumption and cost (LLM tokens).

**Recommendation**: Add periodic check inside `classify_conversation_async` or use `asyncio.gather` with `return_exceptions=True` and check for cancellation.

---

### Q2: Coda Pipeline Never Checks Stop Signal (HIGH)

**Concern**: `_run_coda_pipeline_async` defines `should_stop()` but never calls it.

**Trace**:

```python
async def _run_coda_pipeline_async(
    ...
    stop_checker: Optional[callable] = None,
) -> Dict[str, int]:
    def should_stop() -> bool:
        return stop_checker is not None and stop_checker()

    # Fetch Coda data
    raw_items = adapter.fetch(...)  # <-- No stop check

    # Normalize
    for item in raw_items:  # <-- No stop check
        conv = adapter.normalize(item)

    # Classify
    tasks = [classify_coda_item(conv) for conv in normalized]
    results = await asyncio.gather(*tasks)  # <-- No stop check
```

**Impact**: Coda pipeline runs completely ignore stop signals. The stop button does nothing for Coda-source runs.

**Severity**: MEDIUM - Currently Coda is secondary data source, but this is a silent failure mode.

**Recommendation**: Add stop checks similar to Intercom pipeline.

---

### Q3: Type Inconsistency Between Backend Schemas (LOW)

**Concern**: `PipelineRunListItem.status` uses `str` while `PipelineStatus.status` uses `Literal["running", "stopping", "stopped", "completed", "failed"]`.

**Trace**:

```python
# src/api/schemas/pipeline.py

class PipelineStatus(BaseModel):
    status: Literal["running", "stopping", "stopped", "completed", "failed"]  # Strict

class PipelineRunListItem(BaseModel):
    status: str  # Permissive
```

**Impact**: History items could theoretically contain invalid status values. TypeScript frontend has its own type but relies on backend validation.

**Severity**: LOW - The database constrains values, but schema should be explicit.

---

### Q4: Progress Not Updated During Classification Phase (MEDIUM)

**Concern**: `conversations_classified` and `conversations_stored` remain 0 during the classification phase because the DB is only updated at the end.

**Trace**:

```python
# During Phase 2 (classification):
# - conversations_fetched is final (from Phase 1)
# - conversations_classified is 0 until all classifications complete
# - conversations_stored is 0 until batch insert

# User polls status/42 and sees:
# { fetched: 500, filtered: 0, classified: 0, stored: 0 }
# ... for potentially 60+ seconds ...
# Then suddenly:
# { fetched: 500, filtered: 0, classified: 500, stored: 495 }
```

**Impact**: User experience is degraded - no sense of progress during the longest phase. User might think pipeline is hung.

**Severity**: MEDIUM - UX issue, not data quality. But could lead to unnecessary restarts.

---

### Q5: Unused "not_found" Status in PipelineStopResponse (LOW)

**Concern**: Schema declares "not_found" as valid status but code never returns it.

**Trace**:

```python
class PipelineStopResponse(BaseModel):
    status: Literal["stopping", "stopped", "not_found", "not_running"]

# In stop_pipeline_run():
if not active:
    return PipelineStopResponse(status="not_running", ...)  # Never "not_found"
```

**Impact**: Minor API documentation mismatch.

**Severity**: LOW - No functional impact.

---

## FUNCTIONAL_TEST_REQUIRED Assessment

This PR **MODIFIES PIPELINE EXECUTION FLOW** by adding:

1. Stop signal checking during fetch phase
2. Early return paths based on stop status
3. New "stopping" and "stopped" terminal states

**Verdict**: **FUNCTIONAL_TEST_REQUIRED = YES**

**Rationale**: Per `docs/process-playbook/gates/functional-testing-gate.md`, any PR that modifies the pipeline execution path requires functional test evidence. The stop mechanism affects when and how conversations are classified and stored.

**Required Evidence**:

1. Start pipeline, let it run to completion - verify normal path unaffected
2. Start pipeline, stop during fetch - verify partial results stored correctly
3. Start pipeline, stop during classification - verify graceful completion of in-flight work
4. Verify "stopped" status appears correctly in history

---

## Summary

| ID  | Severity | Issue                                         | Category           |
| --- | -------- | --------------------------------------------- | ------------------ |
| Q1  | HIGH     | Stop signal ineffective during classification | System Behavior    |
| Q2  | HIGH     | Coda pipeline ignores stop signal entirely    | Missed Update      |
| Q3  | LOW      | Type inconsistency in status schemas          | Schema Consistency |
| Q4  | MEDIUM   | No progress updates during classification     | User Experience    |
| Q5  | LOW      | Unused "not_found" status in response schema  | API Consistency    |

**Critical Path Items**: Q1, Q2
**Recommendation**: Fix Q1 and Q2 before merge. Q3-Q5 can be deferred.

---

_Quinn - The Quality Champion_
_"Output quality is non-negotiable."_
