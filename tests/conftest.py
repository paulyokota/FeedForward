"""
Pytest configuration for FeedForward tests.

Test Tier System (Issue #190):
- fast (default): Pure unit tests, all I/O mocked, <2 min total
- medium: Database fixtures, API TestClient, filesystem ops, fast+medium <8 min
- slow: External APIs, pipeline runs, LLM operations

Run tiers:
- pytest                      # Fast only (default, quick feedback)
- pytest -m medium            # Medium only
- pytest -m "not slow"        # Fast + Medium (pre-merge)
- pytest -m slow              # Slow only
- pytest tests/ -v            # Full suite (all tiers)

Parallel execution:
- pytest -n auto              # Auto-detect workers
- pytest -n 4                 # 4 parallel workers
- pytest -n auto -m "not slow"  # Parallel pre-merge run
"""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

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
# pytest-xdist Support for Serial Tests
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Ensure OPENAI_API_KEY has a test value to prevent import errors
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing")


# =============================================================================
# Session-Scoped Fixtures (shared across all tests in session)
# =============================================================================

@pytest.fixture(scope="session")
def project_root():
    """Return project root path (session-scoped for efficiency)."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def test_data_dir(project_root):
    """Return test data directory path."""
    return project_root / "tests" / "data"


# =============================================================================
# Module-Scoped Mock Factories (shared within a module)
# =============================================================================

@pytest.fixture(scope="module")
def _mock_db_factory():
    """
    Module-scoped mock database factory.

    Creates the mock objects once per module to reduce fixture setup overhead.
    Individual tests should use the `mock_db` fixture which resets state.
    """
    mock_conn = Mock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    return mock_conn, mock_cursor


@pytest.fixture(scope="module")
def _mock_openai_factory():
    """
    Module-scoped mock OpenAI client factory.

    Creates mock client once per module. Tests should use `mock_openai_client`
    which provides fresh mock behavior per test.
    """
    from unittest.mock import AsyncMock

    mock_sync = MagicMock()
    mock_sync.chat.completions.create = MagicMock()

    mock_async = AsyncMock()
    mock_async.embeddings.create = AsyncMock()
    mock_async.chat.completions.create = AsyncMock()

    return {'sync': mock_sync, 'async': mock_async}


# =============================================================================
# Function-Scoped Fixtures (per-test isolation)
# =============================================================================

@pytest.fixture
def mock_db(_mock_db_factory):
    """
    Per-test mock database with fresh cursor state.

    Uses module-scoped factory but resets mock call history for test isolation.
    """
    conn, cursor = _mock_db_factory
    cursor.reset_mock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.rowcount = 0
    return conn, cursor


@pytest.fixture
def mock_openai_client(_mock_openai_factory):
    """
    Per-test mock OpenAI client with fresh state.

    Returns dict with 'sync' and 'async' mock clients.
    """
    mock_sync = _mock_openai_factory['sync']
    mock_async = _mock_openai_factory['async']

    # Reset call history
    mock_sync.reset_mock()
    mock_async.reset_mock()

    return {'sync': mock_sync, 'async': mock_async}


@pytest.fixture
def mock_env(monkeypatch):
    """
    Fixture for setting environment variables in tests.

    Usage:
        def test_something(mock_env):
            mock_env("API_KEY", "test-key")
    """
    def _set_env(key, value):
        monkeypatch.setenv(key, value)
    return _set_env


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_conversation():
    """Sample conversation data for tests."""
    from datetime import datetime
    return {
        "id": "test_conv_001",
        "created_at": datetime.utcnow().isoformat(),
        "source_body": "Test conversation content for unit testing",
        "issue_type": "bug_report",
        "sentiment": "neutral",
        "churn_risk": False,
        "priority": "normal",
    }


@pytest.fixture
def sample_theme():
    """Sample theme data for tests."""
    return {
        "id": 1,
        "name": "Test Theme",
        "description": "A theme for testing purposes",
        "conversation_count": 5,
        "created_at": "2024-01-01T00:00:00Z",
    }
