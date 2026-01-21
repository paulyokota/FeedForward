# PR-100 Review: Search API for Pipeline

**Reviewer**: Reginald (The Architect)
**Date**: 2026-01-21
**Focus**: Correctness, Performance, Error Handling

---

## Overview

This PR adds async methods to `IntercomClient` using aiohttp for server-side date filtering via the Intercom Search API. Key changes include:

1. New async methods in `intercom_client.py` using aiohttp
2. Pipeline updated to use async fetch with semaphore-limited parallel detail fetching
3. Orphan worker cleanup on server startup in `pipeline.py`

---

## Issue Analysis

### R1: aiohttp Session Creation Inside Async Generator Causes Resource Leak Risk (HIGH)

**File**: `src/intercom_client.py`
**Lines**: 365-445

**Analysis**: The `search_by_date_range_async` method creates a new aiohttp session inside the async generator:

```python
async def search_by_date_range_async(self, ...):
    # ...
    async with self._get_aiohttp_session() as session:  # Creates new session
        while True:
            # pagination loop
```

And `fetch_quality_conversations_async` also creates its own session indirectly by calling this method. Meanwhile, in `two_stage_pipeline.py`, the pipeline ALSO creates a session for fetching details:

```python
# two_stage_pipeline.py lines 505-519
async with client._get_aiohttp_session() as session:
    async def fetch_detail(parsed, raw_conv):
        # uses get_conversation_async which requires session
```

**Problem**: `get_conversation_async` requires an external session to be passed in, but during the initial fetch via `search_by_date_range_async`, we're creating sessions that get closed. If the generator is not fully consumed (e.g., early break due to `max_conversations`), the cleanup of the context manager happens immediately, but if there's any delayed usage pattern, we could have session lifecycle issues.

More critically, the pattern creates **multiple sessions** - one for search pagination and another for detail fetching. This is inefficient and could lead to connection pool exhaustion under high concurrency.

**SLOW THINKING - Trace execution**:

1. `run_pipeline_async` calls `fetch_quality_conversations_async`
2. This internally calls `search_by_date_range_async` which creates Session A
3. Session A is used for pagination
4. Generator yields conversations
5. Session A is still open inside the async context manager
6. After loop completes, Session A closes
7. THEN, a NEW Session B is created for `fetch_detail` calls
8. This is 2 sessions, not connection reuse

**Fix**: Pass a session as an optional parameter to share across operations, or restructure to use a single session for the entire pipeline run.

---

### R2: Missing Timeout Configuration for aiohttp Session `sock_read` (MEDIUM)

**File**: `src/intercom_client.py`
**Lines**: 238-250

**Analysis**:

```python
def _get_aiohttp_session(self) -> aiohttp.ClientSession:
    timeout = aiohttp.ClientTimeout(
        connect=self.timeout[0],
        total=self.timeout[0] + self.timeout[1]
    )
```

The `aiohttp.ClientTimeout` has multiple timeout parameters:

- `total`: Total timeout for the whole operation
- `connect`: Time to connect
- `sock_read`: Time to wait for data from peer (per read operation)
- `sock_connect`: Time for socket connection

The code sets `connect` and `total`, but does NOT set `sock_read`. The sync version uses `timeout=(10, 30)` which in `requests` means (connect_timeout, read_timeout). The aiohttp equivalent should explicitly set `sock_read`:

```python
timeout = aiohttp.ClientTimeout(
    connect=self.timeout[0],     # 10s
    sock_read=self.timeout[1],   # 30s - MISSING
    total=self.timeout[0] + self.timeout[1]  # 40s
)
```

**Problem**: Without `sock_read`, a slow server could cause indefinite hangs on individual read operations, as `total` only caps the entire operation. The sync client had explicit read timeout; the async one effectively doesn't.

**Fix**: Add `sock_read=self.timeout[1]` to the ClientTimeout configuration.

---

### R3: Race Condition in PID File Operations (MEDIUM)

**File**: `src/api/routers/pipeline.py`
**Lines**: 91-113

**Analysis**: The `_register_worker_pid` and `_unregister_worker_pid` functions have a TOCTOU (time-of-check-time-of-use) race condition:

```python
def _unregister_worker_pid(pid: int) -> None:
    try:
        if not _PID_FILE.exists():  # CHECK
            return
        pids = _PID_FILE.read_text().strip().split('\n')  # READ
        pids = [p for p in pids if p and p != str(pid)]
        if pids:
            _PID_FILE.write_text('\n'.join(pids) + '\n')  # WRITE
        else:
            _PID_FILE.unlink(missing_ok=True)
```

**SLOW THINKING - Race scenario**:

1. Worker A calls `_unregister_worker_pid(A_PID)`
2. Worker A checks `exists()` -> True
3. Context switch to Worker B
4. Worker B calls `_register_worker_pid(B_PID)`, appends to file
5. Context switch back to Worker A
6. Worker A reads file (now contains A_PID and B_PID)
7. Worker A filters out A_PID, writes only B_PID - OK in this case
8. BUT if Worker A and B both try to unregister simultaneously, one may read stale data

**Alternative race**:

1. Worker A reads file containing [A_PID]
2. Worker B simultaneously registers B_PID (appends to file)
3. Worker A writes file with only [] (since A_PID was removed)
4. B_PID is lost!

This could cause orphan workers to not be tracked properly.

**Fix**: Use file locking (`fcntl.flock` or `filelock` library), or use atomic file operations via rename pattern.

---

### R4: Debug Print Statements Left in Production Code (LOW)

**File**: `src/intercom_client.py`
**Lines**: Multiple (182, 183, 187, 189, 191, 204, 207, 269-315, 332-355, 409-445)

**Analysis**: The async methods are littered with `print(f"[ASYNC]...", flush=True)` statements. This is debug output that:

1. Creates noise in production logs
2. Impacts performance (print is synchronous and blocking)
3. May leak internal implementation details

**Example**:

```python
print(f"[ASYNC] Starting {method} request to {endpoint}, params={params}", flush=True)
print(f"[ASYNC] About to call session.get({url})", flush=True)
```

**Fix**: Remove all debug print statements or convert to proper `logger.debug()` calls that can be controlled via log levels.

---

### R5: Boundary Condition - Search API Uses Exclusive Operators (LOW)

**File**: `src/intercom_client.py`
**Lines**: 386-403

**Analysis**: The Search API query uses `>` and `<` operators:

```python
{
    "field": "created_at",
    "operator": ">",
    "value": start_timestamp,
},
{
    "field": "created_at",
    "operator": "<",
    "value": end_timestamp,
},
```

**SLOW THINKING - Boundary trace**:

- If `since = 2026-01-20 00:00:00` -> `start_ts = 1737331200`
- Query: `created_at > 1737331200`
- A conversation created at EXACTLY `2026-01-20 00:00:00` will be EXCLUDED

This is inconsistent with typical "last N days" semantics where users expect inclusive bounds. The sync methods use client-side filtering with `>=`:

```python
if since and conv_time < since:  # This is < (exclusive on lower bound)
```

Wait, the sync version also uses `<` for the lower bound check, so they are consistent. However, both implementations exclude the exact boundary timestamp.

For `end_timestamp`, `datetime.utcnow().timestamp()` is used. Any conversation created at that exact moment would also be excluded, but this is extremely unlikely.

**Verdict**: Minor consistency issue. Not a bug, but could cause confusion if someone queries for "exactly 7 days" and a conversation at the boundary is missing.

---

## Summary

| ID  | Severity | Category    | Issue                                                           |
| --- | -------- | ----------- | --------------------------------------------------------------- |
| R1  | HIGH     | performance | Multiple aiohttp sessions created, inefficient connection reuse |
| R2  | MEDIUM   | integration | Missing sock_read timeout in aiohttp config                     |
| R3  | MEDIUM   | logic       | Race condition in PID file operations                           |
| R4  | LOW      | performance | Debug print statements in production code                       |
| R5  | LOW      | logic       | Exclusive timestamp operators may exclude boundary values       |

**Verdict**: BLOCK - R1 (session management) and R2 (timeout gap) should be addressed before merge.
