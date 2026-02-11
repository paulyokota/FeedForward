"""Discovery Engine Orchestrator.

Wires all Stage 0-4 agents together into a single run() call.
Stage 5 (human_review) is NOT automated — the orchestrator advances
the state machine to Stage 5 then returns. Humans use the existing
/api/discovery/runs/{id}/opportunities/{idx}/decide endpoints.
"""

import json
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
from src.discovery.agents.opportunity_pm import (
    OpportunityPM,
    extract_evidence_ids,
    extract_evidence_source_map,
)
from src.discovery.agents.posthog_data_access import PostHogReader
from src.discovery.agents.research_data_access import ResearchReader
from src.discovery.agents.research_explorer import ResearchExplorer
from src.discovery.agents.risk_agent import RiskAgent
from src.discovery.agents.solution_designer import SolutionDesigner
from src.discovery.agents.tech_lead_agent import TechLeadAgent
from src.discovery.agents.tpm_agent import TPMAgent
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.db.storage import DiscoveryStorage
from src.discovery.models.artifacts import InputRejection, InputValidationResult
from src.discovery.models.conversation import EventType
from src.discovery.models.enums import AgentStatus, StageType
from src.discovery.models.run import AgentInvocation, DiscoveryRun, RunConfig, TokenUsage
from src.discovery.services.conversation import ConversationService
from src.discovery.services.explorer_merge import merge_explorer_results
from src.discovery.services.repo_syncer import RepoSyncer
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import ConversationTransport

logger = logging.getLogger(__name__)

MAX_VALIDATION_RETRIES = 2


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
        # Determine target repo for codebase/research exploration
        target_repo = run_config.target_repo_path or self.repo_root
        scope_dirs = run_config.scope_dirs or ["src/"]
        doc_paths = run_config.doc_paths or ["docs/", "reference/"]

        # Auto-pull target repo if configured and it's not the FeedForward repo
        if run_config.target_repo_path and run_config.auto_pull:
            syncer = RepoSyncer(target_repo, run_id=str(run_id))
            sync_result = syncer.sync()
            if not sync_result.success:
                raise RuntimeError(
                    f"Failed to sync target repo {target_repo}: "
                    f"{sync_result.error}"
                )
            if sync_result.stash_created:
                logger.warning(
                    "Run %s: stashed %d files in %s (was on branch %s, "
                    "stash ref: %s). Files: %s",
                    run_id,
                    len(sync_result.stashed_files),
                    sync_result.repo_path,
                    sync_result.previous_branch,
                    sync_result.stash_ref,
                    ", ".join(sync_result.stashed_files[:10]),
                )
            if sync_result.commits_pulled > 0:
                logger.info(
                    "Run %s: pulled %d commits in %s (%s)",
                    run_id,
                    sync_result.commits_pulled,
                    sync_result.repo_path,
                    sync_result.default_branch,
                )
            elif sync_result.already_up_to_date:
                logger.info(
                    "Run %s: target repo %s already up to date",
                    run_id,
                    sync_result.repo_path,
                )

        conversation_reader = ConversationReader(self.db)
        codebase_reader = CodebaseReader(target_repo, scope_dirs=scope_dirs)
        research_reader = ResearchReader(
            doc_paths=doc_paths, repo_root=target_repo
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

        stage_exec = self.storage.get_active_stage(run_id)
        agent_names = []

        checkpoints = []
        for name, explorer in explorers:
            logger.info("Run %s: running %s explorer", run_id, name)
            started_at = datetime.now(timezone.utc)
            result = explorer.explore()
            checkpoint = explorer.build_checkpoint_artifacts(result)
            checkpoints.append(checkpoint)
            agent_names.append(name)
            self._record_invocation(
                run_id, stage_exec.id, name, result.token_usage, started_at
            )

        merged = merge_explorer_results(checkpoints)

        self.storage.update_participating_agents(stage_exec.id, agent_names)

        logger.info(
            "Run %s: exploration complete — %d findings from %d explorers",
            run_id,
            len(merged.get("findings", [])),
            len(checkpoints),
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "merged", artifacts=merged
        )

    def _run_opportunity_framing(self, run_id: UUID, convo_id: str):
        """Stage 1: OpportunityPM synthesizes explorer findings into briefs."""
        pm = OpportunityPM(openai_client=self.client)
        stage_exec = self.storage.get_active_stage(run_id)

        explorer_checkpoint = self._get_stage_artifacts(
            run_id, StageType.EXPLORATION
        )

        started_at = datetime.now(timezone.utc)
        result = pm.frame_opportunities(explorer_checkpoint)

        evidence_source_map = extract_evidence_source_map(explorer_checkpoint)
        valid_ids = extract_evidence_ids(explorer_checkpoint)
        artifacts = pm.build_checkpoint_artifacts(
            result,
            valid_evidence_ids=valid_ids if valid_ids else None,
            evidence_source_map=evidence_source_map if evidence_source_map else None,
        )

        self._record_invocation(
            run_id, stage_exec.id, "opportunity_pm",
            result.token_usage, started_at,
        )
        self.storage.update_participating_agents(
            stage_exec.id, ["opportunity_pm"]
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
        """Stage 2: SolutionDesigner runs multi-agent dialogue per brief.

        Validates briefs via SolutionDesigner.validate_input() before processing.
        Rejected briefs are revised by OpportunityPM.reframe_rejected() and
        re-validated up to MAX_VALIDATION_RETRIES times.
        """
        validation_agent = ValidationAgent(openai_client=self.client)
        experience_agent = ExperienceAgent(openai_client=self.client)
        designer = SolutionDesigner(
            validation_agent, experience_agent, openai_client=self.client
        )
        pm = OpportunityPM(openai_client=self.client)
        stage_exec = self.storage.get_active_stage(run_id)

        prior = self.service.get_prior_checkpoints(run_id)
        opp_artifacts = self._get_stage_artifacts(
            run_id, StageType.OPPORTUNITY_FRAMING
        )
        explorer_checkpoint = self._get_stage_artifacts(
            run_id, StageType.EXPLORATION
        )
        briefs = opp_artifacts.get("briefs", [])

        # --- Validate-retry-process loop ---
        final_briefs = self._validate_retry_briefs(
            run_id, convo_id, stage_exec.id, designer, pm,
            briefs, explorer_checkpoint,
        )

        results = []
        for i, brief in enumerate(final_briefs):
            logger.info(
                "Run %s: designing solution %d/%d (%s)",
                run_id,
                i + 1,
                len(final_briefs),
                brief.get("affected_area", "?"),
            )
            started_at = datetime.now(timezone.utc)
            try:
                result = designer.design_solution(brief, prior)
                results.append(result)
                self._record_invocation(
                    run_id, stage_exec.id, "solution_designer",
                    result.token_usage, started_at,
                )
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Run %s: skipping solution %d/%d (%s) — %s: %s",
                    run_id,
                    i + 1,
                    len(final_briefs),
                    brief.get("affected_area", "?"),
                    type(exc).__name__,
                    str(exc)[:200],
                )

        artifacts = designer.build_checkpoint_artifacts(results)

        self.storage.update_participating_agents(
            stage_exec.id,
            ["solution_designer", "validation_agent", "experience_agent"],
        )

        logger.info(
            "Run %s: solution validation complete — %d solutions",
            run_id,
            len(artifacts.get("solutions", [])),
        )

        return self.service.submit_checkpoint(
            convo_id, run_id, "solution_designer", artifacts=artifacts
        )

    def _run_feasibility_risk(self, run_id: UUID, convo_id: str):
        """Stage 3: FeasibilityDesigner assesses each solution.

        Validates solutions via FeasibilityDesigner.validate_input() before
        processing. Rejected solutions are revised by
        SolutionDesigner.revise_rejected() and re-validated up to
        MAX_VALIDATION_RETRIES times.
        """
        tech_lead = TechLeadAgent(openai_client=self.client)
        risk_agent = RiskAgent(openai_client=self.client)
        feas_designer = FeasibilityDesigner(tech_lead, risk_agent)
        # SolutionDesigner needed for revising rejected solutions
        sol_validation_agent = ValidationAgent(openai_client=self.client)
        sol_experience_agent = ExperienceAgent(openai_client=self.client)
        sol_designer = SolutionDesigner(
            sol_validation_agent, sol_experience_agent, openai_client=self.client
        )
        stage_exec = self.storage.get_active_stage(run_id)

        prior = self.service.get_prior_checkpoints(run_id)
        opp_artifacts = self._get_stage_artifacts(
            run_id, StageType.OPPORTUNITY_FRAMING
        )
        sol_artifacts = self._get_stage_artifacts(
            run_id, StageType.SOLUTION_VALIDATION
        )
        briefs = opp_artifacts.get("briefs", [])
        solutions = sol_artifacts.get("solutions", [])

        # --- Validate-retry-process loop ---
        final_briefs, final_solutions = self._validate_retry_solutions(
            run_id, convo_id, stage_exec.id, feas_designer, sol_designer,
            briefs, solutions,
        )

        results = []
        for i, brief in enumerate(final_briefs):
            solution = final_solutions[i] if i < len(final_solutions) else {}
            logger.info(
                "Run %s: assessing feasibility %d/%d (%s)",
                run_id,
                i + 1,
                len(final_briefs),
                brief.get("affected_area", "?"),
            )
            started_at = datetime.now(timezone.utc)
            try:
                result = feas_designer.assess_feasibility(solution, brief, prior)
                results.append(result)
                self._record_invocation(
                    run_id, stage_exec.id, "feasibility_designer",
                    result.token_usage, started_at,
                )
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Run %s: skipping feasibility %d/%d (%s) — %s: %s",
                    run_id,
                    i + 1,
                    len(final_briefs),
                    brief.get("affected_area", "?"),
                    type(exc).__name__,
                    str(exc)[:200],
                )

        artifacts = feas_designer.build_checkpoint_artifacts(results)

        self.storage.update_participating_agents(
            stage_exec.id,
            ["feasibility_designer", "tech_lead", "risk_agent"],
        )

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
        """Stage 4: TPMAgent ranks feasible opportunities.

        Validates packages via TPMAgent.validate_input() before ranking.
        Rejected specs are revised by FeasibilityDesigner.revise_rejected()
        and re-validated up to MAX_VALIDATION_RETRIES times.
        """
        tpm = TPMAgent(openai_client=self.client)
        # FeasibilityDesigner needed for revising rejected specs
        tech_lead = TechLeadAgent(openai_client=self.client)
        risk_agent = RiskAgent(openai_client=self.client)
        feas_designer = FeasibilityDesigner(tech_lead, risk_agent)
        stage_exec = self.storage.get_active_stage(run_id)

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

        # --- Validate-retry-process loop ---
        packages = self._validate_retry_packages(
            run_id, convo_id, stage_exec.id, tpm, feas_designer,
            packages, solution_map,
        )

        # Short-circuit when no feasible specs — emit empty rankings
        started_at = datetime.now(timezone.utc)
        if not packages:
            logger.info(
                "Run %s: no feasible specs — skipping TPM ranking", run_id
            )
            token_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            artifacts = tpm.build_checkpoint_artifacts([], token_usage)
        else:
            ranking_result = tpm.rank_opportunities(packages)
            token_usage = ranking_result["token_usage"]
            artifacts = tpm.build_checkpoint_artifacts(
                ranking_result["rankings"], token_usage
            )

        self._record_invocation(
            run_id, stage_exec.id, "tpm_agent", token_usage, started_at
        )
        self.storage.update_participating_agents(
            stage_exec.id, ["tpm_agent"]
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
    # Validation-retry helpers
    # ========================================================================

    def _validate_retry_briefs(
        self,
        run_id: UUID,
        convo_id: str,
        stage_execution_id: int,
        designer: SolutionDesigner,
        pm: OpportunityPM,
        briefs: List[Dict[str, Any]],
        explorer_checkpoint: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Validate briefs via SolutionDesigner, retry rejected via OpportunityPM.

        Returns final list of briefs: accepted (original order) + warned (appended).
        """
        if not briefs:
            return briefs

        # Build item_id → original index mapping for ordering
        id_field = "affected_area"
        item_ids = [b.get(id_field, f"brief_{i}") for i, b in enumerate(briefs)]
        item_map = {item_ids[i]: briefs[i] for i in range(len(briefs))}

        # Initial validation
        try:
            started_at = datetime.now(timezone.utc)
            validation = designer.validate_input(briefs, explorer_checkpoint)
            self._record_invocation(
                run_id, stage_execution_id, "solution_designer_validate",
                validation.token_usage, started_at,
            )
        except Exception:
            logger.warning(
                "Run %s: validate_input failed — accepting all %d briefs",
                run_id, len(briefs), exc_info=True,
            )
            return briefs

        self._post_validation_event(
            convo_id, "solution_designer", 0, validation,
        )

        accepted_ids = set(validation.accepted_items)
        rejected = validation.rejected_items

        retry_count = 0
        while rejected and retry_count < MAX_VALIDATION_RETRIES:
            retry_count += 1
            logger.info(
                "Run %s: validation retry %d — %d rejected briefs",
                run_id, retry_count, len(rejected),
            )

            rej_briefs = [item_map[r.item_id] for r in rejected if r.item_id in item_map]
            rej_list = [r for r in rejected if r.item_id in item_map]

            if not rej_briefs:
                break

            # Revise via OpportunityPM
            started_at = datetime.now(timezone.utc)
            evidence_source_map = extract_evidence_source_map(explorer_checkpoint)
            valid_ids = extract_evidence_ids(explorer_checkpoint)
            framing_result = pm.reframe_rejected(rej_briefs, rej_list, explorer_checkpoint)
            revised_artifacts = pm.build_checkpoint_artifacts(
                framing_result,
                valid_evidence_ids=valid_ids if valid_ids else None,
                evidence_source_map=evidence_source_map if evidence_source_map else None,
            )
            revised_briefs = revised_artifacts.get("briefs", [])
            self._record_invocation(
                run_id, stage_execution_id, "opportunity_pm_revise",
                framing_result.token_usage, started_at,
            )

            # Update item_map with revised briefs (keyed by affected_area)
            for rb in revised_briefs:
                rb_id = rb.get(id_field, "")
                if rb_id:
                    item_map[rb_id] = rb

            # Re-validate ONLY revised briefs
            try:
                started_at = datetime.now(timezone.utc)
                re_validation = designer.validate_input(revised_briefs, explorer_checkpoint)
                self._record_invocation(
                    run_id, stage_execution_id, "solution_designer_validate",
                    re_validation.token_usage, started_at,
                )
            except Exception:
                logger.warning(
                    "Run %s: re-validation failed — accepting revised briefs",
                    run_id, exc_info=True,
                )
                accepted_ids.update(rb.get(id_field, "") for rb in revised_briefs)
                rejected = []
                break

            self._post_validation_event(
                convo_id, "solution_designer", retry_count, re_validation,
            )

            accepted_ids.update(re_validation.accepted_items)
            rejected = re_validation.rejected_items

        # Items still rejected → add validation_warnings and include them
        warned_ids = set()
        for r in rejected:
            if r.item_id in item_map:
                brief = item_map[r.item_id]
                warnings = brief.get("validation_warnings") or []
                warnings.append(
                    f"Rejected after {MAX_VALIDATION_RETRIES} retries: {r.rejection_reason}"
                )
                brief["validation_warnings"] = warnings
                warned_ids.add(r.item_id)

        # Deterministic ordering: accepted in original order, warned appended
        final = []
        warned = []
        for iid in item_ids:
            if iid in warned_ids:
                warned.append(item_map[iid])
            else:
                final.append(item_map[iid])
        # Include revised items that may have new IDs
        for iid in accepted_ids:
            if iid not in set(item_ids) and iid in item_map:
                final.append(item_map[iid])
        final.extend(warned)

        logger.info(
            "Run %s: brief validation complete — %d accepted, %d warned",
            run_id, len(final) - len(warned), len(warned),
        )
        return final

    def _validate_retry_solutions(
        self,
        run_id: UUID,
        convo_id: str,
        stage_execution_id: int,
        feas_designer: FeasibilityDesigner,
        sol_designer: SolutionDesigner,
        briefs: List[Dict[str, Any]],
        solutions: List[Dict[str, Any]],
    ) -> tuple:
        """Validate solutions via FeasibilityDesigner, retry via SolutionDesigner.

        Returns (final_briefs, final_solutions) with accepted first, warned appended.
        Both lists maintain parallel index correspondence.
        """
        if not solutions:
            return briefs, solutions

        # Item IDs come from the parent brief's affected_area
        id_field = "affected_area"
        item_ids = [
            briefs[i].get(id_field, f"solution_{i}") if i < len(briefs) else f"solution_{i}"
            for i in range(len(solutions))
        ]
        sol_map = {item_ids[i]: solutions[i] for i in range(len(solutions))}
        brief_map = {
            item_ids[i]: briefs[i] if i < len(briefs) else {}
            for i in range(len(solutions))
        }

        # Initial validation
        try:
            started_at = datetime.now(timezone.utc)
            validation = feas_designer.validate_input(solutions, briefs)
            self._record_invocation(
                run_id, stage_execution_id, "feasibility_designer_validate",
                validation.token_usage, started_at,
            )
        except Exception:
            logger.warning(
                "Run %s: validate_input failed — accepting all %d solutions",
                run_id, len(solutions), exc_info=True,
            )
            return briefs, solutions

        self._post_validation_event(
            convo_id, "feasibility_designer", 0, validation,
        )

        accepted_ids = set(validation.accepted_items)
        rejected = validation.rejected_items

        retry_count = 0
        while rejected and retry_count < MAX_VALIDATION_RETRIES:
            retry_count += 1
            logger.info(
                "Run %s: solution validation retry %d — %d rejected",
                run_id, retry_count, len(rejected),
            )

            rej_sols = [sol_map[r.item_id] for r in rejected if r.item_id in sol_map]
            rej_briefs = [brief_map[r.item_id] for r in rejected if r.item_id in brief_map]
            rej_list = [r for r in rejected if r.item_id in sol_map]

            if not rej_sols:
                break

            # Revise via SolutionDesigner
            started_at = datetime.now(timezone.utc)
            revised_results = sol_designer.revise_rejected(rej_sols, rej_list, rej_briefs)
            # Convert SolutionDesignResult list to solution dicts
            revised_artifacts = sol_designer.build_checkpoint_artifacts(revised_results)
            revised_solutions = revised_artifacts.get("solutions", [])
            revision_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            for r in revised_results:
                for k in revision_usage:
                    revision_usage[k] += r.token_usage.get(k, 0)
            self._record_invocation(
                run_id, stage_execution_id, "solution_designer_revise",
                revision_usage, started_at,
            )

            # Update sol_map with revised solutions (keyed by original item_id)
            for idx, r in enumerate(rejected):
                if r.item_id in sol_map and idx < len(revised_solutions):
                    sol_map[r.item_id] = revised_solutions[idx]

            # Re-validate ONLY revised solutions
            revised_briefs_for_val = [brief_map.get(r.item_id, {}) for r in rej_list]
            try:
                started_at = datetime.now(timezone.utc)
                re_validation = feas_designer.validate_input(
                    revised_solutions,
                    revised_briefs_for_val,
                )
                self._record_invocation(
                    run_id, stage_execution_id, "feasibility_designer_validate",
                    re_validation.token_usage, started_at,
                )
            except Exception:
                logger.warning(
                    "Run %s: re-validation failed — accepting revised solutions",
                    run_id, exc_info=True,
                )
                accepted_ids.update(r.item_id for r in rej_list)
                rejected = []
                break

            self._post_validation_event(
                convo_id, "feasibility_designer", retry_count, re_validation,
            )

            accepted_ids.update(re_validation.accepted_items)
            rejected = re_validation.rejected_items

        # Items still rejected → add validation_warnings to their solutions
        warned_ids = set()
        for r in rejected:
            if r.item_id in sol_map:
                sol = sol_map[r.item_id]
                warnings = sol.get("validation_warnings") or []
                warnings.append(
                    f"Rejected after {MAX_VALIDATION_RETRIES} retries: {r.rejection_reason}"
                )
                sol["validation_warnings"] = warnings
                warned_ids.add(r.item_id)

        # Deterministic ordering: accepted in original order, warned appended
        final_briefs = []
        final_solutions = []
        warned_briefs = []
        warned_solutions = []
        for iid in item_ids:
            if iid in warned_ids:
                warned_briefs.append(brief_map[iid])
                warned_solutions.append(sol_map[iid])
            else:
                final_briefs.append(brief_map[iid])
                final_solutions.append(sol_map[iid])
        final_briefs.extend(warned_briefs)
        final_solutions.extend(warned_solutions)

        logger.info(
            "Run %s: solution validation complete — %d accepted, %d warned",
            run_id, len(final_solutions) - len(warned_solutions), len(warned_solutions),
        )
        return final_briefs, final_solutions

    def _validate_retry_packages(
        self,
        run_id: UUID,
        convo_id: str,
        stage_execution_id: int,
        tpm: TPMAgent,
        feas_designer: FeasibilityDesigner,
        packages: List[Dict[str, Any]],
        solution_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Validate packages via TPMAgent, retry rejected specs via FeasibilityDesigner.

        Returns final list of packages: accepted (original order) + warned (appended).
        """
        if not packages:
            return packages

        id_field = "opportunity_id"
        item_ids = [p.get(id_field, f"package_{i}") for i, p in enumerate(packages)]
        pkg_map = {item_ids[i]: packages[i] for i in range(len(packages))}

        # Initial validation
        try:
            started_at = datetime.now(timezone.utc)
            validation = tpm.validate_input(packages)
            self._record_invocation(
                run_id, stage_execution_id, "tpm_validate",
                validation.token_usage, started_at,
            )
        except Exception:
            logger.warning(
                "Run %s: validate_input failed — accepting all %d packages",
                run_id, len(packages), exc_info=True,
            )
            return packages

        self._post_validation_event(
            convo_id, "tpm_agent", 0, validation,
        )

        accepted_ids = set(validation.accepted_items)
        rejected = validation.rejected_items

        retry_count = 0
        while rejected and retry_count < MAX_VALIDATION_RETRIES:
            retry_count += 1
            logger.info(
                "Run %s: package validation retry %d — %d rejected",
                run_id, retry_count, len(rejected),
            )

            rej_specs = []
            rej_solutions = []
            rej_list = []
            for r in rejected:
                if r.item_id in pkg_map:
                    pkg = pkg_map[r.item_id]
                    rej_specs.append(pkg.get("technical_spec", {}))
                    rej_solutions.append(pkg.get("solution_brief", {}))
                    rej_list.append(r)

            if not rej_specs:
                break

            # Revise specs via FeasibilityDesigner
            started_at = datetime.now(timezone.utc)
            revised_results = feas_designer.revise_rejected(rej_specs, rej_list, rej_solutions)
            revised_artifacts = feas_designer.build_checkpoint_artifacts(revised_results)
            revised_specs = revised_artifacts.get("specs", [])
            revision_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            for r in revised_results:
                for k in revision_usage:
                    revision_usage[k] += r.token_usage.get(k, 0)
            self._record_invocation(
                run_id, stage_execution_id, "feasibility_designer_revise",
                revision_usage, started_at,
            )

            # Rebuild packages with revised specs
            revised_packages = []
            for idx, rej in enumerate(rej_list):
                if idx < len(revised_specs) and rej.item_id in pkg_map:
                    pkg = dict(pkg_map[rej.item_id])
                    pkg["technical_spec"] = revised_specs[idx]
                    pkg_map[rej.item_id] = pkg
                    revised_packages.append(pkg)

            # Re-validate ONLY revised packages
            try:
                started_at = datetime.now(timezone.utc)
                re_validation = tpm.validate_input(revised_packages)
                self._record_invocation(
                    run_id, stage_execution_id, "tpm_validate",
                    re_validation.token_usage, started_at,
                )
            except Exception:
                logger.warning(
                    "Run %s: re-validation failed — accepting revised packages",
                    run_id, exc_info=True,
                )
                accepted_ids.update(rej.item_id for rej in rej_list)
                rejected = []
                break

            self._post_validation_event(
                convo_id, "tpm_agent", retry_count, re_validation,
            )

            accepted_ids.update(re_validation.accepted_items)
            rejected = re_validation.rejected_items

        # Items still rejected → add validation_warnings to their specs
        warned_ids = set()
        for r in rejected:
            if r.item_id in pkg_map:
                spec = pkg_map[r.item_id].get("technical_spec", {})
                warnings = spec.get("validation_warnings") or []
                warnings.append(
                    f"Rejected after {MAX_VALIDATION_RETRIES} retries: {r.rejection_reason}"
                )
                spec["validation_warnings"] = warnings
                warned_ids.add(r.item_id)

        # Deterministic ordering: accepted in original order, warned appended
        final = []
        warned = []
        for iid in item_ids:
            if iid in warned_ids:
                warned.append(pkg_map[iid])
            else:
                final.append(pkg_map[iid])
        final.extend(warned)

        logger.info(
            "Run %s: package validation complete — %d accepted, %d warned",
            run_id, len(final) - len(warned), len(warned),
        )
        return final

    def _post_validation_event(
        self,
        convo_id: str,
        agent_name: str,
        cycle: int,
        validation: InputValidationResult,
    ) -> None:
        """Post an INPUT_VALIDATION event to the conversation."""
        try:
            self.service.post_event(
                convo_id,
                agent_name,
                EventType.INPUT_VALIDATION,
                {
                    "cycle": cycle,
                    "accepted": len(validation.accepted_items),
                    "rejected": len(validation.rejected_items),
                    "rejected_item_ids": [r.item_id for r in validation.rejected_items],
                },
            )
        except Exception:
            logger.warning(
                "Failed to post validation event for %s cycle %d",
                agent_name, cycle, exc_info=True,
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

    def _record_invocation(
        self,
        run_id: UUID,
        stage_execution_id: int,
        agent_name: str,
        token_usage: Dict[str, int],
        started_at: datetime,
    ) -> None:
        """Record a completed agent invocation to the database."""
        completed_at = datetime.now(timezone.utc)
        invocation = AgentInvocation(
            stage_execution_id=stage_execution_id,
            run_id=run_id,
            agent_name=agent_name,
            status=AgentStatus.COMPLETED,
            token_usage=TokenUsage(
                prompt_tokens=token_usage.get("prompt_tokens", 0),
                completion_tokens=token_usage.get("completion_tokens", 0),
                total_tokens=token_usage.get("total_tokens", 0),
            ),
            started_at=started_at,
            completed_at=completed_at,
        )
        try:
            self.storage.create_agent_invocation(invocation)
        except Exception:
            logger.warning(
                "Failed to record invocation for %s in run %s",
                agent_name,
                run_id,
                exc_info=True,
            )

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
