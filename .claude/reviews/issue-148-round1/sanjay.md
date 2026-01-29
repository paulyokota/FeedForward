# Security Review: Issue #148 - Pipeline Async Event Loop Changes

**Reviewer:** Sanjay - Security Guardian
**Date:** 2026-01-28
**Files Reviewed:**

- `src/api/routers/pipeline.py`
- `src/api/schemas/pipeline.py`
- `src/theme_extractor.py`

---

## Executive Summary

The Issue #148 changes introduce async parallelization to prevent event loop blocking during theme extraction. While the core implementation is sound, I identified **4 security issues** that require attention, including one HIGH severity issue related to resource exhaustion and one MEDIUM severity race condition in shared state.

---

## Detailed Findings

### S1: Unbounded In-Memory State Growth for Active Runs (HIGH)

**Location:** `src/api/routers/pipeline.py`, lines 43-48

**Description:**
The `_active_runs` dictionary tracks pipeline run states in memory but lacks size limits. While `_cleanup_terminal_runs()` is called at the start of new runs (line 1676), there's no protection against:

1. Many concurrent run attempts that fail validation (hit the "already running" check)
2. Server processes that handle requests but never start runs

**Code:**

```python
_active_runs: dict[int, str] = {}  # run_id -> status
_TERMINAL_STATES = {"stopped", "completed", "failed"}
```

**Security Impact:**
While `_cleanup_terminal_runs()` removes completed/failed runs, the dictionary could still grow if:

- Runs get stuck in "running" or "stopping" state due to bugs
- The cleanup only runs when starting NEW runs, not on periodic basis

**Risk:** Memory exhaustion (DoS) if runs accumulate without proper cleanup.

**Recommendation:**

1. Add a maximum size limit to `_active_runs` (e.g., 100 entries)
2. Add periodic cleanup or TTL for entries older than 24 hours
3. Add metrics/alerting for dictionary size

---

### S2: Race Condition in Concurrent Semaphore Access with Shared State (MEDIUM)

**Location:** `src/api/routers/pipeline.py`, lines 588-628 (`_run_theme_extraction_async`)

**Description:**
Multiple concurrent extraction tasks access shared state through the `ThemeExtractor` instance, specifically:

- `extractor.get_existing_signatures()` (line 614)
- Session signature cache (`_session_signatures` in theme_extractor.py, line 634)

The `extract_async` method uses `asyncio.to_thread()` which offloads to a thread pool. Multiple threads may concurrently read/write to `_session_signatures` dict:

```python
# theme_extractor.py, lines 766-779
def add_session_signature(self, signature: str, product_area: str, component: str) -> None:
    if signature in self._session_signatures:
        self._session_signatures[signature]["count"] += 1  # Race: read-modify-write
    else:
        self._session_signatures[signature] = {...}  # Race: check-then-set
```

**Security Impact:**

- Signature counts may be incorrect (minor data integrity issue)
- Potential for lost updates or inconsistent state during high concurrency
- Could theoretically cause theme fragmentation if deduplication fails

**Risk:** Data integrity issues in theme canonicalization under high load.

**Recommendation:**

1. Use `threading.Lock` to protect `_session_signatures` access
2. Or use `collections.defaultdict` with atomic operations
3. Consider per-run isolation of session signatures instead of shared instance

---

### S3: Error Message Leakage in Pipeline Status API (LOW)

**Location:** `src/api/routers/pipeline.py`, lines 1533-1535

**Description:**
When a pipeline fails, the raw exception message is stored directly in the database and returned to clients:

```python
except Exception as e:
    logger.error(f"Run {run_id}: Pipeline failed with error: {e}", exc_info=True)
    # ...
    cur.execute("""
        UPDATE pipeline_runs SET
            error_message = %s
        WHERE id = %s
    """, (datetime.now(timezone.utc), str(e), run_id))
```

**Security Impact:**
Raw exception messages may contain:

- Database connection strings or hostnames
- Internal file paths
- API error details from OpenAI/Intercom that include request IDs
- Stack trace information (when exception **str** includes it)

While this is an internal tool, exposing raw exceptions is a defense-in-depth violation.

**Recommendation:**

1. Sanitize error messages before storage (strip sensitive patterns)
2. Use error codes with generic user-facing messages
3. Store detailed errors in a separate debug log, not in the API response

---

### S4: Missing Authentication on Pipeline Control Endpoints (LOW)

**Location:** `src/api/routers/pipeline.py` (all endpoints), `src/api/main.py`

**Description:**
All pipeline control endpoints lack authentication:

- `POST /api/pipeline/run` - Start pipeline
- `POST /api/pipeline/stop` - Stop running pipeline
- `POST /api/pipeline/{run_id}/create-stories` - Trigger story creation
- `GET /api/pipeline/status/{run_id}` - View run status
- `GET /api/pipeline/history` - View all runs

The CORS configuration allows only localhost origins, which provides some protection, but:

- Any local process can call these endpoints
- In development, browser extensions or other tools could trigger runs
- No audit trail of who initiated runs

**Security Impact:**

- Unauthorized pipeline execution (resource consumption, API costs)
- No accountability for who triggered expensive operations
- Potential for abuse if server is exposed beyond localhost

**Recommendation:**

1. Add API key authentication for pipeline control endpoints
2. Add audit logging for who initiated each run
3. Consider rate limiting on `/run` endpoint
4. Document that this API should not be exposed publicly

---

## Additional Observations

### Positive Security Patterns Observed

1. **SQL Injection Protection:** The `_ALLOWED_PHASE_FIELDS` whitelist (lines 241-249) properly prevents SQL injection in dynamic queries.

2. **Concurrency Validation:** The Pydantic schema enforces `concurrency` between 1-20, preventing resource exhaustion from excessive parallelization.

3. **Graceful Shutdown:** The stop signal mechanism (`_is_stopping()`) allows clean termination without orphaned tasks.

4. **Token Limit Guard:** Theme extractor has MAX_PROMPT_CHARS guard (line 1026) preventing excessive token usage.

### Items Reviewed But Not Flagged

- Input validation on `days` (1-90 range enforced)
- `max_conversations` accepts None but is used safely
- Dry run preview storage has proper size limits (`_MAX_DRY_RUN_PREVIEWS = 5`)
- No prompt injection vectors identified in theme extraction (product context is from trusted files)

---

## Summary Table

| ID  | Severity | Issue                                       | File                            | Line             |
| --- | -------- | ------------------------------------------- | ------------------------------- | ---------------- |
| S1  | HIGH     | Unbounded in-memory state for active runs   | pipeline.py                     | 43-48            |
| S2  | MEDIUM   | Race condition in session signature cache   | pipeline.py, theme_extractor.py | 588-628, 766-779 |
| S3  | LOW      | Error message leakage in API response       | pipeline.py                     | 1533-1535        |
| S4  | LOW      | Missing authentication on control endpoints | pipeline.py, main.py            | All              |

---

## Verdict: CONDITIONAL PASS

The async changes themselves are well-implemented with proper semaphore controls. However, the HIGH severity issue (S1) should be addressed before production deployment, and the MEDIUM severity race condition (S2) warrants a fix in a follow-up PR.

**Recommended Actions:**

1. **Must Fix (S1):** Add size limit and TTL to `_active_runs` dictionary
2. **Should Fix (S2):** Add thread-safety to session signature cache
3. **Nice to Have (S3, S4):** Error sanitization and authentication improvements
