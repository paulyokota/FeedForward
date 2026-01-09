#!/usr/bin/env python3
"""
Create Shortcut stories from PM-REVIEWED theme groups.

IMPORTANT: This script requires PM review results. Run the full pipeline:
  1. python scripts/extract_themes_async.py --max 1000
  2. python scripts/run_pm_review_all.py        # REQUIRED - validates groupings
  3. python scripts/create_theme_stories.py     # This script - only after PM review

Direct theme-to-story creation bypasses the PM review quality gate.
Use --skip-pm-review only for testing/debugging.

Usage:
    python scripts/create_theme_stories.py                    # Normal - requires PM review
    python scripts/create_theme_stories.py --dry-run          # Preview
    python scripts/create_theme_stories.py --skip-pm-review   # TESTING ONLY - bypass PM review
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from story_formatter import format_excerpt
from evidence_validator import validate_samples, EvidenceQuality

PM_REVIEW_FILE = Path(__file__).parent.parent / "data" / "pm_review_results.json"


def check_pm_review_exists(skip_check: bool = False) -> dict | None:
    """Check that PM review has been run. Returns review results or None."""
    if skip_check:
        print("WARNING: Skipping PM review check (--skip-pm-review flag)")
        print("         Stories will be created without PM validation!")
        print()
        return None

    if not PM_REVIEW_FILE.exists():
        print("ERROR: PM review results not found!")
        print()
        print("You must run PM review before creating stories:")
        print("  1. python scripts/extract_themes_async.py --max 1000")
        print("  2. python scripts/run_pm_review_all.py        # <-- Missing!")
        print("  3. python scripts/create_theme_stories.py")
        print()
        print("To bypass (TESTING ONLY): --skip-pm-review")
        sys.exit(1)

    with open(PM_REVIEW_FILE) as f:
        reviews = json.load(f)

    print(f"Found PM review results: {len(reviews)} groups reviewed")
    return {r["signature"]: r for r in reviews}


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def build_theme_story_description(signature: str, data: dict, total: int) -> str:
    """Build Shortcut story description optimized for issue resolution.

    Structure follows bug report best practices:
    1. Problem Statement (5-second understand)
    2. Impact (why prioritize)
    3. Trigger Context (when does this happen)
    4. Investigation Paths (where to start)
    5. Evidence (samples)
    6. Acceptance Criteria (definition of done)
    """
    pct = data["count"] / total * 100 if total > 0 else 0

    # Get product area and component from first sample
    first = data["samples"][0] if data["samples"] else {}
    product_area = first.get("product_area", "unknown")
    component = first.get("component", "unknown")

    # Aggregate data from all samples
    all_symptoms = []
    user_intents = set()
    root_causes = set()
    affected_flows = set()
    technical_indicators = []  # Error codes, API names, etc.

    # Weak indicators to filter out
    weak_indicators = ["not specified", "no error", "unknown", "not provided", "n/a"]

    for sample in data["samples"]:
        for s in sample.get("symptoms", []):
            if s and s not in all_symptoms:
                all_symptoms.append(s)
                # Extract technical indicators from symptoms (filter weak ones)
                is_technical = any(kw in s.lower() for kw in ["error", "fail", "timeout", "401", "403", "404", "500", "api", "oauth"])
                is_weak = any(w in s.lower() for w in weak_indicators)
                if is_technical and not is_weak:
                    technical_indicators.append(s)
        if sample.get("user_intent"):
            user_intents.add(sample["user_intent"])
        if sample.get("root_cause_hypothesis"):
            root_causes.add(sample["root_cause_hypothesis"])
        if sample.get("affected_flow"):
            affected_flows.add(sample["affected_flow"])

    # Build problem statement from most common intent + top symptom
    primary_intent = list(user_intents)[0] if user_intents else "use the feature"
    # Clean up intent - remove verbose prefixes
    primary_intent = primary_intent.replace("The user was trying to ", "").replace("The user is trying to ", "")
    primary_intent = primary_intent.replace("The user wanted to ", "").replace("User wants to ", "")
    primary_intent = primary_intent.lower().strip().rstrip(".")
    primary_symptom = all_symptoms[0] if all_symptoms else "encountering issues"
    problem_statement = f"Users trying to **{primary_intent}** are {primary_symptom.lower().rstrip('.')}."

    # Build trigger context from affected flows
    flows_list = list(affected_flows)[:3]
    trigger_context = ", ".join(flows_list) if flows_list else "Various user workflows"

    # Build investigation paths from root causes
    investigation_paths = []
    for cause in list(root_causes)[:3]:
        investigation_paths.append(f"- [ ] Check: {cause}")
    if technical_indicators:
        investigation_paths.append(f"- [ ] Review logs for: {', '.join(technical_indicators[:3])}")
    if component != "unknown":
        investigation_paths.append(f"- [ ] Inspect `{component}` component")
    investigation_md = "\n".join(investigation_paths) if investigation_paths else "- [ ] Needs initial investigation"

    # Build symptoms as user-reported vs technical
    user_symptoms = [s for s in all_symptoms if not any(kw in s.lower() for kw in ["error", "fail", "api", "timeout"])]
    tech_symptoms = [s for s in all_symptoms if any(kw in s.lower() for kw in ["error", "fail", "api", "timeout"])]

    user_symptoms_md = "\n".join(f"- {s}" for s in user_symptoms[:5]) or "- No user symptoms captured"
    tech_symptoms_md = "\n".join(f"- {s}" for s in tech_symptoms[:5]) if tech_symptoms else "- No technical errors reported"

    # Build acceptance criteria
    acceptance_criteria = []
    if "failure" in signature or "error" in signature:
        acceptance_criteria.append("- [ ] Error no longer occurs for reported scenarios")
    if "request" in signature:
        acceptance_criteria.append("- [ ] Feature/change is implemented and deployed")
    acceptance_criteria.append("- [ ] Verified with at least one affected user/account")
    acceptance_criteria.append("- [ ] No regression in related functionality")
    acceptance_md = "\n".join(acceptance_criteria)

    description = f"""## Problem Statement

{problem_statement}

| Metric | Value |
|--------|-------|
| **Occurrences** | {data['count']} reports ({pct:.1f}% of analyzed) |
| **Product Area** | {product_area} |
| **Component** | {component} |
| **Trigger Context** | {trigger_context} |

---

## Investigation Paths

Start here to diagnose:

{investigation_md}

---

## Symptoms

**What users report:**
{user_symptoms_md}

**Technical indicators:**
{tech_symptoms_md}

---

## Evidence ({len(data['samples'])} samples)

"""
    for i, sample in enumerate(data["samples"][:5], 1):
        formatted = format_excerpt(
            conversation_id=sample.get("id", "unknown"),
            email=sample.get("email"),
            excerpt=sample.get("excerpt", ""),
            org_id=sample.get("org_id"),
            user_id=sample.get("user_id"),
            intercom_url=sample.get("intercom_url"),
            jarvis_org_url=sample.get("jarvis_org_url"),
            jarvis_user_url=sample.get("jarvis_user_url"),
        )
        affected_flow = sample.get("affected_flow", "Not specified")
        description += f"### Report {i}\n{formatted}\n\n**Flow**: {affected_flow}\n\n"

    description += f"""---

## Acceptance Criteria

This issue is resolved when:

{acceptance_md}

---

<details>
<summary>Metadata</summary>

- **Issue Signature**: `{signature}`
- **Generated by**: FeedForward Theme Extraction Pipeline

</details>
"""
    return description


def get_backlog_state_id(headers: dict) -> int:
    """Get the Backlog workflow state ID from Shortcut."""
    resp = requests.get(
        "https://api.app.shortcut.com/api/v3/workflows",
        headers=headers
    )
    resp.raise_for_status()
    workflows = resp.json()

    for wf in workflows:
        for state in wf.get("states", []):
            if state["name"] == "Backlog":
                return state["id"]

    raise ValueError("Could not find Backlog state")


def determine_story_type(signature: str, product_area: str) -> str:
    """Determine Shortcut story type based on theme."""
    # Bug indicators
    bug_keywords = ["failure", "error", "broken", "not_working", "crash", "timeout"]
    if any(kw in signature for kw in bug_keywords):
        return "bug"

    # Feature request indicators
    feature_keywords = ["request", "enhancement", "want", "need", "missing"]
    if any(kw in signature for kw in feature_keywords):
        return "feature"

    # Billing/account are usually chores
    if product_area in ["billing", "account"]:
        return "chore"

    # Default to bug for technical issues
    return "bug"


def build_story_name(signature: str, count: int, story_type: str) -> str:
    """Build verb-first story title following best practices.

    Best practice: Titles should start with a verb (imperative command)
    and be descriptive enough to understand without opening the ticket.
    Test: "To complete this ticket, I need to $TICKET_TITLE"
    """
    title_sig = signature.replace("_", " ").title()

    # Choose verb based on story type and signature content
    if story_type == "bug":
        if "failure" in signature or "error" in signature:
            verb = "Fix"
        elif "timeout" in signature or "crash" in signature:
            verb = "Resolve"
        else:
            verb = "Investigate"
    elif story_type == "feature":
        if "request" in signature:
            verb = "Implement"
        elif "missing" in signature:
            verb = "Add"
        else:
            verb = "Build"
    else:  # chore
        if "question" in signature or "guidance" in signature:
            verb = "Document"
        elif "deletion" in signature or "cancellation" in signature:
            verb = "Process"
        else:
            verb = "Address"

    return f"[{count}] {verb} {title_sig}"


def create_stories(input_file: Path, dry_run: bool = False, min_count: int = 1, skip_pm_review: bool = False):
    """Create Shortcut stories from PM-reviewed theme groups."""
    load_env()

    # REQUIRED: Check PM review has been run
    pm_reviews = check_pm_review_exists(skip_check=skip_pm_review)

    token = os.getenv("SHORTCUT_API_TOKEN")
    if not token:
        print("ERROR: SHORTCUT_API_TOKEN not set")
        sys.exit(1)

    token = token.strip()
    headers = {
        "Content-Type": "application/json",
        "Shortcut-Token": token,
    }

    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        print("Run extract_themes_to_file.py first.")
        sys.exit(1)

    # Aggregate by issue_signature
    aggregated = defaultdict(lambda: {"count": 0, "samples": []})

    with open(input_file) as f:
        for line in f:
            r = json.loads(line)
            sig = r.get("issue_signature", "unknown")
            aggregated[sig]["count"] += 1
            if len(aggregated[sig]["samples"]) < 5:
                aggregated[sig]["samples"].append(r)

    total = sum(d["count"] for d in aggregated.values())

    # Build conversation lookup by ID for sub-group handling
    conv_by_id = {}
    with open(input_file) as f:
        for line in f:
            r = json.loads(line)
            conv_by_id[r["id"]] = r

    # Apply PM review decisions
    stories_to_create = []
    skipped_splits = []
    orphan_conversations = []  # Sub-groups too small to create stories

    for sig, data in aggregated.items():
        if sig in ["spam", "error", "unknown"]:
            continue

        review = pm_reviews.get(sig) if pm_reviews else None

        if review and review.get("decision") == "split":
            # PM said split - create stories for sub-groups instead
            sub_groups = review.get("sub_groups", [])
            original_count = data["count"]
            sub_group_stories = 0

            for sg in sub_groups:
                sg_sig = sg.get("suggested_signature", "unknown")
                sg_ids = sg.get("conversation_ids", [])
                sg_rationale = sg.get("rationale", "")

                # Get conversation data for this sub-group
                sg_convs = [conv_by_id[cid] for cid in sg_ids if cid in conv_by_id]

                if len(sg_convs) >= min_count:
                    # Create story for this sub-group
                    sg_data = {
                        "count": len(sg_convs),
                        "samples": sg_convs[:5],
                        "rationale": sg_rationale,
                        "parent_signature": sig,
                    }
                    stories_to_create.append((sg_sig, sg_data, "PM_SPLIT"))
                    sub_group_stories += 1
                else:
                    # Too small - becomes orphan
                    for conv in sg_convs:
                        orphan_conversations.append({
                            "conv": conv,
                            "suggested_signature": sg_sig,
                            "parent_signature": sig,
                        })

            skipped_splits.append((sig, original_count, f"Split into {len(sub_groups)} sub-groups, {sub_group_stories} stories"))

        elif review and review.get("decision") == "keep_together":
            # PM validated - create story
            if data["count"] >= min_count:
                stories_to_create.append((sig, data, "PM_VALIDATED"))
        else:
            # No PM review for this group (smaller groups) - create if meets threshold
            if data["count"] >= min_count:
                stories_to_create.append((sig, data, "NO_REVIEW"))

    sorted_themes = sorted(stories_to_create, key=lambda x: x[1]["count"], reverse=True)

    print(f"\n{'='*60}")
    print("Creating Shortcut Stories from PM-Reviewed Themes")
    print(f"{'='*60}")
    print(f"Input: {input_file}")
    print(f"Total conversations: {total}")
    print(f"Unique themes: {len(aggregated)}")
    # Count by status
    pm_validated = sum(1 for _, _, s in sorted_themes if s == "PM_VALIDATED")
    pm_split = sum(1 for _, _, s in sorted_themes if s == "PM_SPLIT")
    no_review = sum(1 for _, _, s in sorted_themes if s == "NO_REVIEW")

    print(f"Stories to create: {len(sorted_themes)}")
    print(f"  - PM_VALIDATED (kept together): {pm_validated}")
    print(f"  - PM_SPLIT (sub-groups): {pm_split}")
    print(f"  - NO_REVIEW (small/error): {no_review}")
    print(f"Original groups split: {len(skipped_splits)}")
    print(f"Orphan conversations (<{min_count} in sub-group): {len(orphan_conversations)}")
    print(f"Dry run: {dry_run}")
    print()

    if skipped_splits:
        print("Split groups → sub-group stories:")
        for sig, count, reason in sorted(skipped_splits, key=lambda x: -x[1])[:10]:
            print(f"  [{count}] {sig}: {reason}")
        print()

    if not dry_run:
        backlog_state_id = get_backlog_state_id(headers)

    stories_created = []
    stories_with_poor_evidence = []

    for signature, data, status in sorted_themes:
        # EVIDENCE VALIDATION: Ensure samples have required fields
        evidence_quality = validate_samples(data.get("samples", []))

        if not evidence_quality.is_valid:
            print(f"⚠️  SKIPPING {signature}: Invalid evidence")
            for err in evidence_quality.errors:
                print(f"     ✗ {err}")
            stories_with_poor_evidence.append((signature, evidence_quality))
            continue

        if evidence_quality.warnings:
            print(f"⚠️  WARNING for {signature}: Poor evidence quality")
            for warn in evidence_quality.warnings:
                print(f"     ⚠ {warn}")
            stories_with_poor_evidence.append((signature, evidence_quality))

        first = data["samples"][0] if data["samples"] else {}
        product_area = first.get("product_area", "unknown")
        story_type = determine_story_type(signature, product_area)

        # Create verb-first title following best practices
        story_name = build_story_name(signature, data["count"], story_type)

        if dry_run:
            status_icon = {"PM_VALIDATED": "✓", "PM_SPLIT": "◆", "NO_REVIEW": "○"}.get(status, "?")
            print(f"{status_icon} Would create: {story_name}")
            print(f"  Type: {story_type}, Area: {product_area}, Status: {status}")
            print(f"  Samples: {len(data['samples'])}")
            # Show evidence quality in dry run
            email_cov = evidence_quality.coverage.get("email", 0)
            url_cov = evidence_quality.coverage.get("intercom_url", 0)
            print(f"  Evidence: email={email_cov:.0f}%, intercom_url={url_cov:.0f}%")
            print()
        else:
            description = build_theme_story_description(signature, data, total)

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
                stories_created.append({
                    "name": story_name,
                    "url": story["app_url"]
                })
                print(f"Created: {story_name}")
                print(f"  URL: {story['app_url']}")
            except Exception as e:
                print(f"ERROR creating story for {signature}: {e}")

    print(f"\n{'='*60}")
    if dry_run:
        print(f"Dry run complete. Would create {len(sorted_themes)} stories.")
    else:
        print(f"Created {len(stories_created)} Shortcut stories for review")

    # Report evidence quality issues
    if stories_with_poor_evidence:
        skipped = sum(1 for _, q in stories_with_poor_evidence if not q.is_valid)
        warned = len(stories_with_poor_evidence) - skipped
        print(f"\n⚠️  EVIDENCE QUALITY ISSUES:")
        print(f"   Skipped (invalid): {skipped}")
        print(f"   Created with warnings: {warned}")
        print(f"\n   To fix, ensure extraction captures: email, intercom_url, excerpt")
        print(f"   See: src/evidence_validator.py for required fields")
    print("="*60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create Shortcut stories from theme extractions")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "theme_extraction_results.jsonl",
        help="Input JSONL file from extract_themes_to_file.py"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--min-count", type=int, default=1, help="Minimum occurrences to create story")
    parser.add_argument("--skip-pm-review", action="store_true",
                        help="TESTING ONLY: Bypass PM review requirement")

    args = parser.parse_args()
    create_stories(args.input, args.dry_run, args.min_count, args.skip_pm_review)
