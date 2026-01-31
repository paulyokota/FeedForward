"""
Tests for ImplementationContextService

Issue: #180 - Hybrid Implementation Context
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, Mock

from src.story_tracking.services.implementation_context_service import (
    ImplementationContextService,
    DEFAULT_TOP_K,
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_MODEL,
)
from src.story_tracking.models import (
    ImplementationContext,
    ImplementationContextCandidate,
    ImplementationContextFile,
)
from src.research.models import UnifiedSearchResult


class TestQueryBuilding:
    """Test retrieval query construction."""

    def test_build_query_with_title_only(self):
        """Query should include title when no theme data."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        query = service._build_retrieval_query(
            story_title="Fix scheduling bug",
            theme_data={},
        )

        assert "Fix scheduling bug" in query

    def test_build_query_with_product_area(self):
        """Query should include product area when available."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        query = service._build_retrieval_query(
            story_title="Fix bug",
            theme_data={"product_area": "scheduling"},
        )

        assert "Fix bug" in query
        assert "scheduling" in query

    def test_build_query_with_symptoms(self):
        """Query should include symptoms when available."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        query = service._build_retrieval_query(
            story_title="Fix bug",
            theme_data={"symptoms": ["slow loading", "timeout errors"]},
        )

        assert "Fix bug" in query
        assert "slow loading" in query
        assert "timeout errors" in query

    def test_build_query_limits_symptoms_to_five(self):
        """Query should limit symptoms to 5 to avoid too-long queries."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        symptoms = [f"symptom_{i}" for i in range(10)]
        query = service._build_retrieval_query(
            story_title="Fix bug",
            theme_data={"symptoms": symptoms},
        )

        # Should contain first 5 symptoms
        assert "symptom_0" in query
        assert "symptom_4" in query
        # Should not contain symptoms beyond 5
        assert "symptom_5" not in query

    def test_build_query_with_user_intent(self):
        """Query should include user intent when available."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        query = service._build_retrieval_query(
            story_title="Fix bug",
            theme_data={"user_intent": "User wants to schedule posts"},
        )

        assert "User wants to schedule posts" in query


class TestCandidateRetrieval:
    """Test vector search retrieval."""

    def test_retrieve_candidates_calls_search_service(self):
        """Should call search service with correct parameters."""
        mock_search = MagicMock()
        mock_search.search.return_value = []
        service = ImplementationContextService(
            search_service=mock_search,
            top_k=10,
            min_similarity=0.5,
        )

        candidates = service._retrieve_candidates("test query")

        mock_search.search.assert_called_once_with(
            query="test query",
            limit=10,
            min_similarity=0.5,
            source_types=["coda_page", "coda_theme"],
        )

    def test_retrieve_candidates_converts_results(self):
        """Should convert search results to ImplementationContextCandidate."""
        mock_search = MagicMock()
        # Use real Pydantic model, not dict (Q5 fix)
        mock_search.search.return_value = [
            UnifiedSearchResult(
                id=1,
                source_id="doc_123",
                title="Prior Story",
                snippet="This is relevant content",
                similarity=0.85,
                source_type="coda_page",
                url="https://example.com/doc",
                metadata={},
            )
        ]
        service = ImplementationContextService(search_service=mock_search)

        candidates = service._retrieve_candidates("test query")

        assert len(candidates) == 1
        assert candidates[0].source_type == "evidence"
        assert candidates[0].source_id == "doc_123"
        assert candidates[0].title == "Prior Story"
        assert candidates[0].similarity == 0.85

    def test_retrieve_candidates_handles_empty_results(self):
        """Should return empty list when no results."""
        mock_search = MagicMock()
        mock_search.search.return_value = []
        service = ImplementationContextService(search_service=mock_search)

        candidates = service._retrieve_candidates("test query")

        assert candidates == []

    def test_retrieve_candidates_handles_search_error(self):
        """Should return empty list on search error."""
        mock_search = MagicMock()
        mock_search.search.side_effect = Exception("Search failed")
        service = ImplementationContextService(search_service=mock_search)

        candidates = service._retrieve_candidates("test query")

        assert candidates == []


class TestSynthesis:
    """Test OpenAI synthesis."""

    def test_synthesize_context_parses_json_response(self):
        """Should parse valid JSON response from OpenAI."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "summary": "Test summary",
            "relevant_files": [
                {"path": "src/test.py", "rationale": "Main file", "priority": "high"}
            ],
            "next_steps": ["Step 1", "Step 2"],
            "prior_art_references": ["Reference 1"],
        })

        # Mock the _client attribute (not the property)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        service._client = mock_client

        candidates = [
            ImplementationContextCandidate(
                source_type="evidence",
                source_id="1",
                title="Test",
                snippet="Content",
                similarity=0.8,
            )
        ]

        context = service._synthesize_context(
            story_title="Test Story",
            theme_data={"product_area": "testing"},
            candidates=candidates,
            retrieval_query="test query",
            retrieval_duration_ms=100,
        )

        assert context.summary == "Test summary"
        assert len(context.relevant_files) == 1
        assert context.relevant_files[0].path == "src/test.py"
        assert len(context.next_steps) == 2
        assert context.source == "hybrid"
        assert context.success is True

    def test_synthesize_context_handles_markdown_json(self):
        """Should parse JSON wrapped in markdown code blocks."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        # Response with markdown code block
        json_content = json.dumps({
            "summary": "Markdown wrapped",
            "relevant_files": [],
            "next_steps": [],
            "prior_art_references": [],
        })
        markdown_response = f"```json\n{json_content}\n```"

        parsed = service._parse_synthesis_response(markdown_response)

        assert parsed["summary"] == "Markdown wrapped"

    def test_synthesize_context_handles_invalid_json(self):
        """Should return fallback on invalid JSON."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        parsed = service._parse_synthesis_response("Not valid JSON at all")

        assert "summary" in parsed
        assert parsed["relevant_files"] == []
        assert parsed["next_steps"] == []


class TestNoCandidatesFallback:
    """Test deterministic fallback when no candidates found."""

    def test_generate_with_no_candidates_returns_fallback(self):
        """Should return deterministic 'no prior art' context when no candidates."""
        mock_search = MagicMock()
        mock_search.search.return_value = []  # No candidates
        service = ImplementationContextService(search_service=mock_search)

        context = service.generate(
            story_title="Novel Issue",
            theme_data={"product_area": "new_area"},
        )

        assert "No prior art found" in context.summary
        assert context.source == "none"
        assert context.success is True
        assert context.candidates_retrieved == 0
        assert context.relevant_files == []
        assert context.next_steps == []
        assert context.schema_version == "1.0"


class TestErrorHandling:
    """Test error handling in generation."""

    def test_generate_handles_synthesis_error(self):
        """Should return error context when synthesis fails."""
        mock_search = MagicMock()
        # Use real Pydantic model, not dict (Q5 fix)
        mock_search.search.return_value = [
            UnifiedSearchResult(
                id=1,
                source_id="1",
                title="Doc",
                snippet="Content",
                similarity=0.8,
                source_type="coda_page",
                url="https://example.com",
                metadata={},
            )
        ]
        service = ImplementationContextService(search_service=mock_search)

        # Make synthesis fail
        with patch.object(service, "_synthesize_context") as mock_synth:
            mock_synth.side_effect = Exception("OpenAI timeout")

            context = service.generate(
                story_title="Test",
                theme_data={},
            )

        assert context.success is False
        assert "OpenAI timeout" in context.error
        assert context.source == "hybrid"
        assert context.candidates_retrieved == 1


class TestConfigurationOptions:
    """Test service configuration."""

    def test_default_configuration(self):
        """Should use default configuration values."""
        mock_search = MagicMock()
        service = ImplementationContextService(search_service=mock_search)

        assert service.top_k == DEFAULT_TOP_K
        assert service.min_similarity == DEFAULT_MIN_SIMILARITY
        assert service.model == DEFAULT_MODEL

    def test_custom_configuration(self):
        """Should accept custom configuration."""
        mock_search = MagicMock()
        service = ImplementationContextService(
            search_service=mock_search,
            top_k=5,
            min_similarity=0.7,
            model="gpt-4",
        )

        assert service.top_k == 5
        assert service.min_similarity == 0.7
        assert service.model == "gpt-4"


class TestImplementationContextModel:
    """Test the Pydantic model."""

    def test_implementation_context_default_values(self):
        """Should have correct default values."""
        context = ImplementationContext()

        assert context.summary == ""
        assert context.relevant_files == []
        assert context.next_steps == []
        assert context.prior_art_references == []
        assert context.candidates_retrieved == 0
        assert context.top_k == 10
        assert context.source == "hybrid"
        assert context.success is True
        assert context.schema_version == "1.0"

    def test_implementation_context_serialization(self):
        """Should serialize to JSON-compatible dict."""
        context = ImplementationContext(
            summary="Test summary",
            relevant_files=[
                ImplementationContextFile(
                    path="src/test.py",
                    rationale="Main file",
                    priority="high",
                )
            ],
            next_steps=["Step 1"],
            candidates_retrieved=5,
            source="hybrid",
        )

        data = context.model_dump()

        assert data["summary"] == "Test summary"
        assert len(data["relevant_files"]) == 1
        assert data["relevant_files"][0]["path"] == "src/test.py"
        assert data["candidates_retrieved"] == 5

    def test_implementation_context_candidate_model(self):
        """Should validate candidate model."""
        candidate = ImplementationContextCandidate(
            source_type="story",
            source_id="story_123",
            title="Prior Story",
            snippet="Content",
            similarity=0.85,
            metadata={"product_area": "scheduling"},
        )

        assert candidate.source_type == "story"
        assert candidate.source_id == "story_123"
        assert candidate.similarity == 0.85


class TestPromptModule:
    """Test the prompt module."""

    def test_build_prompt_with_candidates(self):
        """Should build prompt with candidates section."""
        from src.prompts.implementation_context import build_implementation_context_prompt

        prompt = build_implementation_context_prompt(
            story_title="Fix scheduling bug",
            product_area="scheduling",
            symptoms=["slow loading"],
            candidates=[
                {
                    "title": "Prior Story",
                    "snippet": "Relevant content",
                    "similarity": 0.85,
                    "metadata": {"source_type": "coda_page"},
                }
            ],
        )

        assert "Fix scheduling bug" in prompt
        assert "scheduling" in prompt
        assert "slow loading" in prompt
        assert "Prior Story" in prompt
        assert "0.85" in prompt

    def test_build_prompt_without_candidates(self):
        """Should build prompt with 'no prior art' message."""
        from src.prompts.implementation_context import build_implementation_context_prompt

        prompt = build_implementation_context_prompt(
            story_title="Novel Issue",
            product_area="",
            symptoms=[],
            candidates=[],
        )

        assert "Novel Issue" in prompt
        assert "No similar prior stories" in prompt
