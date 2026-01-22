"""
Tests for conversation_embeddings and conversation_facet data models (#105).

Validates:
- Pydantic model structure and validation
- Type constraints (ActionType, Direction)
- Field validators (embedding dimension, word count)
- Migration file structure
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
    ConversationFacet,
    Direction,
)


# =============================================================================
# ConversationEmbedding Model Tests
# =============================================================================


class TestConversationEmbeddingModel:
    """Tests for ConversationEmbedding Pydantic model."""

    def test_valid_embedding_1536_dimensions(self):
        """Embedding with correct 1536 dimensions is valid."""
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
        embedding = ConversationEmbedding(
            id=uuid4(),
            conversation_id="conv_456",
            pipeline_run_id=42,  # INTEGER, not UUID
            embedding=[0.5] * 1536,
            model_version="text-embedding-3-large",
            created_at=datetime(2026, 1, 22, 12, 0, 0),
        )
        assert embedding.pipeline_run_id == 42
        assert embedding.model_version == "text-embedding-3-large"

    def test_embedding_wrong_dimension_rejected(self):
        """Embedding with wrong dimensions raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationEmbedding(
                conversation_id="conv_bad",
                embedding=[0.1] * 512,  # Wrong dimension
            )
        assert "1536 dimensions" in str(exc_info.value)

    def test_empty_embedding_rejected(self):
        """Empty embedding list raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationEmbedding(
                conversation_id="conv_empty",
                embedding=[],
            )
        assert "1536 dimensions" in str(exc_info.value)

    def test_created_at_default(self):
        """created_at defaults to current time."""
        before = datetime.utcnow()
        embedding = ConversationEmbedding(
            conversation_id="conv_time",
            embedding=[0.1] * 1536,
        )
        after = datetime.utcnow()
        assert before <= embedding.created_at <= after

    def test_pipeline_run_id_is_int(self):
        """pipeline_run_id is Optional[int], not UUID."""
        embedding = ConversationEmbedding(
            conversation_id="conv_int",
            embedding=[0.1] * 1536,
            pipeline_run_id=123,
        )
        assert embedding.pipeline_run_id == 123
        assert isinstance(embedding.pipeline_run_id, int)


# =============================================================================
# ConversationFacet Model Tests
# =============================================================================


class TestConversationFacetModel:
    """Tests for ConversationFacet Pydantic model."""

    def test_minimal_valid_facet(self):
        """Facet with only required fields."""
        facet = ConversationFacet(conversation_id="conv_123")
        assert facet.conversation_id == "conv_123"
        assert facet.action_type == "unknown"
        assert facet.direction == "neutral"
        assert facet.model_version == "gpt-4o-mini"

    def test_full_facet_with_all_fields(self):
        """Facet with all optional fields populated."""
        facet = ConversationFacet(
            id=uuid4(),
            conversation_id="conv_456",
            pipeline_run_id=42,  # INTEGER, not UUID
            action_type="bug_report",
            direction="deficit",
            symptom="Items not appearing",
            user_goal="See all items",
            model_version="gpt-4o",
            extraction_confidence="high",
        )
        assert facet.pipeline_run_id == 42
        assert facet.action_type == "bug_report"
        assert facet.direction == "deficit"
        assert facet.extraction_confidence == "high"

    def test_all_valid_action_types(self):
        """All ActionType literals are accepted."""
        valid_action_types = [
            "inquiry", "complaint", "bug_report", "how_to_question",
            "feature_request", "account_change", "delete_request", "unknown"
        ]
        for action_type in valid_action_types:
            facet = ConversationFacet(
                conversation_id=f"conv_{action_type}",
                action_type=action_type,
            )
            assert facet.action_type == action_type

    def test_all_valid_directions(self):
        """All Direction literals are accepted."""
        valid_directions = [
            "excess", "deficit", "creation", "deletion",
            "modification", "performance", "neutral"
        ]
        for direction in valid_directions:
            facet = ConversationFacet(
                conversation_id=f"conv_{direction}",
                direction=direction,
            )
            assert facet.direction == direction

    def test_invalid_action_type_rejected(self):
        """Invalid action_type raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacet(
                conversation_id="conv_bad",
                action_type="invalid_action",  # type: ignore
            )
        assert "action_type" in str(exc_info.value)

    def test_invalid_direction_rejected(self):
        """Invalid direction raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacet(
                conversation_id="conv_bad",
                direction="invalid_dir",  # type: ignore
            )
        assert "direction" in str(exc_info.value)

    def test_symptom_word_count_validation(self):
        """symptom with more than 10 words is rejected."""
        # Exactly 10 words - should pass
        facet = ConversationFacet(
            conversation_id="conv_ok",
            symptom="one two three four five six seven eight nine ten",
        )
        assert facet.symptom is not None

        # 11 words - should fail
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacet(
                conversation_id="conv_bad",
                symptom="one two three four five six seven eight nine ten eleven",
            )
        assert "10 words or less" in str(exc_info.value)

    def test_user_goal_word_count_validation(self):
        """user_goal with more than 10 words is rejected."""
        # Exactly 10 words - should pass
        facet = ConversationFacet(
            conversation_id="conv_ok",
            user_goal="one two three four five six seven eight nine ten",
        )
        assert facet.user_goal is not None

        # 11 words - should fail
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacet(
                conversation_id="conv_bad",
                user_goal="one two three four five six seven eight nine ten eleven",
            )
        assert "10 words or less" in str(exc_info.value)

    def test_symptom_max_length_validation(self):
        """symptom exceeding 200 chars is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ConversationFacet(
                conversation_id="conv_long",
                symptom="a" * 201,  # 201 chars
            )
        assert "symptom" in str(exc_info.value).lower() or "max_length" in str(exc_info.value).lower()

    def test_pipeline_run_id_is_int(self):
        """pipeline_run_id is Optional[int], not UUID."""
        facet = ConversationFacet(
            conversation_id="conv_int",
            pipeline_run_id=456,
        )
        assert facet.pipeline_run_id == 456
        assert isinstance(facet.pipeline_run_id, int)


# =============================================================================
# Type Literal Tests
# =============================================================================


class TestTypeLiterals:
    """Tests for ActionType and Direction type literals."""

    def test_action_type_values(self):
        """ActionType has expected values per T-006."""
        expected = {
            "inquiry", "complaint", "bug_report", "how_to_question",
            "feature_request", "account_change", "delete_request", "unknown"
        }
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

    def test_creates_conversation_facet_table(self, migration_content):
        """Migration creates conversation_facet table (singular)."""
        assert "CREATE TABLE IF NOT EXISTS conversation_facet" in migration_content

    def test_pipeline_run_id_is_integer(self, migration_content):
        """pipeline_run_id uses INTEGER type to match pipeline_runs.id."""
        assert "pipeline_run_id INTEGER REFERENCES pipeline_runs(id)" in migration_content

    def test_has_foreign_key_constraint(self, migration_content):
        """Tables have explicit FK constraint with ON DELETE SET NULL."""
        assert "ON DELETE SET NULL" in migration_content

    def test_has_unique_constraint(self, migration_content):
        """Tables have UNIQUE constraint on (conversation_id, pipeline_run_id)."""
        assert "UNIQUE (conversation_id, pipeline_run_id)" in migration_content

    def test_embedding_dimension_is_1536(self, migration_content):
        """Embedding uses 1536 dimensions (text-embedding-3-small)."""
        assert "vector(1536)" in migration_content

    def test_embeddings_has_hnsw_index(self, migration_content):
        """conversation_embeddings has HNSW index for vector search."""
        assert "idx_conv_embeddings_hnsw" in migration_content
        assert "hnsw" in migration_content.lower()
        assert "vector_cosine_ops" in migration_content


# =============================================================================
# Model Config Tests
# =============================================================================


class TestModelConfig:
    """Tests for Pydantic V2 model configuration."""

    def test_embedding_uses_config_dict(self):
        """ConversationEmbedding uses ConfigDict (Pydantic V2)."""
        assert hasattr(ConversationEmbedding, "model_config")
        assert ConversationEmbedding.model_config.get("from_attributes") is True

    def test_facet_uses_config_dict(self):
        """ConversationFacet uses ConfigDict (Pydantic V2)."""
        assert hasattr(ConversationFacet, "model_config")
        assert ConversationFacet.model_config.get("from_attributes") is True

    def test_embedding_id_is_uuid(self):
        """ConversationEmbedding.id is Optional[UUID]."""
        embedding = ConversationEmbedding(
            conversation_id="test",
            embedding=[0.1] * 1536,
        )
        assert embedding.id is None or isinstance(embedding.id, UUID)
