# Security Review: PR #100 - Search API for Pipeline

**Reviewer**: Sanjay (Security Auditor)
**Date**: 2026-01-21
**Round**: 1
**Verdict**: BLOCK

## Executive Summary

This PR introduces async Intercom API methods and orphan worker cleanup with PID tracking. I have identified **1 CRITICAL** and **2 HIGH** severity security issues that require remediation before merge.

---

## Critical Findings

### S1: PID File Race Condition and Arbitrary Process Kill (CRITICAL)

**Location**: `src/api/routers/pipeline.py` lines 56-88, 91-113

**Description**: The PID file mechanism at `/tmp/feedforward_pipeline_workers.pid` suffers from a classic TOCTOU (Time-of-Check-Time-of-Use) race condition that could be exploited to kill arbitrary processes.

**Attack Vector**:

1. The PID file is written to a world-writable directory (`/tmp/`)
2. Any local user can write arbitrary PIDs to this file
3. On server restart, `_cleanup_orphaned_workers()` reads PIDs from the file and calls `os.kill(pid, signal.SIGTERM)` on them
4. An attacker could inject PIDs of critical system processes or other user processes

**Code Analysis**:

```python
# Line 66-77 - PIDs read from file and killed without validation
pids = _PID_FILE.read_text().strip().split('\n')
for pid_str in pids:
    if not pid_str:
        continue
    try:
        pid = int(pid_str)
        os.kill(pid, 0)  # Check exists - but doesn't verify ownership!
        os.kill(pid, signal.SIGTERM)  # DANGEROUS: kills any process
```

**Additional concerns**:

- No validation that the PID belongs to this application
- No validation that the process was started by the same user
- Signal 0 only checks existence, not ownership
- File permissions are not set (defaults to 644, readable by all)

**Fix Required**:

1. Store PID file in application-specific directory (e.g., `/var/run/feedforward/` or `~/.feedforward/`)
2. Set restrictive permissions (0600)
3. Validate process belongs to this application by checking `/proc/{pid}/cmdline` or process name
4. Consider using a lockfile mechanism instead

---

### S2: Verbose Debug Print Statements Leak Internal State (HIGH)

**Location**: `src/intercom_client.py` lines 182-315, 332-445

**Description**: The async methods contain numerous `print()` statements that output debugging information directly to stdout. In a production environment, this could leak sensitive operational data.

**Examples of leaky prints**:

```python
# Line 182 - Leaks API endpoint and params
print(f"[ASYNC] Starting {method} request to {endpoint}, params={params}", flush=True)

# Line 269 - Leaks date filtering parameters
print(f"[ASYNC FETCH] Starting fetch_conversations_async, since={since}, max_pages={max_pages}", flush=True)

# Line 309 - Leaks pagination cursors (could be session tokens)
print(f"[ASYNC FETCH] Moving to page {page_count + 1}, starting_after={starting_after[:20]}...", flush=True)

# Line 339 - Leaks timestamp boundaries
print(f"[ASYNC QUALITY] Date range: {since} ({start_ts}) to {until} ({end_ts})", flush=True)
```

**Security Implications**:

- Information disclosure if logs are accessible (common in containerized deployments)
- Pagination cursors may contain encoded session state
- Timestamp information aids reconnaissance for timing attacks
- Violates principle of least privilege for logging

**Fix Required**:

1. Replace all `print()` with proper `logger.debug()` calls
2. Ensure production logging level is INFO or higher
3. Review what data is being logged and sanitize sensitive fields

---

### S3: Missing Rate Limiting on API Endpoints (HIGH)

**Location**: `src/api/routers/pipeline.py` - All endpoints

**Description**: The pipeline endpoints lack rate limiting, allowing potential resource exhaustion attacks.

**Affected Endpoints**:

- `POST /api/pipeline/run` - Starts expensive background tasks
- `POST /api/pipeline/stop` - Can be spammed
- `POST /api/pipeline/{run_id}/create-stories` - Triggers LLM calls
- `GET /api/pipeline/status/{run_id}` - Could be polled aggressively

**Attack Scenario**:
While only one pipeline run can be active at a time (checked at line 831-835), an attacker could:

1. Spam the `/run` endpoint with 409 responses wasting server resources
2. Aggressively poll `/status` endpoints causing DB connection exhaustion
3. Repeatedly call `/stop` and `/run` in sequence to disrupt operations

**Mitigation Already Present** (partial):

```python
# Line 831-835 - Basic check prevents concurrent runs
active = [rid for rid, status in _active_runs.items() if status == "running"]
if active:
    raise HTTPException(status_code=409, ...)
```

**Fix Required**:

1. Add rate limiting middleware (e.g., `slowapi` or custom FastAPI dependency)
2. Consider IP-based throttling for mutation endpoints
3. Add exponential backoff hints in 409/429 responses

---

## Medium Findings

### S4: SQL Injection Protection Exists But Pattern Is Risky (MEDIUM)

**Location**: `src/api/routers/pipeline.py` lines 311-343

**Description**: The `_update_phase` function uses f-strings to build SQL queries with field names. While there is a whitelist (`_ALLOWED_PHASE_FIELDS`), the pattern is error-prone.

**Current Protection** (good):

```python
# Line 311-316 - Whitelist exists
_ALLOWED_PHASE_FIELDS = frozenset({
    "themes_extracted", "themes_new", "stories_created", ...
})

# Line 324-325 - Validation before use
if field not in _ALLOWED_PHASE_FIELDS:
    raise ValueError(f"Invalid field for phase update: {field}")
```

**Concern**:
The f-string SQL construction at lines 335-341 is a code smell. If a developer adds a field to the whitelist without sanitization, SQL injection becomes possible.

```python
# Line 333-341 - Dynamic SQL construction
for field, value in extra_fields.items():
    set_clause += f", {field} = %s"  # field from whitelist, safe
    values.append(value)             # value parameterized, safe
```

**Assessment**: Currently SAFE due to whitelist, but flagged as risky pattern. Recommend using an ORM or query builder instead.

---

### S5: Insufficient Input Validation on Pipeline Parameters (MEDIUM)

**Location**: `src/api/routers/pipeline.py` lines 804-883, `src/two_stage_pipeline.py`

**Description**: The pipeline accepts `days` and `concurrency` parameters without upper bounds, potentially enabling resource exhaustion.

**Code Analysis**:

```python
# From PipelineRunRequest schema (not shown but inferred from usage)
# days: int - no maximum
# concurrency: int - default 20, no maximum
```

**Attack Scenario**:

- `days=10000` could attempt to fetch years of conversations
- `concurrency=1000` could overwhelm the Intercom API or local resources

**Recommendation**: Add reasonable bounds (e.g., days <= 365, concurrency <= 50).

---

## Informational Notes

### I1: Access Token Handling (LOW RISK)

The Intercom access token is handled via environment variable and passed in Authorization headers. This is acceptable but ensure:

- Token is not logged (checked: the print statements do NOT include the token)
- Token is rotated periodically
- Token has minimum required scopes

### I2: Exception Handling Could Leak Stack Traces

Error messages like `f"Classification error: {str(e)}"` (line 269-270 in two_stage_pipeline.py) could expose internal information. Consider generic error messages in production.

---

## Verification Needed

1. **V1**: Confirm the intended deployment environment for PID file security model
2. **V2**: Verify if print statements will be removed before production deployment
3. **V3**: Check if rate limiting is handled at a different layer (API gateway, nginx)

---

## Summary

| ID  | Severity | Category       | Issue                                    |
| --- | -------- | -------------- | ---------------------------------------- |
| S1  | CRITICAL | injection/auth | PID file TOCTOU + arbitrary process kill |
| S2  | HIGH     | exposure       | Debug prints leak internal state         |
| S3  | HIGH     | rate-limit     | Missing rate limiting on endpoints       |
| S4  | MEDIUM   | injection      | Risky SQL pattern (currently protected)  |
| S5  | MEDIUM   | validation     | Missing bounds on pipeline parameters    |

**Verdict: BLOCK** - S1 (arbitrary process kill) and S2 (information disclosure) must be fixed before merge.
