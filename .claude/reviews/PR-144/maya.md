# Maya Maintainability Review - PR #144 Round 1

**Verdict**: APPROVE (with suggestions)
**Date**: 2026-01-28

## Summary

The Smart Digest implementation is well-documented with good inline comments explaining the WHY. The Theme dataclass has comprehensive docstrings, the migration includes SQL comments, and the new `pipeline-disambiguation.md` is excellent product context. However, I found four maintainability improvements: two magic numbers without named constants, one implicit assumption about relevance format, and one potential confusion point in the fallback logic. Overall, this PR is clear and maintainable.

---

## M1: Magic number 30000 for context limit appears in multiple places

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Systemic

**File**: `src/theme_extractor.py:169, 178, 958`

### The Problem

The context character limit of 30000 appears in three different places without a named constant. A future developer changing this limit would need to hunt down all occurrences, risking inconsistency.

### The Maintainer's Test

- Can I understand without author? Yes - comments explain the purpose
- Can I debug at 2am? Yes
- Can I change without fear? **No** - would need to find all occurrences
- Will this make sense in 6 months? Yes

### Current Code

```python
# In load_product_context():
if len(content) > 30000:
    content = content[:30000] + "\n\n[truncated for length]"
# ...
if len(content) > 30000:
    content = content[:30000] + "\n\n[truncated for length]"

# In extract():
product_context=self.product_context[:30000],  # Increased from 10K to 30K (Issue #144)
```

### Suggested Improvement

```python
# At module level:
# Maximum characters per product context file (Issue #144: increased from 15K to 30K)
# Supports richer analysis while staying within LLM context window limits.
MAX_CONTEXT_CHARS_PER_FILE = 30_000

# Then use the constant:
if len(content) > MAX_CONTEXT_CHARS_PER_FILE:
    content = content[:MAX_CONTEXT_CHARS_PER_FILE] + "\n\n[truncated for length]"
```

### Why This Matters

When tuning context limits (e.g., with larger context windows), one constant change updates all locations consistently.

---

## M2: Magic number 500 for excerpt text truncation

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `src/theme_extractor.py:1071`

### The Problem

The key_excerpts text truncation limit of 500 characters is a magic number without explanation of why 500 was chosen.

### The Maintainer's Test

- Can I understand without author? Mostly - it's a truncation limit
- Can I debug at 2am? Yes
- Can I change without fear? **No** - unclear what breaks if changed
- Will this make sense in 6 months? No - why 500?

### Current Code

```python
validated_excerpts.append({
    "text": str(excerpt.get("text", ""))[:500],  # Limit text length
    "relevance": excerpt.get("relevance", "medium"),
})
```

### Suggested Improvement

```python
# At module level:
# Maximum characters per key excerpt (balances detail vs storage/token cost)
MAX_EXCERPT_TEXT_LENGTH = 500

# In validation:
validated_excerpts.append({
    "text": str(excerpt.get("text", ""))[:MAX_EXCERPT_TEXT_LENGTH],
    "relevance": excerpt.get("relevance", "medium"),
})
```

### Why This Matters

Future maintainers will want to know if 500 is arbitrary or derived from analysis. A constant with a comment makes the intent clear.

---

## M3: Implicit assumption about relevance field format

**Severity**: MEDIUM | **Confidence**: Medium | **Scope**: Isolated

**File**: `src/theme_extractor.py:1070-1074`

### The Problem

The prompt instructs LLM to return relevance as a description ("Why this excerpt matters"), but the code defaults to "medium" as if it expects high/medium/low. The migration comment also says "relevance: high|medium|low". This inconsistency between documentation and implementation could confuse future developers.

### The Maintainer's Test

- Can I understand without author? **No** - prompt says description, code assumes enum
- Can I debug at 2am? Maybe - would need to check DB for actual values
- Can I change without fear? No - unclear which format is correct
- Will this make sense in 6 months? No

### Current Code

Prompt (line 353):

```json
{
  "text": "Copy exact text VERBATIM from conversation - no paraphrasing",
  "relevance": "Why this excerpt matters for understanding/reproducing the issue"
}
```

Migration (line 15):

```sql
-- Format: [{"text": "...", "relevance": "high|medium|low"}, ...]
```

Validation (line 1073):

```python
"relevance": excerpt.get("relevance", "medium"),
```

### Suggested Improvement

Choose one format and be consistent:

**Option A (Free-form relevance explanation):**

```python
# Update migration comment:
-- Format: [{"text": "...", "relevance": "description of why this matters"}, ...]

# Update code default:
"relevance": excerpt.get("relevance", "Relevance not specified"),
```

**Option B (Enum-based relevance):**

```python
# Update prompt:
"relevance": "high|medium|low - importance for debugging"
```

### Why This Matters

A developer querying `key_excerpts` JSONB won't know whether to filter by `relevance = 'high'` or parse a description string. The mismatch will cause confusion.

---

## M4: Complex fallback logic in extract() could benefit from flow comment

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `src/theme_extractor.py:929-951`

### The Problem

The three-level fallback logic (full_conversation -> customer_digest -> source_body) is correctly implemented but dense. A future developer modifying this might accidentally break the priority order.

### The Maintainer's Test

- Can I understand without author? Yes, but requires careful reading
- Can I debug at 2am? Mostly
- Can I change without fear? No - might break fallback order
- Will this make sense in 6 months? Yes with effort

### Current Code

```python
# Determine source text for extraction (Issue #144 - Smart Digest)
# Priority order when use_full_conversation=True:
#   1. full_conversation (all messages, richest context)
#   2. customer_digest (first + most specific, good fallback)
#   3. source_body (first message only, minimal context)
# When use_full_conversation=False, skip full_conversation
source_text = ""
using_full_conversation = False

if use_full_conversation and full_conversation and len(full_conversation.strip()) > 10:
    source_text = prepare_conversation_for_extraction(full_conversation.strip())
    using_full_conversation = True
    logger.debug(f"Conv {conv.id}: Using full conversation ({len(source_text)} chars)")
elif customer_digest and len(customer_digest.strip()) > 10:
    source_text = customer_digest.strip()
    logger.debug(f"Conv {conv.id}: Using customer_digest ({len(source_text)} chars)")
else:
    source_text = conv.source_body or ""
    if customer_digest is not None or full_conversation is not None:
        logger.debug(f"Conv {conv.id}: Falling back to source_body")
```

### Suggested Improvement

The existing comment is good! Minor suggestion - consider extracting to a helper function to make the intent even clearer:

```python
def _select_source_text(
    conv_id: str,
    use_full_conversation: bool,
    full_conversation: Optional[str],
    customer_digest: Optional[str],
    source_body: str,
) -> tuple[str, bool]:
    """
    Select best source text for theme extraction.

    Priority (when use_full_conversation=True):
      1. full_conversation - richest context
      2. customer_digest - filtered customer messages
      3. source_body - first message only (minimal)

    Returns (source_text, is_using_full_conversation)
    """
    ...
```

### Why This Matters

Extracting to a named function makes the decision process testable independently and signals to future developers that this is a deliberate priority cascade.

---

## Documentation Gaps

1. **context_usage_logs table purpose**: The migration has a comment, but there's no documentation explaining HOW this table will be used for optimization in Phase 2. A brief note in the migration or a TODO would help.

2. **key_excerpts relevance format mismatch**: As noted in M3, the format is inconsistent between prompt, migration, and code.

## Observations (non-blocking)

1. **Good practice**: The docstrings on new Theme fields are excellent. The comment format `# Smart Digest fields (Issue #144)` makes it easy to trace changes back to the issue.

2. **Good test coverage**: The test file thoroughly covers the new functionality with clear test class names (`TestThemeDataclassSmartDigestFields`, `TestPrepareConversationWithTruncation`).

3. **Excellent new documentation**: `pipeline-disambiguation.md` is a valuable addition that will help future LLM prompts and human developers understand the product.

4. **Migration is safe**: Uses `ADD COLUMN IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` patterns, making it idempotent and safe for re-runs.
