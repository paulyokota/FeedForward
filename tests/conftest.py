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
- Tests marked @pytest.mark.integration (without tier) default to 'medium'

API Key Safety:
- Fast/medium tests force-set a fake OPENAI_API_KEY to prevent accidental API calls
- Only slow tests (and full suite) preserve real API keys from environment
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
    Automatically assign tier markers to unmarked tests.

    This ensures backward compatibility and makes the tier system opt-out
    rather than opt-in. Tests are fast by default unless explicitly marked
    as medium or slow.

    Special case: Tests marked with @pytest.mark.integration (but no tier)
    are assigned to 'medium' tier since integration tests are typically
    heavier than pure unit tests.
    """
    for item in items:
        # Skip if already has a tier marker
        # Note: Using explicit list checks instead of any() for reliability
        has_tier = (
            list(item.iter_markers(name='fast')) or
            list(item.iter_markers(name='medium')) or
            list(item.iter_markers(name='slow'))
        )
        if has_tier:
            continue

        # Skip if test is marked as skip (don't assign tier to skipped tests)
        if list(item.iter_markers(name='skip')):
            continue

        # Integration tests without a tier marker default to medium
        if list(item.iter_markers(name='integration')):
            item.add_marker(pytest.mark.medium)
            continue

        # Add 'fast' marker to unmarked tests
        item.add_marker(pytest.mark.fast)


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Determine if we're running slow tests (which may need real API keys).
    # Check marker expression to decide key handling strategy.
    markexpr = getattr(config.option, 'markexpr', '') or ''

    # Real API keys are ONLY allowed when slow tests are being run:
    # 1. Running slow tests explicitly: -m slow
    # 2. Running full suite: --override-ini="addopts=" (markexpr empty)
    #
    # All other cases force a fake key to prevent accidental API calls:
    # - Default: -m "not slow and not medium" (fast only)
    # - Pre-merge: -m "not slow" (fast + medium)
    # - Medium only: -m medium
    includes_slow_tests = (
        not markexpr or  # Full suite (no marker filter)
        (
            'slow' in markexpr and
            'not slow' not in markexpr  # Positively includes slow tests
        )
    )

    if includes_slow_tests:
        # For slow tests or full suite, preserve real keys if present
        os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing")
    else:
        # Force-set fake key for fast/medium tests to guard against mock failures
        os.environ["OPENAI_API_KEY"] = "sk-test-fake-key-for-testing"


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
