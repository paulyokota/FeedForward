"""
PM Review Service

Evaluates theme groups before story creation to ensure coherence.
Uses LLM to answer: "Would these conversations all be fixed by one implementation?"

Reference: docs/theme-quality-architecture.md (Improvement 2)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import OpenAI

from src.prompts.pm_review import CONVERSATION_TEMPLATE, PM_REVIEW_PROMPT

logger = logging.getLogger(__name__)


class ReviewDecision(str, Enum):
    """PM review decision types."""

    KEEP_TOGETHER = "keep_together"
    SPLIT = "split"
    REJECT = "reject"  # All conversations are too different


@dataclass
class ConversationContext:
    """Context for a conversation in PM review."""

    conversation_id: str
    user_intent: str
    symptoms: List[str]
    affected_flow: str
    excerpt: str
    product_area: str
    component: str


@dataclass
class SubGroupSuggestion:
    """A suggested sub-group when splitting."""

    suggested_signature: str
    conversation_ids: List[str]
    rationale: str
    confidence: float = 0.0


@dataclass
class PMReviewResult:
    """Result of PM review for a theme group."""

    # Input identification
    original_signature: str
    conversation_count: int

    # Decision
    decision: ReviewDecision
    reasoning: str

    # If split, the suggested sub-groups
    sub_groups: List[SubGroupSuggestion] = field(default_factory=list)

    # Conversations that don't fit any sub-group (become orphans)
    orphan_conversation_ids: List[str] = field(default_factory=list)

    # Review metadata
    model_used: str = ""
    review_duration_ms: int = 0

    @property
    def passed(self) -> bool:
        """Whether the group passed review (keep_together)."""
        return self.decision == ReviewDecision.KEEP_TOGETHER


# Default timeout for LLM calls (seconds)
DEFAULT_TIMEOUT = 30.0


class PMReviewService:
    """
    Evaluates theme groups for coherence before story creation.

    Uses LLM to determine if conversations in a group would all be
    addressed by the same implementation.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize PM review service.

        Args:
            model: OpenAI model to use for review
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

    def review_group(
        self,
        signature: str,
        conversations: List[ConversationContext],
        product_context: Optional[str] = None,
    ) -> PMReviewResult:
        """
        Review a theme group for coherence.

        Args:
            signature: The issue_signature for this group
            conversations: List of conversation contexts to review
            product_context: Optional product documentation for context

        Returns:
            PMReviewResult with decision and any suggested splits
        """
        start_time = time.time()

        # Edge case: Single-conversation groups skip PM review
        if len(conversations) <= 1:
            logger.debug(
                f"Skipping PM review for '{signature}': only {len(conversations)} conversation(s)"
            )
            return PMReviewResult(
                original_signature=signature,
                conversation_count=len(conversations),
                decision=ReviewDecision.KEEP_TOGETHER,
                reasoning="Single-conversation group - PM review skipped",
                model_used="",
                review_duration_ms=0,
            )

        # Build conversation text for prompt
        conversations_text = self._format_conversations(conversations)

        # Build prompt
        prompt = PM_REVIEW_PROMPT.format(
            product_context=product_context or "Tailwind is a social media scheduling tool.",
            signature=signature,
            count=len(conversations),
            conversations=conversations_text,
        )

        try:
            # Call LLM
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                timeout=self.timeout,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a PM reviewing product tickets. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            # Parse response
            response_text = response.choices[0].message.content.strip()
            result = self._parse_response(
                response_text,
                signature,
                conversations,
            )

            # Add metadata
            duration_ms = int((time.time() - start_time) * 1000)
            result.model_used = self.model
            result.review_duration_ms = duration_ms

            logger.info(
                f"PM review for '{signature}': {result.decision.value} "
                f"({len(conversations)} conversations, {duration_ms}ms)"
            )

            return result

        except Exception as e:
            # Edge case: Invalid LLM response -> default to keep_together
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                f"PM review failed for '{signature}': {e}. Defaulting to keep_together."
            )
            return PMReviewResult(
                original_signature=signature,
                conversation_count=len(conversations),
                decision=ReviewDecision.KEEP_TOGETHER,
                reasoning=f"PM review error (defaulting to keep_together): {str(e)}",
                model_used=self.model,
                review_duration_ms=duration_ms,
            )

    def review_groups_batch(
        self,
        groups: Dict[str, List[ConversationContext]],
        product_context: Optional[str] = None,
    ) -> Dict[str, PMReviewResult]:
        """
        Review multiple theme groups.

        Processes groups sequentially. For high-volume scenarios,
        consider using async processing.

        Args:
            groups: Dict mapping signature -> list of ConversationContext
            product_context: Optional product documentation for context

        Returns:
            Dict mapping signature -> PMReviewResult
        """
        results: Dict[str, PMReviewResult] = {}

        for signature, conversations in groups.items():
            try:
                result = self.review_group(signature, conversations, product_context)
                results[signature] = result
            except Exception as e:
                # Log error but continue with other groups
                logger.error(f"Batch PM review error for '{signature}': {e}")
                results[signature] = PMReviewResult(
                    original_signature=signature,
                    conversation_count=len(conversations),
                    decision=ReviewDecision.KEEP_TOGETHER,
                    reasoning=f"Batch review error: {str(e)}",
                    model_used=self.model,
                    review_duration_ms=0,
                )

        logger.info(
            f"Batch PM review complete: {len(results)} groups, "
            f"{sum(1 for r in results.values() if r.passed)} kept, "
            f"{sum(1 for r in results.values() if not r.passed)} split"
        )

        return results

    def _format_conversations(self, conversations: List[ConversationContext]) -> str:
        """Format conversations for the prompt."""
        parts = []
        for i, conv in enumerate(conversations, start=1):
            symptoms_text = ", ".join(conv.symptoms) if conv.symptoms else "None"
            part = CONVERSATION_TEMPLATE.format(
                index=i,
                conversation_id=conv.conversation_id,
                user_intent=conv.user_intent or "Unknown",
                symptoms=symptoms_text,
                affected_flow=conv.affected_flow or "Unknown",
                product_area=conv.product_area or "Unknown",
                component=conv.component or "Unknown",
                excerpt=(conv.excerpt or "")[:500],  # Limit excerpt length
            )
            parts.append(part)
        return "\n".join(parts)

    def _parse_response(
        self,
        response_text: str,
        signature: str,
        conversations: List[ConversationContext],
    ) -> PMReviewResult:
        """
        Parse LLM response into PMReviewResult.

        Args:
            response_text: Raw response from LLM
            signature: Original signature being reviewed
            conversations: List of conversations for ID mapping

        Returns:
            Parsed PMReviewResult
        """
        # Try to extract JSON from response
        try:
            # Handle potential markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse PM review response as JSON: {e}")
            return PMReviewResult(
                original_signature=signature,
                conversation_count=len(conversations),
                decision=ReviewDecision.KEEP_TOGETHER,
                reasoning=f"JSON parse error: {str(e)}",
            )

        # Extract decision
        decision_str = data.get("decision", "keep_together").lower()
        if decision_str == "split":
            decision = ReviewDecision.SPLIT
        elif decision_str == "reject":
            decision = ReviewDecision.REJECT
        else:
            decision = ReviewDecision.KEEP_TOGETHER

        # Extract reasoning
        reasoning = data.get("reasoning", "No reasoning provided")

        # Build sub-groups if split
        sub_groups: List[SubGroupSuggestion] = []
        if decision == ReviewDecision.SPLIT:
            for sg in data.get("sub_groups", []):
                sub_groups.append(
                    SubGroupSuggestion(
                        suggested_signature=sg.get("suggested_signature", "unknown"),
                        conversation_ids=sg.get("conversation_ids", []),
                        rationale=sg.get("rationale", ""),
                        confidence=sg.get("same_fix_confidence", 0.0),
                    )
                )

        # Extract orphan conversation IDs
        orphan_ids: List[str] = []
        for orphan in data.get("orphans", []):
            if isinstance(orphan, dict) and "conversation_id" in orphan:
                orphan_ids.append(orphan["conversation_id"])
            elif isinstance(orphan, str):
                orphan_ids.append(orphan)

        # Edge case: All conversations become orphans after split
        if decision == ReviewDecision.SPLIT and not sub_groups:
            # All conversations are too different - treat as reject
            decision = ReviewDecision.REJECT
            reasoning = f"Split suggested but no valid sub-groups: {reasoning}"
            # Preserve any orphan_ids from LLM, then add remaining conversations
            existing_orphan_ids = set(orphan_ids)
            for c in conversations:
                if c.conversation_id not in existing_orphan_ids:
                    orphan_ids.append(c.conversation_id)

        return PMReviewResult(
            original_signature=signature,
            conversation_count=len(conversations),
            decision=decision,
            reasoning=reasoning,
            sub_groups=sub_groups,
            orphan_conversation_ids=orphan_ids,
        )
