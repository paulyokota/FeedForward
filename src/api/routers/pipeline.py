"""
Pipeline Control Endpoints

Start, monitor, and manage pipeline execution.
Supports hybrid pipeline with classification, theme extraction, and story creation phases.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from src.api.deps import get_db
from src.api.schemas.pipeline import (
    CreateStoriesResponse,
    PipelineRunListItem,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatus,
    PipelineStopResponse,
)
from src.db.connection import create_pipeline_run, update_pipeline_run
from src.db.models import PipelineRun

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Track active runs (in-memory for MVP, could use Redis for production)
# States: running, stopping, stopped, completed, failed
_active_runs: dict[int, str] = {}  # run_id -> status

# Terminal states that can be cleaned up
_TERMINAL_STATES = {"stopped", "completed", "failed"}

# Minimum conversations needed to create a full story (vs orphan)
# Based on product decision: fewer than 3 reports indicates insufficient signal
MIN_CONVERSATIONS_FOR_STORY = 3


def _cleanup_terminal_runs() -> None:
    """Remove terminal (completed/failed/stopped) runs to prevent memory leak."""
    terminal_ids = [rid for rid, status in _active_runs.items() if status in _TERMINAL_STATES]
    for rid in terminal_ids:
        del _active_runs[rid]


def _is_stopping(run_id: int) -> bool:
    """Check if the run has been requested to stop."""
    return _active_runs.get(run_id) == "stopping"


# Whitelist of allowed fields for _update_phase to prevent SQL injection
_ALLOWED_PHASE_FIELDS = frozenset({
    "themes_extracted", "themes_new", "stories_created", "orphans_created",
    "stories_ready", "auto_create_stories", "conversations_fetched",
    "conversations_classified", "conversations_stored", "conversations_filtered",
})


def _update_phase(run_id: int, phase: str, **extra_fields) -> None:
    """Update the current phase in database. Called before starting each phase."""
    from src.db.connection import get_connection

    # Validate field names against whitelist to prevent SQL injection
    for field in extra_fields:
        if field not in _ALLOWED_PHASE_FIELDS:
            raise ValueError(f"Invalid field for phase update: {field}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Build dynamic update
            set_clause = "current_phase = %s"
            values = [phase]

            for field, value in extra_fields.items():
                set_clause += f", {field} = %s"
                values.append(value)

            values.append(run_id)
            cur.execute(f"""
                UPDATE pipeline_runs SET {set_clause}
                WHERE id = %s
            """, values)

    logger.info(f"Run {run_id}: Phase updated to '{phase}'")


def _run_theme_extraction(run_id: int, stop_checker: Callable[[], bool]) -> dict:
    """
    Run theme extraction on classified conversations from this pipeline run.

    Returns dict with themes_extracted, themes_new counts.
    """
    from src.db.connection import get_connection
    from src.theme_extractor import ThemeExtractor
    from src.db.models import Conversation

    logger.info(f"Run {run_id}: Starting theme extraction")

    # Get conversations classified in this run
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get conversations from the date range of this run
            cur.execute("""
                SELECT c.id, c.created_at, c.source_body, c.source_url,
                       c.issue_type, c.sentiment, c.priority, c.churn_risk
                FROM conversations c
                JOIN pipeline_runs pr ON c.classified_at >= pr.started_at
                WHERE pr.id = %s
                  AND c.issue_type IN ('bug_report', 'feature_request', 'product_question')
                ORDER BY c.created_at DESC
            """, (run_id,))
            rows = cur.fetchall()

    if not rows:
        logger.info(f"Run {run_id}: No actionable conversations to extract themes from")
        return {"themes_extracted": 0, "themes_new": 0}

    # Convert to Conversation objects
    conversations = []
    for row in rows:
        if stop_checker():
            logger.info(f"Run {run_id}: Stop signal received during theme extraction")
            return {"themes_extracted": 0, "themes_new": 0}

        conv = Conversation(
            id=row["id"],
            created_at=row["created_at"],
            source_body=row["source_body"],
            source_url=row.get("source_url"),
            issue_type=row["issue_type"],
            sentiment=row["sentiment"],
            priority=row["priority"],
            churn_risk=row["churn_risk"],
        )
        conversations.append(conv)

    logger.info(f"Run {run_id}: Extracting themes from {len(conversations)} conversations")

    # Extract themes
    extractor = ThemeExtractor()
    themes = []
    themes_new = 0

    for conv in conversations:
        if stop_checker():
            logger.info(f"Run {run_id}: Stop signal received during theme extraction")
            break

        try:
            theme = extractor.extract(conv, strict_mode=True)
            themes.append(theme)

            # Track if new theme was created
            if not theme.issue_signature.startswith("unclassified"):
                # Check if this is a known theme
                existing = extractor.get_existing_signatures(theme.product_area)
                is_new = not any(
                    s["signature"] == theme.issue_signature for s in existing
                )
                if is_new:
                    themes_new += 1

            logger.debug(f"Extracted theme: {theme.issue_signature} for conv {conv.id}")

        except Exception as e:
            logger.warning(f"Failed to extract theme for {conv.id}: {e}")

    # Store themes in database with pipeline_run_id
    with get_connection() as conn:
        with conn.cursor() as cur:
            for theme in themes:
                cur.execute("""
                    INSERT INTO themes (
                        conversation_id, product_area, component, issue_signature,
                        user_intent, symptoms, affected_flow, root_cause_hypothesis,
                        pipeline_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (conversation_id) DO UPDATE SET
                        product_area = EXCLUDED.product_area,
                        component = EXCLUDED.component,
                        issue_signature = EXCLUDED.issue_signature,
                        user_intent = EXCLUDED.user_intent,
                        symptoms = EXCLUDED.symptoms,
                        affected_flow = EXCLUDED.affected_flow,
                        root_cause_hypothesis = EXCLUDED.root_cause_hypothesis,
                        pipeline_run_id = EXCLUDED.pipeline_run_id,
                        extracted_at = NOW()
                """, (
                    theme.conversation_id,
                    theme.product_area,
                    theme.component,
                    theme.issue_signature,
                    theme.user_intent,
                    theme.symptoms,
                    theme.affected_flow,
                    theme.root_cause_hypothesis,
                    run_id,
                ))

    logger.info(f"Run {run_id}: Extracted {len(themes)} themes ({themes_new} new)")
    return {"themes_extracted": len(themes), "themes_new": themes_new}


def _run_pm_review_and_story_creation(run_id: int, stop_checker: Callable[[], bool]) -> dict:
    """
    Run PM review on theme groups and create stories.

    Returns dict with stories_created, orphans_created counts.
    """
    import json
    import os
    from openai import OpenAI
    from src.db.connection import get_connection
    from src.story_tracking.services.story_service import StoryService
    from src.story_tracking.services.evidence_service import EvidenceService
    from src.story_tracking.services.pipeline_integration import (
        PipelineIntegrationService,
        ValidatedGroup,
    )

    logger.info(f"Run {run_id}: Starting PM review and story creation")

    # Get themes from this run grouped by signature
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.issue_signature, t.product_area, t.component,
                       t.conversation_id, t.user_intent, t.symptoms,
                       t.affected_flow, c.source_body
                FROM themes t
                JOIN conversations c ON t.conversation_id = c.id
                WHERE t.pipeline_run_id = %s
                  AND t.issue_signature != 'unclassified_needs_review'
                ORDER BY t.issue_signature
            """, (run_id,))
            rows = cur.fetchall()

    if not rows:
        logger.info(f"Run {run_id}: No themes to create stories from")
        return {"stories_created": 0, "orphans_created": 0}

    # Group by signature
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["issue_signature"]].append({
            "id": row["conversation_id"],
            "product_area": row["product_area"],
            "component": row["component"],
            "user_intent": row["user_intent"],
            "symptoms": row["symptoms"],
            "affected_flow": row["affected_flow"],
            "excerpt": (row["source_body"] or "")[:500],
        })

    # Filter to groups with sufficient conversations (story-worthy)
    valid_groups = {
        sig: convs for sig, convs in groups.items()
        if len(convs) >= MIN_CONVERSATIONS_FOR_STORY
    }
    orphan_groups = {
        sig: convs for sig, convs in groups.items()
        if len(convs) < MIN_CONVERSATIONS_FOR_STORY
    }

    logger.info(
        f"Run {run_id}: {len(valid_groups)} valid groups, "
        f"{len(orphan_groups)} orphan groups"
    )

    if stop_checker():
        return {"stories_created": 0, "orphans_created": 0}

    # Initialize services
    with get_connection() as conn:
        story_service = StoryService(conn)
        evidence_service = EvidenceService(conn)
        integration_service = PipelineIntegrationService(story_service, evidence_service)

        stories_created = 0
        orphans_created = 0

        # Create stories for valid groups
        for signature, conversations in valid_groups.items():
            if stop_checker():
                break

            try:
                # Create validated group
                product_area = conversations[0]["product_area"]
                component = conversations[0]["component"]

                # Generate title from signature
                title = signature.replace("_", " ").title()

                # Combine intents for description
                intents = list(set(c["user_intent"] for c in conversations if c["user_intent"]))
                description = f"Users experiencing: {'; '.join(intents[:3])}"

                group = ValidatedGroup(
                    signature=signature,
                    conversation_ids=[c["id"] for c in conversations],
                    theme_signatures=[signature],
                    title=title,
                    description=description,
                    product_area=product_area,
                    technical_area=component,
                    excerpts=[
                        {"text": c["excerpt"], "source": "intercom", "conversation_id": c["id"]}
                        for c in conversations[:5]
                    ],
                )

                story = integration_service.create_candidate_story(group)
                stories_created += 1
                logger.info(f"Created story: {story.title}")

                # Link story to pipeline run
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE stories SET pipeline_run_id = %s WHERE id = %s
                    """, (run_id, str(story.id)))

            except Exception as e:
                logger.warning(f"Failed to create story for {signature}: {e}")

        # Create orphan stories (for groups < 3 conversations)
        for signature, conversations in orphan_groups.items():
            if stop_checker():
                break

            try:
                product_area = conversations[0]["product_area"]
                title = f"[Orphan] {signature.replace('_', ' ').title()}"
                description = f"Low-volume theme ({len(conversations)} reports). May merge with similar themes."

                group = ValidatedGroup(
                    signature=signature,
                    conversation_ids=[c["id"] for c in conversations],
                    theme_signatures=[signature],
                    title=title,
                    description=description,
                    product_area=product_area,
                    technical_area=conversations[0]["component"],
                    confidence_score=30.0,  # Low confidence for orphans
                )

                story = integration_service.create_candidate_story(group)
                orphans_created += 1

                # Link to pipeline run
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE stories SET pipeline_run_id = %s WHERE id = %s
                    """, (run_id, str(story.id)))

            except Exception as e:
                logger.warning(f"Failed to create orphan story for {signature}: {e}")

    logger.info(
        f"Run {run_id}: Created {stories_created} stories, {orphans_created} orphans"
    )
    return {"stories_created": stories_created, "orphans_created": orphans_created}


def _run_pipeline_task(
    run_id: int,
    days: int,
    max_conversations: Optional[int],
    dry_run: bool,
    concurrency: int,
    auto_create_stories: bool = False,
):
    """
    Background task to execute the hybrid pipeline.

    Phases:
    1. Classification - Fetch and classify conversations
    2. Theme Extraction - Extract themes from actionable conversations
    3. (Optional) PM Review + Story Creation - Create stories from theme groups

    Updates the pipeline_runs table with progress and results.
    Checks for stop signal between phases and exits gracefully if stopping.
    """
    import asyncio
    from src.db.connection import get_connection
    from src.two_stage_pipeline import run_pipeline_async

    _active_runs[run_id] = "running"
    stop_checker = lambda: _is_stopping(run_id)

    # Track results across phases
    result = {"fetched": 0, "filtered": 0, "classified": 0, "stored": 0}
    theme_result = {"themes_extracted": 0, "themes_new": 0}
    story_result = {"stories_created": 0, "orphans_created": 0}

    try:
        # ==== PHASE 1: Classification ====
        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result)
            return

        _update_phase(run_id, "classification")

        # Run the async classification pipeline
        result = asyncio.run(run_pipeline_async(
            days=days,
            max_conversations=max_conversations,
            dry_run=dry_run,
            concurrency=concurrency,
            stop_checker=stop_checker,
        ))

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result)
            return

        # Update classification results
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        conversations_fetched = %s,
                        conversations_filtered = %s,
                        conversations_classified = %s,
                        conversations_stored = %s
                    WHERE id = %s
                """, (
                    result.get("fetched", 0),
                    result.get("filtered", 0),
                    result.get("classified", 0),
                    result.get("stored", 0),
                    run_id,
                ))

        # Skip subsequent phases if dry run or no conversations stored
        if dry_run or result.get("stored", 0) == 0:
            logger.info(f"Run {run_id}: Skipping theme extraction (dry_run={dry_run}, stored={result.get('stored', 0)})")
            _finalize_completed_run(run_id, result, theme_result, story_result)
            return

        # ==== PHASE 2: Theme Extraction ====
        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result)
            return

        _update_phase(run_id, "theme_extraction")

        theme_result = _run_theme_extraction(run_id, stop_checker)

        # Update theme extraction results
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        themes_extracted = %s,
                        themes_new = %s,
                        stories_ready = TRUE
                    WHERE id = %s
                """, (
                    theme_result.get("themes_extracted", 0),
                    theme_result.get("themes_new", 0),
                    run_id,
                ))

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result)
            return

        # ==== PHASE 3: PM Review + Story Creation (optional) ====
        if auto_create_stories and theme_result.get("themes_extracted", 0) > 0:
            _update_phase(run_id, "story_creation")

            story_result = _run_pm_review_and_story_creation(run_id, stop_checker)

            # Update story creation results
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE pipeline_runs SET
                            stories_created = %s,
                            orphans_created = %s
                        WHERE id = %s
                    """, (
                        story_result.get("stories_created", 0),
                        story_result.get("orphans_created", 0),
                        run_id,
                    ))

            if stop_checker():
                _finalize_stopped_run(run_id, result, theme_result, story_result)
                return

        # ==== COMPLETED ====
        _finalize_completed_run(run_id, result, theme_result, story_result)

    except Exception as e:
        # Update with error
        logger.error(f"Run {run_id}: Pipeline failed with error: {e}")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        completed_at = %s,
                        status = 'failed',
                        error_message = %s
                    WHERE id = %s
                """, (datetime.now(timezone.utc), str(e), run_id))

        _active_runs[run_id] = "failed"
        raise


def _finalize_completed_run(run_id: int, result: dict, theme_result: dict, story_result: dict):
    """Finalize a successfully completed run."""
    from src.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pipeline_runs SET
                    completed_at = %s,
                    current_phase = 'completed',
                    conversations_fetched = %s,
                    conversations_filtered = %s,
                    conversations_classified = %s,
                    conversations_stored = %s,
                    themes_extracted = %s,
                    themes_new = %s,
                    stories_created = %s,
                    orphans_created = %s,
                    status = 'completed'
                WHERE id = %s
            """, (
                datetime.now(timezone.utc),
                result.get("fetched", 0),
                result.get("filtered", 0),
                result.get("classified", 0),
                result.get("stored", 0),
                theme_result.get("themes_extracted", 0),
                theme_result.get("themes_new", 0),
                story_result.get("stories_created", 0),
                story_result.get("orphans_created", 0),
                run_id,
            ))

    logger.info(f"Run {run_id}: Pipeline completed successfully")
    _active_runs[run_id] = "completed"


def _finalize_stopped_run(
    run_id: int,
    result: dict,
    theme_result: Optional[dict] = None,
    story_result: Optional[dict] = None,
):
    """Finalize a run that was stopped gracefully."""
    from src.db.connection import get_connection

    theme_result = theme_result or {"themes_extracted": 0, "themes_new": 0}
    story_result = story_result or {"stories_created": 0, "orphans_created": 0}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pipeline_runs SET
                    completed_at = %s,
                    conversations_fetched = %s,
                    conversations_filtered = %s,
                    conversations_classified = %s,
                    conversations_stored = %s,
                    themes_extracted = %s,
                    themes_new = %s,
                    stories_created = %s,
                    orphans_created = %s,
                    status = 'stopped'
                WHERE id = %s
            """, (
                datetime.now(timezone.utc),
                result.get("fetched", 0),
                result.get("filtered", 0),
                result.get("classified", 0),
                result.get("stored", 0),
                theme_result.get("themes_extracted", 0),
                theme_result.get("themes_new", 0),
                story_result.get("stories_created", 0),
                story_result.get("orphans_created", 0),
                run_id,
            ))

    logger.info(f"Run {run_id}: Pipeline stopped")
    _active_runs[run_id] = "stopped"


@router.post("/run", response_model=PipelineRunResponse)
def start_pipeline_run(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """
    Start a new hybrid pipeline run.

    The pipeline executes in the background with these phases:
    1. Classification - Fetch and classify conversations
    2. Theme Extraction - Extract themes from actionable conversations
    3. Story Creation (optional) - Create stories from theme groups

    Use GET /status/{run_id} to check progress and current phase.

    **Parameters:**
    - **days**: How far back to look for conversations (default 7)
    - **max_conversations**: Limit number processed (useful for testing)
    - **dry_run**: If True, classify but don't store to database
    - **concurrency**: Parallel API calls (default 20)
    - **auto_create_stories**: If True, automatically create stories after theme extraction
    """
    # Clean up terminal runs to prevent memory leak (R2 fix)
    _cleanup_terminal_runs()

    # Check if another run is already active
    active = [rid for rid, status in _active_runs.items() if status == "running"]
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline run {active[0]} is already in progress. Wait for it to complete."
        )

    # Calculate date range
    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=request.days)

    # Create pipeline run record with auto_create_stories flag
    with db.cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_runs (
                started_at, date_from, date_to, status,
                auto_create_stories, current_phase
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            datetime.now(timezone.utc),
            date_from,
            date_to,
            "running",
            request.auto_create_stories,
            "classification",
        ))
        run_id = cur.fetchone()["id"]

    # Commit immediately so the record is visible to status queries
    db.commit()

    # Start background task
    background_tasks.add_task(
        _run_pipeline_task,
        run_id=run_id,
        days=request.days,
        max_conversations=request.max_conversations,
        dry_run=request.dry_run,
        concurrency=request.concurrency,
        auto_create_stories=request.auto_create_stories,
    )

    message = f"Pipeline run started. Processing last {request.days} days."
    if request.auto_create_stories:
        message += " Stories will be created automatically after theme extraction."

    return PipelineRunResponse(
        run_id=run_id,
        status="started",
        message=message,
    )


@router.get("/status/{run_id}", response_model=PipelineStatus)
def get_pipeline_status(run_id: int, db=Depends(get_db)):
    """
    Get status of a specific pipeline run.

    Returns current progress including conversation counts, theme stats,
    story stats, and current phase.

    Poll this endpoint to track long-running pipelines.
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, started_at, completed_at, date_from, date_to,
                   conversations_fetched, conversations_filtered,
                   conversations_classified, conversations_stored,
                   current_phase, auto_create_stories,
                   themes_extracted, themes_new,
                   stories_created, orphans_created, stories_ready,
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
        duration = (datetime.now(timezone.utc) - row["started_at"]).total_seconds()

    return PipelineStatus(
        id=row["id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        date_from=row["date_from"],
        date_to=row["date_to"],
        auto_create_stories=row["auto_create_stories"] or False,
        current_phase=row["current_phase"] or "classification",
        conversations_fetched=row["conversations_fetched"] or 0,
        conversations_filtered=row["conversations_filtered"] or 0,
        conversations_classified=row["conversations_classified"] or 0,
        conversations_stored=row["conversations_stored"] or 0,
        themes_extracted=row["themes_extracted"] or 0,
        themes_new=row["themes_new"] or 0,
        stories_created=row["stories_created"] or 0,
        orphans_created=row["orphans_created"] or 0,
        stories_ready=row["stories_ready"] or False,
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
    Includes phase tracking and story creation stats.
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, started_at, completed_at,
                   conversations_fetched, conversations_classified, conversations_stored,
                   current_phase, themes_extracted, stories_created, stories_ready,
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
            current_phase=row["current_phase"] or "classification",
            conversations_fetched=row["conversations_fetched"] or 0,
            conversations_classified=row["conversations_classified"] or 0,
            conversations_stored=row["conversations_stored"] or 0,
            themes_extracted=row["themes_extracted"] or 0,
            stories_created=row["stories_created"] or 0,
            stories_ready=row["stories_ready"] or False,
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


@router.post("/{run_id}/create-stories", response_model=CreateStoriesResponse)
def create_stories_for_run(
    run_id: int,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """
    Manually trigger story creation for a completed pipeline run.

    Requires:
    - Run must exist and be completed
    - stories_ready must be True (themes extracted)
    - Stories must not already be created (stories_created == 0)

    This endpoint runs synchronously since story creation is typically fast.
    """
    # Check run exists and is ready
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, status, stories_ready, stories_created, themes_extracted
            FROM pipeline_runs
            WHERE id = %s
        """, (run_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")

    if row["status"] not in ("completed", "stopped"):
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline run {run_id} is not completed (status: {row['status']})"
        )

    if not row["stories_ready"]:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline run {run_id} is not ready for story creation (themes not extracted)"
        )

    if row["stories_created"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Stories already created for pipeline run {run_id} ({row['stories_created']} stories)"
        )

    if row["themes_extracted"] == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No themes extracted in pipeline run {run_id}"
        )

    # Run story creation synchronously
    logger.info(f"Run {run_id}: Manual story creation triggered")

    # Update phase
    _update_phase(run_id, "story_creation")

    # Run story creation
    story_result = _run_pm_review_and_story_creation(run_id, lambda: False)

    # Update database with results
    with db.cursor() as cur:
        cur.execute("""
            UPDATE pipeline_runs SET
                stories_created = %s,
                orphans_created = %s,
                current_phase = 'completed'
            WHERE id = %s
        """, (
            story_result.get("stories_created", 0),
            story_result.get("orphans_created", 0),
            run_id,
        ))
    db.commit()

    return CreateStoriesResponse(
        run_id=run_id,
        stories_created=story_result.get("stories_created", 0),
        orphans_created=story_result.get("orphans_created", 0),
        message=f"Created {story_result.get('stories_created', 0)} stories and {story_result.get('orphans_created', 0)} orphan stories.",
    )
