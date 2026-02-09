"""Tech Lead Agent for the Discovery Engine (Issue #221).

Evaluates proposed solutions for technical feasibility against the actual
codebase. Produces technical approach, effort estimates, and identifies
infeasibility when solutions can't be built as proposed.

Pure function: does not interact with ConversationService directly.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.discovery.agents.prompts import (
    TECH_LEAD_ASSESSMENT_SYSTEM,
    TECH_LEAD_ASSESSMENT_USER,
    TECH_LEAD_REVISION_SYSTEM,
    TECH_LEAD_REVISION_USER,
)

logger = logging.getLogger(__name__)


@dataclass
class TechLeadAgentConfig:
    """Configuration for the Tech Lead Agent."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.3  # Low for technical analysis


class TechLeadAgent:
    """Agent that evaluates technical feasibility of proposed solutions.

    Pure transform: takes a solution brief + codebase context, produces
    a technical assessment. Does NOT interact with ConversationService
    directly — the orchestration layer handles that.
    """

    def __init__(
        self,
        openai_client=None,
        config: Optional[TechLeadAgentConfig] = None,
    ):
        self.config = config or TechLeadAgentConfig()
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def evaluate_feasibility(
        self,
        solution_brief: Dict[str, Any],
        opportunity_brief: Dict[str, Any],
        prior_checkpoints: List[Dict[str, Any]],
        dialogue_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Evaluate technical feasibility of a proposed solution.

        Args:
            solution_brief: The SolutionBrief from Stage 2.
            opportunity_brief: The OpportunityBrief being addressed.
            prior_checkpoints: All prior stage outputs (includes Stage 0
                codebase explorer findings for grounding).
            dialogue_history: List of DialogueTurn dicts from prior rounds.

        Returns:
            Dict with keys: feasibility_assessment, approach, effort_estimate,
            dependencies, acceptance_criteria, infeasibility_reason,
            constraints_identified, evidence_ids, confidence, token_usage.

        Raises:
            json.JSONDecodeError: If LLM returns non-JSON.
            ValueError: If required keys are missing from the response.
        """
        user_prompt = TECH_LEAD_ASSESSMENT_USER.format(
            solution_brief_json=json.dumps(solution_brief, indent=2),
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            prior_checkpoints_json=json.dumps(prior_checkpoints, indent=2),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": TECH_LEAD_ASSESSMENT_SYSTEM},
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

        if "feasibility_assessment" not in raw:
            raise ValueError(
                "Tech Lead response missing required 'feasibility_assessment' key"
            )

        valid_assessments = {"feasible", "infeasible", "needs_revision"}
        if raw["feasibility_assessment"] not in valid_assessments:
            logger.warning(
                "Unknown feasibility_assessment '%s', defaulting to 'needs_revision'",
                raw["feasibility_assessment"],
            )
            raw["feasibility_assessment"] = "needs_revision"

        return {
            "feasibility_assessment": raw["feasibility_assessment"],
            "approach": raw.get("approach", ""),
            "effort_estimate": raw.get("effort_estimate", ""),
            "dependencies": raw.get("dependencies", ""),
            "acceptance_criteria": raw.get("acceptance_criteria", ""),
            "infeasibility_reason": raw.get("infeasibility_reason", ""),
            "constraints_identified": raw.get("constraints_identified", []),
            "evidence_ids": raw.get("evidence_ids", []),
            "confidence": raw.get("confidence", "medium"),
            "token_usage": usage,
        }

    def revise_approach(
        self,
        solution_brief: Dict[str, Any],
        opportunity_brief: Dict[str, Any],
        original_approach: Dict[str, Any],
        risk_feedback: Dict[str, Any],
        dialogue_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Revise technical approach after risk feedback.

        Same return schema as evaluate_feasibility.
        """
        user_prompt = TECH_LEAD_REVISION_USER.format(
            solution_brief_json=json.dumps(solution_brief, indent=2),
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            original_approach_json=json.dumps(original_approach, indent=2),
            risk_feedback_json=json.dumps(risk_feedback, indent=2),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": TECH_LEAD_REVISION_SYSTEM},
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

        if "feasibility_assessment" not in raw:
            raise ValueError(
                "Tech Lead revision response missing required 'feasibility_assessment' key"
            )

        valid_assessments = {"feasible", "infeasible", "needs_revision"}
        if raw["feasibility_assessment"] not in valid_assessments:
            logger.warning(
                "Unknown feasibility_assessment '%s', defaulting to 'needs_revision'",
                raw["feasibility_assessment"],
            )
            raw["feasibility_assessment"] = "needs_revision"

        return {
            "feasibility_assessment": raw["feasibility_assessment"],
            "approach": raw.get("approach", ""),
            "effort_estimate": raw.get("effort_estimate", ""),
            "dependencies": raw.get("dependencies", ""),
            "acceptance_criteria": raw.get("acceptance_criteria", ""),
            "infeasibility_reason": raw.get("infeasibility_reason", ""),
            "constraints_identified": raw.get("constraints_identified", []),
            "evidence_ids": raw.get("evidence_ids", []),
            "confidence": raw.get("confidence", "medium"),
            "token_usage": usage,
        }
