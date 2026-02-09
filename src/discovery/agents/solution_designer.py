"""Solution Designer orchestrator for the Discovery Engine (Issue #220).

Manages the multi-turn dialogue between three agents:
- Opportunity PM (solution mode): proposes solutions via LLM calls
- Validation Agent: challenges and designs experiments
- Experience Agent: evaluates user impact

This is the first iterative stage — agents go back and forth until convergence.
Each "round" is one cycle of PM → Validation → Experience. Convergence is
reached when the Validation Agent approves. If max_rounds is hit, convergence
is forced with a note.

Pure orchestrator: uses ValidationAgent and ExperienceAgent instances, and
makes its own LLM calls for the PM solution role. Does NOT interact with
ConversationService directly.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.discovery.agents.experience_agent import ExperienceAgent
from src.discovery.agents.prompts import (
    SOLUTION_PROPOSAL_SYSTEM,
    SOLUTION_PROPOSAL_USER,
    SOLUTION_REVISION_SYSTEM,
    SOLUTION_REVISION_USER,
)
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.models.enums import (
    BuildExperimentDecision,
    ConfidenceLevel,
    SourceType,
)

logger = logging.getLogger(__name__)


@dataclass
class DialogueTurn:
    """A single turn in the multi-agent dialogue."""

    round_number: int  # 1-indexed
    agent: str  # "opportunity_pm" | "validation" | "experience"
    role: str  # "proposal" | "evaluation" | "revision"
    content: Dict[str, Any]  # The agent's output dict


@dataclass
class SolutionDesignerConfig:
    """Configuration for the SolutionDesigner orchestrator."""

    max_rounds: int = 3
    model: str = "gpt-4o-mini"
    temperature: float = 0.5


@dataclass
class SolutionDesignResult:
    """Result of a multi-agent solution design dialogue."""

    proposed_solution: str
    experiment_plan: str
    success_metrics: str
    build_experiment_decision: str  # BuildExperimentDecision value
    decision_rationale: str
    evidence: List[Dict[str, Any]]
    dialogue_rounds: int
    validation_challenges: List[Dict[str, Any]]
    experience_direction: Dict[str, Any]
    convergence_forced: bool
    convergence_note: str
    token_usage: Dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )


class SolutionDesigner:
    """Orchestrator that manages the multi-agent solution design dialogue.

    Does NOT take an OpportunityPM instance. The PM's "solution mode" is
    a separate LLM persona — SolutionDesigner makes its own LLM calls
    using SOLUTION_PROPOSAL_* prompts.
    """

    def __init__(
        self,
        validation_agent: ValidationAgent,
        experience_agent: ExperienceAgent,
        openai_client=None,
        config: Optional[SolutionDesignerConfig] = None,
    ):
        self.validation_agent = validation_agent
        self.experience_agent = experience_agent
        self.config = config or SolutionDesignerConfig()
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def design_solution(
        self,
        opportunity_brief: Dict[str, Any],
        prior_checkpoints: List[Dict[str, Any]],
    ) -> SolutionDesignResult:
        """Run the multi-agent dialogue to design a solution.

        Processes a single OpportunityBrief. The caller iterates over
        multiple briefs and collects results.

        Flow per round:
        1. PM proposes/revises solution direction
        2. Validation Agent evaluates
        3. Experience Agent evaluates
        4. Check convergence (Validation assessment == "approve")
        5. If not converged and round < max_rounds, loop

        Returns a SolutionDesignResult.
        """
        dialogue_history: List[DialogueTurn] = []
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        validation_challenges: List[Dict[str, Any]] = []
        latest_proposal = None
        latest_validation = None
        latest_experience = None

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

            # Step 1: PM proposes or revises
            if round_num == 1:
                proposal = self._call_pm_solution(
                    opportunity_brief, prior_checkpoints, history_dicts
                )
            else:
                proposal = self._call_pm_revision(
                    opportunity_brief,
                    latest_proposal,
                    latest_validation,
                    latest_experience,
                    history_dicts,
                )

            self._accumulate_usage(total_usage, proposal.pop("token_usage", {}))
            latest_proposal = proposal

            dialogue_history.append(
                DialogueTurn(
                    round_number=round_num,
                    agent="opportunity_pm",
                    role="proposal" if round_num == 1 else "revision",
                    content=proposal,
                )
            )

            # Rebuild history dicts for agents that need the updated history
            history_dicts = [
                {
                    "round_number": t.round_number,
                    "agent": t.agent,
                    "role": t.role,
                    "content": t.content,
                }
                for t in dialogue_history
            ]

            # Step 2: Validation Agent evaluates
            validation = self.validation_agent.evaluate_solution(
                proposed_solution=proposal,
                opportunity_brief=opportunity_brief,
                dialogue_history=history_dicts,
            )
            self._accumulate_usage(total_usage, validation.pop("token_usage", {}))
            latest_validation = validation

            dialogue_history.append(
                DialogueTurn(
                    round_number=round_num,
                    agent="validation",
                    role="evaluation",
                    content=validation,
                )
            )

            # Record challenges
            if validation["assessment"] == "challenge":
                validation_challenges.append(
                    {
                        "round": round_num,
                        "challenge_reason": validation.get("challenge_reason", ""),
                        "critique": validation.get("critique", ""),
                    }
                )

            # Rebuild history dicts again
            history_dicts = [
                {
                    "round_number": t.round_number,
                    "agent": t.agent,
                    "role": t.role,
                    "content": t.content,
                }
                for t in dialogue_history
            ]

            # Step 3: Experience Agent evaluates
            experience = self.experience_agent.evaluate_experience(
                proposed_solution=proposal,
                opportunity_brief=opportunity_brief,
                dialogue_history=history_dicts,
                validation_feedback=validation,
            )
            self._accumulate_usage(total_usage, experience.pop("token_usage", {}))
            latest_experience = experience

            dialogue_history.append(
                DialogueTurn(
                    round_number=round_num,
                    agent="experience",
                    role="evaluation",
                    content=experience,
                )
            )

            # Step 4: Check convergence
            if validation["assessment"] == "approve":
                logger.info(
                    "Solution design converged in round %d for brief: %s",
                    round_num,
                    opportunity_brief.get("problem_statement", "?")[:50],
                )
                return self._build_result(
                    proposal=latest_proposal,
                    validation=latest_validation,
                    experience=latest_experience,
                    dialogue_rounds=round_num,
                    validation_challenges=validation_challenges,
                    convergence_forced=False,
                    convergence_note="",
                    total_usage=total_usage,
                )

        # Max rounds hit — forced convergence
        logger.warning(
            "Solution design forced convergence after %d rounds for brief: %s",
            self.config.max_rounds,
            opportunity_brief.get("problem_statement", "?")[:50],
        )
        last_assessment = latest_validation.get("assessment", "unknown") if latest_validation else "unknown"
        convergence_note = (
            f"Forced convergence after {self.config.max_rounds} rounds. "
            f"Last validation assessment: {last_assessment}. "
        )
        if validation_challenges:
            unresolved = validation_challenges[-1]
            convergence_note += (
                f"Unresolved challenge from round {unresolved['round']}: "
                f"{unresolved.get('challenge_reason', 'no reason given')}"
            )

        return self._build_result(
            proposal=latest_proposal,
            validation=latest_validation,
            experience=latest_experience,
            dialogue_rounds=self.config.max_rounds,
            validation_challenges=validation_challenges,
            convergence_forced=True,
            convergence_note=convergence_note,
            total_usage=total_usage,
        )

    def build_checkpoint_artifacts(
        self,
        results: List[SolutionDesignResult],
    ) -> Dict[str, Any]:
        """Convert list of SolutionDesignResults into SolutionValidationCheckpoint.

        One SolutionDesignResult per OpportunityBrief → one SolutionBrief each.
        """
        now = datetime.now(timezone.utc).isoformat()
        solutions = []
        total_rounds = 0
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        for result in results:
            total_rounds += result.dialogue_rounds
            self._accumulate_usage(total_usage, result.token_usage)

            # Build evidence pointers from the result's evidence list
            evidence = []
            for ev in result.evidence:
                evidence.append(
                    {
                        "source_type": ev.get(
                            "source_type", SourceType.INTERCOM.value
                        ),
                        "source_id": ev.get("source_id", "unknown"),
                        "retrieved_at": ev.get("retrieved_at", now),
                        "confidence": ConfidenceLevel.from_raw(
                            ev.get("confidence", "medium")
                        ),
                    }
                )

            # Build SolutionBrief dict with core + extra fields
            solution_brief = {
                "schema_version": 1,
                "proposed_solution": result.proposed_solution,
                "experiment_plan": result.experiment_plan,
                "success_metrics": result.success_metrics,
                "build_experiment_decision": result.build_experiment_decision,
                "evidence": evidence,
                # Extra fields (stored via extra='allow')
                "decision_rationale": result.decision_rationale,
                "validation_challenges": result.validation_challenges,
                "experience_direction": result.experience_direction,
                "convergence_forced": result.convergence_forced,
                "convergence_note": result.convergence_note,
            }
            solutions.append(solution_brief)

        return {
            "schema_version": 1,
            "solutions": solutions,
            "design_metadata": {
                "opportunity_briefs_processed": len(results),
                "solutions_produced": len(solutions),
                "total_dialogue_rounds": total_rounds,
                "total_token_usage": total_usage,
                "model": self.config.model,
            },
        }

    # ========================================================================
    # Internal LLM call methods
    # ========================================================================

    def _call_pm_solution(
        self,
        opportunity_brief: Dict[str, Any],
        prior_checkpoints: List[Dict[str, Any]],
        dialogue_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Call the PM in solution mode (first round)."""
        user_prompt = SOLUTION_PROPOSAL_USER.format(
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            prior_context_json=json.dumps(prior_checkpoints, indent=2),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": SOLUTION_PROPOSAL_SYSTEM},
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

        if "proposed_solution" not in raw:
            raise ValueError(
                "PM solution response missing required 'proposed_solution' key"
            )

        raw["token_usage"] = usage
        return raw

    def _call_pm_revision(
        self,
        opportunity_brief: Dict[str, Any],
        original_proposal: Dict[str, Any],
        validation_feedback: Dict[str, Any],
        experience_feedback: Dict[str, Any],
        dialogue_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Call the PM to revise after feedback."""
        user_prompt = SOLUTION_REVISION_USER.format(
            opportunity_brief_json=json.dumps(opportunity_brief, indent=2),
            original_proposal_json=json.dumps(original_proposal, indent=2),
            validation_feedback_json=json.dumps(validation_feedback, indent=2),
            experience_feedback_json=json.dumps(experience_feedback, indent=2),
            dialogue_history_json=json.dumps(dialogue_history, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": SOLUTION_REVISION_SYSTEM},
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

        if "proposed_solution" not in raw:
            raise ValueError(
                "PM revision response missing required 'proposed_solution' key"
            )

        raw["token_usage"] = usage
        return raw

    # ========================================================================
    # Internal helpers
    # ========================================================================

    def _build_result(
        self,
        proposal: Dict[str, Any],
        validation: Dict[str, Any],
        experience: Dict[str, Any],
        dialogue_rounds: int,
        validation_challenges: List[Dict[str, Any]],
        convergence_forced: bool,
        convergence_note: str,
        total_usage: Dict[str, int],
    ) -> SolutionDesignResult:
        """Build a SolutionDesignResult from the latest state."""
        # Build evidence from proposal's evidence_ids
        now = datetime.now(timezone.utc).isoformat()
        evidence = []
        for eid in proposal.get("evidence_ids", []):
            evidence.append(
                {
                    "source_type": SourceType.INTERCOM.value,
                    "source_id": eid,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        proposal.get("confidence", "medium")
                    ),
                }
            )

        # Use experiment suggestion from validation if it provided one
        experiment_plan = proposal.get("experiment_plan", "")
        if validation.get("experiment_suggestion"):
            experiment_plan = validation["experiment_suggestion"]

        success_metrics = proposal.get("success_metrics", "")
        if validation.get("success_criteria"):
            success_metrics = (
                f"{success_metrics} | Validation criteria: "
                f"{validation['success_criteria']}"
            )

        return SolutionDesignResult(
            proposed_solution=proposal.get("proposed_solution", ""),
            experiment_plan=experiment_plan,
            success_metrics=success_metrics,
            build_experiment_decision=proposal.get(
                "build_experiment_decision", "experiment_first"
            ),
            decision_rationale=proposal.get("decision_rationale", ""),
            evidence=evidence,
            dialogue_rounds=dialogue_rounds,
            validation_challenges=validation_challenges,
            experience_direction={
                "user_impact_level": experience.get("user_impact_level", ""),
                "experience_direction": experience.get("experience_direction", ""),
                "engagement_depth": experience.get("engagement_depth", ""),
                "notes": experience.get("notes", ""),
            },
            convergence_forced=convergence_forced,
            convergence_note=convergence_note,
            token_usage=total_usage,
        )

    @staticmethod
    def _accumulate_usage(
        total: Dict[str, int], addition: Dict[str, int]
    ) -> None:
        """Accumulate token usage counts."""
        for key in total:
            total[key] += addition.get(key, 0)
