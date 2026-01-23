"""
Normalization and canonicalization utilities for consistent data formatting.

These helpers ensure data consistency across the pipeline,
particularly for fields used in grouping and matching.

Two levels of normalization:
1. Format normalization: spaces/hyphens → underscores, lowercase, collapse repeats
2. Semantic canonicalization: alias map for known equivalent variants

The alias map is intentionally small and conservative. New aliases require
manual review to avoid over-grouping.
"""

import re
from typing import Callable, Optional


# Component alias map: maps known variants to canonical form
# Key: (product_area, raw_normalized_value) -> canonical_value
# Only add entries when there's strong evidence of semantic equivalence
#
# Format: { "product_area": { "variant": "canonical" } }
# Use "*" for product_area to match any area (use sparingly)
COMPONENT_ALIASES: dict[str, dict[str, str]] = {
    # Scheduling variants - same feature, different LLM output formats
    "scheduling": {
        "smartschedule": "smart_schedule",
        "smartpin": "smart_schedule",  # same feature
    },
    # Catch-all for any product area (use sparingly)
    "*": {
        # Example: "smartschedule": "smart_schedule",
    },
}


def _lookup_alias(product_area: str, raw_normalized: str) -> Optional[str]:
    """
    Look up canonical alias for a component.

    Checks product-area-specific aliases first, then global (*) aliases.

    Args:
        product_area: Normalized product area
        raw_normalized: Format-normalized component value

    Returns:
        Canonical value if alias exists, None otherwise
    """
    # Check product-area-specific aliases
    area_aliases = COMPONENT_ALIASES.get(product_area, {})
    if raw_normalized in area_aliases:
        return area_aliases[raw_normalized]

    # Check global aliases
    global_aliases = COMPONENT_ALIASES.get("*", {})
    if raw_normalized in global_aliases:
        return global_aliases[raw_normalized]

    return None


def normalize_component(value: str | None) -> str:
    """
    Normalize component name for consistent storage and matching.

    Rules:
    - Lowercase
    - Replace spaces and hyphens with underscores
    - Collapse repeated underscores
    - Strip leading/trailing underscores

    Examples:
        "performance tracking" -> "performance_tracking"
        "Performance-Tracking" -> "performance_tracking"
        "pin__scheduler" -> "pin_scheduler"

    Args:
        value: Raw component string (may be None)

    Returns:
        Normalized component string, or "unknown" if None/empty
    """
    if not value:
        return "unknown"

    # Lowercase
    result = value.lower()

    # Replace spaces and hyphens with underscores
    result = result.replace(" ", "_").replace("-", "_")

    # Collapse repeated underscores
    result = re.sub(r"_+", "_", result)

    # Strip leading/trailing underscores
    result = result.strip("_")

    return result or "unknown"


def canonicalize_component(
    raw: str | None,
    product_area: str | None = None,
    alias_lookup: Optional[Callable[[str, str], Optional[str]]] = None,
) -> str:
    """
    Canonicalize component for grouping/matching.

    Applies format normalization, then checks alias map for semantic equivalents.
    Use this for grouping keys (signatures, clustering). Store raw value separately
    for audit/debugging.

    Args:
        raw: Raw component string from LLM
        product_area: Product area (used for scoped alias lookup)
        alias_lookup: Optional custom alias lookup function (for testing/extension)

    Returns:
        Canonical component value

    Example:
        >>> canonicalize_component("SmartSchedule", "scheduling")
        'smart_schedule'  # via alias map
        >>> canonicalize_component("pin_scheduler", "scheduling")
        'pin_scheduler'   # no alias, just normalized
    """
    # Step 1: Format normalization
    normalized = normalize_component(raw)

    if normalized == "unknown":
        return normalized

    # Step 2: Normalize product_area for lookup
    area_normalized = normalize_product_area(product_area) if product_area else "general"

    # Step 3: Check alias map
    lookup = alias_lookup or _lookup_alias
    canonical = lookup(area_normalized, normalized)

    return canonical if canonical else normalized


def normalize_product_area(value: str | None) -> str:
    """
    Normalize product area name for consistent storage and matching.

    Same rules as normalize_component.

    Args:
        value: Raw product area string (may be None)

    Returns:
        Normalized product area string, or "general" if None/empty
    """
    if not value:
        return "general"

    # Lowercase
    result = value.lower()

    # Replace spaces and hyphens with underscores
    result = result.replace(" ", "_").replace("-", "_")

    # Collapse repeated underscores
    result = re.sub(r"_+", "_", result)

    # Strip leading/trailing underscores
    result = result.strip("_")

    return result or "general"
