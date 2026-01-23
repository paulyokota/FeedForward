"""
Tests for stable hybrid signature computation.

Validates that hybrid cluster orphans get deterministic signatures
that enable cross-run accumulation, unlike run-local emb_X_facet_Y_Z.
"""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import Mock


# Test fixture: minimal ConversationData for testing
@dataclass
class MockConversationData:
    """Minimal ConversationData for signature tests."""

    id: str
    issue_signature: str = ""  # Preferred for stable signatures
    product_area: Optional[str] = None
    component: Optional[str] = None  # Included in signature
    user_intent: Optional[str] = None
    symptoms: List[str] = field(default_factory=list)  # Fallback only
    affected_flow: Optional[str] = None


@dataclass
class MockHybridCluster:
    """Minimal HybridCluster for signature tests."""

    cluster_id: str
    action_type: str
    direction: str
    embedding_cluster: int = 0
    conversation_ids: List[str] = field(default_factory=list)


class TestStableHybridSignature:
    """Tests for _compute_stable_hybrid_signature method."""

    @pytest.fixture
    def service(self):
        """Create a StoryCreationService with mocked dependencies."""
        from src.story_tracking.services.story_creation_service import (
            StoryCreationService,
        )

        # Mock the required services
        mock_story_service = Mock()
        mock_orphan_service = Mock()

        return StoryCreationService(
            story_service=mock_story_service,
            orphan_service=mock_orphan_service,
        )

    def test_same_issue_different_clusters_get_same_signature(self, service):
        """
        Two hybrid clusters with same semantic content get same stable signature,
        even if their emb_X cluster IDs differ.
        """
        # Cluster from run 81: emb_5_facet_complaint_deficit
        cluster_run81 = MockHybridCluster(
            cluster_id="emb_5_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
            embedding_cluster=5,
        )

        # Cluster from run 82: emb_3_facet_complaint_deficit (same issue, different index)
        cluster_run82 = MockHybridCluster(
            cluster_id="emb_3_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
            embedding_cluster=3,
        )

        # Same conversations with same semantic content (using issue_signature for stability)
        conversations = [
            MockConversationData(
                id="conv1",
                product_area="scheduling",
                component="calendar",
                issue_signature="appointment_sync_failure",
            ),
            MockConversationData(
                id="conv2",
                product_area="scheduling",
                component="calendar",
                issue_signature="appointment_sync_failure",
            ),
        ]

        sig1 = service._compute_stable_hybrid_signature(cluster_run81, conversations)
        sig2 = service._compute_stable_hybrid_signature(cluster_run82, conversations)

        assert sig1 == sig2, "Same semantic content should produce same signature"
        assert "emb_" not in sig1, "Stable signature should not contain run-local emb_X"
        assert sig1.startswith("hybrid_"), "Stable signature should start with hybrid_"

    def test_different_issues_get_different_signatures(self, service):
        """Different action_type/direction/product_area/component produce different signatures."""
        # Deficit complaint about scheduling/calendar
        cluster1 = MockHybridCluster(
            cluster_id="emb_1_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
        )
        conversations1 = [
            MockConversationData(
                id="conv1",
                product_area="scheduling",
                component="calendar",
                issue_signature="appointment_missing",
            ),
        ]

        # Excess complaint about billing/invoices
        cluster2 = MockHybridCluster(
            cluster_id="emb_2_facet_complaint_excess",
            action_type="complaint",
            direction="excess",
        )
        conversations2 = [
            MockConversationData(
                id="conv2",
                product_area="billing",
                component="invoices",
                issue_signature="double_charge",
            ),
        ]

        sig1 = service._compute_stable_hybrid_signature(cluster1, conversations1)
        sig2 = service._compute_stable_hybrid_signature(cluster2, conversations2)

        assert sig1 != sig2, "Different issues should have different signatures"

    def test_signature_deterministic_across_conversation_order(self, service):
        """Signature doesn't change based on conversation ordering."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )

        conversations_order1 = [
            MockConversationData(
                id="conv1",
                product_area="dashboard",
                component="widgets",
                issue_signature="widget_render_failure",
            ),
            MockConversationData(
                id="conv2",
                product_area="dashboard",
                component="widgets",
                issue_signature="widget_render_failure",
            ),
        ]

        conversations_order2 = [
            MockConversationData(
                id="conv2",
                product_area="dashboard",
                component="widgets",
                issue_signature="widget_render_failure",
            ),
            MockConversationData(
                id="conv1",
                product_area="dashboard",
                component="widgets",
                issue_signature="widget_render_failure",
            ),
        ]

        sig1 = service._compute_stable_hybrid_signature(cluster, conversations_order1)
        sig2 = service._compute_stable_hybrid_signature(cluster, conversations_order2)

        assert sig1 == sig2, "Signature should be deterministic regardless of order"

    def test_fallback_on_missing_product_area(self, service):
        """Gracefully handles missing product_area."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_inquiry_neutral",
            action_type="inquiry",
            direction="neutral",
        )
        conversations = [
            MockConversationData(id="conv1", product_area=None, component=None),
            MockConversationData(id="conv2", product_area=None, component=None),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert "general" in sig, "Missing product_area should use 'general' fallback"
        assert "unknown" in sig, "Missing component should use 'unknown' fallback"
        assert sig.startswith("hybrid_"), "Should still produce valid signature"

    def test_fallback_on_missing_issue_signature_uses_symptoms(self, service):
        """Falls back to symptoms when issue_signature is missing."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_feature_request_neutral",
            action_type="feature_request",
            direction="neutral",
        )
        conversations = [
            MockConversationData(
                id="conv1",
                product_area="reports",
                component="analytics",
                issue_signature="",  # Empty - should fallback
                symptoms=["export fails", "timeout error"],
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        # Should contain symptom-based fallback
        assert "export" in sig or "timeout" in sig, "Should fallback to symptoms"

    def test_fallback_on_missing_everything_uses_unspecified(self, service):
        """Uses 'unspecified' when both issue_signature and symptoms are missing."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_feature_request_neutral",
            action_type="feature_request",
            direction="neutral",
        )
        conversations = [
            MockConversationData(
                id="conv1",
                product_area="reports",
                component="analytics",
                issue_signature="",
                symptoms=[],
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert "unspecified" in sig, "Missing issue_signature and symptoms should use 'unspecified'"

    def test_fallback_on_missing_action_type(self, service):
        """Gracefully handles missing action_type."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_unknown_neutral",
            action_type=None,
            direction="neutral",
        )
        conversations = [
            MockConversationData(id="conv1", product_area="settings", component="prefs"),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert sig.startswith("hybrid_unknown_"), "Missing action_type should use 'unknown' fallback"

    def test_signature_format_correct(self, service):
        """Verify format: hybrid_{action}_{direction}_{area}_{component}_{issue_part}."""
        cluster = MockHybridCluster(
            cluster_id="emb_7_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
        )
        conversations = [
            MockConversationData(
                id="conv1",
                product_area="Billing",
                component="Invoices",
                issue_signature="double_charge_error",
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        # Verify format: hybrid_{action}_{direction}_{area}_{component}_{issue}
        assert sig.startswith("hybrid_complaint_deficit_")
        assert "billing" in sig.lower()  # product_area normalized
        assert "invoices" in sig.lower()  # component normalized
        assert "double_charge" in sig.lower()  # issue_signature included

    def test_product_area_normalization(self, service):
        """Product area is normalized (lowercase, underscores)."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )

        # Same product area with different casing/formatting
        conv1 = [
            MockConversationData(
                id="c1",
                product_area="User Settings",
                component="prefs",
                issue_signature="save_failure",
            )
        ]
        conv2 = [
            MockConversationData(
                id="c2",
                product_area="user-settings",
                component="prefs",
                issue_signature="save_failure",
            )
        ]
        conv3 = [
            MockConversationData(
                id="c3",
                product_area="USER SETTINGS",
                component="prefs",
                issue_signature="save_failure",
            )
        ]

        sig1 = service._compute_stable_hybrid_signature(cluster, conv1)
        sig2 = service._compute_stable_hybrid_signature(cluster, conv2)
        sig3 = service._compute_stable_hybrid_signature(cluster, conv3)

        assert sig1 == sig2 == sig3, "Product area normalization should make them equal"

    def test_issue_signature_truncation(self, service):
        """Long issue_signature is truncated to prevent overly long signatures."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )
        conversations = [
            MockConversationData(
                id="conv1",
                product_area="dashboard",
                component="widgets",
                issue_signature="this_is_a_very_long_issue_signature_that_should_be_truncated_to_forty_characters_maximum",
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        # Signature should be reasonable length
        assert len(sig) < 150, "Signature should not be excessively long"

    def test_most_common_product_area_used(self, service):
        """When conversations have different product_areas, most common is used."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
        )
        conversations = [
            MockConversationData(
                id="c1", product_area="billing", component="charges", issue_signature="overcharge"
            ),
            MockConversationData(
                id="c2", product_area="billing", component="charges", issue_signature="overcharge"
            ),
            MockConversationData(
                id="c3", product_area="scheduling", component="calendar", issue_signature="overcharge"
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert "billing" in sig, "Most common product_area should be used"

    def test_issue_signature_preferred_over_symptoms(self, service):
        """issue_signature is used when available, symptoms ignored."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )

        conversations = [
            MockConversationData(
                id="c1",
                product_area="dashboard",
                component="charts",
                issue_signature="chart_render_failure",
                symptoms=["generic error", "something broke"],  # Should be ignored
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert "chart_render_failure" in sig, "issue_signature should be used"
        assert "generic" not in sig, "Symptoms should be ignored when issue_signature exists"

    def test_unclassified_issue_signature_falls_back_to_symptoms(self, service):
        """issue_signature containing 'unclassified' triggers symptom fallback."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )

        conversations = [
            MockConversationData(
                id="c1",
                product_area="dashboard",
                component="charts",
                issue_signature="unclassified_issue",  # Should be skipped
                symptoms=["chart fails to load"],
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert "unclassified" not in sig, "Unclassified signature should be skipped"
        assert "chart" in sig or "fails" in sig, "Should fallback to symptoms"

    def test_component_included_in_signature(self, service):
        """Component is included and normalized in the signature."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
        )

        conv1 = [
            MockConversationData(
                id="c1",
                product_area="billing",
                component="Invoice Generator",
                issue_signature="pdf_error",
            )
        ]
        conv2 = [
            MockConversationData(
                id="c2",
                product_area="billing",
                component="Payment Processor",
                issue_signature="pdf_error",
            )
        ]

        sig1 = service._compute_stable_hybrid_signature(cluster, conv1)
        sig2 = service._compute_stable_hybrid_signature(cluster, conv2)

        assert sig1 != sig2, "Different components should produce different signatures"
        assert "invoice_generator" in sig1
        assert "payment_processor" in sig2

    def test_emb_issue_signature_is_ignored(self, service):
        """
        CRITICAL: issue_signature set to cluster_id (emb_*) must be ignored.

        In hybrid clusters, _dict_to_conversation_data sets issue_signature
        to cluster.cluster_id, which is run-local. If we don't skip it,
        the "stable" signature will contain emb_X and won't accumulate.
        """
        cluster = MockHybridCluster(
            cluster_id="emb_5_facet_complaint_deficit",
            action_type="complaint",
            direction="deficit",
        )

        # issue_signature is set to cluster_id (common in hybrid path)
        conversations = [
            MockConversationData(
                id="c1",
                product_area="scheduling",
                component="calendar",
                issue_signature="emb_5_facet_complaint_deficit",  # Run-local!
                symptoms=["appointment missing", "sync failed"],
            ),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        assert "emb_" not in sig, "Run-local emb_* issue_signature must be ignored"
        assert sig.startswith("hybrid_"), "Should still produce valid signature"
        # Should fallback to symptoms since issue_signature is skipped
        assert "appointment" in sig or "sync" in sig, "Should use symptom fallback"

    def test_deterministic_tie_breaking_product_area(self, service):
        """Product area selection is deterministic when tied (alphabetical)."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )

        # Two product areas with equal counts - should pick alphabetically first
        conversations = [
            MockConversationData(id="c1", product_area="billing", component="x"),
            MockConversationData(id="c2", product_area="scheduling", component="x"),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        # "billing" comes before "scheduling" alphabetically
        assert "billing" in sig, "Should pick alphabetically first on tie"

    def test_deterministic_tie_breaking_component(self, service):
        """Component selection is deterministic when tied (alphabetical)."""
        cluster = MockHybridCluster(
            cluster_id="emb_1_facet_bug_report_deficit",
            action_type="bug_report",
            direction="deficit",
        )

        # Two components with equal counts - should pick alphabetically first
        conversations = [
            MockConversationData(id="c1", product_area="billing", component="widgets"),
            MockConversationData(id="c2", product_area="billing", component="charts"),
        ]

        sig = service._compute_stable_hybrid_signature(cluster, conversations)

        # "charts" comes before "widgets" alphabetically
        assert "charts" in sig, "Should pick alphabetically first on tie"
