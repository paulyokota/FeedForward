# Correctness Review: PR #112 - Fix Run Scoping with pipeline_run_id

**Reviewer**: Reginald (Correctness & Performance)
**PR**: #112
**Date**: 2026-01-22
**Verdict**: BLOCK

## Executive Summary

Found **4 HIGH** and **2 MEDIUM** severity issues. The core fix is correct, but there are critical NULL handling gaps and a dangerous data migration issue that will cause production failures.

---

## Critical Issues (BLOCK)

### R1: NULL pipeline_run_id Breaks Theme Extraction Query (HIGH)

**File**: `src/api/routers/pipeline.py:298`
**Problem**: The fixed query uses `WHERE c.pipeline_run_id = %s` but doesn't handle NULL values.

**What breaks**:

```sql
-- Line 298: Fixed query
WHERE c.pipeline_run_id = %s

-- Problem: What about conversations classified BEFORE migration?
-- Those have pipeline_run_id = NULL
-- Query will exclude them even though they should be included
```

**Scenario**:

1. User has 10,000 conversations classified before migration
2. All have `pipeline_run_id = NULL`
3. Run theme extraction on an old run
4. Query returns 0 conversations (should return thousands)
5. No themes extracted, silent data loss

**Root Cause**: Migration adds column as nullable but doesn't backfill. Old data has NULL, new data has integer. Query doesn't handle both cases.

**Evidence from migration**:

```sql
-- Line 10 of 010_conversation_run_scoping.sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id);
-- No NOT NULL, no DEFAULT, no backfill = existing rows get NULL
```

**Fix Required**:

```sql
-- Option 1: Handle NULL in query (backward compatible)
WHERE (c.pipeline_run_id = %s OR (c.pipeline_run_id IS NULL AND c.classified_at >= pr.started_at))

-- Option 2: Backfill migration (breaking change)
UPDATE conversations SET pipeline_run_id = (
    SELECT id FROM pipeline_runs pr
    WHERE c.classified_at >= pr.started_at
    ORDER BY pr.started_at DESC LIMIT 1
) WHERE pipeline_run_id IS NULL;
```

**Why this is HIGH**: Silent data loss in production. Theme extraction fails but returns success (0 themes).

---

### R2: Race Condition in Batch Storage (HIGH)

**File**: `src/db/classification_storage.py:276-318`
**Problem**: `pipeline_run_id` is passed to `store_classification_results_batch()` but individual result dicts might also contain `pipeline_run_id`.

**What breaks**:

```python
# Line 179: Function signature
def store_classification_results_batch(
    results: List[Dict[str, Any]],
    pipeline_run_id: Optional[int] = None
) -> int:

# Line 275: What if result dict has pipeline_run_id key?
rows.append((
    # ... other fields ...
    pipeline_run_id,  # Uses function parameter
))

# Problem: If result dict contains {"pipeline_run_id": 456}
# But function called with pipeline_run_id=123
# Which one wins? Function parameter (123) ALWAYS wins
# Result dict value is IGNORED
```

**Scenario**:

1. Pipeline runs with `run_id=100`
2. Stores results with `pipeline_run_id=100`
3. Later, someone calls storage with old results: `store_classification_results_batch(old_results, pipeline_run_id=200)`
4. Old conversations (from run 100) now linked to run 200
5. Data corruption: conversations appear in wrong run

**Root Cause**: No validation that result-level `pipeline_run_id` matches function-level `pipeline_run_id`.

**Fix Required**:

```python
# Add validation in store_classification_results_batch
for r in results:
    result_run_id = r.get("pipeline_run_id")
    if result_run_id is not None and pipeline_run_id is not None:
        if result_run_id != pipeline_run_id:
            raise ValueError(
                f"Mismatch: result has pipeline_run_id={result_run_id} "
                f"but function called with pipeline_run_id={pipeline_run_id}"
            )
```

**Why this is HIGH**: Data corruption. Conversations get assigned to wrong runs, breaking run isolation.

---

### R3: Missing Foreign Key Constraint Enforcement (HIGH)

**File**: `src/db/migrations/010_conversation_run_scoping.sql:10`
**Problem**: Foreign key constraint `REFERENCES pipeline_runs(id)` allows NULL but doesn't validate referenced IDs exist.

**What breaks**:

```sql
-- Line 10: Migration
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id);

-- Problem: What if someone stores with pipeline_run_id=999 but run 999 doesn't exist?
-- PostgreSQL will reject the insert, but code doesn't handle this error
```

**Scenario**:

1. API receives `run_id=999` from malformed request
2. Pipeline runs classification, stores results
3. `store_classification_results_batch(results, pipeline_run_id=999)`
4. PostgreSQL raises: `ERROR: insert or update violates foreign key constraint`
5. Exception bubbles up, pipeline crashes
6. No results stored, work lost

**Evidence from storage code**:

```python
# Lines 317-318 of classification_storage.py
execute_values(cur, sql, rows)
conn.commit()
# No try/except for foreign key violations
# No validation that pipeline_run_id exists in pipeline_runs table
```

**Fix Required**:

```python
# In store_classification_results_batch, validate before insert:
if pipeline_run_id is not None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pipeline_runs WHERE id = %s", (pipeline_run_id,))
            if not cur.fetchone():
                raise ValueError(f"Pipeline run {pipeline_run_id} does not exist")
```

**Why this is HIGH**: Production crashes. Batch storage fails, data lost, no recovery path.

---

### R4: Inconsistent NULL Handling Between Single and Batch Insert (MEDIUM)

**File**: `src/db/classification_storage.py:120 vs 294`
**Problem**: Single insert and batch insert handle `pipeline_run_id` in ON CONFLICT differently.

**What breaks**:

```python
# Line 120 (single insert): Includes pipeline_run_id in INSERT
pipeline_run_id

# Line 157 (single insert ON CONFLICT): Updates pipeline_run_id
pipeline_run_id = EXCLUDED.pipeline_run_id

# Line 294 (batch insert): Includes pipeline_run_id in INSERT
pipeline_run_id

# Line 315 (batch insert ON CONFLICT): Updates pipeline_run_id
pipeline_run_id = EXCLUDED.pipeline_run_id

# Looks consistent BUT...
```

**Edge Case**:

```python
# T1: Store conversation 123 with pipeline_run_id=100
store_classification_result(..., pipeline_run_id=100)
# conversations.pipeline_run_id = 100

# T2: Re-classify same conversation in different run
store_classification_result(..., pipeline_run_id=200)
# ON CONFLICT DO UPDATE SET pipeline_run_id = 200
# conversations.pipeline_run_id = 200 (OVERWRITTEN)

# Problem: Conversation 123 now shows it was classified in run 200
# But it was ALSO classified in run 100
# History lost - can't tell which run originally classified it
```

**Root Cause**: `ON CONFLICT` overwrites `pipeline_run_id` instead of preserving first classification.

**Design Question**: Should `pipeline_run_id` be:

- **First run** that classified the conversation (immutable)?
- **Most recent run** that classified it (current behavior)?

If "first run", need:

```sql
ON CONFLICT (id) DO UPDATE SET
    -- Update other fields
    pipeline_run_id = COALESCE(conversations.pipeline_run_id, EXCLUDED.pipeline_run_id)
    -- Preserves existing value, only sets if NULL
```

**Why this is MEDIUM**: Depends on intended semantics. Could be HIGH if "first run" is required for audit trail.

---

## Performance Issues

### R5: Missing Index on Conversations JOIN (MEDIUM)

**File**: `src/api/routers/pipeline.py:437-438`
**Problem**: Story creation query joins themes to conversations but no compound index.

**Query**:

```sql
-- Lines 437-438
FROM themes t
JOIN conversations c ON t.conversation_id = c.id
WHERE t.pipeline_run_id = %s
```

**Performance Impact**:

- `themes.pipeline_run_id` has index (from previous work)
- `conversations.pipeline_run_id` has index (added in this PR)
- BUT join on `t.conversation_id = c.id` uses `conversations.id` PK
- Efficient JOIN (PK lookup)

**Actually, this is FINE**. Index exists on both sides.

**Revised**: Not an issue. Retracting R5.

---

### R6: Batch Size Not Configurable in Sync Pipeline (LOW)

**File**: `src/two_stage_pipeline.py:827-828`
**Problem**: Sync pipeline hardcodes `BATCH_SIZE = 50` but async pipeline allows customization.

**Code**:

```python
# Line 827 (sync)
BATCH_SIZE = 50

# Line 418 (async)
batch_size: int = 50,  # Configurable parameter
```

**Impact**: Minor. Sync pipeline is for debugging only (per docstring line 792). But inconsistent API.

**Fix**: Add `batch_size` parameter to `run_pipeline()` for consistency.

---

## Logic Correctness

### Trace: Pipeline Flow

**Entry Point**: `src/api/routers/pipeline.py:_run_pipeline_task()`

```python
# Line 571-578: Calls async pipeline
result = asyncio.run(run_pipeline_async(
    days=days,
    max_conversations=max_conversations,
    dry_run=dry_run,
    concurrency=concurrency,
    stop_checker=stop_checker,
    pipeline_run_id=run_id,  # ✓ Passed correctly
))
```

**Pipeline Execution**: `src/two_stage_pipeline.py:run_pipeline_async()`

```python
# Line 421: Receives pipeline_run_id
pipeline_run_id: Optional[int] = None,

# Line 576: Passes to batch storage
stored = store_classification_results_batch(batch, pipeline_run_id=pipeline_run_id)
# ✓ Correct threading
```

**Coda Branch**: `src/two_stage_pipeline.py:_run_coda_pipeline_async()`

```python
# Line 608: Receives pipeline_run_id
pipeline_run_id: Optional[int] = None,

# Line 764: Passes to batch storage
stored = store_classification_results_batch(batch, pipeline_run_id=pipeline_run_id)
# ✓ Correct threading
```

**Sync Pipeline**: `src/two_stage_pipeline.py:run_pipeline()`

```python
# Line 787: Receives pipeline_run_id
pipeline_run_id: Optional[int] = None,

# Line 860: Passes to batch storage
stored = store_classification_results_batch(results_batch, pipeline_run_id=pipeline_run_id)
# ✓ Correct threading
```

**Storage**: `src/db/classification_storage.py:store_classification_results_batch()`

```python
# Line 179: Receives pipeline_run_id
pipeline_run_id: Optional[int] = None

# Line 275: Uses in row construction
pipeline_run_id,  # ✓ Uses function parameter, not result dict

# Line 294: Column in INSERT
pipeline_run_id  # ✓ Correct position (30th column)

# Line 315: ON CONFLICT UPDATE
pipeline_run_id = EXCLUDED.pipeline_run_id  # ⚠️ See R4
```

**Theme Extraction**: `src/api/routers/pipeline.py:_run_theme_extraction()`

```python
# Line 298: Query fixed
WHERE c.pipeline_run_id = %s  # ✗ See R1 (NULL handling)

# Line 405: Theme storage
run_id,  # ✓ Uses run_id from function parameter
```

**Verdict**: Flow is correct EXCEPT for NULL handling and validation gaps.

---

## Boundary Conditions

### Test Case: pipeline_run_id = 0

```python
# Valid run ID? PostgreSQL serial starts at 1
# But 0 is a valid integer per schema (INTEGER, not SERIAL)
# Behavior: Foreign key constraint will reject (no run with id=0)
# Result: Exception, no handling
```

**Missing**: Validation that `pipeline_run_id > 0` if not None.

---

### Test Case: pipeline_run_id = NULL (old data)

```python
# Scenario: 10,000 conversations classified before migration
# All have pipeline_run_id = NULL
# Query: WHERE c.pipeline_run_id = %s with %s = 100
# Result: 0 rows (should handle NULL with fallback)
```

**Missing**: See R1.

---

### Test Case: Empty results batch

```python
# Line 193 of classification_storage.py
if not results:
    return 0
# ✓ Handles empty batch correctly
```

---

### Test Case: Duplicate conversation_id in batch

```python
# If results contains same conversation_id twice
# Batch: [{"conversation_id": "123", ...}, {"conversation_id": "123", ...}]
# execute_values will attempt two inserts
# First: INSERT ... ON CONFLICT DO UPDATE (succeeds)
# Second: INSERT ... ON CONFLICT DO UPDATE (succeeds, overwrites first)
# Result: Last entry wins, no error
```

**This is actually FINE** per SQL semantics. Last write wins.

---

## Integration Verification

### Schema Consistency

**Migration adds**:

```sql
pipeline_run_id INTEGER REFERENCES pipeline_runs(id)
```

**Storage uses**:

```python
# Line 294 of classification_storage.py
pipeline_run_id  # 30th column, matches INSERT position
```

**Query uses**:

```sql
# Line 298 of pipeline.py
WHERE c.pipeline_run_id = %s
```

**Index created**:

```sql
-- Line 13-14 of migration
CREATE INDEX IF NOT EXISTS idx_conversations_pipeline_run_id
    ON conversations(pipeline_run_id);
```

✓ Schema is consistent EXCEPT for NULL handling.

---

## Test Coverage Analysis

**Tests exist for**:

- ✓ Function signatures accept `pipeline_run_id`
- ✓ Migration file exists
- ✓ Query uses `c.pipeline_run_id = %s`
- ✓ Integration tests (skipped, require DB)

**Tests MISSING for**:

- ✗ NULL `pipeline_run_id` behavior
- ✗ Foreign key violation handling
- ✗ Result dict vs function parameter mismatch
- ✗ ON CONFLICT behavior (first vs last run)
- ✗ Boundary: `pipeline_run_id = 0`
- ✗ Theme extraction with old (NULL) data

---

## Performance Impact

**Before PR**:

```sql
-- Old query (timestamp heuristic)
JOIN pipeline_runs pr ON c.classified_at >= pr.started_at
WHERE pr.id = %s

-- Scan: conversations where classified_at >= some timestamp
-- Then filter by pr.id
-- Problem: Includes conversations from OTHER runs with overlapping timestamps
```

**After PR**:

```sql
-- New query (explicit ID)
WHERE c.pipeline_run_id = %s

-- Index scan: idx_conversations_pipeline_run_id
-- Direct lookup, O(log N)
-- Much faster, correct isolation
```

**Performance**: ✓ Improvement. Index scan vs timestamp range scan.

---

## Summary of Findings

| ID  | Severity | Category       | Issue                                    | Impact                  |
| --- | -------- | -------------- | ---------------------------------------- | ----------------------- |
| R1  | HIGH     | Logic          | NULL pipeline_run_id breaks theme query  | Silent data loss        |
| R2  | HIGH     | Logic          | Race condition in batch storage          | Data corruption         |
| R3  | HIGH     | Error Handling | Missing FK validation                    | Production crashes      |
| R4  | MEDIUM   | Logic          | ON CONFLICT overwrites run history       | Audit trail loss        |
| R6  | LOW      | API            | Inconsistent batch_size parameter (sync) | Minor API inconsistency |

**Total**: 4 HIGH, 1 MEDIUM, 1 LOW

---

## Recommendations

1. **CRITICAL**: Add NULL handling to theme extraction query (R1)
2. **CRITICAL**: Validate foreign key before batch insert (R3)
3. **CRITICAL**: Add mismatch detection for result vs function pipeline_run_id (R2)
4. **REQUIRED**: Decide semantics for ON CONFLICT (first run vs last run) and implement (R4)
5. **OPTIONAL**: Add batch_size parameter to sync pipeline for consistency (R6)
6. **OPTIONAL**: Add validation that pipeline_run_id > 0 if not None

---

## Verification Checklist

- [ ] Add test for NULL pipeline_run_id in theme extraction
- [ ] Add test for foreign key violation handling
- [ ] Add test for result/function parameter mismatch
- [ ] Add test for ON CONFLICT behavior
- [ ] Run integration tests with real database
- [ ] Verify backfill migration if NULL handling uses COALESCE

---

## Conclusion

The core fix (explicit `pipeline_run_id` instead of timestamp heuristic) is **architecturally correct** and solves the original issue (#103). However, the implementation has **critical gaps** in NULL handling, validation, and error recovery that will cause production failures.

**Verdict**: BLOCK until R1, R2, R3 are fixed.
