"""
Pytest configuration for FeedForward tests.

Adds project root to sys.path so tests can import from src/.
Auto-assigns the ``fast`` marker to any test without a tier marker.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Tier markers: fast / medium / slow
# Tests without an explicit tier marker are assumed to be fast (pure unit).
# ---------------------------------------------------------------------------
TIER_MARKERS = {"fast", "medium", "slow"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-assign ``fast`` to tests that have no tier marker."""
    fast_mark = pytest.mark.fast
    for item in items:
        own_markers = {m.name for m in item.iter_markers()}
        if not own_markers & TIER_MARKERS:
            item.add_marker(fast_mark)
