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
    DryRunClassificationBreakdown,
    DryRunPreview,
    DryRunSample,
    PipelineRunListItem,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatus,
    PipelineStopResponse,
)
from src.db.connection import create_pipeline_run, update_pipeline_run
from src.db.models import PipelineRun
from src.story_tracking.models import MIN_GROUP_SIZE
from src.story_tracking.services.story_service import StoryService
from src.story_tracking.services.orphan_service import OrphanService
from src.story_tracking.services.evidence_service import EvidenceService
from src.story_tracking.services.story_creation_service import StoryCreationService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Track active runs (in-memory for MVP, could use Redis for production)
# States: running, stopping, stopped, completed, failed
_active_runs: dict[int, str] = {}  # run_id -> status

# Terminal states that can be cleaned up
_TERMINAL_STATES = {"stopped", "completed", "failed"}

# In-memory storage for dry run previews (keyed by run_id)
# Design: Keep last 5 previews, auto-cleanup on new dry runs
_dry_run_previews: dict[int, DryRunPreview] = {}
# Memory limit: Keep only 5 most recent previews to prevent unbounded growth.
# Each preview contains samples and breakdown data (~1-5KB typical).
_MAX_DRY_RUN_PREVIEWS = 5


def _cleanup_old_dry_run_previews() -> None:
    """Remove oldest dry run previews when limit exceeded.

    Called proactively BEFORE storing a new preview to ensure we have room.
    This guarantees we never exceed _MAX_DRY_RUN_PREVIEWS even if storage fails.
    """
    global _dry_run_previews
    # Use >= to make room for new preview (called before storing)
    if len(_dry_run_previews) >= _MAX_DRY_RUN_PREVIEWS:
        # Sort by timestamp and keep only the most recent (N-1 to make room)
        sorted_run_ids = sorted(
            _dry_run_previews.keys(),
            key=lambda rid: _dry_run_previews[rid].timestamp,
            reverse=True,
        )
        # Keep only the most recent N-1 previews to make room for new one
        ids_to_remove = sorted_run_ids[_MAX_DRY_RUN_PREVIEWS - 1:]
        for rid in ids_to_remove:
            del _dry_run_previews[rid]
        logger.info(f"Cleaned up {len(ids_to_remove)} old dry run previews")


def _store_dry_run_preview(run_id: int, results: list[dict]) -> None:
    """
    Store dry run classification results for later preview retrieval.

    Args:
        run_id: Pipeline run ID
        results: List of classification result dicts from run_pipeline_async
                 Each dict has: conversation_id, source_body, stage1_result,
                 stage2_result, support_messages, etc.
    """
    from collections import Counter

    if not results:
        logger.info(f"Run {run_id}: No results to store for dry run preview")
        return

    # Proactive cleanup: remove old previews BEFORE storing new one
    # to ensure we stay within memory limits even if storage fails
    _cleanup_old_dry_run_previews()

    # Build classification breakdown
    type_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    theme_counts: Counter[str] = Counter()

    for r in results:
        # Get final type (stage2 if available, else stage1)
        # Note: Check if stage2 dict exists first, then use its values.
        # Empty string "" is falsy in Python, so we can't just use `or` fallback
        # which would incorrectly trigger on valid empty strings.
        stage2 = r.get("stage2_result") or {}
        stage1 = r.get("stage1_result") or {}

        if stage2:
            conv_type = stage2.get("conversation_type") or "unknown"
            confidence = stage2.get("confidence") or "low"
        else:
            conv_type = stage1.get("conversation_type", "unknown")
            confidence = stage1.get("confidence", "low")

        type_counts[conv_type] += 1
        confidence_counts[confidence] += 1

        # Extract themes from stage1 result if present
        themes = stage1.get("themes", [])
        if isinstance(themes, list):
            for theme in themes:
                if isinstance(theme, str) and theme:
                    theme_counts[theme] += 1

    # Build samples (5-10 representative)
    # Strategy: Take up to 10 samples, prioritizing diversity of types
    samples: list[DryRunSample] = []
    seen_types: set[str] = set()
    # Use a set for O(1) lookup instead of O(n) list scan in second pass
    seen_conv_ids: set[str] = set()

    # First pass: get one sample per type (up to 5)
    for r in results:
        if len(samples) >= 5:
            break
        stage2 = r.get("stage2_result") or {}
        stage1 = r.get("stage1_result") or {}

        if stage2:
            conv_type = stage2.get("conversation_type") or "unknown"
        else:
            conv_type = stage1.get("conversation_type", "unknown")

        if conv_type not in seen_types:
            seen_types.add(conv_type)
            conv_id = str(r.get("conversation_id", ""))
            seen_conv_ids.add(conv_id)
            samples.append(_build_sample(r))

    # Second pass: fill up to 10 with remaining diverse samples
    # O(1) lookup using set instead of O(n) list comprehension
    for r in results:
        if len(samples) >= 10:
            break
        conv_id = str(r.get("conversation_id", ""))
        if conv_id not in seen_conv_ids:
            seen_conv_ids.add(conv_id)
            samples.append(_build_sample(r))

    # Get top 5 themes
    top_themes = theme_counts.most_common(5)

    # Create preview object
    preview = DryRunPreview(
        run_id=run_id,
        classification_breakdown=DryRunClassificationBreakdown(
            by_type=dict(type_counts),
            by_confidence=dict(confidence_counts),
        ),
        samples=samples,
        top_themes=top_themes,
        total_classified=len(results),
        timestamp=datetime.now(timezone.utc),
    )

    # Store preview
    _dry_run_previews[run_id] = preview

    logger.info(
        f"Run {run_id}: Stored dry run preview with {len(results)} results, "
        f"{len(samples)} samples, {len(top_themes)} top themes"
    )


def _build_sample(result: dict) -> DryRunSample:
    """Build a DryRunSample from a classification result dict."""
    stage2 = result.get("stage2_result") or {}
    stage1 = result.get("stage1_result") or {}

    # Check if stage2 dict exists first, then use its values.
    # Empty string "" is falsy in Python, so we can't just use `or` fallback
    # which would incorrectly trigger on valid empty strings.
    if stage2:
        conv_type = stage2.get("conversation_type") or "unknown"
        confidence = stage2.get("confidence") or "low"
    else:
        conv_type = stage1.get("conversation_type", "unknown")
        confidence = stage1.get("confidence", "low")

    themes = stage1.get("themes", [])
    if not isinstance(themes, list):
        themes = []

    source_body = result.get("source_body", "") or ""
    support_messages = result.get("support_messages", [])

    return DryRunSample(
        conversation_id=str(result.get("conversation_id", "")),
        # Truncate to 200 chars: Keeps samples concise for UI display
        # while providing enough context to understand the conversation topic.
        snippet=source_body[:200] if source_body else "",
        conversation_type=conv_type,
        confidence=confidence,
        themes=themes[:5],  # Limit to 5 themes per sample
        has_support_response=bool(support_messages),
    )


def _cleanup_terminal_runs() -> None:
    """Remove terminal (completed/failed/stopped) runs to prevent memory leak."""
    terminal_ids = [rid for rid, status in _active_runs.items() if status in _TERMINAL_STATES]
    for rid in terminal_ids:
        del _active_runs[rid]
        # Also cleanup associated dry run preview if it exists
        # This prevents memory leak from orphaned previews
        if rid in _dry_run_previews:
            del _dry_run_previews[rid]


def _is_stopping(run_id: int) -> bool:
    """Check if the run has been requested to stop."""
    return _active_runs.get(run_id) == "stopping"


# Whitelist of allowed fields for _update_phase to prevent SQL injection
_ALLOWED_PHASE_FIELDS = frozenset({
    "themes_extracted", "themes_new", "themes_filtered",
    "stories_created", "orphans_created",
    "stories_ready", "auto_create_stories", "conversations_fetched",
    "conversations_classified", "conversations_stored", "conversations_filtered",
    "embeddings_generated", "embeddings_failed",  # #106: Embedding generation phase
    "facets_extracted", "facets_failed",  # #107: Facet extraction phase
    "warnings", "errors",  # #104: Structured error tracking
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


async def _run_embedding_generation_async(
    run_id: int, stop_checker: Callable[[], bool]
) -> dict:
    """
    Generate embeddings for classified conversations from this pipeline run.

    Returns dict with embeddings_generated and embeddings_failed counts.

    Issue #106: Pipeline step for embedding generation.
    Embeddings are generated for actionable conversation types:
    product_issue, feature_request, how_to_question.
    """
    from src.db.connection import get_connection
    from src.services.embedding_service import EmbeddingService
    from src.db.embedding_storage import store_embeddings_batch
    from psycopg2.extras import RealDictCursor

    logger.info(f"Run {run_id}: Starting embedding generation")

    # Get conversations classified in this run (same query as theme extraction)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Use pipeline_run_id for run scoping (per #103)
            # Filter to actionable types that need embeddings for clustering
            # Note: conversations table does not have an 'excerpt' column.
            # EmbeddingService._prepare_text supports excerpt but we use source_body.
            cur.execute("""
                SELECT c.id, c.source_body
                FROM conversations c
                JOIN pipeline_runs pr ON pr.id = %s
                WHERE (c.pipeline_run_id = %s
                       OR (c.pipeline_run_id IS NULL AND c.classified_at >= pr.started_at))
                  AND COALESCE(c.stage2_type, c.stage1_type) IN (
                      'product_issue', 'feature_request', 'how_to_question'
                  )
                ORDER BY c.created_at DESC
            """, (run_id, run_id))
            rows = cur.fetchall()

    if not rows:
        logger.info(f"Run {run_id}: No actionable conversations for embedding generation")
        return {"embeddings_generated": 0, "embeddings_failed": 0}

    # Prepare conversations for embedding service
    conversations = [
        {"id": row["id"], "source_body": row["source_body"]}
        for row in rows
    ]

    logger.info(f"Run {run_id}: Generating embeddings for {len(conversations)} conversations")

    # Generate embeddings
    service = EmbeddingService()
    result = await service.generate_conversation_embeddings_async(
        conversations=conversations,
        stop_checker=stop_checker,
    )

    # Store successful embeddings
    if result.successful:
        stored_count = store_embeddings_batch(
            results=result.successful,
            pipeline_run_id=run_id,
        )
        logger.info(f"Run {run_id}: Stored {stored_count} embeddings")
    else:
        stored_count = 0

    # Log failures for observability
    if result.failed:
        failed_ids = [r.conversation_id for r in result.failed[:5]]  # First 5 for brevity
        logger.warning(
            f"Run {run_id}: Failed to generate embeddings for {len(result.failed)} conversations. "
            f"Sample IDs: {failed_ids}"
        )

    logger.info(
        f"Run {run_id}: Embedding generation complete. "
        f"Generated: {result.total_success}, Failed: {result.total_failed}"
    )

    return {
        "embeddings_generated": result.total_success,
        "embeddings_failed": result.total_failed,
    }


def _run_embedding_generation(run_id: int, stop_checker: Callable[[], bool]) -> dict:
    """
    Synchronous wrapper for _run_embedding_generation_async.

    Bridges the sync pipeline task with async embedding service.

    Note: asyncio.run() is safe here because _run_pipeline_task runs in a
    separate background thread (via FastAPI BackgroundTasks), not in an
    existing event loop. Each asyncio.run() call creates a fresh event loop.
    """
    import asyncio

    return asyncio.run(_run_embedding_generation_async(run_id, stop_checker))


async def _run_facet_extraction_async(
    run_id: int, stop_checker: Callable[[], bool]
) -> dict:
    """
    Extract facets from classified conversations for hybrid clustering.

    Returns dict with facets_extracted and facets_failed counts.

    Issue #107: Pipeline step for facet extraction.
    Facets are extracted for actionable conversation types:
    product_issue, feature_request, how_to_question.

    Facets include:
    - action_type: inquiry, complaint, bug_report, etc.
    - direction: excess, deficit, creation, etc. (critical for clustering)
    - symptom: Brief description of user issue
    - user_goal: What user is trying to accomplish
    """
    from src.db.connection import get_connection
    from src.services.facet_service import FacetExtractionService
    from src.db.facet_storage import store_facets_batch
    from psycopg2.extras import RealDictCursor

    logger.info(f"Run {run_id}: Starting facet extraction")

    # Get conversations classified in this run (same query as embedding generation)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Use pipeline_run_id for run scoping (per #103)
            # Filter to actionable types that need facets for clustering
            cur.execute("""
                SELECT c.id, c.source_body
                FROM conversations c
                JOIN pipeline_runs pr ON pr.id = %s
                WHERE (c.pipeline_run_id = %s
                       OR (c.pipeline_run_id IS NULL AND c.classified_at >= pr.started_at))
                  AND COALESCE(c.stage2_type, c.stage1_type) IN (
                      'product_issue', 'feature_request', 'how_to_question'
                  )
                ORDER BY c.created_at DESC
            """, (run_id, run_id))
            rows = cur.fetchall()

    if not rows:
        logger.info(f"Run {run_id}: No actionable conversations for facet extraction")
        return {"facets_extracted": 0, "facets_failed": 0}

    # Prepare conversations for facet service
    conversations = [
        {"id": row["id"], "source_body": row["source_body"]}
        for row in rows
    ]

    logger.info(f"Run {run_id}: Extracting facets for {len(conversations)} conversations")

    # Extract facets
    service = FacetExtractionService()
    result = await service.extract_facets_batch_async(
        conversations=conversations,
        stop_checker=stop_checker,
    )

    # Store successful facets
    if result.successful:
        stored_count = store_facets_batch(
            results=result.successful,
            pipeline_run_id=run_id,
        )
        logger.info(f"Run {run_id}: Stored {stored_count} facets")
    else:
        stored_count = 0

    # Log failures for observability
    if result.failed:
        failed_ids = [r.conversation_id for r in result.failed[:5]]  # First 5 for brevity
        logger.warning(
            f"Run {run_id}: Failed to extract facets for {len(result.failed)} conversations. "
            f"Sample IDs: {failed_ids}"
        )

    logger.info(
        f"Run {run_id}: Facet extraction complete. "
        f"Extracted: {result.total_success}, Failed: {result.total_failed}"
    )

    return {
        "facets_extracted": result.total_success,
        "facets_failed": result.total_failed,
    }


def _run_facet_extraction(run_id: int, stop_checker: Callable[[], bool]) -> dict:
    """
    Synchronous wrapper for _run_facet_extraction_async.

    Bridges the sync pipeline task with async facet service.

    Note: asyncio.run() is safe here because _run_pipeline_task runs in a
    separate background thread (via FastAPI BackgroundTasks), not in an
    existing event loop. Each asyncio.run() call creates a fresh event loop.
    """
    import asyncio

    return asyncio.run(_run_facet_extraction_async(run_id, stop_checker))


def _run_theme_extraction(run_id: int, stop_checker: Callable[[], bool]) -> dict:
    """
    Run theme extraction on classified conversations from this pipeline run.

    Returns dict with themes_extracted, themes_new, themes_filtered counts and warnings.

    Quality Gates (#104):
    - Filters themes below confidence threshold
    - Filters themes not in vocabulary with low confidence
    - Logs filtered themes for observability
    """
    from src.db.connection import get_connection
    from src.theme_extractor import ThemeExtractor
    from src.theme_quality import filter_themes_by_quality
    from src.db.models import Conversation
    from psycopg2.extras import RealDictCursor

    logger.info(f"Run {run_id}: Starting theme extraction")

    # Get conversations classified in this run
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Fix #103: Use explicit pipeline_run_id instead of timestamp heuristics
            # BACKWARD COMPATIBILITY: For pre-migration conversations (pipeline_run_id IS NULL),
            # fall back to timestamp heuristic. New conversations use explicit run association.
            # Use COALESCE(stage2_type, stage1_type) as the final classification
            # New classifier types: product_issue, feature_request, how_to_question
            cur.execute("""
                SELECT c.id, c.created_at, c.source_body, c.source_url,
                       COALESCE(c.stage2_type, c.stage1_type) as issue_type,
                       c.sentiment, c.priority, c.churn_risk
                FROM conversations c
                JOIN pipeline_runs pr ON pr.id = %s
                WHERE (c.pipeline_run_id = %s
                       OR (c.pipeline_run_id IS NULL AND c.classified_at >= pr.started_at))
                  AND COALESCE(c.stage2_type, c.stage1_type) IN (
                      'product_issue', 'feature_request', 'how_to_question'
                  )
                ORDER BY c.created_at DESC
            """, (run_id, run_id))
            rows = cur.fetchall()

    if not rows:
        logger.info(f"Run {run_id}: No actionable conversations to extract themes from")
        return {"themes_extracted": 0, "themes_new": 0, "themes_filtered": 0, "warnings": []}

    # Map new classifier types to legacy IssueType for Conversation model
    # New → Legacy: product_issue → bug_report, how_to_question → product_question
    NEW_TO_LEGACY_TYPE = {
        "product_issue": "bug_report",
        "feature_request": "feature_request",
        "how_to_question": "product_question",
    }

    # Convert to Conversation objects
    conversations = []
    for row in rows:
        if stop_checker():
            logger.info(f"Run {run_id}: Stop signal received during theme extraction")
            return {"themes_extracted": 0, "themes_new": 0, "themes_filtered": 0, "warnings": []}

        # Map new type to legacy type for Pydantic model compatibility
        new_type = row["issue_type"]
        legacy_type = NEW_TO_LEGACY_TYPE.get(new_type, "other")

        conv = Conversation(
            id=row["id"],
            created_at=row["created_at"],
            source_body=row["source_body"],
            source_url=row.get("source_url"),
            issue_type=legacy_type,
            sentiment=row["sentiment"],
            priority=row["priority"],
            churn_risk=row["churn_risk"],
        )
        conversations.append(conv)

    logger.info(f"Run {run_id}: Extracting themes from {len(conversations)} conversations")

    # Extract themes
    extractor = ThemeExtractor()
    # Clear session signatures for clean batch canonicalization
    extractor.clear_session_signatures()
    all_themes = []
    themes_new = 0

    for conv in conversations:
        if stop_checker():
            logger.info(f"Run {run_id}: Stop signal received during theme extraction")
            break

        try:
            theme = extractor.extract(conv, strict_mode=False)
            all_themes.append(theme)

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

    # Apply quality gates (#104)
    # Filter themes that don't meet quality thresholds
    high_quality_themes, low_quality_themes, warnings = filter_themes_by_quality(all_themes)

    if low_quality_themes:
        logger.info(
            f"Run {run_id}: Quality gates filtered {len(low_quality_themes)} of "
            f"{len(all_themes)} themes"
        )

    # Store themes in database with pipeline_run_id and quality metadata
    from psycopg2.extras import Json
    from src.theme_quality import check_theme_quality

    with get_connection() as conn:
        with conn.cursor() as cur:
            for theme in high_quality_themes:
                # Calculate quality score for storage
                quality_result = check_theme_quality(
                    issue_signature=theme.issue_signature,
                    matched_existing=theme.matched_existing,
                    match_confidence=theme.match_confidence or "low",
                )

                cur.execute("""
                    INSERT INTO themes (
                        conversation_id, product_area, component, issue_signature,
                        user_intent, symptoms, affected_flow, root_cause_hypothesis,
                        pipeline_run_id, quality_score, quality_details
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (conversation_id) DO UPDATE SET
                        product_area = EXCLUDED.product_area,
                        component = EXCLUDED.component,
                        issue_signature = EXCLUDED.issue_signature,
                        user_intent = EXCLUDED.user_intent,
                        symptoms = EXCLUDED.symptoms,
                        affected_flow = EXCLUDED.affected_flow,
                        root_cause_hypothesis = EXCLUDED.root_cause_hypothesis,
                        pipeline_run_id = EXCLUDED.pipeline_run_id,
                        quality_score = EXCLUDED.quality_score,
                        quality_details = EXCLUDED.quality_details,
                        extracted_at = NOW()
                """, (
                    theme.conversation_id,
                    theme.product_area,
                    theme.component,
                    theme.issue_signature,
                    theme.user_intent,
                    Json(theme.symptoms),  # Wrap list for JSONB column
                    theme.affected_flow,
                    theme.root_cause_hypothesis,
                    run_id,
                    quality_result.quality_score,
                    Json(quality_result.details),
                ))

    logger.info(
        f"Run {run_id}: Extracted {len(high_quality_themes)} themes ({themes_new} new), "
        f"filtered {len(low_quality_themes)}"
    )
    return {
        "themes_extracted": len(high_quality_themes),
        "themes_new": themes_new,
        "themes_filtered": len(low_quality_themes),
        "warnings": warnings,
    }


def _run_pm_review_and_story_creation(run_id: int, stop_checker: Callable[[], bool]) -> dict:
    """
    Run story creation from theme groups, optionally using hybrid clustering.

    When HYBRID_CLUSTERING_ENABLED=true (default: true):
    - Uses HybridClusteringService to group conversations by embedding + facets
    - Groups by semantic similarity + action_type/direction for coherent stories
    - Falls back to signature-based grouping if clustering fails

    When HYBRID_CLUSTERING_ENABLED=false:
    - Uses legacy signature-based grouping
    - PM review evaluates group coherence (if enabled)

    Uses StoryCreationService for proper story/orphan handling with:
    - Evidence bundle creation
    - Proper orphan lifecycle via OrphanService

    Returns dict with stories_created, orphans_created counts.
    """
    import os
    from src.db.connection import get_connection
    from psycopg2.extras import RealDictCursor

    logger.info(f"Run {run_id}: Starting story creation")

    # Check if hybrid clustering is enabled (default: true for #109)
    hybrid_clustering_enabled = os.environ.get(
        "HYBRID_CLUSTERING_ENABLED", "true"
    ).lower() == "true"

    # Get themes from this run
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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

    # Build conversation data lookup (needed for both paths)
    conversation_data: dict[str, dict] = {}
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        conv_dict = {
            "id": row["conversation_id"],
            "issue_signature": row["issue_signature"],
            "product_area": row["product_area"],
            "component": row["component"],
            "user_intent": row["user_intent"],
            "symptoms": row["symptoms"],
            "affected_flow": row["affected_flow"],
            "excerpt": (row["source_body"] or "")[:500],
        }
        conversation_data[row["conversation_id"]] = conv_dict
        groups[row["issue_signature"]].append(conv_dict)

    logger.info(
        f"Run {run_id}: {len(groups)} theme groups, "
        f"{len(conversation_data)} conversations"
    )

    if stop_checker():
        return {"stories_created": 0, "orphans_created": 0}

    # Initialize services
    with get_connection() as conn:
        conn.cursor_factory = RealDictCursor
        story_service = StoryService(conn)
        orphan_service = OrphanService(conn)
        evidence_service = EvidenceService(conn)

        # Determine dual format settings from environment
        dual_format_enabled = os.environ.get("FEEDFORWARD_DUAL_FORMAT", "true").lower() == "true"
        target_repo = os.environ.get("FEEDFORWARD_TARGET_REPO", "FeedForward")

        # PM Review settings
        pm_review_enabled = os.environ.get("PM_REVIEW_ENABLED", "true").lower() == "true"
        pm_review_service = None

        # Initialize PM review for both hybrid and signature-based paths
        if pm_review_enabled:
            try:
                from src.story_tracking.services.pm_review_service import PMReviewService
                pm_review_service = PMReviewService()
                logger.info(f"Run {run_id}: PM review enabled")
            except ImportError:
                logger.warning(f"Run {run_id}: PM review requested but service not available")
                pm_review_enabled = False

        story_creation_service = StoryCreationService(
            story_service=story_service,
            orphan_service=orphan_service,
            evidence_service=evidence_service,
            dual_format_enabled=dual_format_enabled,
            target_repo=target_repo,
            pm_review_service=pm_review_service,
            pm_review_enabled=pm_review_enabled,  # PM review works for both signature and hybrid clustering
        )

        # Try hybrid clustering if enabled
        if hybrid_clustering_enabled:
            result = _try_hybrid_clustering_story_creation(
                run_id=run_id,
                conversation_data=conversation_data,
                story_creation_service=story_creation_service,
            )

            # If clustering succeeded, use those results
            if result is not None:
                logger.info(
                    f"Run {run_id}: Hybrid clustering created {result.stories_created} stories, "
                    f"{result.orphans_created} orphans"
                )
                return {
                    "stories_created": result.stories_created,
                    "orphans_created": result.orphans_created,
                    "grouping_method": "hybrid_cluster",
                    "pm_review_splits": result.pm_review_splits,
                    "pm_review_rejects": result.pm_review_rejects,
                    "pm_review_kept": result.pm_review_kept,
                    "pm_review_skipped": result.pm_review_skipped,
                }

            # Fall back to signature-based if clustering failed
            logger.warning(
                f"Run {run_id}: Hybrid clustering failed, falling back to signature-based grouping"
            )

        # Signature-based grouping (legacy path)
        result = story_creation_service.process_theme_groups(
            theme_groups=groups,
            pipeline_run_id=run_id,
        )

    logger.info(
        f"Run {run_id}: Created {result.stories_created} stories, "
        f"{result.orphans_created} orphans. "
        f"PM review: {result.pm_review_splits} splits, {result.pm_review_kept} kept, "
        f"{result.pm_review_rejects} rejects, {result.pm_review_skipped} skipped"
    )

    # Include PM review metrics in return value
    return {
        "stories_created": result.stories_created,
        "orphans_created": result.orphans_created,
        "grouping_method": "signature",
        "pm_review_splits": result.pm_review_splits,
        "pm_review_rejects": result.pm_review_rejects,
        "pm_review_kept": result.pm_review_kept,
        "pm_review_skipped": result.pm_review_skipped,
    }


def _try_hybrid_clustering_story_creation(
    run_id: int,
    conversation_data: dict[str, dict],
    story_creation_service: "StoryCreationService",
) -> Optional["ProcessingResult"]:
    """
    Attempt hybrid clustering story creation.

    Uses HybridClusteringService to cluster conversations by embedding + facets,
    then creates stories from the resulting clusters.

    Args:
        run_id: Pipeline run ID
        conversation_data: Dict mapping conversation_id -> conversation dict
        story_creation_service: StoryCreationService instance

    Returns:
        ProcessingResult if successful, None if clustering failed/unavailable
    """
    try:
        from src.services.hybrid_clustering_service import HybridClusteringService

        # Run hybrid clustering (loads embeddings + facets from DB for this run)
        clustering_service = HybridClusteringService()
        clustering_result = clustering_service.cluster_for_run(
            pipeline_run_id=run_id,
        )

        if not clustering_result.success:
            logger.warning(
                f"Run {run_id}: Hybrid clustering failed: {clustering_result.errors}"
            )
            return None

        if not clustering_result.clusters:
            logger.info(f"Run {run_id}: Hybrid clustering produced no clusters")
            return None

        logger.info(
            f"Run {run_id}: Hybrid clustering produced {len(clustering_result.clusters)} clusters "
            f"with {clustering_result.total_conversations} conversations"
        )

        # Process clusters through StoryCreationService
        result = story_creation_service.process_hybrid_clusters(
            clustering_result=clustering_result,
            conversation_data=conversation_data,
            pipeline_run_id=run_id,
        )

        return result

    except ImportError as e:
        logger.warning(f"Run {run_id}: HybridClusteringService not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Run {run_id}: Hybrid clustering error: {e}")
        return None


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
    2. Embedding Generation (#106) - Generate embeddings for actionable conversations
    3. Theme Extraction - Extract themes from actionable conversations
    4. (Optional) PM Review + Story Creation - Create stories from theme groups

    Updates the pipeline_runs table with progress and results.
    Checks for stop signal between phases and exits gracefully if stopping.
    """
    import asyncio
    from src.db.connection import get_connection
    from src.two_stage_pipeline import run_pipeline_async

    try:
        _active_runs[run_id] = "running"
        stop_checker = lambda: _is_stopping(run_id)

        # Track results across phases
        result = {"fetched": 0, "filtered": 0, "classified": 0, "stored": 0}
        theme_result = {"themes_extracted": 0, "themes_new": 0}
        story_result = {"stories_created": 0, "orphans_created": 0}
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
            pipeline_run_id=run_id,
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

            # Store dry run preview for later retrieval (Issue #75)
            if dry_run:
                dry_run_results = result.pop("_dry_run_results", [])
                if dry_run_results:
                    _store_dry_run_preview(run_id, dry_run_results)

            _finalize_completed_run(run_id, result, theme_result, story_result)
            return

        # ==== PHASE 2: Embedding Generation (#106) ====
        embedding_result = {"embeddings_generated": 0, "embeddings_failed": 0}

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result)
            return

        _update_phase(run_id, "embedding_generation")

        embedding_result = _run_embedding_generation(run_id, stop_checker)

        # Update embedding results in database
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        embeddings_generated = %s,
                        embeddings_failed = %s
                    WHERE id = %s
                """, (
                    embedding_result.get("embeddings_generated", 0),
                    embedding_result.get("embeddings_failed", 0),
                    run_id,
                ))

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result)
            return

        # ==== PHASE 3: Facet Extraction (#107) ====
        facet_result = {"facets_extracted": 0, "facets_failed": 0}

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result, facet_result)
            return

        _update_phase(run_id, "facet_extraction")

        facet_result = _run_facet_extraction(run_id, stop_checker)

        # Update facet results in database
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        facets_extracted = %s,
                        facets_failed = %s
                    WHERE id = %s
                """, (
                    facet_result.get("facets_extracted", 0),
                    facet_result.get("facets_failed", 0),
                    run_id,
                ))

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result, facet_result)
            return

        # ==== PHASE 4: Theme Extraction ====
        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result, facet_result)
            return

        _update_phase(run_id, "theme_extraction")

        theme_result = _run_theme_extraction(run_id, stop_checker)

        # Update theme extraction results
        # Fix #104: stories_ready only TRUE when themes_extracted > 0
        themes_extracted = theme_result.get("themes_extracted", 0)
        themes_filtered = theme_result.get("themes_filtered", 0)
        theme_warnings = theme_result.get("warnings", [])

        from psycopg2.extras import Json

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pipeline_runs SET
                        themes_extracted = %s,
                        themes_new = %s,
                        themes_filtered = %s,
                        stories_ready = %s,
                        warnings = COALESCE(warnings, '[]'::jsonb) || %s::jsonb
                    WHERE id = %s
                """, (
                    themes_extracted,
                    theme_result.get("themes_new", 0),
                    themes_filtered,
                    themes_extracted > 0,  # Fix: only ready if themes exist
                    Json(theme_warnings),
                    run_id,
                ))

        if stop_checker():
            _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result, facet_result)
            return

        # ==== PHASE 5: PM Review + Story Creation (optional) ====
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
                _finalize_stopped_run(run_id, result, theme_result, story_result, embedding_result, facet_result)
                return

        # ==== COMPLETED ====
        _finalize_completed_run(run_id, result, theme_result, story_result, embedding_result, facet_result)

    except Exception as e:
        # Update with error
        logger.error(f"Run {run_id}: Pipeline failed with error: {e}", exc_info=True)
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


def _finalize_completed_run(
    run_id: int,
    result: dict,
    theme_result: dict,
    story_result: dict,
    embedding_result: Optional[dict] = None,
    facet_result: Optional[dict] = None,
):
    """Finalize a successfully completed run."""
    from src.db.connection import get_connection

    embedding_result = embedding_result or {"embeddings_generated": 0, "embeddings_failed": 0}
    facet_result = facet_result or {"facets_extracted": 0, "facets_failed": 0}

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
                    embeddings_generated = %s,
                    embeddings_failed = %s,
                    facets_extracted = %s,
                    facets_failed = %s,
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
                embedding_result.get("embeddings_generated", 0),
                embedding_result.get("embeddings_failed", 0),
                facet_result.get("facets_extracted", 0),
                facet_result.get("facets_failed", 0),
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
    embedding_result: Optional[dict] = None,
    facet_result: Optional[dict] = None,
):
    """Finalize a run that was stopped gracefully."""
    from src.db.connection import get_connection

    theme_result = theme_result or {"themes_extracted": 0, "themes_new": 0}
    story_result = story_result or {"stories_created": 0, "orphans_created": 0}
    embedding_result = embedding_result or {"embeddings_generated": 0, "embeddings_failed": 0}
    facet_result = facet_result or {"facets_extracted": 0, "facets_failed": 0}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pipeline_runs SET
                    completed_at = %s,
                    conversations_fetched = %s,
                    conversations_filtered = %s,
                    conversations_classified = %s,
                    conversations_stored = %s,
                    embeddings_generated = %s,
                    embeddings_failed = %s,
                    facets_extracted = %s,
                    facets_failed = %s,
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
                embedding_result.get("embeddings_generated", 0),
                embedding_result.get("embeddings_failed", 0),
                facet_result.get("facets_extracted", 0),
                facet_result.get("facets_failed", 0),
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
    story stats, current phase, and any errors/warnings (#104).

    Poll this endpoint to track long-running pipelines.
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, started_at, completed_at, date_from, date_to,
                   conversations_fetched, conversations_filtered,
                   conversations_classified, conversations_stored,
                   embeddings_generated, embeddings_failed,
                   current_phase, auto_create_stories,
                   themes_extracted, themes_new, themes_filtered,
                   stories_created, orphans_created, stories_ready,
                   status, error_message, errors, warnings
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

    # Parse JSONB fields (may be None for pre-migration runs)
    errors = row.get("errors") or []
    warnings = row.get("warnings") or []

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
        embeddings_generated=row.get("embeddings_generated") or 0,  # #106
        embeddings_failed=row.get("embeddings_failed") or 0,  # #106
        themes_extracted=row["themes_extracted"] or 0,
        themes_new=row["themes_new"] or 0,
        themes_filtered=row.get("themes_filtered") or 0,  # #104
        stories_created=row["stories_created"] or 0,
        orphans_created=row["orphans_created"] or 0,
        stories_ready=row["stories_ready"] or False,
        status=row["status"],
        error_message=row["error_message"],
        errors=errors,  # #104
        warnings=warnings,  # #104
        duration_seconds=round(duration, 1) if duration else None,
    )


@router.get("/status/{run_id}/preview", response_model=DryRunPreview)
def get_dry_run_preview(run_id: int, db=Depends(get_db)):
    """
    Get dry run classification preview for a specific pipeline run.

    Returns preview data including:
    - Classification breakdown by type and confidence
    - Sample conversations (5-10 representative samples)
    - Top themes with counts
    - Total classified count

    **Returns 404 if:**
    - Run doesn't exist
    - Run was not a dry run
    - Preview has expired (server restart or cleanup)

    Preview data is stored in memory and limited to last 5 dry runs.
    """
    # First check if the run exists
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, status, conversations_stored
            FROM pipeline_runs
            WHERE id = %s
        """, (run_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline run {run_id} not found"
        )

    # Check if this was a dry run (stored == 0 indicates dry run)
    # Note: Could also be a run that found 0 conversations
    if row["conversations_stored"] is not None and row["conversations_stored"] > 0:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline run {run_id} was not a dry run (conversations were stored)"
        )

    # Check if preview is available in memory
    preview = _dry_run_previews.get(run_id)
    if not preview:
        raise HTTPException(
            status_code=404,
            detail=f"Preview for pipeline run {run_id} not found. "
            f"Preview may have expired (server restart) or been cleaned up."
        )

    return preview


@router.get("/history", response_model=List[PipelineRunListItem])
def get_pipeline_history(
    db=Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Get list of recent pipeline runs.

    Returns runs ordered by start time (newest first).
    Includes phase tracking, story creation stats, and error count (#104).
    """
    with db.cursor() as cur:
        cur.execute("""
            SELECT id, started_at, completed_at,
                   conversations_fetched, conversations_classified, conversations_stored,
                   embeddings_generated,
                   current_phase, themes_extracted, stories_created, stories_ready,
                   status, COALESCE(jsonb_array_length(errors), 0) as error_count
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
            embeddings_generated=row.get("embeddings_generated") or 0,  # #106
            themes_extracted=row["themes_extracted"] or 0,
            stories_created=row["stories_created"] or 0,
            stories_ready=row["stories_ready"] or False,
            error_count=row.get("error_count") or 0,  # #104
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
