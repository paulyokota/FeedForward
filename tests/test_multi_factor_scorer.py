"""
Tests for MultiFactorScorer.

Issue #188: Add sortable multi-factor story scoring
"""

import pytest
from datetime import datetime, timezone

from src.multi_factor_scorer import (
    MultiFactorScorer,
    StoryScoreInput,
    ConversationScoreData,
    MultiFactorScores,
    create_default_scores,
    ACTIONABILITY_IMPL_CONTEXT,
    ACTIONABILITY_RESOLUTION_ACTION,
    ACTIONABILITY_RESOLUTION_CATEGORY,
    ACTIONABILITY_KEY_EXCERPTS,
    ACTIONABILITY_DIAGNOSTIC_SUMMARY,
    ACTIONABILITY_EVIDENCE_BONUS,
    SEVERITY_PRIORITY_MAP,
    CHURN_RISK_TRUE_BASE,
    CHURN_RISK_FALSE_BASE,
    CHURN_RISK_UNKNOWN_DEFAULT,
)


class TestMultiFactorScorer:
    """Test suite for MultiFactorScorer."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer instance."""
        return MultiFactorScorer()

    @pytest.fixture
    def minimal_conversation(self):
        """Create a minimal conversation for testing."""
        return ConversationScoreData(id="conv-1")

    @pytest.fixture
    def full_conversation(self):
        """Create a conversation with all fields populated."""
        return ConversationScoreData(
            id="conv-1",
            priority="high",
            churn_risk=True,
            org_id="org-123",
            diagnostic_summary="User experiencing timeout errors when loading dashboard",
            key_excerpts=[{"text": "error loading", "relevance": "high"}],
            symptoms=["timeout", "slow loading", "dashboard"],
            resolution_action="escalated_to_engineering",
            resolution_category="escalation",
        )

    # =========================================================================
    # ACTIONABILITY SCORE TESTS
    # =========================================================================

    def test_actionability_all_factors_present(self, scorer, full_conversation):
        """Test actionability score when all factors are present."""
        input_data = StoryScoreInput(
            conversations=[full_conversation],
            implementation_context={"summary": "Fix the timeout issue"},
            evidence_count=5,  # >= 3 threshold
        )

        scores = scorer.score(input_data)

        # All factors should contribute
        expected_min = (
            ACTIONABILITY_IMPL_CONTEXT +
            ACTIONABILITY_RESOLUTION_ACTION +
            ACTIONABILITY_RESOLUTION_CATEGORY +
            ACTIONABILITY_KEY_EXCERPTS +
            ACTIONABILITY_DIAGNOSTIC_SUMMARY +
            ACTIONABILITY_EVIDENCE_BONUS
        )
        assert scores.actionability_score == expected_min
        assert scores.metadata["actionability"]["total"] == expected_min

    def test_actionability_minimal_data(self, scorer, minimal_conversation):
        """Test actionability score with minimal data returns 0."""
        input_data = StoryScoreInput(
            conversations=[minimal_conversation],
            evidence_count=1,
        )

        scores = scorer.score(input_data)

        assert scores.actionability_score == 0
        assert scores.metadata["actionability"]["implementation_context_present"] == 0

    def test_actionability_partial_data(self, scorer):
        """Test actionability with some but not all factors."""
        conv = ConversationScoreData(
            id="conv-1",
            diagnostic_summary="Issue description",
            resolution_action="provided_workaround",
        )
        input_data = StoryScoreInput(
            conversations=[conv],
            evidence_count=1,
        )

        scores = scorer.score(input_data)

        # Should have diagnostic_summary and resolution_action bonuses
        expected = ACTIONABILITY_DIAGNOSTIC_SUMMARY + ACTIONABILITY_RESOLUTION_ACTION
        assert scores.actionability_score == expected

    # =========================================================================
    # FIX SIZE SCORE TESTS
    # =========================================================================

    def test_fix_size_normalization(self, scorer):
        """Test fix_size score is normalized to 0-100."""
        conv = ConversationScoreData(
            id="conv-1",
            key_excerpts=[{"text": f"excerpt {i}"} for i in range(20)],  # 20 excerpts
            symptoms=["s1", "s2", "s3", "s4", "s5", "s6"],  # >= 5 symptoms
        )
        input_data = StoryScoreInput(
            conversations=[conv],
            implementation_context={"relevant_files": [{"path": f"/file{i}.py"} for i in range(15)]},
            code_context={"relevant_files": [{"path": "/code.py"}]},
        )

        scores = scorer.score(input_data)

        # Should be normalized to max 100
        assert 0 <= scores.fix_size_score <= 100
        assert scores.metadata["fix_size"]["normalized"] is True

    def test_fix_size_empty_data(self, scorer, minimal_conversation):
        """Test fix_size with no contributing factors."""
        input_data = StoryScoreInput(
            conversations=[minimal_conversation],
        )

        scores = scorer.score(input_data)

        assert scores.fix_size_score == 0
        assert scores.metadata["fix_size"]["raw_total"] == 0

    def test_fix_size_caps_at_limits(self, scorer):
        """Test that individual factors are capped correctly."""
        conv = ConversationScoreData(
            id="conv-1",
            key_excerpts=[{"text": f"excerpt {i}"} for i in range(50)],  # Way over cap
        )
        input_data = StoryScoreInput(
            conversations=[conv],
            implementation_context={"relevant_files": [{"path": f"/file{i}.py"} for i in range(100)]},  # Way over cap
        )

        scores = scorer.score(input_data)
        breakdown = scores.metadata["fix_size"]

        # Files capped at 40, excerpts capped at 20
        assert breakdown["relevant_files_score"] <= 40
        assert breakdown["evidence_excerpts_score"] <= 20

    # =========================================================================
    # SEVERITY SCORE TESTS
    # =========================================================================

    def test_severity_priority_mapping_urgent(self, scorer):
        """Test severity score for urgent priority."""
        conv = ConversationScoreData(id="conv-1", priority="urgent")
        input_data = StoryScoreInput(conversations=[conv])

        scores = scorer.score(input_data)

        assert scores.severity_score == SEVERITY_PRIORITY_MAP["urgent"]
        assert scores.metadata["severity"]["max_priority"] == "urgent"

    def test_severity_priority_mapping_high(self, scorer):
        """Test severity score for high priority."""
        conv = ConversationScoreData(id="conv-1", priority="high")
        input_data = StoryScoreInput(conversations=[conv])

        scores = scorer.score(input_data)

        assert scores.severity_score == SEVERITY_PRIORITY_MAP["high"]

    def test_severity_priority_mapping_low(self, scorer):
        """Test severity score for low priority."""
        conv = ConversationScoreData(id="conv-1", priority="low")
        input_data = StoryScoreInput(conversations=[conv])

        scores = scorer.score(input_data)

        assert scores.severity_score == SEVERITY_PRIORITY_MAP["low"]

    def test_severity_takes_max_priority(self, scorer):
        """Test that severity uses max priority across conversations."""
        convs = [
            ConversationScoreData(id="conv-1", priority="low"),
            ConversationScoreData(id="conv-2", priority="urgent"),
            ConversationScoreData(id="conv-3", priority="medium"),
        ]
        input_data = StoryScoreInput(conversations=convs)

        scores = scorer.score(input_data)

        # Should use urgent (highest)
        assert scores.severity_score == SEVERITY_PRIORITY_MAP["urgent"]

    def test_severity_cap_at_100(self, scorer):
        """Test severity is capped at 100."""
        conv = ConversationScoreData(
            id="conv-1",
            priority="urgent",
            diagnostic_summary="critical failure crash timeout error",
        )
        input_data = StoryScoreInput(
            conversations=[conv],
            platform_uniformity=1.0,
            product_area_match=True,
        )

        scores = scorer.score(input_data)

        # Even with all bonuses, should cap at 100
        assert scores.severity_score <= 100
        assert scores.metadata["severity"]["capped"] is True

    def test_severity_error_keywords(self, scorer):
        """Test severity bonus for error keywords in diagnostic."""
        conv = ConversationScoreData(
            id="conv-1",
            priority="low",  # Base of 20
            diagnostic_summary="The application crashed with a timeout error",
        )
        input_data = StoryScoreInput(conversations=[conv])

        scores = scorer.score(input_data)

        # Should have error keyword bonus
        assert scores.severity_score > SEVERITY_PRIORITY_MAP["low"]
        assert len(scores.metadata["severity"]["error_keywords_found"]) > 0

    def test_severity_focused_impact_bonus(self, scorer):
        """Test severity bonus for focused impact."""
        conv = ConversationScoreData(id="conv-1", priority="medium")
        input_data = StoryScoreInput(
            conversations=[conv],
            platform_uniformity=1.0,
            product_area_match=True,
        )

        scores = scorer.score(input_data)

        # Should have focused impact bonus
        assert scores.metadata["severity"]["focused_impact"] is True
        assert scores.metadata["severity"]["focused_impact_bonus"] == 10

    # =========================================================================
    # CHURN RISK SCORE TESTS
    # =========================================================================

    def test_churn_risk_true_base(self, scorer):
        """Test churn risk score when flag is True."""
        conv = ConversationScoreData(id="conv-1", churn_risk=True)
        input_data = StoryScoreInput(conversations=[conv])

        scores = scorer.score(input_data)

        assert scores.churn_risk_score >= CHURN_RISK_TRUE_BASE
        assert scores.metadata["churn_risk"]["churn_risk_source"] == "flagged"

    def test_churn_risk_false_base(self, scorer):
        """Test churn risk score when flag is explicitly False."""
        conv = ConversationScoreData(id="conv-1", churn_risk=False)
        input_data = StoryScoreInput(conversations=[conv])

        scores = scorer.score(input_data)

        assert scores.churn_risk_score >= CHURN_RISK_FALSE_BASE
        assert scores.metadata["churn_risk"]["churn_risk_source"] == "not_flagged"

    def test_churn_risk_unknown_default(self, scorer, minimal_conversation):
        """Test churn risk score when no churn data available."""
        input_data = StoryScoreInput(conversations=[minimal_conversation])

        scores = scorer.score(input_data)

        assert scores.churn_risk_score >= CHURN_RISK_UNKNOWN_DEFAULT
        assert scores.metadata["churn_risk"]["churn_risk_source"] == "unknown"

    def test_churn_risk_org_breadth_bonus(self, scorer):
        """Test churn risk org breadth bonus."""
        convs = [
            ConversationScoreData(id=f"conv-{i}", churn_risk=True, org_id=f"org-{i}")
            for i in range(5)
        ]
        input_data = StoryScoreInput(conversations=convs)

        scores = scorer.score(input_data)

        # 5 unique orgs should give max breadth bonus
        assert scores.metadata["churn_risk"]["unique_org_count"] == 5
        assert scores.metadata["churn_risk"]["org_breadth_bonus"] > 0
        assert scores.churn_risk_score > CHURN_RISK_TRUE_BASE

    def test_churn_risk_any_flagged_is_high(self, scorer):
        """Test that any churn_risk=True results in high base."""
        convs = [
            ConversationScoreData(id="conv-1", churn_risk=False),
            ConversationScoreData(id="conv-2", churn_risk=True),
            ConversationScoreData(id="conv-3", churn_risk=False),
        ]
        input_data = StoryScoreInput(conversations=convs)

        scores = scorer.score(input_data)

        assert scores.churn_risk_score >= CHURN_RISK_TRUE_BASE
        assert scores.metadata["churn_risk"]["churn_risk_source"] == "flagged"

    # =========================================================================
    # METADATA STRUCTURE TESTS
    # =========================================================================

    def test_metadata_structure(self, scorer, full_conversation):
        """Test that metadata has expected structure."""
        input_data = StoryScoreInput(
            conversations=[full_conversation],
            implementation_context={"summary": "Fix it"},
            evidence_count=5,
        )

        scores = scorer.score(input_data)

        # Check top-level keys
        assert "schema_version" in scores.metadata
        assert "computed_at" in scores.metadata
        assert "conversation_count" in scores.metadata
        assert "actionability" in scores.metadata
        assert "fix_size" in scores.metadata
        assert "severity" in scores.metadata
        assert "churn_risk" in scores.metadata

        # Check schema version
        assert scores.metadata["schema_version"] == "1.0"

        # Check computed_at is valid ISO format
        datetime.fromisoformat(scores.metadata["computed_at"].replace("Z", "+00:00"))

    def test_metadata_conversation_count(self, scorer):
        """Test metadata includes correct conversation count."""
        convs = [ConversationScoreData(id=f"conv-{i}") for i in range(7)]
        input_data = StoryScoreInput(conversations=convs)

        scores = scorer.score(input_data)

        assert scores.metadata["conversation_count"] == 7

    # =========================================================================
    # FROM_CONVERSATION_DICTS TESTS
    # =========================================================================

    def test_from_conversation_dicts(self, scorer):
        """Test creating input from raw dicts (pipeline format)."""
        dicts = [
            {
                "id": "conv-1",
                "priority": "urgent",
                "churn_risk": True,
                "org_id": "org-1",
                "diagnostic_summary": "Error occurred",
                "key_excerpts": [{"text": "error"}],
                "symptoms": ["crash"],
                "resolution_action": "escalated_to_engineering",
                "resolution_category": "escalation",
            }
        ]

        input_data = StoryScoreInput.from_conversation_dicts(
            conv_dicts=dicts,
            implementation_context={"summary": "Fix"},
            evidence_count=3,
        )

        scores = scorer.score(input_data)

        # Should be able to score from dict input
        assert scores.severity_score == SEVERITY_PRIORITY_MAP["urgent"]
        assert scores.churn_risk_score >= CHURN_RISK_TRUE_BASE

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_empty_conversations_list(self, scorer):
        """Test handling empty conversations list."""
        input_data = StoryScoreInput(conversations=[])

        scores = scorer.score(input_data)

        # Should handle gracefully with defaults
        assert scores.actionability_score == 0
        assert scores.fix_size_score == 0
        assert scores.severity_score == 0
        assert scores.churn_risk_score >= CHURN_RISK_UNKNOWN_DEFAULT

    def test_none_values_handled(self, scorer):
        """Test that None values in conversation data are handled."""
        conv = ConversationScoreData(
            id="conv-1",
            priority=None,
            churn_risk=None,
            org_id=None,
            diagnostic_summary=None,
            key_excerpts=None,
            symptoms=None,
        )
        input_data = StoryScoreInput(conversations=[conv])

        # Should not raise
        scores = scorer.score(input_data)

        assert isinstance(scores, MultiFactorScores)


class TestCreateDefaultScores:
    """Test suite for create_default_scores helper."""

    def test_default_scores_values(self):
        """Test default scores have expected values."""
        scores = create_default_scores()

        assert scores.actionability_score == 0.0
        assert scores.fix_size_score == 0.0
        assert scores.severity_score == 40.0  # Neutral midpoint
        assert scores.churn_risk_score == 40.0  # Neutral midpoint

    def test_default_scores_metadata(self):
        """Test default scores have metadata note."""
        scores = create_default_scores()

        assert "note" in scores.metadata
        assert "Default scores" in scores.metadata["note"]
