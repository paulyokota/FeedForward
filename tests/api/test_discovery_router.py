"""Discovery API Router + Service Tests.

Tests the DiscoveryApiService (cross-stage data assembly) and the
FastAPI router endpoints for the discovery review interface.

Run with: pytest tests/api/test_discovery_router.py -v
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import Mock
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers.discovery import get_discovery_service
from src.api.services.discovery_service import DiscoveryApiService
from src.discovery.models.enums import (
    ReviewDecisionType,
    RunStatus,
    StageStatus,
    StageType,
)
from src.discovery.models.run import DiscoveryRun, RunConfig, RunMetadata, StageExecution


# =============================================================================
# InMemoryStorage for service-layer tests
# =============================================================================


class InMemoryStorage:
    """Minimal in-memory storage for DiscoveryApiService testing."""

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

    def list_runs(
        self, status: Optional[RunStatus] = None, limit: int = 50
    ) -> List[DiscoveryRun]:
        runs = list(self.runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        runs.sort(
            key=lambda r: r.started_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return runs[:limit]

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
            artifacts=stage_exec.artifacts,
            conversation_id=stage_exec.conversation_id,
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


# =============================================================================
# Test data builders
# =============================================================================

NOW = datetime.now(timezone.utc)

SAMPLE_BRIEF = {
    "schema_version": 1,
    "problem_statement": "Users can't find the settings page",
    "evidence": [
        {
            "source_type": "intercom",
            "source_id": "conv_001",
            "retrieved_at": NOW.isoformat(),
            "confidence": "high",
        }
    ],
    "counterfactual": "If we add a settings shortcut, navigation complaints drop 40%",
    "affected_area": "navigation",
    "explorer_coverage": "100 intercom conversations reviewed",
}

SAMPLE_SOLUTION = {
    "schema_version": 1,
    "proposed_solution": "Add settings link to sidebar",
    "experiment_plan": "A/B test sidebar link vs current",
    "success_metrics": "Navigation complaints drop from 12/week to <5/week",
    "build_experiment_decision": "experiment_first",
    "evidence": [
        {
            "source_type": "intercom",
            "source_id": "conv_001",
            "retrieved_at": NOW.isoformat(),
            "confidence": "high",
        }
    ],
}

SAMPLE_SPEC = {
    "schema_version": 1,
    "opportunity_id": "navigation",
    "approach": "Add sidebar link with icon",
    "effort_estimate": "2-3 days",
    "dependencies": "Sidebar component refactor",
    "risks": [{"description": "Sidebar too crowded", "severity": "low", "mitigation": "Collapsible menu"}],
    "acceptance_criteria": "Link visible, navigates to settings",
}

SAMPLE_RANKING = {
    "opportunity_id": "navigation",
    "recommended_rank": 1,
    "rationale": "High impact, low effort",
    "dependencies": [],
    "flags": [],
}


def _build_completed_run(storage: InMemoryStorage) -> UUID:
    """Build a completed run with all 6 stage artifacts."""
    run = storage.create_run(
        DiscoveryRun(
            status=RunStatus.RUNNING,
            current_stage=StageType.HUMAN_REVIEW,
        )
    )
    run_id = run.id

    # Stage 0: Exploration
    storage.create_stage_execution(StageExecution(
        run_id=run_id,
        stage=StageType.EXPLORATION,
        status=StageStatus.COMPLETED,
        attempt_number=1,
        started_at=NOW,
        artifacts={
            "schema_version": 1,
            "agent_name": "customer_voice",
            "findings": [{"finding": "Users complain about settings"}],
            "coverage": {"documents_reviewed": 100, "documents_matched": 15, "source_type": "intercom"},
        },
    ))

    # Stage 1: Opportunity Framing
    storage.create_stage_execution(StageExecution(
        run_id=run_id,
        stage=StageType.OPPORTUNITY_FRAMING,
        status=StageStatus.COMPLETED,
        attempt_number=1,
        started_at=NOW,
        artifacts={
            "schema_version": 1,
            "briefs": [SAMPLE_BRIEF],
            "framing_metadata": {
                "explorer_findings_count": 5,
                "opportunities_identified": 1,
                "model": "gpt-4o-mini",
            },
        },
    ))

    # Stage 2: Solution Validation
    storage.create_stage_execution(StageExecution(
        run_id=run_id,
        stage=StageType.SOLUTION_VALIDATION,
        status=StageStatus.COMPLETED,
        attempt_number=1,
        started_at=NOW,
        artifacts={
            "schema_version": 1,
            "solutions": [SAMPLE_SOLUTION],
            "design_metadata": {
                "opportunity_briefs_processed": 1,
                "solutions_produced": 1,
                "total_dialogue_rounds": 3,
                "total_token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                "model": "gpt-4o-mini",
            },
        },
    ))

    # Stage 3: Feasibility + Risk
    storage.create_stage_execution(StageExecution(
        run_id=run_id,
        stage=StageType.FEASIBILITY_RISK,
        status=StageStatus.COMPLETED,
        attempt_number=1,
        started_at=NOW,
        artifacts={
            "schema_version": 1,
            "specs": [SAMPLE_SPEC],
            "infeasible": [],
            "feasibility_metadata": {
                "solutions_assessed": 1,
                "feasible_count": 1,
                "infeasible_count": 0,
                "model": "gpt-4o-mini",
            },
        },
    ))

    # Stage 4: Prioritization
    storage.create_stage_execution(StageExecution(
        run_id=run_id,
        stage=StageType.PRIORITIZATION,
        status=StageStatus.COMPLETED,
        attempt_number=1,
        started_at=NOW,
        artifacts={
            "schema_version": 1,
            "rankings": [SAMPLE_RANKING],
            "prioritization_metadata": {
                "opportunities_ranked": 1,
                "model": "gpt-4o-mini",
            },
        },
    ))

    # Stage 5: Human Review (in progress, no artifacts yet)
    storage.create_stage_execution(StageExecution(
        run_id=run_id,
        stage=StageType.HUMAN_REVIEW,
        status=StageStatus.IN_PROGRESS,
        attempt_number=1,
        started_at=NOW,
    ))

    return run_id


# =============================================================================
# Service layer tests
# =============================================================================


class TestDiscoveryApiServiceListRuns:
    def test_list_runs_returns_correct_format(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)

        result = service.list_runs()
        assert len(result) == 1
        r = result[0]
        assert r["id"] == str(run_id)
        assert r["status"] == "running"
        assert r["opportunity_count"] == 1
        assert r["stages_completed"] >= 4  # stages 0-4 completed

    def test_list_runs_empty(self):
        storage = InMemoryStorage()
        service = DiscoveryApiService(storage)
        assert service.list_runs() == []


class TestDiscoveryApiServiceRunDetail:
    def test_get_run_detail(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)

        result = service.get_run_detail(run_id)
        assert result is not None
        assert result["id"] == str(run_id)
        assert len(result["stages"]) == 6

    def test_get_run_detail_not_found(self):
        storage = InMemoryStorage()
        service = DiscoveryApiService(storage)
        assert service.get_run_detail(uuid4()) is None


class TestDiscoveryApiServiceOpportunities:
    def test_get_opportunities_ranked_list(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)

        result = service.get_opportunities(run_id)
        assert result is not None
        assert len(result) == 1

        opp = result[0]
        assert opp["index"] == 0
        assert opp["opportunity_id"] == "navigation"
        assert opp["problem_statement"] == "Users can't find the settings page"
        assert opp["recommended_rank"] == 1
        assert opp["build_experiment_decision"] == "experiment_first"
        assert opp["evidence_count"] == 1
        assert opp["review_status"] is None  # not yet reviewed

    def test_get_opportunities_not_found(self):
        storage = InMemoryStorage()
        service = DiscoveryApiService(storage)
        assert service.get_opportunities(uuid4()) is None

    def test_get_opportunities_no_prioritization(self):
        """Run without completed Stage 4 returns empty list."""
        storage = InMemoryStorage()
        run = storage.create_run(DiscoveryRun(status=RunStatus.RUNNING))
        service = DiscoveryApiService(storage)
        assert service.get_opportunities(run.id) == []

    def test_get_opportunities_reordered_rankings(self):
        """Rankings in different order from briefs still map correctly."""
        storage = InMemoryStorage()
        run = storage.create_run(DiscoveryRun(
            status=RunStatus.RUNNING,
            current_stage=StageType.HUMAN_REVIEW,
        ))
        run_id = run.id

        brief_a = {**SAMPLE_BRIEF, "affected_area": "checkout", "problem_statement": "Checkout is slow"}
        brief_b = {**SAMPLE_BRIEF, "affected_area": "navigation", "problem_statement": "Users can't find the settings page"}

        solution_a = {**SAMPLE_SOLUTION, "proposed_solution": "Optimize checkout API"}
        solution_b = {**SAMPLE_SOLUTION, "proposed_solution": "Add settings link to sidebar"}

        # Stage 1: briefs in order [checkout, navigation]
        storage.create_stage_execution(StageExecution(
            run_id=run_id, stage=StageType.OPPORTUNITY_FRAMING,
            status=StageStatus.COMPLETED, attempt_number=1, started_at=NOW,
            artifacts={"schema_version": 1, "briefs": [brief_a, brief_b],
                       "framing_metadata": {"explorer_findings_count": 5, "opportunities_identified": 2, "model": "gpt-4o-mini"}},
        ))

        # Stage 2: solutions in same order [checkout, navigation]
        storage.create_stage_execution(StageExecution(
            run_id=run_id, stage=StageType.SOLUTION_VALIDATION,
            status=StageStatus.COMPLETED, attempt_number=1, started_at=NOW,
            artifacts={"schema_version": 1, "solutions": [solution_a, solution_b],
                       "design_metadata": {"opportunity_briefs_processed": 2, "solutions_produced": 2,
                                           "total_dialogue_rounds": 3, "total_token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "model": "gpt-4o-mini"}},
        ))

        # Stage 4: rankings REORDERED — navigation first, checkout second
        storage.create_stage_execution(StageExecution(
            run_id=run_id, stage=StageType.PRIORITIZATION,
            status=StageStatus.COMPLETED, attempt_number=1, started_at=NOW,
            artifacts={"schema_version": 1, "rankings": [
                {"opportunity_id": "navigation", "recommended_rank": 1, "rationale": "Higher impact", "dependencies": [], "flags": []},
                {"opportunity_id": "checkout", "recommended_rank": 2, "rationale": "Lower priority", "dependencies": [], "flags": []},
            ], "prioritization_metadata": {"opportunities_ranked": 2, "model": "gpt-4o-mini"}},
        ))

        # Stage 5: human review
        storage.create_stage_execution(StageExecution(
            run_id=run_id, stage=StageType.HUMAN_REVIEW,
            status=StageStatus.IN_PROGRESS, attempt_number=1, started_at=NOW,
        ))

        service = DiscoveryApiService(storage)
        result = service.get_opportunities(run_id)
        assert len(result) == 2

        # Rank 1 (index 0) should be navigation, not checkout
        assert result[0]["opportunity_id"] == "navigation"
        assert result[0]["problem_statement"] == "Users can't find the settings page"
        assert result[0]["build_experiment_decision"] == "experiment_first"  # from solution_b

        # Rank 2 (index 1) should be checkout
        assert result[1]["opportunity_id"] == "checkout"
        assert result[1]["problem_statement"] == "Checkout is slow"

    def test_get_opportunities_with_review_status(self):
        """Opportunities that have been reviewed show the decision type."""
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)

        # Add a decision to the HUMAN_REVIEW stage
        for se in storage.stage_executions.values():
            if se.run_id == run_id and se.stage == StageType.HUMAN_REVIEW:
                se.artifacts = {
                    "schema_version": 1,
                    "decisions": [{
                        "opportunity_id": "navigation",
                        "decision": "accepted",
                        "reasoning": "Good opportunity",
                    }],
                    "review_metadata": {"reviewer": "tester", "opportunities_reviewed": 1},
                }
                break

        service = DiscoveryApiService(storage)
        result = service.get_opportunities(run_id)
        assert result[0]["review_status"] == "accepted"


class TestDiscoveryApiServiceOpportunityDetail:
    def test_get_opportunity_detail_full_chain(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)

        result = service.get_opportunity_detail(run_id, 0)
        assert result is not None
        assert result["index"] == 0
        assert result["exploration"] is not None
        assert result["opportunity_brief"]["problem_statement"] == "Users can't find the settings page"
        assert result["solution_brief"]["proposed_solution"] == "Add settings link to sidebar"
        assert result["tech_spec"]["approach"] == "Add sidebar link with icon"
        assert result["priority_rationale"]["recommended_rank"] == 1
        assert result["review_decision"] is None  # not yet decided

    def test_get_opportunity_detail_not_found_run(self):
        storage = InMemoryStorage()
        service = DiscoveryApiService(storage)
        assert service.get_opportunity_detail(uuid4(), 0) is None

    def test_get_opportunity_detail_out_of_bounds(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)
        assert service.get_opportunity_detail(run_id, 99) is None

    def test_get_opportunity_detail_negative_index(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)
        assert service.get_opportunity_detail(run_id, -1) is None


class TestDiscoveryApiServiceSubmitDecision:
    def test_submit_decision_accepted(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)

        result = service.submit_decision(run_id, 0, {
            "decision": "accepted",
            "reasoning": "Looks good",
        })
        assert result is not None
        assert result["opportunity_id"] == "navigation"
        assert result["decision"] == "accepted"

    def test_submit_decision_replaces_existing(self):
        """Last-write-wins for the same opportunity."""
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)

        service.submit_decision(run_id, 0, {"decision": "deferred", "reasoning": "Need more data"})
        result = service.submit_decision(run_id, 0, {"decision": "accepted", "reasoning": "Changed mind"})

        assert result["decision"] == "accepted"

        # Verify only one decision stored
        for se in storage.stage_executions.values():
            if se.run_id == run_id and se.stage == StageType.HUMAN_REVIEW:
                assert len(se.artifacts["decisions"]) == 1
                break

    def test_submit_decision_run_not_found(self):
        storage = InMemoryStorage()
        service = DiscoveryApiService(storage)
        assert service.submit_decision(uuid4(), 0, {"decision": "accepted", "reasoning": "ok"}) is None

    def test_submit_decision_idx_out_of_bounds(self):
        storage = InMemoryStorage()
        run_id = _build_completed_run(storage)
        service = DiscoveryApiService(storage)
        assert service.submit_decision(run_id, 99, {"decision": "accepted", "reasoning": "ok"}) is None

    def test_submit_decision_no_hr_stage_raises(self):
        """Run not at human_review stage raises ValueError."""
        storage = InMemoryStorage()
        run = storage.create_run(DiscoveryRun(status=RunStatus.RUNNING))
        # Add only Stage 4 so idx resolves but no HR stage
        storage.create_stage_execution(StageExecution(
            run_id=run.id,
            stage=StageType.PRIORITIZATION,
            status=StageStatus.COMPLETED,
            attempt_number=1,
            started_at=NOW,
            artifacts={
                "schema_version": 1,
                "rankings": [SAMPLE_RANKING],
                "prioritization_metadata": {"opportunities_ranked": 1, "model": "gpt-4o-mini"},
            },
        ))
        service = DiscoveryApiService(storage)
        with pytest.raises(ValueError, match="No active human_review"):
            service.submit_decision(run.id, 0, {"decision": "accepted", "reasoning": "ok"})


# =============================================================================
# Router integration tests (FastAPI TestClient)
# =============================================================================


@pytest.fixture
def mock_service():
    return Mock(spec=DiscoveryApiService)


@pytest.fixture
def client(mock_service):
    app.dependency_overrides[get_discovery_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestDiscoveryRouterListRuns:
    def test_list_runs_ok(self, client, mock_service):
        mock_service.list_runs.return_value = [
            {"id": str(uuid4()), "status": "running", "opportunity_count": 2, "stages_completed": 3}
        ]
        resp = client.get("/api/discovery/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "running"

    def test_list_runs_with_limit(self, client, mock_service):
        mock_service.list_runs.return_value = []
        resp = client.get("/api/discovery/runs?limit=10")
        assert resp.status_code == 200
        mock_service.list_runs.assert_called_once_with(limit=10)


class TestDiscoveryRouterGetRun:
    def test_get_run_ok(self, client, mock_service):
        run_id = uuid4()
        mock_service.get_run_detail.return_value = {"id": str(run_id), "status": "completed", "stages": []}
        resp = client.get(f"/api/discovery/runs/{run_id}")
        assert resp.status_code == 200

    def test_get_run_not_found(self, client, mock_service):
        mock_service.get_run_detail.return_value = None
        resp = client.get(f"/api/discovery/runs/{uuid4()}")
        assert resp.status_code == 404


class TestDiscoveryRouterGetOpportunities:
    def test_get_opportunities_ok(self, client, mock_service):
        run_id = uuid4()
        mock_service.get_opportunities.return_value = [
            {"index": 0, "problem_statement": "test", "review_status": None}
        ]
        resp = client.get(f"/api/discovery/runs/{run_id}/opportunities")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_opportunities_not_found(self, client, mock_service):
        mock_service.get_opportunities.return_value = None
        resp = client.get(f"/api/discovery/runs/{uuid4()}/opportunities")
        assert resp.status_code == 404


class TestDiscoveryRouterGetOpportunityDetail:
    def test_get_detail_ok(self, client, mock_service):
        run_id = uuid4()
        mock_service.get_opportunity_detail.return_value = {"index": 0, "exploration": {}}
        resp = client.get(f"/api/discovery/runs/{run_id}/opportunities/0")
        assert resp.status_code == 200

    def test_get_detail_not_found(self, client, mock_service):
        mock_service.get_opportunity_detail.return_value = None
        resp = client.get(f"/api/discovery/runs/{uuid4()}/opportunities/0")
        assert resp.status_code == 404


class TestDiscoveryRouterSubmitDecision:
    def test_submit_accepted(self, client, mock_service):
        run_id = uuid4()
        mock_service.submit_decision.return_value = {
            "opportunity_id": "opp_1",
            "decision": "accepted",
            "reasoning": "Good",
        }
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "accepted", "reasoning": "Good"},
        )
        assert resp.status_code == 200

    def test_submit_missing_reasoning_422(self, client, mock_service):
        run_id = uuid4()
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "accepted", "reasoning": ""},
        )
        assert resp.status_code == 422

    def test_submit_priority_adjusted_requires_adjusted_priority(self, client, mock_service):
        run_id = uuid4()
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "priority_adjusted", "reasoning": "Needs bump"},
        )
        assert resp.status_code == 422

    def test_submit_sent_back_requires_stage(self, client, mock_service):
        run_id = uuid4()
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "sent_back", "reasoning": "Needs rework"},
        )
        assert resp.status_code == 422

    def test_submit_invalid_decision_type(self, client, mock_service):
        run_id = uuid4()
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "invalid_type", "reasoning": "Whatever"},
        )
        assert resp.status_code == 422

    def test_submit_not_found(self, client, mock_service):
        mock_service.submit_decision.return_value = None
        run_id = uuid4()
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "accepted", "reasoning": "Good"},
        )
        assert resp.status_code == 404

    def test_submit_no_hr_stage_409(self, client, mock_service):
        mock_service.submit_decision.side_effect = ValueError("No active human_review")
        run_id = uuid4()
        resp = client.post(
            f"/api/discovery/runs/{run_id}/opportunities/0/decide",
            json={"decision": "accepted", "reasoning": "Good"},
        )
        assert resp.status_code == 409


class TestDiscoveryRouterCompleteRun:
    def test_complete_run_ok(self, client, mock_service):
        run_id = uuid4()
        mock_service.complete_run.return_value = {"id": str(run_id), "status": "completed"}
        resp = client.post(f"/api/discovery/runs/{run_id}/complete")
        assert resp.status_code == 200

    def test_complete_run_not_found(self, client, mock_service):
        mock_service.complete_run.return_value = None
        resp = client.post(f"/api/discovery/runs/{uuid4()}/complete")
        assert resp.status_code == 404

    def test_complete_run_not_ready_409(self, client, mock_service):
        mock_service.complete_run.side_effect = ValueError("Not at human_review")
        resp = client.post(f"/api/discovery/runs/{uuid4()}/complete")
        assert resp.status_code == 409
