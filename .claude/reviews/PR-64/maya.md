# Maya Code Review - PR #64 Round 1

**Verdict**: COMMENT
**Date**: 2026-01-20

## Summary

This PR fixes a SQL column mismatch bug in `coda_adapter.py` where queries referenced `name` and `parent_id` columns that don't exist in the actual SQLite schema (which has `title` instead of `name`, and no `parent_id`). The fix is functionally correct and aligns the code with the database schema defined in `scripts/coda_storage_optimize.js`.

However, from a maintainability perspective, there are opportunities to prevent this class of bug from recurring and to help future developers understand the schema mapping.

---

## M1: Missing Schema Documentation Comment

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/research/adapters/coda_adapter.py:107-126`

### The Problem

The SQL queries reference columns from an external SQLite database (`coda_content.db`), but there's no documentation explaining:

1. What columns exist in the `pages` table
2. Where the schema is defined
3. What the data looks like

This PR itself is evidence that the previous code author assumed columns (`name`, `parent_id`) that didn't exist. A future developer reading this file has no way to verify the queries are correct without hunting down the schema definition in `scripts/coda_storage_optimize.js`.

### Why This Matters

When this code breaks at 2am (or 6 months from now), the debugging developer will need to:

1. Find the SQLite database file
2. Introspect its schema manually (`.schema pages`)
3. Cross-reference with this code

This is exactly the kind of tribal knowledge that gets lost.

### Current Code

```python
def _extract_page(self, cur: sqlite3.Cursor, page_id: str) -> Optional[SearchableContent]:
    """Extract a single page."""
    cur.execute("""
        SELECT canvas_id, title, content
        FROM pages
        WHERE canvas_id = ?
    """, (page_id,))
```

### Suggested Fix

Add a schema reference comment at the top of the page extraction methods or in the class docstring:

```python
class CodaSearchAdapter(SearchSourceAdapter):
    """
    Adapter for Coda research data.

    Supports two source types:
    - coda_page: AI Summary pages and research pages
    - coda_theme: Extracted themes from synthesis tables

    SQLite Schema Reference (coda_content.db):
        pages: canvas_id, title, content, file_path, char_count, extracted_at
        Schema defined in: scripts/coda_storage_optimize.js
    """
```

This documents the contract and points future developers to the authoritative schema definition.

---

## M2: No Integration Test Validates Schema Alignment

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Systemic

**File**: `tests/test_research.py:216-250`

### The Problem

The existing tests for `CodaSearchAdapter` only test:

- Source type validation
- URL generation

They don't actually run queries against a database, which is why this bug shipped. The tests use unit-level mocking and never validate that the SQL queries match the actual schema.

### Why This Matters

Looking at the test file, the Coda adapter tests are significantly thinner than other adapter tests. There's no:

- Test with an in-memory SQLite database
- Test that actually fetches a row and validates the mapping
- Test that verifies the metadata structure

This means the same class of bug (schema drift) can recur whenever someone modifies the database schema or the queries.

### Current Test Coverage

```python
class TestCodaSearchAdapter:
    def test_source_type_page(self):
        adapter = CodaSearchAdapter(source_type="coda_page")
        assert adapter.get_source_type() == "coda_page"
    # ... URL tests only
```

### Suggested Approach

Add an integration-style test that creates an in-memory SQLite database with the correct schema and validates the adapter can extract content:

```python
def test_extract_page_from_sqlite(self, tmp_path):
    """Test actual page extraction from SQLite."""
    db_path = tmp_path / "test_coda.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            canvas_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            file_path TEXT,
            char_count INTEGER,
            extracted_at TEXT
        )
    """)
    conn.execute("""
        INSERT INTO pages (canvas_id, title, content)
        VALUES ('test_page_1', 'Test Page Title', 'This is sufficient test content for extraction.')
    """)
    conn.commit()
    conn.close()

    adapter = CodaSearchAdapter(source_type="coda_page", db_path=db_path)
    result = adapter.extract_content("test_page_1")

    assert result is not None
    assert result.title == "Test Page Title"
```

This would have caught the `name` vs `title` bug before it shipped.

---

## M3: Magic Number for Content Length Threshold

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `src/research/adapters/coda_adapter.py:124,139`

### The Problem

The number `50` appears twice as a content length threshold:

- Line 124: `WHERE content IS NOT NULL AND LENGTH(content) > 50`
- Line 139: `if not content or len(content.strip()) < 50:`

This is a magic number with no explanation of why 50 characters is the threshold.

### Why This Matters

A future developer might:

1. Change one instance but not the other
2. Not understand why this threshold exists (is 50 too high? too low?)
3. Miss that there are two places enforcing the same rule

### Suggested Fix

Extract to a named constant:

```python
# Minimum content length to consider a page meaningful
# Pages shorter than this are typically navigation/stub pages
MIN_CONTENT_LENGTH = 50
```

This is a pre-existing issue, not introduced by this PR, but worth noting since we're touching these lines.

---

## M4: Implicit Import Inside Method

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `src/research/adapters/coda_adapter.py:148`

### The Problem

The `re` module is imported inside `_row_to_page_content()`:

```python
if "@" in title:
    import re
    match = re.search(r'[\w\.-]+@[\w\.-]+', title)
```

### Why This Matters

This is a minor clarity issue, but:

1. Imports inside functions are unusual in this codebase
2. It makes the function's dependencies non-obvious
3. The pattern suggests this was added later as a quick fix

This is pre-existing, not from this PR, but if we're doing maintainability review, it's worth flagging.

---

## Checklist Evaluation

| Question                                  | Answer                                          |
| ----------------------------------------- | ----------------------------------------------- |
| Can I understand this without the author? | Mostly yes - the fix is straightforward         |
| If this breaks at 2am, can I debug it?    | Partially - would need to hunt for schema       |
| Can I change this without fear?           | No - no integration tests to catch schema drift |
| Would this make sense in 6 months?        | Yes, if schema docs added                       |

---

## Verdict: COMMENT

The functional fix is correct and the PR should proceed. However, I recommend addressing M1 (schema documentation) before merge to prevent future schema drift issues. M2 (integration tests) could be tracked as a follow-up issue.

**Issues Summary**:

- M1 (MEDIUM): Add schema documentation comment
- M2 (MEDIUM): Add integration test for schema validation
- M3 (LOW): Magic number 50 for content length (pre-existing)
- M4 (LOW): Inline import of `re` module (pre-existing)
