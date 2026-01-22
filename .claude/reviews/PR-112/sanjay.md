# Security Review: PR #112 - Fix run scoping with pipeline_run_id

**Reviewer**: Sanjay (Security Auditor)
**PR**: #112 - Fix run scoping: use pipeline_run_id instead of timestamp heuristics
**Round**: 1
**Date**: 2026-01-22
**Verdict**: BLOCK (2 CRITICAL, 1 HIGH, 2 MEDIUM issues)

---

## Executive Summary

This PR introduces a foreign key relationship to replace timestamp heuristics for run scoping. While the core approach is sound, **critical security gaps exist**:

1. **CRITICAL**: Missing foreign key cascade behavior creates orphan data vulnerability
2. **CRITICAL**: No authorization controls on API endpoints exposing pipeline_run_id
3. **HIGH**: SQL injection risk in theme extraction query
4. **MEDIUM**: Missing input validation on pipeline_run_id parameter
5. **MEDIUM**: Potential integer overflow on pipeline_run_id

The migration itself is clean, but the API layer and referential integrity protections are insufficient.

---

## Detailed Findings

### S1: CRITICAL - Missing CASCADE behavior on foreign key (Referential Integrity Violation)

**File**: `src/db/migrations/010_conversation_run_scoping.sql`
**Lines**: 9-10
**Severity**: CRITICAL
**Confidence**: HIGH

**Attack Vector**:
The migration adds a foreign key constraint but does NOT specify `ON DELETE` or `ON UPDATE` behavior:

```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id);
```

**What Goes Wrong**:

1. If a `pipeline_run` is deleted, PostgreSQL's default behavior is `ON DELETE NO ACTION`
2. This means the DELETE will **fail** if any conversations reference that run
3. This creates two problems:
   - **Data retention risk**: Cannot delete old pipeline runs, leading to unbounded data growth
   - **Orphan data vulnerability**: If constraint is later dropped or disabled, orphaned conversations with invalid `pipeline_run_id` values can exist

**Exploit Scenario**:

1. Attacker gains access to DB or exploits an admin endpoint
2. Deletes pipeline_run records to hide evidence of data exfiltration
3. Without CASCADE DELETE, operation fails - BUT if constraints are later disabled for "performance", orphaned data remains with no audit trail

**Evidence**:

```bash
# Grep for CASCADE behavior in migration
grep -i "ON DELETE\|ON UPDATE" src/db/migrations/010_conversation_run_scoping.sql
# Returns: No matches found
```

**Fix**:
Add explicit cascade behavior. Recommended:

```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id) ON DELETE SET NULL;
```

`ON DELETE SET NULL` is safer than `CASCADE` because:

- Preserves conversation data for audit/compliance
- Allows querying orphaned conversations: `WHERE pipeline_run_id IS NULL`
- Prevents accidental mass deletion

**Alternative** (if conversations should always be scoped to a run):

```sql
ON DELETE RESTRICT  -- Prevents deletion of runs with conversations
```

**Verification Needed**:

- What is the business requirement for pipeline_run lifecycle?
- Should conversations persist after run deletion?
- Is there a data retention policy?

---

### S2: CRITICAL - No Authorization Controls on API Endpoints (Broken Access Control)

**File**: `src/api/routers/pipeline.py`
**Lines**: Multiple (768-1070)
**Severity**: CRITICAL
**Confidence**: HIGH

**Attack Vector**:
ALL pipeline endpoints accept `run_id` as a parameter but have **zero authorization checks**:

```python
@router.get("/status/{run_id}", response_model=PipelineStatus)
def get_pipeline_status(run_id: int, db=Depends(get_db)):
    # No check if user is authorized to view this run_id
    ...

@router.get("/status/{run_id}/preview", response_model=DryRunPreview)
def get_dry_run_preview(run_id: int, db=Depends(get_db)):
    # No check if user owns this run_id
    ...
```

**What Goes Wrong**:

1. Attacker can enumerate all `run_id` values (they're sequential integers)
2. Can view status, previews, and results for ANY pipeline run
3. Can potentially stop other users' pipeline runs via `/stop` endpoint
4. Can view sensitive customer data in conversation previews

**Exploit Scenario**:

```bash
# Enumerate all runs
for i in {1..1000}; do
  curl -s "https://api.feedforward.com/api/pipeline/status/$i" | jq .
done

# Exfiltrate all conversation data
for i in {1..1000}; do
  curl -s "https://api.feedforward.com/api/pipeline/status/$i/preview" \
    | jq '.samples[].source_body' >> stolen_data.txt
done
```

**Evidence from Code**:

```python
# src/api/deps.py
def get_db() -> Generator:
    """FastAPI dependency for database connections."""
    # NO authentication/authorization logic
    conn = psycopg2.connect(get_connection_string())
    ...
```

**Fix**:

1. Add authentication middleware (JWT, API key, etc.)
2. Add `user_id` or `tenant_id` to `pipeline_runs` table
3. Add dependency to check ownership:

```python
def verify_run_access(run_id: int, current_user: User, db) -> PipelineRun:
    """Verify user has access to this run."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT * FROM pipeline_runs WHERE id = %s AND user_id = %s",
            (run_id, current_user.id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Access denied")
    return run_id

@router.get("/status/{run_id}")
def get_pipeline_status(
    run_id: int = Depends(verify_run_access),
    db=Depends(get_db)
):
    ...
```

**Scope**: SYSTEMIC - affects ALL pipeline endpoints

---

### S3: HIGH - Potential SQL Injection in Theme Extraction Query (Injection Risk)

**File**: `src/api/routers/pipeline.py`
**Lines**: 298, 438
**Severity**: HIGH
**Confidence**: MEDIUM

**Attack Vector**:
While the code uses parameterized queries (`%s`), the `run_id` parameter is passed directly from the API without type validation:

```python
def get_pipeline_status(run_id: int, db=Depends(get_db)):
    # FastAPI type hint `int` provides SOME protection
    ...
    cur.execute("""
        SELECT ... FROM conversations c
        WHERE c.pipeline_run_id = %s
    """, (run_id,))
```

**Current Protection**:
FastAPI's type system provides basic validation - if `run_id` is not an integer, FastAPI returns 422 Unprocessable Entity.

**What Could Go Wrong**:

1. If FastAPI type validation is bypassed (e.g., internal calls, middleware bugs)
2. If code is copy-pasted to non-FastAPI context (e.g., CLI script)
3. Future refactoring might remove type hints

**Why This is Still a Risk**:
Defense in depth principle - relying solely on framework validation is insufficient.

**Evidence**:

```python
# src/two_stage_pipeline.py:421
pipeline_run_id: Optional[int] = None
# Type hint, but no runtime validation
```

**Fix**:
Add explicit validation:

```python
def get_pipeline_status(run_id: int, db=Depends(get_db)):
    # Explicit validation (defense in depth)
    if not isinstance(run_id, int) or run_id < 1:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    # Additional bounds check
    if run_id > 2147483647:  # PostgreSQL INTEGER max
        raise HTTPException(status_code=400, detail="run_id exceeds maximum")

    # Now safe to use in query
    cur.execute("SELECT ... WHERE c.pipeline_run_id = %s", (run_id,))
```

**Verification Needed**:

- Test with malicious payloads: `run_id="1 OR 1=1"`, `run_id="1; DROP TABLE conversations;--"`
- Confirm FastAPI rejects these (it should, but verify)

---

### S4: MEDIUM - Missing Input Validation on pipeline_run_id in Storage Functions (Validation Bypass)

**File**: `src/db/classification_storage.py`
**Lines**: 35, 179
**Severity**: MEDIUM
**Confidence**: HIGH

**Attack Vector**:
Storage functions accept `pipeline_run_id: Optional[int] = None` but perform **no validation**:

```python
def store_classification_result(
    ...,
    pipeline_run_id: Optional[int] = None
) -> None:
    # No validation - directly passes to SQL
    cur.execute("""
        INSERT INTO conversations (..., pipeline_run_id)
        VALUES (..., %s)
    """, (..., pipeline_run_id))
```

**What Goes Wrong**:

1. Accepts `None` (NULL) - is this intentional?
2. Accepts negative integers: `pipeline_run_id=-1`
3. Accepts zero: `pipeline_run_id=0`
4. No check if `pipeline_run_id` actually exists in `pipeline_runs` table

**Why This Matters**:
Foreign key constraint will prevent invalid references, BUT:

- Error messages leak database schema information
- Violates fail-fast principle (should validate at application layer)
- Makes debugging harder (constraint violation errors are cryptic)

**Fix**:

```python
def store_classification_result(
    ...,
    pipeline_run_id: Optional[int] = None
) -> None:
    # Validate pipeline_run_id if provided
    if pipeline_run_id is not None:
        if not isinstance(pipeline_run_id, int) or pipeline_run_id < 1:
            raise ValueError(f"Invalid pipeline_run_id: {pipeline_run_id}")

        # Optional: Verify run exists (if not trusting caller)
        cur.execute(
            "SELECT 1 FROM pipeline_runs WHERE id = %s",
            (pipeline_run_id,)
        )
        if not cur.fetchone():
            raise ValueError(f"Pipeline run {pipeline_run_id} does not exist")

    # Now safe to insert
    cur.execute(...)
```

**Scope**: ISOLATED - only affects storage layer

---

### S5: MEDIUM - Integer Overflow Risk on pipeline_run_id (Denial of Service)

**File**: `src/db/migrations/010_conversation_run_scoping.sql`
**Lines**: 10
**Severity**: MEDIUM
**Confidence**: MEDIUM

**Attack Vector**:
The migration uses `INTEGER` type for `pipeline_run_id`:

```sql
pipeline_run_id INTEGER REFERENCES pipeline_runs(id)
```

**PostgreSQL INTEGER Range**:

- Type: `INTEGER` (4 bytes)
- Range: -2,147,483,648 to +2,147,483,647
- Max safe value: ~2.1 billion

**What Goes Wrong**:
If the system runs long enough, `pipeline_run_id` will overflow:

- Assuming 1000 runs/day: 2,147,483 days = ~5,882 years (safe)
- Assuming 100,000 runs/day: 21,474 days = ~58 years (risky for long-lived system)
- Assuming 1,000,000 runs/day (high-frequency testing): 2,147 days = ~6 years (PROBLEM)

**Exploit Scenario**:

1. Attacker triggers thousands of pipeline runs (if no rate limiting)
2. Exhausts `pipeline_run_id` sequence
3. System fails to create new runs (denial of service)

**Evidence**:

```python
# src/db/connection.py:137
def create_pipeline_run(run: PipelineRun) -> int:
    sql = """
    INSERT INTO pipeline_runs (started_at, date_from, date_to, status)
    VALUES (%s, %s, %s, %s)
    RETURNING id
    """
    # No check for approaching max ID
```

**Fix**:
Use `BIGINT` instead of `INTEGER`:

```sql
-- Migration 010 (revised)
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    pipeline_run_id BIGINT REFERENCES pipeline_runs(id) ON DELETE SET NULL;
```

**BIGINT Range**:

- Type: `BIGINT` (8 bytes)
- Range: -9,223,372,036,854,775,808 to +9,223,372,036,854,775,807
- Effectively unlimited for this use case

**Cost of Fix**: Negligible (8 bytes vs 4 bytes per row)

**Verification Needed**:

- Check if `pipeline_runs.id` is already `BIGINT` (if so, mismatch is a bug)
- Add monitoring for `pipeline_run_id` approaching max value

---

## Additional Observations (Not Blocking)

### 1. Missing Indexes for Query Performance

Not a security issue, but theme extraction queries on large datasets may be slow without composite index:

```sql
CREATE INDEX idx_conversations_run_type
    ON conversations(pipeline_run_id, stage2_type, stage1_type);
```

### 2. No Audit Logging

`pipeline_run_id` changes are not logged. Consider adding:

- Trigger to log `pipeline_run_id` updates
- Audit table for run lifecycle events

### 3. Missing Rate Limiting

No evidence of rate limiting on `/run` endpoint. Attacker could spam pipeline runs.

---

## Remediation Priority

1. **S2 (CRITICAL)**: Add authorization controls - MUST FIX before merge
2. **S1 (CRITICAL)**: Add CASCADE behavior - MUST FIX before merge
3. **S3 (HIGH)**: Add input validation to API layer - STRONGLY RECOMMENDED
4. **S4 (MEDIUM)**: Add validation to storage functions - RECOMMENDED
5. **S5 (MEDIUM)**: Use BIGINT for future-proofing - NICE TO HAVE

---

## Testing Recommendations

1. **Penetration Testing**:
   - Test run_id enumeration attacks
   - Test SQL injection payloads (should fail gracefully)
   - Test orphaned data scenarios

2. **Unit Tests Needed**:
   - Test `pipeline_run_id=None` behavior
   - Test `pipeline_run_id=-1`, `pipeline_run_id=0`
   - Test foreign key constraint violations
   - Test CASCADE behavior after fix

3. **Integration Tests**:
   - Test overlapping runs with authorization
   - Test run deletion with conversations
   - Test concurrent access to same run_id

---

## Conclusion

The core architecture (explicit `pipeline_run_id` vs timestamp heuristics) is a **significant improvement**. However, the implementation has critical security gaps that MUST be addressed:

1. **No authorization = data breach risk**
2. **No CASCADE behavior = data integrity risk**
3. **Insufficient validation = injection/overflow risk**

**Recommendation**: BLOCK until S1 and S2 are fixed. S3-S5 should be addressed in follow-up PR if time-constrained.

---

**Next Steps**:

1. Original developer (likely Marcus or Kai) should fix S1, S2
2. Re-run security review after fixes
3. Add security tests to prevent regression
4. Update CLAUDE.md with secure coding patterns for foreign keys

---

## Reviewer Notes

- This is a foundational change that affects multiple components
- Security debt here will compound as features build on this
- The tests in `test_run_scoping.py` are excellent for functionality but lack security edge cases
- Consider adding `tests/security/test_run_scoping_security.py`

---

**Reviewed by**: Sanjay (Security Auditor)
**Timestamp**: 2026-01-22T19:45:00Z
**Review Duration**: 45 minutes
**Files Analyzed**: 5 core files + 3 migration files
