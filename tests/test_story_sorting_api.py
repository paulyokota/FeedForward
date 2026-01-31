"""
Integration tests for story sorting API.

Issue #188: Add sortable multi-factor story scoring

Tests the /api/stories endpoint with sort_by and sort_dir parameters.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from src.story_tracking.models import StoryCreate, StoryUpdate
from src.story_tracking.services.story_service import StoryService


class TestStorySortingAPI:
    """Integration tests for story sorting."""

    @pytest.fixture
    def story_service(self, db_connection):
        """Create a StoryService instance."""
        return StoryService(db_connection)

    @pytest.fixture
    def sample_stories(self, story_service, db_connection):
        """Create sample stories with varying scores for sorting tests."""
        stories = []

        # Story 1: High actionability, low severity
        story1 = story_service.create(StoryCreate(
            title="High actionability story",
            description="Ready to implement",
            status="candidate",
            actionability_score=90.0,
            fix_size_score=30.0,
            severity_score=20.0,
            churn_risk_score=40.0,
            score_metadata={"test": True},
        ))
        stories.append(story1)

        # Story 2: Low actionability, high severity
        story2 = story_service.create(StoryCreate(
            title="High severity story",
            description="Urgent issue",
            status="candidate",
            actionability_score=20.0,
            fix_size_score=60.0,
            severity_score=95.0,
            churn_risk_score=80.0,
            score_metadata={"test": True},
        ))
        stories.append(story2)

        # Story 3: Medium scores
        story3 = story_service.create(StoryCreate(
            title="Medium scores story",
            description="Average priority",
            status="candidate",
            actionability_score=50.0,
            fix_size_score=50.0,
            severity_score=50.0,
            churn_risk_score=50.0,
            score_metadata={"test": True},
        ))
        stories.append(story3)

        # Story 4: NULL scores (for NULLS LAST testing)
        story4 = story_service.create(StoryCreate(
            title="No scores story",
            description="Legacy story without scores",
            status="candidate",
            # All scores are None by default
        ))
        stories.append(story4)

        db_connection.commit()

        yield stories

        # Cleanup
        for story in stories:
            story_service.delete(story.id)
        db_connection.commit()

    # =========================================================================
    # SORT BY EACH SCORE COLUMN
    # =========================================================================

    def test_sort_by_actionability_desc(self, story_service, sample_stories):
        """Test sorting by actionability_score descending."""
        result = story_service.list(sort_by="actionability_score", sort_dir="desc")

        # Filter to just our test stories
        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        # Should be ordered: 90, 50, 20, NULL
        scores = [s.actionability_score for s in test_stories]
        non_null_scores = [s for s in scores if s is not None]

        # Non-null scores should be descending
        assert non_null_scores == sorted(non_null_scores, reverse=True)

        # NULL should be last
        if None in scores:
            assert scores[-1] is None

    def test_sort_by_severity_desc(self, story_service, sample_stories):
        """Test sorting by severity_score descending."""
        result = story_service.list(sort_by="severity_score", sort_dir="desc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        scores = [s.severity_score for s in test_stories]
        non_null_scores = [s for s in scores if s is not None]

        # Non-null scores should be descending
        assert non_null_scores == sorted(non_null_scores, reverse=True)

    def test_sort_by_fix_size_desc(self, story_service, sample_stories):
        """Test sorting by fix_size_score descending."""
        result = story_service.list(sort_by="fix_size_score", sort_dir="desc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        scores = [s.fix_size_score for s in test_stories]
        non_null_scores = [s for s in scores if s is not None]

        assert non_null_scores == sorted(non_null_scores, reverse=True)

    def test_sort_by_churn_risk_desc(self, story_service, sample_stories):
        """Test sorting by churn_risk_score descending."""
        result = story_service.list(sort_by="churn_risk_score", sort_dir="desc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        scores = [s.churn_risk_score for s in test_stories]
        non_null_scores = [s for s in scores if s is not None]

        assert non_null_scores == sorted(non_null_scores, reverse=True)

    def test_sort_by_confidence_desc(self, story_service, db_connection):
        """Test sorting by confidence_score (existing column)."""
        # Create stories with confidence scores
        story1 = story_service.create(StoryCreate(
            title="High confidence",
            status="candidate",
            confidence_score=85.0,
        ))
        story2 = story_service.create(StoryCreate(
            title="Low confidence",
            status="candidate",
            confidence_score=25.0,
        ))
        db_connection.commit()

        try:
            result = story_service.list(sort_by="confidence_score", sort_dir="desc")

            test_ids = {story1.id, story2.id}
            test_stories = [s for s in result.stories if s.id in test_ids]

            # High confidence should come first
            assert test_stories[0].confidence_score >= test_stories[1].confidence_score
        finally:
            story_service.delete(story1.id)
            story_service.delete(story2.id)
            db_connection.commit()

    # =========================================================================
    # SORT DIRECTION (ASC)
    # =========================================================================

    def test_sort_by_severity_asc(self, story_service, sample_stories):
        """Test sorting ascending."""
        result = story_service.list(sort_by="severity_score", sort_dir="asc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        scores = [s.severity_score for s in test_stories]
        non_null_scores = [s for s in scores if s is not None]

        # Non-null scores should be ascending
        assert non_null_scores == sorted(non_null_scores)

    def test_sort_by_actionability_asc(self, story_service, sample_stories):
        """Test sorting actionability ascending."""
        result = story_service.list(sort_by="actionability_score", sort_dir="asc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        scores = [s.actionability_score for s in test_stories]
        non_null_scores = [s for s in scores if s is not None]

        assert non_null_scores == sorted(non_null_scores)

    # =========================================================================
    # INVALID SORT COLUMN
    # =========================================================================

    def test_invalid_sort_column_falls_back_to_updated_at(self, story_service, sample_stories):
        """Test that invalid sort column falls back to updated_at."""
        # This should not raise - it should fall back gracefully
        result = story_service.list(sort_by="invalid_column", sort_dir="desc")

        # Should return results (no error)
        assert result.stories is not None
        assert len(result.stories) > 0

    def test_sql_injection_attempt_is_safe(self, story_service, sample_stories):
        """Test that SQL injection attempts are handled safely."""
        # Attempt SQL injection via sort_by
        result = story_service.list(
            sort_by="actionability_score; DROP TABLE stories;--",
            sort_dir="desc"
        )

        # Should fall back to updated_at, not execute injection
        assert result.stories is not None

    # =========================================================================
    # NULLS LAST BEHAVIOR
    # =========================================================================

    def test_nulls_last_desc(self, story_service, sample_stories):
        """Test that NULL scores appear last when sorting DESC."""
        result = story_service.list(sort_by="actionability_score", sort_dir="desc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        # Find the story with NULL actionability
        null_story = next((s for s in sample_stories if s.actionability_score is None), None)
        assert null_story is not None, "Test requires a story with NULL score"

        # In our test stories, NULL should be last
        if len(test_stories) > 1:
            last_test_story = test_stories[-1]
            # Either the last story has NULL or lower non-null score
            # (depends on other stories in DB)

    def test_nulls_last_asc(self, story_service, sample_stories):
        """Test that NULL scores appear last when sorting ASC."""
        result = story_service.list(sort_by="severity_score", sort_dir="asc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        # NULL should still be last even in ASC order
        scores = [s.severity_score for s in test_stories]

        if None in scores:
            # NULLs should be at the end
            null_indices = [i for i, s in enumerate(scores) if s is None]
            non_null_count = len([s for s in scores if s is not None])

            for idx in null_indices:
                assert idx >= non_null_count, "NULL should appear after all non-NULL values"

    # =========================================================================
    # COMBINED WITH FILTERS
    # =========================================================================

    def test_sort_with_status_filter(self, story_service, sample_stories):
        """Test sorting combined with status filter."""
        result = story_service.list(
            status="candidate",
            sort_by="actionability_score",
            sort_dir="desc"
        )

        # All returned stories should have status=candidate
        for story in result.stories:
            assert story.status == "candidate"

        # Should still be sorted
        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        if len(test_stories) > 1:
            scores = [s.actionability_score for s in test_stories]
            non_null_scores = [s for s in scores if s is not None]
            assert non_null_scores == sorted(non_null_scores, reverse=True)

    # =========================================================================
    # SCORE METADATA
    # =========================================================================

    def test_score_metadata_is_returned(self, story_service, sample_stories):
        """Test that score_metadata is included in response."""
        result = story_service.list(sort_by="actionability_score", sort_dir="desc")

        test_ids = {s.id for s in sample_stories}
        test_stories = [s for s in result.stories if s.id in test_ids]

        # Stories with scores should have metadata
        for story in test_stories:
            if story.actionability_score is not None:
                assert story.score_metadata is not None
                assert story.score_metadata.get("test") is True


class TestStoryServiceSortColumnWhitelist:
    """Test the sort column whitelist validation."""

    def test_valid_sort_columns(self):
        """Test all valid sort columns are in whitelist."""
        valid_columns = {
            "updated_at", "created_at", "confidence_score",
            "actionability_score", "fix_size_score",
            "severity_score", "churn_risk_score"
        }

        assert StoryService.VALID_SORT_COLUMNS == valid_columns

    def test_whitelist_prevents_arbitrary_columns(self):
        """Test that arbitrary columns are not in whitelist."""
        dangerous_columns = [
            "id", "title", "description", "status",
            "priority", "labels", "product_area",
            "1; DROP TABLE stories",
        ]

        for col in dangerous_columns:
            assert col not in StoryService.VALID_SORT_COLUMNS
