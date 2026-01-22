# Duplicate Assignment Bug Fix - Learnings

**Date**: 2026-01-22
**Commits**: f24c56b (duplicate fix), b8a8a38 (canonicalization), 51551c1 (StructuredDescription)

## Context

This session fixed a subtle bug where PM review splits could assign the same conversation to multiple stories, plus added UI improvements for story descriptions.

## Patterns That Worked Well

### 1. Defense-in-Depth for LLM Output

The duplicate assignment bug showed that LLM output can violate constraints even when instructed. The fix used defense-in-depth:

1. **Prompt constraint** - Explicit instruction that each ID appears in exactly ONE place
2. **Code enforcement** - `pop()` instead of `dict.get()` ensures first assignment wins
3. **Observability** - Warning logs when constraint violations are detected

**Pattern**: Never trust LLM output to follow constraints. Always validate/enforce in code.

### 2. pop() vs get() for Idempotent Assignment

```python
# Before: allows duplicate reads
conv_data = available_conversations.get(conv_id)
if conv_data:
    sub_group_convos.append(conv_data)

# After: get-and-remove prevents duplicates
conv_data = available_conversations.pop(conv_id, None)
if conv_data:
    sub_group_convos.append(conv_data)
```

**Why pop()**: When assigning items from a pool to buckets, `pop()` guarantees each item is assigned exactly once. First assignment wins, subsequent attempts return None.

### 3. Session-Scoped State for Batch Consistency

The canonicalization fix used session-scoped tracking:

```python
_session_signatures: dict[str, str] = {}  # Maps new sig -> canonical sig

def get_existing_signatures():
    # Include both DB signatures AND session-created ones
    return db_signatures | set(_session_signatures.values())
```

**Pattern**: When batch processing needs consistency, track state at session level. Prevents fragmentation where same concept gets different signatures in same batch.

### 4. Known-Header Pattern for Markdown Parsing

`StructuredDescription` only parses known section headers:

```typescript
const KNOWN_SECTIONS = new Set([
  "summary",
  "impact",
  "evidence",
  "user story",
  "acceptance criteria",
  "symptoms",
  "technical notes",
]);
```

**Why restrict**: Prevents over-fragmentation. Random bold text or headers don't create spurious sections.

**Fallback**: If no known sections found, show raw view (graceful degradation).

### 5. Progressive Disclosure for Long Content

Long sections (>5 lines) collapsed by default with "Show N more lines" button:

- Respects user attention
- Keeps critical info visible
- Full content available on demand

**Pattern**: Default to concise, expand on demand.

## Lessons for Future Documentation

1. **LLM constraint violations need regression tests** - The duplicate test explicitly verifies the constraint is enforced
2. **Batch processing state requires explicit scoping** - Document whether state is per-item, per-batch, or global
3. **UI component fallbacks deserve attention** - Document what happens when parsing fails (raw view)
4. **Copy buttons need error states** - User feedback for clipboard failures

## Files Changed

| File                                                    | Purpose                         |
| ------------------------------------------------------- | ------------------------------- |
| `src/story_tracking/services/story_creation_service.py` | pop() for duplicate prevention  |
| `src/prompts/pm_review.py`                              | Explicit uniqueness constraint  |
| `src/theme_extractor.py`                                | Session-scoped canonicalization |
| `webapp/src/components/StructuredDescription.tsx`       | Markdown section parsing        |
| `tests/test_story_creation_service_pm_review.py`        | Duplicate regression test       |

## Related Documentation Updated

- `docs/session/last-session.md` - Session summary with all changes
- `docs/changelog.md` - Four new entries (component, fix, canonicalization, removal)
- `docs/architecture.md` - Section 12 updated for Next.js, Section 14 adds component
- `docs/status.md` - Note added about Streamlit removal
