"""Discovery Engine API Endpoints.

Review interface for the discovery pipeline. Lists runs, shows ranked
opportunities with full artifact chains, and accepts review decisions.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import get_db
from src.api.services.discovery_service import DiscoveryApiService
from src.discovery.db.storage import DiscoveryStorage
from src.discovery.models.artifacts import ReviewDecision
from src.discovery.models.enums import ReviewDecisionType

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


def get_discovery_service(db=Depends(get_db)) -> DiscoveryApiService:
    """Dependency for DiscoveryApiService."""
    return DiscoveryApiService(DiscoveryStorage(db))


class ReviewDecisionRequest(BaseModel):
    """Request body for submitting a review decision."""

    decision: ReviewDecisionType
    reasoning: str = Field(min_length=1)
    adjusted_priority: Optional[int] = Field(default=None, ge=1)
    send_back_to_stage: Optional[str] = Field(default=None, min_length=1)


@router.get("/runs")
def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    service: DiscoveryApiService = Depends(get_discovery_service),
):
    """List discovery runs with summary stats."""
    return service.list_runs(limit=limit)


@router.get("/runs/{run_id}")
def get_run(
    run_id: UUID,
    service: DiscoveryApiService = Depends(get_discovery_service),
):
    """Get full run detail including stages."""
    result = service.get_run_detail(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return result


@router.get("/runs/{run_id}/opportunities")
def get_opportunities(
    run_id: UUID,
    service: DiscoveryApiService = Depends(get_discovery_service),
):
    """Get ranked opportunity list for a run."""
    result = service.get_opportunities(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return result


@router.get("/runs/{run_id}/opportunities/{idx}")
def get_opportunity_detail(
    run_id: UUID,
    idx: int,
    service: DiscoveryApiService = Depends(get_discovery_service),
):
    """Get full artifact chain for a single opportunity."""
    result = service.get_opportunity_detail(run_id, idx)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity {idx} not found in run {run_id}",
        )
    return result


@router.post("/runs/{run_id}/opportunities/{idx}/decide")
def submit_decision(
    run_id: UUID,
    idx: int,
    body: ReviewDecisionRequest,
    service: DiscoveryApiService = Depends(get_discovery_service),
):
    """Submit a review decision for an opportunity.

    Validates conditional fields via Pydantic (ReviewDecision model_validator).
    Returns the saved decision.
    """
    # Validate conditional fields by constructing ReviewDecision
    # This triggers the model_validator that enforces adjusted_priority / send_back_to_stage rules
    try:
        ReviewDecision(
            opportunity_id="validation_placeholder",
            decision=body.decision,
            reasoning=body.reasoning,
            adjusted_priority=body.adjusted_priority,
            send_back_to_stage=body.send_back_to_stage,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        result = service.submit_decision(
            run_id,
            idx,
            {
                "decision": body.decision.value,
                "reasoning": body.reasoning,
                "adjusted_priority": body.adjusted_priority,
                "send_back_to_stage": body.send_back_to_stage,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity {idx} not found in run {run_id}",
        )
    return result


@router.post("/runs/{run_id}/complete")
def complete_run(
    run_id: UUID,
    service: DiscoveryApiService = Depends(get_discovery_service),
):
    """Complete a run after human review.

    Separate from submitting individual decisions — the reviewer decides
    when they're done reviewing.
    """
    try:
        result = service.complete_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return result
