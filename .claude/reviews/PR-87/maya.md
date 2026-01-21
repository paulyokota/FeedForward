# Maya Maintainability Review - PR #87 Round 1

**Verdict**: REQUEST_CHANGES
**Date**: 2026-01-21

## Summary

This PR implements retry logic for the Intercom API client, which is a solid reliability improvement. However, there are several maintainability concerns that will make it harder for future developers to understand, debug, and modify this code. The main issues are: magic numbers without explanation, missing context about retry strategy decisions, and inconsistent application of retry logic across API methods. Additionally, one method bypasses the retry mechanism entirely, which could lead to confusion about when retries happen.

---

## M1: Magic Numbers in Retry Configuration

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/intercom_client.py:54-57`

### The Problem

The retry configuration uses hardcoded values without explaining WHY these specific values were chosen:

```python
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds (exponential backoff: 2s, 4s, 8s)
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
```

While there's a comment showing the backoff sequence, it doesn't explain:
- Why 3 retries instead of 2 or 5?
- Why 2 seconds base instead of 1 or 3?
- Why only these specific 5xx codes?
- What was the reasoning or research that led to these values?

### The Maintainer's Test

- Can I understand without author? **Partially** - I see WHAT happens but not WHY
- Can I debug at 2am? **No** - If failures persist, I won't know if these limits are appropriate
- Can I change without fear? **No** - I don't know if these values came from Intercom docs or empirical testing
- Will this make sense in 6 months? **No** - The reasoning will be lost

### Current Code

```python
# Retry configuration for transient errors (5xx)
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds (exponential backoff: 2s, 4s, 8s)
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
```

### Suggested Improvement

```python
# Retry configuration for transient errors (5xx)
# Values based on Intercom API documentation recommendations:
# - 3 retries provides good balance between resilience and fast failure
# - 2s base with exponential backoff (2s, 4s, 8s) = 14s total retry window
# - Total max time: 14s retry + 40s timeout (10s connect + 30s read) = ~54s worst case
# - Only retry server errors; 4xx indicates client error (bad request, auth, etc.)
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds (exponential backoff: 2s, 4s, 8s)
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}  # All server-side error codes
```

### Why This Matters

When debugging production issues or tuning performance, future developers need to know:
1. Whether these values can be adjusted
2. What constraints guided the original choices
3. What the total worst-case latency is (retries + timeouts)

Without this context, someone might cargo-cult these values into other API clients or be afraid to tune them when needed.

---

## M2: Complex Retry Loop Without Algorithm Explanation

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/intercom_client.py:84-145`

### The Problem

The `_request_with_retry` method implements a complex retry algorithm with several edge cases, but the docstring doesn't explain the algorithm flow. A reader has to trace through the code to understand:
- When does it retry vs raise immediately?
- What happens on the final retry attempt?
- Why are there two different exception handling paths?
- What's the relationship between `attempt` counter and `max_retries`?

### The Maintainer's Test

- Can I understand without author? **No** - Need to trace code flow
- Can I debug at 2am? **No** - Would struggle to predict behavior
- Can I change without fear? **No** - Complex branching logic is fragile
- Will this make sense in 6 months? **No** - Algorithm is implicit

### Current Code

```python
def _request_with_retry(
    self,
    method: str,
    endpoint: str,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
) -> dict:
    """
    Make an HTTP request with retry on transient errors.

    Retries on:
    - 5xx server errors (500, 502, 503, 504)
    - Connection errors (network issues, timeouts)

    Does NOT retry on:
    - 4xx client errors (these indicate a problem with the request)
    """
```

### Suggested Improvement

```python
def _request_with_retry(
    self,
    method: str,
    endpoint: str,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
) -> dict:
    """
    Make an HTTP request with retry on transient errors.

    Retry algorithm:
    1. Try request (attempt 0)
    2. If 5xx status code:
       - Retry with exponential backoff (2s, 4s, 8s)
       - On final attempt, raise HTTPError
    3. If 4xx status code:
       - Raise immediately (no retry - client error)
    4. If connection/timeout error:
       - Retry with exponential backoff
       - On final attempt, re-raise original exception
    5. If 2xx status code:
       - Return JSON response

    Total attempts = 1 + MAX_RETRIES (default: 4 attempts)

    Retries on:
    - 5xx server errors (500, 502, 503, 504)
    - Connection errors (network issues, timeouts)

    Does NOT retry on:
    - 4xx client errors (these indicate a problem with the request)
    """
```

### Why This Matters

Complex retry logic is notoriously hard to reason about. When debugging why a request failed after retries, or why it didn't retry when expected, developers need to quickly understand the decision tree without stepping through code. Clear algorithm documentation prevents bugs during modifications.

---

## M3: Unclear Fallback Logic

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `src/intercom_client.py:142-145`

### The Problem

The fallback at the end of the retry loop is confusing:

```python
# Should not reach here, but just in case
if last_exception:
    raise last_exception
raise RuntimeError("Unexpected retry loop exit")
```

This code suggests the author wasn't confident about the loop termination logic. A future maintainer will wonder: "Can this actually be reached? Under what conditions?"

### The Maintainer's Test

- Can I understand without author? **No** - Unclear what scenario this handles
- Can I debug at 2am? **No** - If I see this error, I won't know root cause
- Can I change without fear? **Maybe** - Might be dead code?
- Will this make sense in 6 months? **No** - "Just in case" is vague

### Current Code

```python
# Should not reach here, but just in case
if last_exception:
    raise last_exception
raise RuntimeError("Unexpected retry loop exit")
```

### Suggested Improvement

Either:
1. **Remove it** - If the loop logic is correct, this is dead code
2. **Document the edge case** - If there's a real scenario, explain it:

```python
# Defensive fallback: this should only be reached if max_retries=0 AND
# the first attempt raised an exception that wasn't caught above
# (e.g., unexpected exception type). In practice, should never happen.
if last_exception:
    raise last_exception
raise RuntimeError("Unexpected retry loop exit - please report this as a bug")
```

### Why This Matters

"Just in case" code suggests incomplete understanding. Either it's needed (document why) or it's dead code (remove it). Leaving it ambiguous creates maintenance burden.

---

## M4: Missing Error Handling Documentation

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `src/intercom_client.py:127`

### The Problem

The code assumes `response.json()` will succeed:

```python
response.raise_for_status()
return response.json()
```

But what if the API returns 200 OK with invalid JSON? This could happen during API incidents. There's no comment explaining whether this is intentional or an oversight.

### The Maintainer's Test

- Can I understand without author? **No** - Don't know if JSON errors are possible
- Can I debug at 2am? **No** - JSONDecodeError would be confusing
- Can I change without fear? **No** - Don't know if this is deliberate
- Will this make sense in 6 months? **No** - No rationale documented

### Current Code

```python
response.raise_for_status()
return response.json()
```

### Suggested Improvement

Add a comment explaining the assumption:

```python
response.raise_for_status()
# Note: We don't catch JSONDecodeError here. If Intercom returns
# malformed JSON, we want it to fail loudly rather than retry
# (since retry won't fix a server-side JSON generation bug).
return response.json()
```

Or handle it explicitly:

```python
response.raise_for_status()
try:
    return response.json()
except requests.exceptions.JSONDecodeError as e:
    logger.error(f"Intercom returned invalid JSON for {endpoint}: {e}")
    raise  # Don't retry - this is a server bug, not a transient error
```

### Why This Matters

Undocumented assumptions about error conditions make debugging harder. When this fails in production, the maintainer needs to know if it's expected or a bug.

---

## M5: Inconsistent Retry Application

**Severity**: HIGH | **Confidence**: High | **Scope**: Systemic

**File**: `src/intercom_client.py:246-261`

### The Problem

The `fetch_contact_org_id` method makes API calls but bypasses the retry mechanism:

```python
def fetch_contact_org_id(self, contact_id: str) -> Optional[str]:
    """Fetch org_id from contact's custom_attributes.account_id."""
    if not contact_id:
        return None

    try:
        response = self.session.get(
            f"{self.BASE_URL}/contacts/{contact_id}",
            timeout=self.timeout
        )
        response.raise_for_status()
        contact = response.json()
        # ... rest of method
```

This is inconsistent with the rest of the client, which uses `_get()` and `_post()` wrappers that provide retry logic. A future developer might:
1. Copy this pattern thinking retries aren't needed for contact fetching
2. Be confused why some API calls retry and others don't
3. Not realize this is susceptible to the same transient errors

### The Maintainer's Test

- Can I understand without author? **No** - Why is this method different?
- Can I debug at 2am? **Maybe** - But would be confused by inconsistency
- Can I change without fear? **No** - Don't know if bypass is intentional
- Will this make sense in 6 months? **No** - No explanation for difference

### Current Code

```python
def fetch_contact_org_id(self, contact_id: str) -> Optional[str]:
    """Fetch org_id from contact's custom_attributes.account_id."""
    if not contact_id:
        return None

    try:
        response = self.session.get(
            f"{self.BASE_URL}/contacts/{contact_id}",
            timeout=self.timeout
        )
        response.raise_for_status()
        # ...
    except requests.RequestException:
        return None
```

### Suggested Improvement

```python
def fetch_contact_org_id(self, contact_id: str) -> Optional[str]:
    """Fetch org_id from contact's custom_attributes.account_id."""
    if not contact_id:
        return None

    try:
        # Use _get to benefit from retry logic
        contact = self._get(f"/contacts/{contact_id}")
        custom_attrs = contact.get("custom_attributes", {})
        return custom_attrs.get("account_id")
    except requests.RequestException:
        # Swallow errors since org_id is optional enrichment data
        return None
```

### Why This Matters

**This is a systemic issue** - if one method bypasses retries, future developers might not realize retries are the standard pattern. Consistency in error handling is critical for reliability. This also means contact fetching is less resilient than conversation fetching, which seems unintentional.

---

## M6: Test Documentation Gap

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `tests/test_intercom_retry.py:172-195`

### The Problem

The exponential backoff test expects `[2, 4, 8]` but doesn't explain the formula in a way that helps verify correctness:

```python
def test_exponential_backoff_delays(self, client):
    """Test that retry delays follow exponential backoff."""
    # ...
    # Exponential backoff: 2^0 * 2 = 2, 2^1 * 2 = 4, 2^2 * 2 = 8
    assert sleep_calls == [2, 4, 8]
```

The comment shows the formula, but doesn't explain:
- Why exponent starts at 0 vs 1
- How this relates to the `attempt` counter in the code
- What happens on attempt 0 (no sleep expected)

### The Maintainer's Test

- Can I understand without author? **Partially** - Formula is there but context is thin
- Can I debug at 2am? **Maybe** - Would need to re-derive
- Can I change without fear? **No** - Don't fully understand mapping
- Will this make sense in 6 months? **Maybe** - Formula helps but incomplete

### Current Code

```python
# Exponential backoff: 2^0 * 2 = 2, 2^1 * 2 = 4, 2^2 * 2 = 8
assert sleep_calls == [2, 4, 8]
```

### Suggested Improvement

```python
# Exponential backoff formula: RETRY_DELAY_BASE * (2 ** attempt)
# Attempt 0 (initial): no sleep
# Attempt 1 (1st retry): 2 * (2^0) = 2s
# Attempt 2 (2nd retry): 2 * (2^1) = 4s
# Attempt 3 (3rd retry): 2 * (2^2) = 8s
# This test forces 3 failures + 1 success = 3 sleep calls
assert sleep_calls == [2, 4, 8]
```

### Why This Matters

Tests serve as executable documentation. When someone needs to modify the backoff algorithm (e.g., add jitter), clear test documentation helps them understand the current behavior and verify their changes preserve expected properties.

---

## Additional Observations (Not Blocking)

1. **Good**: The docstring at line 91-100 clearly lists what is/isn't retried
2. **Good**: Logging at lines 115-118 and 134-137 provides good debugging context
3. **Good**: Test coverage is comprehensive (11 test cases covering all branches)
4. **Suggestion**: Consider extracting retry logic to a decorator for reusability in future API clients

---

## Verdict

**REQUEST_CHANGES** - The retry logic is sound, but maintainability issues need addressing:

**Must Fix:**
- M5 (HIGH): Inconsistent retry application in `fetch_contact_org_id`
- M1 (MEDIUM): Magic numbers need context/rationale
- M2 (MEDIUM): Complex retry algorithm needs clearer documentation

**Should Fix:**
- M3 (LOW): Unclear fallback logic
- M4 (LOW): JSON error handling documentation
- M6 (LOW): Test documentation

These changes will make the code much easier to maintain, debug, and extend in the future.
