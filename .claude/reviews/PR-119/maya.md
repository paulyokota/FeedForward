# Maya Maintainability Review - PR #119 Round 1

**Verdict**: APPROVE with suggestions
**Date**: 2026-01-22

## Summary

The code is well-documented with clear docstrings, good variable naming, and helpful comments explaining the WHY behind decisions. Found 3 maintainability improvements around magic constants, error messages, and test documentation. Overall very maintainable.

---

## M1: MIN_GROUP_SIZE constant used without local context

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/story_tracking/services/story_creation_service.py:634-640`

### The Problem

Code checks `if len(conversations) < MIN_GROUP_SIZE` but MIN_GROUP_SIZE is imported from models module (line 5 in tests shows this). In the service file, there's no comment explaining what this threshold means or why it exists.

### The Maintainer's Test

- Can I understand without author? **Partially** - I see it's a threshold but not why
- Can I debug at 2am? **Yes** - but would need to grep for MIN_GROUP_SIZE definition
- Can I change without fear? **No** - don't know impact of changing it
- Will this make sense in 6 months? **Maybe** - depends on remembering the context

### Current Code

```python
# Check minimum group size
if len(conversations) < MIN_GROUP_SIZE:
    self._route_to_orphan_integration(
        signature=cluster.cluster_id,
        conversations=conversations,
        failure_reason=f"Cluster has {len(conversations)} conversations (min: {MIN_GROUP_SIZE})",
        result=result,
    )
    return
```

### Suggested Improvement

Add comment explaining the threshold:

```python
# Check minimum group size
# MIN_GROUP_SIZE (currently 3) is the threshold for creating a story vs orphan.
# Rationale: Stories need multiple examples to demonstrate pattern validity.
# Single or paired conversations are treated as orphans until more evidence accumulates.
if len(conversations) < MIN_GROUP_SIZE:
    self._route_to_orphan_integration(
        signature=cluster.cluster_id,
        conversations=conversations,
        failure_reason=f"Cluster has {len(conversations)} conversations (min: {MIN_GROUP_SIZE})",
        result=result,
    )
    return
```

### Why This Matters

Future maintainer might wonder:
- Why 3? Why not 2 or 5?
- Can I change this threshold?
- What breaks if I do?

The comment answers these questions without requiring archaeology through the codebase.

---

## M2: Generic error messages in fallback path

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `src/story_tracking/services/story_creation_service.py:676-679`

### The Problem

When processing fallback conversations fails, error message is:

```python
logger.warning(f"Failed to process fallback conversation {conv_id}: {e}")
result.errors.append(f"Fallback conversation {conv_id} error: {e}")
```

This is better than nothing, but if I'm debugging at 2am:
- What was the conversation about?
- What issue_signature did it have?
- Why did it fail?

### The Maintainer's Test

- Can I debug at 2am? **Partially** - I know it failed but not why
- Would this make sense in 6 months? **No** - generic error gives no actionable context

### Current Code

```python
except Exception as e:
    logger.warning(f"Failed to process fallback conversation {conv_id}: {e}")
    result.errors.append(f"Fallback conversation {conv_id} error: {e}")
```

### Suggested Improvement

```python
except Exception as e:
    signature = conv_dict.get("issue_signature", "unknown")
    logger.warning(
        f"Failed to process fallback conversation {conv_id} "
        f"(signature='{signature}'): {e}",
        exc_info=True  # Include stack trace in logs
    )
    result.errors.append(
        f"Fallback conversation {conv_id} (signature='{signature}') error: {e}"
    )
```

### Why This Matters

Better error messages = faster debugging. Including signature helps correlate errors with conversation content.

---

## M3: Test class names don't indicate what they test

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `tests/test_hybrid_story_creation.py:1075-1246`

### The Problem

Test classes:
- `TestProcessHybridClusters` - OK, clear
- `TestHybridClusterTitleGeneration` - OK, clear
- `TestStoryClusterFields` - What does this test?

Looking at tests in `TestStoryClusterFields`:
- `test_story_model_has_cluster_fields` - Tests Story model includes cluster fields
- `test_story_model_default_grouping_method` - Tests default value

### The Maintainer's Test

- Will this make sense in 6 months? **Unclear** - "cluster fields" is vague

### Suggested Improvement

Rename to be more specific:

```python
class TestStoryModelClusterFields:
    """Tests for Story model cluster field integration."""
```

OR add a docstring to the current class:

```python
class TestStoryClusterFields:
    """Tests verifying Story model properly handles hybrid clustering fields."""
```

### Why This Matters

When tests fail, clear class names help you understand what broke. "TestStoryClusterFields" could mean many things.

---

## M4: Magic number 500 in excerpt truncation

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `src/api/routers/pipeline.py:725`

### The Problem

```python
"excerpt": (row["source_body"] or "")[:500],
```

Why 500? Is this characters or words? What happens if we change it?

### Suggested Improvement

Extract to named constant:

```python
# At top of file
EXCERPT_MAX_LENGTH = 500  # characters - balance between context and memory usage
```

Then use:

```python
"excerpt": (row["source_body"] or "")[:EXCERPT_MAX_LENGTH],
```

### Why This Matters

Self-documenting code. Future maintainer knows:
- It's 500 characters (not words)
- It's a balance between context and memory
- There's one place to change it if needed

---

## Summary

**APPROVE** with suggestions

The code is generally very maintainable with good documentation. Improvements:

- **M1 (MEDIUM)**: Add comment explaining MIN_GROUP_SIZE threshold and rationale
- **M2 (MEDIUM)**: Include signature in fallback error messages for better debugging
- **M3 (LOW)**: Add docstring to TestStoryClusterFields class
- **M4 (LOW)**: Extract magic number 500 to named constant EXCERPT_MAX_LENGTH

None of these block merge, but they would help future maintainers.

