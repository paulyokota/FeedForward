# Maya's Maintainability Review - PR #100

**Reviewer**: Maya (The Maintainer)
**PR**: #100 - Search API for Pipeline
**Date**: 2026-01-21
**Review Round**: 1

---

## Summary

This PR adds async methods to `IntercomClient` for server-side date filtering using the Search API, updates the pipeline to use async fetch, and adds orphan worker cleanup to the pipeline router. While the functionality is sound, there are significant maintainability concerns that will hurt future developers.

---

## Critical Findings

### 1. **DEBUG PRINT STATEMENTS POLLUTING PRODUCTION CODE** (BLOCK)

**Location**: `src/intercom_client.py`, lines 182-315, 332-355, 409-445

The async methods are littered with `print()` statements that are clearly debug artifacts, not production logging:

```python
print(f"[ASYNC] Starting {method} request to {endpoint}, params={params}", flush=True)
print(f"[ASYNC] Attempt {attempt + 1}/{self.max_retries + 1} for {endpoint}", flush=True)
print(f"[ASYNC] About to call session.get({url})", flush=True)
print(f"[ASYNC] Got response status {response.status} for {endpoint}", flush=True)
```

**Why this matters**:

- These will spam production logs with hundreds of lines per pipeline run
- Mix of `print()` and `logger.warning()` makes log levels meaningless
- `[ASYNC]`, `[SEARCH API]`, `[PIPELINE]` prefixes suggest temporary debugging, not permanent logging
- Impossible to filter these from real issues in log aggregation

**Recommendation**: Remove all debug prints or convert to `logger.debug()` with proper log levels. The existing `logger` is already imported and used correctly for retry warnings.

---

### 2. **MAGIC NUMBER: `_MAX_DRY_RUN_PREVIEWS = 5`** (Minor)

**Location**: `src/api/routers/pipeline.py`, line 126

```python
_MAX_DRY_RUN_PREVIEWS = 5
```

While this has a comment explaining the memory limit, the number itself is arbitrary and not derived from any requirement.

**Why this matters**:

- If someone changes this, there's no way to know what value is appropriate
- No documentation of memory footprint per preview
- The comment says "1-5KB typical" but provides no basis for the limit of 5

**Recommendation**: Add a comment explaining the rationale (e.g., "At 5KB per preview, 5 previews = ~25KB max memory usage" or link to a decision document).

---

### 3. **IMPLICIT ASSUMPTION: PID file location** (Minor)

**Location**: `src/api/routers/pipeline.py`, line 53

```python
_PID_FILE = Path("/tmp/feedforward_pipeline_workers.pid")
```

**Why this matters**:

- Hardcoded to `/tmp` which may not exist or be writable in all environments
- Docker containers may not persist `/tmp` across restarts
- Multiple server instances could step on each other's PID files
- No documentation of why this location was chosen

**Recommendation**: Make configurable via environment variable with fallback, or document the assumption clearly.

---

### 4. **MISSING DOCSTRING ON KEY ASYNC METHOD**

**Location**: `src/intercom_client.py`, lines 166-236

`_request_with_retry_async` has no docstring, unlike its sync counterpart `_request_with_retry` which has a proper docstring explaining retry behavior.

```python
async def _request_with_retry_async(
    self,
    session: aiohttp.ClientSession,
    method: str,
    endpoint: str,
    params: Optional[dict] = None,
    json_data: Optional[dict] = None,
) -> dict:
    """
    Make an async HTTP request with retry on transient errors.

    Same retry logic as sync version but using aiohttp.
    """
```

The docstring says "Same retry logic as sync version" but doesn't explain:

- What errors are retried
- What the backoff strategy is
- Why `aiohttp` behaves differently

**Recommendation**: Copy the detailed docstring from `_request_with_retry` or reference it explicitly with link.

---

### 5. **DUPLICATED LOGIC: Retry handling in async vs sync** (Minor)

**Location**: `src/intercom_client.py`

The sync `_request_with_retry` (lines 91-151) and async `_request_with_retry_async` (lines 166-236) have duplicated retry logic with slight differences:

- Sync version catches `requests.exceptions.ConnectionError` and `requests.exceptions.Timeout`
- Async version catches `aiohttp.ClientError`

**Why this matters**:

- If retry logic changes, both need to be updated
- Easy to accidentally diverge the behavior
- The async version is harder to read due to all the debug prints

**Recommendation**: Extract retry parameters to constants or a shared configuration, and add a comment explaining the relationship between the two methods.

---

### 6. **UNCLEAR VARIABLE NAME: `_ALLOWED_PHASE_FIELDS`** (Minor)

**Location**: `src/api/routers/pipeline.py`, lines 312-317

```python
_ALLOWED_PHASE_FIELDS = frozenset({
    "themes_extracted", "themes_new", "stories_created", "orphans_created",
    "stories_ready", "auto_create_stories", "conversations_fetched",
    "conversations_classified", "conversations_stored", "conversations_filtered",
})
```

**Why this matters**:

- The name suggests these are "phase" fields but they're actually "pipeline_runs table columns"
- Used for SQL injection prevention but that's not obvious from the name
- No comment explaining why this whitelist exists

**Recommendation**: Rename to `_SAFE_PIPELINE_RUN_COLUMNS` or add a comment explaining it's a SQL injection safeguard.

---

### 7. **TIMESTAMP HANDLING: UTC vs local confusion**

**Location**: `src/intercom_client.py`, lines 336-337

```python
start_ts = int(since.timestamp()) if since else 0
end_ts = int(until.timestamp()) if until else int(datetime.utcnow().timestamp())
```

**Why this matters**:

- `since` and `until` parameters could be timezone-naive or timezone-aware
- If naive, `timestamp()` assumes local timezone
- `datetime.utcnow()` is deprecated in Python 3.12+
- Mix of potentially-local `since` with explicit UTC `utcnow()` could cause subtle date range bugs

**Recommendation**: Explicitly handle timezone-aware datetimes throughout, or add validation that inputs are UTC.

---

## The Maintainer's Test Results

| Question                                  | Answer    | Notes                                    |
| ----------------------------------------- | --------- | ---------------------------------------- |
| Can I understand this without the author? | Partially | Debug prints obscure the actual logic    |
| If this breaks at 2am, can I debug it?    | Yes       | Good error handling in retry logic       |
| Can I change this without fear?           | No        | Duplicated sync/async logic is fragile   |
| Would this make sense to me in 6 months?  | Partially | Core logic is clear, but cruft distracts |

---

## Verdict: **BLOCK**

The debug print statements are a blocker. They indicate code that wasn't production-ready when committed. The other issues are minor improvements that would help maintainability but don't need to block merge.

---

## Required Changes

1. **Remove all debug print statements** from `intercom_client.py` (lines 182-315, 332-355, 409-445, 478-500)
   - Either delete entirely or convert to `logger.debug()` with proper log configuration

## Suggested Improvements (Non-blocking)

1. Document the rationale for `_MAX_DRY_RUN_PREVIEWS = 5`
2. Make `_PID_FILE` location configurable or document the assumption
3. Copy the full docstring from sync to async retry method
4. Rename `_ALLOWED_PHASE_FIELDS` to be clearer about its purpose
5. Use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`
