#!/usr/bin/env python3
"""
Two-Stage Classification Pipeline Integration.

Orchestrates:
1. Fetching conversations from Intercom
2. Running Stage 1 classification (fast routing)
3. Running Stage 2 classification (refined analysis with support context)
4. Storing results in database
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from intercom_client import IntercomClient, IntercomConversation
from classifier_stage1 import classify_stage1
from classifier_stage2 import classify_stage2
from db.classification_storage import store_classification_result


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
    Detect if conversation shows resolution patterns.

    Simple implementation - checks for common resolution phrases.
    Can be enhanced with ML later.
    """
    if not support_messages:
        return None

    # Common resolution patterns
    resolution_phrases = [
        "resolved",
        "fixed",
        "should be working now",
        "let me know if",
        "closing this ticket",
        "marking this as complete",
    ]

    last_message = support_messages[-1].lower()

    for phrase in resolution_phrases:
        if phrase in last_message:
            return {"action": "resolved", "signal": phrase}

    return None


def classify_conversation(
    parsed: IntercomConversation,
    raw_conversation: dict,
) -> Dict[str, Any]:
    """
    Run two-stage classification on a conversation.

    Returns:
        Dictionary with stage1_result, stage2_result, support_messages, resolution_signal
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
    else:
        resolution_signal = None

    return {
        "stage1_result": stage1_result,
        "stage2_result": stage2_result,
        "support_messages": support_messages,
        "resolution_signal": resolution_signal,
    }


def run_pipeline(
    days: int = 7,
    max_conversations: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Run the full two-stage classification pipeline.

    Args:
        days: Number of days to look back
        max_conversations: Maximum conversations to process
        dry_run: If True, don't store to database

    Returns:
        Statistics dictionary
    """
    print(f"\n{'='*60}")
    print(f"Two-Stage Classification Pipeline")
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

    # Process conversations
    for parsed, raw_conv in client.fetch_quality_conversations(since=since, max_pages=1):
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

        # Store to database
        if not dry_run:
            store_classification_result(
                conversation_id=parsed.id,
                created_at=parsed.created_at,
                source_body=parsed.source_body,
                source_type=parsed.source_type,
                source_url=parsed.source_url,
                contact_email=parsed.contact_email,
                contact_id=parsed.contact_id,
                stage1_result=result["stage1_result"],
                stage2_result=result["stage2_result"],
                support_messages=result["support_messages"],
                resolution_signal=result["resolution_signal"],
            )
            stats["stored"] += 1

        print()

        # Check limit
        if max_conversations and stats["classified"] >= max_conversations:
            break

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

    args = parser.parse_args()

    run_pipeline(
        days=args.days,
        max_conversations=args.max,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
