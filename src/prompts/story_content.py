"""
Story Content Generation Prompt

LLM prompt for generating synthesized story content from grouped conversation data.
Produces outcome-focused titles, context-specific user stories, and AI agent goals.

Owner: Kai (Prompt Engineering)
Used by: StoryContentGenerator (Marcus - Backend)
"""

from dataclasses import dataclass
from typing import List, Optional


# Story Content Generation Prompt Template
# Uses OpenAI JSON mode for structured output
STORY_CONTENT_PROMPT = '''You are a product manager synthesizing support conversations into actionable product stories for Tailwind, a social media scheduling tool.

## Your Task

Generate 9 fields that will be used in product tickets. Each field serves a specific purpose and has strict formatting requirements.

## Input Context

**Classification**: {classification_category}
**Product Area**: {product_area}
**Component**: {component}
**Issue Signature**: {issue_signature}

### What Users Were Trying To Do
{user_intents_formatted}

### What Went Wrong (Symptoms)
{symptoms_formatted}

{optional_context}

## Output Requirements

Generate valid JSON with these 5 fields:

### 1. title (max 80 chars, no trailing period)

**Format**: `[Action Verb] [specific problem/capability]`

**Choose the action verb based on what the symptoms suggest is needed**:
- Fix - when something is broken or erroring
- Add/Enable - when users need functionality that doesn't exist
- Clarify - when documentation is unclear but feature works correctly
- Resolve - when accounts/connections need repair
- Improve - when existing functionality is inadequate
- Support - when a platform/format needs to be handled

**Important**: Let the symptoms guide your verb choice. A "how_to_question" where symptoms reveal missing functionality should use "Add" or "Enable", not "Clarify". A "product_issue" where users are confused (not blocked) might need "Clarify".

**Examples**:
- "Fix pin upload failures when saving to drafts" (errors occurring)
- "Add bulk scheduling for Instagram Reels" (feature doesn't exist)
- "Clarify SmartSchedule timezone settings in help docs" (feature works, docs unclear)
- "Resolve Pinterest OAuth connection timeouts" (connection broken)
- "Enable bulk deletion for scheduled pins" (users asking how to do something impossible)

**Bad examples** (avoid these patterns):
- "User cannot upload pins" (passive, not outcome-focused)
- "Pins not working" (too vague)
- "Fix the issue with scheduling" (not specific)

### 2. user_type (specific persona)

**Format**: A specific persona description based on product area and context.

**Good examples**:
- "content creator managing multiple Pinterest accounts"
- "social media manager scheduling bulk content for clients"
- "e-commerce owner using Tailwind for product promotion"
- "marketing team member tracking Pinterest analytics"
- "new Tailwind user learning the scheduling workflow"

**Bad examples** (never use):
- "Tailwind user" (too generic)
- "user" (meaningless)
- "customer" (not persona-based)

### 3. user_story_want (first-person infinitive)

**Format**: Starts with "to be able to" or "to" + verb phrase

This completes the sentence: "As a [user_type], I want [user_story_want]"

**Good examples**:
- "to be able to upload pins to my drafts without errors"
- "to schedule posts for multiple accounts in one action"
- "to understand how timezone settings affect my posting schedule"
- "to reconnect my Pinterest account without losing scheduled pins"

**Bad examples**:
- "upload pins" (incomplete - missing "to be able to")
- "the pins to work" (not first-person)
- "fix the scheduling" (imperative, not infinitive)

### 4. user_story_benefit (specific outcome)

**Format**: Explains WHY the user wants this, specific to the problem.

This completes: "So that [user_story_benefit]"

**Good examples**:
- "I can maintain my posting schedule without interruption"
- "I save time on repetitive scheduling tasks"
- "I can optimize my posting times for engagement"
- "I don't miss my product launch deadlines"

**Bad examples** (never use):
- "I can achieve my goals" (too generic)
- "achieve my goals without friction" (boilerplate)
- "things work properly" (vague)

### 5. ai_agent_goal (action + success criteria)

**Format**: `[Action verb] the [specific issue]. Success: [measurable criteria]`

Must include:
- Specific action to take
- Explicit "Success:" criteria (observable, measurable)

**Good examples**:
- "Resolve the pin upload failure where users receive Server 0 response code. Success: uploads complete successfully and pins appear in drafts within 5 seconds."
- "Implement bulk scheduling for Instagram Reels. Success: user can select multiple reels and schedule with one action."
- "Update documentation for SmartSchedule timezone behavior. Success: help docs clearly explain how user timezone affects scheduled post times."

**Bad examples**:
- "Fix the bug" (not specific)
- "Make it work" (no success criteria)
- "Resolve the issue and restore expected functionality" (generic)

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
"**Testing**: API integration test verifying pin save endpoint handles Pinterest API errors gracefully. **Vertical Slice**: API endpoint -> pin_scheduler service -> Pinterest API client. **Focus Area**: Error handling and retry logic when Pinterest returns Server 0."

**Bad example** (never use):
"Integration test covering the full flow" (too generic, applies to anything)

## CRITICAL: Field Coherence

The acceptance_criteria MUST verify that the ai_agent_goal was achieved. These fields must be logically connected:

**Pattern**: If ai_agent_goal says "Do X", acceptance_criteria must verify "X was done correctly"

**Good coherence**:
- Goal: "Update help docs for timezone settings. Success: docs explain timezone behavior."
- AC: "Given a user reads the help docs, When they look for timezone info, Then the explanation is clear and accurate"
(AC verifies the goal - docs were updated and are clear)

**Bad coherence** (NEVER do this):
- Goal: "Update the documentation for board selection"
- AC: "Given a user is on the scheduling page, When they look for guidance, Then instructions are displayed"
(AC tests UI display, but goal only promises documentation update - these don't match!)

**Rule**: An AI agent that achieves the goal MUST also pass all acceptance criteria. If an agent could complete the goal but fail an AC, the fields are incoherent.

## Response Format

Respond with valid JSON only. No markdown code blocks, no explanations outside JSON.

{{
  "title": "string (max 80 chars, action verb first, no trailing period)",
  "user_type": "string (specific persona, NOT 'Tailwind user')",
  "user_story_want": "string (starts with 'to', first-person infinitive)",
  "user_story_benefit": "string (specific outcome, NOT 'achieve my goals')",
  "ai_agent_goal": "string (must include 'Success:' criteria)",
  "acceptance_criteria": ["string (Given/When/Then format)", "...2-4 items"],
  "investigation_steps": ["string (specific to component)", "...3-5 items"],
  "success_criteria": ["string (observable outcome)", "...3-5 items"],
  "technical_notes": "string (testing expectations + vertical slice)"
}}

## Quality Checklist (verify before responding)

- [ ] Title starts with action verb that matches what symptoms suggest is needed
- [ ] Title is under 80 characters
- [ ] user_type is NOT "Tailwind user" or "user"
- [ ] user_story_want starts with "to"
- [ ] user_story_benefit is specific to this problem
- [ ] ai_agent_goal contains "Success:" followed by measurable criteria
- [ ] acceptance_criteria uses Given/When/Then format derived from symptoms
- [ ] **COHERENCE CHECK**: An agent achieving ai_agent_goal would ALSO pass all acceptance_criteria
- [ ] investigation_steps are specific to component (NOT generic "verify API")
- [ ] success_criteria are observable negations of symptoms
- [ ] technical_notes include test type appropriate to symptom type
'''


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

    # Issue #146: Resolution context from LLM extraction
    root_cause: Optional[str] = None  # LLM hypothesis for WHY this happened
    solution_provided: Optional[str] = None  # Solution given by support (if resolved)

    # Issue #159: Resolution action/category for fix guidance in stories
    resolution_action: Optional[str] = None  # escalated_to_engineering | provided_workaround | user_education | manual_intervention | no_resolution
    resolution_category: Optional[str] = None  # escalation | workaround | education | self_service_gap | unresolved


def format_user_intents(user_intents: List[str]) -> str:
    """
    Format user intents for the prompt.

    Args:
        user_intents: List of user intent strings

    Returns:
        Formatted string for inclusion in prompt
    """
    if not user_intents:
        return "- (No user intent data available)"

    # Deduplicate and limit
    unique_intents = list(dict.fromkeys(user_intents))[:5]
    return "\n".join(f"- {intent}" for intent in unique_intents)


def format_symptoms(symptoms: List[str]) -> str:
    """
    Format symptoms for the prompt.

    Args:
        symptoms: List of symptom strings

    Returns:
        Formatted string for inclusion in prompt
    """
    if not symptoms:
        return "- (No symptom data available)"

    # Deduplicate and limit
    unique_symptoms = list(dict.fromkeys(symptoms))[:5]
    return "\n".join(f"- {symptom}" for symptom in unique_symptoms)


def format_optional_context(
    root_cause_hypothesis: Optional[str] = None,
    affected_flow: Optional[str] = None,
    excerpts: Optional[List[str]] = None,
    root_cause: Optional[str] = None,
    solution_provided: Optional[str] = None,
    resolution_action: Optional[str] = None,
    resolution_category: Optional[str] = None,
) -> str:
    """
    Format optional context sections for the prompt.

    Args:
        root_cause_hypothesis: Technical hypothesis about root cause
        affected_flow: The user journey/flow affected
        excerpts: Conversation excerpts for additional context
        root_cause: LLM-extracted root cause hypothesis (Issue #146)
        solution_provided: LLM-extracted solution from support (Issue #146)
        resolution_action: Support action taken (Issue #159)
        resolution_category: Resolution category for analytics (Issue #159)

    Returns:
        Formatted optional context string
    """
    sections = []

    if root_cause_hypothesis:
        sections.append(f"### Root Cause Hypothesis\n{root_cause_hypothesis}")

    if affected_flow:
        sections.append(f"### Affected User Flow\n{affected_flow}")

    # Issue #146 + #159: Add resolution context when available
    if root_cause or solution_provided or resolution_action or resolution_category:
        resolution_parts = []
        if root_cause:
            resolution_parts.append(f"**Root Cause Analysis**: {root_cause}")
        if solution_provided:
            resolution_parts.append(f"**Current Workaround**: {solution_provided}")
        # Issue #159: Include resolution action and category for fix guidance
        if resolution_action:
            resolution_parts.append(f"**Support Action Taken**: {resolution_action}")
        if resolution_category:
            resolution_parts.append(f"**Resolution Category**: {resolution_category}")
        sections.append("### Resolution Context\n" + "\n".join(resolution_parts))

    if excerpts:
        # Truncate and limit excerpts
        formatted_excerpts = []
        for excerpt in excerpts[:3]:
            truncated = excerpt[:200] + "..." if len(excerpt) > 200 else excerpt
            formatted_excerpts.append(f'> "{truncated}"')
        sections.append("### Sample Customer Messages\n" + "\n".join(formatted_excerpts))

    return "\n\n".join(sections)


def build_story_content_prompt(content_input: StoryContentInput) -> str:
    """
    Build the complete story content generation prompt.

    Args:
        content_input: StoryContentInput with all required fields

    Returns:
        Complete formatted prompt string ready for OpenAI API
    """
    # Format the user intents
    user_intents_formatted = format_user_intents(content_input.user_intents)

    # Format symptoms
    symptoms_formatted = format_symptoms(content_input.symptoms)

    # Format optional context (including Issue #146 + #159 resolution fields)
    optional_context = format_optional_context(
        root_cause_hypothesis=content_input.root_cause_hypothesis,
        affected_flow=content_input.affected_flow,
        excerpts=content_input.excerpts,
        root_cause=content_input.root_cause,
        solution_provided=content_input.solution_provided,
        resolution_action=content_input.resolution_action,
        resolution_category=content_input.resolution_category,
    )

    return STORY_CONTENT_PROMPT.format(
        classification_category=content_input.classification_category,
        product_area=content_input.product_area,
        component=content_input.component,
        issue_signature=content_input.issue_signature,
        user_intents_formatted=user_intents_formatted,
        symptoms_formatted=symptoms_formatted,
        optional_context=optional_context,
    )
