# Story Content Generation Architecture

> Architecture designed by Priya, updated with requirements from tech lead review and Quality/Pragmatist architecture review.

## Overview

This document defines the architecture for LLM-generated story content, replacing the current direct use of `user_intent` with synthesized, purpose-appropriate outputs.

**Problem**: The raw `user_intent` field from theme extraction describes what the user was doing ("The user was trying to upload pins to their drafts.") but is being used directly in places where it doesn't fit:

1. **Story Title** - Should be outcome-focused: "Fix pin upload failures when saving to drafts"
2. **User Story "I want" clause** - Should be first-person infinitive: "to be able to upload pins to my drafts without errors"
3. **User Story "As a" clause** - Currently hardcoded to "Tailwind user", should be context-specific
4. **User Story "So that" clause** - Currently hardcoded to "achieve my goals without friction", should be context-specific
5. **AI Agent Goal** - Should be actionable with success criteria: "Resolve the pin upload failure where users receive Server 0 response code. Success: uploads complete, pins appear in drafts."

## Components

### 1. StoryContentGenerator (New Module)

**Location**: `src/story_tracking/services/story_content_generator.py`

**Purpose**: Single LLM call that generates all synthesized outputs from grouped conversation data.

### 2. Integration Point

**Location**: `src/story_tracking/services/story_creation_service.py`

**Hook**: `_generate_title()` method (line 1907) is the primary hook point. The generator will be called once before title/description generation, with results used by both.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Story Creation Flow (Proposed)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  conversations ──► _build_theme_data() ──► StoryContentGenerator.generate()│
│                                                    │                        │
│                    ┌───────────────────────────────┼───────────────────────┐│
│                    │            │           │      │       │               ││
│                    ▼            ▼           ▼      ▼       ▼               ││
│               [title]    [user_type]  [want]  [benefit]  [goal]            ││
│                    │            │           │      │       │               ││
│                    └───────────────────────────────┼───────────────────────┘│
│                                                    │                        │
│                                        GeneratedStoryContent                │
│                                                    │                        │
│                              ┌─────────────────────┼─────────────────────┐  │
│                              ▼                     ▼                     ▼  │
│                   _generate_title()    DualStoryFormatter     DualStoryFormatter│
│                   (uses .title)        ._format_user_story()  .format_ai_section()│
│                                        (uses all 4 fields)    (uses .goal)  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Interface Contracts

### Input Model

```python
@dataclass
class StoryContentInput:
    """Input data for story content generation."""

    # From grouped conversations
    user_intents: List[str]  # All user_intent values from conversations
    symptoms: List[str]      # All symptoms (deduplicated)
    issue_signature: str     # The theme signature

    # Context
    classification_category: str  # product_issue, feature_request, how_to_question, account_issue, billing_question
    product_area: str
    component: str

    # Optional: Additional context
    root_cause_hypothesis: Optional[str] = None
    affected_flow: Optional[str] = None
    excerpts: Optional[List[str]] = None  # Conversation excerpts for additional context
```

### Output Model

```python
@dataclass
class GeneratedStoryContent:
    """LLM-generated story content."""

    title: str
    """
    Outcome-focused story title.

    Format: Action verb + specific problem
    Examples:
      - "Fix pin upload failures when saving to drafts"
      - "Add bulk scheduling for Instagram Reels"
      - "Clarify SmartSchedule timezone settings"

    Derived from classification_category:
      - product_issue: "Fix [symptom]"
      - feature_request: "Add [capability]"
      - how_to_question: "Clarify [topic] documentation"
      - account_issue: "Resolve [account problem]"
      - billing_question: "Clarify [billing topic]"
    """

    user_type: str
    """
    The persona for "As a [user_type]" in user story.

    Examples:
      - "content creator managing multiple Pinterest accounts"
      - "social media manager scheduling bulk content"
      - "new Tailwind user learning pin scheduling"

    Should be specific to the context, not generic "Tailwind user".
    """

    user_story_want: str
    """
    First-person infinitive clause for "I want..." in user story.

    Format: "to be able to [action] [context] [without error/successfully]"
    Examples:
      - "to be able to upload pins to my drafts without errors"
      - "to schedule posts for multiple accounts in one action"
      - "to understand how timezone settings affect my schedule"

    Must be grammatically correct when inserted into:
    "As a [user_type], I want [user_story_want], So that [benefit]"
    """

    user_story_benefit: str
    """
    The benefit clause for "So that [benefit]" in user story.

    Examples:
      - "I can maintain my posting schedule without interruption"
      - "I save time on repetitive scheduling tasks"
      - "I can optimize my posting times for engagement"

    Should be specific to the problem, not generic "achieve my goals".
    """

    ai_agent_goal: str
    """
    Actionable goal with success criteria for AI agent.

    Format: "[Action verb] the [specific issue]. Success: [measurable criteria]"
    Examples:
      - "Resolve the pin upload failure where users receive Server 0 response code.
         Success: uploads complete, pins appear in drafts within 5 seconds."
      - "Implement bulk scheduling for Instagram Reels.
         Success: user can select multiple reels and schedule with one action."

    Must include:
      - Specific action to take
      - Explicit success criteria (observable, measurable)
      - Boundaries (what's in/out of scope)
    """

    acceptance_criteria: List[str]
    """
    Specific Given/When/Then acceptance criteria derived from symptoms.

    Each criterion maps a symptom to its expected positive outcome.
    Minimum 2, maximum 5 criteria.

    Examples:
      - "Given a user with draft pins, When they upload a new pin, Then the pin appears in drafts within 5 seconds"
      - "Given a scheduled post, When the scheduled time arrives, Then the post is published automatically"
    """

    investigation_steps: List[str]
    """
    Investigation steps specific to component and symptom type.

    Maps symptom type (API error, timeout, UI issue, data issue)
    to appropriate investigation approach.

    Examples:
      - "Check `PinUploadService` for error handling around Server 0 response"
      - "Review rate limiting logic in API gateway"
      - "Verify database connection pool settings"
    """

    success_criteria: List[str]
    """
    Observable, measurable success criteria.

    Each criterion is the negation of a reported symptom.

    Examples:
      - "Pin uploads complete without Server 0 errors"
      - "Upload time remains under 5 seconds for standard images"
      - "All existing tests pass (no regressions)"
    """

    technical_notes: str
    """
    Context-specific testing expectations based on symptom type.

    Includes test type, vertical slice, and focus areas.

    Example:
      "**Target Components**: `PinUploadService`, `DraftManager`
       **Testing**: Integration test for upload flow + unit tests for error handling
       **Vertical Slice**: API -> Service -> Database"
    """

```

### Generator Interface

```python
class StoryContentGenerator:
    """
    Generates synthesized story content from grouped conversation data.

    Uses a single LLM call to produce 9 fields:
    - Outcome-focused title
    - Context-specific user type
    - User story "I want" clause
    - Context-specific benefit
    - AI agent goal with success criteria
    - Acceptance criteria (Given/When/Then)
    - Investigation steps (component-specific)
    - Success criteria (observable outcomes)
    - Technical notes (testing approach)
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        prompt_template: str = None,  # Designed by Kai
    ):
        ...

    def generate(
        self,
        content_input: StoryContentInput,
        max_retries: int = 3,
    ) -> GeneratedStoryContent:
        """
        Generate story content with retry logic.

        Retries with exponential backoff on transient failures.
        Falls back to mechanical defaults after retries exhausted.
        """
        ...
```

## LLM Prompt Structure

**Owner: Kai (Prompt Engineering)**

The prompt should be designed by Kai following these requirements:

### Required Outputs (JSON Schema)

```json
{
  "title": "string (max 80 chars, action verb first)",
  "user_type": "string (specific persona, not generic)",
  "user_story_want": "string (starts with 'to', first-person)",
  "user_story_benefit": "string (specific outcome)",
  "ai_agent_goal": "string (includes Success: criteria)",
  "acceptance_criteria": ["string (Given/When/Then format)", "..."],
  "investigation_steps": ["string (component-specific steps)", "..."],
  "success_criteria": ["string (observable outcomes)", "..."],
  "technical_notes": "string (target components, testing approach, vertical slice)"
}
```

### Prompt Design Requirements

1. **Title**:
   - Outcome-focused, not action-focused
   - Uses classification to pick appropriate verb (Fix, Add, Clarify, etc.)
   - Max 80 characters, no trailing period

2. **User Type**:
   - Context-specific persona based on product area and symptoms
   - More specific than "Tailwind user"
   - Examples: "content creator", "social media manager", "business owner"

3. **User Story Want**:
   - First-person infinitive ("to be able to...")
   - References specific action from user_intents
   - Includes success qualifier

4. **User Story Benefit**:
   - Specific to the problem being solved
   - Explains the "why" behind the request
   - Not generic "achieve goals without friction"

5. **AI Agent Goal**:
   - Action verb first
   - References specific symptoms/errors
   - Includes explicit "Success:" criteria
   - Optionally includes scope boundaries

6. **Acceptance Criteria**:
   - Given/When/Then format
   - Maps each symptom to expected positive outcome
   - Minimum 2, maximum 5 criteria
   - Specific and testable

7. **Investigation Steps**:
   - Component-specific (references actual module names)
   - Matches symptom type to appropriate investigation
   - Actionable steps for developer

8. **Success Criteria**:
   - Observable and measurable
   - Negation of reported symptoms
   - Includes regression check

9. **Technical Notes**:
   - Target components identified
   - Testing approach specified
   - Vertical slice defined

## File Boundaries

### Files to Create

| File                                                     | Owner  | Purpose                                     |
| -------------------------------------------------------- | ------ | ------------------------------------------- |
| `src/story_tracking/services/story_content_generator.py` | Marcus | New module with StoryContentGenerator class |
| `src/prompts/story_content.py`                           | Kai    | Prompt template for content generation      |
| `tests/story_tracking/test_story_content_generator.py`   | Marcus | Unit tests                                  |

### Files to Modify

| File                                                    | Owner  | Changes                                                                   |
| ------------------------------------------------------- | ------ | ------------------------------------------------------------------------- |
| `src/story_tracking/services/story_creation_service.py` | Marcus | Call generator, pass results to description                               |
| `src/story_formatter.py`                                | Marcus | Use generated content in `_format_user_story()` and `format_ai_section()` |

## Retry and Fallback Strategy

### Retry Logic

LLM calls use exponential backoff before falling back to mechanical defaults:

```python
def generate(self, content_input: StoryContentInput, max_retries: int = 3) -> GeneratedStoryContent:
    """Generate with retry logic."""
    base_delay = 1.0  # seconds

    for attempt in range(max_retries):
        try:
            return self._call_llm(content_input)
        except (RateLimitError, TimeoutError, TransientError) as e:
            if attempt == max_retries - 1:
                logger.warning(f"LLM generation failed after {max_retries} attempts: {e}")
                return self._mechanical_fallback(content_input)
            delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
            time.sleep(delay)

    return self._mechanical_fallback(content_input)
```

### Mechanical Fallbacks (Per Field)

After retries exhausted, each field falls back to mechanical defaults (no LLM required):

| Field                 | Fallback Logic                                                                                                                                             |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `title`               | Use `user_intent` if > 10 chars, else humanize signature ("pin_upload" → "Pin Upload")                                                                     |
| `user_type`           | Hardcode: `"Tailwind user"`                                                                                                                                |
| `user_story_want`     | Use `user_intent` directly (grammatically awkward but matches current behavior)                                                                            |
| `user_story_benefit`  | Hardcode: `"achieve my goals without friction"`                                                                                                            |
| `ai_agent_goal`       | `user_intent` + `. Success: issue is resolved and functionality works as expected.`                                                                        |
| `acceptance_criteria` | Generic: `["Given the reported conditions, When the user performs the action, Then the expected behavior occurs"]`                                         |
| `investigation_steps` | Component-based: `["Review {component} code for issues matching symptoms", "Check logs for errors in {product_area} flow"]`                                |
| `success_criteria`    | Generic: `["Issue is resolved and functionality works as expected", "All existing tests pass (no regressions)"]`                                           |
| `technical_notes`     | Template: `"**Target Components**: {component} module\n**Testing**: Integration test covering the relevant flow\n**Vertical Slice**: Backend -> Frontend"` |

```python
def _mechanical_fallback(self, content_input: StoryContentInput) -> GeneratedStoryContent:
    """Purely mechanical fallback - no LLM involved."""
    user_intent = content_input.user_intents[0] if content_input.user_intents else None
    signature = content_input.issue_signature
    component = content_input.component or "Unknown"
    product_area = content_input.product_area or "Unknown"

    return GeneratedStoryContent(
        title=user_intent if user_intent and len(user_intent) > 10
              else signature.replace("_", " ").title(),
        user_type="Tailwind user",
        user_story_want=user_intent or "use the product successfully",
        user_story_benefit="achieve my goals without friction",
        ai_agent_goal=f"{user_intent or signature}. Success: issue is resolved and functionality works as expected.",
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
        technical_notes=(
            f"**Target Components**: `{component}` module\n"
            f"**Testing**: Integration test covering the relevant flow\n"
            f"**Vertical Slice**: Backend -> Frontend"
        ),
    )
```

## Edge Case Handling

| Scenario                       | Behavior                                                  |
| ------------------------------ | --------------------------------------------------------- |
| Empty `user_intents`           | Use first symptom as pseudo-intent, else use signature    |
| Empty `symptoms`               | Generate from user_intents only (symptoms not required)   |
| Both empty                     | Use signature-based defaults, log warning                 |
| Unknown classification         | Map to `product_issue` (most common), log warning         |
| Very long inputs (>4000 chars) | Truncate before LLM call to stay under token limits       |
| Invalid JSON from LLM          | Retry (counted in retry budget), then mechanical fallback |
| Partial JSON from LLM          | Use valid fields, mechanical fallback for missing fields  |

## Testing Strategy

### Unit Tests (Marcus)

- Basic generation with valid input (all 9 fields)
- All classification categories produce appropriate output
- Title format validation (verb first, < 80 chars)
- User story grammar validation
- AI goal includes success criteria
- Acceptance criteria are list of strings
- Investigation steps are component-based
- Success criteria are measurable
- Technical notes include testing approach
- List field extraction: handles valid lists, empty lists, invalid types
- Retry logic: transient failures trigger retries with backoff
- Retry exhaustion: falls back to mechanical defaults after 3 attempts
- Mechanical fallback: each of 9 fields uses correct default
- Edge cases: empty inputs, unknown categories, long inputs

### Prompt Tests (Kai)

- Prompt produces valid JSON for all categories
- Output quality meets requirements
- Edge cases (empty symptoms, no user_intent, etc.)

### Integration Tests

- Full flow from conversations to story
- Orphan graduation uses same logic
- Retry behavior under realistic failure scenarios

## Agent Assignments

### Kai (Prompt Engineering)

**Creates**:

- `src/prompts/story_content.py` - Prompt template

**Acceptance Criteria**:

- [x] Prompt produces valid JSON for all 9 fields
- [x] Titles use category-appropriate action verbs
- [x] User types are context-specific, not generic
- [x] User story clauses are grammatically correct
- [x] Benefits are specific to the problem
- [x] AI goals include success criteria
- [x] Acceptance criteria use Given/When/Then format
- [x] Investigation steps are component-specific
- [x] Success criteria are observable and measurable
- [x] Technical notes include testing approach

### Marcus (Backend)

**Creates**:

- `src/story_tracking/services/story_content_generator.py`
- `tests/story_tracking/test_story_content_generator.py`

**Modifies**:

- `src/story_tracking/services/story_creation_service.py`
- `src/story_formatter.py`

**Acceptance Criteria**:

- [x] Generator integrates Kai's prompt
- [x] Results used for title, user story, AI goal, and 4 new fields
- [x] Retry logic with exponential backoff (3 attempts)
- [x] Mechanical fallback per field after retries exhausted
- [x] Edge case handling (empty inputs, unknown categories)
- [x] Unit tests cover all methods including retry/fallback
- [x] Orphan graduation uses same logic
- [x] List field extraction with validation
- [x] Formatter uses all 9 generated fields

## Implementation Plan

1. **Phase 1: Prompt Design** (Kai)
   - Design and test the LLM prompt
   - Create `src/prompts/story_content.py`
   - Verify outputs for all classification categories

2. **Phase 2: Core Module** (Marcus)
   - Create `story_content_generator.py`
   - Integrate Kai's prompt
   - Add unit tests

3. **Phase 3: Integration** (Marcus)
   - Modify `story_creation_service.py` to call generator
   - Update `story_formatter.py` to use all generated fields
   - Add retry logic and mechanical fallbacks

4. **Phase 4: Testing** (Marcus + Kenji)
   - Integration tests
   - Functional test with real pipeline run

## Orphan Graduation

Same content generation logic applies when orphans graduate to stories. The generator is called with orphan data, and the resulting content is used to create the story.

## Migration Considerations

Not in scope for this feature. Architecture supports future migration by:

- No schema changes required
- Backward compatible fallback
- Existing stories continue to work
