"""
Signature utilities for consistent theme signature handling.

This module provides centralized signature normalization and equivalence tracking
to prevent mismatches between extraction and story creation phases.

KEY DESIGN DECISION:
- All signature comparisons and storage should use normalized signatures
- When PM review suggests a different signature, we track the mapping
- Historical counts can be reconciled by looking up equivalences

Usage:
    from signature_utils import SignatureRegistry

    registry = SignatureRegistry()

    # Register an equivalence when PM review changes a signature
    registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")

    # Normalize any signature for storage/lookup
    normalized = registry.normalize("Billing Cancellation Request")  # -> billing_cancellation_request

    # Find canonical signature (follows equivalences)
    canonical = registry.get_canonical("billing_cancellation_request")  # -> billing_cancellation_requests
"""

import json
import re
from pathlib import Path
from typing import Optional


class SignatureRegistry:
    """
    Registry for signature normalization and equivalence tracking.

    Prevents the signature mismatch issue where:
    - Extractor produces: billing_cancellation_request
    - PM review changes to: billing_cancellation_requests
    - Backfill counts the original, can't match to story

    Solution: Track equivalences and always use canonical form.
    """

    EQUIVALENCES_FILE = Path(__file__).parent.parent / "data" / "signature_equivalences.json"

    def __init__(self, auto_load: bool = True):
        # Maps original -> canonical signature
        self._equivalences: dict[str, str] = {}
        # Reverse mapping for lookup
        self._reverse: dict[str, set[str]] = {}

        if auto_load and self.EQUIVALENCES_FILE.exists():
            self.load()

    def normalize(self, signature: str) -> str:
        """
        Normalize a signature to standard format.

        - Lowercase
        - Replace spaces/hyphens with underscores
        - Remove special characters
        - Collapse multiple underscores

        This is the FIRST step before any signature comparison.
        """
        if not signature:
            return "unknown"

        # Lowercase and replace separators
        normalized = signature.lower()
        normalized = re.sub(r'[\s\-]+', '_', normalized)

        # Remove non-alphanumeric except underscores
        normalized = re.sub(r'[^a-z0-9_]', '', normalized)

        # Collapse multiple underscores
        normalized = re.sub(r'_+', '_', normalized)

        # Strip leading/trailing underscores
        normalized = normalized.strip('_')

        return normalized or "unknown"

    def register_equivalence(self, original: str, canonical: str) -> None:
        """
        Register that `original` signature should map to `canonical`.

        Call this when PM review suggests a different signature than extractor.
        The canonical signature is what's used in story_mapping.

        Args:
            original: The extractor's signature (e.g., billing_cancellation_request)
            canonical: The PM-approved signature (e.g., billing_cancellation_requests)
        """
        original_norm = self.normalize(original)
        canonical_norm = self.normalize(canonical)

        if original_norm == canonical_norm:
            return  # Same signature, no equivalence needed

        self._equivalences[original_norm] = canonical_norm

        # Update reverse mapping
        if canonical_norm not in self._reverse:
            self._reverse[canonical_norm] = set()
        self._reverse[canonical_norm].add(original_norm)

    def get_canonical(self, signature: str) -> str:
        """
        Get the canonical (PM-approved) form of a signature.

        Follows equivalence chain to find the final canonical form.
        Returns the normalized signature if no equivalence exists.
        """
        normalized = self.normalize(signature)

        # Follow equivalence chain (handle transitive mappings)
        seen = {normalized}
        current = normalized

        while current in self._equivalences:
            current = self._equivalences[current]
            if current in seen:
                break  # Prevent infinite loops
            seen.add(current)

        return current

    def get_all_forms(self, canonical: str) -> set[str]:
        """
        Get all signature forms that map to a canonical signature.

        Useful for counting: sum counts for all equivalent forms.
        """
        canonical_norm = self.normalize(canonical)
        forms = {canonical_norm}

        if canonical_norm in self._reverse:
            forms.update(self._reverse[canonical_norm])

        return forms

    def save(self) -> None:
        """Save equivalences to disk."""
        self.EQUIVALENCES_FILE.parent.mkdir(exist_ok=True)

        data = {
            "equivalences": self._equivalences,
            "description": "Maps original extractor signatures to canonical PM-approved signatures"
        }

        with open(self.EQUIVALENCES_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self) -> None:
        """Load equivalences from disk."""
        if not self.EQUIVALENCES_FILE.exists():
            return

        with open(self.EQUIVALENCES_FILE) as f:
            data = json.load(f)

        self._equivalences = data.get("equivalences", {})

        # Rebuild reverse mapping
        self._reverse = {}
        for original, canonical in self._equivalences.items():
            if canonical not in self._reverse:
                self._reverse[canonical] = set()
            self._reverse[canonical].add(original)

    def reconcile_counts(
        self,
        counts: dict[str, int],
        story_mapping: dict[str, dict]
    ) -> dict[str, int]:
        """
        Reconcile historical counts with story mapping using equivalences.

        For each signature in counts:
        1. If it exists in story_mapping, keep as-is
        2. If its canonical form exists in story_mapping, add to canonical
        3. Otherwise, keep as orphan

        Returns reconciled counts keyed by story_mapping signatures.
        """
        reconciled = {}
        orphans = {}

        story_sigs = set(story_mapping.keys())

        for sig, count in counts.items():
            normalized = self.normalize(sig)
            canonical = self.get_canonical(sig)

            # Direct match
            if normalized in story_sigs:
                reconciled[normalized] = reconciled.get(normalized, 0) + count
            # Canonical match
            elif canonical in story_sigs:
                reconciled[canonical] = reconciled.get(canonical, 0) + count
            # Try fuzzy match to story_mapping
            else:
                # Check if any story_mapping key normalizes to same
                matched = False
                for story_sig in story_sigs:
                    if self.normalize(story_sig) == normalized:
                        reconciled[story_sig] = reconciled.get(story_sig, 0) + count
                        matched = True
                        break

                if not matched:
                    orphans[sig] = count

        return reconciled, orphans


def build_signature_from_components(
    product_area: str,
    component: str,
    issue_type: str
) -> str:
    """
    Build a consistent signature from components.

    Format: [component]_[issue_type]
    Falls back to [product_area]_[issue_type] if no component.
    """
    registry = SignatureRegistry(auto_load=False)

    if component and component != "unknown":
        base = f"{component}_{issue_type}"
    elif product_area and product_area != "unknown":
        base = f"{product_area}_{issue_type}"
    else:
        base = issue_type

    return registry.normalize(base)


# Singleton instance for convenience
_registry: Optional[SignatureRegistry] = None


def get_registry() -> SignatureRegistry:
    """Get the global signature registry."""
    global _registry
    if _registry is None:
        _registry = SignatureRegistry()
    return _registry


# Quick test
if __name__ == "__main__":
    registry = SignatureRegistry(auto_load=False)

    # Test normalization
    assert registry.normalize("Billing Cancellation Request") == "billing_cancellation_request"
    assert registry.normalize("billing-cancellation-request") == "billing_cancellation_request"
    assert registry.normalize("BILLING_CANCELLATION_REQUEST") == "billing_cancellation_request"

    # Test equivalences
    registry.register_equivalence("billing_cancellation_request", "billing_cancellation_requests")
    assert registry.get_canonical("billing_cancellation_request") == "billing_cancellation_requests"
    assert registry.get_all_forms("billing_cancellation_requests") == {
        "billing_cancellation_request",
        "billing_cancellation_requests"
    }

    # Test reconciliation
    counts = {
        "billing_cancellation_request": 100,
        "billing_cancellation_requests": 50,
        "unknown_sig": 10,
    }
    story_mapping = {
        "billing_cancellation_requests": {"story_id": 1},
    }

    reconciled, orphans = registry.reconcile_counts(counts, story_mapping)
    assert reconciled["billing_cancellation_requests"] == 150  # 100 + 50
    assert "unknown_sig" in orphans

    print("All tests passed!")
