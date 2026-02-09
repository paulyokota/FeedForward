"""Validation Agent for the Discovery Engine (Issue #220).

Evaluates proposed solutions from the Opportunity PM (solution mode) and
challenges premature build commitment. Designs the smallest experiment
that would validate the hypothesis.

Has structural authority to challenge build_direct and build_with_metrics
decisions — these challenges are recorded in the final SolutionBrief.

Pure function: does not interact with ConversationService directly.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.discovery.agents.prompts import (
    VALIDATION_EVALUATION_SYSTEM,
    VALIDATION_EVALUATION_USER,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationAgentConfig:
    """Configuration for the Validation Agent."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.4  # Lower for structured critique


class ValidationAgent:
    """Agent that evaluates proposed solutions and challenges build decisions.

    Pure transform: takes a proposal and opportunity brief, produces an
    assessment with experiment suggestion. Does NOT interact with
    ConversationService directly — the orchestration layer handles that.
    """

    def __init__(
        self,
        openai_client=None,
        config: Optional[ValidationAgentConfig] = None,
    ):
        self.config = config or ValidationAgentConfig()
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def evaluate_solution(
        self,
        proposed_solution: Dict[str, Any],
        opportunity_brief: Dict[str, Any],
        dialogue_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluate a proposed solution. Returns critique + experiment suggestion.

        Args:
            proposed_solution: The PM's proposal dict (proposed_solution,
                experiment_plan, success_metrics, build_experiment_decision, etc.)
            opportunity_brief: The OpportunityBrief being addressed.
            dialogue_history: List of DialogueTurn dicts from prior rounds.

        Returns:
            Dict with keys: assessment, critique, experiment_suggestion,
            success_criteria, challenge_reason.

        Raises:
            json.JSONDecodeError: If LLM returns non-JSON.
            ValueError: If required keys are missing from the response.
        """
        user_prompt = VALIDATION_EVALUATION_USER.format(
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            proposed_solution_json=json.dumps(proposed_solution, indent=2),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": VALIDATION_EVALUATION_SYSTEM},
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
        if "assessment" not in raw:
            raise ValueError(
                "Validation Agent response missing required 'assessment' key"
            )

        valid_assessments = {"approve", "challenge", "request_revision"}
        if raw["assessment"] not in valid_assessments:
            logger.warning(
                "Unknown assessment '%s', defaulting to 'request_revision'",
                raw["assessment"],
            )
            raw["assessment"] = "request_revision"

        return {
            "assessment": raw["assessment"],
            "critique": raw.get("critique", ""),
            "experiment_suggestion": raw.get("experiment_suggestion", ""),
            "success_criteria": raw.get("success_criteria", ""),
            "challenge_reason": raw.get("challenge_reason", ""),
            "token_usage": usage,
        }
