# Quinn - Quality Champion Review: Story Content Generation

**Reviewer**: Quinn (Quality Champion)
**Date**: 2026-01-26
**PR Focus**: Story Content Generation - LLM-generated story fields

---

## PASS 1: Brain Dump (Unfiltered Concerns)

Every concern that came to mind while reviewing:

1. Mechanical fallback produces "Tailwind user" and "achieve my goals without friction" - these are explicitly called out as BAD examples in the prompt!
2. Classification categories are hardcoded in multiple places - VALID_CATEGORIES in generator vs CATEGORY_VERBS in prompt
3. The `classification_category` parameter defaults to "product_issue" in `_generate_story_content` - what if the actual category is different?
4. No validation that the LLM output actually follows the prompt guidelines (e.g., title starts with correct verb)
5. The fallback user_story_want uses raw user_intent directly instead of converting to "to be able to" format
6. Long prompt truncation (12000 chars) could cut important context mid-sentence
7. STORY_CONTENT_GENERATOR_AVAILABLE feature flag could cause silent behavior differences
8. Integration in story_formatter.py imports GeneratedStoryContent with try/except - silent degradation
9. Tests mock OpenAI but don't validate prompt quality against real examples
10. `_format_user_story` in story_formatter.py has complex priority logic between theme_data and generated_content
11. What happens if LLM returns title without the expected action verb for the category?
12. Markdown code block parsing could fail on edge cases (triple backticks in content)
13. Temperature 0.3 might still produce inconsistent outputs for similar inputs
14. No metrics/logging to track LLM vs fallback usage rates
15. `_build_story_content_input` only uses first user_intent even if multiple exist
16. Excerpts limited to 3 in `_build_story_content_input` but 5 in prompt formatter - inconsistency?
17. The ai_agent_goal fallback lacks "Success:" criteria format

---

## PASS 2: Traced Implications & Severity Rating

### Q1: CRITICAL - Mechanical Fallback Produces Explicitly Bad Content

**Category**: quality-impact
**Severity**: HIGH
**Files**: `src/story_tracking/services/story_content_generator.py` (lines 376-421)

**Evidence**:
The prompt explicitly says these are BAD examples to never use:

- `user_type`: "Tailwind user" - prompt says "Bad examples (never use): 'Tailwind user' (too generic)"
- `user_story_benefit`: "achieve my goals without friction" - prompt says "Bad examples (never use): 'achieve my goals without friction' (boilerplate)"

But the mechanical fallback returns EXACTLY these values:

```python
return GeneratedStoryContent(
    title=title,
    user_type="Tailwind user",  # Explicitly bad per prompt!
    user_story_want=want,
    user_story_benefit="achieve my goals without friction",  # Explicitly bad per prompt!
    ai_agent_goal=ai_goal,
)
```

**Impact**: When LLM fails (transient errors, rate limits, etc.), stories are created with content quality the prompt itself says is unacceptable. This defeats the purpose of having quality guidelines.

**Recommendation**: Fallback should produce clearly-marked placeholder content like "[Auto-generated - manual review needed]" OR use more contextual fallbacks like:

- `user_type`: Build from product_area/component: "user working with {product_area}"
- `user_story_benefit`: "this issue is resolved" or use symptom data

---

### Q2: HIGH - Classification Category Not Passed From Upstream

**Category**: missed-update
**Severity**: HIGH
**Files**:

- `src/story_tracking/services/story_creation_service.py` (line 1967)
- `src/story_tracking/services/story_content_generator.py` (VALID_CATEGORIES)

**Evidence**:
The `_generate_story_content` method defaults `classification_category` to "product_issue":

```python
def _generate_story_content(
    self,
    signature: str,
    theme_data: Dict[str, Any],
    classification_category: str = "product_issue",  # Default!
) -> Optional["GeneratedStoryContent"]:
```

However, I searched `story_creation_service.py` and the calls to `_generate_story_content` don't appear to pass the actual classification category from the conversation data. The theme_data dict doesn't include `classification_category` in `_build_theme_data`.

**Impact**: All stories may be generated with "Fix" action verb even when they should use "Add" (feature_request), "Clarify" (how_to_question), or "Resolve" (account_issue). This produces misleading titles.

**Recommendation**:

1. Add `classification_category` to theme_data aggregation
2. Pass actual category through the call chain
3. Add integration test verifying correct verb selection per category

---

### Q3: MEDIUM - Inconsistent ai_agent_goal Fallback Format

**Category**: quality-impact
**Severity**: MEDIUM
**Files**: `src/story_tracking/services/story_content_generator.py` (lines 411-413)

**Evidence**:
The prompt requires ai_agent_goal to include "Success:" criteria:

```
**Format**: `[Action verb] the [specific issue]. Success: [measurable criteria]`
Must include:
- Explicit "Success:" criteria (observable, measurable)
```

But the fallback produces:

```python
ai_goal = f"{intent_prefix}. Fix the reported issue and restore expected functionality."
```

This lacks the required "Success:" keyword and measurable criteria.

**Impact**: Fallback ai_agent_goals won't match the expected format, making them less useful for AI agents parsing the ticket.

**Recommendation**:

```python
ai_goal = f"{intent_prefix}. Success: issue is resolved and functionality works as expected."
```

---

### Q4: MEDIUM - Integration Tests Mock LLM Completely

**Category**: regression-risk
**Severity**: MEDIUM
**Files**: `tests/story_tracking/test_story_content_generator.py`

**Evidence**:
All tests mock the OpenAI client entirely. The integration test class is marked `@pytest.mark.skip`:

```python
@pytest.mark.skip(reason="Requires OpenAI API key - run manually")
class TestStoryContentGeneratorIntegration:
```

This means there's no automated validation that:

1. The prompt actually produces valid JSON
2. The LLM follows the formatting rules
3. The title verbs match categories
4. The output fields match the prompt requirements

**Impact**: Prompt changes could silently break output quality without any test catching it. Only manual testing would reveal issues.

**Recommendation**:

- Add a functional test fixture that captures LLM output samples
- Compare against golden examples
- OR flag this for FUNCTIONAL_TEST_REQUIRED

---

### Q5: MEDIUM - story_formatter.py Complex Fallback Logic

**Category**: system-conflict
**Severity**: MEDIUM
**Files**: `src/story_formatter.py` (lines 941-975)

**Evidence**:
The `_format_user_story` method has layered fallback logic:

```python
# Start with theme_data defaults (which may already include generated values)
user_type = theme_data.get("user_type", "Tailwind user")
user_intent = theme_data.get("user_intent", "use the product successfully")
benefit = theme_data.get("benefit", "achieve my goals without friction")

# Override with generated content if available (higher priority)
if generated_content:
    if generated_content.user_type:
        user_type = generated_content.user_type
    ...
```

But now with Q1, the generated_content itself might contain "Tailwind user" from fallback, meaning the fallback bad values can come from either:

1. theme_data defaults
2. generated_content fallback

This creates confusion about the source of bad values and makes debugging harder.

**Impact**: Two independent fallback chains producing the same bad content obscures where quality problems originate.

**Recommendation**:

- Story formatter should detect fallback markers
- OR generator should use distinct fallback values like "[FALLBACK: Tailwind user]"

---

### Q6: LOW - No Observability for LLM vs Fallback Usage

**Category**: quality-impact
**Severity**: LOW
**Files**: `src/story_tracking/services/story_content_generator.py`

**Evidence**:
The generator logs at DEBUG level when LLM succeeds or fails:

```python
logger.debug(f"Generated story content for '{signature}': title='{generated_content.title[:50]}...'")
logger.warning(f"Story content generation failed for '{signature}': {e}...")
```

But there's no structured metric tracking:

- LLM success rate
- Fallback trigger rate
- Retry counts
- Error types distribution

**Impact**: In production, we won't know if 50% of stories are getting fallback content vs 5%.

**Recommendation**: Add structured metrics:

```python
metrics.increment("story_content.generation", tags={"source": "llm" | "fallback"})
```

---

### Q7: LOW - Prompt Truncation Could Break Context

**Category**: quality-impact
**Severity**: LOW
**Files**: `src/story_tracking/services/story_content_generator.py` (lines 268-273)

**Evidence**:

```python
max_prompt_chars = 12000  # ~4000 tokens with buffer
if len(prompt) > max_prompt_chars:
    logger.debug(f"Truncating prompt from {len(prompt)} to {max_prompt_chars} chars")
    prompt = prompt[:max_prompt_chars]
```

This truncates without considering:

- Markdown section boundaries
- JSON template integrity
- Word boundaries

**Impact**: Truncation could produce incomplete prompt sections or cut the JSON template, causing parsing failures.

**Recommendation**: Truncate before formatting the prompt (e.g., truncate excerpts) rather than after.

---

## FUNCTIONAL_TEST_REQUIRED Decision

**FUNCTIONAL_TEST_REQUIRED: YES**

**Reasoning**:

1. This is a new LLM prompt (story_content.py) that directly affects output quality
2. The mechanical fallback produces content explicitly marked as bad in the prompt
3. Classification category flow is not validated end-to-end
4. Unit tests mock the LLM entirely - no validation of actual prompt behavior
5. Per `docs/process-playbook/gates/functional-testing-gate.md`, LLM/pipeline changes require functional test evidence

**Required Functional Tests**:

1. Run pipeline with sample conversations for each classification category
2. Verify titles start with correct verb (Fix/Add/Clarify/Resolve)
3. Verify user_type is NOT "Tailwind user" for LLM-generated content
4. Verify ai_agent_goal contains "Success:" criteria
5. Trigger fallback (mock transient error) and verify fallback content is acceptable or clearly marked

---

## Summary

| ID  | Category        | Severity | Issue                                               |
| --- | --------------- | -------- | --------------------------------------------------- |
| Q1  | quality-impact  | HIGH     | Fallback produces explicitly bad content per prompt |
| Q2  | missed-update   | HIGH     | Classification category not passed from upstream    |
| Q3  | quality-impact  | MEDIUM   | ai_agent_goal fallback lacks "Success:" format      |
| Q4  | regression-risk | MEDIUM   | No automated LLM output validation                  |
| Q5  | system-conflict | MEDIUM   | Dual fallback chains obscure problem source         |
| Q6  | quality-impact  | LOW      | No observability for LLM vs fallback rates          |
| Q7  | quality-impact  | LOW      | Prompt truncation could break context               |

**Blocking Issues**: Q1, Q2 (HIGH severity)
**Requires Functional Test**: YES

---

_Quinn - The Quality Champion_
_"Every change degrades output until proven otherwise."_
