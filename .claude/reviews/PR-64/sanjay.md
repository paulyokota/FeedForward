# Security Review: PR #64 - Fix coda_page adapter SQL column mismatch

**Reviewer**: Sanjay (The Security Auditor)
**PR**: #64
**Round**: 1
**Date**: 2026-01-20
**File Reviewed**: `src/research/adapters/coda_adapter.py`

---

## Executive Summary

This PR fixes SQL column mismatches in the Coda adapter by changing `name` to `title` and removing `parent_id`. While the changes themselves are straightforward, my review uncovered a **PRE-EXISTING SQL INJECTION VULNERABILITY** that was NOT introduced by this PR but is present in the code being modified. Additionally, I found minor issues related to input validation and information disclosure.

---

## Issues Found

### S1: SQL Injection via String Interpolation in `limit` Parameter (HIGH - PRE-EXISTING)

**Severity**: HIGH
**Location**: Lines 127-128 in `_extract_all_pages()` and line 215-216 in `_extract_all_themes()`
**Type**: SQL Injection / CWE-89

**Code**:

```python
if limit:
    query += f" LIMIT {limit}"
```

**Analysis**:
The `limit` parameter is inserted into the SQL query via string formatting (`f" LIMIT {limit}"`). While the `limit` parameter is typed as `Optional[int]` in the method signature, Python's type hints are NOT enforced at runtime.

An attacker who can control the `limit` parameter (e.g., via API endpoint that calls `extract_all()`) could pass a malicious value:

- If input validation is weak upstream: `limit = "1; DROP TABLE pages; --"`
- Or via type coercion attacks

**Note**: This vulnerability exists in BOTH SQLite (pages) and PostgreSQL (themes) code paths.

**Why this matters even for `int` type**:

1. Type hints are documentation, not enforcement
2. If called from an API endpoint, the value may come from user input
3. Even if currently safe, future code changes could introduce unsafe paths

**Recommendation**:
Use parameterized queries for the LIMIT clause:

```python
# SQLite
cur.execute(query + " LIMIT ?", (limit,))

# PostgreSQL
pg_cur.execute(query + " LIMIT %s", (limit,))
```

**Status**: PRE-EXISTING BUG (not introduced by this PR, but in scope for security review)

---

### S2: Insufficient Input Validation on `source_type` Parameter (LOW)

**Severity**: LOW
**Location**: Lines 39-40
**Type**: Input Validation / CWE-20

**Code**:

```python
if source_type not in ("coda_page", "coda_theme"):
    raise ValueError(f"Invalid source_type: {source_type}. Must be 'coda_page' or 'coda_theme'")
```

**Analysis**:
The validation uses a simple tuple membership check. While this is generally fine, the error message includes the raw user input `source_type`, which could:

1. Expose implementation details in logs
2. Enable log injection if the value contains newlines or control characters
3. Cause encoding issues with malicious Unicode

**Recommendation**:
Sanitize or truncate the input before including in error messages:

```python
safe_type = repr(source_type)[:50]  # Truncate and escape
raise ValueError(f"Invalid source_type: {safe_type}...")
```

---

### S3: Path Traversal Risk via `db_path` Parameter (MEDIUM - PRE-EXISTING)

**Severity**: MEDIUM
**Location**: Lines 31-43
**Type**: Path Traversal / CWE-22

**Code**:

```python
def __init__(self, source_type: str = "coda_page", db_path: Optional[Path] = None):
    ...
    self._db_path = db_path or CODA_DB_PATH
```

**Analysis**:
The `db_path` parameter accepts an arbitrary `Path` without validation. If an attacker can influence this parameter (e.g., through a configuration file, environment variable, or API), they could:

1. Read arbitrary SQLite databases: `db_path = Path("/etc/passwd")` (would fail gracefully, but still probing)
2. Access sensitive local databases: `db_path = Path("~/.ssh/known_hosts")`
3. Path traversal: `db_path = Path("../../../sensitive.db")`

The code does check `if not self._db_path.exists()` in `_get_connection()`, but this only prevents reading non-existent files; it doesn't restrict which existing files can be accessed.

**Recommendation**:

1. Validate that `db_path` is within an allowed directory
2. Resolve the path and check it doesn't escape the data directory

```python
allowed_base = Path(__file__).parent.parent.parent.parent / "data"
if db_path:
    resolved = db_path.resolve()
    if not resolved.is_relative_to(allowed_base):
        raise ValueError("db_path must be within the data directory")
```

---

### S4: Information Disclosure via Exception Logging (LOW)

**Severity**: LOW
**Location**: Lines 69-71, 86-90, 198-200, 223-225
**Type**: Information Disclosure / CWE-200

**Code**:

```python
except Exception as e:
    logger.error(f"Failed to extract Coda content {source_id}: {e}")
    return None
```

**Analysis**:
The broad `except Exception` catches all errors and logs them with full exception details. This could expose:

1. Database schema information from SQL errors
2. File paths from file system errors
3. Stack traces if the logger is configured to include them
4. Internal implementation details

While logging errors is important for debugging, the level of detail should be appropriate for the log audience.

**Recommendation**:

1. Log full details at DEBUG level, sanitized summary at ERROR level
2. Consider structured logging to control what's exposed
3. Catch specific exceptions when possible

---

### S5: Regex Denial of Service (ReDoS) Potential (LOW)

**Severity**: LOW
**Location**: Lines 148-151
**Type**: ReDoS / CWE-1333

**Code**:

```python
if "@" in title:
    import re
    match = re.search(r'[\w\.-]+@[\w\.-]+', title)
```

**Analysis**:
The regex `[\w\.-]+@[\w\.-]+` is relatively simple and unlikely to cause catastrophic backtracking. However:

1. The `title` field comes from database content (potentially user-influenced)
2. The pattern has no anchors or length limits
3. A title with many `@` symbols could cause multiple match attempts

The risk is LOW because:

- The pattern doesn't have nested quantifiers
- It's called per-row, not in a tight loop
- Database content is somewhat controlled

**Recommendation**:
Consider adding a length limit or using a compiled regex for performance:

```python
if "@" in title and len(title) < 1000:  # Sanity limit
    EMAIL_PATTERN = re.compile(r'[\w\.-]+@[\w\.-]+')
    match = EMAIL_PATTERN.search(title)
```

---

## Changes Introduced by PR #64

The actual changes in this PR are:

1. `name` -> `title` in SELECT queries
2. Removed `parent_id` from SELECT queries
3. Removed `parent_id` from metadata dict

**Security assessment of these specific changes**: **NO NEW VULNERABILITIES INTRODUCED**

The column name changes are semantically equivalent and don't introduce new attack vectors. The removal of `parent_id` actually reduces the metadata surface area slightly.

---

## Summary Table

| ID  | Severity | Type             | Introduced By PR? | Requires Fix?  |
| --- | -------- | ---------------- | ----------------- | -------------- |
| S1  | HIGH     | SQL Injection    | No (pre-existing) | YES - Critical |
| S2  | LOW      | Input Validation | No (pre-existing) | Recommended    |
| S3  | MEDIUM   | Path Traversal   | No (pre-existing) | YES            |
| S4  | LOW      | Info Disclosure  | No (pre-existing) | Recommended    |
| S5  | LOW      | ReDoS            | No (pre-existing) | Optional       |

---

## Verdict

**The PR itself is SAFE to merge** - it doesn't introduce new vulnerabilities.

**However**, I recommend filing issues for the pre-existing vulnerabilities discovered:

- **S1 (SQL Injection)** should be addressed urgently in a separate PR
- **S3 (Path Traversal)** should be assessed based on how `db_path` is used in practice

---

## Checklist Coverage

| Category                        | Findings                                             |
| ------------------------------- | ---------------------------------------------------- |
| 1. Injection Risks              | S1 - SQL Injection in LIMIT clause                   |
| 2. Authentication/Authorization | N/A - No auth logic in this file                     |
| 3. Sensitive Data Exposure      | S4 - Exception logging                               |
| 4. Input Validation             | S2 - source_type validation, S3 - db_path validation |
| 5. CSRF/SSRF Vulnerabilities    | N/A - No web request handling                        |
| 6. Insecure Cryptography        | N/A - No crypto in this file                         |
| 7. Rate Limiting and Abuse      | S5 - ReDoS potential                                 |

---

_Reviewed by Sanjay, Security Auditor_
_"Trust nothing. Validate everything."_
