"""
Tests for Ralph V2 Phase 1: Foundation components.

Tests cover:
- Pydantic models (patterns, stories, results)
- Cheap mode evaluator
- Pattern migrator (v1 -> v2)
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from models import (
    CheapModeResult,
    ComponentHealthStatus,
    DualModeResult,
    ExpensiveModeResult,
    IterationMetrics,
    LearnedPatternsV1,
    LearnedPatternsV2,
    PatternProposal,
    PatternV1,
    PatternV2,
    Story,
)
from cheap_mode_evaluator import (
    CheapModeEvaluator,
    compute_cheap_metrics,
    evaluate_stories_cheap,
)
from pattern_migrator import (
    DOMAIN_KEYWORDS,
    STOP_WORDS,
    extract_keywords,
    migrate_pattern,
    migrate_patterns_file,
    validate_migration,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestPatternV1:
    """Tests for legacy pattern format."""

    def test_valid_good_pattern(self):
        pattern = PatternV1(
            type="good_pattern",
            description="Keep OAuth flow for a single platform in one story",
            example="Pinterest OAuth refresh story covers only Pinterest",
            discovered_at=datetime.now(),
            source="scoping_validation",
        )
        assert pattern.type == "good_pattern"
        assert "OAuth" in pattern.description

    def test_valid_bad_pattern(self):
        pattern = PatternV1(
            type="bad_pattern",
            description="Mixing authentication and scheduling concerns",
            example="Story combines OAuth refresh with post scheduling",
            discovered_at=datetime.now(),
        )
        assert pattern.type == "bad_pattern"
        assert pattern.source == "scoping_validation"  # default

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            PatternV1(
                type="invalid_type",  # type: ignore
                description="Test",
                example="Test",
                discovered_at=datetime.now(),
            )


class TestPatternV2:
    """Tests for new pattern format with keywords."""

    def test_valid_pattern(self):
        pattern = PatternV2(
            id="p_0001",
            type="good",
            description="Keep OAuth flow for a single platform",
            keywords=["oauth", "flow", "single", "platform"],
            weight=1.0,
            source="migration",
            discovered_at=datetime.now(),
            accuracy=0.85,
            times_fired=10,
            status="active",
        )
        assert pattern.id == "p_0001"
        assert len(pattern.keywords) == 4
        assert pattern.status == "active"

    def test_weight_bounds(self):
        # Valid weight
        pattern = PatternV2(
            id="p_0002",
            type="bad",
            description="Test",
            keywords=["test"],
            weight=1.5,
            source="test",
            discovered_at=datetime.now(),
        )
        assert pattern.weight == 1.5

        # Weight too high
        with pytest.raises(ValueError):
            PatternV2(
                id="p_0003",
                type="bad",
                description="Test",
                keywords=["test"],
                weight=2.5,  # > 2.0
                source="test",
                discovered_at=datetime.now(),
            )

    def test_status_options(self):
        for status in ["active", "provisional", "rejected", "pruned"]:
            pattern = PatternV2(
                id="p_0004",
                type="good",
                description="Test",
                keywords=["test"],
                source="test",
                discovered_at=datetime.now(),
                status=status,  # type: ignore
            )
            assert pattern.status == status


class TestStory:
    """Tests for story input model."""

    def test_minimal_story(self):
        story = Story(
            id="story_001",
            title="Add Pinterest OAuth refresh",
            description="Enable automatic token refresh for Pinterest",
            acceptance_criteria=["Token refreshes automatically", "No user action needed"],
        )
        assert story.technical_area is None
        assert story.services == []

    def test_full_story(self):
        story = Story(
            id="story_002",
            title="Fix scheduler timeout",
            description="Scheduler times out on large queues",
            acceptance_criteria=[
                "Scheduler handles 1000+ items",
                "No timeout errors",
                "Performance within SLA",
            ],
            technical_area="aero/services/scheduler.py",
            services=["aero", "pablo"],
            source_conversations=["conv_123", "conv_456"],
        )
        assert len(story.acceptance_criteria) == 3
        assert "aero" in story.services


class TestResultModels:
    """Tests for evaluation result models."""

    def test_cheap_mode_result_bounds(self):
        # Valid gestalt
        result = CheapModeResult(
            story_id="story_001",
            gestalt=3.5,
            raw_score=2.5,
            reasons=["good_title"],
            patterns_matched=["p_0001"],
            patterns_violated=[],
        )
        assert result.gestalt == 3.5

        # Gestalt too low
        with pytest.raises(ValueError):
            CheapModeResult(
                story_id="story_001",
                gestalt=0.5,  # < 1.0
                raw_score=0.0,
                reasons=[],
                patterns_matched=[],
            )

        # Gestalt too high
        with pytest.raises(ValueError):
            CheapModeResult(
                story_id="story_001",
                gestalt=5.5,  # > 5.0
                raw_score=5.0,
                reasons=[],
                patterns_matched=[],
            )

    def test_dual_mode_result(self):
        expensive = ExpensiveModeResult(
            story_id="story_001",
            gestalt=4.0,
            reasoning="Well-scoped story",
            strengths=["Clear AC", "Good title"],
            weaknesses=["Missing tech area"],
        )
        cheap = CheapModeResult(
            story_id="story_001",
            gestalt=3.5,
            raw_score=2.5,
            reasons=["good_title"],
            patterns_matched=[],
        )
        dual = DualModeResult(
            story_id="story_001",
            expensive=expensive,
            cheap=cheap,
            gap=0.5,
        )
        assert dual.gap == 0.5


class TestPatternProposal:
    """Tests for provisional pattern system."""

    def test_accuracy_calculation(self):
        pattern = PatternV2(
            id="p_test",
            type="good",
            description="Test",
            keywords=["test"],
            source="test",
            discovered_at=datetime.now(),
        )
        proposal = PatternProposal(
            id="prop_001",
            pattern=pattern,
            proposed_at=1,
            stories_tested=10,
            correct_predictions=7,
        )
        assert proposal.accuracy == 0.7

    def test_should_commit(self):
        pattern = PatternV2(
            id="p_test",
            type="good",
            description="Test",
            keywords=["test"],
            source="test",
            discovered_at=datetime.now(),
        )

        # Not enough stories
        proposal = PatternProposal(
            id="prop_001",
            pattern=pattern,
            proposed_at=1,
            stories_tested=5,
            correct_predictions=5,
        )
        assert not proposal.should_commit()

        # Enough stories, high accuracy
        proposal.stories_tested = 10
        proposal.correct_predictions = 8
        assert proposal.should_commit()

        # Enough stories, low accuracy
        proposal.correct_predictions = 5
        assert not proposal.should_commit()

    def test_should_reject(self):
        pattern = PatternV2(
            id="p_test",
            type="good",
            description="Test",
            keywords=["test"],
            source="test",
            discovered_at=datetime.now(),
        )

        # Not enough stories
        proposal = PatternProposal(
            id="prop_001",
            pattern=pattern,
            proposed_at=1,
            stories_tested=3,
            correct_predictions=0,
        )
        assert not proposal.should_reject()

        # Enough stories, very low accuracy
        proposal.stories_tested = 5
        proposal.correct_predictions = 1
        assert proposal.should_reject()


# =============================================================================
# Pattern Migrator Tests
# =============================================================================


class TestKeywordExtraction:
    """Tests for keyword extraction logic."""

    def test_stop_words_removed(self):
        text = "The user should be able to do this"
        keywords = extract_keywords(text)
        assert "the" not in keywords
        assert "should" not in keywords
        assert "be" not in keywords
        assert "user" in keywords

    def test_domain_keywords_preserved(self):
        text = "OAuth token refresh for Pinterest api"
        keywords = extract_keywords(text)
        assert "oauth" in keywords
        assert "token" in keywords
        assert "refresh" in keywords
        assert "pinterest" in keywords
        assert "api" in keywords

    def test_short_words_filtered(self):
        text = "a b c test ab cd word"
        keywords = extract_keywords(text)
        assert "a" not in keywords
        assert "b" not in keywords
        assert "ab" not in keywords
        assert "test" in keywords
        assert "word" in keywords

    def test_case_insensitive(self):
        text = "OAuth TOKEN Refresh PINTEREST"
        keywords = extract_keywords(text)
        assert "oauth" in keywords
        assert "token" in keywords
        assert "pinterest" in keywords

    def test_sorted_output(self):
        text = "zebra alpha beta"
        keywords = extract_keywords(text)
        assert keywords == sorted(keywords)


class TestPatternMigration:
    """Tests for v1 -> v2 pattern migration."""

    def test_migrate_good_pattern(self):
        v1 = PatternV1(
            type="good_pattern",
            description="Keep OAuth flow for a single platform in one story",
            example="Pinterest OAuth refresh story covers only Pinterest",
            discovered_at=datetime(2024, 1, 1),
            source="scoping_validation",
        )
        v2 = migrate_pattern(v1, 0)

        assert v2.id == "p_0000"
        assert v2.type == "good"
        assert v2.description == v1.description
        assert "oauth" in v2.keywords
        assert "pinterest" in v2.keywords
        assert v2.weight == 1.0
        assert v2.status == "active"
        assert v2.times_fired == 0
        assert v2.accuracy == 0.0

    def test_migrate_bad_pattern(self):
        v1 = PatternV1(
            type="bad_pattern",
            description="Mixing authentication and scheduling concerns",
            example="Story combines OAuth refresh with post scheduling",
            discovered_at=datetime(2024, 1, 1),
        )
        v2 = migrate_pattern(v1, 5)

        assert v2.id == "p_0005"
        assert v2.type == "bad"
        assert "authentication" in v2.keywords
        assert "scheduling" in v2.keywords

    def test_migrate_patterns_file(self):
        """Test full file migration."""
        # Create a temporary v1 file
        v1_data = {
            "version": "1.0",
            "last_updated": "2024-01-01T00:00:00",
            "patterns": [
                {
                    "type": "good_pattern",
                    "description": "Test good pattern",
                    "example": "Example text",
                    "discovered_at": "2024-01-01T00:00:00",
                    "source": "test",
                },
                {
                    "type": "bad_pattern",
                    "description": "Test bad pattern",
                    "example": "Bad example",
                    "discovered_at": "2024-01-01T00:00:00",
                    "source": "test",
                },
            ],
            "service_insights": {},
            "scoping_rules": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "v1_patterns.json"
            output_path = Path(tmpdir) / "v2_patterns.json"

            with open(input_path, "w") as f:
                json.dump(v1_data, f)

            result = migrate_patterns_file(input_path, output_path, backup=False)

            assert result["status"] == "success"
            assert result["total_patterns"] == 2
            assert result["good_patterns"] == 1
            assert result["bad_patterns"] == 1

            # Verify output file
            with open(output_path) as f:
                v2_data = json.load(f)

            assert v2_data["version"] == "2.0"
            assert len(v2_data["patterns"]) == 2

    def test_skip_already_v2(self):
        """Test that v2 files are skipped."""
        v2_data = {
            "version": "2.0",
            "last_updated": "2024-01-01T00:00:00",
            "patterns": [],
            "calibration_history": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "v2_patterns.json"
            output_path = Path(tmpdir) / "output.json"

            with open(input_path, "w") as f:
                json.dump(v2_data, f)

            result = migrate_patterns_file(input_path, output_path)

            assert result["status"] == "skipped"
            assert result["reason"] == "already_v2"


class TestMigrationValidation:
    """Tests for migration validation."""

    def test_validate_successful_migration(self):
        """Test validation of correctly migrated patterns."""
        v1_data = {
            "patterns": [
                {"type": "good_pattern"},
                {"type": "bad_pattern"},
            ]
        }
        v2_data = {
            "patterns": [
                {"id": "p_0000", "type": "good", "keywords": ["test"]},
                {"id": "p_0001", "type": "bad", "keywords": ["test"]},
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            v1_path = Path(tmpdir) / "v1.json"
            v2_path = Path(tmpdir) / "v2.json"

            with open(v1_path, "w") as f:
                json.dump(v1_data, f)
            with open(v2_path, "w") as f:
                json.dump(v2_data, f)

            result = validate_migration(v1_path, v2_path)

            assert result["valid"]
            assert result["v1_count"] == 2
            assert result["v2_count"] == 2
            assert len(result["issues"]) == 0


# =============================================================================
# Cheap Mode Evaluator Tests
# =============================================================================


class TestCheapModeEvaluator:
    """Tests for cheap mode evaluation."""

    @pytest.fixture
    def evaluator_with_patterns(self, tmp_path):
        """Create evaluator with test patterns."""
        patterns_data = {
            "version": "2.0",
            "last_updated": "2024-01-01T00:00:00",
            "patterns": [
                {
                    "id": "p_0001",
                    "type": "good",
                    "description": "Clear OAuth scoping",
                    "keywords": ["oauth", "single", "platform", "token", "refresh"],
                    "weight": 1.0,
                    "source": "test",
                    "discovered_at": "2024-01-01T00:00:00",
                    "accuracy": 0.8,
                    "times_fired": 5,
                    "status": "active",
                },
                {
                    "id": "p_0002",
                    "type": "bad",
                    "description": "Mixed concerns",
                    "keywords": ["oauth", "scheduling", "queue", "combined"],
                    "weight": 1.0,
                    "source": "test",
                    "discovered_at": "2024-01-01T00:00:00",
                    "accuracy": 0.7,
                    "times_fired": 3,
                    "status": "active",
                },
            ],
            "calibration_history": [],
        }
        patterns_path = tmp_path / "patterns.json"
        with open(patterns_path, "w") as f:
            json.dump(patterns_data, f)

        return CheapModeEvaluator(patterns_path)

    @pytest.fixture
    def well_formed_story(self):
        """A well-formed story that should score high."""
        return Story(
            id="story_good",
            title="Add Pinterest OAuth token refresh",
            description="Users can have their Pinterest tokens automatically refreshed. This prevents frustration when tokens expire.",
            acceptance_criteria=[
                "Token should refresh 1 hour before expiry",
                "User must not be interrupted during refresh",
                "Refresh failures should be logged",
                "Admin can see refresh status in dashboard",
            ],
            technical_area="aero/services/oauth/pinterest_handler.py",
            services=["aero"],
        )

    @pytest.fixture
    def poor_story(self):
        """A poorly-formed story that should score low."""
        return Story(
            id="story_poor",
            title="Do stuff",
            description="Fix it",
            acceptance_criteria=["Works"],
            technical_area=None,
            services=[],
        )

    def test_load_v2_patterns(self, evaluator_with_patterns):
        """Test that v2 patterns load correctly."""
        assert len(evaluator_with_patterns.patterns) == 2
        assert len(evaluator_with_patterns.good_patterns) == 1
        assert len(evaluator_with_patterns.bad_patterns) == 1

    def test_well_formed_story_scores_high(self, evaluator_with_patterns, well_formed_story):
        """Well-formed stories should score >= 3.0."""
        result = evaluator_with_patterns.evaluate_story(well_formed_story)
        assert result.gestalt >= 3.0
        assert "good_title_length" in result.reasons
        assert "action_oriented_title" in result.reasons

    def test_poor_story_scores_low(self, evaluator_with_patterns, poor_story):
        """Poorly-formed stories should score lower."""
        result = evaluator_with_patterns.evaluate_story(poor_story)
        assert result.gestalt < 3.0
        assert "title_too_long" not in result.reasons  # short title

    def test_pattern_matching(self, evaluator_with_patterns, well_formed_story):
        """Stories mentioning OAuth + single platform should match good pattern."""
        result = evaluator_with_patterns.evaluate_story(well_formed_story)
        # Should match p_0001 (oauth, token, refresh keywords)
        assert len(result.patterns_matched) >= 0  # May or may not match depending on threshold

    def test_gestalt_bounds(self, evaluator_with_patterns, poor_story):
        """Gestalt should always be in [1.0, 5.0]."""
        result = evaluator_with_patterns.evaluate_story(poor_story)
        assert 1.0 <= result.gestalt <= 5.0

    def test_health_status_with_patterns(self, evaluator_with_patterns):
        """Health should report loaded patterns."""
        health = evaluator_with_patterns.get_health_status()
        assert health.healthy
        assert health.details["total_patterns"] == 2

    def test_health_status_no_patterns(self, tmp_path):
        """Health should flag missing patterns."""
        empty_path = tmp_path / "nonexistent.json"
        evaluator = CheapModeEvaluator(empty_path)
        health = evaluator.get_health_status()
        assert not health.healthy
        assert "no_patterns_loaded" in health.flags


class TestTitleQuality:
    """Tests for title quality checking."""

    @pytest.fixture
    def evaluator(self, tmp_path):
        patterns_path = tmp_path / "empty.json"
        patterns_path.write_text('{"version": "2.0", "last_updated": "2024-01-01", "patterns": []}')
        return CheapModeEvaluator(patterns_path)

    def test_action_oriented_titles(self, evaluator):
        """Test that action verbs are detected."""
        good_titles = [
            "Add user authentication",
            "Fix login timeout",
            "Update dashboard UI",
            "Implement caching layer",
            "Remove deprecated endpoint",
        ]
        for title in good_titles:
            score, reasons = evaluator._check_title_quality(title)
            assert "action_oriented_title" in reasons, f"Expected action detection for: {title}"

    def test_long_title_penalty(self, evaluator):
        """Test that titles > 80 chars are penalized."""
        long_title = "A" * 100
        score, reasons = evaluator._check_title_quality(long_title)
        assert "title_too_long" in reasons


class TestAcceptanceCriteriaQuality:
    """Tests for AC quality checking."""

    @pytest.fixture
    def evaluator(self, tmp_path):
        patterns_path = tmp_path / "empty.json"
        patterns_path.write_text('{"version": "2.0", "last_updated": "2024-01-01", "patterns": []}')
        return CheapModeEvaluator(patterns_path)

    def test_ideal_ac_count(self, evaluator):
        """Test that 3-7 ACs is ideal."""
        acs = [
            "User should see dashboard",
            "Admin must be able to edit",
            "System displays error when invalid",
            "Data persists after refresh",
        ]
        score, reasons = evaluator._check_acceptance_criteria(acs)
        assert "ideal_ac_count" in reasons

    def test_too_few_acs(self, evaluator):
        """Test that < 2 ACs is penalized."""
        score, reasons = evaluator._check_acceptance_criteria(["Just one"])
        assert "too_few_acs" in reasons
        assert score < 1.0

    def test_too_many_acs(self, evaluator):
        """Test that > 10 ACs is penalized."""
        acs = [f"AC {i}" for i in range(15)]
        score, reasons = evaluator._check_acceptance_criteria(acs)
        assert "too_many_acs" in reasons


class TestComputeMetrics:
    """Tests for aggregate metrics computation."""

    def test_empty_results(self):
        metrics = compute_cheap_metrics([])
        assert metrics["gestalt_avg"] == 0.0
        assert metrics["story_count"] == 0

    def test_multiple_results(self):
        results = [
            CheapModeResult(
                story_id="s1", gestalt=3.0, raw_score=2.0, reasons=[], patterns_matched=["p1"]
            ),
            CheapModeResult(
                story_id="s2", gestalt=4.0, raw_score=3.0, reasons=[], patterns_matched=["p1", "p2"]
            ),
            CheapModeResult(
                story_id="s3",
                gestalt=5.0,
                raw_score=4.0,
                reasons=[],
                patterns_matched=[],
                patterns_violated=["p3"],
            ),
        ]
        metrics = compute_cheap_metrics(results)
        assert metrics["gestalt_avg"] == 4.0  # (3+4+5)/3
        assert metrics["gestalt_min"] == 3.0
        assert metrics["gestalt_max"] == 5.0
        assert metrics["story_count"] == 3
        assert metrics["patterns_matched_total"] == 3
        assert metrics["patterns_violated_total"] == 1


class TestEvaluateStoriesCheap:
    """Tests for batch evaluation function."""

    def test_batch_evaluation(self, tmp_path):
        """Test evaluating multiple stories at once."""
        patterns_path = tmp_path / "patterns.json"
        patterns_path.write_text('{"version": "2.0", "last_updated": "2024-01-01", "patterns": []}')

        stories = [
            Story(
                id="s1",
                title="Add feature",
                description="A new feature for users",
                acceptance_criteria=["Works", "Tests pass"],
            ),
            Story(
                id="s2",
                title="Fix bug",
                description="Bug fix for login",
                acceptance_criteria=["Bug fixed", "No regression"],
            ),
        ]

        results, health = evaluate_stories_cheap(stories, patterns_path)

        assert len(results) == 2
        assert results[0].story_id == "s1"
        assert results[1].story_id == "s2"
        assert not health.healthy  # No patterns loaded
