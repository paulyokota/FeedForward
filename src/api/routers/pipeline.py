"""
Pipeline Control Endpoints

Start, monitor, and manage pipeline execution.
Supports hybrid pipeline with classification, theme extraction, and story creation phases.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

import anyio

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
from src.story_tracking.services.orphan_integration import OrphanIntegrationService

# Optional: ConfidenceScorer for quality gates (Issue #161)
try:
    from src.confidence_scorer import ConfidenceScorer
    CONFIDENCE_SCORER_AVAILABLE = True
except ImportError:
    ConfidenceScorer = None
    CONFIDENCE_SCORER_AVAILABLE = False

# Optional: ImplementationContextService for hybrid context (Issue #180)
try:
    from src.story_tracking.services.implementation_context_service import (
        ImplementationContextService,
    )
    from src.research.unified_search import UnifiedSearchService
    IMPLEMENTATION_CONTEXT_AVAILABLE = True
except ImportError:
    ImplementationContextService = None
    UnifiedSearchService = None
    IMPLEMENTATION_CONTEXT_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Theme Extraction Type Filtering (Issue #165)
# =============================================================================
# TODO: Replace keyword-based filtering with subtype-based filtering when
# Stage 2 classifier supports stable subtypes.

import re

# Types that always pass theme extraction filter
THEME_EXTRACTION_ALWAYS_ALLOWED = {'product_issue', 'feature_request', 'how_to_question'}

# Types that require actionable keywords to pass filter
THEME_EXTRACTION_CONDITIONAL = {'account_issue', 'configuration_help'}

# Keywords indicating actionable technical issues (not general account support)
# Organized by category for maintainability
# PR review fix: Include common variants with digits/underscores (oauth2, api_key, etc.)
ACTIONABLE_KEYWORDS = frozenset({
    # Authentication (including oauth2 variant)
    'oauth', 'oauth2', 'auth', 'authorize', 'authorization', 'bearer', 'jwt',
    # Tokens & Credentials (including underscore variants)
    'token', 'tokens', 'access_token', 'refresh_token', 'api_key', 'api_keys',
    'credential', 'credentials', 'refresh',
    # Integration (including hyphenated/underscore variants)
    'api', 'integration', 'integrations', 'webhook', 'webhooks',
    'api_webhook', 'api_integration',
    # Permissions
    'permissions', 'permission', 'scope', 'scopes',
    # Security/TLS
    'ssl', 'tls', 'certificate', 'cors',
})

# Pre-compile regex pattern for keyword matching
# PR review fix: Use word boundary at START only, allow trailing digits/underscores/hyphens
# This matches "oauth2", "api_key", "refresh_token", "api-webhook" correctly
_ACTIONABLE_PATTERN = re.compile(
    r'(?<![a-zA-Z])(' + '|'.join(re.escape(kw) for kw in ACTIONABLE_KEYWORDS) + r')(?![a-zA-Z])',
    re.IGNORECASE
)


def is_actionable_for_theme_extraction(
    issue_type: str,
    support_insights: dict | None,
    source_body: str | None,
    full_conversation: str | None,
) -> bool:
    """
    Determine if a conversation should be included in theme extraction.

    Args:
        issue_type: The conversation type (stage2_type or stage1_type)
        support_insights: Extracted insights from Stage 2 (may be None or empty)
        source_body: The initial customer message
        full_conversation: Complete conversation text (fallback for keyword scan)

    Returns:
        True if the conversation should be processed for theme extraction
    """
    # Always-allowed types pass unconditionally
    if issue_type in THEME_EXTRACTION_ALWAYS_ALLOWED:
        return True

    # Non-conditional types are filtered out
    if issue_type not in THEME_EXTRACTION_CONDITIONAL:
        return False

    # For conditional types, check for actionable keywords using word boundary matching
    # (Review fix: use regex to avoid substring false positives like "auth" in "authenticated")

    # Priority 1: Check support_insights.products_mentioned and features_mentioned
    if support_insights:
        products = support_insights.get('products_mentioned', []) or []
        features = support_insights.get('features_mentioned', []) or []
        insights_text = ' '.join(products + features)

        if _ACTIONABLE_PATTERN.search(insights_text):
            return True

    # Priority 2: Fallback - scan customer message and full conversation
    fallback_text = (full_conversation or source_body or '')

    if fallback_text and _ACTIONABLE_PATTERN.search(fallback_text):
        return True

    # No actionable signals found - filter out
    return False


router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Track active runs (in-memory for MVP, could use Redis for production)
# States: running, stopping, stopped, completed, failed
_active_runs: dict[int, str] = {}  # run_id -> status

# Terminal states that can be cleaned up
_TERMINAL_STATES = {"stopped", "completed", "failed"}

# Issue #148 fix S1: Limit _active_runs size to prevent unbounded growth
# This caps memory usage even if cleanup is delayed
_MAX_ACTIVE_RUNS = 100

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
    """Remove terminal (completed/failed/stopped) runs to prevent memory leak.

    Issue #148 fix S1: Also enforces size limit on _active_runs to prevent
    unbounded growth even if cleanup is delayed.
    """
    terminal_ids = [rid for rid, status in _active_runs.items() if status in _TERMINAL_STATES]
    for rid in terminal_ids:
        del _active_runs[rid]
        # Also cleanup associated dry run preview if it exists
        # This prevents memory leak from orphaned previews
        if rid in _dry_run_previews:
            del _dry_run_previews[rid]

    # Issue #148 fix S1: If still over limit, remove oldest entries
    if len(_active_runs) > _MAX_ACTIVE_RUNS:
        # Remove oldest entries (lowest run_ids) that are in terminal state
        sorted_ids = sorted(_active_runs.keys())
        for rid in sorted_ids:
            if len(_active_runs) <= _MAX_ACTIVE_RUNS:
                break
            if _active_runs.get(rid) in _TERMINAL_STATES:
                del _active_runs[rid]
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
            # Issue #139: Include customer_digest from support_insights for better embedding quality
            cur.execute("""
                SELECT c.id, c.source_body,
                       c.support_insights->>'customer_digest' as customer_digest
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

    # Prepare conversations for embedding service (Issue #139: include digest)
    conversations = [
        {
            "id": row["id"],
            "source_body": row["source_body"],
            "customer_digest": row["customer_digest"],
        }
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
            # Issue #139: Include customer_digest from support_insights for better facet quality
            cur.execute("""
                SELECT c.id, c.source_body,
                       c.support_insights->>'customer_digest' as customer_digest
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

    # Prepare conversations for facet service (Issue #139: include digest)
    conversations = [
        {
            "id": row["id"],
            "source_body": row["source_body"],
            "customer_digest": row["customer_digest"],
        }
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


async def _run_theme_extraction_async(
    run_id: int,
    stop_checker: Callable[[], bool],
    concurrency: int = 20,
) -> dict:
    """
    Run theme extraction with semaphore-controlled concurrency (Issue #148).

    Parallelizes theme extraction to reduce processing time from ~60 min
    (sequential) to ~5-10 min (parallel) for 500 conversations.

    Args:
        run_id: Pipeline run ID
        stop_checker: Callback to check for stop signal
        concurrency: Max parallel extractions (default 20, matches OpenAI rate limits)

    Returns:
        dict with themes_extracted, themes_new, themes_filtered counts and warnings
    """
    from src.db.connection import get_connection
    from src.theme_extractor import ThemeExtractor
    from src.theme_quality import filter_themes_by_quality
    from src.db.models import Conversation
    from psycopg2.extras import RealDictCursor

    logger.info(f"Run {run_id}: Starting async theme extraction (concurrency={concurrency})")

    # Get conversations classified in this run (Issue #165: expanded types)
    # Fetch all potentially-actionable types, then filter in Python
    all_allowed_types = THEME_EXTRACTION_ALWAYS_ALLOWED | THEME_EXTRACTION_CONDITIONAL
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT c.id, c.created_at, c.source_body, c.source_url,
                       COALESCE(c.stage2_type, c.stage1_type) as issue_type,
                       c.sentiment, c.priority, c.churn_risk,
                       c.support_insights as support_insights,
                       c.support_insights->>'customer_digest' as customer_digest,
                       c.support_insights->>'full_conversation' as full_conversation
                FROM conversations c
                JOIN pipeline_runs pr ON pr.id = %s
                WHERE (c.pipeline_run_id = %s
                       OR (c.pipeline_run_id IS NULL AND c.classified_at >= pr.started_at))
                  AND COALESCE(c.stage2_type, c.stage1_type) = ANY(%s)
                ORDER BY c.created_at DESC
            """, (run_id, run_id, list(all_allowed_types)))
            rows = cur.fetchall()

    if not rows:
        logger.info(f"Run {run_id}: No actionable conversations to extract themes from")
        return {"themes_extracted": 0, "themes_new": 0, "themes_filtered": 0, "conditional_filtered": 0, "warnings": []}

    # Map new classifier types to legacy IssueType for Conversation model
    # Issue #165: Added account_issue and configuration_help mappings
    NEW_TO_LEGACY_TYPE = {
        "product_issue": "bug_report",
        "feature_request": "feature_request",
        "how_to_question": "product_question",
        "account_issue": "other",  # No direct legacy equivalent
        "configuration_help": "other",  # No direct legacy equivalent
    }

    # Build conversation objects and context maps
    conversations = []
    conversation_digests = {}
    conversation_full_texts = {}
    conditional_filtered_count = 0  # Issue #165: Track filtered conditional types

    for row in rows:
        if stop_checker():
            logger.info(f"Run {run_id}: Stop signal received during theme extraction setup")
            return {"themes_extracted": 0, "themes_new": 0, "themes_filtered": 0, "conditional_filtered": 0, "warnings": []}

        new_type = row["issue_type"]

        # Issue #165: Apply Python-side filtering for conditional types
        support_insights = row.get("support_insights") or {}
        source_body = row.get("source_body")
        full_conversation = row.get("full_conversation")

        if not is_actionable_for_theme_extraction(
            issue_type=new_type,
            support_insights=support_insights,
            source_body=source_body,
            full_conversation=full_conversation,
        ):
            conditional_filtered_count += 1
            continue

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

        if row.get("customer_digest"):
            conversation_digests[row["id"]] = row["customer_digest"]
        if row.get("full_conversation"):
            conversation_full_texts[row["id"]] = row["full_conversation"]

    if conditional_filtered_count > 0:
        logger.info(
            f"Run {run_id}: Filtered {conditional_filtered_count} non-actionable "
            f"account_issue/configuration_help conversations"
        )

    # Check if all conversations were filtered out
    if not conversations:
        logger.info(f"Run {run_id}: No actionable conversations after filtering")
        return {"themes_extracted": 0, "themes_new": 0, "themes_filtered": 0, "conditional_filtered": 0, "warnings": []}

    logger.info(f"Run {run_id}: Extracting themes from {len(conversations)} conversations (parallel)")

    # Create semaphore and extractor
    semaphore = asyncio.Semaphore(concurrency)
    extractor = ThemeExtractor()
    extractor.clear_session_signatures()

    async def extract_one(conv: Conversation) -> Optional[tuple]:
        """Extract theme for one conversation with semaphore control."""
        if stop_checker():
            return None

        async with semaphore:
            try:
                customer_digest = conversation_digests.get(conv.id)
                full_conversation = conversation_full_texts.get(conv.id)

                theme = await extractor.extract_async(
                    conv,
                    strict_mode=False,
                    customer_digest=customer_digest,
                    full_conversation=full_conversation,
                    use_full_conversation=True,
                )

                # Check if new theme
                is_new = False
                if not theme.issue_signature.startswith("unclassified"):
                    existing = extractor.get_existing_signatures(theme.product_area)
                    is_new = not any(
                        s["signature"] == theme.issue_signature for s in existing
                    )

                logger.debug(f"Extracted theme: {theme.issue_signature} for conv {conv.id}")
                return (theme, is_new)

            except Exception as e:
                # Issue #148 fix: Log with traceback for debugging (Q2/R2)
                logger.warning(f"Failed to extract theme for {conv.id}: {e}", exc_info=True)
                return None

    # Run all extractions in parallel with semaphore control
    tasks = [extract_one(conv) for conv in conversations]
    results = await asyncio.gather(*tasks)

    # Collect results and track failures (Issue #148 fix: Q2/R2)
    all_themes = []
    themes_new = 0
    extraction_failed = 0
    for result in results:
        if result is not None:
            theme, is_new = result
            all_themes.append(theme)
            if is_new:
                themes_new += 1
        else:
            extraction_failed += 1

    logger.info(
        f"Run {run_id}: Extracted {len(all_themes)} themes ({themes_new} new), "
        f"{extraction_failed} failed"
    )

    # Apply quality gates
    high_quality_themes, low_quality_themes, warnings = filter_themes_by_quality(all_themes)

    if low_quality_themes:
        logger.info(
            f"Run {run_id}: Quality gates filtered {len(low_quality_themes)} of "
            f"{len(all_themes)} themes"
        )

    # Store themes in database
    from psycopg2.extras import Json, execute_values
    from src.theme_quality import check_theme_quality
    from src.utils.normalize import normalize_product_area, canonicalize_component

    context_logs_to_insert: list[tuple] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for theme in high_quality_themes:
                quality_result = check_theme_quality(
                    issue_signature=theme.issue_signature,
                    matched_existing=theme.matched_existing,
                    match_confidence=theme.match_confidence or "low",
                )

                product_area_raw = theme.product_area
                component_raw = theme.component
                product_area_normalized = normalize_product_area(product_area_raw)
                component_canonical = canonicalize_component(component_raw, product_area_normalized)

                cur.execute("""
                    INSERT INTO themes (
                        conversation_id, product_area, component, issue_signature,
                        user_intent, symptoms, affected_flow, root_cause_hypothesis,
                        pipeline_run_id, quality_score, quality_details,
                        product_area_raw, component_raw,
                        diagnostic_summary, key_excerpts,
                        resolution_action, root_cause, solution_provided, resolution_category
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        product_area_raw = EXCLUDED.product_area_raw,
                        component_raw = EXCLUDED.component_raw,
                        diagnostic_summary = EXCLUDED.diagnostic_summary,
                        key_excerpts = EXCLUDED.key_excerpts,
                        resolution_action = EXCLUDED.resolution_action,
                        root_cause = EXCLUDED.root_cause,
                        solution_provided = EXCLUDED.solution_provided,
                        resolution_category = EXCLUDED.resolution_category,
                        extracted_at = NOW()
                    RETURNING id
                """, (
                    theme.conversation_id,
                    product_area_normalized,
                    component_canonical,
                    theme.issue_signature,
                    theme.user_intent,
                    Json(theme.symptoms) if theme.symptoms else None,
                    theme.affected_flow,
                    theme.root_cause_hypothesis,
                    run_id,
                    quality_result.quality_score,
                    Json(asdict(quality_result)),
                    product_area_raw,
                    component_raw,
                    theme.diagnostic_summary,
                    Json(theme.key_excerpts) if theme.key_excerpts else None,
                    theme.resolution_action,
                    theme.root_cause,
                    theme.solution_provided,
                    theme.resolution_category,
                ))

                theme_id = cur.fetchone()[0]

                # Collect context usage logs for batch insert
                if theme.context_used or theme.context_gaps:
                    context_logs_to_insert.append((
                        theme_id,
                        theme.conversation_id,
                        run_id,
                        Json(theme.context_used) if theme.context_used else None,
                        Json(theme.context_gaps) if theme.context_gaps else None,
                    ))

            # Batch insert context usage logs
            if context_logs_to_insert:
                execute_values(
                    cur,
                    """
                    INSERT INTO context_usage_logs (theme_id, conversation_id, pipeline_run_id, context_used, context_gaps)
                    VALUES %s
                    ON CONFLICT (theme_id) DO UPDATE SET
                        context_used = EXCLUDED.context_used,
                        context_gaps = EXCLUDED.context_gaps
                    """,
                    context_logs_to_insert,
                )

        conn.commit()

    return {
        "themes_extracted": len(high_quality_themes),
        "themes_new": themes_new,
        "themes_filtered": len(low_quality_themes),
        "conditional_filtered": conditional_filtered_count,  # PR review fix: surface #165 filtering
        "extraction_failed": extraction_failed,  # Issue #148 fix: Q2/R2
        "warnings": warnings,
    }


def _run_theme_extraction(
    run_id: int,
    stop_checker: Callable[[], bool],
    concurrency: int = 20,
) -> dict:
    """
    Run theme extraction on classified conversations from this pipeline run.

    Issue #148: Now uses async parallel extraction for performance.

    Returns dict with themes_extracted, themes_new, themes_filtered counts and warnings.

    Quality Gates (#104):
    - Filters themes below confidence threshold
    - Filters themes not in vocabulary with low confidence
    - Logs filtered themes for observability
    """
    return asyncio.run(_run_theme_extraction_async(run_id, stop_checker, concurrency))



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

    # Get themes from this run (including Smart Digest fields for PM Review - Issue #144)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT t.issue_signature, t.product_area, t.component,
                       t.conversation_id, t.user_intent, t.symptoms,
                       t.affected_flow, c.source_body, c.issue_type,
                       t.diagnostic_summary, t.key_excerpts,
                       t.resolution_action, t.root_cause,
                       t.solution_provided, t.resolution_category,
                       c.contact_email, c.contact_id, c.user_id, c.org_id,
                       c.priority, c.churn_risk,
                       c.created_at  -- Issue #200: Recency gate
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
    # Issue #144: Include Smart Digest fields for PM Review context
    conversation_data: dict[str, dict] = {}
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        # Smart Digest fields (Issue #144): Use for richer PM Review context
        # Fallback to excerpt from source_body when diagnostic_summary is empty
        diagnostic_summary = row.get("diagnostic_summary") or ""
        key_excerpts = row.get("key_excerpts") or []

        conv_dict = {
            "id": row["conversation_id"],
            "issue_signature": row["issue_signature"],
            "product_area": row["product_area"],
            "component": row["component"],
            "user_intent": row["user_intent"],
            "symptoms": row["symptoms"],
            "affected_flow": row["affected_flow"],
            # Keep excerpt for backward compatibility and fallback
            "excerpt": (row["source_body"] or "")[:500],
            "classification_category": row["issue_type"],
            # Smart Digest fields (Issue #144)
            "diagnostic_summary": diagnostic_summary,
            "key_excerpts": key_excerpts,
            # Issue #159: Resolution fields for story content
            "resolution_action": row.get("resolution_action"),
            "root_cause": row.get("root_cause"),
            "solution_provided": row.get("solution_provided"),
            "resolution_category": row.get("resolution_category"),
            # Issue #157: Evidence metadata completeness
            "contact_email": row.get("contact_email"),
            "contact_id": row.get("contact_id"),
            "user_id": row.get("user_id"),
            "org_id": row.get("org_id"),
            # Issue #166: Severity fields for MIN_GROUP_SIZE exception
            "priority": row.get("priority"),
            "churn_risk": row.get("churn_risk"),
            # Issue #200: Recency gate
            "created_at": row.get("created_at"),
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

        # Initialize orphan integration for canonicalization (Issue #155)
        # This ensures orphan signatures are canonicalized via SignatureRegistry,
        # preventing fragmentation of synonymous signatures across pipeline runs.
        # Uses default auto_graduate=True, so orphans graduate to stories at MIN_GROUP_SIZE.
        orphan_integration_service = OrphanIntegrationService(db_connection=conn)

        # Determine dual format settings from environment
        dual_format_enabled = os.environ.get("FEEDFORWARD_DUAL_FORMAT", "true").lower() == "true"
        # ⚠️  READ BEFORE CHANGING: target_repo MUST default to None.
        # "FeedForward" is THIS repo (the pipeline itself), NOT a product repo.
        # Valid product repos are in APPROVED_REPOS: aero, tack, charlotte, ghostwriter, zuck.
        # When target_repo=None, the classifier dynamically suggests the right repo.
        # Hardcoding "FeedForward" here breaks codebase exploration with a validation error.
        target_repo = os.environ.get("FEEDFORWARD_TARGET_REPO") or None

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

        # Initialize ConfidenceScorer for quality gates (Issue #161)
        # Routes low-confidence groups to orphans instead of forcing story creation
        confidence_scorer = None
        if CONFIDENCE_SCORER_AVAILABLE:
            try:
                confidence_scorer = ConfidenceScorer()
                logger.info(f"Run {run_id}: ConfidenceScorer enabled for quality gates")
            except Exception as e:
                logger.warning(
                    f"Run {run_id}: Failed to initialize ConfidenceScorer: {e}. "
                    f"Groups will not be confidence-scored (quality gate disabled)."
                )

        # Initialize ImplementationContextService for hybrid context (Issue #180)
        # Retrieves similar evidence via vector search + synthesizes guidance
        implementation_context_service = None
        if IMPLEMENTATION_CONTEXT_AVAILABLE:
            try:
                import os
                import yaml
                from pathlib import Path

                # Check feature flag
                impl_context_enabled = os.getenv(
                    "IMPLEMENTATION_CONTEXT_ENABLED", "true"
                ).lower() == "true"

                if impl_context_enabled:
                    # Load config from research_search.yaml
                    config_path = Path(__file__).parent.parent.parent.parent / "config" / "research_search.yaml"
                    impl_config = {}
                    if config_path.exists():
                        with open(config_path) as f:
                            full_config = yaml.safe_load(f)
                            impl_config = full_config.get("implementation_context", {})

                    # Initialize UnifiedSearchService (uses same config file for embeddings)
                    search_service = UnifiedSearchService()

                    # Initialize ImplementationContextService with config values
                    implementation_context_service = ImplementationContextService(
                        search_service=search_service,
                        model=impl_config.get("model", "gpt-4o-mini"),
                        top_k=impl_config.get("top_k", 10),
                        min_similarity=impl_config.get("min_similarity", 0.5),
                        timeout=impl_config.get("timeout", 15),
                    )
                    logger.info(
                        f"Run {run_id}: ImplementationContextService enabled "
                        f"(top_k={impl_config.get('top_k', 10)}, "
                        f"min_similarity={impl_config.get('min_similarity', 0.5)})"
                    )
            except Exception as e:
                logger.warning(
                    f"Run {run_id}: Failed to initialize ImplementationContextService: {e}. "
                    f"Implementation context generation will be skipped."
                )

        story_creation_service = StoryCreationService(
            story_service=story_service,
            orphan_service=orphan_service,
            evidence_service=evidence_service,
            orphan_integration_service=orphan_integration_service,
            confidence_scorer=confidence_scorer,  # Issue #161: Enable quality gate
            dual_format_enabled=dual_format_enabled,
            target_repo=target_repo,
            pm_review_service=pm_review_service,
            pm_review_enabled=pm_review_enabled,  # PM review works for both signature and hybrid clustering
            implementation_context_service=implementation_context_service,  # Issue #180
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


async def _run_pipeline_async(
    run_id: int,
    days: int,
    max_conversations: Optional[int],
    dry_run: bool,
    concurrency: int,
    auto_create_stories: bool = False,
):
    """
    Async wrapper that runs the pipeline task in a thread pool.

    This keeps the FastAPI event loop responsive while the pipeline executes
    blocking I/O operations (OpenAI API calls, database queries).

    Issue #148: The previous implementation used BackgroundTasks.add_task()
    with a sync function, which blocked the event loop during theme extraction
    (500+ sequential OpenAI calls = 40-80+ minutes of blocking).

    By using anyio.to_thread.run_sync(), the blocking work runs in a separate
    thread, allowing the event loop to continue serving HTTP requests.
    """
    await anyio.to_thread.run_sync(
        lambda: _run_pipeline_task(
            run_id=run_id,
            days=days,
            max_conversations=max_conversations,
            dry_run=dry_run,
            concurrency=concurrency,
            auto_create_stories=auto_create_stories,
        ),
        # abandon_on_cancel=True allows graceful shutdown when stop signal received
        # (Note: 'cancellable' was deprecated in anyio 4.1.0+)
        abandon_on_cancel=True,
    )


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
    import os
    from pathlib import Path
    from datetime import datetime, timezone
    from dotenv import load_dotenv

    # Issue #189: Ensure env vars are loaded before IntercomClient instantiation.
    # uvicorn --reload can change working directory, causing relative .env paths to fail.
    # Use resolved absolute path anchored to this file's location (4 levels up from
    # src/api/routers/pipeline.py → project root where .env lives).
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    load_dotenv(env_path)

    # Log token presence (not value) for debugging pipeline startup issues
    token_present = os.getenv("INTERCOM_ACCESS_TOKEN") is not None
    logger.info(f"Run {run_id}: INTERCOM_ACCESS_TOKEN present: {token_present}")

    # Fail fast if token missing - prevents pipeline from appearing to start successfully
    # then getting stuck at fetched=0 when IntercomClient can't authenticate (Issue #189)
    if not token_present:
        logger.error(f"Run {run_id}: INTERCOM_ACCESS_TOKEN not found. Checked .env at: {env_path}")
        _finalize_failed_run(run_id, "INTERCOM_ACCESS_TOKEN not configured")
        return

    from src.db.connection import get_connection
    from src.classification_pipeline import run_pipeline_async

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

        # Issue #148: Pass concurrency for parallel theme extraction
        theme_result = _run_theme_extraction(run_id, stop_checker, concurrency=concurrency)

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
        _finalize_failed_run(run_id, str(e))
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


def _finalize_failed_run(run_id: int, error_message: str) -> None:
    """Finalize a run that failed with an error.

    Used by both the fail-fast check (Issue #189) and the exception handler.
    """
    from src.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pipeline_runs SET
                    completed_at = %s,
                    status = 'failed',
                    error_message = %s
                WHERE id = %s
            """, (datetime.now(timezone.utc), error_message, run_id))

    logger.info(f"Run {run_id}: Pipeline failed - {error_message}")
    _active_runs[run_id] = "failed"


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
    # Issue #148: Use async wrapper to run pipeline in thread pool,
    # keeping the event loop responsive during long-running operations
    background_tasks.add_task(
        _run_pipeline_async,
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
