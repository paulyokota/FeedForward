#!/usr/bin/env python3
"""
Parallel classification of Intercom conversations.
Uses asyncio to classify multiple conversations concurrently.
"""
import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import openai
from intercom_client import IntercomClient

# Configure OpenAI
client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CLASSIFICATION_PROMPT = """Classify this customer support message into exactly ONE category.

Categories:
- product_issue: Bug reports, features not working, errors, data problems
- how_to_question: How to use a feature, workflows, feature discovery
- feature_request: Requests for new capabilities or enhancements
- account_issue: Login problems, access issues, OAuth, permissions
- billing_question: Payment, plans, invoices, subscriptions, cancellation
- configuration_help: Setup, integration config, settings
- general_inquiry: Unclear intent, exploratory questions
- spam: Not a real support request

Message: {message}

Respond with ONLY the category name, nothing else."""


async def classify_message(message: str, semaphore: asyncio.Semaphore) -> dict:
    """Classify a single message using OpenAI."""
    async with semaphore:
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a support ticket classifier. Respond with only the category name."},
                    {"role": "user", "content": CLASSIFICATION_PROMPT.format(message=message[:1000])}
                ],
                temperature=0.1,
                max_tokens=20,
            )
            category = response.choices[0].message.content.strip().lower()
            # Normalize category names
            if category not in ["product_issue", "how_to_question", "feature_request",
                               "account_issue", "billing_question", "configuration_help",
                               "general_inquiry", "spam"]:
                category = "general_inquiry"
            return {"category": category, "success": True}
        except Exception as e:
            return {"category": "error", "success": False, "error": str(e)}


async def classify_batch(conversations: list, concurrency: int = 20) -> list:
    """Classify a batch of conversations concurrently."""
    semaphore = asyncio.Semaphore(concurrency)
    tasks = []

    for conv in conversations:
        task = classify_message(conv["message"], semaphore)
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    for conv, result in zip(conversations, results):
        conv["classification"] = result

    return conversations


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."


async def main(days: int = 30, max_conversations: int = None, concurrency: int = 20):
    """Main entry point."""
    print(f"\n{'='*60}")
    print(f"Parallel Classification Pipeline")
    print(f"{'='*60}")
    print(f"Fetching conversations from last {days} days...")
    print(f"Concurrency: {concurrency} parallel requests")
    print()

    # Fetch all conversations first
    intercom = IntercomClient()
    since = datetime.utcnow() - timedelta(days=days)

    conversations = []
    print("Fetching conversations from Intercom...")
    for parsed, _ in intercom.fetch_quality_conversations(since=since, max_pages=None):
        conversations.append({
            "id": parsed.id,
            "message": parsed.source_body,
            "created_at": parsed.created_at.isoformat(),
        })
        if max_conversations and len(conversations) >= max_conversations:
            break
        if len(conversations) % 100 == 0:
            print(f"  Fetched {len(conversations)} conversations...", flush=True)

    print(f"\nFetched {len(conversations)} conversations total")
    print(f"\nClassifying in parallel (batches of {concurrency})...")

    # Classify in parallel
    start_time = datetime.now()
    classified = await classify_batch(conversations, concurrency)
    elapsed = (datetime.now() - start_time).total_seconds()

    print(f"Classification complete in {elapsed:.1f} seconds")
    print(f"Rate: {len(conversations)/elapsed:.1f} conversations/second")

    # Aggregate results
    aggregated = defaultdict(lambda: {"count": 0, "samples": []})
    errors = 0

    for conv in classified:
        result = conv["classification"]
        if not result["success"]:
            errors += 1
            continue

        category = result["category"]
        agg = aggregated[category]
        agg["count"] += 1
        if len(agg["samples"]) < 5:
            agg["samples"].append({
                "id": conv["id"],
                "excerpt": truncate(conv["message"]),
                "created_at": conv["created_at"],
            })

    # Print summary
    print(f"\n{'='*60}")
    print("Classification Summary")
    print(f"{'='*60}")
    print(f"Total classified: {len(conversations) - errors}")
    print(f"Errors: {errors}")
    print()

    sorted_types = sorted(aggregated.items(), key=lambda x: x[1]["count"], reverse=True)

    for category, data in sorted_types:
        print(f"\n{category}:")
        print(f"  Count: {data['count']}")
        print(f"  Sample excerpts:")
        for sample in data["samples"][:3]:
            print(f"    - {sample['excerpt'][:80]}...")

    # Create Shortcut stories
    print(f"\n{'='*60}")
    print("Creating Shortcut Stories")
    print(f"{'='*60}")

    create_shortcut_stories(sorted_types, days, len(conversations))


def create_shortcut_stories(sorted_types: list, days: int, total: int):
    """Create Shortcut stories for each category."""
    import requests

    token = os.getenv("SHORTCUT_API_TOKEN")
    if not token:
        print("ERROR: SHORTCUT_API_TOKEN not set")
        return

    headers = {
        "Content-Type": "application/json",
        "Shortcut-Token": token,
    }

    # Get Backlog state ID
    workflow_resp = requests.get(
        "https://api.app.shortcut.com/api/v3/workflows",
        headers=headers
    )
    workflows = workflow_resp.json()
    backlog_state_id = None
    for wf in workflows:
        for state in wf.get("states", []):
            if state["name"] == "Backlog":
                backlog_state_id = state["id"]
                break

    if not backlog_state_id:
        print("ERROR: Could not find Backlog state")
        return

    stories_created = []

    for category, data in sorted_types:
        if data["count"] == 0 or category in ["spam", "error"]:
            continue

        pct = data["count"] / total * 100

        description = f"""## Classification Results (Last {days} Days)

**Category**: {category}
**Count**: {data['count']} ({pct:.1f}% of total)
**Total Conversations Analyzed**: {total}

---

## Sample Conversations

"""
        for i, sample in enumerate(data["samples"], 1):
            description += f"""### Sample {i}
- **Conversation ID**: {sample['id']}
- **Created**: {sample['created_at']}
- **Excerpt**: {sample['excerpt']}

"""

        description += """---

## Review Checklist
- [ ] Classification accuracy looks correct
- [ ] Sample excerpts match the category
- [ ] No obvious misclassifications

---
*Generated by FeedForward Parallel Classification Pipeline*
"""

        # Determine story type
        if category in ("product_issue",):
            story_type = "bug"
        elif category == "feature_request":
            story_type = "feature"
        else:
            story_type = "chore"

        story_data = {
            "name": f"[{data['count']}] {category.replace('_', ' ').title()} - Review",
            "description": description,
            "story_type": story_type,
            "workflow_state_id": backlog_state_id,
        }

        try:
            resp = requests.post(
                "https://api.app.shortcut.com/api/v3/stories",
                json=story_data,
                headers=headers,
            )
            resp.raise_for_status()
            story = resp.json()
            stories_created.append({
                "id": story["id"],
                "name": story_data["name"],
                "url": story["app_url"],
            })
            print(f"  Created: {story_data['name']}")
            print(f"    URL: {story['app_url']}")
        except Exception as e:
            print(f"  ERROR creating story for {category}: {e}")

    print(f"\n{'='*60}")
    print(f"Created {len(stories_created)} Shortcut stories for review")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parallel classification")
    parser.add_argument("--days", type=int, default=30, help="Days to look back")
    parser.add_argument("--max", type=int, help="Maximum conversations")
    parser.add_argument("--concurrency", type=int, default=20, help="Parallel requests")

    args = parser.parse_args()

    asyncio.run(main(
        days=args.days,
        max_conversations=args.max,
        concurrency=args.concurrency,
    ))
