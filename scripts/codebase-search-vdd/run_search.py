#!/usr/bin/env python3
"""
Run Search Phase for VDD Loop

Executes the existing codebase search logic on a batch of conversations
and captures detailed results for evaluation.

Usage:
    python run_search.py < conversations.json > search_results.json
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from story_tracking.services.codebase_context_provider import CodebaseContextProvider
from story_tracking.services.codebase_security import APPROVED_REPOS, REPO_BASE_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load VDD configuration."""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def run_search_for_conversation(
    provider: CodebaseContextProvider,
    conversation: dict,
    config: dict,
) -> dict:
    """
    Run codebase search for a single conversation.

    Args:
        provider: Codebase context provider instance
        conversation: Conversation data with issue_summary
        config: VDD configuration

    Returns:
        Search results including files found, snippets, and metadata
    """
    start_time = time.time()

    # Extract issue summary to use as search input
    issue_summary = conversation.get("issue_summary", "")
    product_area = conversation.get("product_area", "uncertain")

    # Build theme-like data structure for existing search logic
    # The existing logic expects theme_data with component, symptoms, user_intent
    theme_data = {
        "component": product_area,
        "symptoms": [issue_summary],
        "user_intent": issue_summary,
    }

    files_found = []
    snippets = []
    search_terms_used = []
    exploration_log = []

    # Run search across all approved repos
    for repo_name in config.get("approved_repos", APPROVED_REPOS):
        try:
            # Get keywords from theme data
            keywords = provider._extract_keywords(theme_data)
            search_terms_used.extend(keywords)

            exploration_log.append({
                "action": "extract_keywords",
                "repo": repo_name,
                "keywords": keywords,
            })

            # Build search patterns
            patterns = provider._build_search_patterns(theme_data, repo_name)
            exploration_log.append({
                "action": "build_patterns",
                "repo": repo_name,
                "patterns": patterns,
            })

            # Glob for files
            repo_path = provider._get_repo_path(repo_name)
            if not repo_path:
                exploration_log.append({
                    "action": "skip_repo",
                    "repo": repo_name,
                    "reason": "repo not found",
                })
                continue

            matched_files = provider._glob_for_files(repo_path, patterns)
            exploration_log.append({
                "action": "glob_files",
                "repo": repo_name,
                "files_found": len(matched_files),
            })

            # Search for keywords in files
            file_refs = provider._search_for_keywords(
                repo_path,
                matched_files,
                keywords,
                max_results=20
            )

            # Add repo prefix to paths for cross-repo comparison
            for ref in file_refs:
                files_found.append({
                    "repo": repo_name,
                    "path": f"{repo_name}/{ref.path}",
                    "line_start": ref.line_start,
                    "relevance": ref.relevance,
                })

            exploration_log.append({
                "action": "search_keywords",
                "repo": repo_name,
                "files_matched": len(file_refs),
            })

            # Extract snippets from top files
            repo_snippets = provider._extract_snippets(file_refs)
            for snippet in repo_snippets:
                snippets.append({
                    "repo": repo_name,
                    "file_path": f"{repo_name}/{snippet.file_path}",
                    "line_start": snippet.line_start,
                    "line_end": snippet.line_end,
                    "content": snippet.content[:500],  # Truncate for output size
                    "language": snippet.language,
                    "context": snippet.context,
                })

        except Exception as e:
            exploration_log.append({
                "action": "error",
                "repo": repo_name,
                "error": str(e),
            })
            logger.warning(f"Error searching repo {repo_name}: {e}")

    duration_ms = int((time.time() - start_time) * 1000)

    return {
        "conversation_id": conversation.get("conversation_id"),
        "issue_summary": issue_summary,
        "product_area": product_area,
        "classification_confidence": conversation.get("classification_confidence", 1.0),
        "search_results": {
            "files_found": files_found,
            "snippets": snippets,
            "search_terms_used": list(set(search_terms_used)),
            "exploration_log": exploration_log,
        },
        "search_duration_ms": duration_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Run codebase search on conversations")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    config = load_config()

    # Read conversations from stdin
    try:
        conversations = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse input JSON: {e}")
        sys.exit(1)

    if not isinstance(conversations, list):
        conversations = [conversations]

    logger.info(f"Processing {len(conversations)} conversations")

    # Initialize provider
    provider = CodebaseContextProvider()

    # Process each conversation
    results = []
    for i, conv in enumerate(conversations):
        logger.info(f"Processing conversation {i+1}/{len(conversations)}: {conv.get('conversation_id', 'unknown')}")
        result = run_search_for_conversation(provider, conv, config)
        results.append(result)

    # Output results in envelope format expected by evaluate_results.py
    # Parse iteration number from environment or default to 1
    iteration_number = int(os.environ.get("VDD_ITERATION", 1))
    output = {
        "conversations": results,
        "iteration_number": iteration_number,
        "timestamp": datetime.utcnow().isoformat(),
    }
    json.dump(output, sys.stdout, indent=2)

    logger.info(f"Completed search for {len(results)} conversations")


if __name__ == "__main__":
    main()
