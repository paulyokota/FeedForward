# Dmitri's Review: Story Content Generation Feature

**Reviewer**: Dmitri - The Pragmatist
**Date**: 2026-01-26
**Focus**: Over-engineering, YAGNI violations, unnecessary complexity

---

## Executive Summary

This feature shows reasonable pragmatism overall, but I found **4 simplification opportunities** and **2 dead code items**. The retry logic is justified (transient OpenAI errors are real), and the dataclasses are appropriately minimal. However, there's speculative flexibility that should be removed.

---

## Issues Found

### D1: YAGNI - Unused `prompt_template` Parameter [MEDIUM]

**Category**: yagni
**Severity**: medium
**File**: `src/story_tracking/services/story_content_generator.py:121-135`

**What**: The `prompt_template` parameter is accepted in the constructor but **never used**:

```python
def __init__(
    self,
    model: str = "gpt-4o-mini",
    prompt_template: Optional[str] = None,  # <-- YAGNI
    temperature: float = 0.3,
    timeout: float = DEFAULT_TIMEOUT,
):
    ...
    self.prompt_template = prompt_template  # Reserved for future customization
```

**Why it's bloat**: Comment says "Reserved for future customization" - classic YAGNI. The `_call_llm` method always uses `build_story_content_prompt()` and ignores `self.prompt_template`.

**Fix**: Remove the parameter entirely. When/if customization is needed, add it then. Current code adds confusion without benefit.

---

### D2: Dead Code - `get_category_verb()` Function [LOW]

**Category**: yagni
**Severity**: low
**File**: `src/prompts/story_content.py:290-301`

**What**: Function `get_category_verb()` and constant `CATEGORY_VERBS` are defined, exported, and imported but **never actually called** anywhere in the codebase.

```python
# Defined in story_content.py
CATEGORY_VERBS = {
    "product_issue": "Fix",
    "feature_request": "Add",
    ...
}

def get_category_verb(classification_category: str) -> str:
    return CATEGORY_VERBS.get(classification_category, "Fix")
```

The function is imported in `story_content_generator.py:29` but never invoked. The LLM prompt already contains the verb mapping in its instructions - this helper is redundant.

**Fix**: Remove `CATEGORY_VERBS` and `get_category_verb()`. If they're truly needed for mechanical fallback title generation, add them back when that use case materializes.

---

### D3: Over-Engineering - Three Formatting Functions That Do the Same Thing [LOW]

**Category**: over-engineering
**Severity**: low
**File**: `src/prompts/story_content.py:185-254`

**What**: Three separate functions that are nearly identical:

```python
def format_user_intents(user_intents: List[str]) -> str:
    if not user_intents:
        return "- (No user intent data available)"
    unique_intents = list(dict.fromkeys(user_intents))[:5]
    return "\n".join(f"- {intent}" for intent in unique_intents)

def format_symptoms(symptoms: List[str]) -> str:
    if not symptoms:
        return "- (No symptom data available)"
    unique_symptoms = list(dict.fromkeys(symptoms))[:5]
    return "\n".join(f"- {symptom}" for symptom in unique_symptoms)
```

These are identical except for variable names and the empty-case message.

**Pragmatist's Question**: Could this be 10 lines instead of 30?

**Fix**: Single helper:

```python
def format_list_section(items: List[str], empty_msg: str, limit: int = 5) -> str:
    if not items:
        return f"- ({empty_msg})"
    unique = list(dict.fromkeys(items))[:limit]
    return "\n".join(f"- {item}" for item in unique)
```

---

### D4: Complexity - Markdown Code Block Parsing in \_parse_response [LOW]

**Category**: config-complexity
**Severity**: low
**File**: `src/story_tracking/services/story_content_generator.py:315-319`

**What**: The code handles markdown code blocks despite using `response_format={"type": "json_object"}`:

````python
# Handle potential markdown code blocks
if "```json" in response_text:
    response_text = response_text.split("```json")[1].split("```")[0]
elif "```" in response_text:
    response_text = response_text.split("```")[1].split("```")[0]
````

**Why it might be unnecessary**: When using OpenAI's JSON mode (`response_format={"type": "json_object"}`), the API guarantees valid JSON output without markdown wrapping. This defensive code may be solving a problem that doesn't exist anymore.

**However**: I'll downgrade this to informational. If there's historical evidence of OpenAI returning markdown-wrapped JSON even in JSON mode, keep it. Otherwise, consider removing after monitoring.

---

### D5: YAGNI - Unused Optional Fields in StoryContentInput [INFORMATIONAL]

**Category**: yagni
**Severity**: informational
**File**: `src/prompts/story_content.py:179-182`

**What**: Three optional fields are defined:

```python
root_cause_hypothesis: Optional[str] = None
affected_flow: Optional[str] = None
excerpts: Optional[List[str]] = None  # Conversation excerpts for additional context
```

These are used in `format_optional_context()` but let me check actual usage...

**Update**: After checking `story_creation_service.py`, I see `root_cause_hypothesis` and `affected_flow` ARE populated. The `excerpts` field is also used. This one is **valid** - withdrawing the concern.

---

## What's NOT Bloat (Justified Complexity)

### Retry Logic with Exponential Backoff

The retry logic for OpenAI errors (RateLimitError, APITimeoutError, etc.) is **justified**. These errors are common and transient. Without retry, the pipeline would fail unnecessarily.

### Two Dataclasses (StoryContentInput, GeneratedStoryContent)

These are **appropriately minimal**. StoryContentInput has 9 fields that map directly to prompt inputs. GeneratedStoryContent has 5 fields for the 5 LLM outputs. No unnecessary abstraction.

### Mechanical Fallback Logic

The fallback when LLM fails is **necessary** for pipeline robustness. The fallbacks are simple (humanize signature, use boilerplate) and don't over-engineer.

### Separate Prompt File

Having `src/prompts/story_content.py` separate from `story_content_generator.py` is **good separation**. Kai owns prompts, Marcus owns the generator. This is organizational, not over-engineering.

---

## Recommendations Summary

| Issue                              | Severity      | Action                            |
| ---------------------------------- | ------------- | --------------------------------- |
| D1: Unused `prompt_template` param | Medium        | Remove parameter                  |
| D2: Dead `get_category_verb()`     | Low           | Remove function and constant      |
| D3: Duplicate formatting functions | Low           | Consider consolidating (optional) |
| D4: Markdown parsing               | Informational | Monitor if truly needed           |

---

## Metrics

- **Total Issues**: 4 (1 medium, 2 low, 1 informational)
- **Simplification Opportunities**: 2 clear, 1 optional
- **Dead Code Items**: 2 (`prompt_template`, `get_category_verb`)
- **Unnecessary Abstractions**: 0
- **YAGNI Violations**: 2

---

_Generated by Dmitri - The Pragmatist_
_"Could this be 10 lines instead of 100?"_
