"""
Story Content Generator

Generates synthesized story content from grouped conversation data using LLM.
Produces outcome-focused titles, context-specific user stories, and AI agent goals.

Owner: Marcus (Backend)
Prompt: Kai (Prompt Engineering) - src/prompts/story_content.py
Architecture: docs/architecture/story-content-generation.md
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from src.prompts.story_content import (
    StoryContentInput,
    build_story_content_prompt,
)

logger = logging.getLogger(__name__)


# Default timeout for LLM calls (seconds)
DEFAULT_TIMEOUT = 30.0

# Classification category mapping for unknown categories
DEFAULT_CATEGORY = "product_issue"

# Valid classification categories
VALID_CATEGORIES = {
    "product_issue",
    "feature_request",
    "how_to_question",
    "account_issue",
    "billing_question",
}


@dataclass
class GeneratedStoryContent:
    """
    LLM-generated story content.

    All fields are populated either from LLM generation or mechanical fallbacks.
    """

    title: str
    """
    Outcome-focused story title.

    Format: Action verb + specific problem
    Examples:
      - "Fix pin upload failures when saving to drafts"
      - "Add bulk scheduling for Instagram Reels"
      - "Clarify SmartSchedule timezone settings"
    """

    user_type: str
    """
    The persona for "As a [user_type]" in user story.

    Examples:
      - "content creator managing multiple Pinterest accounts"
      - "social media manager scheduling bulk content"
    """

    user_story_want: str
    """
    First-person infinitive clause for "I want..." in user story.

    Format: "to be able to [action] [context] [without error/successfully]"
    """

    user_story_benefit: str
    """
    The benefit clause for "So that [benefit]" in user story.

    Should be specific to the problem, not generic "achieve my goals".
    """

    ai_agent_goal: str
    """
    Actionable goal with success criteria for AI agent.

    Format: "[Action verb] the [specific issue]. Success: [measurable criteria]"
    """


class StoryContentGenerator:
    """
    Generates synthesized story content from grouped conversation data.

    Uses a single LLM call to produce:
    - Outcome-focused title
    - Context-specific user type
    - User story "I want" clause
    - Context-specific benefit
    - AI agent goal with success criteria

    Features:
    - Retry with exponential backoff on transient failures
    - Mechanical fallback per field after retries exhausted
    - Edge case handling for empty inputs and unknown categories
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize story content generator.

        Args:
            model: OpenAI model to use for generation
            temperature: LLM temperature (lower = more deterministic)
            timeout: Timeout for LLM calls in seconds
        """
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            self._client = OpenAI()
        return self._client

    def generate(
        self,
        content_input: StoryContentInput,
        max_retries: int = 3,
    ) -> GeneratedStoryContent:
        """
        Generate story content with retry logic.

        Retries with exponential backoff on transient failures (rate limit, timeout,
        server errors). Falls back to mechanical defaults after retries exhausted.

        Args:
            content_input: StoryContentInput with conversation data
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            GeneratedStoryContent with all 5 fields populated
        """
        # Validate and normalize input
        normalized_input = self._normalize_input(content_input)

        base_delay = 1.0  # seconds

        for attempt in range(max_retries):
            try:
                return self._call_llm(normalized_input)
            except (RateLimitError, APITimeoutError, InternalServerError, APIConnectionError) as e:
                if attempt == max_retries - 1:
                    logger.warning(
                        f"LLM generation failed after {max_retries} attempts: {e}"
                    )
                    return self._mechanical_fallback(normalized_input)
                delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
                logger.info(
                    f"Transient error on attempt {attempt + 1}, "
                    f"retrying in {delay}s: {type(e).__name__}"
                )
                time.sleep(delay)
            except Exception as e:
                # Non-transient errors - don't retry
                logger.warning(f"Non-transient LLM error: {e}. Using mechanical fallback.")
                return self._mechanical_fallback(normalized_input)

        # Should not reach here, but safety fallback
        return self._mechanical_fallback(normalized_input)

    def _normalize_input(self, content_input: StoryContentInput) -> StoryContentInput:
        """
        Normalize and validate input, handling edge cases.

        Edge cases handled:
        - Empty user_intents: use first symptom as pseudo-intent, else use signature
        - Empty symptoms: allowed (generate from user_intents only)
        - Both empty: use signature-based defaults, log warning
        - Unknown classification: map to product_issue, log warning

        Args:
            content_input: Original input

        Returns:
            Normalized StoryContentInput
        """
        user_intents = list(content_input.user_intents) if content_input.user_intents else []
        symptoms = list(content_input.symptoms) if content_input.symptoms else []
        classification = content_input.classification_category

        # Handle unknown classification category
        if classification not in VALID_CATEGORIES:
            logger.warning(
                f"Unknown classification category '{classification}', "
                f"mapping to '{DEFAULT_CATEGORY}'"
            )
            classification = DEFAULT_CATEGORY

        # Handle empty user_intents
        if not user_intents:
            if symptoms:
                # Use first symptom as pseudo-intent
                pseudo_intent = symptoms[0]
                logger.debug(
                    f"Empty user_intents, using symptom as pseudo-intent (hash: {hash(pseudo_intent) & 0xFFFFFFFF:08x})"
                )
                user_intents = [pseudo_intent]
            else:
                # Both empty - use signature-based default
                logger.warning(
                    f"Both user_intents and symptoms are empty for signature "
                    f"'{content_input.issue_signature}'. Using signature-based defaults."
                )
                user_intents = [self._humanize_signature(content_input.issue_signature)]

        return StoryContentInput(
            user_intents=user_intents,
            symptoms=symptoms,
            issue_signature=content_input.issue_signature,
            classification_category=classification,
            product_area=content_input.product_area or "Unknown",
            component=content_input.component or "Unknown",
            root_cause_hypothesis=content_input.root_cause_hypothesis,
            affected_flow=content_input.affected_flow,
            excerpts=content_input.excerpts,
        )

    def _call_llm(self, content_input: StoryContentInput) -> GeneratedStoryContent:
        """
        Make LLM call to generate story content.

        Args:
            content_input: Normalized StoryContentInput

        Returns:
            GeneratedStoryContent from LLM response

        Raises:
            Various OpenAI errors on transient failures
            ValueError on invalid response
        """
        # Build prompt
        prompt = build_story_content_prompt(content_input)

        # Truncate if too long (stay under token limits)
        max_prompt_chars = 12000  # ~4000 tokens with buffer
        if len(prompt) > max_prompt_chars:
            logger.debug(
                f"Truncating prompt from {len(prompt)} to {max_prompt_chars} chars"
            )
            prompt = prompt[:max_prompt_chars]

        # Call OpenAI
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            timeout=self.timeout,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a product manager generating story content. Respond only with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        # Parse response - handle null content (R1 fix)
        response_text = response.choices[0].message.content
        if response_text is None:
            raise ValueError("OpenAI returned empty content")
        response_text = response_text.strip()
        return self._parse_response(response_text, content_input)

    def _parse_response(
        self,
        response_text: str,
        content_input: StoryContentInput,
    ) -> GeneratedStoryContent:
        """
        Parse LLM response into GeneratedStoryContent.

        Handles partial JSON by using valid fields and mechanical fallback for missing.

        Args:
            response_text: Raw JSON response from LLM
            content_input: Original input for fallback values

        Returns:
            GeneratedStoryContent with all fields populated

        Raises:
            ValueError if JSON is completely invalid
        """
        try:
            # Handle potential markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            raise ValueError(f"Invalid JSON response: {e}")

        # Build fallback for missing fields
        fallback = self._mechanical_fallback(content_input)

        # Extract fields with fallback for missing/invalid
        title = self._extract_field(data, "title", fallback.title)
        user_type = self._extract_field(data, "user_type", fallback.user_type)
        user_story_want = self._extract_field(data, "user_story_want", fallback.user_story_want)
        user_story_benefit = self._extract_field(data, "user_story_benefit", fallback.user_story_benefit)
        ai_agent_goal = self._extract_field(data, "ai_agent_goal", fallback.ai_agent_goal)

        # Validate title length (max 80 chars)
        if len(title) > 80:
            title = title[:77] + "..."

        return GeneratedStoryContent(
            title=title,
            user_type=user_type,
            user_story_want=user_story_want,
            user_story_benefit=user_story_benefit,
            ai_agent_goal=ai_agent_goal,
        )

    def _extract_field(
        self,
        data: dict,
        field_name: str,
        fallback_value: str,
    ) -> str:
        """
        Extract a field from parsed JSON with fallback.

        Args:
            data: Parsed JSON dict
            field_name: Field name to extract
            fallback_value: Value to use if field missing or invalid

        Returns:
            Field value or fallback
        """
        value = data.get(field_name)
        if value is None or not isinstance(value, str) or not value.strip():
            return fallback_value
        return value.strip()

    def _mechanical_fallback(
        self,
        content_input: StoryContentInput,
    ) -> GeneratedStoryContent:
        """
        Generate purely mechanical fallback - no LLM involved.

        Fallback logic per field:
        - title: user_intent if > 10 chars, else humanize signature
        - user_type: "Tailwind user"
        - user_story_want: user_intent directly
        - user_story_benefit: "achieve my goals without friction"
        - ai_agent_goal: user_intent + success criteria

        Args:
            content_input: Normalized StoryContentInput

        Returns:
            GeneratedStoryContent with mechanical defaults
        """
        # M5: Log when fallback is used for debugging
        logger.info(
            f"Using mechanical fallback for signature (hash: {hash(content_input.issue_signature) & 0xFFFFFFFF:08x}) "
            f"(category: {content_input.classification_category})"
        )

        # Get first user intent (or None)
        user_intent = (
            content_input.user_intents[0]
            if content_input.user_intents
            else None
        )
        signature = content_input.issue_signature

        # Title: user_intent if > 10 chars, else humanize signature
        if user_intent and len(user_intent) > 10:
            title = user_intent
        else:
            title = self._humanize_signature(signature)

        # Ensure title is under 80 chars
        if len(title) > 80:
            title = title[:77] + "..."

        # user_story_want: use user_intent directly
        want = user_intent if user_intent else "use the product successfully"

        # ai_agent_goal: combine user_intent with success criteria (Q3 fix)
        intent_prefix = user_intent or signature
        ai_goal = f"{intent_prefix}. Success: issue is resolved and functionality works as expected."

        # NOTE: These values intentionally match the "Bad examples" in story_content.py
        # (M6/R6 documentation). This signals that LLM generation failed and content
        # may need human review. Do not "fix" these to be more specific - they serve
        # as fallback markers indicating mechanical generation was used.
        return GeneratedStoryContent(
            title=title,
            user_type="Tailwind user",
            user_story_want=want,
            user_story_benefit="achieve my goals without friction",
            ai_agent_goal=ai_goal,
        )

    def _humanize_signature(self, signature: str) -> str:
        """
        Convert issue_signature to human-readable title.

        Examples:
          - "pin_upload_failure" -> "Pin Upload Failure"
          - "scheduling_error" -> "Scheduling Error"

        Args:
            signature: The issue_signature string

        Returns:
            Human-readable title
        """
        return signature.replace("_", " ").title()
