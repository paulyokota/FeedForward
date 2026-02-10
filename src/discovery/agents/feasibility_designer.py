"""Feasibility Designer for the Discovery Engine (Issue #221).

Stage 3 orchestrator: coordinates the Tech Lead Agent and Risk/QA Agent
in a dialogue loop to produce TechnicalSpecs for feasible solutions and
InfeasibleSolution records for solutions that can't be built.

Pattern mirrors SolutionDesigner (Stage 2): per-brief assessment with
multi-round dialogue, convergence check, and forced convergence.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.discovery.agents.risk_agent import RiskAgent
from src.discovery.agents.tech_lead_agent import TechLeadAgent
from src.discovery.models.enums import ConfidenceLevel, FeasibilityAssessment, SourceType

logger = logging.getLogger(__name__)


@dataclass
class DialogueTurn:
    """A single turn in the Tech Lead ↔ Risk Agent dialogue."""

    round_number: int
    agent: str  # "tech_lead" or "risk_agent"
    role: str  # "assessment", "revision", "risk_evaluation"
    content: Dict[str, Any]


@dataclass
class FeasibilityResult:
    """Result from assessing a single solution brief."""

    opportunity_id: str
    is_feasible: bool
    assessment: Dict[str, Any]  # Tech Lead's final assessment
    risk_evaluation: Optional[Dict[str, Any]] = None  # Risk Agent's evaluation
    dialogue_history: List[DialogueTurn] = field(default_factory=list)
    total_rounds: int = 0
    token_usage: Dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )


@dataclass
class FeasibilityDesignerConfig:
    """Configuration for the Feasibility Designer."""

    model: str = "gpt-4o-mini"
    max_rounds: int = 3
    temperature: float = 0.3


class FeasibilityDesigner:
    """Orchestrates Tech Lead + Risk Agent dialogue for feasibility assessment.

    For each solution brief:
    1. Tech Lead assesses feasibility
    2. If infeasible → record and return early
    3. Risk Agent evaluates risks
    4. If risks critical/high → Tech Lead revises (up to max_rounds)
    5. Converge when risks acceptable or max rounds reached
    """

    def __init__(
        self,
        tech_lead: TechLeadAgent,
        risk_agent: RiskAgent,
        config: Optional[FeasibilityDesignerConfig] = None,
    ):
        self.tech_lead = tech_lead
        self.risk_agent = risk_agent
        self.config = config or FeasibilityDesignerConfig()

    def assess_feasibility(
        self,
        solution_brief: Dict[str, Any],
        opportunity_brief: Dict[str, Any],
        prior_checkpoints: List[Dict[str, Any]],
    ) -> FeasibilityResult:
        """Assess feasibility of a single solution brief.

        Returns a FeasibilityResult with is_feasible=True (TechnicalSpec data)
        or is_feasible=False (InfeasibleSolution data).
        """
        opportunity_id = opportunity_brief.get(
            "opportunity_id",
            opportunity_brief.get("affected_area", "unknown"),
        )
        dialogue_history: List[DialogueTurn] = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        latest_approach = None
        latest_risk = None

        for round_num in range(1, self.config.max_rounds + 1):
            history_dicts = [
                {
                    "round_number": t.round_number,
                    "agent": t.agent,
                    "role": t.role,
                    "content": t.content,
                }
                for t in dialogue_history
            ]

            # --- Tech Lead assessment (or revision) ---
            if round_num == 1:
                approach = self.tech_lead.evaluate_feasibility(
                    solution_brief=solution_brief,
                    opportunity_brief=opportunity_brief,
                    prior_checkpoints=prior_checkpoints,
                    dialogue_history=history_dicts,
                )
            else:
                approach = self.tech_lead.revise_approach(
                    solution_brief=solution_brief,
                    opportunity_brief=opportunity_brief,
                    original_approach=latest_approach,
                    risk_feedback=latest_risk,
                    dialogue_history=history_dicts,
                )

            self._accumulate_usage(total_usage, approach.get("token_usage", {}))

            dialogue_history.append(
                DialogueTurn(
                    round_number=round_num,
                    agent="tech_lead",
                    role="assessment" if round_num == 1 else "revision",
                    content=approach,
                )
            )

            latest_approach = approach

            # --- Early exit: infeasible ---
            if approach["feasibility_assessment"] == "infeasible":
                logger.info(
                    "Solution for %s assessed as infeasible in round %d",
                    opportunity_id,
                    round_num,
                )
                return FeasibilityResult(
                    opportunity_id=opportunity_id,
                    is_feasible=False,
                    assessment=approach,
                    dialogue_history=dialogue_history,
                    total_rounds=round_num,
                    token_usage=total_usage,
                )

            # --- Risk Agent evaluation ---
            history_dicts = [
                {
                    "round_number": t.round_number,
                    "agent": t.agent,
                    "role": t.role,
                    "content": t.content,
                }
                for t in dialogue_history
            ]

            risk_eval = self.risk_agent.evaluate_risks(
                technical_approach=approach,
                solution_brief=solution_brief,
                opportunity_brief=opportunity_brief,
                dialogue_history=history_dicts,
            )

            self._accumulate_usage(total_usage, risk_eval.get("token_usage", {}))

            dialogue_history.append(
                DialogueTurn(
                    round_number=round_num,
                    agent="risk_agent",
                    role="risk_evaluation",
                    content=risk_eval,
                )
            )

            latest_risk = risk_eval

            # --- Convergence check ---
            # Both conditions required: Tech Lead says "feasible" AND Risk Agent
            # says risk <= medium. A "needs_revision" assessment with low risk
            # should NOT converge — the loop continues so the Tech Lead can
            # produce a proper feasible assessment with filled-in fields.
            is_risk_acceptable = risk_eval["overall_risk_level"] in ("low", "medium")
            is_assessment_feasible = approach["feasibility_assessment"] == "feasible"

            if is_risk_acceptable and is_assessment_feasible:
                logger.info(
                    "Feasibility converged for %s in round %d (risk: %s)",
                    opportunity_id,
                    round_num,
                    risk_eval["overall_risk_level"],
                )
                return FeasibilityResult(
                    opportunity_id=opportunity_id,
                    is_feasible=True,
                    assessment=latest_approach,
                    risk_evaluation=latest_risk,
                    dialogue_history=dialogue_history,
                    total_rounds=round_num,
                    token_usage=total_usage,
                )

        # --- Forced convergence: max rounds reached ---
        # If the final assessment is still "needs_revision" (not "feasible"),
        # treat as infeasible — building a TechnicalSpec from empty fields
        # would fail validation.
        final_assessment = latest_approach["feasibility_assessment"] if latest_approach else "unknown"
        if final_assessment != "feasible":
            logger.warning(
                "Feasibility forced infeasible for %s after %d rounds "
                "(assessment: %s, risk: %s)",
                opportunity_id,
                self.config.max_rounds,
                final_assessment,
                latest_risk["overall_risk_level"] if latest_risk else "unknown",
            )
            return FeasibilityResult(
                opportunity_id=opportunity_id,
                is_feasible=False,
                assessment=latest_approach,
                risk_evaluation=latest_risk,
                dialogue_history=dialogue_history,
                total_rounds=self.config.max_rounds,
                token_usage=total_usage,
            )

        logger.warning(
            "Feasibility forced convergence for %s after %d rounds (risk: %s)",
            opportunity_id,
            self.config.max_rounds,
            latest_risk["overall_risk_level"] if latest_risk else "unknown",
        )
        return FeasibilityResult(
            opportunity_id=opportunity_id,
            is_feasible=True,
            assessment=latest_approach,
            risk_evaluation=latest_risk,
            dialogue_history=dialogue_history,
            total_rounds=self.config.max_rounds,
            token_usage=total_usage,
        )

    def build_checkpoint_artifacts(
        self,
        results: List[FeasibilityResult],
    ) -> Dict[str, Any]:
        """Build FeasibilityRiskCheckpoint from assessment results.

        Separates feasible (→ TechnicalSpec) from infeasible (→ InfeasibleSolution).
        """
        now = datetime.now(timezone.utc).isoformat()
        specs = []
        infeasible = []
        total_rounds = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for result in results:
            total_rounds += result.total_rounds
            self._accumulate_usage(total_usage, result.token_usage)

            if result.is_feasible:
                spec = self._build_technical_spec(result, now)
                specs.append(spec)
            else:
                inf = self._build_infeasible_solution(result)
                infeasible.append(inf)

        return {
            "schema_version": 1,
            "specs": specs,
            "infeasible_solutions": infeasible,
            "feasibility_metadata": {
                "solutions_assessed": len(results),
                "feasible_count": len(specs),
                "infeasible_count": len(infeasible),
                "total_dialogue_rounds": total_rounds,
                "total_token_usage": total_usage,
                "model": self.config.model,
            },
        }

    def _build_technical_spec(
        self,
        result: FeasibilityResult,
        now: str,
    ) -> Dict[str, Any]:
        """Build a TechnicalSpec dict from a feasible result."""
        assessment = result.assessment
        risk_eval = result.risk_evaluation or {}

        # Guard: warn if required TechnicalSpec fields are empty
        for field in ("approach", "effort_estimate", "dependencies", "acceptance_criteria"):
            if not assessment.get(field):
                logger.warning(
                    "Building TechnicalSpec for %s with empty '%s' — "
                    "this may fail validation",
                    result.opportunity_id,
                    field,
                )

        # Build structured risks from Risk Agent output
        risks = []
        for risk_item in risk_eval.get("risks", []):
            if isinstance(risk_item, dict):
                risks.append({
                    "description": risk_item.get("description", "Unspecified risk"),
                    "severity": risk_item.get("severity", "medium"),
                    "mitigation": risk_item.get("mitigation", "No mitigation specified"),
                })
            else:
                risks.append({
                    "description": str(risk_item),
                    "severity": "medium",
                    "mitigation": "To be determined",
                })

        # Fallback: ensure at least one risk
        if not risks:
            risks.append({
                "description": "No specific risks identified by Risk Agent",
                "severity": "low",
                "mitigation": "Standard testing and review process",
            })

        # LLM sometimes returns structured dicts for string fields — coerce.
        def _coerce_str(val):
            if isinstance(val, str):
                return val
            return json.dumps(val, indent=2)

        spec = {
            "schema_version": 1,
            "opportunity_id": result.opportunity_id,
            "approach": _coerce_str(assessment.get("approach", "")),
            "effort_estimate": _coerce_str(assessment.get("effort_estimate", "")),
            "dependencies": _coerce_str(assessment.get("dependencies", "")),
            "risks": risks,
            "acceptance_criteria": _coerce_str(assessment.get("acceptance_criteria", "")),
        }

        # Add extra fields from assessment
        if risk_eval.get("rollout_concerns"):
            spec["rollout_concerns"] = risk_eval["rollout_concerns"]
        if risk_eval.get("regression_potential"):
            spec["regression_potential"] = risk_eval["regression_potential"]
        if risk_eval.get("test_scope_estimate"):
            spec["test_scope_estimate"] = risk_eval["test_scope_estimate"]
        if risk_eval.get("overall_risk_level"):
            spec["overall_risk_level"] = risk_eval["overall_risk_level"]

        return spec

    def _build_infeasible_solution(
        self,
        result: FeasibilityResult,
    ) -> Dict[str, Any]:
        """Build an InfeasibleSolution dict from an infeasible result."""
        assessment = result.assessment
        return {
            "opportunity_id": result.opportunity_id,
            "solution_summary": assessment.get("approach", "")
            or "Solution assessed as infeasible before approach was developed",
            "feasibility_assessment": FeasibilityAssessment.INFEASIBLE.value,
            "infeasibility_reason": assessment.get("infeasibility_reason", "") or "Assessed as infeasible (no specific reason provided)",
            "constraints_identified": assessment.get("constraints_identified", []),
        }

    @staticmethod
    def _accumulate_usage(
        total: Dict[str, int],
        new: Dict[str, int],
    ) -> None:
        """Add new token usage to running total."""
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            total[key] = total.get(key, 0) + new.get(key, 0)
