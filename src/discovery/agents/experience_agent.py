"""Experience Agent for the Discovery Engine (Issue #220).

Evaluates user impact for proposed solutions and proposes experience direction.
Scales engagement depth to the degree of user-facing change — from full UX
direction for high-impact changes to minimal notes for backend-only work.

Pure function: does not interact with ConversationService directly.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.discovery.agents.prompts import (
    EXPERIENCE_EVALUATION_SYSTEM,
    EXPERIENCE_EVALUATION_USER,
)

logger = logging.getLogger(__name__)


@dataclass
class ExperienceAgentConfig:
    """Configuration for the Experience Agent."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.5


class ExperienceAgent:
    """Agent that evaluates user experience impact of proposed solutions.

    Pure transform: takes a proposal and opportunity brief, produces an
    experience evaluation. Does NOT interact with ConversationService
    directly — the orchestration layer handles that.
    """

    def __init__(
        self,
        openai_client=None,
        config: Optional[ExperienceAgentConfig] = None,
    ):
        self.config = config or ExperienceAgentConfig()
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def evaluate_experience(
        self,
        proposed_solution: Dict[str, Any],
        opportunity_brief: Dict[str, Any],
        dialogue_history: List[Dict[str, Any]],
        validation_feedback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate user experience impact. Returns experience direction.

        Args:
            proposed_solution: The PM's proposal dict.
            opportunity_brief: The OpportunityBrief being addressed.
            dialogue_history: List of DialogueTurn dicts from prior rounds.
            validation_feedback: The Validation Agent's response from this
                round (None if not yet available).

        Returns:
            Dict with keys: user_impact_level, experience_direction,
            engagement_depth, notes.

        Raises:
            json.JSONDecodeError: If LLM returns non-JSON.
            ValueError: If required keys are missing from the response.
        """
        user_prompt = EXPERIENCE_EVALUATION_USER.format(
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            proposed_solution_json=json.dumps(proposed_solution, indent=2),
            validation_feedback_json=json.dumps(
                validation_feedback or {}, indent=2
            ),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": EXPERIENCE_EVALUATION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        raw = json.loads(response.choices[0].message.content)

        # Validate required keys
        if "user_impact_level" not in raw:
            raise ValueError(
                "Experience Agent response missing required 'user_impact_level' key"
            )

        valid_levels = {"high", "moderate", "low", "transparent"}
        if raw["user_impact_level"] not in valid_levels:
            logger.warning(
                "Unknown user_impact_level '%s', defaulting to 'moderate'",
                raw["user_impact_level"],
            )
            raw["user_impact_level"] = "moderate"

        return {
            "user_impact_level": raw["user_impact_level"],
            "experience_direction": raw.get("experience_direction", ""),
            "engagement_depth": raw.get("engagement_depth", "partial"),
            "notes": raw.get("notes", ""),
            "token_usage": usage,
        }
