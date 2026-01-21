"""
Research Module Tests

Tests for search adapters, UnifiedSearchService, EmbeddingPipeline,
and evidence decision endpoints.
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

from fastapi.testclient import TestClient
from psycopg2 import IntegrityError

from src.api.main import app
from src.api.deps import get_db
from research.models import (
    SearchableContent,
    UnifiedSearchResult,
    UnifiedSearchRequest,
    SimilarContentRequest,
    SuggestedEvidence,
    EmbeddingStats,
    ReindexRequest,
    ReindexResponse,
    EvidenceDecisionResponse,
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


# -----------------------------------------------------------------------------
# Evidence Decision Endpoint Tests
# -----------------------------------------------------------------------------


class TestEvidenceDecisionEndpoints:
    """Tests for POST /api/research/stories/{story_id}/suggested-evidence/{evidence_id}/accept|reject endpoints."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection with cursor context manager."""
        db = Mock()
        cursor = MagicMock()
        db.cursor.return_value.__enter__ = Mock(return_value=cursor)
        db.cursor.return_value.__exit__ = Mock(return_value=False)
        return db, cursor

    @pytest.fixture
    def client(self, mock_db):
        """Create a test client with overridden database dependency."""
        db, _ = mock_db
        app.dependency_overrides[get_db] = lambda: db

        yield TestClient(app)

        # Clean up overrides after test
        app.dependency_overrides.clear()

    @pytest.fixture
    def sample_story_id(self):
        """Generate a valid UUID for a story."""
        return uuid4()

    @pytest.fixture
    def valid_evidence_id(self):
        """Generate a valid evidence ID."""
        return "coda_page:page_123"

    # -------------------------------------------------------------------------
    # Happy Path Tests
    # -------------------------------------------------------------------------

    def test_accept_evidence_success(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test accepting valid evidence returns 200 and records in DB."""
        db, cursor = mock_db
        # Story exists
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/accept"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["story_id"] == str(sample_story_id)
        assert data["evidence_id"] == valid_evidence_id
        assert data["decision"] == "accepted"

        # Verify DB was called to insert the decision
        cursor.execute.assert_called()
        # Note: db.commit() is called by FastAPI dependency, not by the endpoint

    def test_reject_evidence_success(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test rejecting valid evidence returns 200 and records in DB."""
        db, cursor = mock_db
        # Story exists
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/reject"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["story_id"] == str(sample_story_id)
        assert data["evidence_id"] == valid_evidence_id
        assert data["decision"] == "rejected"

        # Verify DB was called to insert the decision
        cursor.execute.assert_called()
        # Note: db.commit() is called by FastAPI dependency, not by the endpoint

    # -------------------------------------------------------------------------
    # Validation Tests
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_evidence_invalid_format_missing_colon(self, client, mock_db, sample_story_id, action):
        """Test evidence with missing colon in evidence_id returns 400 for both accept and reject."""
        db, cursor = mock_db

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/invalid_evidence_id/{action}"
        )

        assert response.status_code == 400
        assert "Invalid evidence_id format" in response.json()["detail"]
        if action == "accept":
            assert "Expected 'source_type:source_id'" in response.json()["detail"]

    def test_accept_evidence_invalid_source_type(self, client, mock_db, sample_story_id):
        """Test accepting evidence with unknown source_type returns 400."""
        db, cursor = mock_db

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/unknown_type:page_123/accept"
        )

        assert response.status_code == 400
        assert "Invalid source_type" in response.json()["detail"]
        assert "unknown_type" in response.json()["detail"]

    def test_accept_evidence_empty_source_type(self, client, mock_db, sample_story_id):
        """Test accepting evidence with empty source_type returns 400."""
        db, cursor = mock_db

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/:page_123/accept"
        )

        assert response.status_code == 400
        assert "Invalid evidence_id format" in response.json()["detail"]
        assert "Both source_type and source_id are required" in response.json()["detail"]

    def test_accept_evidence_empty_source_id(self, client, mock_db, sample_story_id):
        """Test accepting evidence with empty source_id returns 400."""
        db, cursor = mock_db

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/coda_page:/accept"
        )

        assert response.status_code == 400
        assert "Invalid evidence_id format" in response.json()["detail"]
        assert "Both source_type and source_id are required" in response.json()["detail"]

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_evidence_story_not_found(self, client, mock_db, valid_evidence_id, action):
        """Test accepting/rejecting evidence for non-existent story returns 404."""
        db, cursor = mock_db
        # Story does not exist
        cursor.fetchone.return_value = None

        non_existent_story_id = uuid4()

        response = client.post(
            f"/api/research/stories/{non_existent_story_id}/suggested-evidence/{valid_evidence_id}/{action}"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
        if action == "accept":
            assert str(non_existent_story_id) in response.json()["detail"]

    def test_state_transition_accepted_to_rejected(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test state transition from accepted to rejected succeeds (UPSERT behavior)."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        # First accept (initial decision)
        response1 = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/accept"
        )
        assert response1.status_code == 200
        assert response1.json()["decision"] == "accepted"

        # Then reject (state transition)
        response2 = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/reject"
        )
        assert response2.status_code == 200
        assert response2.json()["decision"] == "rejected"

    def test_state_transition_rejected_to_accepted(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test state transition from rejected to accepted succeeds (UPSERT behavior)."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        # First reject (initial decision)
        response1 = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/reject"
        )
        assert response1.status_code == 200
        assert response1.json()["decision"] == "rejected"

        # Then accept (state transition)
        response2 = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/accept"
        )
        assert response2.status_code == 200
        assert response2.json()["decision"] == "accepted"

    def test_repeat_same_decision_succeeds(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test repeating the same decision succeeds (idempotent UPSERT)."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        # Accept twice
        response1 = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/accept"
        )
        assert response1.status_code == 200

        response2 = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/accept"
        )
        assert response2.status_code == 200
        assert response2.json()["decision"] == "accepted"

    # -------------------------------------------------------------------------
    # Valid Source Type Tests
    # -------------------------------------------------------------------------

    def test_accept_evidence_coda_theme_source_type(self, client, mock_db, sample_story_id):
        """Test accepting evidence with coda_theme source type succeeds."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        evidence_id = "coda_theme:theme_456"

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{evidence_id}/accept"
        )

        assert response.status_code == 200
        assert response.json()["evidence_id"] == evidence_id
        assert response.json()["decision"] == "accepted"

    def test_accept_evidence_intercom_source_type(self, client, mock_db, sample_story_id):
        """Test accepting evidence with intercom source type succeeds."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        evidence_id = "intercom:conv_789"

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{evidence_id}/accept"
        )

        assert response.status_code == 200
        assert response.json()["evidence_id"] == evidence_id
        assert response.json()["decision"] == "accepted"

    # -------------------------------------------------------------------------
    # Response Structure Tests
    # -------------------------------------------------------------------------

    # Contract test: Verifies API response structure matches EvidenceDecisionResponse model
    def test_accept_response_matches_evidence_decision_response_model(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test accept response structure matches EvidenceDecisionResponse model."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/accept"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present and have correct types
        assert "success" in data
        assert isinstance(data["success"], bool)

        assert "story_id" in data
        assert isinstance(data["story_id"], str)

        assert "evidence_id" in data
        assert isinstance(data["evidence_id"], str)

        assert "decision" in data
        assert data["decision"] in ["accepted", "rejected"]

    # Contract test: Verifies API response structure matches EvidenceDecisionResponse model
    def test_reject_response_matches_evidence_decision_response_model(self, client, mock_db, sample_story_id, valid_evidence_id):
        """Test reject response structure matches EvidenceDecisionResponse model."""
        db, cursor = mock_db
        cursor.fetchone.return_value = {"id": str(sample_story_id)}

        response = client.post(
            f"/api/research/stories/{sample_story_id}/suggested-evidence/{valid_evidence_id}/reject"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present and have correct types
        assert "success" in data
        assert isinstance(data["success"], bool)

        assert "story_id" in data
        assert isinstance(data["story_id"], str)

        assert "evidence_id" in data
        assert isinstance(data["evidence_id"], str)

        assert "decision" in data
        assert data["decision"] in ["accepted", "rejected"]

# -----------------------------------------------------------------------------
# Suggested Evidence Filtering Tests (Issue #50)
# -----------------------------------------------------------------------------


class TestSuggestedEvidenceFiltering:
    """Tests for filtering rejected evidence from suggested evidence endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection with cursor context manager."""
        db = Mock()
        cursor = MagicMock()
        db.cursor.return_value.__enter__ = Mock(return_value=cursor)
        db.cursor.return_value.__exit__ = Mock(return_value=False)
        return db, cursor

    @pytest.fixture
    def mock_search_service(self):
        """Create mock search service that returns test results."""
        service = Mock()
        service.suggest_evidence.return_value = [
            UnifiedSearchResult(
                id=1,
                source_type="coda_page",
                source_id="page_123",
                title="Test Page 1",
                snippet="Test content 1",
                similarity=0.85,
                url="https://coda.io/page_123",
                metadata={},
            ),
            UnifiedSearchResult(
                id=2,
                source_type="coda_theme",
                source_id="theme_456",
                title="Test Theme 2",
                snippet="Test content 2",
                similarity=0.80,
                url="https://coda.io/theme_456",
                metadata={},
            ),
            UnifiedSearchResult(
                id=3,
                source_type="coda_page",
                source_id="page_789",
                title="Test Page 3",
                snippet="Test content 3",
                similarity=0.75,
                url="https://coda.io/page_789",
                metadata={},
            ),
        ]
        return service

    @pytest.fixture
    def client(self, mock_db):
        """Create a test client with overridden database dependency."""
        db, _ = mock_db
        app.dependency_overrides[get_db] = lambda: db

        yield TestClient(app)

        # Clean up overrides after test
        app.dependency_overrides.clear()

    @pytest.fixture
    def sample_story_id(self):
        """Generate a valid UUID for a story."""
        return uuid4()

    def test_suggested_evidence_filters_rejected(self, client, mock_db, mock_search_service, sample_story_id):
        """Test that previously rejected evidence is excluded from suggestions."""
        db, cursor = mock_db

        # First call: Get story title/description
        # Second call: Get all evidence decisions (evidence_id, decision)
        cursor.fetchone.return_value = {
            "title": "Test Story",
            "description": "Test Description",
        }
        cursor.fetchall.return_value = [
            {"evidence_id": "coda_page:page_123", "decision": "rejected"},
            {"evidence_id": "coda_theme:theme_456", "decision": "rejected"},
        ]

        # Override search service dependency
        from src.api.routers.research import get_search_service
        app.dependency_overrides[get_search_service] = lambda: mock_search_service

        response = client.get(f"/api/research/stories/{sample_story_id}/suggested-evidence")

        assert response.status_code == 200
        data = response.json()

        # Should only return page_789 (the non-rejected one)
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["source_id"] == "page_789"
        assert data["suggestions"][0]["source_type"] == "coda_page"
        assert data["suggestions"][0]["status"] == "suggested"

        # Cleanup
        app.dependency_overrides.clear()

    def test_suggested_evidence_shows_accepted_status(self, client, mock_db, mock_search_service, sample_story_id):
        """Test that accepted evidence shows status='accepted' in response."""
        db, cursor = mock_db

        # First call: Get story title/description
        # Second call: Get all evidence decisions
        cursor.fetchone.return_value = {
            "title": "Test Story",
            "description": "Test Description",
        }
        cursor.fetchall.return_value = [
            {"evidence_id": "coda_page:page_123", "decision": "accepted"},
        ]

        # Override search service dependency
        from src.api.routers.research import get_search_service
        app.dependency_overrides[get_search_service] = lambda: mock_search_service

        response = client.get(f"/api/research/stories/{sample_story_id}/suggested-evidence")

        assert response.status_code == 200
        data = response.json()

        # All 3 items should be returned (none are rejected)
        assert len(data["suggestions"]) == 3

        # page_123 should have accepted status
        page_123 = next(s for s in data["suggestions"] if s["source_id"] == "page_123")
        assert page_123["status"] == "accepted"

        # Others should have suggested status
        theme_456 = next(s for s in data["suggestions"] if s["source_id"] == "theme_456")
        assert theme_456["status"] == "suggested"

        # Cleanup
        app.dependency_overrides.clear()

    def test_suggested_evidence_no_decisions_returns_all_as_suggested(self, client, mock_db, mock_search_service, sample_story_id):
        """Test that when no decisions exist, all suggestions are returned with status='suggested'."""
        db, cursor = mock_db

        # First call: Get story title/description
        # Second call: Get all evidence decisions (empty)
        cursor.fetchone.return_value = {
            "title": "Test Story",
            "description": "Test Description",
        }
        cursor.fetchall.return_value = []  # Empty rejection set

        # Override search service dependency
        from src.api.routers.research import get_search_service
        app.dependency_overrides[get_search_service] = lambda: mock_search_service

        response = client.get(f"/api/research/stories/{sample_story_id}/suggested-evidence")

        assert response.status_code == 200
        data = response.json()

        # All 3 items should be returned
        assert len(data["suggestions"]) == 3

        # Verify order, IDs, and all have "suggested" status
        assert data["suggestions"][0]["id"] == "coda_page:page_123"
        assert data["suggestions"][0]["status"] == "suggested"
        assert data["suggestions"][1]["id"] == "coda_theme:theme_456"
        assert data["suggestions"][1]["status"] == "suggested"
        assert data["suggestions"][2]["id"] == "coda_page:page_789"
        assert data["suggestions"][2]["status"] == "suggested"

        # Cleanup
        app.dependency_overrides.clear()
