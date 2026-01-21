# Security Review: PR #68 - Pipeline Control Page + Graceful Stop

**Reviewer**: Sanjay (Security Auditor)
**Round**: 1
**Date**: 2026-01-20
**Verdict**: CHANGES REQUESTED

---

## Executive Summary

This PR introduces a web-based pipeline control interface with start/stop functionality. While the implementation is functional, I've identified **4 security concerns**, including **1 HIGH severity** issue related to lack of authentication on destructive endpoints. The in-memory state management pattern also creates race conditions and denial-of-service vectors.

---

## Issues Found

### S1: MISSING AUTHENTICATION ON PIPELINE CONTROL ENDPOINTS [HIGH]

**Location**: `src/api/routers/pipeline.py` (all endpoints)

**Issue**: The `/api/pipeline/run`, `/api/pipeline/stop`, and all other pipeline endpoints have **NO authentication or authorization** checks. Any client that can reach the API can:

- Start pipeline runs that consume API credits (OpenAI), database resources, and Intercom API quota
- Stop in-progress pipeline runs, disrupting legitimate operations
- View pipeline history and internal operational data

**Evidence**:

```python
@router.post("/run", response_model=PipelineRunResponse)
def start_pipeline_run(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    # No authentication dependency!
```

The grep for authentication shows only one TODO comment in the entire API:

```python
# src/api/routers/research.py:209:    # TODO: Add authentication check for admin
```

**Impact**:

- **Cost explosion**: Attacker can repeatedly trigger pipeline runs, burning OpenAI tokens and Intercom API quota
- **Service disruption**: Attacker can stop legitimate pipeline runs
- **Data exposure**: Pipeline history reveals internal operational metrics

**Recommendation**: Add authentication middleware at minimum, preferably with RBAC for admin-only operations like start/stop.

---

### S2: RACE CONDITION IN IN-MEMORY STATE MANAGEMENT [MEDIUM]

**Location**: `src/api/routers/pipeline.py` lines 28, 155-156, 314-323

**Issue**: The `_active_runs` dictionary is used for state management across requests without any synchronization primitives. This creates multiple race conditions:

1. **Check-then-act race in start_pipeline_run**:

```python
active = [rid for rid, status in _active_runs.items() if status == "running"]
if active:
    raise HTTPException(status_code=409, detail=...)
# Race window: another request could check here before _active_runs is updated
```

2. **Stop-run race**: The stop endpoint reads and writes to `_active_runs` without locking:

```python
active = [rid for rid, status in _active_runs.items() if status == "running"]
# ...
run_id = active[0]
_active_runs[run_id] = "stopping"  # Not atomic with the check above
```

**Impact**:

- Multiple concurrent requests could each pass the "is running" check and start multiple pipeline runs
- Stop signal could be applied to the wrong run if state changes between check and set
- Dictionary iteration during modification could cause RuntimeError

**Recommendation**: Use `threading.Lock` for all reads/writes to `_active_runs`, or migrate to a proper state store (Redis, database) as noted in the comment.

---

### S3: ERROR MESSAGE INFORMATION DISCLOSURE [LOW]

**Location**: `src/api/routers/pipeline.py` lines 101-103, 239

**Issue**: Exception messages are stored directly in the database and returned to clients:

```python
except Exception as e:
    # ...
    cur.execute("""
        UPDATE pipeline_runs SET
            ...
            error_message = %s
        WHERE id = %s
    """, (datetime.utcnow(), str(e), run_id))
```

And exposed via the status endpoint:

```python
return PipelineStatus(
    ...
    error_message=row["error_message"],
    ...
)
```

**Impact**: Exception messages may contain:

- Internal file paths
- Database connection strings or partial credentials
- Stack traces revealing system architecture
- Third-party API error details

**Recommendation**: Sanitize error messages before storage/display. Log full exceptions server-side, return generic messages to clients.

---

### S4: MISSING RATE LIMITING ON PIPELINE START [MEDIUM]

**Location**: `src/api/routers/pipeline.py` `/run` endpoint

**Issue**: While there is a check to prevent concurrent runs, there is no rate limiting to prevent rapid sequential abuse:

1. User starts run
2. User immediately stops run
3. User starts another run
4. Repeat

Each start still consumes resources (database row created, background task spawned, potentially Intercom API calls before stop is processed).

**Evidence**: No rate limiting middleware in `src/api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    ...
)
# No RateLimitMiddleware
```

**Impact**:

- Resource exhaustion through rapid start/stop cycles
- OpenAI token consumption if classification begins before stop signal
- Database bloat from abandoned pipeline_runs rows

**Recommendation**: Add rate limiting (e.g., slowapi) with reasonable limits like 1 run per minute per client.

---

## Additional Observations

### CORS Configuration

The CORS configuration in `main.py` is reasonably locked down to specific localhost origins:

```python
allow_origins=[
    "http://localhost:8501",  # Streamlit
    "http://localhost:3000",  # Next.js
    ...
]
```

This is acceptable for local development but should be reviewed for production deployment.

### SQL Injection Risk: NONE

The SQL queries use parameterized queries correctly:

```python
cur.execute("""
    UPDATE pipeline_runs
    SET status = 'stopping'
    WHERE id = %s AND status = 'running'
""", (run_id,))
```

This is the correct pattern. No SQL injection vulnerabilities found.

### Input Validation: ACCEPTABLE

Pydantic schemas provide reasonable bounds checking:

```python
days: int = Field(default=7, ge=1, le=90)
concurrency: int = Field(default=20, ge=1, le=50)
```

These limits prevent the most obvious resource exhaustion through extreme values.

### Frontend: NO MAJOR ISSUES

The frontend correctly:

- Uses `parseInt(e.target.value, 10)` for number parsing
- Disables form inputs while pipeline is running
- Uses controlled components for form state

No XSS vectors identified - data flow is to API, not dangerouslySetInnerHTML.

---

## Summary Table

| ID  | Severity | Category        | Description                           |
| --- | -------- | --------------- | ------------------------------------- |
| S1  | HIGH     | Authentication  | No auth on pipeline control endpoints |
| S2  | MEDIUM   | Race Condition  | Unsynchronized in-memory state        |
| S3  | LOW      | Info Disclosure | Raw exceptions exposed to clients     |
| S4  | MEDIUM   | Rate Limiting   | No rate limit on start endpoint       |

---

## Verdict

**CHANGES REQUESTED**

- S1 requires immediate attention before production deployment
- S2 and S4 should be addressed to prevent abuse
- S3 is low priority but good hygiene

The lack of authentication (S1) is a blocking issue for any deployment beyond localhost development.
