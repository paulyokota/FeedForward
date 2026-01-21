# Security Review: PR #72 - Evidence Accept/Reject Workflow

**Reviewer**: Sanjay (Security Auditor)
**PR**: #72 - feat(evidence): Implement suggested evidence accept/reject workflow
**Round**: 1
**Date**: 2026-01-20

---

## Executive Summary

This PR implements an accept/reject workflow for suggested evidence in the story tracking system. The implementation is **reasonably secure** for an internal tool, with proper input validation and parameterized queries. However, there are notable gaps around authentication/authorization that should be addressed before production use with sensitive data.

**Verdict**: PASS WITH OBSERVATIONS (no blocking issues, but document known limitations)

---

## Files Reviewed

1. `src/api/routers/research.py` - Backend API endpoints
2. `tests/test_research.py` - Test coverage
3. `webapp/src/lib/api.ts` - Frontend API client
4. `webapp/src/components/SuggestedEvidence.tsx` - React UI component
5. `webapp/src/components/__tests__/SuggestedEvidence.test.tsx` - Frontend tests
6. `src/db/migrations/007_suggested_evidence_decisions.sql` - Database schema
7. `src/research/models.py` - Pydantic models

---

## Security Analysis

### 1. SQL Injection Protection - GOOD

**Status**: Protected

The implementation uses parameterized queries throughout:

```python
# research.py line 253-258
cur.execute("""
    SELECT title, description
    FROM stories
    WHERE id = %s
""", (str(story_id),))
```

```python
# research.py line 405-416
cur.execute(
    """
    INSERT INTO suggested_evidence_decisions
        (story_id, evidence_id, source_type, source_id, decision, similarity_score, decided_at)
    VALUES (%s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (story_id, evidence_id)
    DO UPDATE SET ...
    """,
    (str(story_id), evidence_id, source_type, source_id, decision, similarity_score)
)
```

All user-controlled inputs are passed as parameters, not string-concatenated.

---

### 2. Input Validation - GOOD

**Status**: Properly Validated

**Backend Validation** (research.py):

- `story_id` is typed as `UUID` in FastAPI path parameter - FastAPI validates UUID format automatically
- `evidence_id` is validated with custom `_parse_evidence_id()` function:
  - Checks for colon separator (line 341-345)
  - Validates source_type against whitelist `VALID_SOURCE_TYPES` (line 357-361)
  - Ensures both source_type and source_id are non-empty (line 351-355)

**Database Constraints** (migration 007):

- CHECK constraints on `decision` values: `CHECK (decision IN ('accepted', 'rejected'))`
- CHECK constraints on `source_type`: `CHECK (source_type IN ('coda_page', 'coda_theme', 'intercom'))`
- NOT NULL constraints on critical fields
- Empty string prevention: `CHECK (evidence_id != '')`

**Frontend** (api.ts):

- Uses `encodeURIComponent()` on evidenceId (line 272, 284) - proper URL encoding

---

### 3. Authentication & Authorization - OBSERVATION (S1)

**Issue ID**: S1
**Severity**: Medium (Informational for internal tool)
**Category**: Missing Access Control

**Finding**: There is NO authentication or authorization on the evidence decision endpoints:

```python
# research.py line 438-485
@router.post("/stories/{story_id}/suggested-evidence/{evidence_id}/accept", ...)
def accept_evidence(
    story_id: UUID,
    evidence_id: str,
    db=Depends(get_db),
):
    # No auth check - anyone can accept/reject evidence
```

**Impact**: Any user (or automated script) can:

- Accept or reject evidence for any story
- Change decisions made by other users
- No audit trail of WHO made the decision

**Current State**: The codebase has a TODO at line 209:

```python
# TODO: Add authentication check for admin
# For now, this endpoint is available to all users
```

**Recommendation**:

- For internal tool: Document this limitation
- For production: Add user authentication and record `decided_by` user ID

---

### 4. IDOR (Insecure Direct Object Reference) - OBSERVATION (S2)

**Issue ID**: S2
**Severity**: Low
**Category**: Access Control

**Finding**: Users can accept/reject evidence for ANY story by guessing/enumerating UUIDs:

```
POST /api/research/stories/{any-story-uuid}/suggested-evidence/{evidence-id}/accept
```

**Current Mitigation**: Story IDs are UUIDs, making enumeration impractical (2^122 possible values).

**Recommendation**: If story ownership matters, add ownership validation.

---

### 5. Rate Limiting - OBSERVATION (S3)

**Issue ID**: S3
**Severity**: Low
**Category**: Denial of Service

**Finding**: No rate limiting on evidence decision endpoints. An attacker could:

- Rapidly flip evidence decisions between accept/reject
- Spam the database with rapid writes
- Potentially cause database contention

**Recommendation**: Add rate limiting (e.g., X decisions per minute per IP/session).

---

### 6. Error Information Disclosure - GOOD

**Status**: Properly Handled

Error handling does not leak sensitive information:

```python
# research.py line 425-435
except IntegrityError as e:
    error_str = str(e).lower()
    if "foreign key" in error_str or "fk_" in error_str:
        raise HTTPException(
            status_code=404,
            detail=f"Story {story_id} not found"  # Generic message
        )
    logger.error("Database integrity error...", exc_info=True)  # Logged server-side
    raise HTTPException(
        status_code=500,
        detail="Failed to record evidence decision"  # Generic message
    )
```

Database error details are logged server-side but not exposed to clients.

---

### 7. XSS Protection - GOOD

**Status**: React provides automatic escaping

The frontend renders user-controlled data (title, snippet) through JSX:

```tsx
// SuggestedEvidence.tsx line 208-209
<h4 className="suggestion-title">{suggestion.title}</h4>
<p className="suggestion-snippet">{suggestion.snippet}</p>
```

React automatically escapes these values, preventing XSS.

The external link uses proper attributes:

```tsx
// line 278-279
rel = "noopener noreferrer";
```

---

### 8. CSRF Protection - OBSERVATION (S4)

**Issue ID**: S4
**Severity**: Low
**Category**: Cross-Site Request Forgery

**Finding**: No explicit CSRF protection visible. The endpoints use POST requests which is good, but there's no CSRF token validation.

**Current Mitigation**:

- Modern browsers' SameSite cookie defaults provide some protection
- Application appears to use JSON content type which adds a layer of protection

**Recommendation**: Ensure proper CORS configuration and consider adding CSRF tokens for state-changing operations.

---

### 9. Logging & Audit Trail - GOOD (with caveat)

**Status**: Partial Implementation

Decisions are logged:

```python
# research.py line 478
logger.info(f"Evidence accepted: story={story_id}, evidence={evidence_id}")
```

Database records `decided_at` timestamp. However, NO user identity is recorded (relates to S1).

---

### 10. Database Schema Security - GOOD

**Status**: Well-designed constraints

The migration (007) includes:

- Primary key with UUID
- Foreign key with CASCADE delete (proper cleanup)
- UNIQUE constraint preventing duplicate decisions
- CHECK constraints on enum values
- Index for query performance

---

## Test Coverage Assessment

**Backend Tests**: Comprehensive

- Happy path tests for accept/reject
- Validation tests for invalid evidence format
- Error handling tests for story not found
- State transition tests (accept->reject, reject->accept)

**Frontend Tests**: Comprehensive (21 tests)

- Loading states
- Empty states
- Action buttons based on status
- API call verification
- Error handling
- Processing state (disabled buttons)

---

## OWASP Top 10 Checklist

| Vulnerability                      | Status  | Notes                                |
| ---------------------------------- | ------- | ------------------------------------ |
| A01:2021 Broken Access Control     | OBSERVE | S1, S2 - No auth/authz               |
| A02:2021 Cryptographic Failures    | N/A     | No sensitive data encryption needed  |
| A03:2021 Injection                 | PASS    | Parameterized queries                |
| A04:2021 Insecure Design           | PASS    | Reasonable design for internal tool  |
| A05:2021 Security Misconfiguration | OBSERVE | S3 - No rate limiting                |
| A06:2021 Vulnerable Components     | N/A     | No new dependencies                  |
| A07:2021 Auth Failures             | OBSERVE | S1 - No authentication               |
| A08:2021 Data Integrity Failures   | PASS    | DB constraints + validation          |
| A09:2021 Logging Failures          | PASS    | Actions logged (user missing)        |
| A10:2021 SSRF                      | N/A     | No server-side requests to user URLs |

---

## Issues Summary

| ID  | Severity | Category       | Title                                            |
| --- | -------- | -------------- | ------------------------------------------------ |
| S1  | Medium   | Access Control | No authentication on evidence decision endpoints |
| S2  | Low      | Access Control | IDOR - can modify evidence for any story         |
| S3  | Low      | DoS            | No rate limiting on decision endpoints           |
| S4  | Low      | CSRF           | No explicit CSRF protection                      |

---

## Recommendations

### Must Address (before production with sensitive data):

1. **S1**: Add authentication layer and record `decided_by` user ID

### Should Address (defense in depth):

2. **S3**: Add rate limiting
3. **S4**: Verify CORS configuration and consider CSRF tokens

### Nice to Have:

4. **S2**: Add story ownership validation if needed
5. Add audit log table for decision history (who, when, old value, new value)

---

## Conclusion

The code is well-written from a security perspective with proper input validation, parameterized queries, and reasonable error handling. The main gap is authentication/authorization, which is a known limitation documented in the codebase (TODO comment).

For an **internal tool**, this is acceptable with the documented limitations. For **production use with external users or sensitive data**, S1 must be addressed.

**Final Verdict**: PASS WITH OBSERVATIONS
