"""Shared base types for Discovery Engine explorer agents.

Extracted per the 'third use = extract' rule when Issue #216 (Analytics
Explorer) became the third consumer of ExplorerResult.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


def coerce_str(val: Any, fallback: str = "") -> str:
    """Coerce an LLM response value to a string.

    gpt-4o-mini returns structured dicts/lists for Pydantic str fields ~30%
    of the time. This utility normalizes those to JSON strings.

    Fallback semantics: only None and empty string trigger fallback.
    Dicts and lists are ALWAYS serialized (even empty ones) because they
    represent structured data the LLM returned. Other types (int, bool,
    float) are converted via str().

    Args:
        val: The value to coerce. If str, returned as-is (unless empty).
             If dict/list, serialized via json.dumps(). If None, returns
             fallback.
        fallback: Default string when val is None or empty string.

    Returns:
        A plain string suitable for Pydantic str fields.
    """
    if isinstance(val, str):
        return val if val else fallback
    if isinstance(val, (dict, list)):
        return json.dumps(val, indent=2)
    if val is None:
        return fallback
    return str(val)


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
