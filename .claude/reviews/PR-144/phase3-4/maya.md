# Maya Maintainability Review - PR #144 Phase 3+4 Round 1

**Verdict**: APPROVE (with suggestions)
**Date**: 2026-01-28

## Summary

The Smart Digest integration changes are generally well-documented with clear comments explaining the "why" behind key decisions. The code follows consistent patterns across files and uses meaningful names. However, I found 5 maintainability improvements that would help future developers understand the code faster: a magic number in prompt formatting, duplicated context-building logic across services, an implicit fallback pattern that could confuse readers, and two areas where documentation could be enhanced.

---

## M1: Magic Number in Key Excerpts Truncation

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `/Users/paulyokota/Documents/GitHub/FeedForward/src/prompts/pm_review.py:118-119`

### The Problem

The `_format_key_excerpts` function uses hardcoded limits (5 excerpts, 300 chars) without explanation of why these specific values were chosen.

### The Maintainer's Test

- Can I understand without author? No - why 5? why 300?
- Can I debug at 2am? Yes
- Can I change without fear? No - unclear if these limits are coordinated elsewhere
- Will this make sense in 6 months? Partially

### Current Code

```python
def _format_key_excerpts(key_excerpts: list[dict]) -> str:
    ...
    for i, excerpt in enumerate(key_excerpts[:5], 1):  # Limit to 5 excerpts
        text = excerpt.get("text", "")[:300]  # Truncate long excerpts
```

### Suggested Improvement

```python
# Constants for prompt token budget management
# 5 excerpts x ~300 chars each = ~1500 chars, keeping prompt under 4K tokens
MAX_KEY_EXCERPTS_IN_PROMPT = 5
MAX_EXCERPT_TEXT_LENGTH = 300

def _format_key_excerpts(key_excerpts: list[dict]) -> str:
    ...
    for i, excerpt in enumerate(key_excerpts[:MAX_KEY_EXCERPTS_IN_PROMPT], 1):
        text = excerpt.get("text", "")[:MAX_EXCERPT_TEXT_LENGTH]
```

### Why This Matters

Future maintainers tuning prompt sizes need to know these limits exist and why they were set to these values. The constants also enable consistent reuse if the same limits apply elsewhere.

---

## M2: Duplicated Smart Digest Context-Building Pattern

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Systemic

**File**: `/Users/paulyokota/Documents/GitHub/FeedForward/src/prompts/pm_review.py:149-163` and `/Users/paulyokota/Documents/GitHub/FeedForward/src/story_tracking/services/pm_review_service.py:286-297`

### The Problem

The same Smart Digest vs Excerpt fallback logic appears in two places: `format_conversations_for_review()` in pm_review.py and `_format_conversations()` in PMReviewService. This duplication means changes to the fallback behavior must be made in two places.

### The Maintainer's Test

- Can I understand without author? Yes
- Can I debug at 2am? Harder - which one is actually used?
- Can I change without fear? No - must update both places
- Will this make sense in 6 months? Confusing - why two implementations?

### Current Code

In `pm_review.py`:

```python
if diagnostic_summary:
    # Smart Digest available - use richer context
    key_excerpts_formatted = _format_key_excerpts(key_excerpts)
    context_section = SMART_DIGEST_TEMPLATE.format(...)
else:
    # Fallback: use raw excerpt
    excerpt = conv.get("excerpt", "")[:200]
    context_section = EXCERPT_TEMPLATE.format(excerpt=excerpt)
```

In `pm_review_service.py`:

```python
if conv.diagnostic_summary:
    key_excerpts_formatted = _format_key_excerpts(conv.key_excerpts or [])
    context_section = SMART_DIGEST_TEMPLATE.format(...)
else:
    excerpt = (conv.excerpt or "")[:500]  # Note: different limit!
    context_section = EXCERPT_TEMPLATE.format(excerpt=excerpt)
```

### Suggested Improvement

The PMReviewService should import and use `format_conversations_for_review()` from pm_review.py, or a shared helper should be extracted. Note the inconsistent truncation limits (200 vs 500 chars).

### Why This Matters

The 200 vs 500 character inconsistency is a bug waiting to happen. One path gives more context than the other, which could affect PM review decisions unpredictably.

---

## M3: Implicit Fallback Chain Needs Documentation

**Severity**: LOW | **Confidence**: High | **Scope**: Isolated

**File**: `/Users/paulyokota/Documents/GitHub/FeedForward/src/api/routers/pipeline.py:605-614`

### The Problem

The fallback chain (full_conversation -> customer_digest -> source_body) is mentioned in a comment but the actual fallback behavior is split across the theme extractor call and the caller. A reader needs to trace through multiple files to understand the complete fallback logic.

### The Maintainer's Test

- Can I understand without author? Partially - need to check theme_extractor.py
- Can I debug at 2am? Harder than necessary
- Can I change without fear? Need to verify extractor behavior first
- Will this make sense in 6 months? Need to cross-reference

### Current Code

```python
# Issue #144: Pass full_conversation for richer theme extraction with
# diagnostic_summary and key_excerpts. Fallback chain:
# full_conversation -> customer_digest -> source_body
customer_digest = conversation_digests.get(conv.id)
full_conversation = conversation_full_texts.get(conv.id)
theme = extractor.extract(
    conv,
    strict_mode=False,
    customer_digest=customer_digest,
    full_conversation=full_conversation,
    use_full_conversation=True,  # Issue #144: Use full conversation when available
)
```

### Suggested Improvement

Add a docstring or inline comment that explicitly states what the extractor will use when both are None:

```python
# Issue #144: Fallback chain for theme extraction context:
# 1. full_conversation (when use_full_conversation=True) - richest context
# 2. customer_digest - curated summary from support_insights
# 3. conv.source_body - raw conversation text (always present)
# See ThemeExtractor.extract() for implementation details.
```

### Why This Matters

When debugging theme quality issues, developers need to know exactly which text source was used for extraction without tracing through the extractor implementation.

---

## M4: ConversationData Dataclass Needs Field Documentation

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `/Users/paulyokota/Documents/GitHub/FeedForward/src/story_tracking/services/story_creation_service.py:159-175`

### The Problem

The `ConversationData` dataclass has grown with Smart Digest fields but lacks field-level documentation explaining the purpose and expected format of each field.

### The Maintainer's Test

- Can I understand without author? Mostly - but key_excerpts format is unclear
- Can I debug at 2am? Need to find source to understand field meanings
- Can I change without fear? Might break consumers
- Will this make sense in 6 months? Need to trace usage

### Current Code

```python
@dataclass
class ConversationData:
    """Conversation data from theme extraction."""

    id: str
    issue_signature: str
    product_area: Optional[str] = None
    # ... many fields ...
    # Smart Digest fields (Issue #144) - used for PM Review when available
    diagnostic_summary: Optional[str] = None
    # Format: [{"text": "...", "relevance": "Why this matters"}, ...]
    key_excerpts: List[dict] = field(default_factory=list)
```

### Suggested Improvement

```python
@dataclass
class ConversationData:
    """
    Conversation data from theme extraction for story creation.

    This dataclass aggregates classification and theme data for a single
    conversation, used by StoryCreationService to build stories and orphans.
    """

    id: str  # Intercom conversation ID
    issue_signature: str  # Theme signature from classification
    product_area: Optional[str] = None  # Tailwind product area (scheduling, analytics, etc.)
    # ...

    # Smart Digest fields (Issue #144)
    # Used for PM Review to provide richer context than raw excerpts
    diagnostic_summary: Optional[str] = None
    """LLM-generated summary of the customer's issue."""

    key_excerpts: List[dict] = field(default_factory=list)
    """
    Relevant conversation excerpts with context.
    Format: [{"text": "excerpt text", "relevance": "Why this matters"}, ...]
    Populated during classification when full_conversation is available.
    """
```

### Why This Matters

As the dataclass grows, field-level documentation prevents misuse and helps developers understand which fields are required vs optional for different code paths.

---

## M5: Context Gap Endpoint Missing Query Explanation

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `/Users/paulyokota/Documents/GitHub/FeedForward/src/api/routers/analytics.py:343-394`

### The Problem

The SQL query in `get_context_gaps` has a complex join and date filtering logic, but the comment block doesn't explain why the query is structured this way or what the expected data shape is.

### The Maintainer's Test

- Can I understand without author? Need to trace schema
- Can I debug at 2am? Need to understand context_usage_logs table first
- Can I change without fear? Unclear which parts are essential
- Will this make sense in 6 months? Need schema context

### Current Code

```python
cur.execute(
    """
    SELECT
        c.context_used,
        c.context_gaps,
        t.product_area
    FROM context_usage_logs c
    LEFT JOIN themes t ON c.theme_id = t.id
    WHERE c.created_at >= %s AND c.created_at <= %s
    """,
    (period_start, period_end),
)
```

### Suggested Improvement

Add a comment explaining the query structure:

```python
# Query context_usage_logs with theme join for product_area grouping.
# LEFT JOIN ensures we capture logs even if theme was later deleted.
# context_used/context_gaps are JSONB arrays populated by theme extractor
# when it reports what product docs it referenced vs what was missing.
cur.execute(
    """
    SELECT
        c.context_used,
        c.context_gaps,
        t.product_area
    FROM context_usage_logs c
    LEFT JOIN themes t ON c.theme_id = t.id
    WHERE c.created_at >= %s AND c.created_at <= %s
    """,
    (period_start, period_end),
)
```

### Why This Matters

When optimizing query performance or debugging missing data, developers need to understand the relationship between context_usage_logs and themes without digging through schema migrations.

---

## Positive Observations

1. **Good issue references**: Consistent use of `# Issue #144` comments helps trace features back to requirements
2. **Clear template separation**: The SMART_DIGEST_TEMPLATE and EXCERPT_TEMPLATE in pm_review.py make the prompt structure easy to understand
3. **Graceful degradation**: The fallback patterns are defensive and won't break if Smart Digest data is missing
4. **Good docstrings**: Most functions have clear docstrings explaining Args and Returns
5. **Consistent field naming**: `diagnostic_summary` and `key_excerpts` are used consistently across all files

---
