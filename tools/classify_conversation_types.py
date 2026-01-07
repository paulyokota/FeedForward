#!/usr/bin/env python3
"""
LLM-as-judge conversation type classification.

Fetches a diverse sample of Intercom conversations (last 90 days, closed, all sources)
and uses LLM to classify conversation type, letting it propose categories organically.

This data-informed approach reveals what conversation types exist in real support traffic
before designing a rigid schema.

Output:
- CSV with conversation details + LLM classification (type, reasoning, confidence)
- Summary report with type distribution and patterns
"""

import os
import sys
import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI


CLASSIFICATION_PROMPT = """You are analyzing a customer support conversation to understand what TYPE of conversation it is.

Your goal is to propose a conversation type category that will help us understand the distribution of support traffic.

DO NOT use predefined categories - instead, analyze the conversation and propose the most appropriate type based on what the customer needs.

Common patterns you might see (but feel free to propose others):
- Bug reports (something is broken)
- Feature requests (customer wants new capability)
- How-to questions (how do I do X?)
- Billing questions (payment, plans, invoices)
- Account issues (login, access, permissions)
- Configuration help (setup, settings)
- General inquiry (non-specific questions)

Analyze this conversation and extract:

**Conversation Details:**
- Source Type: {source_type}
- Source URL: {source_url}
- Subject: {subject}

**First Message:**
{first_message}

**Follow-up Context (if any):**
{followup_context}

---

Respond in JSON format:
{{
  "conversation_type": "your proposed type (2-4 words, lowercase with underscores)",
  "reasoning": "brief explanation of why you chose this type (1-2 sentences)",
  "confidence": "high|medium|low",
  "key_signals": ["signal 1", "signal 2", "signal 3"]
}}

Focus on the customer's PRIMARY need, not secondary topics. Be specific but generalizable."""


def fetch_conversations_sample(
    target_size: int = 150,
    days_back: int = 90
) -> list[dict]:
    """
    Fetch diverse sample of closed conversations from Intercom via MCP.

    Returns list of conversation IDs to fetch full details for.
    """
    from datetime import datetime, timezone

    # Calculate timestamp for 90 days ago
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_timestamp = int(cutoff_date.timestamp())

    print(f"Fetching closed conversations from last {days_back} days...")
    print(f"Target sample size: {target_size}")
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d')}")

    # Note: We'll use the Intercom MCP via subprocess or direct API
    # For now, return empty list - this will be filled by MCP calls
    return []


def classify_conversation(
    client: OpenAI,
    conversation: dict,
) -> dict:
    """
    Use LLM to classify conversation type.

    Returns: {
        "conversation_type": str,
        "reasoning": str,
        "confidence": str,
        "key_signals": list[str]
    }
    """
    # Extract conversation details
    source_type = conversation.get("source", {}).get("type", "unknown")
    source_url = conversation.get("source", {}).get("url", "none")
    subject = conversation.get("source", {}).get("subject", "none")

    # Get first customer message
    conversation_parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])

    # Find first customer message (not admin)
    first_message = ""
    for part in conversation_parts:
        if part.get("part_type") == "comment" and part.get("author", {}).get("type") != "admin":
            first_message = part.get("body", "")
            break

    # If no customer message found, use source body
    if not first_message:
        first_message = conversation.get("source", {}).get("body", "")

    # Get follow-up context (next 1-2 messages)
    followup_context = ""
    customer_messages = [
        part.get("body", "")
        for part in conversation_parts[1:4]  # Get next 3 parts
        if part.get("part_type") == "comment"
    ]
    if customer_messages:
        followup_context = "\n\n".join(customer_messages[:2])

    # Format prompt
    prompt = CLASSIFICATION_PROMPT.format(
        source_type=source_type,
        source_url=source_url or "none",
        subject=subject or "none",
        first_message=first_message[:1000] if first_message else "(empty)",
        followup_context=followup_context[:500] if followup_context else "(no follow-up)"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a support conversation analyst. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        print(f"  ⚠️  Classification error: {e}")
        return {
            "conversation_type": "error",
            "reasoning": str(e),
            "confidence": "low",
            "key_signals": []
        }


def generate_report(results: list[dict], output_dir: Path):
    """Generate CSV and summary report."""

    # 1. Write CSV
    csv_path = output_dir / f"conversation_types_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    csv_headers = [
        "conversation_id",
        "created_at",
        "source_type",
        "source_url",
        "subject",
        "first_message_preview",
        "conversation_type",
        "confidence",
        "reasoning",
        "key_signals",
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()

        for r in results:
            writer.writerow({
                "conversation_id": r["conversation_id"],
                "created_at": r["created_at"],
                "source_type": r["source_type"],
                "source_url": r["source_url"],
                "subject": r["subject"],
                "first_message_preview": r["first_message"][:200] + "..." if len(r["first_message"]) > 200 else r["first_message"],
                "conversation_type": r["classification"]["conversation_type"],
                "confidence": r["classification"]["confidence"],
                "reasoning": r["classification"]["reasoning"],
                "key_signals": "; ".join(r["classification"].get("key_signals", [])),
            })

    print(f"\n✓ CSV saved to {csv_path}")

    # 2. Generate summary report
    type_counts = Counter(r["classification"]["conversation_type"] for r in results)
    confidence_counts = Counter(r["classification"]["confidence"] for r in results)

    # Group by source type
    by_source = defaultdict(list)
    for r in results:
        by_source[r["source_type"]].append(r["classification"]["conversation_type"])

    # Group by URL presence
    with_url = [r for r in results if r["source_url"]]
    without_url = [r for r in results if not r["source_url"]]

    report = f"""
{'='*80}
CONVERSATION TYPE CLASSIFICATION REPORT
{'='*80}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Conversations: {len(results)}
Sample Period: Last 90 days (closed conversations only)

{'='*80}
TYPE DISTRIBUTION
{'='*80}

"""

    for conv_type, count in type_counts.most_common():
        percentage = 100 * count / len(results)
        report += f"{conv_type:30} {count:4} ({percentage:5.1f}%)\n"

    report += f"\n{'='*80}\n"
    report += "CONFIDENCE DISTRIBUTION\n"
    report += f"{'='*80}\n\n"

    for confidence, count in confidence_counts.most_common():
        percentage = 100 * count / len(results)
        report += f"{confidence:10} {count:4} ({percentage:5.1f}%)\n"

    report += f"\n{'='*80}\n"
    report += "BY SOURCE TYPE\n"
    report += f"{'='*80}\n\n"

    for source_type in sorted(by_source.keys()):
        types = by_source[source_type]
        report += f"\n{source_type} ({len(types)} conversations):\n"
        type_dist = Counter(types)
        for conv_type, count in type_dist.most_common(5):
            percentage = 100 * count / len(types)
            report += f"  {conv_type:30} {count:4} ({percentage:5.1f}%)\n"

    report += f"\n{'='*80}\n"
    report += "URL CONTEXT ANALYSIS\n"
    report += f"{'='*80}\n\n"

    report += f"With URL: {len(with_url)} ({100*len(with_url)/len(results):.1f}%)\n"
    report += f"Without URL: {len(without_url)} ({100*len(without_url)/len(results):.1f}%)\n"

    if with_url:
        report += "\nTop types WITH URL:\n"
        with_url_types = Counter(r["classification"]["conversation_type"] for r in with_url)
        for conv_type, count in with_url_types.most_common(5):
            percentage = 100 * count / len(with_url)
            report += f"  {conv_type:30} {count:4} ({percentage:5.1f}%)\n"

    if without_url:
        report += "\nTop types WITHOUT URL:\n"
        without_url_types = Counter(r["classification"]["conversation_type"] for r in without_url)
        for conv_type, count in without_url_types.most_common(5):
            percentage = 100 * count / len(without_url)
            report += f"  {conv_type:30} {count:4} ({percentage:5.1f}%)\n"

    report += f"\n{'='*80}\n"
    report += "KEY INSIGHTS\n"
    report += f"{'='*80}\n\n"

    # Generate insights
    most_common_type = type_counts.most_common(1)[0]
    report += f"• Most common type: {most_common_type[0]} ({100*most_common_type[1]/len(results):.1f}%)\n"

    high_confidence = sum(1 for r in results if r["classification"]["confidence"] == "high")
    report += f"• High confidence classifications: {high_confidence}/{len(results)} ({100*high_confidence/len(results):.1f}%)\n"

    unique_types = len(type_counts)
    report += f"• Unique conversation types identified: {unique_types}\n"

    report += f"\n{'='*80}\n"

    # Print to console
    print(report)

    # Save to file
    report_path = output_dir / f"conversation_types_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text(report)
    print(f"✓ Report saved to {report_path}")

    # Save full results as JSON
    json_path = output_dir / f"conversation_types_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total": len(results),
            "type_distribution": dict(type_counts),
            "confidence_distribution": dict(confidence_counts),
            "results": results
        }, f, indent=2)
    print(f"✓ Full results saved to {json_path}")


def main():
    """Main entry point - to be called with conversation data from MCP."""
    print("="*80)
    print("Conversation Type Classification (LLM-as-Judge)")
    print("="*80)
    print("\nThis script requires conversation data to be passed from Intercom MCP.")
    print("It should be invoked by Claude Code after fetching conversations via MCP.\n")
    print("Expected workflow:")
    print("1. Claude fetches 150-200 closed conversations via Intercom MCP")
    print("2. Saves conversations to temporary JSON file")
    print("3. Calls this script with --input <json_file>")
    print("4. Script classifies and generates report")
    print("\nUsage: python classify_conversation_types.py --input conversations.json")

    import argparse
    parser = argparse.ArgumentParser(description="Classify conversation types using LLM")
    parser.add_argument("--input", type=str, required=True, help="JSON file with conversation data")
    parser.add_argument("--output-dir", type=str, default="data/conversation_types",
                       help="Output directory for results")
    args = parser.parse_args()

    # Load conversations
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return 1

    with open(input_path) as f:
        conversations = json.load(f)

    if not isinstance(conversations, list):
        print(f"❌ Expected JSON array, got {type(conversations)}")
        return 1

    print(f"\n✓ Loaded {len(conversations)} conversations from {input_path}")

    # Initialize OpenAI client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Classify each conversation
    print(f"\nClassifying conversations...")
    results = []

    for i, conv in enumerate(conversations, 1):
        conv_id = conv.get("id", "unknown")
        print(f"[{i}/{len(conversations)}] Classifying {conv_id}...", end=" ")

        classification = classify_conversation(client, conv)

        # Extract key fields for results
        result = {
            "conversation_id": conv_id,
            "created_at": conv.get("created_at"),
            "source_type": conv.get("source", {}).get("type", "unknown"),
            "source_url": conv.get("source", {}).get("url", ""),
            "subject": conv.get("source", {}).get("subject", ""),
            "first_message": "",  # Will be filled below
            "classification": classification
        }

        # Get first message for preview
        conversation_parts = conv.get("conversation_parts", {}).get("conversation_parts", [])
        for part in conversation_parts:
            if part.get("part_type") == "comment" and part.get("author", {}).get("type") != "admin":
                result["first_message"] = part.get("body", "")
                break

        if not result["first_message"]:
            result["first_message"] = conv.get("source", {}).get("body", "")

        results.append(result)
        print(f"→ {classification['conversation_type']} ({classification['confidence']})")

    # Generate reports
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_report(results, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
