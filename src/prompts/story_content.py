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

Generate 5 fields that will be used in product tickets. Each field serves a specific purpose and has strict formatting requirements.

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

**Action verb based on category**:
- product_issue: "Fix [symptom/error]"
- feature_request: "Add [capability]"
- how_to_question: "Clarify [topic] documentation"
- account_issue: "Resolve [account problem]"
- billing_question: "Clarify [billing topic]"

**Examples**:
- "Fix pin upload failures when saving to drafts"
- "Add bulk scheduling for Instagram Reels"
- "Clarify SmartSchedule timezone settings in help docs"
- "Resolve Pinterest OAuth connection timeouts"

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

## Response Format

Respond with valid JSON only. No markdown code blocks, no explanations outside JSON.

{{
  "title": "string (max 80 chars, action verb first, no trailing period)",
  "user_type": "string (specific persona, NOT 'Tailwind user')",
  "user_story_want": "string (starts with 'to', first-person infinitive)",
  "user_story_benefit": "string (specific outcome, NOT 'achieve my goals')",
  "ai_agent_goal": "string (must include 'Success:' criteria)"
}}

## Quality Checklist (verify before responding)

- [ ] Title starts with appropriate action verb for category
- [ ] Title is under 80 characters
- [ ] user_type is NOT "Tailwind user" or "user"
- [ ] user_story_want starts with "to"
- [ ] user_story_benefit is specific to this problem
- [ ] ai_agent_goal contains "Success:" followed by measurable criteria
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
) -> str:
    """
    Format optional context sections for the prompt.

    Args:
        root_cause_hypothesis: Technical hypothesis about root cause
        affected_flow: The user journey/flow affected
        excerpts: Conversation excerpts for additional context

    Returns:
        Formatted optional context string
    """
    sections = []

    if root_cause_hypothesis:
        sections.append(f"### Root Cause Hypothesis\n{root_cause_hypothesis}")

    if affected_flow:
        sections.append(f"### Affected User Flow\n{affected_flow}")

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

    # Format optional context
    optional_context = format_optional_context(
        root_cause_hypothesis=content_input.root_cause_hypothesis,
        affected_flow=content_input.affected_flow,
        excerpts=content_input.excerpts,
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
