"""
Pytest configuration for FeedForward tests.

Test Tier System (Issue #190):
- fast (default): Pure unit tests, all I/O mocked, <2 min total
- medium: Database fixtures, API TestClient, filesystem ops, fast+medium <8 min
- slow: External APIs, pipeline runs, LLM operations

Run tiers:
- pytest                          # Fast only (default, quick feedback)
- pytest -m medium                # Medium only
- pytest -m "not slow"            # Fast + Medium (pre-merge)
- pytest -m slow                  # Slow only
- pytest --override-ini="addopts=" -v   # Full suite (all tiers)

Parallel execution:
- pytest -n auto                  # Auto-detect workers
- pytest -n auto -m "not slow"    # Parallel pre-merge run

Note: Unmarked tests are auto-assigned to 'fast' tier. To add a new test:
- No marker needed for fast (unit) tests
- Add @pytest.mark.medium for API TestClient tests
- Add @pytest.mark.slow for external API / pipeline tests
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Tier Auto-Assignment
# =============================================================================

def pytest_collection_modifyitems(config, items):
    """
    Automatically assign 'fast' marker to unmarked tests.

    This ensures backward compatibility and makes the tier system opt-out
    rather than opt-in. Tests are fast by default unless explicitly marked
    as medium or slow.
    """
    for item in items:
        # Skip if already has a tier marker
        if any(item.iter_markers(name=tier) for tier in ('fast', 'medium', 'slow')):
            continue

        # Skip if test is marked as skip (don't assign tier to skipped tests)
        if any(item.iter_markers(name='skip')):
            continue

        # Add 'fast' marker to unmarked tests
        item.add_marker(pytest.mark.fast)


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Ensure OPENAI_API_KEY has a test value to prevent import errors.
    # Uses setdefault so real keys in environment are preserved (for slow tests).
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing")


# =============================================================================
# Session-Scoped Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def project_root():
    """Return project root path (session-scoped for efficiency)."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def test_data_dir(project_root):
    """Return test data directory path."""
    return project_root / "tests" / "data"
