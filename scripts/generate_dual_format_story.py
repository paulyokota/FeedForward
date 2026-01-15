#!/usr/bin/env python3
"""
Generate Dual-Format Story from Pipeline Results

Runs theme extraction data through the DualStoryFormatter to generate
properly formatted stories with codebase context (when available).

Usage:
    python scripts/generate_dual_format_story.py tests/communities_bug_pipeline_results.json
    python scripts/generate_dual_format_story.py tests/communities_bug_pipeline_results.json --repo aero
    python scripts/generate_dual_format_story.py tests/communities_bug_pipeline_results.json --output examples/output.md
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.story_formatter import DualStoryFormatter

# Try to import codebase context provider (optional)
try:
    from src.story_tracking.services.codebase_context_provider import (
        CodebaseContextProvider,
        ExplorationResult,
    )
    from src.story_tracking.services.codebase_security import (
        APPROVED_REPOS,
        validate_repo_name,
    )
    CODEBASE_CONTEXT_AVAILABLE = True
except ImportError:
    CODEBASE_CONTEXT_AVAILABLE = False
    APPROVED_REPOS = set()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_pipeline_results(path: Path) -> List[Dict]:
    """Load pipeline results from JSON file."""
    with open(path) as f:
        return json.load(f)


def aggregate_conversations(conversations: List[Dict]) -> Dict:
    """
    Aggregate multiple conversation themes into a single story theme.

    Args:
        conversations: List of conversation dicts with theme data

    Returns:
        Aggregated theme data for story generation
    """
    if not conversations:
        return {}

    # Collect all symptoms
    all_symptoms = []
    for conv in conversations:
        theme = conv.get("theme", {})
        symptoms = theme.get("symptoms", [])
        all_symptoms.extend(symptoms)

    # Deduplicate while preserving order
    unique_symptoms = list(dict.fromkeys(all_symptoms))

    # Collect customer messages (from original conversation data if available)
    customer_messages = []
    for conv in conversations:
        name = conv.get("name", "Customer")
        theme = conv.get("theme", {})
        user_intent = theme.get("user_intent", "")
        if user_intent:
            customer_messages.append(f"{name}: {user_intent}")

    # Use first conversation as base
    first = conversations[0]
    first_theme = first.get("theme", {})
    first_classification = first.get("classification", {})

    # Determine first and last seen dates
    first_seen = "2025-12-15"  # From test data
    last_seen = "2026-01-10"   # From test data

    return {
        "title": first_theme.get("user_intent", "Unknown Issue"),
        "issue_signature": first_theme.get("issue_signature", "unknown"),
        "product_area": first_theme.get("product_area", "Unknown"),
        "component": first_theme.get("component", "Unknown"),
        "user_intent": first_theme.get("user_intent", ""),
        "symptoms": unique_symptoms,
        "root_cause_hypothesis": first_theme.get("root_cause_hypothesis", ""),
        "affected_flow": first_theme.get("affected_flow", ""),
        "occurrences": len(conversations),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "task_type": "bug-fix" if first_classification.get("issue_type") == "bug_report" else "feature",
        "priority": first_classification.get("priority", "normal"),
    }


def explore_codebase(
    theme_data: Dict,
    target_repo: Optional[str],
) -> Optional["ExplorationResult"]:
    """
    Explore codebase for relevant context.

    Args:
        theme_data: Aggregated theme data
        target_repo: Target repository name (must be in approved list)

    Returns:
        ExplorationResult if successful, None otherwise
    """
    if not CODEBASE_CONTEXT_AVAILABLE:
        logger.warning("Codebase context provider not available")
        return None

    if not target_repo:
        logger.info("No target repo specified - skipping codebase exploration")
        return None

    if not validate_repo_name(target_repo):
        logger.warning(
            f"Target repo '{target_repo}' not in approved list: {APPROVED_REPOS}"
        )
        return None

    try:
        provider = CodebaseContextProvider()
        result = provider.explore_for_theme(theme_data, target_repo)

        if result.success:
            logger.info(
                f"Codebase exploration complete: "
                f"{len(result.relevant_files)} files, "
                f"{len(result.code_snippets)} snippets"
            )
        else:
            logger.warning(f"Codebase exploration failed: {result.error}")

        return result

    except Exception as e:
        logger.error(f"Codebase exploration error: {e}")
        return None


def generate_story(
    conversations: List[Dict],
    target_repo: Optional[str] = None,
) -> str:
    """
    Generate a dual-format story from conversation data.

    Args:
        conversations: List of conversation dicts with theme data
        target_repo: Optional target repository for codebase exploration

    Returns:
        Formatted markdown story
    """
    # Aggregate conversations into theme data
    theme_data = aggregate_conversations(conversations)
    theme_data["target_repo"] = target_repo

    # Build evidence data from conversations
    evidence_data = {
        "customer_messages": []
    }
    for conv in conversations:
        name = conv.get("name", "Customer")
        theme = conv.get("theme", {})

        # Add symptoms as customer messages (they represent what customers reported)
        for symptom in theme.get("symptoms", [])[:2]:  # Top 2 per conversation
            evidence_data["customer_messages"].append({
                "text": symptom,
                "source": name,
            })

    # Deduplicate messages
    seen = set()
    unique_messages = []
    for msg in evidence_data["customer_messages"]:
        text = msg.get("text", msg) if isinstance(msg, dict) else msg
        if text not in seen:
            seen.add(text)
            unique_messages.append(text)
    evidence_data["customer_messages"] = unique_messages[:5]  # Top 5

    # Attempt codebase exploration
    exploration_result = explore_codebase(theme_data, target_repo)

    # Generate dual-format story
    formatter = DualStoryFormatter()
    result = formatter.format_story(
        theme_data=theme_data,
        exploration_result=exploration_result,
        evidence_data=evidence_data,
    )

    # Add header
    header = f"""# DUAL-FORMAT STORY OUTPUT - {theme_data.get('title', 'Untitled')}

> Generated by FeedForward Pipeline v2.0 | Format Version: {result.format_version}
> Generated at: {result.generated_at.isoformat()}
> Target Repository: {target_repo or 'Not specified'}
> Codebase Exploration: {f'Success ({len(exploration_result.relevant_files)} files found)' if exploration_result and exploration_result.success else 'Not performed'}

---

"""

    return header + result.combined


def main():
    parser = argparse.ArgumentParser(
        description="Generate dual-format story from pipeline results"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to pipeline results JSON file"
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help=f"Target repository for codebase exploration (approved: {', '.join(sorted(APPROVED_REPOS)) if APPROVED_REPOS else 'none'})"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--signature",
        type=str,
        default=None,
        help="Filter to specific issue signature"
    )

    args = parser.parse_args()

    if not args.input_file.exists():
        logger.error(f"Input file not found: {args.input_file}")
        sys.exit(1)

    # Load data
    conversations = load_pipeline_results(args.input_file)
    logger.info(f"Loaded {len(conversations)} conversations from {args.input_file}")

    # Filter by signature if specified
    if args.signature:
        conversations = [
            c for c in conversations
            if c.get("theme", {}).get("issue_signature") == args.signature
        ]
        logger.info(f"Filtered to {len(conversations)} conversations with signature '{args.signature}'")

    if not conversations:
        logger.error("No conversations to process")
        sys.exit(1)

    # Generate story
    story = generate_story(conversations, target_repo=args.repo)

    # Output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(story)
        logger.info(f"Story written to: {args.output}")
    else:
        print(story)


if __name__ == "__main__":
    main()
