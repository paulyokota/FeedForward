"""Discovery API Service.

Thin wrapper over DiscoveryStorage that assembles cross-stage data
for the discovery review UI. Reads Stage 0-5 artifacts and composes
them into API response shapes.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.discovery.db.storage import DiscoveryStorage
from src.discovery.models.enums import StageStatus, StageType

logger = logging.getLogger(__name__)


class DiscoveryApiService:
    """Reads discovery runs and assembles cross-stage data for the API."""

    def __init__(self, storage: DiscoveryStorage):
        self.storage = storage

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List runs with summary stats (opportunity count, stages completed)."""
        runs = self.storage.list_runs(limit=limit)
        result = []
        for run in runs:
            stages = self.storage.get_stage_executions_for_run(run.id)
            completed_stages = [
                s for s in stages if s.status == StageStatus.COMPLETED
            ]
            # Count opportunities from Stage 1 artifacts
            opp_count = 0
            for s in stages:
                if s.stage == StageType.OPPORTUNITY_FRAMING and s.artifacts:
                    opp_count = len(s.artifacts.get("briefs", []))
                    break

            result.append({
                "id": str(run.id),
                "status": run.status.value,
                "current_stage": run.current_stage.value if run.current_stage else None,
                "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "opportunity_count": opp_count,
                "stages_completed": len(completed_stages),
            })
        return result

    def get_run_detail(self, run_id: UUID) -> Optional[Dict[str, Any]]:
        """Get full run detail including all stage executions."""
        run = self.storage.get_run(run_id)
        if not run:
            return None

        stages = self.storage.get_stage_executions_for_run(run_id)
        stage_list = []
        for s in stages:
            stage_list.append({
                "id": s.id,
                "stage": s.stage.value,
                "status": s.status.value,
                "attempt_number": s.attempt_number,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "sent_back_from": s.sent_back_from.value if s.sent_back_from else None,
                "send_back_reason": s.send_back_reason,
            })

        return {
            "id": str(run.id),
            "status": run.status.value,
            "current_stage": run.current_stage.value if run.current_stage else None,
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "stages": stage_list,
        }

    def get_opportunities(self, run_id: UUID) -> Optional[List[Dict[str, Any]]]:
        """Get ranked opportunity list from Stage 4 prioritization.

        Returns None if run not found. Returns empty list if Stage 4
        hasn't completed yet. Each item includes review_status from
        Stage 5 if available.
        """
        run = self.storage.get_run(run_id)
        if not run:
            return None

        stages = self.storage.get_stage_executions_for_run(run_id)

        # Find Stage 4 (prioritization) artifacts
        rankings = []
        for s in stages:
            if (
                s.stage == StageType.PRIORITIZATION
                and s.status == StageStatus.COMPLETED
                and s.artifacts
            ):
                rankings = s.artifacts.get("rankings", [])
                break

        if not rankings:
            return []

        # Find Stage 1 briefs for problem_statement / affected_area
        briefs = []
        for s in stages:
            if s.stage == StageType.OPPORTUNITY_FRAMING and s.artifacts:
                briefs = s.artifacts.get("briefs", [])
                break

        # Find Stage 2 solutions for build_experiment_decision
        solutions = []
        for s in stages:
            if s.stage == StageType.SOLUTION_VALIDATION and s.artifacts:
                solutions = s.artifacts.get("solutions", [])
                break

        # Find Stage 5 decisions for review_status
        decisions = []
        for s in stages:
            if s.stage == StageType.HUMAN_REVIEW and s.artifacts:
                decisions = s.artifacts.get("decisions", [])
                break

        # Build decision lookup by opportunity_id
        decision_map = {d["opportunity_id"]: d for d in decisions if "opportunity_id" in d}

        # Build brief lookup by affected_area (which becomes opportunity_id in Stage 3+)
        brief_map: Dict[str, Dict[str, Any]] = {}
        for brief in briefs:
            area = brief.get("affected_area", "")
            if area:
                brief_map[area] = brief

        # Build solution lookup — solutions are positional with briefs,
        # so map using the same affected_area key from the corresponding brief
        solution_map: Dict[str, Dict[str, Any]] = {}
        for i, solution in enumerate(solutions):
            if i < len(briefs):
                area = briefs[i].get("affected_area", "")
                if area:
                    solution_map[area] = solution

        result = []
        for idx, ranking in enumerate(rankings):
            opp_id = ranking.get("opportunity_id", "")

            # Find matching brief by opportunity_id
            brief = brief_map.get(opp_id, {})
            problem_statement = brief.get("problem_statement", "")
            affected_area = brief.get("affected_area", "")
            evidence_count = len(brief.get("evidence", []))

            # Find matching solution by opportunity_id
            solution = solution_map.get(opp_id, {})
            build_experiment_decision = solution.get("build_experiment_decision", "")
            effort_estimate = solution.get("effort_estimate", "")

            # Check review status
            decision = decision_map.get(opp_id)
            review_status = decision["decision"] if decision else None

            result.append({
                "index": idx,
                "opportunity_id": opp_id,
                "problem_statement": problem_statement,
                "affected_area": affected_area,
                "recommended_rank": ranking.get("recommended_rank", idx + 1),
                "rationale": ranking.get("rationale", ""),
                "effort_estimate": effort_estimate,
                "build_experiment_decision": build_experiment_decision,
                "evidence_count": evidence_count,
                "review_status": review_status,
            })

        return result

    def get_opportunity_detail(
        self, run_id: UUID, idx: int
    ) -> Optional[Dict[str, Any]]:
        """Get full artifact chain for a single opportunity by index.

        idx is the position in Stage 4 rankings array. Returns None
        if run not found or idx out of bounds.
        """
        run = self.storage.get_run(run_id)
        if not run:
            return None

        stages = self.storage.get_stage_executions_for_run(run_id)

        # Stage 4 rankings
        rankings = []
        for s in stages:
            if (
                s.stage == StageType.PRIORITIZATION
                and s.status == StageStatus.COMPLETED
                and s.artifacts
            ):
                rankings = s.artifacts.get("rankings", [])
                break

        if idx < 0 or idx >= len(rankings):
            return None

        ranking = rankings[idx]
        opp_id = ranking.get("opportunity_id", "")

        # Stage 0 exploration findings
        exploration = None
        for s in stages:
            if s.stage == StageType.EXPLORATION and s.artifacts:
                exploration = s.artifacts
                break

        # Stage 1 opportunity brief — match by affected_area == opportunity_id
        opportunity_brief = None
        briefs = []
        for s in stages:
            if s.stage == StageType.OPPORTUNITY_FRAMING and s.artifacts:
                briefs = s.artifacts.get("briefs", [])
                break
        for brief in briefs:
            if brief.get("affected_area") == opp_id:
                opportunity_brief = brief
                break

        # Stage 2 solution brief — solutions are positional with briefs,
        # so find the brief's index and use it
        solution_brief = None
        solutions = []
        for s in stages:
            if s.stage == StageType.SOLUTION_VALIDATION and s.artifacts:
                solutions = s.artifacts.get("solutions", [])
                break
        for i, brief in enumerate(briefs):
            if brief.get("affected_area") == opp_id and i < len(solutions):
                solution_brief = solutions[i]
                break

        # Stage 3 tech spec — match by opportunity_id
        tech_spec = None
        for s in stages:
            if s.stage == StageType.FEASIBILITY_RISK and s.artifacts:
                specs = s.artifacts.get("specs", [])
                for spec in specs:
                    if spec.get("opportunity_id") == opp_id:
                        tech_spec = spec
                        break
                break

        # Stage 5 review decision
        review_decision = None
        for s in stages:
            if s.stage == StageType.HUMAN_REVIEW and s.artifacts:
                for d in s.artifacts.get("decisions", []):
                    if d.get("opportunity_id") == opp_id:
                        review_decision = d
                        break
                break

        return {
            "index": idx,
            "opportunity_id": opp_id,
            "exploration": exploration,
            "opportunity_brief": opportunity_brief,
            "solution_brief": solution_brief,
            "tech_spec": tech_spec,
            "priority_rationale": ranking,
            "review_decision": review_decision,
        }

    def submit_decision(
        self,
        run_id: UUID,
        idx: int,
        decision_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Submit a review decision for a single opportunity.

        Accumulates decisions in the Stage 5 (HUMAN_REVIEW) stage
        execution's artifacts. Last-write-wins for duplicate opportunity_id.

        Returns the updated ReviewDecision dict, or None if run/idx invalid.
        Raises ValueError if Stage 5 isn't active or ready.
        """
        run = self.storage.get_run(run_id)
        if not run:
            return None

        stages = self.storage.get_stage_executions_for_run(run_id)

        # Get rankings to resolve idx → opportunity_id
        rankings = []
        for s in stages:
            if (
                s.stage == StageType.PRIORITIZATION
                and s.status == StageStatus.COMPLETED
                and s.artifacts
            ):
                rankings = s.artifacts.get("rankings", [])
                break

        if idx < 0 or idx >= len(rankings):
            return None

        opp_id = rankings[idx].get("opportunity_id", "")

        # Find the HUMAN_REVIEW stage execution
        hr_stage = None
        for s in stages:
            if s.stage == StageType.HUMAN_REVIEW and s.status in (
                StageStatus.IN_PROGRESS,
                StageStatus.CHECKPOINT_REACHED,
            ):
                hr_stage = s
                break

        if hr_stage is None:
            raise ValueError(
                f"No active human_review stage for run {run_id}. "
                "Run may not have reached Stage 5 yet."
            )

        # Build the ReviewDecision
        review_decision = {
            "opportunity_id": opp_id,
            **decision_data,
        }

        # Read current artifacts (may be None for first decision)
        current_artifacts = hr_stage.artifacts or {
            "schema_version": 1,
            "decisions": [],
            "review_metadata": {
                "reviewer": decision_data.get("reviewer", "api_user"),
                "opportunities_reviewed": 0,
            },
        }

        # Replace existing decision for same opportunity_id, or append
        existing_decisions = current_artifacts.get("decisions", [])
        updated = False
        for i, d in enumerate(existing_decisions):
            if d.get("opportunity_id") == opp_id:
                existing_decisions[i] = review_decision
                updated = True
                break
        if not updated:
            existing_decisions.append(review_decision)

        current_artifacts["decisions"] = existing_decisions
        # Update reviewed count
        current_artifacts.setdefault("review_metadata", {})
        current_artifacts["review_metadata"]["opportunities_reviewed"] = len(
            existing_decisions
        )

        # Write back to stage execution
        self.storage.update_stage_status(
            hr_stage.id,
            hr_stage.status,  # preserve current status
            artifacts=current_artifacts,
        )

        return review_decision

    def complete_run(self, run_id: UUID) -> Optional[Dict[str, Any]]:
        """Complete a run after human review is done.

        This is a separate action from submitting decisions — the reviewer
        decides when they're done.

        Returns run summary or None if not found.
        Raises ValueError if run isn't at human_review stage.
        """
        from src.discovery.services.state_machine import DiscoveryStateMachine

        run = self.storage.get_run(run_id)
        if not run:
            return None

        stages = self.storage.get_stage_executions_for_run(run_id)

        # Find active HUMAN_REVIEW stage
        hr_stage = None
        for s in stages:
            if s.stage == StageType.HUMAN_REVIEW and s.status in (
                StageStatus.IN_PROGRESS,
                StageStatus.CHECKPOINT_REACHED,
            ):
                hr_stage = s
                break

        if hr_stage is None:
            raise ValueError(f"No active human_review stage for run {run_id}")

        artifacts = hr_stage.artifacts or {
            "schema_version": 1,
            "decisions": [],
            "review_metadata": {"reviewer": "api_user", "opportunities_reviewed": 0},
        }

        state_machine = DiscoveryStateMachine(self.storage)
        completed_run = state_machine.complete_run(run_id, artifacts=artifacts)

        return {
            "id": str(completed_run.id),
            "status": completed_run.status.value,
            "completed_at": completed_run.completed_at.isoformat() if completed_run.completed_at else None,
        }
