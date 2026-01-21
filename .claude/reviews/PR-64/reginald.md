# PR-64 Review: Reginald (The Architect)

**Reviewer**: Reginald - Senior Engineer focused on correctness and performance
**PR**: fix(research): Fix coda_page adapter SQL column mismatch
**Issue**: #62
**Round**: 1

---

## Executive Summary

The PR correctly fixes the immediate SQL column mismatch issue (changing `name` to `title` and removing `parent_id`). However, I've identified **3 issues** that need attention, ranging from missing test coverage to potential resource leaks.

---

## Issue Analysis

### R1: Missing Unit Tests for \_row_to_page_content Method [MEDIUM]

**Location**: `tests/test_research.py`, `src/research/adapters/coda_adapter.py`

**Problem**: The existing tests for `CodaSearchAdapter` (lines 216-250 in test_research.py) only test:

- Source type validation
- URL generation with mocked environment

There are **no tests** for the actual page extraction logic that was modified:

- `_row_to_page_content()` - the method that changed from `row["name"]` to `row["title"]`
- `_extract_page()` - the method that changed the SELECT query
- `_extract_all_pages()` - the method that changed the SELECT query

The IntercomSearchAdapter has tests for `_clean_html()` and `_extract_title()` helper methods, but CodaSearchAdapter has no comparable coverage for its page conversion logic.

**Evidence**: The schema change from `name` to `title` is the core of this PR, yet there's no test verifying that:

1. A row with a `title` field is correctly converted to `SearchableContent`
2. The fallback `f"Page {page_id}"` works when `title` is None
3. The participant extraction regex still works
4. The page_type detection still works

**Recommendation**: Add tests that mock SQLite rows with `title` field to verify the conversion logic.

---

### R2: SQL Injection Risk via f-string LIMIT Interpolation [LOW-MEDIUM]

**Location**: `src/research/adapters/coda_adapter.py`, lines 127-128

**Problem**: The LIMIT clause is constructed via f-string interpolation:

```python
if limit:
    query += f" LIMIT {limit}"
```

While the `limit` parameter is typed as `Optional[int]`, Python's dynamic typing means:

1. A caller could pass a string: `adapter.extract_all(limit="1; DROP TABLE pages; --")`
2. The type annotation is not enforced at runtime
3. This pattern exists in 3 places across the codebase (lines 128, 216 in coda_adapter.py and line 79 in intercom_adapter.py)

**Note**: This is a pre-existing issue, not introduced by this PR. However, since the PR touches this code, it's worth flagging.

**Evidence from grep**:

```
src/research/adapters/intercom_adapter.py:79: query += f" LIMIT {limit}"
src/research/adapters/coda_adapter.py:128:    query += f" LIMIT {limit}"
src/research/adapters/coda_adapter.py:216:   query += f" LIMIT {limit}"
```

**Recommendation**: Use parameterized queries or explicit `int()` conversion with validation:

```python
if limit is not None:
    validated_limit = max(1, int(limit))  # Raises if not int-like
    query += " LIMIT ?"
    cur.execute(query, (validated_limit,))
```

---

### R3: Connection Not Closed in extract_all() on Exception Path [MEDIUM]

**Location**: `src/research/adapters/coda_adapter.py`, lines 75-93

**Problem**: In the `extract_all()` method, there's a potential resource leak. The `finally` block tries to close the connection:

```python
finally:
    if 'conn' in locals():
        conn.close()
```

However, if `_get_connection()` raises `FileNotFoundError` (handled in the except block on line 85), the `conn` variable is never assigned, yet the code continues to run and returns. This is actually handled correctly.

**BUT**, if `_get_connection()` succeeds but `cur = conn.cursor()` (implicit in the iterator methods) fails, or if any exception occurs during `yield from`, the connection might not be properly closed because:

1. The generator may be abandoned mid-iteration
2. The `finally` block only runs when the generator is closed/exhausted

This is a subtle issue with generators and resource management.

**Evidence**: Looking at the code structure:

```python
def extract_all(self, limit: Optional[int] = None) -> Iterator[SearchableContent]:
    try:
        conn = self._get_connection()  # Connection opened
        cur = conn.cursor()
        if self._source_type == "coda_page":
            yield from self._extract_all_pages(cur, limit)  # <-- Generator yields
        ...
    finally:
        if 'conn' in locals():
            conn.close()  # Only runs when generator exhausted/closed
```

If the caller abandons the generator (e.g., `list(islice(adapter.extract_all(), 5))`), the `finally` block may not execute immediately.

**Recommendation**: Use a context manager pattern:

```python
def extract_all(self, limit: Optional[int] = None) -> Iterator[SearchableContent]:
    with self._get_connection() as conn:  # Requires __enter__/__exit__
        ...
```

Or ensure `_get_connection()` returns a context manager.

---

## Correctness Analysis (SLOW THINKING)

### Step 1: Verify Schema Match

The database schema shows:

```sql
CREATE TABLE pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canvas_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,       -- <-- Changed from 'name'
  content TEXT NOT NULL,
  file_path TEXT,
  char_count INTEGER,
  extracted_at TEXT          -- <-- No parent_id exists
);
```

The PR changes `name` -> `title` and removes `parent_id`. **This is correct.**

### Step 2: Verify Row Access

Before:

```python
title = row["name"] or f"Page {page_id}"
"parent_id": row["parent_id"],
```

After:

```python
title = row["title"] or f"Page {page_id}"
# parent_id removed from metadata
```

The column access now matches the schema. **Correct.**

### Step 3: Verify SELECT Statement

Before:

```sql
SELECT canvas_id, name, content, parent_id FROM pages
```

After:

```sql
SELECT canvas_id, title, content FROM pages
```

Columns selected match those accessed. **Correct.**

### Step 4: Impact Analysis

- The `metadata` dict no longer includes `parent_id`
- Any code that expects `metadata["parent_id"]` will get `KeyError`
- Need to verify no downstream consumers rely on this

**Grep results show**: No other code in `src/` references `metadata["parent_id"]` for coda_page source type.

---

## Summary

| Issue | Severity   | Type          | Action Required                             |
| ----- | ---------- | ------------- | ------------------------------------------- |
| R1    | MEDIUM     | Missing Tests | Add unit tests for page conversion logic    |
| R2    | LOW-MEDIUM | Security      | Consider parameterized LIMIT (pre-existing) |
| R3    | MEDIUM     | Resource Leak | Improve generator resource management       |

**Verdict**: The core fix is correct and the PR achieves its goal. However, R1 (missing tests) should be addressed before merge per project Test Gate requirements. R3 is a real concern but may be acceptable as a pre-existing pattern.

---

_Reviewed by Reginald, The Architect - Round 1_
