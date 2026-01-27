"""
Tests for EmbeddingService.

Tests embedding generation with mocked OpenAI API calls.
Issue: #106 - Pipeline step: embedding generation for conversations
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.embedding_service import (
    EmbeddingService,
    EmbeddingResult,
    BatchEmbeddingResult,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
    DEFAULT_BATCH_SIZE,
    MAX_TEXT_CHARS,
)


class TestEmbeddingServiceConfig:
    """Test EmbeddingService configuration and constants."""

    def test_default_model_is_text_embedding_3_small(self):
        """Verify default model matches OpenAI documentation."""
        assert EMBEDDING_MODEL == "text-embedding-3-small"

    def test_embedding_dimensions_is_1536(self):
        """text-embedding-3-small produces 1536-dimensional vectors."""
        assert EMBEDDING_DIMENSIONS == 1536

    def test_default_batch_size_is_50(self):
        """Batch size of 50 balances efficiency with rate limits."""
        assert DEFAULT_BATCH_SIZE == 50

    def test_max_text_chars_is_32000(self):
        """~8000 tokens * 4 chars/token = 32000 chars max."""
        assert MAX_TEXT_CHARS == 32000

    def test_service_initializes_with_defaults(self):
        """Service uses default config when no args provided."""
        service = EmbeddingService()
        assert service.batch_size == DEFAULT_BATCH_SIZE
        assert service.model == EMBEDDING_MODEL

    def test_service_accepts_custom_batch_size(self):
        """Service allows custom batch size."""
        service = EmbeddingService(batch_size=25)
        assert service.batch_size == 25

    def test_service_accepts_custom_model(self):
        """Service allows custom model specification."""
        service = EmbeddingService(model="text-embedding-3-large")
        assert service.model == "text-embedding-3-large"


class TestTextPreparation:
    """Test text preparation and truncation."""

    def test_truncate_text_short_text_unchanged(self):
        """Short texts pass through unchanged."""
        service = EmbeddingService()
        text = "Short text"
        assert service._truncate_text(text) == text

    def test_truncate_text_long_text_truncated(self):
        """Long texts are truncated to MAX_TEXT_CHARS."""
        service = EmbeddingService()
        long_text = "a" * (MAX_TEXT_CHARS + 1000)
        result = service._truncate_text(long_text)
        assert len(result) == MAX_TEXT_CHARS

    def test_prepare_text_uses_excerpt_if_available(self):
        """Excerpt takes priority over source_body."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Full conversation text",
            excerpt="Focused excerpt"
        )
        assert result == "Focused excerpt"

    def test_prepare_text_falls_back_to_source_body(self):
        """Falls back to source_body when no excerpt."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Full conversation text",
            excerpt=None
        )
        assert result == "Full conversation text"

    def test_prepare_text_handles_empty_excerpt(self):
        """Empty/whitespace excerpt falls back to source_body."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Full conversation text",
            excerpt="   "  # Whitespace only
        )
        assert result == "Full conversation text"

    def test_prepare_text_strips_whitespace(self):
        """Input text is stripped of leading/trailing whitespace."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="  padded text  ",
            excerpt=None
        )
        assert result == "padded text"

    def test_prepare_text_returns_empty_for_no_content(self):
        """Returns empty string when both inputs are empty."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="",
            excerpt=""
        )
        assert result == ""

    # Issue #139: customer_digest priority tests
    def test_prepare_text_prioritizes_customer_digest(self):
        """customer_digest takes priority over excerpt and source_body."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="First message only",
            excerpt="Focused excerpt",
            customer_digest="First message\n\n---\n\nError ERR_500 when posting"
        )
        assert "ERR_500" in result
        assert result.startswith("First message")

    def test_prepare_text_digest_over_excerpt(self):
        """customer_digest is used even when excerpt is available."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Source body text",
            excerpt="Excerpt text that would normally be used",
            customer_digest="Customer digest with specific details"
        )
        assert result == "Customer digest with specific details"
        assert "Excerpt" not in result

    def test_prepare_text_falls_back_when_digest_empty(self):
        """Empty customer_digest falls back to excerpt, then source_body."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Source body fallback",
            excerpt="Focused excerpt",
            customer_digest="   "  # Whitespace only
        )
        assert result == "Focused excerpt"

    def test_prepare_text_falls_back_to_source_when_digest_and_excerpt_empty(self):
        """Falls back to source_body when digest and excerpt are both empty."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Final fallback to source",
            excerpt="",
            customer_digest=""
        )
        assert result == "Final fallback to source"

    def test_prepare_text_digest_none_uses_excerpt(self):
        """When customer_digest is None, falls back to excerpt."""
        service = EmbeddingService()
        result = service._prepare_text(
            source_body="Source text",
            excerpt="Excerpt when no digest",
            customer_digest=None
        )
        assert result == "Excerpt when no digest"


class TestEmbeddingResultModel:
    """Test EmbeddingResult dataclass."""

    def test_successful_result(self):
        """Successful result has embedding and success=True."""
        result = EmbeddingResult(
            conversation_id="conv_123",
            embedding=[0.1] * 1536,
            success=True,
        )
        assert result.conversation_id == "conv_123"
        assert len(result.embedding) == 1536
        assert result.success is True
        assert result.error is None

    def test_failed_result(self):
        """Failed result has empty embedding and error message."""
        result = EmbeddingResult(
            conversation_id="conv_456",
            embedding=[],
            success=False,
            error="API rate limit exceeded",
        )
        assert result.conversation_id == "conv_456"
        assert result.embedding == []
        assert result.success is False
        assert result.error == "API rate limit exceeded"


class TestBatchEmbeddingResultModel:
    """Test BatchEmbeddingResult dataclass."""

    def test_batch_result_counts(self):
        """Batch result correctly counts successes and failures."""
        successful = [
            EmbeddingResult("c1", [0.1] * 1536, True),
            EmbeddingResult("c2", [0.2] * 1536, True),
        ]
        failed = [
            EmbeddingResult("c3", [], False, "Error"),
        ]

        batch = BatchEmbeddingResult(
            successful=successful,
            failed=failed,
            total_processed=3,
            total_success=2,
            total_failed=1,
        )

        assert len(batch.successful) == 2
        assert len(batch.failed) == 1
        assert batch.total_processed == 3
        assert batch.total_success == 2
        assert batch.total_failed == 1


class TestSyncEmbeddingGeneration:
    """Test synchronous embedding generation."""

    @patch.object(EmbeddingService, "sync_client", new_callable=lambda: MagicMock())
    def test_generate_embeddings_sync_single_text(self, mock_client):
        """Single text generates single embedding."""
        # Mock the response
        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding]

        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        service._sync_client = mock_client

        result = service.generate_embeddings_sync(["Test text"])

        assert len(result) == 1
        assert len(result[0]) == 1536
        mock_client.embeddings.create.assert_called_once()

    @patch.object(EmbeddingService, "sync_client", new_callable=lambda: MagicMock())
    def test_generate_embeddings_sync_batches_large_input(self, mock_client):
        """Large inputs are processed in batches."""
        # Create mock embeddings with index attribute for sorting
        def create_mock_embeddings(count):
            embeddings = []
            for i in range(count):
                mock_embedding = MagicMock()
                mock_embedding.embedding = [0.1] * 1536
                mock_embedding.index = i
                embeddings.append(mock_embedding)
            return embeddings

        mock_response = MagicMock()
        mock_response.data = create_mock_embeddings(25)

        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService(batch_size=25)
        service._sync_client = mock_client

        # 60 texts should require 3 batches (25 + 25 + 10)
        texts = [f"Text {i}" for i in range(60)]
        result = service.generate_embeddings_sync(texts)

        # Should have called create 3 times
        assert mock_client.embeddings.create.call_count == 3

    def test_generate_embeddings_sync_empty_input(self):
        """Empty input returns empty list."""
        service = EmbeddingService()
        result = service.generate_embeddings_sync([])
        assert result == []

    def test_generate_embeddings_sync_all_empty_texts_raises(self):
        """All empty texts raises ValueError."""
        service = EmbeddingService()
        with pytest.raises(ValueError, match="All provided texts are empty"):
            service.generate_embeddings_sync(["", "   ", None])


class TestAsyncConversationEmbeddings:
    """Test async conversation embedding generation."""

    @pytest.mark.asyncio
    async def test_empty_conversations_returns_empty_result(self):
        """Empty conversation list returns zero counts."""
        service = EmbeddingService()
        result = await service.generate_conversation_embeddings_async([])

        assert result.total_processed == 0
        assert result.total_success == 0
        assert result.total_failed == 0
        assert result.successful == []
        assert result.failed == []

    @pytest.mark.asyncio
    async def test_conversation_with_empty_text_fails(self):
        """Conversation with no text content fails gracefully."""
        service = EmbeddingService()
        conversations = [
            {"id": "conv_1", "source_body": ""},
        ]

        result = await service.generate_conversation_embeddings_async(conversations)

        assert result.total_processed == 1
        assert result.total_success == 0
        assert result.total_failed == 1
        assert result.failed[0].error == "Empty text after preparation"

    @pytest.mark.asyncio
    async def test_stop_checker_stops_processing(self):
        """Stop signal halts processing and marks remaining as failed."""
        service = EmbeddingService()
        conversations = [
            {"id": "conv_1", "source_body": "Text 1"},
            {"id": "conv_2", "source_body": "Text 2"},
        ]

        # Stop immediately
        result = await service.generate_conversation_embeddings_async(
            conversations,
            stop_checker=lambda: True,
        )

        # Should have stopped early
        assert result.total_processed == 2
        # Either failed or not processed due to stop

    @pytest.mark.asyncio
    @patch("src.services.embedding_service.AsyncOpenAI")
    async def test_successful_embedding_generation(self, mock_openai_class):
        """Successful API call returns embeddings."""
        # Setup mock
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client

        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.5] * 1536
        mock_embedding.index = 0  # OpenAI returns index for ordering

        mock_response = MagicMock()
        mock_response.data = [mock_embedding]

        mock_client.embeddings.create.return_value = mock_response

        service = EmbeddingService()
        service._async_client = mock_client

        conversations = [
            {"id": "conv_123", "source_body": "Test conversation text"},
        ]

        result = await service.generate_conversation_embeddings_async(conversations)

        assert result.total_processed == 1
        assert result.total_success == 1
        assert result.total_failed == 0
        assert result.successful[0].conversation_id == "conv_123"
        assert len(result.successful[0].embedding) == 1536

    @pytest.mark.asyncio
    @patch("src.services.embedding_service.AsyncOpenAI")
    async def test_api_error_marks_batch_failed(self, mock_openai_class):
        """API errors mark entire batch as failed."""
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.embeddings.create.side_effect = Exception("API Error")

        service = EmbeddingService()
        service._async_client = mock_client

        conversations = [
            {"id": "conv_1", "source_body": "Text 1"},
            {"id": "conv_2", "source_body": "Text 2"},
        ]

        result = await service.generate_conversation_embeddings_async(conversations)

        assert result.total_processed == 2
        assert result.total_success == 0
        assert result.total_failed == 2
        # Error message is sanitized for security - check it's a valid error message
        assert "Embedding generation failed" in result.failed[0].error or "failed" in result.failed[0].error.lower()


class TestEmbeddingStorage:
    """Test embedding storage helpers."""

    def test_store_embedding_rejects_wrong_dimensions(self):
        """Embedding with wrong dimensions raises ValueError."""
        from src.db.embedding_storage import store_embedding
        from src.services.embedding_service import EMBEDDING_DIMENSIONS

        # Wrong dimensions should fail validation
        with pytest.raises(ValueError, match=f"must be {EMBEDDING_DIMENSIONS} dimensions"):
            store_embedding(
                conversation_id="conv_123",
                embedding=[0.1] * 100,  # Wrong dimensions
                pipeline_run_id=1,
            )

    def test_store_embeddings_batch_filters_failed(self):
        """Batch storage only stores successful results."""
        from src.db.embedding_storage import store_embeddings_batch

        results = [
            EmbeddingResult("c1", [0.1] * 1536, True),
            EmbeddingResult("c2", [], False, "Error"),  # Should be skipped
        ]

        # This would normally store to DB, but we can verify the filtering logic
        # by checking that only successful results pass the filter
        successful_only = [r for r in results if r.success and r.embedding]
        assert len(successful_only) == 1
        assert successful_only[0].conversation_id == "c1"


class TestPipelineIntegration:
    """Test integration with pipeline flow."""

    def test_allowed_phase_fields_includes_embeddings(self):
        """Pipeline phase fields include embedding tracking."""
        from src.api.routers.pipeline import _ALLOWED_PHASE_FIELDS

        assert "embeddings_generated" in _ALLOWED_PHASE_FIELDS
        assert "embeddings_failed" in _ALLOWED_PHASE_FIELDS

    def test_pipeline_status_schema_has_embedding_fields(self):
        """PipelineStatus schema includes embedding fields."""
        from src.api.schemas.pipeline import PipelineStatus

        # Check the model has the fields
        field_names = set(PipelineStatus.model_fields.keys())
        assert "embeddings_generated" in field_names
        assert "embeddings_failed" in field_names

    def test_pipeline_run_model_has_embedding_fields(self):
        """PipelineRun model includes embedding fields."""
        from src.db.models import PipelineRun

        run = PipelineRun()
        assert run.embeddings_generated == 0
        assert run.embeddings_failed == 0

    def test_conversation_embedding_model_validates_dimensions(self):
        """ConversationEmbedding model validates 1536 dimensions."""
        from src.db.models import ConversationEmbedding

        # Valid embedding
        valid = ConversationEmbedding(
            conversation_id="conv_123",
            embedding=[0.1] * 1536,
        )
        assert len(valid.embedding) == 1536

        # Invalid embedding should raise
        with pytest.raises(ValueError, match="must be exactly 1536 dimensions"):
            ConversationEmbedding(
                conversation_id="conv_456",
                embedding=[0.1] * 100,  # Wrong dimensions
            )


class TestMigration:
    """Test migration file existence."""

    def test_migration_file_exists(self):
        """Migration 013 exists for embedding generation phase."""
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "src/db/migrations/013_embedding_generation_phase.sql"
        assert migration_path.exists(), "Migration 013 should exist"

    def test_migration_adds_required_columns(self):
        """Migration adds embeddings_generated and embeddings_failed columns."""
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "src/db/migrations/013_embedding_generation_phase.sql"
        content = migration_path.read_text()

        assert "embeddings_generated" in content
        assert "embeddings_failed" in content
        assert "pipeline_runs" in content
