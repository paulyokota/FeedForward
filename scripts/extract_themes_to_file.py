#!/usr/bin/env python3
"""
Extract specific themes from Intercom conversations using our vocabulary.

Uses ThemeExtractor to map conversations to the 78 specific themes in
config/theme_vocabulary.json, NOT broad categories.

Output includes:
- issue_signature: Specific theme like 'pinterest_publishing_failure'
- product_area: Product area like 'pinterest_publishing'
- component: Component like 'pin_scheduler'
- Rich metadata for Shortcut story formatting

Usage:
    python scripts/extract_themes_to_file.py --max 100
    python scripts/extract_themes_to_file.py --max 100 --strict  # Only match known themes

API Reference:
    ThemeExtractor.extract() takes a Conversation object (from db.models)
    with required fields: id, created_at, source_body, issue_type, sentiment,
    churn_risk, priority. See src/db/models.py for full schema.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from intercom_client import IntercomClient
from theme_extractor import ThemeExtractor
from classifier_stage1 import classify_stage1
from db.models import Conversation

OUTPUT_FILE = Path(__file__).parent.parent / "data" / "theme_extraction_results.jsonl"
INTERCOM_APP_ID = os.getenv("INTERCOM_APP_ID", "2t3d8az2")

# Valid values from db/models.py Literal types
# IssueType = Literal["bug_report", "feature_request", "product_question", "plan_question",
#                     "marketing_question", "billing", "account_access", "feedback", "other"]
# Sentiment = Literal["frustrated", "neutral", "satisfied"]
# Priority = Literal["urgent", "high", "normal", "low"]


def map_stage1_to_model(stage1: dict) -> tuple:
    """Map Stage 1 output to db.models Literal string values."""
    # Map conversation_type to IssueType (Literal string)
    type_mapping = {
        "bug_report": "bug_report",
        "product_issue": "bug_report",
        "how_to_question": "product_question",
        "feature_request": "feature_request",
        "billing_question": "billing",
        "account_issue": "account_access",
        "configuration_help": "product_question",
        "general_inquiry": "other",
    }
    issue_type = type_mapping.get(stage1.get("conversation_type"), "other")

    # Map sentiment (Literal string: "frustrated", "neutral", "satisfied")
    sentiment_mapping = {
        "positive": "satisfied",
        "neutral": "neutral",
        "negative": "frustrated",
        "frustrated": "frustrated",
    }
    sentiment = sentiment_mapping.get(stage1.get("sentiment"), "neutral")

    # Map priority (Literal string: "urgent", "high", "normal", "low")
    priority_mapping = {
        "urgent": "urgent",
        "high": "high",
        "normal": "normal",
        "low": "low",
    }
    priority = priority_mapping.get(stage1.get("routing_priority"), "normal")

    # Map churn_risk to bool
    churn_risk = stage1.get("churn_risk", "low") in ["high", "medium"]

    return issue_type, sentiment, priority, churn_risk


def main(max_convs=100, strict_mode=False):
    """Extract themes from conversations."""
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text("")

    intercom = IntercomClient()
    extractor = ThemeExtractor(model="gpt-4o-mini", use_vocabulary=True)

    since = datetime.utcnow() - timedelta(days=30)

    print(f"Extracting themes from up to {max_convs} conversations")
    print(f"Results saved to: {OUTPUT_FILE}")
    print(f"Strict mode (only known themes): {strict_mode}")
    print("-" * 60)
    sys.stdout.flush()

    count = 0
    for parsed, raw_conv in intercom.fetch_quality_conversations(since=since, max_pages=None):
        count += 1

        # Fetch org_id
        org_id = None
        if parsed.contact_id:
            org_id = intercom.fetch_contact_org_id(parsed.contact_id)

        # First do Stage 1 classification to get issue_type, sentiment, etc.
        try:
            stage1 = classify_stage1(
                customer_message=parsed.source_body,
                source_type=parsed.source_type
            )
        except Exception as e:
            print(f"  Stage 1 error: {e}")
            stage1 = {
                "conversation_type": "general_inquiry",
                "sentiment": "neutral",
                "routing_priority": "normal",
                "churn_risk": "low"
            }

        # Map Stage 1 output to model enums
        issue_type, sentiment, priority, churn_risk = map_stage1_to_model(stage1)

        # Create Conversation object for ThemeExtractor
        # See src/db/models.py for full schema
        conv = Conversation(
            id=parsed.id,
            created_at=parsed.created_at,
            source_body=parsed.source_body,
            source_type=parsed.source_type,
            source_subject=parsed.source_subject,
            source_url=parsed.source_url,
            contact_email=parsed.contact_email,
            contact_id=parsed.contact_id,
            issue_type=issue_type,
            sentiment=sentiment,
            priority=priority,
            churn_risk=churn_risk,
        )

        # Extract theme using ThemeExtractor
        try:
            theme = extractor.extract(
                conv=conv,
                strict_mode=strict_mode,
            )

            # Build URLs
            intercom_url = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/{parsed.id}"
            jarvis_org_url = f"https://jarvis.tailwind.ai/organizations/{org_id}" if org_id else None
            jarvis_user_url = f"https://jarvis.tailwind.ai/organizations/{org_id}/users/{parsed.user_id}" if org_id and parsed.user_id else None

            result = {
                "id": parsed.id,
                # Theme details (the key output!)
                "issue_signature": theme.issue_signature,
                "product_area": theme.product_area,
                "component": theme.component,
                "user_intent": theme.user_intent,
                "symptoms": theme.symptoms,
                "affected_flow": theme.affected_flow,
                "root_cause_hypothesis": theme.root_cause_hypothesis,
                # Excerpt and metadata
                "excerpt": parsed.source_body[:300],
                "created_at": parsed.created_at.isoformat(),
                "source_url": parsed.source_url,
                # User metadata
                "email": parsed.contact_email,
                "user_id": parsed.user_id,
                "org_id": org_id,
                # Pre-built URLs
                "intercom_url": intercom_url,
                "jarvis_org_url": jarvis_org_url,
                "jarvis_user_url": jarvis_user_url,
            }

            with open(OUTPUT_FILE, "a") as f:
                f.write(json.dumps(result) + "\n")

            email_display = (parsed.contact_email or "no-email")[:25]
            print(f"{count}/{max_convs}: {theme.issue_signature} | {theme.product_area} | {email_display}")
            sys.stdout.flush()

        except Exception as e:
            print(f"{count}/{max_convs}: ERROR - {e}")
            sys.stdout.flush()

        if count >= max_convs:
            break

    print("-" * 60)
    print(f"Done! {count} themes saved to {OUTPUT_FILE}")

    # Summary by issue_signature
    from collections import Counter
    signatures = Counter()
    product_areas = Counter()

    with open(OUTPUT_FILE) as f:
        for line in f:
            r = json.loads(line)
            signatures[r["issue_signature"]] += 1
            product_areas[r["product_area"]] += 1

    print(f"\nTop Issue Signatures:")
    for sig, cnt in signatures.most_common(15):
        print(f"  {sig}: {cnt}")

    print(f"\nBy Product Area:")
    for area, cnt in product_areas.most_common():
        print(f"  {area}: {cnt}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract specific themes from conversations")
    parser.add_argument("--max", type=int, default=100, help="Max conversations")
    parser.add_argument("--strict", action="store_true", help="Only match known themes (no new signatures)")
    args = parser.parse_args()
    main(max_convs=args.max, strict_mode=args.strict)
