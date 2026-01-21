# Sanjay Security Review - PR #87 Round 1

**Verdict**: REQUEST_CHANGES
**Date**: 2026-01-21

## Summary

This PR introduces retry logic for Intercom API calls to handle transient 5xx errors and connection failures. The implementation follows reasonable patterns (exponential backoff, 4xx no-retry) but has **one CRITICAL security issue** and **one HIGH-severity concern** that must be addressed. The retry logic itself is sound, but error logging could leak sensitive information, and the timeout configuration lacks safeguards against resource exhaustion attacks.

---

## S1: Potential Information Leakage in Error Logs

**Severity**: CRITICAL | **Confidence**: High | **Scope**: Isolated

**File**: `src/intercom_client.py:115-118, 134-137`

### The Problem

The retry warning logs include the full exception object and endpoint path without sanitization. If an attacker can trigger errors (e.g., by causing connection failures through network manipulation or by triggering specific 5xx responses), these logs may leak:

1. **Internal API structure** - Full endpoint paths reveal API design
2. **Authentication tokens** - Exception messages might include headers or request context
3. **Infrastructure details** - Connection errors expose network topology, internal IPs, or DNS names
4. **Sensitive query parameters** - If endpoints include user IDs, org IDs, or other identifiers in the URL

### Attack Scenario

1. Attacker has limited access to logs (e.g., through a compromised monitoring dashboard, log aggregation service, or error tracking tool like Sentry)
2. Attacker triggers connection errors or 5xx responses by:
   - Network manipulation (DNS poisoning, routing attacks)
   - API abuse causing rate limits or 503 responses
   - Timing attacks during Intercom maintenance windows
3. Error logs reveal internal endpoint structures, authentication context, or user identifiers
4. Result: Information disclosure enables reconnaissance for further attacks

### Current Code

```python
logger.warning(
    f"Intercom API error {response.status_code} on {endpoint}, "
    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
)

# ...

logger.warning(
    f"Intercom API connection error: {e}, "
    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
)
```

**Issues:**
- Exception `{e}` is logged directly - may include sensitive context
- Endpoint paths may contain sensitive IDs (e.g., `/contacts/{contact_id}`)
- No sanitization or masking of potentially sensitive data

### Suggested Fix

```python
# Sanitize endpoint for logging (mask IDs, preserve structure)
def _sanitize_endpoint(self, endpoint: str) -> str:
    """Mask sensitive IDs in endpoints for logging."""
    # Replace numeric IDs with placeholder
    import re
    sanitized = re.sub(r'/\d+', '/***', endpoint)
    return sanitized

# In retry logic:
sanitized_endpoint = self._sanitize_endpoint(endpoint)
logger.warning(
    f"Intercom API error {response.status_code} on {sanitized_endpoint}, "
    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
)

# For connection errors, log exception type but NOT full message:
logger.warning(
    f"Intercom API connection error ({type(e).__name__}) on {sanitized_endpoint}, "
    f"retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
)
```

### Related Concerns

- Check all other logging statements in the file for similar issues
- Review log aggregation configuration - who has access to these logs?
- Consider if error tracking tools (Sentry, DataDog) are configured to scrub sensitive data

---

## S2: Missing Timeout Bounds Validation

**Severity**: HIGH | **Confidence**: High | **Scope**: Systemic

**File**: `src/intercom_client.py:68-74`

### The Problem

The `timeout` parameter in `__init__` accepts arbitrary tuples without validation. An attacker or misconfigured code could pass extremely large timeouts, enabling resource exhaustion attacks:

1. **Denial of Service** - Huge timeouts (e.g., `(3600, 3600)` = 1 hour) tie up connections and threads
2. **Thread pool exhaustion** - Long-running requests in async batch operations block other work
3. **No upper bound enforcement** - Unlike `max_retries` which has a class default, timeout can be arbitrarily large

### Attack Scenario

1. Attacker controls environment variables or configuration files that influence timeout settings
2. Attacker sets absurdly high timeouts (e.g., 10 minutes, 1 hour)
3. System makes Intercom API calls that hang for extended periods during:
   - Network issues
   - Slow API responses
   - Attacker-induced delays (e.g., slowloris-style attacks if they can MITM)
4. Result: Application threads/workers exhausted, service becomes unresponsive

### Current Code

```python
def __init__(self, access_token: Optional[str] = None, timeout: tuple = None, max_retries: int = None):
    # ...
    self.timeout = timeout or self.DEFAULT_TIMEOUT
    self.max_retries = max_retries if max_retries is not None else self.MAX_RETRIES
```

**Issues:**
- No validation that `timeout` is a 2-tuple
- No upper bounds on timeout values
- No type checking (could pass non-numeric values)

### Suggested Fix

```python
# Add class constant for maximum allowed timeout
MAX_TIMEOUT_CONNECT = 30  # Max 30s to connect
MAX_TIMEOUT_READ = 300    # Max 5 minutes to read

def __init__(self, access_token: Optional[str] = None, timeout: tuple = None, max_retries: int = None):
    self.access_token = access_token or os.getenv("INTERCOM_ACCESS_TOKEN")
    if not self.access_token:
        raise ValueError("INTERCOM_ACCESS_TOKEN not set")

    # Validate and bound timeout
    if timeout is not None:
        if not isinstance(timeout, tuple) or len(timeout) != 2:
            raise ValueError("timeout must be a 2-tuple (connect_timeout, read_timeout)")
        
        connect_timeout, read_timeout = timeout
        if not isinstance(connect_timeout, (int, float)) or not isinstance(read_timeout, (int, float)):
            raise ValueError("timeout values must be numeric")
        
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("timeout values must be positive")
        
        if connect_timeout > self.MAX_TIMEOUT_CONNECT:
            raise ValueError(f"connect_timeout cannot exceed {self.MAX_TIMEOUT_CONNECT}s")
        
        if read_timeout > self.MAX_TIMEOUT_READ:
            raise ValueError(f"read_timeout cannot exceed {self.MAX_TIMEOUT_READ}s")
        
        self.timeout = timeout
    else:
        self.timeout = self.DEFAULT_TIMEOUT

    # Validate max_retries
    if max_retries is not None and max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    
    self.max_retries = max_retries if max_retries is not None else self.MAX_RETRIES
```

### Related Concerns

- `fetch_contact_org_ids_batch` uses `timeout` but doesn't validate it either (lines 292-295)
- All scripts/tools that instantiate `IntercomClient` should be reviewed for timeout configuration

---

## S3: fetch_contact_org_id Missing Retry Logic

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/intercom_client.py:246-261`

### The Problem

The `fetch_contact_org_id` method makes a direct `self.session.get()` call without using the retry wrapper. This creates inconsistent behavior:

1. **Reliability regression** - While most API calls now have retry logic, this one doesn't
2. **Silent failures** - Returns `None` on any exception, masking transient vs permanent errors
3. **Inconsistent error handling** - Other methods raise exceptions, this one swallows them

This isn't a direct security vulnerability, but it creates observability gaps that could hide attacks or misconfigurations.

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
        contact = response.json()
        custom_attrs = contact.get("custom_attributes", {})
        return custom_attrs.get("account_id")
    except requests.RequestException:
        return None  # Silently swallows ALL errors
```

### Suggested Fix

```python
def fetch_contact_org_id(self, contact_id: str) -> Optional[str]:
    """Fetch org_id from contact's custom_attributes.account_id."""
    if not contact_id:
        return None

    try:
        # Use the retry-enabled _get method
        contact = self._get(f"/contacts/{contact_id}")
        custom_attrs = contact.get("custom_attributes", {})
        return custom_attrs.get("account_id")
    except requests.RequestException as e:
        # Log but still return None for compatibility
        logger.warning(f"Failed to fetch org_id for contact (error type: {type(e).__name__})")
        return None
```

### Related Concerns

- `fetch_contact_org_ids_batch` already implements its own retry-like logic via async - verify it handles transient errors correctly
- Consider deprecating `fetch_contact_org_id` in favor of the batch method for consistency

---

## S4: Test Coverage Gap - Malformed Response Bodies

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `tests/test_intercom_retry.py` (gap)

### The Problem

The test suite doesn't verify behavior when:
1. Response has 200 status but invalid JSON body
2. Response has 200 status but `.json()` raises exception
3. Network succeeds but response is truncated/corrupted

While the implementation calls `response.json()` (line 127 in `intercom_client.py`), there's no test coverage for JSON parsing failures after a successful HTTP response.

### Suggested Test

```python
def test_json_decode_error_handling(self, client):
    """Test handling of malformed JSON in response body."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Invalid JSON", "", 0)
    
    with patch.object(client.session, "get", return_value=mock_response):
        with pytest.raises(requests.exceptions.JSONDecodeError):
            client._get("/test")
```

**Why this matters:** If Intercom's API returns malformed JSON (e.g., during an outage, load balancer misconfiguration, or MITM attack), the error should be raised clearly rather than silently failing or causing confusing stack traces.

---

## Positive Security Findings

These are good practices observed in the code:

1. **No retry on 4xx** - Correctly avoids retrying client errors (400, 401, etc.)
2. **Exponential backoff** - Prevents thundering herd problems
3. **Bounded retries** - `MAX_RETRIES = 3` prevents infinite loops
4. **Connection error retry** - Handles transient network issues
5. **Timeout enforcement** - All requests have timeouts (prevents indefinite hangs)
6. **Token not in code** - Uses environment variable for `INTERCOM_ACCESS_TOKEN`

---

## Recommendation Summary

| Issue | Severity | Action Required |
|-------|----------|-----------------|
| S1: Information leakage in logs | CRITICAL | Sanitize endpoints and exception messages |
| S2: Missing timeout validation | HIGH | Add bounds checking and validation |
| S3: Inconsistent retry behavior | MEDIUM | Use `_get()` wrapper in `fetch_contact_org_id` |
| S4: Missing test coverage | LOW | Add JSON decode error test |

**Verdict: REQUEST_CHANGES**

Must fix S1 and S2 before merge. S3 is strongly recommended. S4 is nice-to-have.
