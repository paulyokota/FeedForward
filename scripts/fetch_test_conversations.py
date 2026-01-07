#!/usr/bin/env python3
"""
Helper script to fetch conversations from Intercom and prepare test dataset.

Fetches conversations, formats them for testing, and saves to JSON file.
The user can then manually add ground truth labels for accuracy testing.

Usage:
    # Fetch 50 closed conversations
    python scripts/fetch_test_conversations.py --count 50 --state closed --output data/test_conversations_raw.json

    # Fetch conversations with specific topics
    python scripts/fetch_test_conversations.py --count 100 --topic Billing --output data/billing_conversations.json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Note: This script uses the Intercom MCP server which should be configured in .mcp.json
# It does NOT import Python modules - it documents the expected data format


def format_conversation_for_testing(raw_conversation: dict) -> dict:
    """
    Transform raw Intercom conversation into test dataset format.

    Args:
        raw_conversation: Full conversation object from Intercom API

    Returns:
        Formatted conversation ready for manual labeling
    """
    # Extract customer message (first message from user)
    customer_message = ""
    if raw_conversation.get("source", {}).get("body"):
        customer_message = raw_conversation["source"]["body"]

    # Extract support messages (all admin/bot responses)
    support_messages = []
    conversation_parts = raw_conversation.get("conversation_parts", {}).get("conversation_parts", [])

    for part in conversation_parts:
        if part.get("part_type") == "comment":
            author_type = part.get("author", {}).get("type", "")
            if author_type in ["admin", "bot"]:
                body = part.get("body", "")
                if body and len(body.strip()) > 0:
                    support_messages.append(body)

    # Create formatted conversation
    formatted = {
        "id": f"conversation_{raw_conversation.get('id', 'unknown')}",
        "customer_message": customer_message,
        "support_messages": support_messages,
        "ground_truth": {
            "primary_theme": "LABEL_ME",  # User needs to fill this in
            "issue_type": "LABEL_ME"      # User needs to fill this in
        },
        "raw_conversation": raw_conversation,
        "_metadata": {
            "fetched_at": datetime.now().isoformat(),
            "state": raw_conversation.get("state", "unknown"),
            "topics": [topic.get("name", "") for topic in raw_conversation.get("topics", {}).get("topics", [])],
            "has_story_id": bool(raw_conversation.get("custom_attributes", {}).get("story_id_v2")),
            "ai_agent_sources": len(raw_conversation.get("ai_agent", {}).get("content_sources", {}).get("content_sources", []))
        }
    }

    return formatted


def print_usage_instructions():
    """Print instructions for using the fetched data."""
    print("\n" + "=" * 80)
    print("NEXT STEPS: Manual Labeling Required")
    print("=" * 80)
    print()
    print("The conversations have been fetched and saved. Now you need to:")
    print()
    print("1. Open the output file in a text editor")
    print()
    print("2. For each conversation, replace LABEL_ME with correct labels:")
    print("   - primary_theme: Instagram, Pinterest, Billing, Scheduling, etc.")
    print("   - issue_type: Bug, Question, Feature Request, etc.")
    print()
    print("3. Use conversation metadata to help with labeling:")
    print("   - topics: Existing Intercom topic tags")
    print("   - has_story_id: Whether support linked a Shortcut story")
    print("   - ai_agent_sources: Help articles the AI referenced")
    print()
    print("4. After labeling, use the file with accuracy testing script:")
    print()
    print("   python scripts/test_phase4_accuracy_improvement.py \\")
    print("     --test-set <your_labeled_file.json> \\")
    print("     --output results/accuracy_results.txt")
    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Intercom conversations and prepare for testing"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of conversations to fetch (default: 50)"
    )
    parser.add_argument(
        "--state",
        type=str,
        choices=["open", "closed", "snoozed", "all"],
        default="closed",
        help="Filter by conversation state (default: closed)"
    )
    parser.add_argument(
        "--topic",
        type=str,
        help="Filter by Intercom topic name (e.g., 'Billing')"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output JSON file path (e.g., data/test_conversations_raw.json)"
    )
    parser.add_argument(
        "--include-open",
        action="store_true",
        help="Include open conversations (not recommended for ground truth)"
    )

    args = parser.parse_args()

    print(f"\n{'=' * 80}")
    print("Intercom Conversation Fetcher for Test Dataset Preparation")
    print(f"{'=' * 80}\n")

    print("⚠️  MANUAL STEPS REQUIRED:\n")
    print("This script documents the process, but you need to use the Intercom MCP")
    print("to fetch conversations. Here's how:\n")

    print("1. Use Claude Code's Intercom MCP to search for conversations:")
    print(f"   Query: object_type:conversations state:{args.state} limit:{args.count}")
    if args.topic:
        print(f"   With topic filter: {args.topic}")

    print("\n2. For each conversation ID returned, fetch full details:")
    print("   Use: mcp__intercom__get_conversation with the conversation ID")

    print("\n3. Format each conversation using this structure:")
    print("""
    {
        "id": "conversation_123456",
        "customer_message": "<extracted from source.body>",
        "support_messages": ["<admin/bot responses from conversation_parts>"],
        "ground_truth": {
            "primary_theme": "LABEL_ME",
            "issue_type": "LABEL_ME"
        },
        "raw_conversation": {<full Intercom conversation object>}
    }
    """)

    print(f"\n4. Save all formatted conversations to: {args.output}")

    print("\n5. Manually label ground_truth fields based on:")
    print("   - Customer message content")
    print("   - Support responses")
    print("   - Intercom topics")
    print("   - Shortcut story labels (if story_id_v2 present)")

    print("\n" + "=" * 80)
    print("RECOMMENDED APPROACH: Use Claude Code to automate fetching")
    print("=" * 80)
    print("""
You can ask Claude Code to:

1. Fetch 50 closed conversations using Intercom MCP
2. Extract and format them into the test dataset structure
3. Save to the output file
4. Generate a summary showing:
   - Distribution by topic
   - Conversations with help articles
   - Conversations with Story ID v2
   - Conversations by state

This will give you a good sample for manual labeling.
    """)

    print("\n" + "=" * 80)
    print("After Manual Labeling")
    print("=" * 80)
    print(f"""
Once you've added ground truth labels, run accuracy tests:

python scripts/test_phase4_accuracy_improvement.py \\
  --test-set {args.output} \\
  --output results/accuracy_improvement.txt

This will measure:
- Baseline accuracy (no context enrichment)
- Help article context impact
- Shortcut story context impact
- Combined context impact
    """)


if __name__ == "__main__":
    main()
