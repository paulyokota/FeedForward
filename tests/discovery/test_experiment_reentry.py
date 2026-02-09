"""Tests for experiment re-entry mechanism (Issue #224).

Covers:
- ExperimentResult model validation
- ExperimentOutcome / ExperimentRecommendation enums
- RunMetadata extra='allow' for experiment_results
- State machine create_reentry_run
- ConversationService get_reentry_context
- SolutionDesigner re-entry branch (uses SOLUTION_REENTRY prompts)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.discovery.agents.experience_agent import ExperienceAgent
from src.discovery.agents.prompts import (
    SOLUTION_PROPOSAL_SYSTEM,
    SOLUTION_REENTRY_SYSTEM,
    SOLUTION_REENTRY_USER,
)
from src.discovery.agents.solution_designer import (
    SolutionDesigner,
    SolutionDesignerConfig,
)
from src.discovery.agents.validation_agent import ValidationAgent
from src.discovery.models.artifacts import ExperimentResult
from src.discovery.models.enums import (
    ConfidenceLevel,
    ExperimentOutcome,
    ExperimentRecommendation,
    RunStatus,
    SourceType,
    StageStatus,
    StageType,
    STAGE_ORDER,
)
from src.discovery.models.run import (
    DiscoveryRun,
    RunConfig,
    RunMetadata,
    StageExecution,
)
from src.discovery.services.conversation import ConversationService
from src.discovery.services.state_machine import (
    DiscoveryStateMachine,
    InvalidTransitionError,
)
from src.discovery.services.transport import InMemoryTransport


# ============================================================================
# Helpers
# ============================================================================


def _valid_experiment_results():
    """Minimal valid ExperimentResult dict."""
    return {
        "opportunity_id": "opp-001",
        "experiment_plan_executed": "A/B tested simplified scheduling wizard",
        "success_criteria": "15% improvement in scheduling completion rate",
        "measured_outcome": "22% improvement observed over 2 weeks",
        "outcome_vs_criteria": "met",
        "observations": "Users completed flow faster; no increase in errors",
        "recommendation": "scale_up",
    }


def _valid_evidence():
    return {
        "source_type": SourceType.INTERCOM.value,
        "source_id": "conv_001",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "confidence": ConfidenceLevel.HIGH.value,
    }


def _make_opportunity_brief():
    return {
        "problem_statement": "Users confused by scheduling UI",
        "evidence": [_valid_evidence()],
        "counterfactual": "15% fewer support tickets if simplified",
        "affected_area": "scheduling",
        "explorer_coverage": "180 conversations over 14 days",
    }


def _make_solution_brief():
    return {
        "schema_version": 1,
        "proposed_solution": "Simplify scheduling wizard to 2 steps",
        "experiment_plan": "A/B test with 10% of users",
        "success_metrics": "Scheduling completion rate +15%",
        "build_experiment_decision": "experiment_first",
        "evidence": [_valid_evidence()],
    }


def _make_llm_response(content_dict):
    """Create mock OpenAI ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 80
    mock_response.usage.total_tokens = 180
    return mock_response


# ============================================================================
# In-memory storage (supports parent_run_id)
# ============================================================================


class InMemoryStorage:
    """In-memory storage for testing — includes parent_run_id support."""

    def __init__(self):
        self.runs: Dict[UUID, DiscoveryRun] = {}
        self.stage_executions: Dict[int, StageExecution] = {}
        self.next_stage_id = 1

    def create_run(self, run: DiscoveryRun) -> DiscoveryRun:
        run_id = uuid4()
        now = datetime.now(timezone.utc)
        created = DiscoveryRun(
            id=run_id,
            parent_run_id=run.parent_run_id,
            status=run.status,
            current_stage=run.current_stage,
            config=run.config,
            metadata=run.metadata,
            started_at=now,
            errors=run.errors,
            warnings=run.warnings,
        )
        self.runs[run_id] = created
        return created

    def get_run(self, run_id: UUID) -> Optional[DiscoveryRun]:
        return self.runs.get(run_id)

    _UNSET = object()

    def update_run_status(
        self,
        run_id: UUID,
        status: RunStatus,
        current_stage=_UNSET,
        completed_at: Optional[datetime] = None,
    ) -> Optional[DiscoveryRun]:
        run = self.runs.get(run_id)
        if not run:
            return None
        run.status = status
        if current_stage is not self._UNSET:
            run.current_stage = current_stage
        if completed_at is not None:
            run.completed_at = completed_at
        return run

    def append_run_error(self, run_id: UUID, error: Dict[str, Any]) -> None:
        run = self.runs.get(run_id)
        if run:
            run.errors.append(error)

    def create_stage_execution(self, stage_exec: StageExecution) -> StageExecution:
        stage_id = self.next_stage_id
        self.next_stage_id += 1
        created = StageExecution(
            id=stage_id,
            run_id=stage_exec.run_id,
            stage=stage_exec.stage,
            status=stage_exec.status,
            attempt_number=stage_exec.attempt_number,
            participating_agents=stage_exec.participating_agents,
            artifacts=stage_exec.artifacts,
            artifact_schema_version=stage_exec.artifact_schema_version,
            conversation_id=stage_exec.conversation_id,
            sent_back_from=stage_exec.sent_back_from,
            send_back_reason=stage_exec.send_back_reason,
            started_at=stage_exec.started_at,
        )
        self.stage_executions[stage_id] = created
        return created

    def get_active_stage(self, run_id: UUID) -> Optional[StageExecution]:
        for se in self.stage_executions.values():
            if se.run_id == run_id and se.status in (
                StageStatus.IN_PROGRESS,
                StageStatus.CHECKPOINT_REACHED,
            ):
                return se
        return None

    def get_stage_executions_for_run(
        self, run_id: UUID, stage: Optional[StageType] = None
    ) -> List[StageExecution]:
        execs = [se for se in self.stage_executions.values() if se.run_id == run_id]
        if stage:
            execs = [se for se in execs if se.stage == stage]
        execs.sort(
            key=lambda se: (
                se.started_at or datetime.min.replace(tzinfo=timezone.utc),
                se.id,
            )
        )
        return execs

    def update_stage_status(
        self,
        execution_id: int,
        status: StageStatus,
        artifacts: Optional[Dict[str, Any]] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[StageExecution]:
        se = self.stage_executions.get(execution_id)
        if not se:
            return None
        se.status = status
        if artifacts is not None:
            se.artifacts = artifacts
        if completed_at is not None:
            se.completed_at = completed_at
        return se

    def get_latest_attempt_number(self, run_id: UUID, stage: StageType) -> int:
        attempts = [
            se.attempt_number
            for se in self.stage_executions.values()
            if se.run_id == run_id and se.stage == stage
        ]
        return max(attempts) if attempts else 0

    def update_stage_conversation_id(
        self, execution_id: int, conversation_id: str
    ) -> Optional[StageExecution]:
        se = self.stage_executions.get(execution_id)
        if not se:
            return None
        se.conversation_id = conversation_id
        return se

    def get_stage_conversation_id(
        self, run_id: UUID, stage: StageType
    ) -> Optional[str]:
        execs = [
            se
            for se in self.stage_executions.values()
            if se.run_id == run_id and se.stage == stage and se.conversation_id
        ]
        if not execs:
            return None
        execs.sort(key=lambda se: se.attempt_number, reverse=True)
        return execs[0].conversation_id

    def get_child_runs(self, parent_run_id: UUID) -> List[DiscoveryRun]:
        return [
            r for r in self.runs.values()
            if r.parent_run_id == parent_run_id
        ]


def _create_completed_parent_run(storage: InMemoryStorage):
    """Create a completed parent run with Stage 1 + Stage 2 artifacts."""
    now = datetime.now(timezone.utc)

    # Create parent run
    parent = storage.create_run(
        DiscoveryRun(
            status=RunStatus.COMPLETED,
            current_stage=StageType.HUMAN_REVIEW,
            completed_at=now,
        )
    )
    # Manually set completed status (create_run doesn't persist status)
    storage.runs[parent.id].status = RunStatus.COMPLETED
    storage.runs[parent.id].completed_at = now

    # Stage 1: Opportunity Framing — completed with briefs
    storage.create_stage_execution(
        StageExecution(
            run_id=parent.id,
            stage=StageType.OPPORTUNITY_FRAMING,
            status=StageStatus.COMPLETED,
            attempt_number=1,
            started_at=now,
            completed_at=now,
            artifacts={
                "schema_version": 1,
                "briefs": [_make_opportunity_brief()],
                "framing_metadata": {"findings_processed": 5},
            },
        )
    )

    # Stage 2: Solution Validation — completed with solutions
    storage.create_stage_execution(
        StageExecution(
            run_id=parent.id,
            stage=StageType.SOLUTION_VALIDATION,
            status=StageStatus.COMPLETED,
            attempt_number=1,
            started_at=now,
            completed_at=now,
            artifacts={
                "schema_version": 1,
                "solutions": [_make_solution_brief()],
                "design_metadata": {
                    "opportunity_briefs_processed": 1,
                    "solutions_produced": 1,
                    "total_dialogue_rounds": 2,
                    "total_token_usage": {
                        "prompt_tokens": 500,
                        "completion_tokens": 400,
                        "total_tokens": 900,
                    },
                    "model": "gpt-4o-mini",
                },
            },
        )
    )

    return parent


# ============================================================================
# ExperimentResult Model Tests
# ============================================================================


class TestExperimentResultModel:
    """ExperimentResult Pydantic model validation."""

    def test_valid_experiment_result(self):
        result = ExperimentResult(**_valid_experiment_results())
        assert result.opportunity_id == "opp-001"
        assert result.outcome_vs_criteria == ExperimentOutcome.MET
        assert result.recommendation == ExperimentRecommendation.SCALE_UP

    def test_extra_fields_allowed(self):
        data = _valid_experiment_results()
        data["custom_field"] = "extra data"
        result = ExperimentResult(**data)
        assert result.custom_field == "extra data"

    def test_missing_required_field_raises(self):
        data = _valid_experiment_results()
        del data["opportunity_id"]
        with pytest.raises(ValidationError):
            ExperimentResult(**data)

    def test_empty_string_required_field_raises(self):
        data = _valid_experiment_results()
        data["opportunity_id"] = ""
        with pytest.raises(ValidationError):
            ExperimentResult(**data)

    def test_invalid_outcome_raises(self):
        data = _valid_experiment_results()
        data["outcome_vs_criteria"] = "invalid_value"
        with pytest.raises(ValidationError):
            ExperimentResult(**data)

    def test_invalid_recommendation_raises(self):
        data = _valid_experiment_results()
        data["recommendation"] = "invalid_value"
        with pytest.raises(ValidationError):
            ExperimentResult(**data)

    def test_all_outcome_values(self):
        for outcome in ExperimentOutcome:
            data = _valid_experiment_results()
            data["outcome_vs_criteria"] = outcome.value
            result = ExperimentResult(**data)
            assert result.outcome_vs_criteria == outcome

    def test_all_recommendation_values(self):
        for rec in ExperimentRecommendation:
            data = _valid_experiment_results()
            data["recommendation"] = rec.value
            result = ExperimentResult(**data)
            assert result.recommendation == rec


# ============================================================================
# RunMetadata extra='allow' Tests
# ============================================================================


class TestRunMetadataExtra:
    """RunMetadata now accepts extra fields for experiment_results."""

    def test_experiment_results_stored_in_metadata(self):
        metadata = RunMetadata(experiment_results=_valid_experiment_results())
        dumped = metadata.model_dump()
        assert "experiment_results" in dumped
        assert dumped["experiment_results"]["opportunity_id"] == "opp-001"

    def test_metadata_still_has_standard_fields(self):
        metadata = RunMetadata(
            agent_versions={"pm": "v1"},
            experiment_results=_valid_experiment_results(),
        )
        assert metadata.agent_versions == {"pm": "v1"}
        dumped = metadata.model_dump()
        assert "experiment_results" in dumped


# ============================================================================
# State Machine: create_reentry_run
# ============================================================================


class TestCreateReentryRun:
    """State machine re-entry run creation."""

    def test_happy_path(self):
        storage = InMemoryStorage()
        sm = DiscoveryStateMachine(storage)
        parent = _create_completed_parent_run(storage)

        reentry = sm.create_reentry_run(
            parent_run_id=parent.id,
            experiment_results=_valid_experiment_results(),
        )

        assert reentry.parent_run_id == parent.id
        assert reentry.status == RunStatus.RUNNING
        assert reentry.current_stage == StageType.SOLUTION_VALIDATION

        # Experiment results stored in metadata
        dumped = reentry.metadata.model_dump()
        assert "experiment_results" in dumped
        assert dumped["experiment_results"]["opportunity_id"] == "opp-001"

        # Stage execution created at SOLUTION_VALIDATION
        active = storage.get_active_stage(reentry.id)
        assert active is not None
        assert active.stage == StageType.SOLUTION_VALIDATION
        assert active.status == StageStatus.IN_PROGRESS

    def test_parent_not_completed_raises(self):
        storage = InMemoryStorage()
        sm = DiscoveryStateMachine(storage)

        parent = storage.create_run(
            DiscoveryRun(status=RunStatus.RUNNING, current_stage=StageType.EXPLORATION)
        )
        # Manually set running
        storage.runs[parent.id].status = RunStatus.RUNNING

        with pytest.raises(InvalidTransitionError, match="not completed"):
            sm.create_reentry_run(
                parent_run_id=parent.id,
                experiment_results=_valid_experiment_results(),
            )

    def test_parent_not_found_raises(self):
        storage = InMemoryStorage()
        sm = DiscoveryStateMachine(storage)

        with pytest.raises(ValueError, match="not found"):
            sm.create_reentry_run(
                parent_run_id=uuid4(),
                experiment_results=_valid_experiment_results(),
            )

    def test_invalid_experiment_results_raises(self):
        storage = InMemoryStorage()
        sm = DiscoveryStateMachine(storage)
        parent = _create_completed_parent_run(storage)

        with pytest.raises(ValidationError):
            sm.create_reentry_run(
                parent_run_id=parent.id,
                experiment_results={"invalid": "data"},
            )

    def test_inherits_parent_config(self):
        storage = InMemoryStorage()
        sm = DiscoveryStateMachine(storage)
        parent = _create_completed_parent_run(storage)
        # Set a custom config on parent
        storage.runs[parent.id].config = RunConfig(
            target_domain="scheduling", time_window_days=30
        )

        reentry = sm.create_reentry_run(
            parent_run_id=parent.id,
            experiment_results=_valid_experiment_results(),
        )

        assert reentry.config.target_domain == "scheduling"
        assert reentry.config.time_window_days == 30

    def test_custom_start_stage(self):
        storage = InMemoryStorage()
        sm = DiscoveryStateMachine(storage)
        parent = _create_completed_parent_run(storage)

        reentry = sm.create_reentry_run(
            parent_run_id=parent.id,
            experiment_results=_valid_experiment_results(),
            start_stage=StageType.FEASIBILITY_RISK,
        )

        assert reentry.current_stage == StageType.FEASIBILITY_RISK
        active = storage.get_active_stage(reentry.id)
        assert active.stage == StageType.FEASIBILITY_RISK


# ============================================================================
# ConversationService: get_reentry_context
# ============================================================================


class TestGetReentryContext:
    """ConversationService.get_reentry_context retrieves parent context."""

    def _make_service(self):
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        sm = DiscoveryStateMachine(storage)
        svc = ConversationService(transport, storage, sm)
        return svc, storage

    def test_returns_parent_checkpoints_and_briefs(self):
        svc, storage = self._make_service()
        parent = _create_completed_parent_run(storage)

        # Create re-entry run
        reentry = storage.create_run(
            DiscoveryRun(
                parent_run_id=parent.id,
                status=RunStatus.RUNNING,
                current_stage=StageType.SOLUTION_VALIDATION,
                metadata=RunMetadata(
                    experiment_results=_valid_experiment_results()
                ),
            )
        )
        # Fix parent_run_id (create_run generates new UUID)
        storage.runs[reentry.id].parent_run_id = parent.id

        ctx = svc.get_reentry_context(reentry.id, opportunity_index=0)

        assert len(ctx["parent_checkpoints"]) >= 2
        assert ctx["experiment_results"] is not None
        assert ctx["original_opportunity_brief"] is not None
        assert ctx["original_opportunity_brief"]["problem_statement"] == "Users confused by scheduling UI"
        assert ctx["original_solution_brief"] is not None
        assert ctx["original_solution_brief"]["proposed_solution"] == "Simplify scheduling wizard to 2 steps"

    def test_non_reentry_run_raises(self):
        svc, storage = self._make_service()

        run = storage.create_run(
            DiscoveryRun(status=RunStatus.RUNNING)
        )

        with pytest.raises(ValueError, match="not a re-entry run"):
            svc.get_reentry_context(run.id, opportunity_index=0)

    def test_out_of_bounds_index_raises(self):
        svc, storage = self._make_service()
        parent = _create_completed_parent_run(storage)

        reentry = storage.create_run(
            DiscoveryRun(
                parent_run_id=parent.id,
                status=RunStatus.RUNNING,
                metadata=RunMetadata(
                    experiment_results=_valid_experiment_results()
                ),
            )
        )
        storage.runs[reentry.id].parent_run_id = parent.id

        with pytest.raises(IndexError, match="out of bounds"):
            svc.get_reentry_context(reentry.id, opportunity_index=5)

    def test_solution_index_out_of_bounds_raises(self):
        """Stage 2 solutions shorter than opportunity_index raises IndexError."""
        svc, storage = self._make_service()
        now = datetime.now(timezone.utc)

        # Create parent with 2 briefs but only 1 solution
        parent = storage.create_run(
            DiscoveryRun(
                status=RunStatus.COMPLETED,
                current_stage=StageType.HUMAN_REVIEW,
                completed_at=now,
            )
        )
        storage.runs[parent.id].status = RunStatus.COMPLETED
        storage.runs[parent.id].completed_at = now

        # Stage 1 with 2 briefs
        storage.create_stage_execution(
            StageExecution(
                run_id=parent.id,
                stage=StageType.OPPORTUNITY_FRAMING,
                status=StageStatus.COMPLETED,
                attempt_number=1,
                started_at=now,
                completed_at=now,
                artifacts={
                    "schema_version": 1,
                    "briefs": [_make_opportunity_brief(), _make_opportunity_brief()],
                    "framing_metadata": {"findings_processed": 5},
                },
            )
        )

        # Stage 2 with only 1 solution
        storage.create_stage_execution(
            StageExecution(
                run_id=parent.id,
                stage=StageType.SOLUTION_VALIDATION,
                status=StageStatus.COMPLETED,
                attempt_number=1,
                started_at=now,
                completed_at=now,
                artifacts={
                    "schema_version": 1,
                    "solutions": [_make_solution_brief()],
                    "design_metadata": {
                        "opportunity_briefs_processed": 1,
                        "solutions_produced": 1,
                        "total_dialogue_rounds": 1,
                        "total_token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                        "model": "gpt-4o-mini",
                    },
                },
            )
        )

        reentry = storage.create_run(
            DiscoveryRun(
                parent_run_id=parent.id,
                status=RunStatus.RUNNING,
                metadata=RunMetadata(
                    experiment_results=_valid_experiment_results()
                ),
            )
        )
        storage.runs[reentry.id].parent_run_id = parent.id

        # Index 0 should work (1 solution exists)
        ctx = svc.get_reentry_context(reentry.id, opportunity_index=0)
        assert ctx["original_solution_brief"] is not None

        # Index 1 should fail (only 1 solution)
        with pytest.raises(IndexError, match="out of bounds"):
            svc.get_reentry_context(reentry.id, opportunity_index=1)

    def test_run_not_found_raises(self):
        svc, storage = self._make_service()

        with pytest.raises(ValueError, match="not found"):
            svc.get_reentry_context(uuid4(), opportunity_index=0)


# ============================================================================
# SolutionDesigner: re-entry branch
# ============================================================================


class TestSolutionDesignerReentry:
    """SolutionDesigner uses SOLUTION_REENTRY prompts when experiment_results provided."""

    def _make_designer_with_mock(self):
        """Create a SolutionDesigner and return it with its mock PM client."""
        mock_client = MagicMock()
        mock_val_client = MagicMock()
        mock_exp_client = MagicMock()

        validation_agent = ValidationAgent(openai_client=mock_val_client)
        experience_agent = ExperienceAgent(openai_client=mock_exp_client)

        config = SolutionDesignerConfig(max_rounds=1)
        designer = SolutionDesigner(
            validation_agent=validation_agent,
            experience_agent=experience_agent,
            openai_client=mock_client,
            config=config,
        )

        return designer, mock_client, mock_val_client, mock_exp_client

    def test_reentry_uses_reentry_prompts(self):
        """When experiment_results provided, round 1 uses SOLUTION_REENTRY_SYSTEM."""
        designer, mock_client, mock_val_client, mock_exp_client = (
            self._make_designer_with_mock()
        )

        # PM response
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "proposed_solution": "Scale up the simplified wizard",
            "experiment_plan": "",
            "success_metrics": "Maintain 22% improvement at scale",
            "build_experiment_decision": "build_with_metrics",
            "decision_rationale": "Experiment met criteria — scale up",
            "evidence_ids": ["conv_001"],
            "confidence": "high",
            "reentry_action": "scale_up",
        })

        # Validation response (approve)
        mock_val_client.chat.completions.create.return_value = _make_llm_response({
            "assessment": "approve",
            "critique": "Experiment results are strong",
            "experiment_suggestion": "",
            "success_criteria": "22% sustained",
            "challenge_reason": "",
        })

        # Experience response
        mock_exp_client.chat.completions.create.return_value = _make_llm_response({
            "user_impact_level": "high",
            "experience_direction": "Roll out wizard redesign to all users",
            "engagement_depth": "full",
            "notes": "",
        })

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            experiment_results=_valid_experiment_results(),
            original_solution_brief=_make_solution_brief(),
        )

        # Verify PM was called with SOLUTION_REENTRY_SYSTEM
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        system_msg = messages[0]["content"]
        assert system_msg == SOLUTION_REENTRY_SYSTEM
        assert "reconvening" in system_msg.lower()

        # Verify result is valid
        assert result.proposed_solution == "Scale up the simplified wizard"
        assert result.dialogue_rounds == 1

    def test_without_experiment_results_uses_proposal_prompts(self):
        """Without experiment_results, round 1 uses SOLUTION_PROPOSAL_SYSTEM."""
        designer, mock_client, mock_val_client, mock_exp_client = (
            self._make_designer_with_mock()
        )

        mock_client.chat.completions.create.return_value = _make_llm_response({
            "proposed_solution": "Simplify scheduling wizard",
            "experiment_plan": "A/B test",
            "success_metrics": "15% improvement",
            "build_experiment_decision": "experiment_first",
            "decision_rationale": "Need validation first",
            "evidence_ids": ["conv_001"],
            "confidence": "medium",
        })

        mock_val_client.chat.completions.create.return_value = _make_llm_response({
            "assessment": "approve",
            "critique": "Sound approach",
            "experiment_suggestion": "A/B test",
            "success_criteria": "15% improvement",
            "challenge_reason": "",
        })

        mock_exp_client.chat.completions.create.return_value = _make_llm_response({
            "user_impact_level": "moderate",
            "experience_direction": "Streamline flow",
            "engagement_depth": "partial",
            "notes": "",
        })

        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
        )

        # Verify PM was called with SOLUTION_PROPOSAL_SYSTEM (not reentry)
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        system_msg = messages[0]["content"]
        assert system_msg == SOLUTION_PROPOSAL_SYSTEM
        assert "reconvening" not in system_msg.lower()

    def test_reentry_pm_missing_key_raises(self):
        """Re-entry PM response without proposed_solution raises ValueError."""
        designer, mock_client, mock_val_client, mock_exp_client = (
            self._make_designer_with_mock()
        )

        mock_client.chat.completions.create.return_value = _make_llm_response({
            "some_other_key": "no proposed_solution here",
        })

        with pytest.raises(ValueError, match="missing required 'proposed_solution'"):
            designer.design_solution(
                opportunity_brief=_make_opportunity_brief(),
                prior_checkpoints=[],
                experiment_results=_valid_experiment_results(),
                original_solution_brief=_make_solution_brief(),
            )

    def test_reentry_with_empty_original_brief(self):
        """Re-entry works even if original_solution_brief is empty dict."""
        designer, mock_client, mock_val_client, mock_exp_client = (
            self._make_designer_with_mock()
        )

        mock_client.chat.completions.create.return_value = _make_llm_response({
            "proposed_solution": "Revised approach based on experiment",
            "experiment_plan": "Follow-up test",
            "success_metrics": "10% improvement",
            "build_experiment_decision": "experiment_first",
            "decision_rationale": "Results were inconclusive",
            "evidence_ids": [],
            "confidence": "low",
            "reentry_action": "revise",
        })

        mock_val_client.chat.completions.create.return_value = _make_llm_response({
            "assessment": "approve",
            "critique": "Reasonable given inconclusive results",
            "experiment_suggestion": "Focused test",
            "success_criteria": "Clear signal",
            "challenge_reason": "",
        })

        mock_exp_client.chat.completions.create.return_value = _make_llm_response({
            "user_impact_level": "low",
            "experience_direction": "Minimal UX change",
            "engagement_depth": "minimal",
            "notes": "",
        })

        # Should not raise — empty original_solution_brief is valid
        result = designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            experiment_results=_valid_experiment_results(),
            original_solution_brief={},
        )

        assert result.proposed_solution == "Revised approach based on experiment"

    def test_reentry_user_prompt_includes_experiment_data(self):
        """The user prompt sent to LLM includes experiment results and original brief."""
        designer, mock_client, mock_val_client, mock_exp_client = (
            self._make_designer_with_mock()
        )

        mock_client.chat.completions.create.return_value = _make_llm_response({
            "proposed_solution": "Scale up",
            "experiment_plan": "",
            "success_metrics": "Maintain gains",
            "build_experiment_decision": "build_with_metrics",
            "decision_rationale": "Met criteria",
            "evidence_ids": [],
            "confidence": "high",
        })

        mock_val_client.chat.completions.create.return_value = _make_llm_response({
            "assessment": "approve",
            "critique": "Good",
            "experiment_suggestion": "",
            "success_criteria": "",
            "challenge_reason": "",
        })

        mock_exp_client.chat.completions.create.return_value = _make_llm_response({
            "user_impact_level": "high",
            "experience_direction": "Full rollout",
            "engagement_depth": "full",
            "notes": "",
        })

        experiment_results = _valid_experiment_results()
        original_brief = _make_solution_brief()

        designer.design_solution(
            opportunity_brief=_make_opportunity_brief(),
            prior_checkpoints=[],
            experiment_results=experiment_results,
            original_solution_brief=original_brief,
        )

        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_msg = messages[1]["content"]

        # User prompt should contain experiment results data
        assert "22% improvement" in user_msg
        assert "opp-001" in user_msg
        # And original solution brief data
        assert "Simplify scheduling wizard to 2 steps" in user_msg


# ============================================================================
# InMemoryStorage: get_child_runs
# ============================================================================


class TestGetChildRuns:
    """InMemoryStorage.get_child_runs returns child runs."""

    def test_returns_children(self):
        storage = InMemoryStorage()
        parent = _create_completed_parent_run(storage)

        child = storage.create_run(
            DiscoveryRun(
                parent_run_id=parent.id,
                status=RunStatus.RUNNING,
            )
        )
        storage.runs[child.id].parent_run_id = parent.id

        children = storage.get_child_runs(parent.id)
        assert len(children) == 1
        assert children[0].id == child.id

    def test_returns_empty_for_no_children(self):
        storage = InMemoryStorage()
        parent = _create_completed_parent_run(storage)

        children = storage.get_child_runs(parent.id)
        assert children == []
