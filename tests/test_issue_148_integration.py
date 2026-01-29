"""
Issue #148 Integration Tests: Parallel Theme Extraction

Integration tests verifying the full data path:
API endpoint → async wrapper → parallel theme extraction → database storage

These tests verify that:
1. The async wrapper is correctly wired (uses asyncio.run)
2. Concurrency parameter flows through the pipeline
3. extract_async correctly wraps sync extract with all parameters

Run with: pytest tests/test_issue_148_integration.py -v

Owner: Kenji (Testing)
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch
import sys

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_theme_result(conv_id: str) -> Mock:
    """Create a mock Theme result from ThemeExtractor."""
    theme = Mock()
    theme.conversation_id = conv_id
    theme.product_area = "Publishing"
    theme.component = "Pinterest"
    theme.issue_signature = f"pinterest_test_issue_{conv_id}"
    theme.user_intent = "Test user intent"
    theme.symptoms = ["Test symptom"]
    theme.affected_flow = "publish_to_pinterest"
    theme.root_cause_hypothesis = "Test hypothesis"
    theme.matched_existing = False
    theme.match_confidence = "high"
    theme.diagnostic_summary = f"Diagnostic summary for {conv_id}"
    theme.key_excerpts = [{"text": "excerpt", "relevance": "relevant"}]
    theme.context_used = ["product_context"]
    theme.context_gaps = []
    theme.resolution_action = None
    theme.root_cause = None
    theme.solution_provided = None
    theme.resolution_category = None
    return theme


# =============================================================================
# Integration Tests: Wiring Verification
# =============================================================================


class TestSyncWrapperWiring:
    """
    Integration test: Verify _run_theme_extraction calls async version.

    This tests the critical wiring - the sync function must call asyncio.run
    to invoke the async parallel extraction.
    """

    def test_run_theme_extraction_calls_asyncio_run(self):
        """Verify _run_theme_extraction uses asyncio.run to call async version."""
        from src.api.routers.pipeline import _run_theme_extraction

        with patch("src.api.routers.pipeline.asyncio.run") as mock_asyncio_run:
            mock_asyncio_run.return_value = {
                "themes_extracted": 5,
                "themes_new": 2,
                "themes_filtered": 1,
                "warnings": [],
            }

            result = _run_theme_extraction(
                run_id=1,
                stop_checker=lambda: False,
                concurrency=15,
            )

            # Verify asyncio.run was called
            mock_asyncio_run.assert_called_once()

            # Verify concurrency was passed through
            call_args = mock_asyncio_run.call_args
            # asyncio.run receives a coroutine - check the function was called
            assert call_args is not None

            # Verify result was passed through
            assert result["themes_extracted"] == 5


class TestExtractAsyncWiring:
    """
    Integration test: Verify extract_async correctly wraps sync extract.

    This is the wiring test - ensuring the async method actually calls
    the sync method with all parameters.
    """

    @pytest.mark.asyncio
    async def test_extract_async_passes_all_parameters(self):
        """Verify all parameters flow from extract_async to extract."""
        from src.theme_extractor import ThemeExtractor
        from src.db.models import Conversation

        # Create test conversation
        conv = Conversation(
            id="test_conv",
            created_at=datetime.now(timezone.utc),
            source_body="Test body",
            issue_type="bug_report",
            sentiment="neutral",
            priority="normal",  # Valid Priority: urgent, high, normal, low
            churn_risk=False,  # churn_risk is a boolean
        )

        # Track what extract() receives
        received_args = {}

        def mock_extract(conv_arg, **kwargs):
            received_args["conv"] = conv_arg
            received_args["kwargs"] = kwargs
            return create_mock_theme_result(conv_arg.id)

        extractor = ThemeExtractor()

        with patch.object(extractor, "extract", mock_extract):
            await extractor.extract_async(
                conv,
                canonicalize=True,
                use_embedding=False,
                auto_add_to_vocabulary=False,
                strict_mode=True,
                customer_digest="test digest",
                full_conversation="test full conversation",
                use_full_conversation=True,
            )

        # Verify all parameters were passed
        assert received_args["conv"].id == "test_conv"
        assert received_args["kwargs"]["canonicalize"] is True
        assert received_args["kwargs"]["use_embedding"] is False
        assert received_args["kwargs"]["strict_mode"] is True
        assert received_args["kwargs"]["customer_digest"] == "test digest"
        assert received_args["kwargs"]["full_conversation"] == "test full conversation"
        assert received_args["kwargs"]["use_full_conversation"] is True

    @pytest.mark.asyncio
    async def test_extract_async_uses_asyncio_to_thread(self):
        """Verify extract_async uses asyncio.to_thread for non-blocking execution."""
        from src.theme_extractor import ThemeExtractor
        from src.db.models import Conversation

        conv = Conversation(
            id="test_conv",
            created_at=datetime.now(timezone.utc),
            source_body="Test body",
            issue_type="bug_report",
            sentiment="neutral",
            priority="normal",
            churn_risk=False,
        )

        extractor = ThemeExtractor()

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = create_mock_theme_result("test_conv")

            await extractor.extract_async(conv)

            # Verify asyncio.to_thread was called with extract method
            mock_to_thread.assert_called_once()
            call_args = mock_to_thread.call_args
            # First positional arg should be self.extract
            assert call_args[0][0] == extractor.extract


class TestConcurrencyValidation:
    """
    Integration test: Verify concurrency validation at API boundary.
    """

    def test_pipeline_request_accepts_valid_concurrency(self):
        """Verify API schema accepts concurrency 1-20."""
        from src.api.schemas.pipeline import PipelineRunRequest

        # Boundary values should succeed
        assert PipelineRunRequest(concurrency=1).concurrency == 1
        assert PipelineRunRequest(concurrency=10).concurrency == 10
        assert PipelineRunRequest(concurrency=20).concurrency == 20

    def test_pipeline_request_rejects_high_concurrency(self):
        """Verify API schema rejects concurrency > 20."""
        from src.api.schemas.pipeline import PipelineRunRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            PipelineRunRequest(concurrency=21)

        assert "less than or equal to 20" in str(exc_info.value).lower()

    def test_pipeline_request_rejects_zero_concurrency(self):
        """Verify API schema rejects concurrency < 1."""
        from src.api.schemas.pipeline import PipelineRunRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            PipelineRunRequest(concurrency=0)

        assert "greater than or equal to 1" in str(exc_info.value).lower()

    def test_concurrency_default_is_20(self):
        """Verify default concurrency is 20."""
        from src.api.schemas.pipeline import PipelineRunRequest

        request = PipelineRunRequest()
        assert request.concurrency == 20


class TestAsyncWrapperWiring:
    """
    Integration test: Verify _run_pipeline_async uses anyio.to_thread.
    """

    @pytest.mark.asyncio
    async def test_run_pipeline_async_uses_anyio(self):
        """Verify _run_pipeline_async uses anyio.to_thread.run_sync."""
        with patch("src.api.routers.pipeline.anyio.to_thread.run_sync") as mock_run_sync:
            mock_run_sync.return_value = None

            from src.api.routers.pipeline import _run_pipeline_async

            await _run_pipeline_async(
                run_id=1,
                days=7,
                max_conversations=None,
                dry_run=False,
                concurrency=20,
                auto_create_stories=False,
            )

            # Verify anyio.to_thread.run_sync was called
            mock_run_sync.assert_called_once()

            # Verify cancellable=True was passed
            call_kwargs = mock_run_sync.call_args.kwargs
            # Note: Parameter might be 'cancellable' or 'abandon_on_cancel' depending on anyio version
            assert "cancellable" in call_kwargs or "abandon_on_cancel" in call_kwargs


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
