"""
Research Module Tests

Tests for search adapters, UnifiedSearchService, and EmbeddingPipeline.
Run with: pytest tests/test_research.py -v
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from research.models import (
    SearchableContent,
    UnifiedSearchResult,
    UnifiedSearchRequest,
    SimilarContentRequest,
    SuggestedEvidence,
    EmbeddingStats,
    ReindexRequest,
    ReindexResponse,
)
from research.adapters.base import SearchSourceAdapter
from research.adapters.coda_adapter import CodaSearchAdapter
from research.adapters.intercom_adapter import IntercomSearchAdapter


# -----------------------------------------------------------------------------
# Model Tests
# -----------------------------------------------------------------------------

class TestSearchableContent:
    """Tests for SearchableContent model."""

    def test_create_valid_content(self):
        """Test creating valid SearchableContent."""
        content = SearchableContent(
            source_type="coda_page",
            source_id="page_123",
            title="Test Page",
            content="Some test content",
            url="https://coda.io/d/doc123/_/page_123",
            metadata={"participant": "user@example.com"},
        )

        assert content.source_type == "coda_page"
        assert content.source_id == "page_123"
        assert content.title == "Test Page"
        assert content.content == "Some test content"
        assert content.metadata["participant"] == "user@example.com"

    def test_default_metadata(self):
        """Test that metadata defaults to empty dict."""
        content = SearchableContent(
            source_type="intercom",
            source_id="conv_456",
            title="Test Conversation",
            content="User message",
            url="https://intercom.com/conv_456",
        )

        assert content.metadata == {}


class TestUnifiedSearchResult:
    """Tests for UnifiedSearchResult model."""

    def test_create_valid_result(self):
        """Test creating valid search result."""
        result = UnifiedSearchResult(
            id=1,
            source_type="coda_theme",
            source_id="theme_123",
            title="Pin Spacing Issues",
            snippet="Users report confusion about pin spacing...",
            similarity=0.85,
            url="https://coda.io/d/doc#theme_123",
            metadata={"product_area": "scheduling"},
        )

        assert result.similarity == 0.85
        assert result.source_type == "coda_theme"

    def test_similarity_bounds(self):
        """Test similarity must be between 0 and 1."""
        with pytest.raises(ValueError):
            UnifiedSearchResult(
                id=1,
                source_type="coda_page",
                source_id="page_1",
                title="Test",
                snippet="Test",
                similarity=1.5,  # Invalid
                url="https://example.com",
            )


class TestUnifiedSearchRequest:
    """Tests for UnifiedSearchRequest model."""

    def test_query_max_length(self):
        """Test query max length validation."""
        long_query = "a" * 501
        with pytest.raises(ValueError):
            UnifiedSearchRequest(query=long_query)

    def test_min_similarity_server_enforced(self):
        """Test minimum similarity is server-enforced at 0.3."""
        with pytest.raises(ValueError):
            UnifiedSearchRequest(query="test", min_similarity=0.2)

    def test_valid_request(self):
        """Test valid request creation."""
        request = UnifiedSearchRequest(
            query="scheduling issues",
            limit=50,
            source_types=["coda_page", "coda_theme"],
            min_similarity=0.6,
        )

        assert request.query == "scheduling issues"
        assert request.limit == 50


# -----------------------------------------------------------------------------
# Adapter Tests
# -----------------------------------------------------------------------------

class TestSearchSourceAdapterBase:
    """Tests for SearchSourceAdapter base class methods."""

    def test_compute_content_hash(self):
        """Test content hash computation."""
        hash1 = SearchSourceAdapter.compute_content_hash("test content")
        hash2 = SearchSourceAdapter.compute_content_hash("test content")
        hash3 = SearchSourceAdapter.compute_content_hash("different content")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA-256 hex length

    def test_create_snippet_short_content(self):
        """Test snippet for short content."""
        content = "Short text"
        snippet = SearchSourceAdapter.create_snippet(content)
        assert snippet == content

    def test_create_snippet_long_content(self):
        """Test snippet truncation for long content."""
        content = "This is a very long piece of content. " * 20
        snippet = SearchSourceAdapter.create_snippet(content, max_length=100)

        assert len(snippet) <= 103  # 100 + "..."

    def test_create_snippet_sentence_boundary(self):
        """Test snippet truncation at sentence boundary."""
        content = "First sentence. Second sentence. Third sentence is very long and continues."
        snippet = SearchSourceAdapter.create_snippet(content, max_length=50)

        # Should end at a sentence boundary
        assert snippet.endswith(".") or snippet.endswith("...")


class TestIntercomSearchAdapter:
    """Tests for IntercomSearchAdapter."""

    def test_source_type(self):
        """Test source type is 'intercom'."""
        adapter = IntercomSearchAdapter()
        assert adapter.get_source_type() == "intercom"

    def test_source_url(self):
        """Test URL generation."""
        adapter = IntercomSearchAdapter()
        url = adapter.get_source_url("12345")

        assert "12345" in url
        assert "intercom.com" in url

    def test_clean_html(self):
        """Test HTML cleaning."""
        html = "<p>Hello <b>world</b></p>"
        clean = IntercomSearchAdapter._clean_html(html)

        assert "<" not in clean
        assert ">" not in clean
        assert "Hello" in clean
        assert "world" in clean

    def test_extract_title_short(self):
        """Test title extraction from short content."""
        content = "Short message"
        title = IntercomSearchAdapter._extract_title(content)
        assert title == "Short message"

    def test_extract_title_long(self):
        """Test title extraction from long content."""
        content = "This is a very long message that should be truncated for the title display"
        title = IntercomSearchAdapter._extract_title(content, max_length=30)

        assert len(title) <= 33  # 30 + "..."


class TestCodaSearchAdapter:
    """Tests for CodaSearchAdapter."""

    def test_source_type_page(self):
        """Test page source type."""
        adapter = CodaSearchAdapter(source_type="coda_page")
        assert adapter.get_source_type() == "coda_page"

    def test_source_type_theme(self):
        """Test theme source type."""
        adapter = CodaSearchAdapter(source_type="coda_theme")
        assert adapter.get_source_type() == "coda_theme"

    def test_invalid_source_type(self):
        """Test invalid source type raises error."""
        with pytest.raises(ValueError):
            CodaSearchAdapter(source_type="invalid_type")

    @patch.dict("os.environ", {"CODA_DOC_ID": "test_doc_id"})
    def test_source_url_page(self):
        """Test page URL generation."""
        adapter = CodaSearchAdapter(source_type="coda_page")
        url = adapter.get_source_url("page_123")

        assert "coda.io" in url
        assert "page_123" in url

    @patch.dict("os.environ", {"CODA_DOC_ID": "test_doc_id"})
    def test_source_url_theme(self):
        """Test theme URL generation."""
        adapter = CodaSearchAdapter(source_type="coda_theme")
        url = adapter.get_source_url("theme_456")

        assert "coda.io" in url
        assert "theme_456" in url


# -----------------------------------------------------------------------------
# UnifiedSearchService Tests
# -----------------------------------------------------------------------------

class TestUnifiedSearchService:
    """Tests for UnifiedSearchService."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_client.embeddings.create.return_value = mock_response
        return mock_client

    def test_create_snippet_short(self):
        """Test snippet creation for short content."""
        from research.unified_search import UnifiedSearchService

        snippet = UnifiedSearchService._create_snippet("Short text")
        assert snippet == "Short text"

    def test_create_snippet_long(self):
        """Test snippet creation for long content."""
        from research.unified_search import UnifiedSearchService

        content = "This is a long text. " * 50
        snippet = UnifiedSearchService._create_snippet(content, max_length=100)

        assert len(snippet) <= 103  # Allow for "..."

    @patch.dict("os.environ", {"CODA_DOC_ID": "test_doc"})
    def test_build_url_coda_page(self):
        """Test URL building for Coda pages."""
        from research.unified_search import UnifiedSearchService

        url = UnifiedSearchService._build_url("coda_page", "page_123")
        assert "coda.io" in url
        assert "page_123" in url

    @patch.dict("os.environ", {"CODA_DOC_ID": "test_doc"})
    def test_build_url_intercom(self):
        """Test URL building for Intercom."""
        from research.unified_search import UnifiedSearchService

        url = UnifiedSearchService._build_url("intercom", "conv_456")
        assert "intercom.com" in url
        assert "conv_456" in url


# -----------------------------------------------------------------------------
# EmbeddingPipeline Tests
# -----------------------------------------------------------------------------

class TestEmbeddingPipeline:
    """Tests for EmbeddingPipeline."""

    def test_register_adapter(self):
        """Test adapter registration."""
        from research.embedding_pipeline import EmbeddingPipeline

        pipeline = EmbeddingPipeline()

        mock_adapter = Mock(spec=SearchSourceAdapter)
        mock_adapter.get_source_type.return_value = "test_source"

        pipeline.register_adapter(mock_adapter)

        assert len(pipeline._adapters) == 1

    def test_register_default_adapters(self):
        """Test default adapter registration."""
        from research.embedding_pipeline import EmbeddingPipeline

        pipeline = EmbeddingPipeline()

        # Mock the adapter imports to avoid file dependencies
        with patch('research.embedding_pipeline.get_coda_adapters') as mock_coda:
            with patch('research.embedding_pipeline.IntercomSearchAdapter') as mock_intercom:
                mock_coda_page = Mock()
                mock_coda_page.get_source_type.return_value = "coda_page"
                mock_coda_theme = Mock()
                mock_coda_theme.get_source_type.return_value = "coda_theme"
                mock_coda.return_value = [mock_coda_page, mock_coda_theme]

                mock_intercom_adapter = Mock()
                mock_intercom_adapter.get_source_type.return_value = "intercom"
                mock_intercom.return_value = mock_intercom_adapter

                pipeline.register_default_adapters()

                assert len(pipeline._adapters) == 3


# -----------------------------------------------------------------------------
# Integration Tests (with mocked DB)
# -----------------------------------------------------------------------------

class TestEvidenceServiceSuggestEvidence:
    """Tests for EvidenceService.suggest_research_evidence."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database connection."""
        db = Mock()
        cursor = MagicMock()
        db.cursor.return_value.__enter__ = Mock(return_value=cursor)
        db.cursor.return_value.__exit__ = Mock(return_value=False)
        return db, cursor

    @pytest.fixture
    def mock_search_service(self):
        """Create mock search service."""
        service = Mock()
        service.suggest_evidence.return_value = [
            UnifiedSearchResult(
                id=1,
                source_type="coda_page",
                source_id="page_123",
                title="Research Page",
                snippet="Relevant research content...",
                similarity=0.85,
                url="https://coda.io/d/doc/_/page_123",
                metadata={},
            )
        ]
        return service

    def test_suggest_evidence_success(self, mock_db, mock_search_service):
        """Test successful evidence suggestion."""
        from story_tracking.services.evidence_service import EvidenceService

        db, cursor = mock_db
        cursor.fetchone.return_value = {
            "title": "Test Story",
            "description": "Story about scheduling issues",
        }

        service = EvidenceService(db)
        story_id = uuid4()

        suggestions = service.suggest_research_evidence(
            story_id=story_id,
            search_service=mock_search_service,
        )

        assert len(suggestions) == 1
        assert suggestions[0].source_type == "coda_page"
        assert suggestions[0].similarity == 0.85
        assert suggestions[0].status == "suggested"

    def test_suggest_evidence_story_not_found(self, mock_db, mock_search_service):
        """Test when story is not found."""
        from story_tracking.services.evidence_service import EvidenceService

        db, cursor = mock_db
        cursor.fetchone.return_value = None

        service = EvidenceService(db)
        story_id = uuid4()

        suggestions = service.suggest_research_evidence(
            story_id=story_id,
            search_service=mock_search_service,
        )

        assert suggestions == []

    def test_suggest_evidence_empty_content(self, mock_db, mock_search_service):
        """Test when story has no title or description."""
        from story_tracking.services.evidence_service import EvidenceService

        db, cursor = mock_db
        cursor.fetchone.return_value = {
            "title": "",
            "description": "",
        }

        service = EvidenceService(db)
        story_id = uuid4()

        suggestions = service.suggest_research_evidence(
            story_id=story_id,
            search_service=mock_search_service,
        )

        assert suggestions == []
        # Search should not be called with empty query
        mock_search_service.suggest_evidence.assert_not_called()


# -----------------------------------------------------------------------------
# ReindexResponse Tests
# -----------------------------------------------------------------------------

class TestReindexResponse:
    """Tests for ReindexResponse model."""

    def test_completed_response(self):
        """Test completed reindex response."""
        response = ReindexResponse(
            status="completed",
            source_types=["coda_page", "coda_theme"],
            items_processed=100,
            items_updated=50,
            items_failed=0,
            duration_seconds=5.5,
        )

        assert response.status == "completed"
        assert response.items_processed == 100
        assert response.items_updated == 50

    def test_failed_response(self):
        """Test failed reindex response."""
        response = ReindexResponse(
            status="failed",
            source_types=["intercom"],
            items_processed=10,
            items_failed=10,
            error="Database connection failed",
        )

        assert response.status == "failed"
        assert response.error == "Database connection failed"
