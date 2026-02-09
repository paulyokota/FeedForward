"""Discovery Engine Orchestrator.

Wires all Stage 0-4 agents together into a single run() call.
Stage 5 (human_review) is NOT automated — the orchestrator advances
the state machine to Stage 5 then returns. Humans use the existing
/api/discovery/runs/{id}/opportunities/{idx}/decide endpoints.
"""

import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.discovery.agents.analytics_explorer import AnalyticsExplorer
from src.discovery.agents.codebase_data_access import CodebaseReader
from src.discovery.agents.codebase_explorer import CodebaseExplorer
from src.discovery.agents.customer_voice import CustomerVoiceExplorer
from src.discovery.agents.data_access import ConversationReader
from src.discovery.agents.experience_agent import ExperienceAgent
from src.discovery.agents.feasibility_designer import FeasibilityDesigner
from src.discovery.agents.opportunity_pm import OpportunityPM
from src.discovery.agents.posthog_data_access import PostHogReader
from src.discovery.agents.research_data_access import ResearchReader
from src.discovery.agents.research_explorer import ResearchExplorer
from src.discovery.agents.risk_agent import RiskAgent
from src.discovery.agents.solution_designer import SolutionDesigner
from src.discovery.agents.tech_lead_agent import TechLeadAgent
from src.discovery.agents.tpm_agent import TPMAgent
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.db.storage import DiscoveryStorage
from src.discovery.models.enums import StageType
from src.discovery.models.run import DiscoveryRun, RunConfig
from src.discovery.services.conversation import ConversationService
from src.discovery.services.explorer_merge import merge_explorer_results
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import ConversationTransport

logger = logging.getLogger(__name__)


class DiscoveryOrchestrator:
    """Runs the discovery pipeline Stages 0-4, then pauses for human review.

    Stage 5 (human_review) is NOT automated — the orchestrator advances
    the state machine to Stage 5, then returns. Humans use the existing
    /api/discovery/runs/{id}/opportunities/{idx}/decide endpoints.
    """

    def __init__(
        self,
        db_connection,
        transport: ConversationTransport,
        openai_client=None,
        posthog_data: Optional[Dict[str, Any]] = None,
        repo_root: Optional[str] = None,
    ):
        self.db = db_connection
        self.storage = DiscoveryStorage(db_connection)
        self.state_machine = DiscoveryStateMachine(self.storage)
        self.service = ConversationService(
            transport=transport,
            storage=self.storage,
            state_machine=self.state_machine,
        )
        self.posthog_data = posthog_data or {}
        self.repo_root = repo_root or str(
            Path(__file__).parent.parent.parent
        )
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def run(self, config: Optional[RunConfig] = None) -> DiscoveryRun:
        """Execute Stages 0-4 and return the DiscoveryRun with actual status.

        Returns DiscoveryRun so caller sees real status:
        - status=RUNNING, current_stage=human_review -> success, awaiting review
        - status=FAILED -> a stage errored, check run.errors
        """
        run_config = config or RunConfig()

        # Create and start the run (creates first stage execution)
        run = self.state_machine.create_run(config=run_config)
        run_id = run.id
        run = self.state_machine.start_run(run_id)

        logger.info("Discovery run %s started", run_id)

        # Stage 0 — Exploration
        stage_exec = self.storage.get_active_stage(run_id)
        convo_id = self.service.create_stage_conversation(run_id, stage_exec.id)

        try:
            new_stage = self._run_exploration(run_id, convo_id, run_config)
        except Exception as e:
            return self._fail_run(run_id, "exploration", e)

        # Stages 1-4: each stage method receives the convo_id from the
        # previous submit_checkpoint (which creates the new conversation).
        # But submit_checkpoint creates the conversation internally and
        # returns the new StageExecution. We need the new conversation_id
        # from the new stage execution.
        stage_methods = [
            ("opportunity_framing", self._run_opportunity_framing),
            ("solution_validation", self._run_solution_validation),
            ("feasibility_risk", self._run_feasibility_risk),
            ("prioritization", self._run_prioritization),
        ]

        for stage_name, method in stage_methods:
            # Get the conversation for the current active stage
            active = self.storage.get_active_stage(run_id)
            convo_id = active.conversation_id

            # If no conversation yet (shouldn't happen — submit_checkpoint creates one),
            # create one as fallback
            if not convo_id:
                convo_id = self.service.create_stage_conversation(run_id, active.id)

            try:
                method(run_id, convo_id)
            except Exception as e:
                return self._fail_run(run_id, stage_name, e)

        # After Stage 4, the state machine has advanced to Stage 5 (human_review).
        # Return the run so the caller sees status=running, current_stage=human_review.
        return self.storage.get_run(run_id)

    # ========================================================================
    # Stage implementations
    # ========================================================================

    def _run_exploration(
        self,
        run_id: UUID,
        convo_id: str,
        run_config: RunConfig,
    ):
        """Stage 0: Run all 4 explorers, merge results, submit checkpoint."""
        conversation_reader = ConversationReader(self.db)
        codebase_reader = CodebaseReader(self.repo_root, scope_dirs=["src/"])
        research_reader = ResearchReader(
            doc_paths=["docs/", "reference/"], repo_root=self.repo_root
        )
        posthog_reader = PostHogReader(**self.posthog_data)

        explorers = [
            (
                "customer_voice",
                CustomerVoiceExplorer(
                    reader=conversation_reader, openai_client=self.client
                ),
            ),
            (
                "analytics",
                AnalyticsExplorer(
                    reader=posthog_reader, openai_client=self.client
                ),
            ),
            (
                "codebase",
                CodebaseExplorer(
                    reader=codebase_reader, openai_client=self.client
                ),
            ),
            (
                "research",
                ResearchExplorer(
                    reader=research_reader, openai_client=self.client
                ),
            ),
        ]

        results = []
        for name, explorer in explorers:
            logger.info("Run %s: running %s explorer", run_id, name)
            result = explorer.explore()
            results.append((name, result))

        merged = merge_explorer_results(results)

        logger.info(
            "Run %s: exploration complete — %d findings from %d explorers",
            run_id,
            len(merged.get("findings", [])),
            len(results),
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "merged", artifacts=merged
        )

    def _run_opportunity_framing(self, run_id: UUID, convo_id: str):
        """Stage 1: OpportunityPM synthesizes explorer findings into briefs."""
        pm = OpportunityPM(openai_client=self.client)

        explorer_checkpoint = self._get_stage_artifacts(
            run_id, StageType.EXPLORATION
        )

        result = pm.frame_opportunities(explorer_checkpoint)

        # Extract valid evidence IDs for filtering
        valid_ids = set()
        for finding in explorer_checkpoint.get("findings", []):
            for ev in finding.get("evidence", []):
                if "id" in ev:
                    valid_ids.add(ev["id"])

        artifacts = pm.build_checkpoint_artifacts(
            result, valid_evidence_ids=valid_ids if valid_ids else None
        )

        logger.info(
            "Run %s: opportunity framing complete — %d briefs",
            run_id,
            len(artifacts.get("briefs", [])),
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "opportunity_pm", artifacts=artifacts
        )

    def _run_solution_validation(self, run_id: UUID, convo_id: str):
        """Stage 2: SolutionDesigner runs multi-agent dialogue per brief."""
        validation_agent = ValidationAgent(openai_client=self.client)
        experience_agent = ExperienceAgent(openai_client=self.client)
        designer = SolutionDesigner(
            validation_agent, experience_agent, openai_client=self.client
        )

        prior = self.service.get_prior_checkpoints(run_id)
        opp_artifacts = self._get_stage_artifacts(
            run_id, StageType.OPPORTUNITY_FRAMING
        )
        briefs = opp_artifacts.get("briefs", [])

        results = []
        for i, brief in enumerate(briefs):
            logger.info(
                "Run %s: designing solution %d/%d (%s)",
                run_id,
                i + 1,
                len(briefs),
                brief.get("affected_area", "?"),
            )
            result = designer.design_solution(brief, prior)
            results.append(result)

        artifacts = designer.build_checkpoint_artifacts(results)

        logger.info(
            "Run %s: solution validation complete — %d solutions",
            run_id,
            len(artifacts.get("solutions", [])),
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "solution_designer", artifacts=artifacts
        )

    def _run_feasibility_risk(self, run_id: UUID, convo_id: str):
        """Stage 3: FeasibilityDesigner assesses each solution."""
        tech_lead = TechLeadAgent(openai_client=self.client)
        risk_agent = RiskAgent(openai_client=self.client)
        designer = FeasibilityDesigner(tech_lead, risk_agent)

        prior = self.service.get_prior_checkpoints(run_id)
        opp_artifacts = self._get_stage_artifacts(
            run_id, StageType.OPPORTUNITY_FRAMING
        )
        sol_artifacts = self._get_stage_artifacts(
            run_id, StageType.SOLUTION_VALIDATION
        )
        briefs = opp_artifacts.get("briefs", [])
        solutions = sol_artifacts.get("solutions", [])

        results = []
        for i, brief in enumerate(briefs):
            solution = solutions[i] if i < len(solutions) else {}
            logger.info(
                "Run %s: assessing feasibility %d/%d (%s)",
                run_id,
                i + 1,
                len(briefs),
                brief.get("affected_area", "?"),
            )
            result = designer.assess_feasibility(solution, brief, prior)
            results.append(result)

        artifacts = designer.build_checkpoint_artifacts(results)

        feasible_count = len(artifacts.get("specs", []))
        infeasible_count = len(artifacts.get("infeasible_solutions", []))
        logger.info(
            "Run %s: feasibility complete — %d feasible, %d infeasible",
            run_id,
            feasible_count,
            infeasible_count,
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "feasibility_designer", artifacts=artifacts
        )

    def _run_prioritization(self, run_id: UUID, convo_id: str):
        """Stage 4: TPMAgent ranks feasible opportunities."""
        tpm = TPMAgent(openai_client=self.client)

        feas_artifacts = self._get_stage_artifacts(
            run_id, StageType.FEASIBILITY_RISK
        )
        opp_artifacts = self._get_stage_artifacts(
            run_id, StageType.OPPORTUNITY_FRAMING
        )
        sol_artifacts = self._get_stage_artifacts(
            run_id, StageType.SOLUTION_VALIDATION
        )
        briefs = opp_artifacts.get("briefs", [])
        solutions = sol_artifacts.get("solutions", [])

        # KEY MAPPING: Stage 1 briefs use "affected_area" as the ID.
        # Stage 3 FeasibilityDesigner copies it to "opportunity_id" on TechnicalSpecs.
        # So spec["opportunity_id"] == brief["affected_area"].
        brief_map = {b.get("affected_area", ""): b for b in briefs}
        solution_map: Dict[str, Any] = {}
        for i, b in enumerate(briefs):
            if i < len(solutions):
                solution_map[b.get("affected_area", "")] = solutions[i]

        # Build packages from ONLY feasible specs (not infeasible)
        packages = []
        for spec in feas_artifacts.get("specs", []):
            opp_id = spec.get("opportunity_id", "")
            packages.append(
                {
                    "opportunity_id": opp_id,
                    "opportunity_brief": brief_map.get(opp_id, {}),
                    "solution_brief": solution_map.get(opp_id, {}),
                    "technical_spec": spec,
                }
            )

        ranking_result = tpm.rank_opportunities(packages)
        artifacts = tpm.build_checkpoint_artifacts(
            ranking_result["rankings"], ranking_result["token_usage"]
        )

        logger.info(
            "Run %s: prioritization complete — %d opportunities ranked",
            run_id,
            len(artifacts.get("rankings", [])),
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "tpm_agent", artifacts=artifacts
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _get_stage_artifacts(
        self, run_id: UUID, stage: StageType
    ) -> Dict[str, Any]:
        """Fetch artifacts for a specific completed stage by name."""
        for checkpoint in self.service.get_prior_checkpoints(run_id):
            if checkpoint.get("stage") == stage.value:
                return checkpoint.get("artifacts", {})
        return {}

    def _fail_run(
        self, run_id: UUID, stage_name: str, error: Exception
    ) -> DiscoveryRun:
        """Mark a run as failed and return it."""
        error_detail = {
            "stage": stage_name,
            "error_type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.error(
            "Run %s failed at %s: %s", run_id, stage_name, error
        )
        return self.state_machine.fail_run(run_id, error_detail)
