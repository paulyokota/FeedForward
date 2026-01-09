"""
Tests for signature utilities - preventing the signature mismatch issue.

This test suite validates the SignatureRegistry which prevents the issue where:
- Extractor produces: billing_cancellation_request
- PM review changes to: billing_cancellation_requests
- Without tracking, 88% of counts become orphaned
"""

import json
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signature_utils import SignatureRegistry, build_signature_from_components


class TestSignatureNormalization:
    """Test signature normalization to standard format."""

    def test_lowercase(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("BILLING_REQUEST") == "billing_request"

    def test_spaces_to_underscores(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("Billing Cancellation Request") == "billing_cancellation_request"

    def test_hyphens_to_underscores(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("billing-cancellation-request") == "billing_cancellation_request"

    def test_mixed_separators(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("Billing-Cancellation Request") == "billing_cancellation_request"

    def test_collapse_multiple_underscores(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("billing__cancellation___request") == "billing_cancellation_request"

    def test_strip_special_characters(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("billing@cancellation#request!") == "billingcancellationrequest"

    def test_empty_string(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.normalize("") == "unknown"

    def test_none_handling(self):
        registry = SignatureRegistry(auto_load=False)
        # Should handle None gracefully
        assert registry.normalize(None) == "unknown"


class TestEquivalenceTracking:
    """Test equivalence registration and lookup."""

    def test_register_equivalence(self):
        registry = SignatureRegistry(auto_load=False)
        registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")

        assert registry.get_canonical("billing_cancellation_request") == "billing_cancellation_requests"

    def test_canonical_unchanged_if_no_equivalence(self):
        registry = SignatureRegistry(auto_load=False)
        assert registry.get_canonical("unknown_signature") == "unknown_signature"

    def test_get_all_forms(self):
        registry = SignatureRegistry(auto_load=False)
        registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")

        forms = registry.get_all_forms("billing_cancellation_requests")
        assert forms == {"billing_cancellation_request", "billing_cancellation_requests"}

    def test_multiple_equivalences_same_canonical(self):
        registry = SignatureRegistry(auto_load=False)
        registry.register_equivalence("billing_cancel_request", "billing_cancellation_requests")
        registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")

        forms = registry.get_all_forms("billing_cancellation_requests")
        assert "billing_cancel_request" in forms
        assert "billing_cancellation_request" in forms
        assert "billing_cancellation_requests" in forms

    def test_no_self_equivalence(self):
        """Registering same -> same should not create an entry."""
        registry = SignatureRegistry(auto_load=False)
        registry.register_equivalence("billing_request", "billing_request")

        assert len(registry._equivalences) == 0


class TestCountReconciliation:
    """Test reconciling historical counts with story mapping."""

    def test_direct_match(self):
        registry = SignatureRegistry(auto_load=False)

        counts = {"billing_request": 100}
        story_mapping = {"billing_request": {"story_id": 1}}

        reconciled, orphans = registry.reconcile_counts(counts, story_mapping)

        assert reconciled == {"billing_request": 100}
        assert orphans == {}

    def test_equivalence_match(self):
        """The core use case: count key differs from story key."""
        registry = SignatureRegistry(auto_load=False)
        registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")

        counts = {"billing_cancellation_request": 100}
        story_mapping = {"billing_cancellation_requests": {"story_id": 1}}

        reconciled, orphans = registry.reconcile_counts(counts, story_mapping)

        assert reconciled == {"billing_cancellation_requests": 100}
        assert orphans == {}

    def test_merge_both_forms(self):
        """Both original and canonical have counts - should merge."""
        registry = SignatureRegistry(auto_load=False)
        registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")

        counts = {
            "billing_cancellation_request": 100,
            "billing_cancellation_requests": 50
        }
        story_mapping = {"billing_cancellation_requests": {"story_id": 1}}

        reconciled, orphans = registry.reconcile_counts(counts, story_mapping)

        assert reconciled == {"billing_cancellation_requests": 150}
        assert orphans == {}

    def test_orphan_detection(self):
        """Signatures with no story and no equivalence become orphans."""
        registry = SignatureRegistry(auto_load=False)

        counts = {
            "billing_request": 100,
            "unknown_signature": 50
        }
        story_mapping = {"billing_request": {"story_id": 1}}

        reconciled, orphans = registry.reconcile_counts(counts, story_mapping)

        assert reconciled == {"billing_request": 100}
        assert orphans == {"unknown_signature": 50}


class TestPersistence:
    """Test saving and loading equivalences."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create registry with custom path
            registry = SignatureRegistry(auto_load=False)
            registry.EQUIVALENCES_FILE = Path(tmpdir) / "equivalences.json"

            registry.register_equivalence("original", "canonical")
            registry.save()

            # Load in new instance
            registry2 = SignatureRegistry(auto_load=False)
            registry2.EQUIVALENCES_FILE = Path(tmpdir) / "equivalences.json"
            registry2.load()

            assert registry2.get_canonical("original") == "canonical"

    def test_load_nonexistent_file(self):
        """Should handle missing file gracefully."""
        registry = SignatureRegistry(auto_load=False)
        registry.EQUIVALENCES_FILE = Path("/nonexistent/path/file.json")
        registry.load()  # Should not raise

        assert len(registry._equivalences) == 0


class TestBuildSignatureFromComponents:
    """Test building signatures from product/component/issue."""

    def test_with_component(self):
        sig = build_signature_from_components("billing", "invoices", "missing")
        assert sig == "invoices_missing"

    def test_without_component(self):
        sig = build_signature_from_components("billing", "unknown", "payment_failure")
        assert sig == "billing_payment_failure"

    def test_normalization_applied(self):
        sig = build_signature_from_components("Billing", "Invoices", "Missing Invoice")
        # Should be normalized
        assert sig == "invoices_missing_invoice"


class TestRealWorldScenarios:
    """Test scenarios based on actual issues encountered."""

    def test_historical_backfill_scenario(self):
        """
        Scenario: Historical pipeline created stories with PM-modified signatures,
        but backfill counted using original extractor signatures.

        Result without fix: 88% of counts orphaned
        Result with fix: 0% orphaned
        """
        registry = SignatureRegistry(auto_load=False)

        # PM changed these signatures during Phase 1
        registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")
        registry.register_equivalence("guest_post_inquiry", "guest_posting_inquiry")
        registry.register_equivalence("billing_downgrade_request", "billing_plan_downgrade_request")

        # Historical counts use extractor signatures
        counts = {
            "billing_cancellation_request": 3296,
            "guest_post_inquiry": 56,
            "billing_downgrade_request": 72,
            "other_theme": 100  # Has direct match
        }

        # Stories use PM signatures
        story_mapping = {
            "billing_cancellation_requests": {"story_id": 338},
            "guest_posting_inquiry": {"story_id": 355},
            "billing_plan_downgrade_request": {"story_id": 369},
            "other_theme": {"story_id": 500}
        }

        reconciled, orphans = registry.reconcile_counts(counts, story_mapping)

        # All counts should be reconciled
        total_reconciled = sum(reconciled.values())
        total_counts = sum(counts.values())

        assert total_reconciled == total_counts, f"Expected {total_counts}, got {total_reconciled}"
        assert len(orphans) == 0, f"Unexpected orphans: {orphans}"

        # Verify specific mappings
        assert reconciled["billing_cancellation_requests"] == 3296
        assert reconciled["guest_posting_inquiry"] == 56
        assert reconciled["billing_plan_downgrade_request"] == 72


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
