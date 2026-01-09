#!/usr/bin/env python3
"""
Historical Pipeline: Two-phase analysis of Intercom conversations.


Phase 1 (seed): Last 60 days - full pipeline with PM review, creates stories
Phase 2 (backfill): 60 days → Jan 2024 - count historical instances only
Phase 3 (finalize): Update story counts, promote orphans that crossed threshold

Usage:
    python scripts/run_historical_pipeline.py --phase seed
    python scripts/run_historical_pipeline.py --phase backfill
    python scripts/run_historical_pipeline.py --phase finalize
    python scripts/run_historical_pipeline.py --phase all  # Run everything
"""
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import AsyncOpenAI
from theme_extractor import ThemeExtractor
from db.models import Conversation
from signature_utils import SignatureRegistry, get_registry
from evidence_validator import validate_samples

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
ACTIVE_THEMES_FILE = DATA_DIR / "active_themes.json"
HISTORICAL_COUNTS_FILE = DATA_DIR / "historical_counts.json"
ORPHANS_FILE = DATA_DIR / "orphans.json"
STORY_MAPPING_FILE = DATA_DIR / "story_mapping.json"

SEED_DAYS = 60
BACKFILL_START = datetime(2024, 1, 1)
MIN_COUNT = 3
CONCURRENCY = 25


def get_intercom_headers():
    """Get Intercom API headers."""
    token = os.getenv("INTERCOM_ACCESS_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Intercom-Version": "2.11"
    }


def get_shortcut_headers():
    """Get Shortcut API headers."""
    token = os.getenv("SHORTCUT_API_TOKEN", "").strip()
    return {
        "Content-Type": "application/json",
        "Shortcut-Token": token,
    }


def fetch_conversations_for_period(start_date: datetime, end_date: datetime, show_progress: bool = True) -> list[dict]:
    """Fetch all conversations from Intercom for a date range."""
    headers = get_intercom_headers()
    conversations = []

    # Use search API with pagination
    query = {
        "query": {
            "operator": "AND",
            "value": [
                {
                    "field": "created_at",
                    "operator": ">",
                    "value": int(start_date.timestamp())
                },
                {
                    "field": "created_at",
                    "operator": "<",
                    "value": int(end_date.timestamp())
                }
            ]
        },
        "pagination": {"per_page": 150}
    }

    url = "https://api.intercom.io/conversations/search"
    page_num = 0

    while True:
        resp = requests.post(url, headers=headers, json=query)
        if resp.status_code != 200:
            print(f"  Error fetching conversations: {resp.status_code}")
            break

        data = resp.json()
        batch = data.get("conversations", [])
        conversations.extend(batch)
        page_num += 1

        # Show progress
        pages = data.get("pages", {})
        total_pages = pages.get("total_pages", "?")
        if show_progress and page_num % 10 == 0:
            print(f"    Fetched page {page_num}/{total_pages} ({len(conversations)} conversations)")

        # Check for next page
        next_cursor = pages.get("next", {}).get("starting_after")
        if not next_cursor:
            break
        query["pagination"]["starting_after"] = next_cursor

    return conversations


def get_conversation_text(conv: dict) -> str:
    """Extract text from conversation for classification."""
    source = conv.get("source", {})
    body = source.get("body", "") or ""
    # Strip HTML
    import re
    text = re.sub(r'<[^>]+>', '', body)
    return text[:2000]


def extract_conversation_metadata(conv: dict) -> dict:
    """Extract metadata from Intercom conversation for evidence linking.

    Returns dict with:
    - email: Customer email for display
    - contact_id: Intercom contact ID (for org_id lookup)
    - user_id: Tailwind user ID (from external_id)
    - intercom_url: Direct link to conversation
    """
    source = conv.get("source", {})
    author = source.get("author", {})
    conv_id = conv.get("id", "unknown")

    # Get email from author
    email = author.get("email")

    # Get contact_id from author
    contact_id = author.get("id")

    # Get user_id from contacts[].external_id
    user_id = None
    contacts_data = conv.get("contacts", {})
    contacts_list = contacts_data.get("contacts", []) if isinstance(contacts_data, dict) else []
    if contacts_list:
        user_id = contacts_list[0].get("external_id")

    # Build Intercom URL
    app_id = os.getenv("INTERCOM_APP_ID", "2t3d8az2")
    intercom_url = f"https://app.intercom.com/a/apps/{app_id}/inbox/inbox/conversation/{conv_id}"

    return {
        "email": email,
        "contact_id": contact_id,
        "user_id": user_id,
        "intercom_url": intercom_url,
    }


async def classify_and_extract_batch(
    conversations: list[dict],
    extractor: ThemeExtractor,
    semaphore: asyncio.Semaphore,
    active_themes: set[str] | None = None,
) -> list[dict]:
    """Classify and extract themes from a batch of conversations."""

    async def process_one(conv: dict) -> dict | None:
        async with semaphore:
            try:
                conv_id = conv.get("id", "unknown")
                text = get_conversation_text(conv)
                if not text or len(text) < 20:
                    return None

                # Classify
                created_at = datetime.fromtimestamp(conv.get("created_at", 0))

                # Build Conversation object
                conv_obj = Conversation(
                    id=conv_id,
                    created_at=created_at,
                    source_body=text,
                    source_type="conversation",
                    source_url=conv.get("source", {}).get("url"),
                    issue_type="other",
                    sentiment="neutral",
                    priority="normal",
                    churn_risk=False,
                )

                # Extract theme
                theme = await asyncio.to_thread(
                    extractor.extract,
                    conv=conv_obj,
                    strict_mode=False,
                )

                sig = theme.issue_signature

                # If backfill mode, only keep if in active themes
                if active_themes is not None and sig not in active_themes:
                    return None

                # Extract metadata for evidence linking
                metadata = extract_conversation_metadata(conv)

                return {
                    "id": conv_id,
                    "issue_signature": sig,
                    "product_area": theme.product_area,
                    "component": theme.component,
                    "user_intent": theme.user_intent,
                    "symptoms": theme.symptoms,
                    "affected_flow": theme.affected_flow,
                    "root_cause_hypothesis": theme.root_cause_hypothesis,
                    "excerpt": text[:300],
                    "created_at": created_at.isoformat(),
                    # Evidence metadata for Shortcut stories
                    "email": metadata["email"],
                    "contact_id": metadata["contact_id"],
                    "user_id": metadata["user_id"],
                    "intercom_url": metadata["intercom_url"],
                }
            except Exception as e:
                return None

    tasks = [process_one(c) for c in conversations]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def enrich_with_org_ids(results: list[dict], concurrency: int = 20) -> list[dict]:
    """Batch fetch org_ids from Intercom contacts and enrich results.

    This enables Jarvis links in Shortcut story evidence sections.
    """
    import aiohttp

    # Collect unique contact_ids
    contact_ids = list(set(r.get("contact_id") for r in results if r.get("contact_id")))
    if not contact_ids:
        return results

    print(f"    Enriching {len(contact_ids)} contacts with org_ids...")

    # Batch fetch org_ids
    org_id_map = {}
    semaphore = asyncio.Semaphore(concurrency)
    token = os.getenv("INTERCOM_ACCESS_TOKEN")

    async def fetch_one(session: aiohttp.ClientSession, contact_id: str):
        async with semaphore:
            try:
                url = f"https://api.intercom.io/contacts/{contact_id}"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Intercom-Version": "2.11",
                }
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        custom_attrs = data.get("custom_attributes", {})
                        org_id_map[contact_id] = custom_attrs.get("account_id")
            except Exception:
                pass  # Skip failures silently

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, cid) for cid in contact_ids]
        await asyncio.gather(*tasks)

    # Enrich results
    for r in results:
        contact_id = r.get("contact_id")
        if contact_id and contact_id in org_id_map:
            r["org_id"] = org_id_map[contact_id]

    print(f"    Enriched {len(org_id_map)} contacts with org_ids")
    return results


def run_pm_review(themes: dict[str, dict]) -> dict:
    """Run PM review on theme groups."""
    # Import the PM review logic
    from openai import OpenAI
    client = OpenAI()

    reviews = {}
    for sig, data in themes.items():
        if data["count"] < MIN_COUNT:
            continue
        if sig in ["spam", "error", "unknown"]:
            continue

        # Build review prompt
        samples = data["samples"][:5]
        sample_text = "\n".join([
            f"- {s.get('excerpt', '')[:200]}" for s in samples
        ])

        prompt = f"""Review this theme grouping for a product feedback system.

Theme: {sig}
Count: {data['count']}
Product Area: {samples[0].get('product_area', 'unknown') if samples else 'unknown'}

Sample conversations:
{sample_text}

Question: Would you put ALL of these conversations in ONE implementation ticket?

Respond with JSON:
{{
  "decision": "keep_together" or "split",
  "reasoning": "brief explanation",
  "sub_groups": [] // only if split, array of {{"suggested_signature": "...", "conversation_ids": [...], "rationale": "..."}}
}}"""

        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            review = json.loads(resp.choices[0].message.content)
            review["signature"] = sig
            reviews[sig] = review
        except Exception as e:
            print(f"  PM review error for {sig}: {e}")
            reviews[sig] = {"signature": sig, "decision": "keep_together", "reasoning": "Review failed"}

    return reviews


def create_stories(themes: dict, reviews: dict, total: int) -> dict:
    """Create Shortcut stories and return mapping.

    IMPORTANT: Tracks signature equivalences when PM review suggests different
    signatures. This prevents the count mismatch issue where:
    - Extractor produces: billing_cancellation_request
    - PM review changes to: billing_cancellation_requests
    - Without tracking, backfill counts can't match to stories
    """
    headers = get_shortcut_headers()
    registry = get_registry()

    # Get backlog state
    resp = requests.get("https://api.app.shortcut.com/api/v3/workflows", headers=headers)
    workflows = resp.json()
    backlog_state_id = None
    for wf in workflows:
        for state in wf.get("states", []):
            if state["name"] == "Backlog":
                backlog_state_id = state["id"]
                break

    if not backlog_state_id:
        print("ERROR: Could not find Backlog state")
        return {}

    # Import story builder
    sys.path.insert(0, str(Path(__file__).parent))
    from create_theme_stories import build_theme_story_description, build_story_name, determine_story_type

    story_mapping = {}  # signature -> story_id

    for sig, data in themes.items():
        if data["count"] < MIN_COUNT:
            continue
        if sig in ["spam", "error", "unknown"]:
            continue

        review = reviews.get(sig, {})

        # Handle splits
        if review.get("decision") == "split":
            sub_groups = review.get("sub_groups", [])
            for sg in sub_groups:
                sg_sig = sg.get("suggested_signature", sig)
                sg_ids = sg.get("conversation_ids", [])
                sg_count = len(sg_ids)
                if sg_count < MIN_COUNT:
                    continue

                # CRITICAL: Track equivalence if PM changed the signature
                # This allows Phase 3 to reconcile counts properly
                if sg_sig != sig:
                    registry.register_equivalence(sig, sg_sig)
                    print(f"  Registered equivalence: {sig} -> {sg_sig}")

                # Get samples for this sub-group
                sg_samples = [s for s in data["samples"] if s["id"] in sg_ids][:5]
                if not sg_samples:
                    sg_samples = data["samples"][:5]

                sg_data = {"count": sg_count, "samples": sg_samples}

                # EVIDENCE VALIDATION: Warn if samples lack required fields
                evidence = validate_samples(sg_samples)
                if not evidence.is_valid:
                    print(f"  ⚠️  SKIPPING {sg_sig}: {', '.join(evidence.errors)}")
                    continue
                if evidence.warnings:
                    print(f"  ⚠️  Poor evidence for {sg_sig}: {', '.join(evidence.warnings)}")

                first = sg_samples[0] if sg_samples else {}
                product_area = first.get("product_area", "unknown")
                story_type = determine_story_type(sg_sig, product_area)

                story_name = build_story_name(sg_sig, sg_count, story_type)
                description = build_theme_story_description(sg_sig, sg_data, total)

                story_data = {
                    "name": story_name,
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
                    story_mapping[sg_sig] = {
                        "story_id": story["id"],
                        "url": story["app_url"],
                        "seed_count": sg_count,
                        "original_signature": sig,  # Track original for debugging
                    }
                    print(f"  Created: {story_name} -> {story['app_url']}")
                except Exception as e:
                    print(f"  Error creating story for {sg_sig}: {e}")
        else:
            # Keep together - create single story

            # EVIDENCE VALIDATION: Warn if samples lack required fields
            evidence = validate_samples(data.get("samples", []))
            if not evidence.is_valid:
                print(f"  ⚠️  SKIPPING {sig}: {', '.join(evidence.errors)}")
                continue
            if evidence.warnings:
                print(f"  ⚠️  Poor evidence for {sig}: {', '.join(evidence.warnings)}")

            first = data["samples"][0] if data["samples"] else {}
            product_area = first.get("product_area", "unknown")
            story_type = determine_story_type(sig, product_area)

            story_name = build_story_name(sig, data["count"], story_type)
            description = build_theme_story_description(sig, data, total)

            story_data = {
                "name": story_name,
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
                story_mapping[sig] = {
                    "story_id": story["id"],
                    "url": story["app_url"],
                    "seed_count": data["count"],
                }
                print(f"  Created: {story_name} -> {story['app_url']}")
            except Exception as e:
                print(f"  Error creating story for {sig}: {e}")

    # Save signature equivalences for Phase 3 reconciliation
    registry.save()
    print(f"  Saved {len(registry._equivalences)} signature equivalences")

    return story_mapping


async def run_phase1_seed():
    """Phase 1: Process last 60 days, create stories."""
    print("=" * 60)
    print("PHASE 1: SEED BATCH (Last 60 days)")
    print("=" * 60)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=SEED_DAYS)

    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print()

    # Fetch conversations
    print("Fetching conversations from Intercom...")
    conversations = fetch_conversations_for_period(start_date, end_date)
    print(f"  Found {len(conversations)} conversations")

    if not conversations:
        print("ERROR: No conversations found")
        return

    # Process in batches
    print("\nExtracting themes...")
    extractor = ThemeExtractor(model="gpt-4o-mini", use_vocabulary=True)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    all_results = []
    batch_size = 100

    for i in range(0, len(conversations), batch_size):
        batch = conversations[i:i + batch_size]
        results = await classify_and_extract_batch(
            batch, extractor, semaphore
        )
        all_results.extend(results)
        print(f"  Progress: {len(all_results)}/{len(conversations)}")

    print(f"\nExtracted {len(all_results)} themes")

    # Enrich with org_ids for Jarvis links in evidence
    print("\nEnriching with org_ids...")
    all_results = await enrich_with_org_ids(all_results)

    # Aggregate by signature
    themes = defaultdict(lambda: {"count": 0, "samples": [], "conversation_ids": []})
    for r in all_results:
        sig = r["issue_signature"]
        themes[sig]["count"] += 1
        themes[sig]["conversation_ids"].append(r["id"])
        if len(themes[sig]["samples"]) < 10:
            themes[sig]["samples"].append(r)

    # Save extraction results
    with open(DATA_DIR / "seed_extraction_results.jsonl", "w") as f:
        for r in all_results:
            f.write(json.dumps(r) + "\n")

    # Identify active themes (3+) and orphans (<3)
    active_themes = {}
    orphans = {}

    for sig, data in themes.items():
        if sig in ["spam", "error", "unknown"]:
            continue
        if data["count"] >= MIN_COUNT:
            active_themes[sig] = data
        else:
            orphans[sig] = data

    print(f"\nActive themes (≥{MIN_COUNT}): {len(active_themes)}")
    print(f"Orphans (<{MIN_COUNT}): {len(orphans)}")

    # Run PM review
    print("\nRunning PM review...")
    reviews = run_pm_review(active_themes)
    print(f"  Reviewed {len(reviews)} themes")

    # Save PM review results
    with open(DATA_DIR / "pm_review_results.json", "w") as f:
        json.dump(list(reviews.values()), f, indent=2)

    # Create stories
    print("\nCreating Shortcut stories...")
    total = len(all_results)
    story_mapping = create_stories(active_themes, reviews, total)

    # Save outputs
    with open(ACTIVE_THEMES_FILE, "w") as f:
        json.dump({
            "signatures": list(active_themes.keys()),
            "seed_date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_conversations": len(conversations),
            "total_extracted": len(all_results),
        }, f, indent=2)

    with open(ORPHANS_FILE, "w") as f:
        json.dump(orphans, f, indent=2)

    with open(STORY_MAPPING_FILE, "w") as f:
        json.dump(story_mapping, f, indent=2)

    with open(HISTORICAL_COUNTS_FILE, "w") as f:
        json.dump({sig: data["count"] for sig, data in active_themes.items()}, f, indent=2)

    print(f"\nPhase 1 complete!")
    print(f"  Stories created: {len(story_mapping)}")
    print(f"  Active themes saved: {len(active_themes)}")
    print(f"  Orphans saved: {len(orphans)}")


async def run_phase2_backfill():
    """Phase 2: Count historical instances of active themes."""
    print("=" * 60)
    print("PHASE 2: HISTORICAL BACKFILL")
    print("=" * 60)

    # Load active themes
    if not ACTIVE_THEMES_FILE.exists():
        print("ERROR: Run phase 1 first to create active_themes.json")
        return

    with open(ACTIVE_THEMES_FILE) as f:
        active_data = json.load(f)

    active_themes = set(active_data["signatures"])
    seed_end = datetime.fromisoformat(active_data["seed_date_range"]["start"])

    print(f"Active themes: {len(active_themes)}")
    print(f"Backfill period: {BACKFILL_START.date()} to {seed_end.date()}")

    # Load current counts
    with open(HISTORICAL_COUNTS_FILE) as f:
        counts = json.load(f)

    # Load orphans for potential promotion
    with open(ORPHANS_FILE) as f:
        orphans = json.load(f)

    # Process in weekly batches concurrently
    extractor = ThemeExtractor(model="gpt-4o-mini", use_vocabulary=True)

    # Generate weekly periods
    periods = []
    current = seed_end
    while current > BACKFILL_START:
        period_start = max(current - timedelta(days=7), BACKFILL_START)
        periods.append((period_start, current))
        current = period_start

    print(f"\nProcessing {len(periods)} weekly batches...")

    async def process_period(start: datetime, end: datetime) -> Counter:
        """Process a single time period."""
        conversations = fetch_conversations_for_period(start, end, show_progress=False)
        if not conversations:
            return Counter()

        semaphore = asyncio.Semaphore(CONCURRENCY)
        results = await classify_and_extract_batch(
            conversations, extractor, semaphore,
            active_themes=active_themes
        )

        # Enrich results with org_ids for proper evidence in promoted stories
        if results:
            results = await enrich_with_org_ids(results, concurrency=10)

        period_counts = Counter()
        for r in results:
            sig = r["issue_signature"]
            period_counts[sig] += 1
            # Track orphan matches
            if sig in orphans:
                orphans[sig]["count"] += 1
                if len(orphans[sig].get("samples", [])) < 10:
                    orphans[sig].setdefault("samples", []).append(r)

        return period_counts

    # Process periods with limited concurrency (3 periods at a time to avoid rate limits)
    period_semaphore = asyncio.Semaphore(3)

    async def process_with_semaphore(start: datetime, end: datetime) -> Counter:
        async with period_semaphore:
            result = await process_period(start, end)
            print(f"  Processed {start.date()} to {end.date()}: {sum(result.values())} matches")
            return result

    tasks = [process_with_semaphore(s, e) for s, e in periods]
    period_results = await asyncio.gather(*tasks)

    # Aggregate counts
    for period_counts in period_results:
        for sig, count in period_counts.items():
            counts[sig] = counts.get(sig, 0) + count

    # Save updated counts
    with open(HISTORICAL_COUNTS_FILE, "w") as f:
        json.dump(counts, f, indent=2)

    # Save updated orphans
    with open(ORPHANS_FILE, "w") as f:
        json.dump(orphans, f, indent=2)

    print(f"\nPhase 2 complete!")
    print(f"  Total historical matches: {sum(counts.values())}")


async def run_phase3_finalize():
    """Phase 3: Update story counts and promote orphans.

    IMPORTANT: Uses SignatureRegistry to reconcile counts when PM review
    changed signatures during Phase 1. This prevents the 88% missing count issue.
    """
    print("=" * 60)
    print("PHASE 3: FINALIZE")
    print("=" * 60)

    # Load data
    with open(HISTORICAL_COUNTS_FILE) as f:
        counts = json.load(f)

    with open(STORY_MAPPING_FILE) as f:
        story_mapping = json.load(f)

    with open(ORPHANS_FILE) as f:
        orphans = json.load(f)

    headers = get_shortcut_headers()

    # Load signature registry for reconciliation
    registry = get_registry()
    print(f"\nLoaded {len(registry._equivalences)} signature equivalences")

    # Reconcile counts using equivalences
    print("\nReconciling counts with signature equivalences...")
    reconciled_counts, orphan_counts = registry.reconcile_counts(counts, story_mapping)

    matched_count = sum(reconciled_counts.values())
    orphan_total = sum(orphan_counts.values())
    total_count = sum(counts.values())
    print(f"  Reconciled: {matched_count:,} counts ({100*matched_count/total_count:.1f}%)")
    print(f"  Orphan: {orphan_total:,} counts ({100*orphan_total/total_count:.1f}%)")

    if orphan_counts:
        print(f"\n  Top orphan signatures (no story match):")
        for sig, count in sorted(orphan_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    [{count}] {sig}")

    # Update existing stories using reconciled counts
    print("\nUpdating story counts...")
    for sig, data in story_mapping.items():
        story_id = data["story_id"]
        seed_count = data.get("seed_count", 0)
        # Use reconciled count if available, otherwise try direct lookup
        total_count = reconciled_counts.get(sig, counts.get(sig, seed_count))

        if total_count == seed_count:
            continue  # No change

        # Get current story
        resp = requests.get(
            f"https://api.app.shortcut.com/api/v3/stories/{story_id}",
            headers=headers
        )
        if resp.status_code != 200:
            continue

        story = resp.json()
        old_name = story["name"]

        # Update title with new count
        import re
        new_name = re.sub(r'^\[\d+\]', f'[{total_count}]', old_name)

        # Add historical note to description
        old_desc = story.get("description", "")
        historical_note = f"\n\n---\n\n**Historical Data**: {total_count} total occurrences ({seed_count} in last 60 days, {total_count - seed_count} historical)"

        if "**Historical Data**" not in old_desc:
            new_desc = old_desc + historical_note
        else:
            new_desc = re.sub(r'\*\*Historical Data\*\*:.*', f'**Historical Data**: {total_count} total occurrences ({seed_count} in last 60 days, {total_count - seed_count} historical)', old_desc)

        # Update story
        update_data = {
            "name": new_name,
            "description": new_desc,
        }

        resp = requests.put(
            f"https://api.app.shortcut.com/api/v3/stories/{story_id}",
            json=update_data,
            headers=headers
        )

        if resp.status_code == 200:
            print(f"  Updated: {old_name} -> {new_name}")

        # Update mapping
        story_mapping[sig]["total_count"] = total_count

    # Promote orphans that crossed threshold
    print("\nChecking orphan promotions...")
    promotions = []

    for sig, data in orphans.items():
        if data["count"] >= MIN_COUNT:
            promotions.append((sig, data))

    if promotions:
        print(f"  Promoting {len(promotions)} orphans to stories...")

        # Get backlog state
        resp = requests.get("https://api.app.shortcut.com/api/v3/workflows", headers=headers)
        workflows = resp.json()
        backlog_state_id = None
        for wf in workflows:
            for state in wf.get("states", []):
                if state["name"] == "Backlog":
                    backlog_state_id = state["id"]
                    break

        sys.path.insert(0, str(Path(__file__).parent))
        from create_theme_stories import build_theme_story_description, build_story_name, determine_story_type

        for sig, data in promotions:
            first = data["samples"][0] if data.get("samples") else {}
            product_area = first.get("product_area", "unknown")
            story_type = determine_story_type(sig, product_area)

            story_name = build_story_name(sig, data["count"], story_type)
            description = build_theme_story_description(sig, data, sum(counts.values()))
            description += f"\n\n---\n\n**Note**: Promoted from orphan status after historical backfill."

            story_data = {
                "name": story_name,
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
                story_mapping[sig] = {
                    "story_id": story["id"],
                    "url": story["app_url"],
                    "seed_count": 0,
                    "total_count": data["count"],
                    "promoted": True,
                }
                print(f"  Promoted: {story_name} -> {story['app_url']}")
            except Exception as e:
                print(f"  Error promoting {sig}: {e}")
    else:
        print("  No orphans to promote")

    # Save final mapping
    with open(STORY_MAPPING_FILE, "w") as f:
        json.dump(story_mapping, f, indent=2)

    # Summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Total stories: {len(story_mapping)}")
    print(f"Promoted orphans: {len(promotions)}")
    print(f"Total issue occurrences: {sum(counts.values())}")

    # Top issues
    print("\nTop 15 issues by total count:")
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])[:15]
    for sig, count in sorted_counts:
        print(f"  [{count}] {sig}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Historical pipeline")
    parser.add_argument("--phase", choices=["seed", "backfill", "finalize", "all"],
                        default="all", help="Which phase to run")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    if args.phase in ["seed", "all"]:
        await run_phase1_seed()

    if args.phase in ["backfill", "all"]:
        await run_phase2_backfill()

    if args.phase in ["finalize", "all"]:
        await run_phase3_finalize()


if __name__ == "__main__":
    asyncio.run(main())
