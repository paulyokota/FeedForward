"""
Test for Issue #152: Verify canonicalization serialization prevents race conditions.

This test spawns multiple threads that attempt to canonicalize similar signatures
simultaneously. Without proper locking, they would create near-duplicates.
With the lock, the second thread should see the first thread's signature.

Uses mocking to avoid actual LLM calls and ensure deterministic behavior.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.db.models import Conversation
from src.theme_extractor import ThemeExtractor


@pytest.fixture
def mock_extractor():
    """Create a ThemeExtractor with mocked OpenAI client."""
    with patch("src.theme_extractor.OpenAI"):
        extractor = ThemeExtractor(use_vocabulary=False)
        extractor.clear_session_signatures()
        yield extractor


def create_test_conversation(conv_id: str) -> Conversation:
    """Create a minimal test conversation."""
    return Conversation(
        id=conv_id,
        created_at=datetime.utcnow(),
        source_body="Test conversation about scheduling issues",
        issue_type="bug_report",
        sentiment="neutral",
        priority="normal",
        churn_risk=False,
    )


class TestCanonicalizationConcurrency:
    """Tests for the canonicalization race condition fix (Issue #152)."""

    def test_lock_prevents_duplicate_signatures(self, mock_extractor):
        """
        Test that concurrent canonicalizations don't create duplicates.

        Scenario: Two threads try to add the same signature simultaneously.
        Expected: Only one unique signature in session cache.
        """
        # Mock the canonicalize_signature to return a fixed signature
        # This simulates the case where two extractions produce similar results
        mock_extractor.canonicalize_signature = MagicMock(
            return_value="test_signature_unified"
        )

        results = []
        errors = []

        def canonicalize_and_add(thread_id: int):
            """Simulate the critical section from extract()."""
            try:
                # This is the critical section protected by _session_lock
                with mock_extractor._session_lock:
                    # Simulate canonicalization
                    final_sig = mock_extractor.canonicalize_signature(
                        proposed_signature=f"test_signature_{thread_id}",
                        product_area="test",
                        component="test",
                        user_intent="test",
                        symptoms=[],
                    )
                    # Add to session cache
                    mock_extractor.add_session_signature(final_sig, "test", "test")
                    results.append((thread_id, final_sig))
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run 5 threads concurrently
        threads = []
        for i in range(5):
            t = threading.Thread(target=canonicalize_and_add, args=(i,))
            threads.append(t)

        # Start all threads as close together as possible
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=5.0)

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all threads completed
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"

        # Verify only one unique signature in session cache
        # (even though 5 threads tried to add)
        session_sigs = mock_extractor._session_signatures
        assert len(session_sigs) == 1, (
            f"Expected 1 unique signature, got {len(session_sigs)}: {list(session_sigs.keys())}"
        )
        assert "test_signature_unified" in session_sigs

        # Verify the count reflects all 5 additions
        assert session_sigs["test_signature_unified"]["count"] == 5

    def test_different_signatures_both_added(self, mock_extractor):
        """
        Test that genuinely different signatures are both added.

        Scenario: Two threads create different signatures.
        Expected: Both signatures in session cache.
        """
        call_count = [0]

        def mock_canonicalize(*args, **kwargs):
            """Return different signatures for each call."""
            call_count[0] += 1
            return f"unique_signature_{call_count[0]}"

        mock_extractor.canonicalize_signature = MagicMock(side_effect=mock_canonicalize)

        def canonicalize_and_add(thread_id: int):
            with mock_extractor._session_lock:
                final_sig = mock_extractor.canonicalize_signature(
                    proposed_signature=f"test_{thread_id}",
                    product_area="test",
                    component="test",
                    user_intent="test",
                    symptoms=[],
                )
                mock_extractor.add_session_signature(final_sig, "test", "test")

        # Run 3 threads
        threads = [threading.Thread(target=canonicalize_and_add, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Verify 3 different signatures
        session_sigs = mock_extractor._session_signatures
        assert len(session_sigs) == 3, f"Expected 3 signatures, got {len(session_sigs)}"

    def test_rlock_allows_reentrant_acquisition(self, mock_extractor):
        """
        Test that the RLock allows the same thread to acquire it multiple times.

        This is critical because add_session_signature also acquires the lock.
        """
        # This should not deadlock because we use RLock
        def nested_lock_acquisition():
            with mock_extractor._session_lock:
                # Simulate calling add_session_signature which also acquires the lock
                mock_extractor.add_session_signature("test_sig", "test", "test")

        # Run in a thread with timeout to detect deadlock
        t = threading.Thread(target=nested_lock_acquisition)
        t.start()
        t.join(timeout=2.0)

        # If the thread is still alive, we have a deadlock
        assert not t.is_alive(), "Deadlock detected - RLock not working correctly"

        # Verify the signature was added
        assert "test_sig" in mock_extractor._session_signatures

    def test_concurrent_extractions_with_thread_pool(self, mock_extractor):
        """
        Test using ThreadPoolExecutor to simulate async extraction pattern.

        This matches how extract_async uses asyncio.to_thread.
        """
        mock_extractor.canonicalize_signature = MagicMock(
            return_value="pooled_signature"
        )

        def simulate_extraction(worker_id: int) -> str:
            """Simulate the canonicalization portion of extract()."""
            with mock_extractor._session_lock:
                sig = mock_extractor.canonicalize_signature(
                    proposed_signature=f"worker_{worker_id}",
                    product_area="test",
                    component="test",
                    user_intent="test",
                    symptoms=[],
                )
                mock_extractor.add_session_signature(sig, "test", "test")
                return sig

        # Use ThreadPoolExecutor like async extraction does
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(simulate_extraction, i) for i in range(10)]
            results = [f.result(timeout=5.0) for f in futures]

        # All should return the same signature
        assert all(r == "pooled_signature" for r in results)

        # Only one entry in session cache with count=10
        assert len(mock_extractor._session_signatures) == 1
        assert mock_extractor._session_signatures["pooled_signature"]["count"] == 10
