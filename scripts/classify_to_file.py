#!/usr/bin/env python3
"""
Classify conversations and write results to file as we go.
Results are persisted immediately - no data loss if interrupted.

Output includes rich metadata for Shortcut story formatting:
- Email linked to Intercom conversation
- Org ID linked to Jarvis org page
- User ID linked to Jarvis user page

Performance: Uses batch org_id fetching (~50x faster than sequential).
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import openai
from intercom_client import IntercomClient

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "classification_results.jsonl"
INTERCOM_APP_ID = os.getenv("INTERCOM_APP_ID", "2t3d8az2")


def main(max_convs=100, fetch_org_ids=True):
    # Ensure data dir exists
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    # Clear previous results
    OUTPUT_FILE.write_text("")

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    intercom = IntercomClient()
    since = datetime.utcnow() - timedelta(days=30)

    print(f"Classifying up to {max_convs} conversations")
    print(f"Results saved to: {OUTPUT_FILE}")
    print(f"Fetching org_ids: {fetch_org_ids}")
    print("-" * 50)
    sys.stdout.flush()

    # Phase 1: Fetch all conversations first
    print("Phase 1: Fetching conversations...")
    conversations = []
    for parsed, _ in intercom.fetch_quality_conversations(since=since, max_pages=None):
        conversations.append(parsed)
        if len(conversations) % 50 == 0:
            print(f"  Fetched {len(conversations)}...", flush=True)
        if len(conversations) >= max_convs:
            break
    print(f"  Total: {len(conversations)} conversations")

    # Phase 2: Batch fetch org_ids (if enabled)
    org_id_map = {}
    if fetch_org_ids:
        print("\nPhase 2: Batch fetching org_ids...")
        contact_ids = [p.contact_id for p in conversations if p.contact_id]
        print(f"  Fetching {len(set(contact_ids))} unique contacts in parallel...")
        start = datetime.now()
        org_id_map = intercom.fetch_contact_org_ids_batch_sync(contact_ids, concurrency=20)
        elapsed = (datetime.now() - start).total_seconds()
        print(f"  Done in {elapsed:.1f}s ({len(org_id_map)/elapsed:.1f} contacts/sec)")

    # Phase 3: Classify and write results
    print("\nPhase 3: Classifying...")
    count = 0
    for parsed in conversations:
        count += 1

        # Look up org_id from batch-fetched cache
        org_id = org_id_map.get(parsed.contact_id) if fetch_org_ids else None

        # Classify
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": f"Classify: product_issue, how_to_question, feature_request, account_issue, billing_question, configuration_help, general_inquiry, spam. Reply with ONLY the category.\n\n{parsed.source_body[:300]}"
                }],
                temperature=0.1,
                max_tokens=20,
            )
            category = resp.choices[0].message.content.strip().lower().replace(" ", "_")
        except Exception as e:
            category = f"error:{e}"

        # Build Intercom conversation URL
        intercom_url = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/{parsed.id}"

        # Build Jarvis URLs
        jarvis_org_url = f"https://jarvis.tailwind.ai/organizations/{org_id}" if org_id else None
        jarvis_user_url = f"https://jarvis.tailwind.ai/organizations/{org_id}/users/{parsed.user_id}" if org_id and parsed.user_id else None

        # Write immediately to file with rich metadata
        result = {
            "id": parsed.id,
            "category": category,
            "excerpt": parsed.source_body[:300],
            "created_at": parsed.created_at.isoformat(),
            # User metadata
            "email": parsed.contact_email,
            "user_id": parsed.user_id,
            "org_id": org_id,
            # Pre-built URLs for easy linking
            "intercom_url": intercom_url,
            "jarvis_org_url": jarvis_org_url,
            "jarvis_user_url": jarvis_user_url,
        }
        with open(OUTPUT_FILE, "a") as f:
            f.write(json.dumps(result) + "\n")

        # Show progress with email
        email_display = parsed.contact_email or "no-email"
        print(f"{count}/{len(conversations)}: {category} | {email_display[:30]} | {parsed.source_body[:40]}...")
        sys.stdout.flush()

    print("-" * 50)
    print(f"Done! {count} results saved to {OUTPUT_FILE}")

    # Quick summary
    from collections import Counter
    categories = Counter()
    with open(OUTPUT_FILE) as f:
        for line in f:
            r = json.loads(line)
            categories[r["category"]] += 1

    print("\nSummary:")
    for cat, cnt in categories.most_common():
        print(f"  {cat}: {cnt}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Classify Intercom conversations with rich metadata")
    parser.add_argument("--max", type=int, default=100, help="Max conversations to classify")
    parser.add_argument("--no-org-ids", action="store_true", help="Skip fetching org_ids (faster but less metadata)")
    args = parser.parse_args()
    main(max_convs=args.max, fetch_org_ids=not args.no_org_ids)
