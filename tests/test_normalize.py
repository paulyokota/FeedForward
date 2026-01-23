"""Tests for normalization utilities."""

import pytest
from src.utils.normalize import (
    normalize_component,
    normalize_product_area,
    canonicalize_component,
    COMPONENT_ALIASES,
)


class TestNormalizeComponent:
    """Tests for normalize_component function."""

    def test_spaces_to_underscores(self):
        """Spaces become underscores."""
        assert normalize_component("performance tracking") == "performance_tracking"

    def test_hyphens_to_underscores(self):
        """Hyphens become underscores."""
        assert normalize_component("multi-network-scheduler") == "multi_network_scheduler"

    def test_lowercase(self):
        """Uppercase becomes lowercase."""
        assert normalize_component("Performance_Tracking") == "performance_tracking"

    def test_collapse_repeated_underscores(self):
        """Multiple underscores collapse to one."""
        assert normalize_component("pin__scheduler") == "pin_scheduler"
        assert normalize_component("a___b") == "a_b"

    def test_strip_leading_trailing_underscores(self):
        """Leading and trailing underscores are stripped."""
        assert normalize_component("_scheduler_") == "scheduler"
        assert normalize_component("__test__") == "test"

    def test_mixed_normalization(self):
        """All rules apply together."""
        assert normalize_component("  Performance - Tracking  ") == "performance_tracking"

    def test_none_returns_unknown(self):
        """None returns 'unknown'."""
        assert normalize_component(None) == "unknown"

    def test_empty_returns_unknown(self):
        """Empty string returns 'unknown'."""
        assert normalize_component("") == "unknown"

    def test_already_normalized(self):
        """Already normalized values pass through."""
        assert normalize_component("pin_scheduler") == "pin_scheduler"


class TestNormalizeProductArea:
    """Tests for normalize_product_area function."""

    def test_spaces_to_underscores(self):
        """Spaces become underscores."""
        assert normalize_product_area("ai creation") == "ai_creation"

    def test_hyphens_to_underscores(self):
        """Hyphens become underscores."""
        assert normalize_product_area("pinterest-publishing") == "pinterest_publishing"

    def test_none_returns_general(self):
        """None returns 'general' (not 'unknown')."""
        assert normalize_product_area(None) == "general"

    def test_empty_returns_general(self):
        """Empty string returns 'general'."""
        assert normalize_product_area("") == "general"


class TestCanonicalizeComponent:
    """Tests for canonicalize_component function (alias map + normalization)."""

    def test_alias_map_applied(self):
        """Known aliases are resolved."""
        # smartschedule -> smart_schedule in scheduling product area
        assert canonicalize_component("smartschedule", "scheduling") == "smart_schedule"
        assert canonicalize_component("SmartSchedule", "scheduling") == "smart_schedule"

    def test_alias_with_different_product_area(self):
        """Alias only applies to matching product area."""
        # smartschedule alias is scoped to 'scheduling'
        # In other product areas, it just normalizes
        assert canonicalize_component("smartschedule", "billing") == "smartschedule"

    def test_non_aliased_passes_through(self):
        """Components without aliases just get format normalized."""
        assert canonicalize_component("pin_scheduler", "scheduling") == "pin_scheduler"
        assert canonicalize_component("Performance Tracking", "analytics") == "performance_tracking"

    def test_format_normalization_applied_first(self):
        """Format normalization happens before alias lookup."""
        # "SmartSchedule" -> "smartschedule" (format) -> "smart_schedule" (alias)
        assert canonicalize_component("SmartSchedule", "scheduling") == "smart_schedule"

    def test_none_returns_unknown(self):
        """None input returns 'unknown'."""
        assert canonicalize_component(None, "scheduling") == "unknown"

    def test_product_area_normalized_for_lookup(self):
        """Product area is normalized before alias lookup."""
        # "Scheduling" -> "scheduling" for lookup
        assert canonicalize_component("smartschedule", "Scheduling") == "smart_schedule"
        assert canonicalize_component("smartschedule", "SCHEDULING") == "smart_schedule"

    def test_custom_alias_lookup(self):
        """Custom alias lookup function can be provided."""
        def custom_lookup(area: str, raw: str) -> str | None:
            if area == "custom" and raw == "foo":
                return "bar"
            return None

        assert canonicalize_component("foo", "custom", alias_lookup=custom_lookup) == "bar"
        assert canonicalize_component("foo", "other", alias_lookup=custom_lookup) == "foo"
