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
from adapters import CodaAdapter, IntercomAdapter, NormalizedConversation
from resolution_analyzer import ResolutionAnalyzer
from knowledge_extractor import KnowledgeExtractor

# Async OpenAI client for parallel processing
async_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Module-level instances (stateless analyzers, cheap to initialize)
_resolution_analyzer = ResolutionAnalyzer()
_knowledge_extractor = KnowledgeExtractor()


def get_resolution_analyzer() -> ResolutionAnalyzer:
    """Get the ResolutionAnalyzer instance."""
    return _resolution_analyzer


def get_knowledge_extractor() -> KnowledgeExtractor:
    """Get the KnowledgeExtractor instance."""
    return _knowledge_extractor


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


def detect_resolution_signal(support_messages: List[str]) -> Optional[Dict[str, Any]]:
    """
    Detect resolution patterns using ResolutionAnalyzer.

    Returns simple format for backward compatibility with Stage 2 prompt.
    Full analysis available via get_full_resolution_analysis().
    """
    if not support_messages:
        return None

    analyzer = get_resolution_analyzer()
    analysis = analyzer.analyze_conversation(support_messages)

    if analysis["primary_action"]:
        return {
            "action": analysis["primary_action"]["action"],
            "signal": analysis["primary_action"]["matched_keyword"]
        }
    return None


def get_full_resolution_analysis(support_messages: List[str]) -> Dict[str, Any]:
    """Get full resolution analysis for storage in support_insights."""
    if not support_messages:
        return {}

    analyzer = get_resolution_analyzer()
    analysis = analyzer.analyze_conversation(support_messages)

    return {
        "primary_action": analysis["primary_action"]["action"] if analysis["primary_action"] else None,
        "action_category": analysis["primary_action"]["action_category"] if analysis["primary_action"] else None,
        "all_actions": [a["action"] for a in analysis["all_actions"]],
        "categories": analysis["categories"],
        "suggested_type": analysis["suggested_type"],
        "matched_keywords": [a["matched_keyword"] for a in analysis["all_actions"]]
    }


def extract_knowledge(
    customer_message: str,
    support_messages: List[str],
    conversation_type: str
) -> Dict[str, Any]:
    """Extract knowledge for storage in support_insights."""
    if not support_messages:
        return {}

    extractor = get_knowledge_extractor()
    knowledge = extractor.extract_from_conversation(
        customer_message,
        support_messages,
        conversation_type
    )

    # Return subset of fields for storage (exclude verbose terminology)
    return {
        "root_cause": knowledge["root_cause"],
        "solution_provided": knowledge["solution_provided"],
        "product_mentions": knowledge["product_mentions"],
        "feature_mentions": knowledge["feature_mentions"],
        "self_service_gap": knowledge["self_service_gap"],
        "gap_evidence": knowledge["gap_evidence"]
    }


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

    # Stage 1: Fast routing (always runs)
    print(f"  [Stage 1] Classifying conversation {parsed.id}...")
    stage1_result = classify_stage1(
        customer_message=parsed.source_body,
        source_type=parsed.source_type
    )

    print(f"    → {stage1_result['conversation_type']} ({stage1_result['confidence']} confidence)")

    # Stage 2: Refined analysis (only if support responded)
    stage2_result = None
    resolution_signal = None
    support_insights = None

    if support_messages:
        print(f"  [Stage 2] Found {len(support_messages)} support messages, running refined analysis...")

        # Detect resolution signal first
        resolution_signal = detect_resolution_signal(support_messages)
        resolution_action = resolution_signal.get("action") if resolution_signal else None

        stage2_result = classify_stage2(
            customer_message=parsed.source_body,
            support_messages=support_messages,
            resolution_signal=resolution_action,
            source_url=parsed.source_url,
            stage1_type=stage1_result["conversation_type"]
        )

        if stage2_result.get("changed_from_stage_1"):
            print(f"    → Classification changed: {stage1_result['conversation_type']} → {stage2_result['conversation_type']}")
        else:
            print(f"    → Classification confirmed: {stage2_result['conversation_type']} ({stage2_result['confidence']} confidence)")

        if resolution_signal:
            print(f"    → Resolution detected: {resolution_signal['signal']}")

        # Build support_insights (same as async version)
        final_type = stage2_result.get("conversation_type", stage1_result["conversation_type"])
        support_insights = {
            "resolution_analysis": get_full_resolution_analysis(support_messages),
            "knowledge": extract_knowledge(
                parsed.source_body,
                support_messages,
                final_type
            )
        }

    return {
        "stage1_result": stage1_result,
        "stage2_result": stage2_result,
        "support_messages": support_messages,
        "resolution_signal": resolution_signal,
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
            response = await async_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a customer support classifier. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            result = json_module.loads(response.choices[0].message.content)

            # Add derived fields
            result["routing_priority"] = "high" if result.get("urgency") in ("critical", "high") else "normal"
            result["auto_response_eligible"] = result.get("conversation_type") in ("spam", "general_inquiry")
            result["routing_team"] = _get_routing_team(result.get("conversation_type"))

            return result
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
    resolution_signal: str = None,
    source_url: str = None,
    semaphore: asyncio.Semaphore = None,
) -> Dict[str, Any]:
    """Async Stage 2 classification."""
    import json as json_module

    async with semaphore:
        # Format support messages
        support_text = "\n\n".join([f"[Support {i+1}]: {msg[:1000]}" for i, msg in enumerate(support_messages[:5])])

        # Resolution context
        resolution_context = ""
        if resolution_signal:
            resolution_context = f"**Resolution Signal:** {resolution_signal}"

        prompt = STAGE2_PROMPT.format(
            source_type="conversation",
            source_url=source_url or "N/A",
            stage1_type=stage1_type,
            customer_message=customer_message[:2000],
            support_messages=support_text,
            help_article_context="",
            shortcut_story_context="",
            resolution_context=resolution_context,
        )

        try:
            response = await async_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a customer support analyst. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=800,
                response_format={"type": "json_object"}
            )

            result = json_module.loads(response.choices[0].message.content)
            result["changed_from_stage_1"] = result.get("conversation_type") != stage1_type

            return result
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

    Includes resolution analysis and knowledge extraction when support messages exist.
    """
    support_messages = extract_support_messages(raw_conversation)

    # Stage 1
    stage1_result = await classify_stage1_async(
        customer_message=parsed.source_body,
        source_type=parsed.source_type,
        source_url=parsed.source_url,
        semaphore=semaphore,
    )

    # Stage 2 + Resolution + Knowledge (only if support responded)
    stage2_result = None
    resolution_signal = None
    support_insights = None

    if support_messages:
        # Resolution analysis (fast, no semaphore needed)
        resolution_signal = detect_resolution_signal(support_messages)
        resolution_action = resolution_signal.get("action") if resolution_signal else None

        # Stage 2 LLM (slow, needs semaphore)
        stage2_result = await classify_stage2_async(
            customer_message=parsed.source_body,
            support_messages=support_messages,
            stage1_type=stage1_result["conversation_type"],
            resolution_signal=resolution_action,
            source_url=parsed.source_url,
            semaphore=semaphore,
        )

        # Build support_insights
        final_type = stage2_result.get("conversation_type", stage1_result["conversation_type"])
        support_insights = {
            "resolution_analysis": get_full_resolution_analysis(support_messages),
            "knowledge": extract_knowledge(
                parsed.source_body,
                support_messages,
                final_type
            )
        }

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
        "resolution_signal": resolution_signal,
        "support_insights": support_insights,
    }


async def run_pipeline_async(
    days: int = 7,
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
    concurrency: int = 20,
    batch_size: int = 50,
    data_source: str = "intercom",
    stop_checker: Optional[callable] = None,
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

    Returns:
        Statistics dictionary
    """
    print(f"\n{'='*60}")
    print(f"Two-Stage Classification Pipeline (ASYNC)")
    print(f"{'='*60}")
    print(f"Data source: {data_source.upper()}")
    print(f"Fetching conversations from last {days} days...")
    print(f"Concurrency: {concurrency} parallel requests")
    print(f"Batch size: {batch_size} for DB inserts")
    if dry_run:
        print("DRY RUN - Will not store to database")
    print()

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
        )

    # Default: Intercom pipeline
    client = IntercomClient()
    since = datetime.utcnow() - timedelta(days=days)

    # Phase 1: Fetch all conversations (fully async with aiohttp)
    print("Phase 1: Fetching conversations from Intercom...", flush=True)
    conversations = []

    async for parsed, raw_conv in client.fetch_quality_conversations_async(since=since):
        # Check for stop signal during fetch
        if should_stop():
            print("  Stop signal received during fetch, stopping...", flush=True)
            break

        # Get full conversation with parts (need session for this)
        # We'll batch this after initial fetch for efficiency
        conversations.append((parsed, raw_conv))

        if len(conversations) % 50 == 0:
            print(f"  Fetched {len(conversations)} conversations...", flush=True)

        if max_conversations and len(conversations) >= max_conversations:
            break

    print(f"  Total fetched: {len(conversations)}", flush=True)

    # Phase 1b: Fetch full conversation details in parallel
    if conversations:
        print(f"  Fetching full conversation details for {len(conversations)} conversations...")
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

            tasks = [fetch_detail(p, r) for p, r in conversations]
            conversations = await asyncio.gather(*tasks)
            conversations = list(conversations)  # Convert from tuple

        print(f"  Fetched details for {len(conversations)} conversations")

    # Check for stop signal before classification
    if should_stop():
        print("  Stop signal received, returning early...")
        return {
            "fetched": len(conversations),
            "filtered": 0,
            "classified": 0,
            "stored": 0,
            "stage2_run": 0,
            "classification_changed": 0,
        }

    # Phase 2: Classify in parallel (with stop checks between batches)
    print(f"\nPhase 2: Classifying {len(conversations)} conversations in parallel...")
    start_time = datetime.now()

    # Process in batches to allow stop signal checks between batches
    CLASSIFICATION_BATCH_SIZE = 50
    results = []

    for batch_start in range(0, len(conversations), CLASSIFICATION_BATCH_SIZE):
        # Check for stop signal between classification batches
        if should_stop():
            print(f"  Stop signal received during classification (batch {batch_start // CLASSIFICATION_BATCH_SIZE + 1}), stopping...")
            break

        batch_end = min(batch_start + CLASSIFICATION_BATCH_SIZE, len(conversations))
        batch = conversations[batch_start:batch_end]

        tasks = [
            classify_conversation_async(parsed, raw_conv, semaphore)
            for parsed, raw_conv in batch
        ]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

        if len(conversations) > CLASSIFICATION_BATCH_SIZE:
            print(f"  Classified batch {batch_start // CLASSIFICATION_BATCH_SIZE + 1}: {len(batch_results)} conversations")

    elapsed = (datetime.now() - start_time).total_seconds()
    throughput = len(results) / elapsed if elapsed > 0 else 0
    print(f"  Classification complete in {elapsed:.1f}s ({throughput:.1f} conv/sec)")

    # Phase 3: Batch store to database
    stats = {
        "fetched": len(conversations),
        "classified": len(results),
        "stored": 0,
        "stage2_run": sum(1 for r in results if r["stage2_result"]),
        "classification_changed": sum(1 for r in results if (r.get("stage2_result") or {}).get("changed_from_stage_1")),
    }

    if not dry_run:
        print(f"\nPhase 3: Storing {len(results)} results in batches of {batch_size}...")

        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            stored = store_classification_results_batch(batch)
            stats["stored"] += stored
            print(f"  Stored batch {i//batch_size + 1}: {stored} rows")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Pipeline Complete")
    print(f"{'='*60}")
    print(f"Conversations fetched:    {stats['fetched']}")
    print(f"Conversations classified: {stats['classified']}")
    print(f"Stage 2 run:              {stats['stage2_run']}")
    print(f"Classifications changed:  {stats['classification_changed']}")
    if not dry_run:
        print(f"Stored to database:       {stats['stored']}")
    print(f"Total time:               {elapsed:.1f}s")
    print(f"Throughput:               {stats['classified']/elapsed:.1f} conv/sec")
    print()

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
) -> Dict[str, int]:
    """
    Run classification pipeline for Coda research data.

    Coda data is evergreen (not time-bounded like Intercom),
    so we process all available research content.
    """
    def should_stop() -> bool:
        return stop_checker is not None and stop_checker()
    from adapters import CodaAdapter

    adapter = CodaAdapter()

    # Fetch Coda data
    print("Phase 1: Fetching research data from Coda...")
    raw_items = adapter.fetch(max_items=max_conversations, include_tables=True, include_pages=True)
    print(f"  Total fetched: {len(raw_items)} items")

    # Check for stop signal after fetch
    if should_stop():
        print("  Stop signal received after fetch, stopping...")
        return {
            "fetched": len(raw_items),
            "filtered": 0,
            "classified": 0,
            "stored": 0,
            "data_source": "coda",
        }

    # Normalize to common format
    print("\nPhase 2: Normalizing Coda data...")
    normalized = []
    for item in raw_items:
        # Check for stop signal during normalization
        if should_stop():
            print("  Stop signal received during normalization, stopping...")
            break
        try:
            conv = adapter.normalize(item)
            if conv.text and len(conv.text) > 50:  # Skip empty content
                normalized.append(conv)
        except Exception as e:
            print(f"  Warning: Failed to normalize item: {e}")

    print(f"  Normalized: {len(normalized)} items with content")

    # Check for stop signal before classification
    if should_stop():
        print("  Stop signal received, returning early...")
        return {
            "fetched": len(raw_items),
            "filtered": len(raw_items) - len(normalized),
            "classified": 0,
            "stored": 0,
            "data_source": "coda",
        }

    # Classify in parallel (Stage 1 only for research data)
    print(f"\nPhase 3: Classifying {len(normalized)} items...")
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
            print(f"  Stop signal received during classification (batch {batch_start // CLASSIFICATION_BATCH_SIZE + 1}), stopping...")
            break

        batch_end = min(batch_start + CLASSIFICATION_BATCH_SIZE, len(normalized))
        batch = normalized[batch_start:batch_end]

        tasks = [classify_coda_item(conv) for conv in batch]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

        if len(normalized) > CLASSIFICATION_BATCH_SIZE:
            print(f"  Classified batch {batch_start // CLASSIFICATION_BATCH_SIZE + 1}: {len(batch_results)} items")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"  Classification complete in {elapsed:.1f}s")

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
        print(f"\nPhase 4: Storing {len(results)} results...")
        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            stored = store_classification_results_batch(batch)
            stats["stored"] += stored
            print(f"  Stored batch {i//batch_size + 1}: {stored} rows")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Coda Pipeline Complete")
    print(f"{'='*60}")
    print(f"Items fetched:     {stats['fetched']}")
    print(f"Items classified:  {stats['classified']}")
    if not dry_run:
        print(f"Stored to database: {stats['stored']}")
    print(f"Total time:        {elapsed:.1f}s")
    print()

    return stats


def run_pipeline(
    days: int = 7,
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
    data_source: str = "intercom",
) -> Dict[str, int]:
    """
    Run the full two-stage classification pipeline (sync version).

    For debugging or small batches. Use run_pipeline_async for production.

    Args:
        days: Number of days to look back
        max_conversations: Maximum conversations to process
        dry_run: If True, don't store to database

    Returns:
        Statistics dictionary
    """
    print(f"\n{'='*60}")
    print(f"Two-Stage Classification Pipeline (SYNC)")
    print(f"{'='*60}")
    print(f"Fetching conversations from last {days} days...")
    if dry_run:
        print("DRY RUN - Will not store to database")
    print()

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
                stored = store_classification_results_batch(results_batch)
                stats["stored"] += stored
                print(f"  [Batch] Stored {stored} results")
                results_batch = []

        print()

        # Check limit
        if max_conversations and stats["classified"] >= max_conversations:
            break

    # Store remaining results
    if results_batch and not dry_run:
        stored = store_classification_results_batch(results_batch)
        stats["stored"] += stored
        print(f"  [Batch] Stored final {stored} results")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Pipeline Complete")
    print(f"{'='*60}")
    print(f"Conversations fetched:    {stats['fetched']}")
    print(f"Conversations classified: {stats['classified']}")
    print(f"Stage 2 run:              {stats['stage2_run']}")
    print(f"Classifications changed:  {stats['classification_changed']}")
    if not dry_run:
        print(f"Stored to database:       {stats['stored']}")
    print()

    return stats


def main():
    """Run pipeline with default settings."""
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

    if args.use_async:
        asyncio.run(run_pipeline_async(
            days=args.days,
            max_conversations=args.max,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            batch_size=args.batch_size,
            data_source=args.source,
        ))
    else:
        run_pipeline(
            days=args.days,
            max_conversations=args.max,
            dry_run=args.dry_run,
            data_source=args.source,
        )


if __name__ == "__main__":
    main()
