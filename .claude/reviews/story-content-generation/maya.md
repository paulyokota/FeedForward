# Maya (The Maintainer) - Story Content Generation Review

**Review Date**: 2026-01-26
**Review Focus**: Clarity, maintainability, and 6-month comprehension test
**Files Reviewed**:

- `src/prompts/story_content.py`
- `src/story_tracking/services/story_content_generator.py`
- `src/story_tracking/services/story_creation_service.py`
- `src/story_formatter.py`
- `tests/story_tracking/test_story_content_generator.py`

---

## Summary

The Story Content Generation feature is well-structured with clear separation between prompt definition (Kai's domain) and generation logic (Marcus's domain). The code includes good docstrings and ownership comments. However, I've identified **6 maintainability improvements** that will help future developers (or your future self) understand this code at 2am.

---

## Issues Found

### M1 - Magic Number: 12000 Character Truncation (MEDIUM)

**File**: `src/story_tracking/services/story_content_generator.py`
**Lines**: 268-273

**Problem**: The `max_prompt_chars = 12000` appears inline with only a brief comment. The relationship between 12000 characters and ~4000 tokens is an implicit assumption that a future developer might not understand or verify.

```python
# Truncate if too long (stay under token limits)
max_prompt_chars = 12000  # ~4000 tokens with buffer
if len(prompt) > max_prompt_chars:
```

**Why it matters**: If someone needs to adjust this for a different model with different token limits, they'll need to understand the 3:1 char-to-token assumption. The "buffer" mentioned is unexplained.

**Recommendation**: Extract to a named constant with documentation explaining the calculation:

```python
# At module level:
# OpenAI token estimation: ~3 chars/token for English text
# gpt-4o-mini context window: 8k tokens, output reserve: ~2k tokens
# Safe input budget: ~4000 tokens * 3 chars = 12000 chars
MAX_PROMPT_CHARS = 12000
```

---

### M2 - Magic Number: Title Length 80 Characters (LOW)

**File**: `src/story_tracking/services/story_content_generator.py`
**Lines**: 337-338, 404-406

**Problem**: The 80-character title limit appears in multiple places (once in `_parse_response`, once in `_mechanical_fallback`) without being a constant. The value `77` (80 - 3 for "...") also appears without explanation.

```python
# In _parse_response:
if len(title) > 80:
    title = title[:77] + "..."

# In _mechanical_fallback:
if len(title) > 80:
    title = title[:77] + "..."
```

**Why it matters**: If the title limit changes (e.g., for Shortcut ticket integration), a developer would need to find and update multiple locations.

**Recommendation**: Define at module level:

```python
TITLE_MAX_LENGTH = 80
TITLE_TRUNCATION_SUFFIX = "..."
```

---

### M3 - Magic Number: User Intent Minimum Length 10 Characters (MEDIUM)

**File**: `src/story_tracking/services/story_content_generator.py`
**Lines**: 399

**Problem**: The threshold `10` for determining if user_intent is "meaningful enough" for a title is unexplained.

```python
if user_intent and len(user_intent) > 10:
    title = user_intent
else:
    title = self._humanize_signature(signature)
```

**Why it matters**: A future developer won't understand why 10 was chosen. Is it based on average word length? Minimum useful information? This decision point affects title quality.

**Recommendation**: Extract to a constant with documentation:

```python
# Minimum length for user_intent to be usable as a title
# Shorter intents (e.g., "Help", "Pins") don't provide enough context
MIN_INTENT_LENGTH_FOR_TITLE = 10
```

---

### M4 - Implicit Assumption: Retry Backoff Sequence (LOW)

**File**: `src/story_tracking/services/story_content_generator.py`
**Lines**: 168-179

**Problem**: The exponential backoff sequence (1s, 2s, 4s) is documented in the class docstring but the actual formula `base_delay * (2 ** attempt)` requires mental math to verify the sequence.

```python
base_delay = 1.0  # seconds
# ...
delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
```

**Why it matters**: The comment `# 1s, 2s, 4s` helps, but if `max_retries` changes from 3, the comment becomes misleading.

**Recommendation**: Add inline explanation or extract retry config:

```python
# Exponential backoff: attempt 0 = 1s, attempt 1 = 2s, attempt 2 = 4s
# Formula: base_delay * 2^attempt
```

---

### M5 - Missing Error Context: Mechanical Fallback Logging (MEDIUM)

**File**: `src/story_tracking/services/story_content_generator.py`
**Lines**: 370-421

**Problem**: The `_mechanical_fallback` method doesn't log that fallback was used. When debugging production issues, it's unclear if a story's generic content ("Tailwind user", "achieve my goals without friction") came from fallback or LLM.

```python
def _mechanical_fallback(
    self,
    content_input: StoryContentInput,
) -> GeneratedStoryContent:
    """Generate purely mechanical fallback - no LLM involved."""
    # No logging that fallback was triggered
```

**Why it matters**: When a PM asks "why does this story have generic text?", there's no log trail to indicate fallback was used. The caller logs in some cases but not all paths.

**Recommendation**: Add INFO-level log at the start of `_mechanical_fallback`:

```python
logger.info(
    f"Using mechanical fallback for signature '{content_input.issue_signature}' "
    f"(category: {content_input.classification_category})"
)
```

---

### M6 - Implicit Assumption: Fallback Values Match Prompt Anti-Patterns (MEDIUM)

**File**: `src/story_tracking/services/story_content_generator.py`
**Lines**: 378-382, 418-419

**Problem**: The fallback values `"Tailwind user"` and `"achieve my goals without friction"` are explicitly called out as BAD examples in the prompt template (`story_content.py` lines 87-88, 119-122), but there's no documentation explaining this is intentional (to signal that LLM generation failed).

```python
# In _mechanical_fallback:
user_type="Tailwind user",  # This is marked as "Bad example" in prompt!
user_story_benefit="achieve my goals without friction",  # Also marked as bad!
```

**Why it matters**: A well-meaning developer might "fix" these values thinking they're bugs, not realizing they serve as a signal that content was not LLM-generated.

**Recommendation**: Add explicit comment:

```python
# NOTE: These values intentionally match the "Bad examples" in story_content.py
# This signals to reviewers that LLM generation failed and content needs human editing
user_type="Tailwind user",
user_story_benefit="achieve my goals without friction",
```

---

## Positive Observations

1. **Excellent ownership comments**: Both files clearly identify owners (Kai for prompts, Marcus for generator)
2. **Good docstrings**: GeneratedStoryContent has per-field documentation with examples
3. **Clear separation of concerns**: Prompt template lives separately from generation logic
4. **Comprehensive tests**: 95%+ coverage with edge cases for empty inputs, retries, fallbacks
5. **Graceful degradation**: Multiple fallback levels ensure stories always get created

---

## The Maintainer's Test Results

| Question                                  | Answer                                                    |
| ----------------------------------------- | --------------------------------------------------------- |
| Can I understand this without the author? | Yes, mostly. Magic numbers need explanation.              |
| If this breaks at 2am, can I debug it?    | Partially - need fallback logging for M5.                 |
| Can I change this without fear?           | Yes for most changes; title limit changes need care (M2). |
| Will this make sense in 6 months?         | Yes, with recommended constant extractions.               |

---

## Required Actions

| ID  | Severity | Category            | Action                                                |
| --- | -------- | ------------------- | ----------------------------------------------------- |
| M1  | MEDIUM   | magic-number        | Extract 12000 to constant with token calculation docs |
| M2  | LOW      | magic-number        | Extract 80-char title limit to constant               |
| M3  | MEDIUM   | magic-number        | Extract 10-char threshold with explanation            |
| M4  | LOW      | implicit-assumption | Document backoff formula more clearly                 |
| M5  | MEDIUM   | error-context       | Add logging in \_mechanical_fallback                  |
| M6  | MEDIUM   | implicit-assumption | Document intentional fallback value choice            |

---

_Review by Maya - The Maintainer_
_"Will someone understand this in 6 months?"_
