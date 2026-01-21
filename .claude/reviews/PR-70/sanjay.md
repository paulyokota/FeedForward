# Security Review: PR #70
**Reviewer**: Sanjay (Security Expert)  
**Focus**: Security vulnerabilities and input validation  
**Date**: 2026-01-20

## Summary

Reviewed PR #70 "feat(pipeline): Add run summary with new stories panel" which adds `created_since` query parameter filtering to the Stories API and a new UI panel for viewing stories created during pipeline runs.

**Verdict**: ⚠️ REQUEST CHANGES - 3 security issues found

## Issues Found

### S1: SQL Injection Risk via Timestamp Parameter (Confidence: 85%)

**Severity**: HIGH  
**Location**: `src/story_tracking/services/story_service.py:248-249`

**Issue**:
The `created_since` parameter is passed directly to SQL query construction with minimal validation. While psycopg uses parameterized queries which provides some protection, there is no validation that the input is actually a valid ISO timestamp format before it reaches the database.

```python
if created_since:
    conditions.append("created_at >= %s")
    values.append(created_since)
```

The API endpoint accepts `created_since` as an `Optional[str]` with only a description, no validation:

```python
created_since: Optional[str] = Query(
    default=None,
    description="Filter to stories created at or after this ISO timestamp (e.g., 2024-01-15T10:30:00Z)",
),
```

**Attack Scenario**:
1. Attacker sends malformed timestamp: `created_since=invalid' OR '1'='1`
2. While psycopg parameterization prevents SQL injection, the database will throw an error when trying to parse the timestamp
3. Error messages could leak database schema information
4. Repeated invalid requests could be used for DoS

**Evidence**:
- No regex validation or parsing of ISO timestamp format
- No try/except wrapper around timestamp comparison in SQL
- Frontend passes value directly from `started_at` without validation
- No API tests for malformed timestamp input

**Recommended Fix**:
1. Add Pydantic validator or regex pattern to ensure ISO 8601 format:
```python
from datetime import datetime

created_since: Optional[str] = Query(
    default=None,
    description="Filter to stories created at or after this ISO timestamp (e.g., 2024-01-15T10:30:00Z)",
    regex=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$'
)
```

2. Validate in service layer:
```python
if created_since:
    try:
        datetime.fromisoformat(created_since.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f"Invalid ISO timestamp format: {created_since}")
    conditions.append("created_at >= %s")
    values.append(created_since)
```

---

### S2: Unauthorized Access to Sensitive Run Information (Confidence: 90%)

**Severity**: MEDIUM  
**Location**: `webapp/src/app/pipeline/page.tsx:74-85`, `src/api/routers/stories.py:40-63`

**Issue**:
The `created_since` filter allows querying stories by arbitrary timestamps with no authentication or authorization checks. This enables:

1. **Information Disclosure**: Any user can query all stories created during specific time windows
2. **Enumeration Attack**: Attacker can binary-search through time to discover when stories were created
3. **Privacy Violation**: Pipeline run history and story creation patterns are business-sensitive data

**Attack Scenario**:
1. Attacker discovers pipeline typically runs at specific times (visible in history)
2. Attacker queries `created_since` for those exact timestamps
3. Attacker gains access to all stories from that run without needing to view pipeline history
4. Attacker can correlate story creation with business activities/incidents

**Evidence**:
- No authentication decorator on `/api/stories` endpoint
- No authorization check for `created_since` parameter
- No rate limiting on list endpoint
- Frontend assumes unrestricted access to pipeline history
- No audit logging for sensitive queries

**Current Code**:
```python
@router.get("", response_model=StoryListResponse)
def list_stories(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    product_area: Optional[str] = Query(default=None, description="Filter by product area"),
    created_since: Optional[str] = Query(...),
    # NO AUTH CHECK HERE
    service: StoryService = Depends(get_story_service),
):
```

**Recommended Fix**:
1. Add authentication/authorization:
```python
from src.api.deps import get_current_user, require_permission

@router.get("", response_model=StoryListResponse)
def list_stories(
    # ... params ...
    current_user: User = Depends(get_current_user),
    service: StoryService = Depends(get_story_service),
):
    # Check if user has permission to filter by created_since
    if created_since and not current_user.has_permission("stories:filter_by_time"):
        raise HTTPException(status_code=403, detail="Permission denied")
```

2. Add audit logging:
```python
if created_since:
    logger.info(
        "Time-based story query",
        extra={"user": current_user.id, "created_since": created_since}
    )
```

3. Add rate limiting for this endpoint

---

### S3: Cross-Site Scripting (XSS) Risk in Story Display (Confidence: 80%)

**Severity**: MEDIUM  
**Location**: `webapp/src/app/pipeline/page.tsx:593-597`, `webapp/src/app/pipeline/page.tsx:577`

**Issue**:
Story titles and descriptions are rendered directly in the UI without explicit sanitization. While React provides some XSS protection by default, there's no Content Security Policy (CSP) header enforcement, and no explicit sanitization of story content.

**Attack Scenario**:
1. Attacker creates or modifies a story with XSS payload in title/description
2. Story appears in "New Stories Created" panel
3. XSS payload executes when panel is rendered
4. Attacker steals session tokens, performs actions as victim

**Evidence**:
```tsx
<span className="story-title">{story.title}</span>
...
<p className="story-description">
  {story.description.length > 120
    ? `${story.description.substring(0, 120)}...`
    : story.description}
</p>
```

While React escapes these by default, risks remain:
- No CSP headers detected in codebase
- No explicit sanitization library (DOMPurify, etc.)
- No validation of story content format on backend
- Story content could contain malicious HTML entities

**Recommended Fix**:
1. Add Content Security Policy headers:
```typescript
// In Next.js config or middleware
headers: [
  {
    key: 'Content-Security-Policy',
    value: "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'"
  }
]
```

2. Add explicit sanitization:
```typescript
import DOMPurify from 'dompurify';

<span className="story-title">
  {DOMPurify.sanitize(story.title)}
</span>
```

3. Validate story content on backend:
```python
from pydantic import validator

class StoryCreate(BaseModel):
    title: str
    description: Optional[str] = None
    
    @validator('title', 'description')
    def sanitize_html(cls, v):
        if v and ('<' in v or '>' in v or '&' in v):
            # Strip HTML tags or raise validation error
            raise ValueError("HTML content not allowed in story fields")
        return v
```

---

## Additional Observations

### O1: Missing Input Validation (Low Risk)
- `limit` and `offset` parameters have bounds (ge=1, le=200) but no validation for the combination
- No protection against requesting offset=1000000 which could cause performance issues
- Recommendation: Add max offset limit or pagination token approach

### O2: No Rate Limiting Evidence
- No decorators or middleware for rate limiting visible
- High-frequency queries with `created_since` could be used for DoS
- Recommendation: Add rate limiting to `/api/stories` endpoint

### O3: Error Information Leakage
- Database errors from invalid timestamps could leak schema information
- Recommendation: Add generic error handler that doesn't expose internals

---

## Testing Coverage Analysis

**Tests Reviewed**:
- `tests/test_story_tracking.py` - Lines 629-683

**Coverage**:
- ✅ Valid ISO timestamp filtering
- ✅ Combining filters (status + created_since)
- ✅ Optional parameter (None case)
- ❌ Invalid timestamp format
- ❌ Malformed SQL injection attempts
- ❌ Authorization checks
- ❌ XSS payloads in story content

**Recommendations**:
Add security test cases:
```python
def test_created_since_invalid_format_rejected(mock_db):
    """Malformed timestamp should raise validation error."""
    service = StoryService(db)
    with pytest.raises(ValueError):
        service.list(created_since="invalid' OR '1'='1")

def test_created_since_sql_injection_blocked(mock_db):
    """SQL injection attempt should be blocked."""
    service = StoryService(db)
    with pytest.raises(ValueError):
        service.list(created_since="2024-01-01'; DROP TABLE stories; --")
```

---

## Risk Assessment

| Issue | Severity | Likelihood | Impact | Priority |
|-------|----------|------------|--------|----------|
| S1: SQL Injection Risk | HIGH | MEDIUM | HIGH | P0 |
| S2: Unauthorized Access | MEDIUM | HIGH | MEDIUM | P1 |
| S3: XSS Risk | MEDIUM | LOW | HIGH | P1 |

**Overall Risk**: MEDIUM-HIGH

---

## Approval Status

**STATUS**: ⚠️ REQUEST CHANGES

**Blocking Issues**:
- S1 must be fixed (input validation)
- S2 should be addressed or explicitly acknowledged as acceptable risk

**Non-Blocking**:
- S3 can be addressed in follow-up if React's default escaping is deemed sufficient
- Additional observations can be tracked as technical debt

---

## References

- [OWASP Top 10 - Injection](https://owasp.org/www-project-top-ten/)
- [OWASP - Broken Access Control](https://owasp.org/www-project-top-ten/)
- [OWASP - XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [ISO 8601 Timestamp Format](https://en.wikipedia.org/wiki/ISO_8601)
