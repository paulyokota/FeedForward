"""
Tests for embedding model configuration alignment (Issue #181)

These tests verify that both UnifiedSearchService and EmbeddingPipeline
read and apply the embedding model configuration from the same config file.

Run with: python -m pytest tests/test_embedding_config_alignment.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import sys

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@pytest.fixture(autouse=True)
def mock_openai_client():
    """Mock OpenAI client to avoid API key requirement."""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1] * 1536)]
    mock_client.embeddings.create.return_value = mock_response

    with patch('research.unified_search.OpenAI', return_value=mock_client):
        with patch('research.embedding_pipeline.OpenAI', return_value=mock_client):
            yield mock_client


class TestEmbeddingModelConfiguration:
    """Tests for embedding model configuration alignment between services.

    Issue #181: Search relevance was weak because UnifiedSearchService used
    a different embedding model than EmbeddingPipeline. Both must use the
    same model for vector similarity to work correctly.
    """

    @pytest.fixture
    def config_path(self, tmp_path):
        """Create a temporary config file."""
        config_content = """
embedding:
  model: "text-embedding-3-large"
  dimensions: 1536
  batch_size: 100

search:
  default_limit: 20
  max_limit: 100
  default_min_similarity: 0.5
  server_min_similarity: 0.3

context_augmentation:
  max_results: 3
  max_tokens: 500

evidence_suggestion:
  min_similarity: 0.7
  max_suggestions: 5
"""
        config_file = tmp_path / "research_search.yaml"
        config_file.write_text(config_content)
        return config_file

    def test_unified_search_service_loads_embedding_model_from_config(self, config_path):
        """Test UnifiedSearchService loads embedding model from config."""
        from research.unified_search import UnifiedSearchService

        service = UnifiedSearchService(config_path=config_path)

        assert service._embedding_model == "text-embedding-3-large"
        assert service._embedding_dimensions == 1536

    def test_embedding_pipeline_loads_embedding_model_from_config(self, config_path):
        """Test EmbeddingPipeline loads embedding model from config."""
        from research.embedding_pipeline import EmbeddingPipeline

        pipeline = EmbeddingPipeline(config_path=config_path)

        assert pipeline._embedding_model == "text-embedding-3-large"
        assert pipeline._embedding_dimensions == 1536
        assert pipeline._batch_size == 100

    def test_both_services_use_same_model_from_shared_config(self, config_path):
        """Test both services load the same model from shared config."""
        from research.unified_search import UnifiedSearchService
        from research.embedding_pipeline import EmbeddingPipeline

        service = UnifiedSearchService(config_path=config_path)
        pipeline = EmbeddingPipeline(config_path=config_path)

        # CRITICAL: Both must use the same model for embeddings to be compatible
        assert service._embedding_model == pipeline._embedding_model
        assert service._embedding_dimensions == pipeline._embedding_dimensions

    def test_explicit_model_override_takes_precedence(self, config_path):
        """Test explicit model parameter overrides config."""
        from research.unified_search import UnifiedSearchService
        from research.embedding_pipeline import EmbeddingPipeline

        # Explicit override should win
        service = UnifiedSearchService(
            embedding_model="text-embedding-3-small",
            config_path=config_path,
        )
        pipeline = EmbeddingPipeline(
            embedding_model="text-embedding-3-small",
            config_path=config_path,
        )

        assert service._embedding_model == "text-embedding-3-small"
        assert pipeline._embedding_model == "text-embedding-3-small"

    def test_default_model_used_when_config_missing(self, tmp_path):
        """Test default model is used when config file is missing."""
        from research.unified_search import UnifiedSearchService
        from research.embedding_pipeline import EmbeddingPipeline

        missing_config = tmp_path / "nonexistent.yaml"

        service = UnifiedSearchService(config_path=missing_config)
        pipeline = EmbeddingPipeline(config_path=missing_config)

        # Both should use the same default
        assert service._embedding_model == "text-embedding-3-small"
        assert pipeline._embedding_model == "text-embedding-3-small"

    def test_stats_exposes_embedding_model(self, config_path):
        """Test get_stats includes embedding model for alignment verification."""
        from research.unified_search import UnifiedSearchService

        service = UnifiedSearchService(config_path=config_path)

        with patch('src.db.connection.get_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            mock_cursor.fetchone.side_effect = [
                (0,),  # total count
                (None,),  # last_updated
            ]
            mock_cursor.fetchall.return_value = []  # by_type

            stats = service.get_stats()

        assert stats.embedding_model == "text-embedding-3-large"
        assert stats.embedding_dimensions == 1536

    def test_production_config_uses_large_model(self):
        """Test the actual production config specifies text-embedding-3-large."""
        import yaml

        config_path = PROJECT_ROOT / "config" / "research_search.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)

            assert "embedding" in config
            assert config["embedding"]["model"] == "text-embedding-3-large"
            assert config["embedding"]["dimensions"] == 1536


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
