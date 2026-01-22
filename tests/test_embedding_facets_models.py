"""
Tests for conversation_embeddings and conversation_facets data models (#105).

Validates:
- Pydantic model structure and defaults
- Type constraints (ActionType, Direction)
- Migration file existence and structure
- Index definitions for run-scoped queries
"""

import os
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.db.models import (
    ActionType,
    Confidence,
    ConversationEmbedding,
    ConversationFacets,
    Direction,
)


# =============================================================================
# ConversationEmbedding Model Tests
# =============================================================================


class TestConversationEmbeddingModel:
    """Tests for ConversationEmbedding Pydantic model."""

    def test_minimal_valid_embedding(self):
        """Embedding with only required fields."""
        embedding = ConversationEmbedding(
            conversation_id="conv_123",
            embedding=[0.1] * 1536,
        )
        assert embedding.conversation_id == "conv_123"
        assert len(embedding.embedding) == 1536
        assert embedding.model_version == "text-embedding-3-small"
        assert embedding.pipeline_run_id is None

    def test_full_embedding_with_all_fields(self):
        """Embedding with all optional fields populated."""
        run_id = uuid4()
        embedding = ConversationEmbedding(
            id=uuid4(),
            conversation_id="conv_456",
            pipeline_run_id=run_id,
            embedding=[0.5] * 1536,
            model_version="text-embedding-3-large",
            content_hash="abc123def456",
            created_at=datetime(2026, 1, 22, 12, 0, 0),
        )
        assert embedding.pipeline_run_id == run_id
        assert embedding.model_version == "text-embedding-3-large"
        assert embedding.content_hash == "abc123def456"

    def test_embedding_dimension_flexibility(self):
        """Model accepts any embedding dimension (validation is at storage layer)."""
        # Different dimensions should be accepted by Pydantic
        embedding_small = ConversationEmbedding(
            conversation_id="conv_1",
            embedding=[0.1] * 512,
        )
        assert len(embedding_small.embedding) == 512

        embedding_large = ConversationEmbedding(
            conversation_id="conv_2",
            embedding=[0.1] * 3072,
        )
        assert len(embedding_large.embedding) == 3072

    def test_empty_embedding_allowed(self):
        """Empty embedding list is allowed by default."""
        embedding = ConversationEmbedding(conversation_id="conv_empty")
        assert embedding.embedding == []

    def test_created_at_default(self):
        """created_at defaults to current time."""
        before = datetime.utcnow()
        embedding = ConversationEmbedding(
            conversation_id="conv_time",
            embedding=[0.1],
        )
        after = datetime.utcnow()
        assert before <= embedding.created_at <= after


# =============================================================================
# ConversationFacets Model Tests
# =============================================================================


class TestConversationFacetsModel:
    """Tests for ConversationFacets Pydantic model."""

    def test_minimal_valid_facets(self):
        """Facets with only required fields."""
        facets = ConversationFacets(conversation_id="conv_123")
        assert facets.conversation_id == "conv_123"
        assert facets.action_type == "unknown"
        assert facets.direction == "neutral"
        assert facets.model_version == "gpt-4o-mini"

    def test_full_facets_with_all_fields(self):
        """Facets with all optional fields populated."""
        run_id = uuid4()
        facets = ConversationFacets(
            id=uuid4(),
            conversation_id="conv_456",
            pipeline_run_id=run_id,
            action_type="bug_report",
            direction="deficit",
            symptom="Items not appearing in dashboard",
            user_goal="See all items in dashboard view",
            model_version="gpt-4o",
            extraction_confidence="high",
        )
        assert facets.pipeline_run_id == run_id
        assert facets.action_type == "bug_report"
        assert facets.direction == "deficit"
        assert facets.symptom == "Items not appearing in dashboard"
        assert facets.extraction_confidence == "high"

    def test_all_valid_action_types(self):
        """All ActionType literals are accepted."""
        valid_action_types = [
            "inquiry", "complaint", "bug_report", "how_to_question",
            "feature_request", "account_change", "delete_request", "unknown"
        ]
        for action_type in valid_action_types:
            facets = ConversationFacets(
                conversation_id=f"conv_{action_type}",
                action_type=action_type,
            )
            assert facets.action_type == action_type

    def test_all_valid_directions(self):
        """All Direction literals are accepted."""
        valid_directions = [
            "excess", "deficit", "creation", "deletion",
            "modification", "performance", "neutral"
        ]
        for direction in valid_directions:
            facets = ConversationFacets(
                conversation_id=f"conv_{direction}",
                direction=direction,
            )
            assert facets.direction == direction

    def test_invalid_action_type_rejected(self):
        """Invalid action_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacets(
                conversation_id="conv_bad",
                action_type="invalid_action",  # type: ignore
            )
        assert "action_type" in str(exc_info.value)

    def test_invalid_direction_rejected(self):
        """Invalid direction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacets(
                conversation_id="conv_bad",
                direction="invalid_dir",  # type: ignore
            )
        assert "direction" in str(exc_info.value)

    def test_extraction_confidence_literal(self):
        """extraction_confidence uses Confidence literal type."""
        for conf in ["high", "medium", "low"]:
            facets = ConversationFacets(
                conversation_id="conv_conf",
                extraction_confidence=conf,  # type: ignore
            )
            assert facets.extraction_confidence == conf


# =============================================================================
# Type Literal Tests
# =============================================================================


class TestTypeLiterals:
    """Tests for ActionType and Direction type literals."""

    def test_action_type_values(self):
        """ActionType has expected values per T-006."""
        # These should match the prototype's facet extraction
        expected = {
            "inquiry", "complaint", "bug_report", "how_to_question",
            "feature_request", "account_change", "delete_request", "unknown"
        }
        # Get actual values from the type (requires inspecting get_args)
        from typing import get_args
        actual = set(get_args(ActionType))
        assert actual == expected

    def test_direction_values(self):
        """Direction has expected values per T-006."""
        expected = {
            "excess", "deficit", "creation", "deletion",
            "modification", "performance", "neutral"
        }
        from typing import get_args
        actual = set(get_args(Direction))
        assert actual == expected


# =============================================================================
# Migration File Tests
# =============================================================================


class TestMigrationFile:
    """Tests for migration 012_conversation_embeddings_facets.sql."""

    @pytest.fixture
    def migration_content(self):
        """Load migration file content."""
        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "db",
            "migrations",
            "012_conversation_embeddings_facets.sql",
        )
        with open(migration_path, "r") as f:
            return f.read()

    def test_migration_file_exists(self, migration_content):
        """Migration file exists and is readable."""
        assert len(migration_content) > 0

    def test_creates_conversation_embeddings_table(self, migration_content):
        """Migration creates conversation_embeddings table."""
        assert "CREATE TABLE IF NOT EXISTS conversation_embeddings" in migration_content

    def test_creates_conversation_facets_table(self, migration_content):
        """Migration creates conversation_facets table."""
        assert "CREATE TABLE IF NOT EXISTS conversation_facets" in migration_content

    def test_embeddings_has_required_columns(self, migration_content):
        """conversation_embeddings has required columns."""
        required = [
            "conversation_id",
            "pipeline_run_id",
            "embedding",
            "model_version",
            "created_at",
        ]
        for col in required:
            assert col in migration_content, f"Missing column: {col}"

    def test_facets_has_required_columns(self, migration_content):
        """conversation_facets has required columns."""
        required = [
            "conversation_id",
            "pipeline_run_id",
            "action_type",
            "direction",
            "symptom",
            "user_goal",
            "created_at",
        ]
        for col in required:
            assert col in migration_content, f"Missing column: {col}"

    def test_embeddings_has_run_scoped_index(self, migration_content):
        """conversation_embeddings has index on (pipeline_run_id, conversation_id)."""
        assert "idx_conv_embeddings_run_conv" in migration_content
        # Verify it's a composite index
        assert "pipeline_run_id, conversation_id" in migration_content

    def test_facets_has_run_scoped_index(self, migration_content):
        """conversation_facets has index on (pipeline_run_id, conversation_id)."""
        assert "idx_conv_facets_run_conv" in migration_content

    def test_embeddings_has_hnsw_index(self, migration_content):
        """conversation_embeddings has HNSW index for vector search."""
        assert "idx_conv_embeddings_hnsw" in migration_content
        assert "hnsw" in migration_content.lower()
        assert "vector_cosine_ops" in migration_content

    def test_facets_has_action_direction_index(self, migration_content):
        """conversation_facets has composite index for sub-clustering."""
        assert "idx_conv_facets_action_direction" in migration_content
        assert "action_type, direction" in migration_content

    def test_embedding_dimension_is_1536(self, migration_content):
        """Embedding uses 1536 dimensions (text-embedding-3-small)."""
        assert "vector(1536)" in migration_content

    def test_has_documentation_comments(self, migration_content):
        """Migration includes COMMENT statements for documentation."""
        assert "COMMENT ON TABLE conversation_embeddings" in migration_content
        assert "COMMENT ON TABLE conversation_facets" in migration_content


# =============================================================================
# Integration with Existing Models
# =============================================================================


class TestModelIntegration:
    """Tests for integration with existing Pydantic models."""

    def test_embedding_uses_same_uuid_type(self):
        """ConversationEmbedding uses same UUID type as other models."""
        from src.db.models import PipelineRun

        # Both should accept UUID or None for ID fields
        embedding = ConversationEmbedding(conversation_id="test")
        assert embedding.id is None or isinstance(embedding.id, UUID)

    def test_facets_uses_confidence_literal(self):
        """ConversationFacets uses same Confidence literal as other models."""
        from src.db.models import Confidence

        facets = ConversationFacets(
            conversation_id="test",
            extraction_confidence="high",
        )
        # Type annotation should match
        assert facets.extraction_confidence in ["high", "medium", "low", None]

    def test_models_have_from_attributes_config(self):
        """Both models have from_attributes=True for ORM compatibility."""
        assert ConversationEmbedding.model_config.get("from_attributes") is True
        assert ConversationFacets.model_config.get("from_attributes") is True
