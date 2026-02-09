"""Multi-explorer checkpoint merge for the Discovery Engine.

Merges findings from multiple Stage 0 explorer results into a single
ExplorerCheckpoint dict. Source tracking is preserved via EvidencePointer
source_type on each finding.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from src.discovery.agents.base import ExplorerResult


def merge_explorer_results(
    results: List[Tuple[str, ExplorerResult]],
) -> Dict[str, Any]:
    """Merge multiple explorer results into one ExplorerCheckpoint dict.

    Args:
        results: List of (agent_name, ExplorerResult) tuples.

    Returns:
        Dict conforming to ExplorerCheckpoint schema with combined findings,
        aggregated coverage, and merged token usage.
    """
    all_findings: List[Dict[str, Any]] = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    agent_names: List[str] = []

    total_reviewed = 0
    total_available = 0
    total_skipped = 0
    total_findings = 0

    for agent_name, result in results:
        agent_names.append(agent_name)
        all_findings.extend(result.findings)
        total_findings += len(result.findings)

        for key in total_tokens:
            total_tokens[key] += result.token_usage.get(key, 0)

        total_reviewed += result.coverage.get("conversations_reviewed", 0)
        total_available += result.coverage.get("conversations_available", 0)
        total_skipped += result.coverage.get("conversations_skipped", 0)

    return {
        "schema_version": 1,
        "agent_name": ",".join(agent_names) if agent_names else "merged",
        "findings": all_findings,
        "coverage": {
            "time_window_days": max(
                (r.coverage.get("time_window_days", 30) for _, r in results),
                default=30,
            ),
            "conversations_available": total_available,
            "conversations_reviewed": total_reviewed,
            "conversations_skipped": total_skipped,
            "model": "merged",
            "findings_count": total_findings,
        },
    }
