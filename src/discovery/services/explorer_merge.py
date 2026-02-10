"""Multi-explorer checkpoint merge for the Discovery Engine.

Merges findings from multiple Stage 0 explorer checkpoint dicts into a
single ExplorerCheckpoint dict. Source tracking is preserved via
EvidencePointer source_type on each finding.
"""

from typing import Any, Dict, List


def merge_explorer_results(
    checkpoints: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge multiple explorer checkpoint dicts into one ExplorerCheckpoint dict.

    Args:
        checkpoints: List of dicts from explorer.build_checkpoint_artifacts().
            Each must have 'agent_name', 'findings', and 'coverage' keys.

    Returns:
        Dict conforming to ExplorerCheckpoint schema with combined findings,
        aggregated coverage.
    """
    all_findings: List[Dict[str, Any]] = []
    agent_names: List[str] = []

    total_reviewed = 0
    total_available = 0
    total_skipped = 0
    total_findings = 0

    for checkpoint in checkpoints:
        agent_names.append(checkpoint.get("agent_name", "unknown"))
        findings = checkpoint.get("findings", [])
        all_findings.extend(findings)
        total_findings += len(findings)

        coverage = checkpoint.get("coverage", {})
        total_reviewed += coverage.get("conversations_reviewed", 0)
        total_available += coverage.get("conversations_available", 0)
        total_skipped += coverage.get("conversations_skipped", 0)

    return {
        "schema_version": 1,
        "agent_name": ",".join(agent_names) if agent_names else "merged",
        "findings": all_findings,
        "coverage": {
            "time_window_days": max(
                (c.get("coverage", {}).get("time_window_days", 30) for c in checkpoints),
                default=30,
            ),
            "conversations_available": total_available,
            "conversations_reviewed": total_reviewed,
            "conversations_skipped": total_skipped,
            "model": "merged",
            "findings_count": total_findings,
        },
    }
