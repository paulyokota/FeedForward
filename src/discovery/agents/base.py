"""Shared base types for Discovery Engine explorer agents.

Extracted per the 'third use = extract' rule when Issue #216 (Analytics
Explorer) became the third consumer of ExplorerResult.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExplorerResult:
    """Result of an exploration run, before checkpoint formatting.

    Shared across all Stage 0 explorer agents (Customer Voice, Codebase,
    Analytics). Each explorer's explore() method returns this, and
    build_checkpoint_artifacts() converts it to an ExplorerCheckpoint dict.
    """

    findings: List[Dict[str, Any]] = field(default_factory=list)
    coverage: Dict[str, Any] = field(default_factory=dict)
    token_usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    batch_errors: List[str] = field(default_factory=list)
