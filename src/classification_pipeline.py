#!/usr/bin/env python3
"""
Two-Stage Classification Pipeline Integration.

Orchestrates:
1. Fetching conversations from multiple sources (Intercom, Coda)
2. Running Stage 1 classification (fast routing)
3. Running Stage 2 classification (refined analysis with support context)
4. Storing results in database with source tracking

Supports both sync (simple) and async (fast) modes:
- Sync: Sequential processing, good for debugging
- Async: Parallel classification with semaphore, ~10-20x faster

Multi-source support:
- --source intercom: Process Intercom support conversations (default)
- --source coda: Process Coda research data
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI, AsyncOpenAI
from intercom_client import IntercomClient, IntercomConversation
from classifier_stage1 import classify_stage1, STAGE1_PROMPT, get_url_context_hint
from classifier_stage2 import classify_stage2, STAGE2_PROMPT
from db.classification_storage import (
    store_classification_result,
    store_classification_results_batch
)
from db.connection import create_pipeline_run
from db.models import PipelineRun
from adapters import CodaAdapter, IntercomAdapter, NormalizedConversation
from digest_extractor import (
    extract_customer_messages,
    build_customer_digest,
    build_full_conversation_text,
)
from src.context_provider import get_context_provider

# Async OpenAI client for parallel processing
async_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Issue #202: Checkpoint update frequency (overrideable via env var for tests)
CHECKPOINT_UPDATE_FREQUENCY = int(os.getenv("CHECKPOINT_UPDATE_FREQUENCY", "50"))


def _parse_env_int(name: str, default: int, min_val: int, max_val: int) -> int:
    """Parse an integer environment variable with bounds checking.

    Issue #209: Used for streaming batch configuration.

    Args:
        name: Environment variable name
        default: Default value if not set or invalid
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)

    Returns:
        Parsed integer within bounds, or default if invalid
    """
    try:
        val = int(os.getenv(name, str(default)))
        if not (min_val <= val <= max_val):
            logger.warning(f"{name}={val} out of bounds [{min_val}, {max_val}], using {default}")
            return default
        return val
    except ValueError:
        logger.warning(f"{name} invalid, using {default}")
        return default


# Issue #209: Streaming batch mode for safe historical backfills
# When enabled, processes in batches with cursor-based checkpoint/resume
PIPELINE_STREAMING_BATCH_ENABLED = os.getenv("PIPELINE_STREAMING_BATCH", "false").lower() == "true"
PIPELINE_STREAMING_BATCH_SIZE = _parse_env_int("PIPELINE_STREAMING_BATCH_SIZE", 50, 10, 500)


def _save_classification_checkpoint(
    run_id: int,
    cursor: Optional[str],
    fetched: int,
    classified: int = 0,
    stored: int = 0,
) -> None:
    """Save classification phase checkpoint for resumability.

    Issue #202: Called periodically during storage loop.

    Args:
        run_id: Pipeline run ID
        cursor: Current Intercom pagination cursor (for observability)
        fetched: Total conversations fetched from Intercom
        classified: Number classified so far
        stored: Number stored so far (represents actual progress)
    """
    from datetime import timezone as tz
    from src.api.routers.pipeline import _save_checkpoint, _active_checkpoints

    checkpoint = {
        "phase": "classification",
        "intercom_cursor": cursor,
        "conversations_processed": stored,  # Progress = durably stored count
        "updated_at": datetime.now(tz.utc).isoformat(),
        "counts": {
            "fetched": fetched,
            "classified": classified,
            "stored": stored,
        }
    }

    # Update in-memory checkpoint for finalize functions
    _active_checkpoints[run_id] = checkpoint

    # Persist to database
    try:
        _save_checkpoint(run_id, checkpoint)
        logger.debug(f"Run {run_id}: Checkpoint saved at {stored} stored conversations")
    except Exception as e:
        logger.warning(f"Run {run_id}: Checkpoint save failed: {e}")


def _clear_checkpoint(run_id: int) -> None:
    """Clear checkpoint after classification completes successfully.

    Issue #202: Signals that classification is complete and not resumable.
    Later phases (embeddings, facets, themes) are not resumable in MVP.
    """
    from src.api.routers.pipeline import _save_checkpoint, _active_checkpoints

    # Clear from in-memory tracking
    _active_checkpoints.pop(run_id, None)

    # Clear in database
    try:
        _save_checkpoint(run_id, {})
        logger.info(f"Run {run_id}: Checkpoint cleared after classification complete")
    except Exception as e:
        logger.warning(f"Run {run_id}: Checkpoint clear failed: {e}")


def _get_stored_conversation_ids(pipeline_run_id: int) -> set:
    """Get conversation IDs already stored for this pipeline run.

    Issue #202: Used on resume to skip classification for already-stored conversations.
    This preserves the expensive classification work done before interruption.

    Returns:
        Set of conversation_id strings already in the database for this run.
    """
    from src.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT conversation_id
                    FROM conversations
                    WHERE pipeline_run_id = %s
                """, (pipeline_run_id,))
                return {row[0] for row in cur.fetchall()}
    except Exception as e:
        logger.warning(f"Failed to get stored conversation IDs: {e}")
        return set()


def extract_support_messages(raw_conversation: dict) -> List[str]:
    """
    Extract support team messages from conversation parts.

    Returns list of support message bodies.
    """
    support_messages = []

    conversation_parts = raw_conversation.get("conversation_parts", {})
    parts = conversation_parts.get("conversation_parts", []) if isinstance(conversation_parts, dict) else []

    for part in parts:
        part_type = part.get("part_type")
        author = part.get("author", {})
        author_type = author.get("type")

        # Support messages are from admins or bots
        if author_type in ("admin", "bot") and part_type == "comment":
            body = part.get("body", "")
            if body:
                support_messages.append(body)

    return support_messages


def classify_conversation(
    parsed: IntercomConversation,
    raw_conversation: dict,
) -> Dict[str, Any]:
    """
    Run two-stage classification on a conversation (sync version).

    Returns:
        Dictionary with stage1_result, stage2_result, support_messages, resolution_signal, support_insights
    """
    # Extract support messages
    support_messages = extract_support_messages(raw_conversation)

    # Extract customer messages and build digest (Issue #139)
    customer_messages = extract_customer_messages(raw_conversation)
    customer_digest = build_customer_digest(parsed.source_body, customer_messages)

    # Issue #144: Build full conversation text for theme extraction
    full_conversation_text = build_full_conversation_text(raw_conversation)

    # Stage 1: Fast routing (always runs)
    logger.info("[Stage 1] Classifying conversation %s...", parsed.id)
    stage1_result = classify_stage1(
        customer_message=parsed.source_body,
        source_type=parsed.source_type
    )

    logger.info("  → %s (%s confidence)", stage1_result['conversation_type'], stage1_result['confidence'])

    # Stage 2: Refined analysis (only if support responded)
    stage2_result = None

    # Initialize support_insights with customer digest and full conversation (always present)
    # Issue #144: full_conversation enables richer theme extraction
    # Issue #146: resolution_analysis and knowledge removed - now extracted by LLM in theme extractor
    support_insights = {
        "customer_digest": customer_digest,
        "full_conversation": full_conversation_text,
    }

    if support_messages:
        logger.info("[Stage 2] Found %d support messages, running refined analysis...", len(support_messages))

        stage2_result = classify_stage2(
            customer_message=parsed.source_body,
            support_messages=support_messages,
            source_url=parsed.source_url,
            stage1_type=stage1_result["conversation_type"]
        )

        if stage2_result.get("changed_from_stage_1"):
            logger.info("  → Classification changed: %s → %s", stage1_result['conversation_type'], stage2_result['conversation_type'])
        else:
            logger.info("  → Classification confirmed: %s (%s confidence)", stage2_result['conversation_type'], stage2_result['confidence'])

    return {
        "stage1_result": stage1_result,
        "stage2_result": stage2_result,
        "support_messages": support_messages,
        "support_insights": support_insights,
    }


async def classify_stage1_async(
    customer_message: str,
    source_type: str = None,
    source_url: str = None,
    semaphore: asyncio.Semaphore = None,
) -> Dict[str, Any]:
    """Async Stage 1 classification."""
    import json as json_module

    async with semaphore:
        url_context_hint = get_url_context_hint(source_url) if source_url else ""

        prompt = STAGE1_PROMPT.format(
            source_type=source_type or "unknown",
            source_url=source_url or "N/A",
            customer_message=customer_message[:2000],
            url_context_hint=url_context_hint,
        )

        try:
            response = await asyncio.wait_for(
                async_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a customer support classifier. Respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    response_format={"type": "json_object"}
                ),
                timeout=30.0  # 30 second timeout
            )

            result = json_module.loads(response.choices[0].message.content)

            # Add derived fields
            result["routing_priority"] = "high" if result.get("urgency") in ("critical", "high") else "normal"
            result["auto_response_eligible"] = result.get("conversation_type") in ("spam", "general_inquiry")
            result["routing_team"] = _get_routing_team(result.get("conversation_type"))

            return result
        except asyncio.TimeoutError:
            return {
                "conversation_type": "general_inquiry",
                "confidence": "low",
                "reasoning": "Classification timeout (>30s)",
                "error": "timeout"
            }
        except Exception as e:
            return {
                "conversation_type": "general_inquiry",
                "confidence": "low",
                "reasoning": f"Classification error: {str(e)}",
                "error": str(e)
            }


async def classify_stage2_async(
    customer_message: str,
    support_messages: List[str],
    stage1_type: str,
    source_url: str = None,
    semaphore: asyncio.Semaphore = None,
) -> Dict[str, Any]:
    """Async Stage 2 classification."""
    import json as json_module

    # Issue #160: Fetch context in parallel BEFORE entering semaphore
    # This allows context fetch to run concurrently with other classifications
    context_provider = get_context_provider()
    help_context, shortcut_context = await context_provider.get_all_context(customer_message)

    # Review fix: Log context retrieval for observability
    if help_context or shortcut_context:
        logger.debug(f"Context retrieved: help={len(help_context)} chars, shortcut={len(shortcut_context)} chars")

    # Review fix: Handle None semaphore gracefully (allows standalone testing)
    if semaphore is None:
        logger.warning("classify_stage2_async called without semaphore - no rate limiting")
        semaphore = asyncio.Semaphore(1)  # Create dummy semaphore

    async with semaphore:
        # Format support messages
        support_text = "\n\n".join([f"[Support {i+1}]: {msg[:1000]}" for i, msg in enumerate(support_messages[:5])])

        prompt = STAGE2_PROMPT.format(
            source_type="conversation",
            source_url=source_url or "N/A",
            stage1_type=stage1_type,
            customer_message=customer_message[:2000],
            support_messages=support_text,
            help_article_context=help_context,
            shortcut_story_context=shortcut_context,
        )

        try:
            response = await asyncio.wait_for(
                async_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a customer support analyst. Respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=800,
                    response_format={"type": "json_object"}
                ),
                timeout=30.0  # 30 second timeout
            )

            result = json_module.loads(response.choices[0].message.content)
            result["changed_from_stage_1"] = result.get("conversation_type") != stage1_type

            return result
        except asyncio.TimeoutError:
            return {
                "conversation_type": stage1_type,
                "confidence": "low",
                "reasoning": "Stage 2 timeout (>30s)",
                "changed_from_stage_1": False,
                "error": "timeout"
            }
        except Exception as e:
            return {
                "conversation_type": stage1_type,
                "confidence": "low",
                "reasoning": f"Stage 2 error: {str(e)}",
                "changed_from_stage_1": False,
                "error": str(e)
            }


def _get_routing_team(conversation_type: str) -> str:
    """Get routing team based on conversation type."""
    routing_map = {
        "billing_question": "billing_team",
        "account_issue": "account_team",
        "product_issue": "technical_support",
        "feature_request": "product_team",
        "configuration_help": "technical_support",
        "how_to_question": "support_team",
        "general_inquiry": "support_team",
        "spam": "spam_filter",
    }
    return routing_map.get(conversation_type, "support_team")


async def classify_conversation_async(
    parsed: IntercomConversation,
    raw_conversation: dict,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    Run two-stage classification on a conversation (async version).

    Issue #146: Resolution analysis and knowledge extraction removed from classification.
    These are now handled by LLM in theme extractor for better coverage.
    """
    support_messages = extract_support_messages(raw_conversation)

    # Extract customer messages and build digest (Issue #139)
    customer_messages = extract_customer_messages(raw_conversation)
    customer_digest = build_customer_digest(parsed.source_body, customer_messages)

    # Issue #144: Build full conversation text for theme extraction
    full_conversation_text = build_full_conversation_text(raw_conversation)

    # Stage 1
    stage1_result = await classify_stage1_async(
        customer_message=parsed.source_body,
        source_type=parsed.source_type,
        source_url=parsed.source_url,
        semaphore=semaphore,
    )

    # Stage 2 (only if support responded)
    stage2_result = None

    # Initialize support_insights with customer digest and full conversation (always present)
    # Issue #144: full_conversation enables richer theme extraction
    # Issue #146: resolution_analysis and knowledge removed - now extracted by LLM in theme extractor
    support_insights = {
        "customer_digest": customer_digest,
        "full_conversation": full_conversation_text,
    }

    if support_messages:
        # Stage 2 LLM (slow, needs semaphore)
        stage2_result = await classify_stage2_async(
            customer_message=parsed.source_body,
            support_messages=support_messages,
            stage1_type=stage1_result["conversation_type"],
            source_url=parsed.source_url,
            semaphore=semaphore,
        )

    return {
        "conversation_id": parsed.id,
        "created_at": parsed.created_at,
        "source_body": parsed.source_body,
        "source_type": parsed.source_type,
        "source_url": parsed.source_url,
        "contact_email": parsed.contact_email,
        "contact_id": parsed.contact_id,
        "stage1_result": stage1_result,
        "stage2_result": stage2_result,
        "support_messages": support_messages,
        "support_insights": support_insights,
    }


def _accumulate_stats(cumulative: Dict[str, Any], batch: Dict[str, Any]) -> None:
    """Accumulate batch stats into cumulative stats.

    Issue #209: Used in streaming batch mode.
    """
    for key in ["fetched", "filtered", "recovered", "classified", "stored",
                "stage2_run", "classification_changed"]:
        cumulative[key] = cumulative.get(key, 0) + batch.get(key, 0)
    # Warnings are appended, not summed
    if batch.get("warnings"):
        cumulative.setdefault("warnings", []).extend(batch["warnings"])


async def _process_streaming_batch(
    batch: List[tuple],
    recovery_candidates: List[tuple],
    client: "IntercomClient",
    session,
    semaphore: asyncio.Semaphore,
    concurrency: int,
    dry_run: bool,
    pipeline_run_id: Optional[int],
) -> Dict[str, Any]:
    """Process a single batch: fetch details → evaluate recovery → classify → store.

    Issue #209: Used in streaming batch mode.

    Args:
        batch: List of (parsed, raw_conv) tuples for quality conversations
        recovery_candidates: List of (parsed, raw_conv, had_template) tuples for recovery
        client: IntercomClient instance
        session: aiohttp session for API calls
        semaphore: Semaphore for concurrency control
        concurrency: Max parallel detail fetches
        dry_run: If True, don't store to database
        pipeline_run_id: Pipeline run ID for storage

    Returns:
        Batch statistics dictionary
    """
    batch_stats = {
        "fetched": len(batch),
        "filtered": 0,  # Always 0 in streaming mode (filtering happens at page level, not batch)
        "recovered": 0,
        "classified": 0,
        "stored": 0,
        "stage2_run": 0,
        "classification_changed": 0,
        "warnings": [],
    }

    if not batch and not recovery_candidates:
        return batch_stats

    # Step 1: Fetch details for batch + recovery candidates (parallel)
    all_to_fetch = list(batch) + [(p, r) for p, r, _ in recovery_candidates]
    detail_semaphore = asyncio.Semaphore(concurrency)

    async def fetch_detail(parsed, raw_conv):
        async with detail_semaphore:
            try:
                full_conv = await client.get_conversation_async(session, parsed.id)
                return (parsed, full_conv)
            except Exception as e:
                logger.warning(f"Failed to fetch details for {parsed.id}: {e}")
                return (parsed, raw_conv)

    tasks = [fetch_detail(p, r) for p, r in all_to_fetch]
    all_results = await asyncio.gather(*tasks)  # Returns list, no conversion needed

    # Split back into batch and recovery
    batch_with_details = all_results[:len(batch)]
    recovery_with_details = all_results[len(batch):]

    # Step 2: Evaluate recovery BEFORE classification (Issue #164 parity)
    for i, (parsed, full_conv) in enumerate(recovery_with_details):
        _, _, had_template = recovery_candidates[i]
        parts = full_conv.get("conversation_parts", {}).get("conversation_parts", [])
        if client.should_recover_conversation(parts, had_template_opener=had_template):
            batch_with_details.append((parsed, full_conv))
            batch_stats["recovered"] += 1

    if not batch_with_details:
        return batch_stats

    # Step 3: Classify (NO stop check here - only at batch boundaries)
    classify_tasks = [
        classify_conversation_async(parsed, raw_conv, semaphore)
        for parsed, raw_conv in batch_with_details
    ]
    results = await asyncio.gather(*classify_tasks, return_exceptions=True)

    valid_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            conv_id = batch_with_details[i][0].id if i < len(batch_with_details) else "unknown"
            logger.error(f"Classification error for {conv_id}: {r}")
            continue
        valid_results.append(r)
        if r.get("stage2_result"):
            batch_stats["stage2_run"] += 1
            if r["stage2_result"].get("changed_from_stage_1"):
                batch_stats["classification_changed"] += 1

    batch_stats["classified"] = len(valid_results)

    # Step 4: Store
    if not dry_run and valid_results:
        stored = store_classification_results_batch(valid_results, pipeline_run_id=pipeline_run_id)
        batch_stats["stored"] = stored

    return batch_stats


async def _run_streaming_batch_pipeline_async(
    client: "IntercomClient",
    since: datetime,
    until: datetime,
    max_conversations: Optional[int],
    dry_run: bool,
    concurrency: int,
    batch_size: int,
    semaphore: asyncio.Semaphore,
    stop_checker: callable,
    pipeline_run_id: Optional[int],
    checkpoint: Optional[Dict[str, Any]],
) -> Dict[str, int]:
    """Streaming batch pipeline: fetch → classify → store → checkpoint per batch.

    Issue #209: True batch-level resume for Intercom backfill.

    Operational guarantees:
    - Max rework on crash = 1 batch
    - Memory bounded to 1 batch
    - Cursor resume skips already-fetched pages

    Args:
        client: IntercomClient instance
        since: Start of date range
        until: End of date range
        max_conversations: Maximum conversations to process
        dry_run: If True, don't store to database
        concurrency: Max parallel API calls
        batch_size: Conversations per batch
        semaphore: Semaphore for classification concurrency
        stop_checker: Callable returning True if pipeline should stop
        pipeline_run_id: Pipeline run ID for storage and checkpointing
        checkpoint: Optional checkpoint dict to resume from

    Returns:
        Statistics dictionary
    """
    logger.info("Starting streaming batch pipeline (Issue #209)")
    start_time = datetime.now()

    # Initialize from checkpoint on resume
    initial_cursor = None
    if checkpoint and checkpoint.get("phase") == "classification":
        initial_cursor = checkpoint.get("intercom_cursor")
        logger.info(f"Resuming from cursor (stored={checkpoint.get('conversations_processed', 0)})")

    # ==========================================================================
    # CURSOR SEMANTICS - READ BEFORE MODIFYING
    # ==========================================================================
    # cursor_callback receives the cursor for the NEXT page to fetch, NOT the
    # page we just processed. This is extracted from pages.next in
    # intercom_client.py:661.
    #
    # Example timeline:
    #   Page 1 fetched → cursor_callback("cursor_for_page_2")
    #   Page 2 fetched → cursor_callback("cursor_for_page_3")
    #   Page 3 fetched → cursor_callback(None) [no more pages]
    #
    # On resume with cursor_for_page_3, we start from page 3, skipping 1-2.
    #
    # CRITICAL INVARIANT: We only checkpoint AFTER processing a batch.
    # This ensures checkpoint.cursor = cursor for FIRST UNFETCHED page.
    # If we checkpointed with unprocessed data in buffer, we'd skip it!
    #
    # Using list wrapper for closure capture (Python scoping limitation)
    # ==========================================================================
    current_cursor = [initial_cursor]

    def cursor_callback(next_page_cursor: str) -> None:
        """Called after each page with cursor for NEXT page."""
        current_cursor[0] = next_page_cursor

    # Stats (cumulative across batches)
    # NOTE: filtered=0 always in streaming mode (schema parity with legacy path)
    stats = {
        "fetched": 0,
        "filtered": 0,
        "recovered": 0,
        "classified": 0,
        "stored": 0,
        "stage2_run": 0,
        "classification_changed": 0,
        "warnings": [],
    }

    # Recovery candidates shared list - generator appends here
    recovery_candidates = []

    def on_cursor_fallback() -> None:
        """Called if cursor is invalid and pagination restarts from beginning."""
        stats["warnings"].append("Cursor invalid on resume, restarted from beginning")
        logger.warning("Cursor fallback: invalid cursor, restarting from beginning")

    batch_buffer = []
    batch_number = 0
    stopped_during_fetch = False

    async with client._get_aiohttp_session() as session:
        async for parsed, raw_conv in client.fetch_quality_conversations_async(
            since=since,
            until=until,
            initial_cursor=initial_cursor,
            cursor_callback=cursor_callback,
            recovery_candidates=recovery_candidates,
            on_cursor_fallback=on_cursor_fallback,
        ):
            # Stop signal during fetch (mid-batch)
            # ===================================================================
            # We buffer conversations before classification. If stopped mid-batch,
            # we have incomplete work that cannot be safely checkpointed:
            #   - Some conversations fetched but not classified
            #   - Recovery candidates not yet evaluated
            #   - Cursor points PAST the buffered conversations
            #
            # Checkpointing here would skip these conversations on resume.
            # Instead, we discard the buffer and let resume refetch them.
            #
            # Cost: Refetch up to batch_size conversations (acceptable)
            # ===================================================================
            if stop_checker():
                stopped_during_fetch = True
                stats["warnings"].append(
                    f"Stopped during fetch with {len(batch_buffer)} conversations buffered "
                    f"(will be refetched on next run - no data loss)"
                )
                logger.info(f"Stop signal during fetch, discarding {len(batch_buffer)} buffered")
                break

            batch_buffer.append((parsed, raw_conv))

            if len(batch_buffer) >= batch_size:
                # Grab recovery candidates accumulated during this batch
                batch_recovery = recovery_candidates.copy()
                recovery_candidates.clear()

                batch_number += 1
                logger.info(f"Processing batch {batch_number}: {len(batch_buffer)} conversations")

                # Process: details → evaluate recovery → classify → store
                batch_stats = await _process_streaming_batch(
                    batch=batch_buffer,
                    recovery_candidates=batch_recovery,
                    client=client,
                    session=session,
                    semaphore=semaphore,
                    concurrency=concurrency,
                    dry_run=dry_run,
                    pipeline_run_id=pipeline_run_id,
                )
                _accumulate_stats(stats, batch_stats)

                logger.info(
                    f"Batch {batch_number} complete: "
                    f"classified={batch_stats['classified']}, stored={batch_stats['stored']}"
                )

                # Checkpoint AFTER storage succeeds (invariant: never checkpoint before storage)
                # Also updates _active_checkpoints in-memory via _save_classification_checkpoint
                if not dry_run and pipeline_run_id:
                    _save_classification_checkpoint(
                        pipeline_run_id, current_cursor[0],
                        fetched=stats["fetched"],
                        classified=stats["classified"],
                        stored=stats["stored"],
                    )

                batch_buffer = []

                # Check stop AFTER processing and checkpointing (not before)
                # This ensures we never checkpoint with unprocessed data in buffer
                if stop_checker():
                    logger.info("Stop signal at batch boundary, exiting after checkpoint")
                    break

                # Max conversations check
                if max_conversations and stats["classified"] >= max_conversations:
                    logger.info(f"Reached max_conversations={max_conversations}")
                    break

        # Process final partial batch (if not stopped during fetch)
        if batch_buffer and not stopped_during_fetch and not stop_checker():
            batch_recovery = recovery_candidates.copy()
            recovery_candidates.clear()

            batch_number += 1
            logger.info(f"Processing final batch {batch_number}: {len(batch_buffer)} conversations")

            batch_stats = await _process_streaming_batch(
                batch=batch_buffer,
                recovery_candidates=batch_recovery,
                client=client,
                session=session,
                semaphore=semaphore,
                concurrency=concurrency,
                dry_run=dry_run,
                pipeline_run_id=pipeline_run_id,
            )
            _accumulate_stats(stats, batch_stats)

            if not dry_run and pipeline_run_id:
                _save_classification_checkpoint(
                    pipeline_run_id, current_cursor[0],
                    fetched=stats["fetched"],
                    classified=stats["classified"],
                    stored=stats["stored"],
                )

    # Clear checkpoint on success (pipeline complete)
    if not dry_run and pipeline_run_id and not stop_checker():
        _clear_checkpoint(pipeline_run_id)

    # Log summary
    elapsed = (datetime.now() - start_time).total_seconds()
    throughput = stats["classified"] / elapsed if elapsed > 0 else 0

    logger.info("")
    logger.info("=" * 60)
    logger.info("Streaming Batch Pipeline Complete")
    logger.info("=" * 60)
    logger.info(f"Batches processed:        {batch_number}")
    logger.info(f"Conversations classified: {stats['classified']}")
    if stats['recovered'] > 0:
        logger.info(f"Conversations recovered:  {stats['recovered']}")
    logger.info(f"Stage 2 run:              {stats['stage2_run']}")
    logger.info(f"Classifications changed:  {stats['classification_changed']}")
    if not dry_run:
        logger.info(f"Stored to database:       {stats['stored']}")
    logger.info(f"Total time:               {elapsed:.1f}s")
    logger.info(f"Throughput:               {throughput:.1f} conv/sec")
    if stats['warnings']:
        logger.info(f"Warnings:                 {len(stats['warnings'])}")
    logger.info("")

    return stats


async def run_pipeline_async(
    days: int = 7,
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
    concurrency: int = 20,
    batch_size: int = 50,
    data_source: str = "intercom",
    stop_checker: Optional[callable] = None,
    pipeline_run_id: Optional[int] = None,
    checkpoint: Optional[Dict[str, Any]] = None,
    date_from_override: Optional[datetime] = None,
    date_to_override: Optional[datetime] = None,
) -> Dict[str, int]:
    """
    Run the two-stage classification pipeline with async parallelization.

    ~10-20x faster than sequential processing.

    Args:
        days: Number of days to look back
        max_conversations: Maximum conversations to process
        dry_run: If True, don't store to database
        concurrency: Number of parallel API calls (default 20)
        batch_size: DB batch insert size (default 50)
        data_source: Source to process ("intercom" or "coda")
        stop_checker: Optional callable returning True if pipeline should stop
        pipeline_run_id: Pipeline run ID for accurate run scoping (links conversations to run)
        checkpoint: Issue #202 - Optional checkpoint dict to resume from
        date_from_override: Issue #202 - Override date range start (for resume)
        date_to_override: Issue #202 - Override date range end (for resume)

    Returns:
        Statistics dictionary
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("Two-Stage Classification Pipeline (ASYNC)")
    logger.info("=" * 60)
    logger.info("Data source: %s", data_source.upper())
    logger.info("Fetching conversations from last %d days...", days)
    logger.info("Concurrency: %d parallel requests", concurrency)
    logger.info("Batch size: %d for DB inserts", batch_size)
    if dry_run:
        logger.info("DRY RUN - Will not store to database")
    logger.info("")

    # Initialize semaphore
    semaphore = asyncio.Semaphore(concurrency)

    # Helper to check if stop requested
    def should_stop() -> bool:
        return stop_checker is not None and stop_checker()

    # Use appropriate adapter based on data source
    if data_source == "coda":
        return await _run_coda_pipeline_async(
            max_conversations=max_conversations,
            dry_run=dry_run,
            concurrency=concurrency,
            batch_size=batch_size,
            semaphore=semaphore,
            stop_checker=stop_checker,
            pipeline_run_id=pipeline_run_id,
        )

    # Default: Intercom pipeline
    client = IntercomClient()

    # Issue #202: Use date overrides if provided (resume case), else compute from days
    if date_from_override and date_to_override:
        since = date_from_override
        until = date_to_override
        logger.info("Resuming with original date range: %s to %s", since, until)
    else:
        since = datetime.utcnow() - timedelta(days=days)
        until = datetime.utcnow()

    # Issue #209: Streaming batch mode for safe historical backfills
    # Processes in batches with true cursor-based checkpoint/resume
    if PIPELINE_STREAMING_BATCH_ENABLED:
        logger.info("Streaming batch mode enabled (batch_size=%d)", PIPELINE_STREAMING_BATCH_SIZE)
        return await _run_streaming_batch_pipeline_async(
            client=client,
            since=since,
            until=until,
            max_conversations=max_conversations,
            dry_run=dry_run,
            concurrency=concurrency,
            batch_size=PIPELINE_STREAMING_BATCH_SIZE,
            semaphore=semaphore,
            stop_checker=should_stop,
            pipeline_run_id=pipeline_run_id,
            checkpoint=checkpoint,
        )

    # Issue #202: Track warnings for observability
    classification_warnings = []

    # Issue #202: On resume, query already-stored conversation IDs to skip classification
    already_stored_ids: set = set()
    if checkpoint and checkpoint.get("phase") == "classification" and pipeline_run_id:
        stored_count = checkpoint.get("conversations_processed", 0)
        logger.info("Resuming from checkpoint: %d conversations already stored", stored_count)
        # Query DB for already-stored conversation IDs to skip classification
        already_stored_ids = _get_stored_conversation_ids(pipeline_run_id)
        logger.info("  Found %d conversation IDs in database, will skip classification for these", len(already_stored_ids))
        classification_warnings.append(
            f"Resuming: {len(already_stored_ids)} conversations already stored, will skip classification for these."
        )

    # Issue #202: Track current cursor for checkpoint persistence (observability only)
    current_cursor = [None]  # Use list to allow mutation in callback

    def cursor_callback(new_cursor: str) -> None:
        """Called after each page to track cursor for checkpointing (observability)."""
        current_cursor[0] = new_cursor

    # Phase 1: Fetch all conversations (fully async with aiohttp)
    # Issue #164: Track recovery candidates (filtered but potentially recoverable)
    logger.info("Phase 1: Fetching conversations from Intercom...")
    conversations = []
    recovery_candidates = []  # Issue #164: Track filtered conversations for recovery

    async for parsed, raw_conv in client.fetch_quality_conversations_async(
        since=since,
        until=until,
        recovery_candidates=recovery_candidates,
        cursor_callback=cursor_callback,  # For observability in checkpoint
    ):
        # Check for stop signal during fetch
        if should_stop():
            logger.info("  Stop signal received during fetch, stopping...")
            break

        # Get full conversation with parts (need session for this)
        # We'll batch this after initial fetch for efficiency
        conversations.append((parsed, raw_conv))

        if len(conversations) % 50 == 0:
            logger.info("  Fetched %d conversations...", len(conversations))
            # Issue #202: Track cursor but DON'T persist checkpoint here.
            # Checkpoint is persisted AFTER storage to prevent data loss on crash.
            # See C2 fix: checkpoint saved after storage, not after fetch.

        if max_conversations and len(conversations) >= max_conversations:
            break

    logger.info("  Total fetched: %d", len(conversations))
    if recovery_candidates:
        logger.info("  Recovery candidates: %d", len(recovery_candidates))

    # Phase 1b: Fetch full conversation details in parallel
    # Issue #164: Also fetch details for recovery candidates
    recovered_count = 0  # Issue #164: Track recovered conversations
    all_to_fetch = [(p, r) for p, r in conversations]
    recovery_indices_start = len(all_to_fetch)
    all_to_fetch.extend([(p, r) for p, r, _ in recovery_candidates])

    if all_to_fetch:
        logger.info("  Fetching full conversation details for %d conversations...", len(all_to_fetch))
        async with client._get_aiohttp_session() as session:
            # Batch fetch with semaphore for rate limiting
            detail_semaphore = asyncio.Semaphore(concurrency)

            async def fetch_detail(parsed, raw_conv):
                async with detail_semaphore:
                    try:
                        full_conv = await client.get_conversation_async(session, parsed.id)
                        return (parsed, full_conv)
                    except Exception as e:
                        logger.warning(f"Failed to fetch details for {parsed.id}: {e}")
                        return (parsed, raw_conv)  # Fall back to raw_conv

            tasks = [fetch_detail(p, r) for p, r in all_to_fetch]
            all_results = await asyncio.gather(*tasks)
            all_results = list(all_results)

        # Split results back into conversations and recovery candidates
        conversations = all_results[:recovery_indices_start]
        recovery_results = all_results[recovery_indices_start:]

        logger.info("  Fetched details for %d conversations", len(conversations))

        # Issue #164: Evaluate recovery candidates with full conversation details
        recovered_count = 0
        for i, (parsed, full_conv) in enumerate(recovery_results):
            _, _, had_template = recovery_candidates[i]
            # Get conversation parts/messages from full_conv
            parts = full_conv.get("conversation_parts", {}).get("conversation_parts", [])
            if client.should_recover_conversation(parts, had_template_opener=had_template):
                conversations.append((parsed, full_conv))
                recovered_count += 1

        if recovered_count > 0:
            logger.info("  Recovered %d conversations with detailed follow-ups", recovered_count)

    # Check for stop signal before classification
    if should_stop():
        logger.info("  Stop signal received, returning early...")
        return {
            "fetched": len(conversations),
            "recovered": recovered_count,  # Issue #164
            "filtered": 0,
            "classified": 0,
            "stored": 0,
            "stage2_run": 0,
            "classification_changed": 0,
        }

    # Issue #202: Filter out already-stored conversations on resume
    # This preserves the expensive classification work from before interruption
    skipped_count = 0
    if already_stored_ids:
        original_count = len(conversations)
        conversations = [
            (parsed, raw_conv) for parsed, raw_conv in conversations
            if parsed.id not in already_stored_ids
        ]
        skipped_count = original_count - len(conversations)
        logger.info("  Skipped %d already-stored conversations, %d remaining to classify",
                   skipped_count, len(conversations))

    # Phase 2: Classify in parallel (with stop checks between batches)
    logger.info("")
    logger.info("Phase 2: Classifying %d conversations in parallel...", len(conversations))
    start_time = datetime.now()

    # Process in batches to allow stop signal checks between batches
    CLASSIFICATION_BATCH_SIZE = 50
    results = []

    for batch_start in range(0, len(conversations), CLASSIFICATION_BATCH_SIZE):
        # Check for stop signal between classification batches
        if should_stop():
            logger.info("  Stop signal received during classification (batch %d), stopping...", batch_start // CLASSIFICATION_BATCH_SIZE + 1)
            break

        batch_end = min(batch_start + CLASSIFICATION_BATCH_SIZE, len(conversations))
        batch = conversations[batch_start:batch_end]

        tasks = [
            classify_conversation_async(parsed, raw_conv, semaphore)
            for parsed, raw_conv in batch
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and log them
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                conv_id = batch[i][0].id if i < len(batch) else "unknown"
                logger.error("ERROR classifying conversation %s: %s", conv_id, result, exc_info=result)
            else:
                results.append(result)

        if len(conversations) > CLASSIFICATION_BATCH_SIZE:
            logger.info("  Classified batch %d: %d conversations", batch_start // CLASSIFICATION_BATCH_SIZE + 1, len(batch_results))

    elapsed = (datetime.now() - start_time).total_seconds()
    throughput = len(results) / elapsed if elapsed > 0 else 0
    logger.info("  Classification complete in %.1fs (%.1f conv/sec)", elapsed, throughput)

    # Phase 3: Batch store to database
    # Issue #202: For totals, include skipped_count (already classified/stored in previous run)
    # This ensures counters don't regress on resume
    stats = {
        "fetched": len(conversations) + skipped_count,  # Total fetched before filtering
        "recovered": recovered_count,  # Issue #164
        "skipped": skipped_count,  # Issue #202: Already-stored conversations skipped on resume
        "classified": len(results) + skipped_count,  # TOTAL: new + previously classified
        "stored": skipped_count,  # Start with previously stored, add new below
        # Note: stage2_run and classification_changed only count NEW results, not previously
        # processed. These are informational counters for this run's classification behavior,
        # not cumulative totals. On resume, they reflect only the newly classified subset.
        "stage2_run": sum(1 for r in results if r["stage2_result"]),
        "classification_changed": sum(1 for r in results if (r.get("stage2_result") or {}).get("changed_from_stage_1")),
        "warnings": classification_warnings,  # Issue #202: Observability
    }

    if not dry_run:
        logger.info("")
        logger.info("Phase 3: Storing %d results in batches of %d...", len(results), batch_size)

        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            stored = store_classification_results_batch(batch, pipeline_run_id=pipeline_run_id)
            stats["stored"] += stored
            logger.info("  Stored batch %d: %d rows", i // batch_size + 1, stored)

            # Issue #202 C2 fix: Save checkpoint AFTER storage, not during fetch.
            # This prevents data loss: checkpoint only advances after data is durably stored.
            # Note: cursor is for observability; on resume, we re-fetch from beginning
            # and upsert handles duplicates. True cursor-based resume requires batch processing.
            if pipeline_run_id:
                _save_classification_checkpoint(
                    pipeline_run_id,
                    current_cursor[0],  # For observability
                    fetched=stats["fetched"],  # Total fetched (constant after fetch phase)
                    classified=stats["classified"],
                    stored=stats["stored"],  # Actual progress
                )

        # Issue #202: Clear checkpoint after classification completes successfully
        # This signals that classification is done and later phases can proceed.
        # If interrupted between classification and embeddings, classification won't re-run.
        if pipeline_run_id:
            _clear_checkpoint(pipeline_run_id)

    # Log summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Pipeline Complete")
    logger.info("=" * 60)
    logger.info("Conversations fetched:    %d", stats['fetched'])
    if stats['recovered'] > 0:
        logger.info("Conversations recovered:  %d", stats['recovered'])  # Issue #164
    logger.info("Conversations classified: %d", stats['classified'])
    logger.info("Stage 2 run:              %d", stats['stage2_run'])
    logger.info("Classifications changed:  %d", stats['classification_changed'])
    if not dry_run:
        logger.info("Stored to database:       %d", stats['stored'])
    logger.info("Total time:               %.1fs", elapsed)
    logger.info("Throughput:               %.1f conv/sec", stats['classified'] / elapsed if elapsed > 0 else 0)
    logger.info("")

    # For dry runs, include results for preview (Issue #75)
    if dry_run:
        stats["_dry_run_results"] = results

    return stats


async def _run_coda_pipeline_async(
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
    concurrency: int = 20,
    batch_size: int = 50,
    semaphore: asyncio.Semaphore = None,
    stop_checker: Optional[callable] = None,
    pipeline_run_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Run classification pipeline for Coda research data.

    Coda data is evergreen (not time-bounded like Intercom),
    so we process all available research content.

    Args:
        pipeline_run_id: Pipeline run ID for accurate run scoping
    """
    def should_stop() -> bool:
        return stop_checker is not None and stop_checker()
    from adapters import CodaAdapter

    adapter = CodaAdapter()

    # Fetch Coda data
    logger.info("Phase 1: Fetching research data from Coda...")
    raw_items = adapter.fetch(max_items=max_conversations, include_tables=True, include_pages=True)
    logger.info("  Total fetched: %d items", len(raw_items))

    # Check for stop signal after fetch
    if should_stop():
        logger.info("  Stop signal received after fetch, stopping...")
        return {
            "fetched": len(raw_items),
            "filtered": 0,
            "classified": 0,
            "stored": 0,
            "data_source": "coda",
        }

    # Normalize to common format
    logger.info("")
    logger.info("Phase 2: Normalizing Coda data...")
    normalized = []
    for item in raw_items:
        # Check for stop signal during normalization
        if should_stop():
            logger.info("  Stop signal received during normalization, stopping...")
            break
        try:
            conv = adapter.normalize(item)
            if conv.text and len(conv.text) > 50:  # Skip empty content
                normalized.append(conv)
        except Exception as e:
            logger.warning("  Failed to normalize item: %s", e)

    logger.info("  Normalized: %d items with content", len(normalized))

    # Check for stop signal before classification
    if should_stop():
        logger.info("  Stop signal received, returning early...")
        return {
            "fetched": len(raw_items),
            "filtered": len(raw_items) - len(normalized),
            "classified": 0,
            "stored": 0,
            "data_source": "coda",
        }

    # Classify in parallel (Stage 1 only for research data)
    logger.info("")
    logger.info("Phase 3: Classifying %d items...", len(normalized))
    start_time = datetime.now()

    async def classify_coda_item(conv: NormalizedConversation) -> Dict[str, Any]:
        """Classify a single Coda item."""
        async with semaphore:
            import json as json_module

            # Use simplified prompt for research content
            prompt = f"""Analyze this research content and extract themes.

Content:
{conv.text[:3000]}

Return JSON with:
- conversation_type: "research_insight" | "user_feedback" | "feature_request" | "pain_point"
- themes: list of 1-3 theme strings
- confidence: "high" | "medium" | "low"
- key_quote: most insightful quote from the content (if any)
"""
            try:
                response = await async_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a research analyst extracting themes from user research. Respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    response_format={"type": "json_object"}
                )
                result = json_module.loads(response.choices[0].message.content)
            except Exception as e:
                result = {
                    "conversation_type": "research_insight",
                    "themes": [],
                    "confidence": "low",
                    "error": str(e)
                }

            return {
                "conversation_id": conv.id,
                "created_at": conv.created_at,
                "source_body": conv.text,
                "source_type": "coda",
                "source_url": conv.url,
                "contact_email": conv.source_metadata.get("participant"),
                "contact_id": None,
                "data_source": "coda",
                "source_metadata": conv.source_metadata,
                "stage1_result": result,
                "stage2_result": None,  # Research doesn't need Stage 2
                "support_messages": [],
                "resolution_signal": None,
            }

    # Process in batches to allow stop signal checks between batches
    CLASSIFICATION_BATCH_SIZE = 50
    results = []

    for batch_start in range(0, len(normalized), CLASSIFICATION_BATCH_SIZE):
        # Check for stop signal between classification batches
        if should_stop():
            logger.info("  Stop signal received during classification (batch %d), stopping...", batch_start // CLASSIFICATION_BATCH_SIZE + 1)
            break

        batch_end = min(batch_start + CLASSIFICATION_BATCH_SIZE, len(normalized))
        batch = normalized[batch_start:batch_end]

        tasks = [classify_coda_item(conv) for conv in batch]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

        if len(normalized) > CLASSIFICATION_BATCH_SIZE:
            logger.info("  Classified batch %d: %d items", batch_start // CLASSIFICATION_BATCH_SIZE + 1, len(batch_results))

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("  Classification complete in %.1fs", elapsed)

    # Stats
    stats = {
        "fetched": len(raw_items),
        "classified": len(results),
        "stored": 0,
        "stage2_run": 0,
        "classification_changed": 0,
        "data_source": "coda",
    }

    # Store to database
    if not dry_run:
        logger.info("")
        logger.info("Phase 4: Storing %d results...", len(results))
        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            stored = store_classification_results_batch(batch, pipeline_run_id=pipeline_run_id)
            stats["stored"] += stored
            logger.info("  Stored batch %d: %d rows", i // batch_size + 1, stored)

    # Log summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Coda Pipeline Complete")
    logger.info("=" * 60)
    logger.info("Items fetched:     %d", stats['fetched'])
    logger.info("Items classified:  %d", stats['classified'])
    if not dry_run:
        logger.info("Stored to database: %d", stats['stored'])
    logger.info("Total time:        %.1fs", elapsed)
    logger.info("")

    return stats


def run_pipeline(
    days: int = 7,
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
    data_source: str = "intercom",
    pipeline_run_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Run the full two-stage classification pipeline (sync version).

    For debugging or small batches. Use run_pipeline_async for production.

    Args:
        days: Number of days to look back
        max_conversations: Maximum conversations to process
        dry_run: If True, don't store to database
        pipeline_run_id: Pipeline run ID for accurate run scoping

    Returns:
        Statistics dictionary
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("Two-Stage Classification Pipeline (SYNC)")
    logger.info("=" * 60)
    logger.info("Fetching conversations from last %d days...", days)
    if dry_run:
        logger.info("DRY RUN - Will not store to database")
    logger.info("")

    # Initialize client
    client = IntercomClient()
    since = datetime.utcnow() - timedelta(days=days)

    # Stats
    stats = {
        "fetched": 0,
        "filtered": 0,
        "classified": 0,
        "stored": 0,
        "stage2_run": 0,
        "classification_changed": 0,
    }

    # Collect results for batch insert
    results_batch = []
    BATCH_SIZE = 50

    # Process conversations
    for parsed, raw_conv in client.fetch_quality_conversations(since=since, max_pages=None):
        stats["fetched"] += 1

        # Get full conversation details (includes parts)
        full_conv = client.get_conversation(parsed.id)

        # Classify
        result = classify_conversation(parsed, full_conv)
        stats["classified"] += 1

        if result["stage2_result"]:
            stats["stage2_run"] += 1
            if result["stage2_result"].get("changed_from_stage_1"):
                stats["classification_changed"] += 1

        # Collect for batch insert
        if not dry_run:
            results_batch.append({
                "conversation_id": parsed.id,
                "created_at": parsed.created_at,
                "source_body": parsed.source_body,
                "source_type": parsed.source_type,
                "source_url": parsed.source_url,
                "contact_email": parsed.contact_email,
                "contact_id": parsed.contact_id,
                **result
            })

            # Batch insert when we hit batch size
            if len(results_batch) >= BATCH_SIZE:
                stored = store_classification_results_batch(results_batch, pipeline_run_id=pipeline_run_id)
                stats["stored"] += stored
                logger.info("  [Batch] Stored %d results", stored)
                results_batch = []

        logger.info("")

        # Check limit
        if max_conversations and stats["classified"] >= max_conversations:
            break

    # Store remaining results
    if results_batch and not dry_run:
        stored = store_classification_results_batch(results_batch, pipeline_run_id=pipeline_run_id)
        stats["stored"] += stored
        logger.info("  [Batch] Stored final %d results", stored)

    # Log summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Pipeline Complete")
    logger.info("=" * 60)
    logger.info("Conversations fetched:    %d", stats['fetched'])
    logger.info("Conversations classified: %d", stats['classified'])
    logger.info("Stage 2 run:              %d", stats['stage2_run'])
    logger.info("Classifications changed:  %d", stats['classification_changed'])
    if not dry_run:
        logger.info("Stored to database:       %d", stats['stored'])
    logger.info("")

    return stats


def main():
    """Run pipeline with default settings."""
    # Configure safe logging for standalone CLI usage (Issue #185)
    from src.logging_utils import configure_safe_logging
    configure_safe_logging()

    import argparse

    parser = argparse.ArgumentParser(description="Two-Stage Classification Pipeline")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--max", type=int, help="Maximum conversations to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't store to database")
    parser.add_argument("--async", dest="use_async", action="store_true",
                        help="Use async parallel processing (faster)")
    parser.add_argument("--concurrency", type=int, default=20,
                        help="Parallel API calls (async mode only)")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="DB batch insert size")
    parser.add_argument("--source", type=str, default="intercom",
                        choices=["intercom", "coda"],
                        help="Data source to process (default: intercom)")

    args = parser.parse_args()

    # Create pipeline run for accurate run scoping (Fix #103)
    pipeline_run_id = None
    if not args.dry_run:
        date_to = datetime.utcnow()
        date_from = date_to - timedelta(days=args.days)
        run = PipelineRun(
            date_from=date_from,
            date_to=date_to,
            status="running",
        )
        pipeline_run_id = create_pipeline_run(run)
        logger.info("Created pipeline run: %d", pipeline_run_id)

    if args.use_async:
        asyncio.run(run_pipeline_async(
            days=args.days,
            max_conversations=args.max,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            batch_size=args.batch_size,
            data_source=args.source,
            pipeline_run_id=pipeline_run_id,
        ))
    else:
        run_pipeline(
            days=args.days,
            max_conversations=args.max,
            dry_run=args.dry_run,
            data_source=args.source,
            pipeline_run_id=pipeline_run_id,
        )


if __name__ == "__main__":
    main()
