# Issue #133: Story Description Boilerplate - LLM Enhancement Architecture

> Architecture revision by Priya
> Date: 2026-01-26
> Status: **REVISED** - Previous approach rejected, now using gold-standard LLM enhancement

## Executive Summary

Story descriptions contain generic boilerplate sections that should be **replaced with LLM-generated, context-specific content** - not removed. The gold-standard approach expands `GeneratedStoryContent` with 4 new fields, enabling every section to contain meaningful, specific content derived from symptoms, user_intents, and context.

**Key insight**: The problem is not "too much content" but "too generic content". Removing sections hides the symptom; enhancing them with LLM generation addresses the root cause.

---

## Architecture Decision

**Chosen approach**: Expand `GeneratedStoryContent` with 4 new LLM-generated fields.

| Field                 | Current State                         | Target State                             |
| --------------------- | ------------------------------------- | ---------------------------------------- |
| `acceptance_criteria` | Generic Given/When/Then template      | Specific criteria derived from symptoms  |
| `investigation_steps` | "Verify API responses" (generic)      | Steps specific to component + root cause |
| `success_criteria`    | "All tests pass" (generic)            | Observable outcomes tied to symptoms     |
| `technical_notes`     | "Integration test covering full flow" | Test expectations based on symptom type  |

**Rationale**: Every section in the story description should provide value. Generic content wastes tokens and causes readers to skim. LLM generation transforms these sections from boilerplate into actionable, context-specific guidance.

---

## Data Flow Design

### Current State (5 fields)

```
StoryContentInput ──► LLM ──► GeneratedStoryContent
                              ├── title
                              ├── user_type
                              ├── user_story_want
                              ├── user_story_benefit
                              └── ai_agent_goal
```

### Target State (9 fields)

```
StoryContentInput ──► LLM ──► GeneratedStoryContent
                              ├── title
                              ├── user_type
                              ├── user_story_want
                              ├── user_story_benefit
                              ├── ai_agent_goal
                              ├── acceptance_criteria       # NEW
                              ├── investigation_steps       # NEW
                              ├── success_criteria          # NEW
                              └── technical_notes           # NEW
```

### Data Mapping: Symptoms/Intents to New Fields

| Source Data                | Maps To               | Generation Logic                                         |
| -------------------------- | --------------------- | -------------------------------------------------------- |
| `symptoms[]`               | `acceptance_criteria` | Each symptom becomes a Given/When/Then criterion         |
| `symptoms[]` + `component` | `investigation_steps` | Symptom type + component suggests investigation approach |
| `symptoms[]`               | `success_criteria`    | Observable negation of each symptom = success            |
| `symptoms[]` + `component` | `technical_notes`     | Symptom type determines test expectations (API/E2E/unit) |
| `root_cause_hypothesis`    | `investigation_steps` | Root cause narrows investigation scope                   |
| `user_intents[]`           | `acceptance_criteria` | User goals inform "expected behavior" in Given/When/Then |
| `classification_category`  | `technical_notes`     | Bug vs feature vs how-to affects testing expectations    |

---

## New Field Specifications

### 1. acceptance_criteria: List[str]

**Purpose**: Specific Given/When/Then acceptance criteria derived from symptoms and user intents.

**Generation logic**:

- Parse each symptom to identify: precondition, action, failure mode
- Convert to Given (precondition) / When (action) / Then (expected behavior)
- Include user intent as the "expected behavior" when symptom describes a failure

**Example transformation**:

| Input                                                                 | Output                                                                                                      |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Symptom: "Pin upload fails with Server 0 error when saving to drafts" | "Given a user is uploading a pin, When they save to drafts, Then the pin is saved successfully (no errors)" |
| Symptom: "Schedule times show in wrong timezone"                      | "Given a user views scheduled pins, When timezone is configured, Then times display in the user's timezone" |
| User intent: "Upload pins to my drafts"                               | Informs the "Then" clause expected behavior                                                                 |

**Mechanical fallback**: `["Given the reported conditions, When the user performs the action, Then the expected behavior occurs"]`

### 2. investigation_steps: List[str]

**Purpose**: Context-specific investigation steps based on component, symptoms, and root cause.

**Generation logic**:

- Map symptom type to investigation approach:
  - API error symptoms -> Check API logs, verify request/response
  - Timeout symptoms -> Check timing, network, async patterns
  - UI display issues -> Check rendering, state management, data binding
  - Data inconsistency -> Check database state, caching, race conditions
- Incorporate component name for specificity
- Use root_cause_hypothesis to narrow scope if available

**Example transformation**:

| Input                                                                              | Output                                                                                                                                                                            |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Component: `pin_scheduler`, Symptom: "Server 0 error"                              | ["Check `pin_scheduler` logs for Server 0 responses", "Verify Pinterest API authentication state", "Review error handling in draft save flow", "Test with different pin formats"] |
| Component: `oauth_manager`, Symptom: "Connection times out"                        | ["Check `oauth_manager` timeout configuration", "Review OAuth token refresh logic", "Test with network latency simulation", "Verify retry behavior on transient failures"]        |
| Root cause: "Token refresh race condition causes stale credentials" (if available) | Adds: "Focus on concurrent token refresh scenarios"                                                                                                                               |

**Mechanical fallback**: `[f"Review {component} code for issues matching symptoms", f"Check logs for errors in {product_area} flow"]`

### 3. success_criteria: List[str]

**Purpose**: Observable, measurable success criteria that are the negation of reported symptoms.

**Generation logic**:

- For each symptom, generate the observable positive outcome
- Include timing expectations where relevant (e.g., "within 5 seconds")
- Add regression criteria (existing functionality preserved)

**Example transformation**:

| Symptom                                 | Success Criterion                                                |
| --------------------------------------- | ---------------------------------------------------------------- |
| "Pin upload fails with Server 0 error"  | "Pin uploads complete successfully without errors"               |
| "Schedule times show in wrong timezone" | "Schedule times display correctly in user's configured timezone" |
| "Page loads slowly (>10s)"              | "Page loads within 3 seconds under normal conditions"            |
| "Posts appear in wrong order"           | "Posts display in chronological order as configured"             |
| (Always included)                       | "All existing tests pass (no regressions)"                       |

**Mechanical fallback**: `["Issue is resolved", "Functionality works as expected", "All existing tests pass"]`

### 4. technical_notes: str

**Purpose**: Context-specific testing expectations and architectural notes based on symptom type and component.

**Generation logic**:

- Map symptom category to test type:
  - API/backend symptoms -> "Unit test + API integration test"
  - UI/display symptoms -> "E2E test with visual verification"
  - Performance symptoms -> "Performance benchmark test"
  - Data symptoms -> "Data integrity test with edge cases"
- Include vertical slice based on component location in architecture
- Add component-specific considerations

**Example transformation**:

| Input                                                          | Output                                                                                                                                                                                              |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Component: `pin_scheduler`, Symptom: "Server 0 error"          | "**Testing**: API integration test verifying pin save endpoint handles Pinterest API errors gracefully. **Vertical slice**: API -> pin_scheduler -> Pinterest API. **Focus**: Error handling paths" |
| Component: `SmartSchedule`, Symptom: "Wrong timezone"          | "**Testing**: Unit test for timezone conversion + E2E test verifying UI displays correct times. **Vertical slice**: Database -> SmartSchedule service -> Frontend display"                          |
| Classification: `feature_request`, Component: `bulk_scheduler` | "**Testing**: New feature requires new test suite. **Coverage**: API endpoint tests + UI workflow test. **Note**: Feature flag recommended for staged rollout"                                      |

**Mechanical fallback**: `f"**Target Components**: {component} module\n**Testing**: Integration test covering the full flow\n**Vertical Slice**: Backend -> Frontend"`

---

## Prompt Design

### Additions to STORY_CONTENT_PROMPT

The following sections should be added to `src/prompts/story_content.py`:

```python
### 6. acceptance_criteria (list of Given/When/Then statements)

**Format**: List of 2-4 specific acceptance criteria in Given/When/Then format.

Derive from symptoms:
- "Given" = the precondition or context where the issue occurs
- "When" = the user action that triggers the issue
- "Then" = the expected behavior (opposite of the reported symptom)

**Good examples**:
- "Given a user is uploading a pin to drafts, When the save action is triggered, Then the pin is saved successfully without Server 0 errors"
- "Given a user has configured timezone settings, When viewing scheduled posts, Then times display in the user's configured timezone"
- "Given multiple Pinterest boards are selected, When bulk scheduling 50+ pins, Then all pins are scheduled within 30 seconds"

**Bad examples** (never use):
- "Given the reported conditions when the user performs the action then the expected behavior occurs" (too generic)
- "The bug is fixed" (not Given/When/Then format)
- "Works as expected" (not specific to symptoms)

### 7. investigation_steps (list of specific steps)

**Format**: List of 3-5 specific investigation steps based on component and symptoms.

Map symptom types to investigation approaches:
- API errors -> Check logs, verify requests, test error handling
- Timeout issues -> Check timing, network, async patterns
- UI issues -> Check rendering, state management, data binding
- Data issues -> Check database, caching, race conditions

**Good examples** (for pin upload Server 0 error in pin_scheduler):
- "Review `pin_scheduler` error logs for Server 0 response patterns"
- "Verify Pinterest API authentication state during draft save"
- "Test pin upload with different image formats and sizes"
- "Check retry logic when Pinterest API returns transient errors"

**Bad examples** (never use):
- "Verify API responses and error handling" (too generic)
- "Check for issues" (not actionable)
- "Debug the code" (meaningless)

### 8. success_criteria (list of observable outcomes)

**Format**: List of 3-5 observable, measurable success criteria.

Each criterion should be the positive outcome (negation of a symptom):
- Symptom: "fails with error" -> Success: "completes without errors"
- Symptom: "shows wrong data" -> Success: "displays correct data"
- Symptom: "takes too long" -> Success: "completes within X seconds"

**Good examples**:
- "Pin uploads to drafts complete successfully without Server 0 errors"
- "Scheduled post times display in user's configured timezone"
- "Bulk scheduling of 50 pins completes within 30 seconds"
- "All existing pin_scheduler tests pass (no regressions)"

**Bad examples** (never use):
- "All tests pass" (not specific to this issue)
- "Bug is fixed" (not observable)
- "Works correctly" (not measurable)

### 9. technical_notes (string with testing expectations)

**Format**: Structured string with testing expectations and architectural notes.

Include:
- **Testing**: Specific test type based on symptom (unit/integration/E2E)
- **Vertical Slice**: Components involved in the fix
- **Focus Area**: What specifically needs testing attention

**Good example** (for API error in pin_scheduler):
"**Testing**: API integration test verifying pin save endpoint handles Pinterest API errors gracefully.
**Vertical Slice**: API endpoint -> pin_scheduler service -> Pinterest API client.
**Focus Area**: Error handling and retry logic when Pinterest returns Server 0."

**Bad example** (never use):
"Integration test covering the full flow" (too generic, applies to anything)
```

### Updated JSON Schema

```json
{
  "title": "string (max 80 chars, action verb first, no trailing period)",
  "user_type": "string (specific persona, NOT 'Tailwind user')",
  "user_story_want": "string (starts with 'to', first-person infinitive)",
  "user_story_benefit": "string (specific outcome, NOT 'achieve my goals')",
  "ai_agent_goal": "string (must include 'Success:' criteria)",
  "acceptance_criteria": ["string (Given/When/Then format)", "..."],
  "investigation_steps": ["string (specific to component)", "..."],
  "success_criteria": ["string (observable outcome)", "..."],
  "technical_notes": "string (testing expectations + vertical slice)"
}
```

---

## Implementation Changes

### File: `src/story_tracking/services/story_content_generator.py`

**Add 4 new fields to GeneratedStoryContent**:

```python
@dataclass
class GeneratedStoryContent:
    """LLM-generated story content."""

    # Existing fields (unchanged)
    title: str
    user_type: str
    user_story_want: str
    user_story_benefit: str
    ai_agent_goal: str

    # NEW: Context-specific acceptance criteria
    acceptance_criteria: List[str]
    """
    Specific Given/When/Then acceptance criteria derived from symptoms.

    Each criterion maps a symptom to its expected positive outcome.
    Minimum 2, maximum 5 criteria.
    """

    # NEW: Context-specific investigation steps
    investigation_steps: List[str]
    """
    Investigation steps specific to component and symptom type.

    Maps symptom type (API error, timeout, UI issue, data issue)
    to appropriate investigation approach.
    """

    # NEW: Observable success criteria
    success_criteria: List[str]
    """
    Observable, measurable success criteria.

    Each criterion is the negation of a reported symptom.
    """

    # NEW: Testing expectations and architectural notes
    technical_notes: str
    """
    Context-specific testing expectations based on symptom type.

    Includes test type, vertical slice, and focus areas.
    """
```

**Update mechanical fallback**:

```python
def _mechanical_fallback(self, content_input: StoryContentInput) -> GeneratedStoryContent:
    """Generate mechanical fallback - no LLM involved."""
    # ... existing fallback logic for title, user_type, etc. ...

    component = content_input.component or "Unknown"
    product_area = content_input.product_area or "Unknown"

    return GeneratedStoryContent(
        title=title,
        user_type="Tailwind user",
        user_story_want=want,
        user_story_benefit="achieve my goals without friction",
        ai_agent_goal=ai_goal,
        # NEW fallbacks
        acceptance_criteria=[
            "Given the reported conditions, When the user performs the action, Then the expected behavior occurs"
        ],
        investigation_steps=[
            f"Review `{component}` code for issues matching symptoms",
            f"Check logs for errors in {product_area} flow",
        ],
        success_criteria=[
            "Issue is resolved and functionality works as expected",
            "All existing tests pass (no regressions)",
        ],
        technical_notes=f"**Target Components**: `{component}` module\n**Testing**: Integration test covering the relevant flow\n**Vertical Slice**: Backend -> Frontend",
    )
```

### File: `src/prompts/story_content.py`

**Expand prompt with 4 new output requirements** (see Prompt Design section above).

**Update build_story_content_prompt()**: No changes needed - prompt template already uses `format()` with all fields.

### File: `src/story_formatter.py`

**Modify `_format_acceptance_criteria()`** (lines 977-999):

```python
def _format_acceptance_criteria(
    self,
    theme_data: Dict,
    generated_content: Optional["GeneratedStoryContent"] = None,
) -> str:
    """Format acceptance criteria - prefer generated over defaults."""
    # Use generated criteria if available
    if generated_content and generated_content.acceptance_criteria:
        criteria = generated_content.acceptance_criteria
    else:
        # Fallback to theme_data or defaults (for backward compatibility)
        criteria = theme_data.get("acceptance_criteria", [
            "Given the reported conditions when the user performs the action then the expected behavior occurs",
        ])

    formatted_criteria = [f"- [ ] {c}" for c in criteria]
    return f"""## Acceptance Criteria

{chr(10).join(formatted_criteria)}"""
```

**Modify `_format_suggested_investigation()`** (lines 1040-1056):

```python
def _format_suggested_investigation(
    self,
    theme_data: Dict,
    generated_content: Optional["GeneratedStoryContent"] = None,
) -> str:
    """Format investigation steps - prefer generated over defaults."""
    if generated_content and generated_content.investigation_steps:
        steps = generated_content.investigation_steps
    else:
        component = theme_data.get("component", "the relevant component")
        product_area = theme_data.get("product_area", "this area")
        steps = [
            f"Review `{component}` code for issues matching symptoms",
            f"Check logs for errors in {product_area} flow",
        ]

    formatted_steps = [f"{i}. {step}" for i, step in enumerate(steps, 1)]
    return f"""## Suggested Investigation

{chr(10).join(formatted_steps)}"""
```

**Modify `_format_success_criteria()`** (lines 1078-1093):

```python
def _format_success_criteria(
    self,
    theme_data: Dict,
    generated_content: Optional["GeneratedStoryContent"] = None,
) -> str:
    """Format success criteria - prefer generated over defaults."""
    if generated_content and generated_content.success_criteria:
        criteria = generated_content.success_criteria
    else:
        criteria = [
            "Issue is resolved and functionality works as expected",
            "All existing tests pass (no regressions)",
        ]

    formatted = [f"- [ ] {c}" for c in criteria]
    return f"""## Success Criteria (Explicit & Observable)

{chr(10).join(formatted)}"""
```

**Modify technical notes section** (lines 754-759):

```python
def _format_technical_notes(
    self,
    theme_data: Dict,
    generated_content: Optional["GeneratedStoryContent"] = None,
) -> str:
    """Format technical notes - prefer generated over defaults."""
    if generated_content and generated_content.technical_notes:
        return f"""## Technical Notes

{generated_content.technical_notes}"""
    else:
        component = theme_data.get("component", "Unknown")
        return f"""## Technical Notes

- **Target Components**: `{component}` module
- **Testing Expectations**: Integration test covering the relevant flow
- **Vertical Slice**: {theme_data.get('vertical_slice', 'Backend -> Frontend')}"""
```

**Update method signatures** to pass `generated_content`:

- `format_human_section()` already receives `generated_content`
- `format_ai_section()` already receives `generated_content`
- Internal helpers need to accept and use `generated_content`

---

## Sections to Remove (Process Artifacts Only)

These sections are true process artifacts that don't benefit from LLM enhancement:

### INVEST Check (lines 762-769)

**Reason for removal**: These are sprint planning checkboxes, not story content. Pre-checked boxes provide false confidence. This assessment should happen during sprint planning by humans, not auto-generated.

**Action**: Remove entirely from `format_human_section()`.

### Instructions (lines 1058-1076)

**Reason for removal**: Generic workflow steps that AI agents already know from their own instructions (CLAUDE.md). Adding these wastes tokens and provides no value.

**Action**: Remove `_format_instructions()` call from `format_ai_section()`.

### Guardrails (lines 1095-1124)

**Reason for removal**: Generic best practices that belong in agent instructions (CLAUDE.md), not individual story descriptions. The only semi-specific item (component reference) is not valuable enough to justify the section.

**Action**: Remove `_format_guardrails()` call from `format_ai_section()`.

---

## Implementation Plan

### Phase 1: Prompt Expansion (Kai)

**Files**: `src/prompts/story_content.py`

**Tasks**:

- [ ] Add 4 new field requirements to `STORY_CONTENT_PROMPT`
- [ ] Include examples for each new field
- [ ] Update JSON schema in prompt
- [ ] Add quality checklist items for new fields
- [ ] Test prompt with representative inputs from all classification categories

**Acceptance criteria**:

- [ ] Prompt generates valid JSON with all 9 fields
- [ ] `acceptance_criteria` are in Given/When/Then format, derived from symptoms
- [ ] `investigation_steps` are specific to component and symptom type
- [ ] `success_criteria` are observable negations of symptoms
- [ ] `technical_notes` include test type appropriate to symptom type

### Phase 2: Generator Enhancement (Marcus)

**Files**: `src/story_tracking/services/story_content_generator.py`

**Tasks**:

- [ ] Add 4 new fields to `GeneratedStoryContent` dataclass
- [ ] Update `_parse_response()` to extract new fields with fallbacks
- [ ] Update `_mechanical_fallback()` with default values for new fields
- [ ] Update `_extract_field()` to handle list types
- [ ] Add unit tests for new fields

**Acceptance criteria**:

- [ ] All 9 fields populated from LLM response
- [ ] Partial JSON handled gracefully (valid fields used, others fallback)
- [ ] Mechanical fallback includes reasonable defaults for new fields
- [ ] Type validation for list fields

### Phase 3: Formatter Integration (Marcus)

**Files**: `src/story_formatter.py`

**Tasks**:

- [ ] Update `_format_acceptance_criteria()` to use generated content
- [ ] Update `_format_suggested_investigation()` to use generated content
- [ ] Update `_format_success_criteria()` to use generated content
- [ ] Create `_format_technical_notes()` to use generated content
- [ ] Remove INVEST Check section
- [ ] Remove Instructions section
- [ ] Remove Guardrails section
- [ ] Update `format_human_section()` to pass `generated_content` to helpers
- [ ] Update `format_ai_section()` to pass `generated_content` to helpers

**Acceptance criteria**:

- [ ] All sections use generated content when available
- [ ] Fallback to mechanical defaults when generated content missing
- [ ] Process artifact sections removed
- [ ] No regressions for stories without generated content

### Phase 4: Testing (Kenji)

**Files**: `tests/test_story_formatter.py`, `tests/story_tracking/test_story_content_generator.py`

**Tasks**:

- [ ] Unit tests for new GeneratedStoryContent fields
- [ ] Unit tests for formatter methods with generated content
- [ ] Unit tests for formatter methods with fallback
- [ ] Integration test: full story generation with new fields
- [ ] Functional test: pipeline run with sample conversations

**Acceptance criteria**:

- [ ] All new code paths covered
- [ ] Fallback behavior verified
- [ ] No regressions in existing tests

---

## Token Budget Analysis

### Current prompt size

- Base prompt: ~3,500 chars (~875 tokens)
- Input context: ~500-2,000 chars (~125-500 tokens)
- **Total input**: ~1,000-1,375 tokens

### New prompt size (estimated)

- Base prompt with 4 new fields: ~5,500 chars (~1,375 tokens)
- Input context (unchanged): ~500-2,000 chars
- **Total input**: ~1,500-1,875 tokens

### Output size

- Current (5 fields): ~300-500 chars (~75-125 tokens)
- New (9 fields): ~600-900 chars (~150-225 tokens)

### Cost impact

- **Additional tokens per story**: ~600-700 tokens
- **At gpt-4o-mini pricing**: ~$0.0003 per story
- **For 100 stories/month**: ~$0.03 additional cost

**Conclusion**: Token increase is minimal and justified by significantly improved story quality.

---

## Success Metrics

### Quality metrics (measured by sampling)

| Metric                            | Target | Measurement                                              |
| --------------------------------- | ------ | -------------------------------------------------------- |
| Acceptance criteria specificity   | 80%+   | % of criteria that reference actual symptoms             |
| Investigation steps actionability | 80%+   | % of steps that are component-specific                   |
| Success criteria observability    | 90%+   | % of criteria that describe observable outcomes          |
| Technical notes relevance         | 80%+   | % of notes that match symptom type (API/UI/data)         |
| Fallback rate                     | <10%   | % of stories using mechanical fallback for any new field |

### Process metrics

| Metric                      | Target | Measurement                                    |
| --------------------------- | ------ | ---------------------------------------------- |
| LLM generation success rate | >95%   | % of calls returning valid JSON for all fields |
| Partial fallback rate       | <5%    | % of calls with some fields falling back       |
| Full fallback rate          | <1%    | % of calls requiring full mechanical fallback  |

---

## References

- Issue #133: Story descriptions contain generic unhelpful boilerplate
- `docs/architecture/story-content-generation.md` - Existing LLM content generation architecture
- `src/story_formatter.py:603-1203` - DualStoryFormatter implementation
- `src/prompts/story_content.py` - Current LLM prompt (5 fields)
- `src/story_tracking/services/story_content_generator.py` - Generator service
