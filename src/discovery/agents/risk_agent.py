"""Risk/QA Agent for the Discovery Engine (Issue #221).

Lightweight risk flagging for technical approaches. Identifies rollout risks,
regression potential, test scope, and system-level concerns. Not full QA
planning — flags what matters so the Tech Lead can address it.

Pure function: does not interact with ConversationService directly.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.discovery.agents.prompts import (
    RISK_EVALUATION_SYSTEM,
    RISK_EVALUATION_USER,
)

logger = logging.getLogger(__name__)


@dataclass
class RiskAgentConfig:
    """Configuration for the Risk/QA Agent."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.3  # Low for risk analysis


class RiskAgent:
    """Agent that evaluates risks of a technical approach.

    Pure transform: takes a technical approach and context, produces a
    risk assessment. Does NOT interact with ConversationService directly.
    """

    def __init__(
        self,
        openai_client=None,
        config: Optional[RiskAgentConfig] = None,
    ):
        self.config = config or RiskAgentConfig()
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def evaluate_risks(
        self,
        technical_approach: Dict[str, Any],
        solution_brief: Dict[str, Any],
        opportunity_brief: Dict[str, Any],
        dialogue_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluate risks of a technical approach.

        Args:
            technical_approach: The Tech Lead's assessment dict.
            solution_brief: The SolutionBrief from Stage 2.
            opportunity_brief: The OpportunityBrief being addressed.
            dialogue_history: List of DialogueTurn dicts from prior rounds.

        Returns:
            Dict with keys: risks, overall_risk_level, rollout_concerns,
            regression_potential, test_scope_estimate, token_usage.

        Raises:
            json.JSONDecodeError: If LLM returns non-JSON.
            ValueError: If required keys are missing from the response.
        """
        user_prompt = RISK_EVALUATION_USER.format(
            technical_approach_json=json.dumps(technical_approach, indent=2),
            solution_brief_json=json.dumps(solution_brief, indent=2),
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": RISK_EVALUATION_SYSTEM},
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

        if "risks" not in raw:
            raise ValueError(
                "Risk Agent response missing required 'risks' key"
            )

        valid_risk_levels = {"low", "medium", "high", "critical"}
        overall = raw.get("overall_risk_level", "medium")
        if overall not in valid_risk_levels:
            logger.warning(
                "Unknown overall_risk_level '%s', defaulting to 'medium'",
                overall,
            )
            overall = "medium"

        return {
            "risks": raw.get("risks", []),
            "overall_risk_level": overall,
            "rollout_concerns": raw.get("rollout_concerns", ""),
            "regression_potential": raw.get("regression_potential", ""),
            "test_scope_estimate": raw.get("test_scope_estimate", ""),
            "token_usage": usage,
        }
