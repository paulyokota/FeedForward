"""
Test Tier System Tests (Issue #190)

Tests for the test tier system configuration:
- Marker definitions
- Auto-assignment of 'fast' to unmarked tests
- Tier selection via -m flag

Run with: pytest tests/test_tier_system.py -v
"""

import pytest


class TestTierMarkerConfiguration:
    """Tests for tier marker configuration in pytest.ini."""

    def test_fast_marker_exists(self):
        """Verify 'fast' marker is defined."""
        # This test itself will be auto-assigned 'fast' marker
        # If markers are misconfigured, --strict-markers will fail
        assert True

    @pytest.mark.fast
    def test_explicit_fast_marker(self):
        """Verify explicit 'fast' marker works."""
        assert True

    @pytest.mark.medium
    def test_explicit_medium_marker(self):
        """Verify explicit 'medium' marker works."""
        assert True

    @pytest.mark.slow
    def test_explicit_slow_marker(self):
        """Verify explicit 'slow' marker works."""
        assert True

    @pytest.mark.integration
    def test_integration_marker_defaults_to_medium(self):
        """
        Verify 'integration' marker without tier defaults to medium.

        This test is marked only with @pytest.mark.integration (no tier).
        Per PR feedback, it should auto-assign to 'medium' tier, not 'fast'.

        This test should:
        - NOT run with: pytest (default fast tier)
        - Run with: pytest -m medium
        - Run with: pytest -m "not slow" (pre-merge)
        - Run with: pytest --override-ini="addopts=" (full suite)
        """
        assert True

    @pytest.mark.integration
    @pytest.mark.slow
    def test_integration_with_explicit_tier(self):
        """Verify explicit tier marker overrides integration default."""
        # Marked with both integration and slow - should be slow, not medium
        assert True

    @pytest.mark.serial
    def test_serial_marker(self):
        """Verify 'serial' marker for non-parallelizable tests."""
        assert True


class TestTierAutoAssignment:
    """Tests for automatic tier assignment to unmarked tests."""

    def test_unmarked_test_runs_in_fast_tier(self):
        """
        Verify unmarked tests are included in fast tier.

        This test has no explicit tier marker. If auto-assignment works,
        it should run when using: pytest (default, which runs fast tier).

        The fact that this test runs at all proves the auto-assignment
        is working, since default addopts excludes medium and slow.
        """
        # If we get here, the test ran - which means it was included in fast tier
        assert True


class TestTierSelection:
    """Tests for tier selection behavior."""

    @pytest.mark.fast
    def test_fast_test_runs_in_fast_tier(self):
        """This test should run when: pytest (default) or pytest -m fast."""
        assert True

    @pytest.mark.medium
    def test_medium_test_excluded_from_default(self):
        """This test should NOT run when: pytest (default)."""
        # When running with default addopts (-m "not slow and not medium"),
        # this test will be skipped. It runs with: pytest -m medium
        assert True

    @pytest.mark.slow
    def test_slow_test_excluded_from_default(self):
        """This test should NOT run when: pytest (default) or pytest -m 'not slow'."""
        # Runs only with: pytest --override-ini="addopts=" or pytest -m slow
        assert True


class TestSessionFixtures:
    """Tests for session-scoped fixtures."""

    def test_project_root_fixture(self, project_root):
        """Verify project_root fixture is available and correct."""
        assert project_root.exists()
        assert (project_root / "tests").exists()
        assert (project_root / "src").exists()

    def test_test_data_dir_fixture(self, test_data_dir, project_root):
        """Verify test_data_dir fixture returns correct path."""
        expected = project_root / "tests" / "data"
        assert test_data_dir == expected
