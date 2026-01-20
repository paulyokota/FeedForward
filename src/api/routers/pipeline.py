"""
Pipeline Control Endpoints

Start, monitor, and manage pipeline execution.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from src.api.deps import get_db
from src.api.schemas.pipeline import (
    PipelineRunListItem,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatus,
    PipelineStopResponse,
)
from src.db.connection import create_pipeline_run, update_pipeline_run
from src.db.models import PipelineRun


router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Track active runs (in-memory for MVP, could use Redis for production)
_active_runs: dict[int, str] = {}  # run_id -> status


def _is_stopping(run_id: int) -> bool:
    """Check if the run has been requested to stop."""
    return _active_runs.get(run_id) == "stopping"


def _run_pipeline_task(run_id: int, days: int, max_conversations: Optional[int], dry_run: bool, concurrency: int):
    """
    Background task to execute the pipeline.

    Updates the pipeline_runs table with progress and results.
    Checks for stop signal and exits gracefully if stopping.
    """
    import asyncio
    from src.db.connection import get_connection
    from src.two_stage_pipeline import run_pipeline_async

    _active_runs[run_id] = "running"

    try:
        # Check for stop signal before starting
        if _is_stopping(run_id):
            _finalize_stopped_run(run_id, {"fetched": 0, "filtered": 0, "classified": 0, "stored": 0})
            return

        # Run the async pipeline in a new event loop
        # Pass stop checker so pipeline can exit gracefully
        result = asyncio.run(run_pipeline_async(
            days=days,
            max_conversations=max_conversations,
            dry_run=dry_run,
            concurrency=concurrency,
            stop_checker=lambda: _is_stopping(run_id),
        ))

        # Check if stopped during execution
        if _is_stopping(run_id):
            _finalize_stopped_run(run_id, result)
            return

        # Update pipeline run record with results
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        completed_at = %s,
                        conversations_fetched = %s,
                        conversations_filtered = %s,
                        conversations_classified = %s,
                        conversations_stored = %s,
                        status = 'completed'
                    WHERE id = %s
                """, (
                    datetime.utcnow(),
                    result.get("fetched", 0),
                    result.get("filtered", 0),
                    result.get("classified", 0),
                    result.get("stored", 0),
                    run_id,
                ))

        _active_runs[run_id] = "completed"

    except Exception as e:
        # Update with error
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        completed_at = %s,
                        status = 'failed',
                        error_message = %s
                    WHERE id = %s
                """, (datetime.utcnow(), str(e), run_id))

        _active_runs[run_id] = "failed"
        raise


def _finalize_stopped_run(run_id: int, result: dict):
    """Finalize a run that was stopped gracefully."""
    from src.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pipeline_runs SET
                    completed_at = %s,
                    conversations_fetched = %s,
                    conversations_filtered = %s,
                    conversations_classified = %s,
                    conversations_stored = %s,
                    status = 'stopped'
                WHERE id = %s
            """, (
                datetime.utcnow(),
                result.get("fetched", 0),
                result.get("filtered", 0),
                result.get("classified", 0),
                result.get("stored", 0),
                run_id,
            ))

    _active_runs[run_id] = "stopped"


@router.post("/run", response_model=PipelineRunResponse)
def start_pipeline_run(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """
    Start a new pipeline run.

    The pipeline executes in the background. Use GET /status/{run_id}
    to check progress.

    **Parameters:**
    - **days**: How far back to look for conversations (default 7)
    - **max_conversations**: Limit number processed (useful for testing)
    - **dry_run**: If True, classify but don't store to database
    - **concurrency**: Parallel API calls (default 20)
    """
    # Check if another run is already active
    active = [rid for rid, status in _active_runs.items() if status == "running"]
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline run {active[0]} is already in progress. Wait for it to complete."
        )

    # Calculate date range
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(days=request.days)

    # Create pipeline run record
    run = PipelineRun(
        started_at=datetime.utcnow(),
        date_from=date_from,
        date_to=date_to,
        status="running",
    )

    with db.cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_runs (started_at, date_from, date_to, status)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (run.started_at, run.date_from, run.date_to, run.status))
        run_id = cur.fetchone()["id"]

    # Start background task
    background_tasks.add_task(
        _run_pipeline_task,
        run_id=run_id,
        days=request.days,
        max_conversations=request.max_conversations,
        dry_run=request.dry_run,
        concurrency=request.concurrency,
    )

    return PipelineRunResponse(
        run_id=run_id,
        status="started",
        message=f"Pipeline run started. Processing last {request.days} days."
    )


@router.get("/status/{run_id}", response_model=PipelineStatus)
def get_pipeline_status(run_id: int, db=Depends(get_db)):
    """
    Get status of a specific pipeline run.

    Returns current progress including conversation counts.
    Poll this endpoint to track long-running pipelines.
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, started_at, completed_at, date_from, date_to,
                   conversations_fetched, conversations_filtered,
                   conversations_classified, conversations_stored,
                   status, error_message
            FROM pipeline_runs
            WHERE id = %s
        """, (run_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")

    # Calculate duration
    duration = None
    if row["completed_at"] and row["started_at"]:
        duration = (row["completed_at"] - row["started_at"]).total_seconds()
    elif row["started_at"]:
        duration = (datetime.utcnow() - row["started_at"]).total_seconds()

    return PipelineStatus(
        id=row["id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        date_from=row["date_from"],
        date_to=row["date_to"],
        conversations_fetched=row["conversations_fetched"] or 0,
        conversations_filtered=row["conversations_filtered"] or 0,
        conversations_classified=row["conversations_classified"] or 0,
        conversations_stored=row["conversations_stored"] or 0,
        status=row["status"],
        error_message=row["error_message"],
        duration_seconds=round(duration, 1) if duration else None,
    )


@router.get("/history", response_model=List[PipelineRunListItem])
def get_pipeline_history(
    db=Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Get list of recent pipeline runs.

    Returns runs ordered by start time (newest first).
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, started_at, completed_at,
                   conversations_fetched, conversations_classified, conversations_stored,
                   status
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        rows = cur.fetchall()

    results = []
    for row in rows:
        duration = None
        if row["completed_at"] and row["started_at"]:
            duration = (row["completed_at"] - row["started_at"]).total_seconds()

        results.append(PipelineRunListItem(
            id=row["id"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            status=row["status"],
            conversations_fetched=row["conversations_fetched"] or 0,
            conversations_classified=row["conversations_classified"] or 0,
            conversations_stored=row["conversations_stored"] or 0,
            duration_seconds=round(duration, 1) if duration else None,
        ))

    return results


@router.get("/active")
def get_active_runs():
    """
    Check if any pipeline run is currently active.

    Returns the run ID if active, or null if idle.
    """
    active = [rid for rid, status in _active_runs.items() if status == "running"]
    return {
        "active": bool(active),
        "run_id": active[0] if active else None,
    }


@router.post("/stop", response_model=PipelineStopResponse)
def stop_pipeline_run(db=Depends(get_db)):
    """
    Request graceful stop of the active pipeline run.

    Sets the run status to 'stopping'. The worker checks this status
    and exits gracefully after completing in-flight tasks.

    Returns:
    - **stopping**: Stop signal sent, worker will exit gracefully
    - **stopped**: Run was already stopped
    - **not_running**: No active run to stop
    """
    # Find active run
    active = [rid for rid, status in _active_runs.items() if status == "running"]

    if not active:
        return PipelineStopResponse(
            run_id=0,
            status="not_running",
            message="No active pipeline run to stop."
        )

    run_id = active[0]

    # Mark as stopping in memory
    _active_runs[run_id] = "stopping"

    # Update database status
    with db.cursor() as cur:
        cur.execute("""
            UPDATE pipeline_runs
            SET status = 'stopping'
            WHERE id = %s AND status = 'running'
        """, (run_id,))

    return PipelineStopResponse(
        run_id=run_id,
        status="stopping",
        message=f"Stop signal sent to pipeline run {run_id}. In-flight tasks will complete before stopping."
    )
