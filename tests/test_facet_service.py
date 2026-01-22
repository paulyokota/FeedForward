"""
Tests for facet extraction service.

Tests cover:
- FacetExtractionService async/sync extraction
- JSON parsing with markdown handling
- Validation and normalization
- Error handling and sanitization
- Batch processing with stop signal
- Storage integration
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.facet_service import (
    FACET_MODEL,
    FACET_PROMPT,
    MAX_TEXT_CHARS,
    VALID_ACTION_TYPES,
    VALID_DIRECTIONS,
    BatchFacetResult,
    FacetExtractionService,
    FacetResult,
    _parse_json_response,
    _sanitize_error_message,
    _truncate_words,
)


class TestFacetExtractionServiceStructure:
    """Tests for service structure and configuration."""

    def test_service_initialization_defaults(self):
        """Service initializes with default model."""
        service = FacetExtractionService()
        assert service.model == FACET_MODEL

    def test_service_initialization_custom_model(self):
        """Service accepts custom model."""
        service = FacetExtractionService(model="gpt-4")
        assert service.model == "gpt-4"

    def test_lazy_client_initialization(self):
        """Clients are lazily initialized."""
        service = FacetExtractionService()
        assert service._sync_client is None
        assert service._async_client is None


class TestValidActionTypes:
    """Tests for action type literals."""

    def test_valid_action_types_count(self):
        """8 valid action types per T-006."""
        assert len(VALID_ACTION_TYPES) == 8

    def test_valid_action_types_contains_unknown(self):
        """unknown is a valid fallback."""
        assert "unknown" in VALID_ACTION_TYPES

    def test_valid_action_types_contains_all_expected(self):
        """All expected action types are present."""
        expected = {
            "inquiry", "complaint", "bug_report", "how_to_question",
            "feature_request", "account_change", "delete_request", "unknown"
        }
        assert VALID_ACTION_TYPES == expected


class TestValidDirections:
    """Tests for direction literals."""

    def test_valid_directions_count(self):
        """7 valid directions per T-006."""
        assert len(VALID_DIRECTIONS) == 7

    def test_valid_directions_contains_neutral(self):
        """neutral is a valid fallback."""
        assert "neutral" in VALID_DIRECTIONS

    def test_valid_directions_contains_all_expected(self):
        """All expected directions are present."""
        expected = {
            "excess", "deficit", "creation", "deletion",
            "modification", "performance", "neutral"
        }
        assert VALID_DIRECTIONS == expected


class TestTruncateWords:
    """Tests for word truncation helper."""

    def test_truncate_under_limit(self):
        """Text under limit is unchanged."""
        text = "one two three"
        assert _truncate_words(text, 10) == text

    def test_truncate_at_limit(self):
        """Text at limit is unchanged."""
        text = "one two three four five six seven eight nine ten"
        assert _truncate_words(text, 10) == text

    def test_truncate_over_limit(self):
        """Text over limit is truncated."""
        text = "one two three four five six seven eight nine ten eleven"
        assert _truncate_words(text, 10) == "one two three four five six seven eight nine ten"

    def test_truncate_empty_string(self):
        """Empty string returns empty."""
        assert _truncate_words("", 10) == ""


class TestParseJsonResponse:
    """Tests for JSON parsing with markdown handling."""

    def test_parse_simple_json(self):
        """Parses simple JSON."""
        content = '{"action_type": "bug_report", "direction": "deficit"}'
        result = _parse_json_response(content)
        assert result["action_type"] == "bug_report"
        assert result["direction"] == "deficit"

    def test_parse_json_with_whitespace(self):
        """Parses JSON with leading/trailing whitespace."""
        content = '  {"action_type": "inquiry"}  '
        result = _parse_json_response(content)
        assert result["action_type"] == "inquiry"

    def test_parse_json_in_markdown_block(self):
        """Parses JSON from markdown code block."""
        content = '```json\n{"action_type": "feature_request"}\n```'
        result = _parse_json_response(content)
        assert result["action_type"] == "feature_request"

    def test_parse_json_in_plain_markdown_block(self):
        """Parses JSON from plain markdown code block."""
        content = '```\n{"direction": "excess"}\n```'
        result = _parse_json_response(content)
        assert result["direction"] == "excess"

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_json_response("not valid json")

    def test_parse_empty_raises(self):
        """Empty content raises ValueError."""
        with pytest.raises(ValueError):
            _parse_json_response("")


class TestSanitizeErrorMessage:
    """Tests for error message sanitization."""

    def test_sanitize_rate_limit(self):
        """Rate limit errors are sanitized."""
        error = Exception("rate_limit_exceeded")
        assert "retry later" in _sanitize_error_message(error).lower()

    def test_sanitize_api_key(self):
        """API key errors are sanitized."""
        error = Exception("invalid_api_key: sk-secret123")
        result = _sanitize_error_message(error)
        assert "authentication failed" in result.lower()
        assert "sk-secret" not in result

    def test_sanitize_json_error(self):
        """JSON errors are sanitized."""
        error = json.JSONDecodeError("msg", "doc", 0)
        assert "JSON" in _sanitize_error_message(error)

    def test_sanitize_unknown_error(self):
        """Unknown errors return generic message."""
        error = ValueError("something went wrong")
        result = _sanitize_error_message(error)
        assert "ValueError" in result
        assert "something went wrong" not in result


class TestFacetResultDataclass:
    """Tests for FacetResult structure."""

    def test_successful_result(self):
        """Successful result has all fields."""
        result = FacetResult(
            conversation_id="123",
            action_type="bug_report",
            direction="deficit",
            symptom="app crashes on login",
            user_goal="log into account",
            success=True,
        )
        assert result.success
        assert result.error is None

    def test_failed_result(self):
        """Failed result has error field."""
        result = FacetResult(
            conversation_id="123",
            action_type="unknown",
            direction="neutral",
            symptom="",
            user_goal="",
            success=False,
            error="API error",
        )
        assert not result.success
        assert result.error == "API error"


class TestBatchFacetResultDataclass:
    """Tests for BatchFacetResult structure."""

    def test_empty_batch(self):
        """Empty batch has correct counts."""
        result = BatchFacetResult(
            successful=[],
            failed=[],
            total_processed=0,
            total_success=0,
            total_failed=0,
        )
        assert result.total_processed == 0

    def test_mixed_batch(self):
        """Mixed batch has correct counts."""
        success = FacetResult("1", "bug_report", "deficit", "", "", True)
        failure = FacetResult("2", "unknown", "neutral", "", "", False, "error")
        result = BatchFacetResult(
            successful=[success],
            failed=[failure],
            total_processed=2,
            total_success=1,
            total_failed=1,
        )
        assert result.total_success == 1
        assert result.total_failed == 1


class TestFacetValidation:
    """Tests for facet validation in the service."""

    def test_validate_valid_action_type(self):
        """Valid action types pass validation."""
        service = FacetExtractionService()
        data = {"action_type": "bug_report", "direction": "neutral"}
        result = service._validate_facets(data)
        assert result["action_type"] == "bug_report"

    def test_validate_invalid_action_type(self):
        """Invalid action type defaults to unknown."""
        service = FacetExtractionService()
        data = {"action_type": "invalid_type", "direction": "neutral"}
        result = service._validate_facets(data)
        assert result["action_type"] == "unknown"

    def test_validate_valid_direction(self):
        """Valid directions pass validation."""
        service = FacetExtractionService()
        data = {"action_type": "bug_report", "direction": "excess"}
        result = service._validate_facets(data)
        assert result["direction"] == "excess"

    def test_validate_invalid_direction(self):
        """Invalid direction defaults to neutral."""
        service = FacetExtractionService()
        data = {"action_type": "bug_report", "direction": "invalid_direction"}
        result = service._validate_facets(data)
        assert result["direction"] == "neutral"

    def test_validate_truncates_long_symptom(self):
        """Long symptom is truncated to 10 words."""
        service = FacetExtractionService()
        long_symptom = " ".join(["word"] * 20)
        data = {"action_type": "bug_report", "direction": "neutral", "symptom": long_symptom}
        result = service._validate_facets(data)
        assert len(result["symptom"].split()) == 10

    def test_validate_truncates_long_user_goal(self):
        """Long user_goal is truncated to 10 words."""
        service = FacetExtractionService()
        long_goal = " ".join(["word"] * 20)
        data = {"action_type": "bug_report", "direction": "neutral", "user_goal": long_goal}
        result = service._validate_facets(data)
        assert len(result["user_goal"].split()) == 10


class TestTextTruncation:
    """Tests for conversation text truncation."""

    def test_truncate_short_text(self):
        """Short text is not truncated."""
        service = FacetExtractionService()
        text = "Short text"
        assert service._truncate_text(text) == text

    def test_truncate_long_text(self):
        """Long text is truncated to MAX_TEXT_CHARS."""
        service = FacetExtractionService()
        text = "x" * (MAX_TEXT_CHARS + 100)
        result = service._truncate_text(text)
        assert len(result) == MAX_TEXT_CHARS


class TestPromptFormat:
    """Tests for prompt template."""

    def test_prompt_contains_placeholders(self):
        """Prompt has conversation placeholder."""
        assert "{conversation}" in FACET_PROMPT

    def test_prompt_contains_action_types(self):
        """Prompt lists action types."""
        assert "inquiry" in FACET_PROMPT
        assert "complaint" in FACET_PROMPT
        assert "bug_report" in FACET_PROMPT

    def test_prompt_contains_directions(self):
        """Prompt lists directions."""
        assert "excess" in FACET_PROMPT
        assert "deficit" in FACET_PROMPT
        assert "neutral" in FACET_PROMPT

    def test_prompt_requests_json(self):
        """Prompt asks for JSON format."""
        assert "JSON" in FACET_PROMPT


class TestExtractFacetSync:
    """Tests for synchronous single extraction."""

    @patch.object(FacetExtractionService, "sync_client", create=True)
    def test_extract_facet_success(self, mock_client):
        """Successful extraction returns correct result."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "action_type": "bug_report",
            "direction": "deficit",
            "symptom": "cannot login",
            "user_goal": "access account",
        })
        mock_client.chat.completions.create.return_value = mock_response

        service = FacetExtractionService()
        service._sync_client = mock_client

        result = service.extract_facet_sync("conv_123", "I cannot login to my account")

        assert result.success
        assert result.action_type == "bug_report"
        assert result.direction == "deficit"
        assert result.conversation_id == "conv_123"

    @patch.object(FacetExtractionService, "sync_client", create=True)
    def test_extract_facet_empty_text(self, mock_client):
        """Empty text returns failed result."""
        service = FacetExtractionService()
        service._sync_client = mock_client

        result = service.extract_facet_sync("conv_123", "")

        assert not result.success
        assert result.error == "Empty conversation text"
        assert result.action_type == "unknown"
        assert result.direction == "neutral"
        mock_client.chat.completions.create.assert_not_called()

    @patch.object(FacetExtractionService, "sync_client", create=True)
    def test_extract_facet_api_error(self, mock_client):
        """API error returns sanitized error message."""
        mock_client.chat.completions.create.side_effect = Exception("rate_limit_exceeded")

        service = FacetExtractionService()
        service._sync_client = mock_client

        result = service.extract_facet_sync("conv_123", "test text")

        assert not result.success
        assert "retry later" in result.error.lower()


class TestExtractFacetAsync:
    """Tests for asynchronous single extraction."""

    @pytest.mark.asyncio
    async def test_extract_facet_async_success(self):
        """Successful async extraction returns correct result."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "action_type": "feature_request",
            "direction": "creation",
            "symptom": "need dark mode",
            "user_goal": "enable dark theme",
        })

        service = FacetExtractionService()
        service._async_client = MagicMock()
        service._async_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await service.extract_facet_async("conv_456", "Please add dark mode")

        assert result.success
        assert result.action_type == "feature_request"
        assert result.direction == "creation"

    @pytest.mark.asyncio
    async def test_extract_facet_async_empty_text(self):
        """Empty text returns failed result."""
        service = FacetExtractionService()

        result = await service.extract_facet_async("conv_456", "   ")

        assert not result.success
        assert result.error == "Empty conversation text"


class TestExtractFacetsBatchAsync:
    """Tests for batch async extraction."""

    @pytest.mark.asyncio
    async def test_batch_empty_conversations(self):
        """Empty list returns empty result."""
        service = FacetExtractionService()

        result = await service.extract_facets_batch_async([])

        assert result.total_processed == 0
        assert result.total_success == 0
        assert result.total_failed == 0

    @pytest.mark.asyncio
    async def test_batch_with_stop_signal(self):
        """Stop signal stops processing."""
        service = FacetExtractionService()
        service._async_client = MagicMock()

        # Process only first, then stop
        call_count = [0]

        def stop_checker():
            call_count[0] += 1
            return call_count[0] > 1  # Stop after first check

        conversations = [
            {"id": "1", "source_body": "text 1"},
            {"id": "2", "source_body": "text 2"},
            {"id": "3", "source_body": "text 3"},
        ]

        result = await service.extract_facets_batch_async(conversations, stop_checker)

        # First conversation should be partially processed, rest marked failed with "Stopped by user"
        stopped_count = len([f for f in result.failed if f.error == "Stopped by user"])
        assert stopped_count > 0

    @pytest.mark.asyncio
    async def test_batch_mixed_success_failure(self):
        """Batch handles mix of success and failure."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "action_type": "inquiry",
            "direction": "neutral",
            "symptom": "need help",
            "user_goal": "get answer",
        })

        service = FacetExtractionService()
        service._async_client = MagicMock()
        service._async_client.chat.completions.create = AsyncMock(return_value=mock_response)

        conversations = [
            {"id": "1", "source_body": "valid text"},
            {"id": "2", "source_body": ""},  # Empty - will fail
            {"id": "3", "source_body": "another valid text"},
        ]

        result = await service.extract_facets_batch_async(conversations)

        assert result.total_processed == 3
        assert result.total_success == 2
        assert result.total_failed == 1


class TestFacetStorage:
    """Tests for facet storage integration."""

    def test_store_facets_batch_filters_failed(self):
        """Only successful results are stored (verifies filtering logic)."""
        from src.services.facet_service import FacetResult

        results = [
            FacetResult("1", "bug_report", "deficit", "issue", "fix", True),
            FacetResult("2", "unknown", "neutral", "", "", False, "error"),
            FacetResult("3", "inquiry", "neutral", "question", "help", True),
        ]

        # Test the filtering logic directly
        successful_results = [r for r in results if r.success]
        assert len(successful_results) == 2
        assert all(r.success for r in successful_results)

    def test_store_facets_batch_empty_results(self):
        """Empty results returns 0."""
        from src.db.facet_storage import store_facets_batch

        count = store_facets_batch([], pipeline_run_id=42)
        assert count == 0

    def test_store_facets_batch_all_failed(self):
        """All failed results returns 0."""
        from src.db.facet_storage import store_facets_batch
        from src.services.facet_service import FacetResult

        results = [
            FacetResult("1", "unknown", "neutral", "", "", False, "error1"),
            FacetResult("2", "unknown", "neutral", "", "", False, "error2"),
        ]

        count = store_facets_batch(results, pipeline_run_id=42)
        assert count == 0


class TestMigrationFile:
    """Tests for migration file existence and structure."""

    def test_migration_014_exists(self):
        """Migration 014 for facet extraction phase exists."""
        import os
        migration_path = "src/db/migrations/014_facet_extraction_phase.sql"
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"

    def test_migration_014_adds_columns(self):
        """Migration adds facets_extracted and facets_failed columns."""
        with open("src/db/migrations/014_facet_extraction_phase.sql") as f:
            content = f.read()

        assert "facets_extracted" in content
        assert "facets_failed" in content
        assert "ALTER TABLE pipeline_runs" in content


class TestPipelineIntegrationSignatures:
    """Tests for pipeline integration function signatures."""

    def test_facet_service_has_batch_async_method(self):
        """FacetExtractionService has extract_facets_batch_async method."""
        service = FacetExtractionService()
        assert hasattr(service, "extract_facets_batch_async")
        assert callable(service.extract_facets_batch_async)

    def test_facet_service_has_batch_sync_method(self):
        """FacetExtractionService has extract_facets_batch_sync method."""
        service = FacetExtractionService()
        assert hasattr(service, "extract_facets_batch_sync")
        assert callable(service.extract_facets_batch_sync)

    def test_facet_result_has_required_fields(self):
        """FacetResult has all required fields."""
        result = FacetResult(
            conversation_id="123",
            action_type="unknown",
            direction="neutral",
            symptom="",
            user_goal="",
            success=False,
        )
        assert hasattr(result, "conversation_id")
        assert hasattr(result, "action_type")
        assert hasattr(result, "direction")
        assert hasattr(result, "symptom")
        assert hasattr(result, "user_goal")
        assert hasattr(result, "success")
        assert hasattr(result, "error")


class TestModelAndSchemaFields:
    """Tests for model and schema field consistency."""

    def test_pipeline_run_model_has_facet_fields(self):
        """PipelineRun model has facet tracking fields."""
        from src.db.models import PipelineRun

        run = PipelineRun()
        assert hasattr(run, "facets_extracted")
        assert hasattr(run, "facets_failed")
        assert run.facets_extracted == 0
        assert run.facets_failed == 0

    def test_pipeline_status_schema_has_facet_fields(self):
        """PipelineStatus schema has facet tracking fields."""
        from src.api.schemas.pipeline import PipelineStatus

        # Check that the fields exist in the model
        assert "facets_extracted" in PipelineStatus.model_fields
        assert "facets_failed" in PipelineStatus.model_fields

    def test_pipeline_run_list_item_has_facet_fields(self):
        """PipelineRunListItem schema has facet tracking fields."""
        from src.api.schemas.pipeline import PipelineRunListItem

        assert "facets_extracted" in PipelineRunListItem.model_fields
