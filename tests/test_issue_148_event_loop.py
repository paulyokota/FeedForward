"""
Tests for Issue #148: Event Loop Blocking During Theme Extraction

Tests the async/parallel implementation that prevents event loop blocking:
1. _run_pipeline_async() - Wraps sync pipeline execution in thread pool
2. _run_theme_extraction_async() - Parallel theme extraction with semaphore control
3. ThemeExtractor.extract_async() - Async wrapper for sync extract()
4. Concurrency validation - Schema validation for rate limit compliance

Issue #148: The pipeline previously blocked the event loop for 40-80+ minutes
during theme extraction (500+ sequential OpenAI calls). These tests verify
that the new implementation:
- Runs blocking work in thread pools (anyio.to_thread.run_sync)
- Parallelizes theme extraction with semaphore-controlled concurrency
- Keeps the FastAPI event loop responsive during long-running operations

Run with: pytest tests/test_issue_148_event_loop.py -v
"""

import pytest
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.db.models import Conversation
from src.api.schemas.pipeline import PipelineRunRequest
from pydantic import ValidationError

# Mark entire module as slow - these are integration tests
pytestmark = pytest.mark.slow


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_conversations():
    """Sample conversations for theme extraction tests."""
    return [
        Conversation(
            id=f"conv_{i:03d}",
            created_at=datetime.now(timezone.utc),
            source_body=f"Test conversation {i} about login issues",
            issue_type="bug_report",
            sentiment="frustrated",
            priority="high",
            churn_risk=False,
        )
        for i in range(5)
    ]


@pytest.fixture
def mock_theme():
    """Mock theme object returned by extractor."""
    theme = Mock()
    theme.issue_signature = "test_signature"
    theme.product_area = "authentication"
    theme.component = "login"
    theme.matched_existing = False
    theme.match_confidence = "high"
    theme.user_intent = "Test intent"
    theme.symptoms = "Test symptoms"
    theme.affected_flow = "Test flow"
    theme.root_cause_hypothesis = "Test hypothesis"
    theme.diagnostic_summary = "Test summary"
    theme.key_excerpts = []
    theme.resolution_action = None
    theme.root_cause = None
    theme.solution_provided = None
    theme.resolution_category = None
    return theme


@pytest.fixture
def mock_db():
    """Mock database connection."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = None
    mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
    return mock_conn


# -----------------------------------------------------------------------------
# _run_pipeline_async Tests
# -----------------------------------------------------------------------------


class TestRunPipelineAsync:
    """Tests for _run_pipeline_async() thread pool wrapper."""

    @pytest.mark.asyncio
    async def test_runs_sync_function_in_thread_pool(self):
        """Test that _run_pipeline_async executes sync function in thread pool."""
        import src.api.routers.pipeline as pipeline_module

        # Mock the sync _run_pipeline_task
        with patch.object(
            pipeline_module, "_run_pipeline_task", return_value=None
        ) as mock_task:
            # Run async wrapper
            await pipeline_module._run_pipeline_async(
                run_id=1,
                days=7,
                max_conversations=10,
                dry_run=True,
                concurrency=5,
                auto_create_stories=False,
            )

            # Verify sync function was called with correct args
            mock_task.assert_called_once_with(
                run_id=1,
                days=7,
                max_conversations=10,
                dry_run=True,
                concurrency=5,
                auto_create_stories=False,
            )

    @pytest.mark.asyncio
    async def test_does_not_block_event_loop(self):
        """Test that async wrapper allows event loop to continue."""
        import src.api.routers.pipeline as pipeline_module

        # Track whether event loop was responsive during execution
        event_loop_ticks = []

        async def tick_counter():
            """Count event loop ticks during pipeline execution."""
            for i in range(10):
                event_loop_ticks.append(i)
                await asyncio.sleep(0.01)  # 10ms between ticks

        def slow_pipeline_task(*args, **kwargs):
            """Simulate slow pipeline execution."""
            import time
            time.sleep(0.1)  # 100ms blocking operation

        with patch.object(
            pipeline_module, "_run_pipeline_task", side_effect=slow_pipeline_task
        ):
            # Run pipeline and tick counter concurrently
            await asyncio.gather(
                pipeline_module._run_pipeline_async(
                    run_id=1,
                    days=7,
                    max_conversations=10,
                    dry_run=True,
                    concurrency=5,
                    auto_create_stories=False,
                ),
                tick_counter(),
            )

            # Event loop should have ticked multiple times during pipeline execution
            # If the pipeline blocked, we'd have 0-1 ticks
            assert len(event_loop_ticks) >= 5, (
                f"Event loop only ticked {len(event_loop_ticks)} times, "
                "suggesting it was blocked"
            )

    @pytest.mark.asyncio
    async def test_propagates_exceptions_from_sync_task(self):
        """Test that exceptions from sync task are propagated."""
        import src.api.routers.pipeline as pipeline_module

        def failing_task(*args, **kwargs):
            raise ValueError("Pipeline failed")

        with patch.object(
            pipeline_module, "_run_pipeline_task", side_effect=failing_task
        ):
            with pytest.raises(ValueError, match="Pipeline failed"):
                await pipeline_module._run_pipeline_async(
                    run_id=1,
                    days=7,
                    max_conversations=10,
                    dry_run=True,
                    concurrency=5,
                    auto_create_stories=False,
                )


# -----------------------------------------------------------------------------
# _run_theme_extraction_async Tests
# -----------------------------------------------------------------------------


class TestRunThemeExtractionAsync:
    """Tests for _run_theme_extraction_async() with semaphore control."""

    @pytest.mark.asyncio
    async def test_respects_concurrency_limit(self, sample_conversations, mock_theme):
        """Test that semaphore limits concurrent extractions."""
        import src.api.routers.pipeline as pipeline_module

        # Track concurrent executions
        active_count = 0
        max_active = 0
        lock = asyncio.Lock()

        async def mock_extract_async(*args, **kwargs):
            """Mock extract that tracks concurrency."""
            nonlocal active_count, max_active

            async with lock:
                active_count += 1
                max_active = max(max_active, active_count)

            await asyncio.sleep(0.05)  # Simulate work

            async with lock:
                active_count -= 1

            return mock_theme

        # Mock database to return sample conversations
        mock_rows = [
            {
                "id": conv.id,
                "created_at": conv.created_at,
                "source_body": conv.source_body,
                "source_url": None,
                "issue_type": "product_issue",
                "sentiment": conv.sentiment,
                "priority": conv.priority,
                "churn_risk": conv.churn_risk,
                "customer_digest": None,
                "full_conversation": None,
            }
            for conv in sample_conversations
        ]

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_conn.encoding = "UTF8"  # For psycopg2 execute_values
            mock_cursor = Mock()
            mock_cursor.connection = mock_conn
            mock_cursor.fetchall.return_value = mock_rows
            mock_cursor.fetchone.return_value = [123]  # theme_id from INSERT RETURNING
            mock_cursor.execute = Mock()  # Prevent actual SQL execution
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            with patch(
                "src.theme_extractor.ThemeExtractor"
            ) as mock_extractor_class:
                mock_extractor = Mock()
                mock_extractor.extract_async = mock_extract_async
                mock_extractor.clear_session_signatures = Mock()
                mock_extractor.get_existing_signatures = Mock(return_value=[])
                mock_extractor_class.return_value = mock_extractor

                with patch(
                    "src.theme_quality.filter_themes_by_quality"
                ) as mock_filter:
                    mock_filter.return_value = ([mock_theme] * 5, [], [])

                    # Mock check_theme_quality to avoid QualityCheckResult issues
                    mock_quality_result = Mock()
                    mock_quality_result.quality_score = 0.8
                    mock_quality_result.to_dict = Mock(return_value={})
                    with patch(
                        "src.theme_quality.check_theme_quality",
                        return_value=mock_quality_result
                    ):
                        with patch("src.utils.normalize.normalize_product_area", return_value="test"):
                            with patch("src.utils.normalize.canonicalize_component", return_value="test"):
                                # Mock execute_values to avoid psycopg2 internals
                                with patch("psycopg2.extras.execute_values"):
                                    # Set concurrency to 2
                                    concurrency = 2
                                    stop_checker = lambda: False

                                    result = await pipeline_module._run_theme_extraction_async(
                                        run_id=1, stop_checker=stop_checker, concurrency=concurrency
                                    )

                                    # Max concurrent should not exceed concurrency limit
                                    assert max_active <= concurrency, (
                                        f"Concurrency limit violated: {max_active} > {concurrency}"
                                    )

    @pytest.mark.asyncio
    async def test_processes_all_conversations_in_parallel(
        self, sample_conversations, mock_theme
    ):
        """Test that all conversations are processed (not sequential)."""
        import src.api.routers.pipeline as pipeline_module
        import time

        call_times = []

        async def mock_extract_async(*args, **kwargs):
            """Mock extract that records call time."""
            call_times.append(time.time())
            await asyncio.sleep(0.01)  # Small delay
            return mock_theme

        # Mock database
        mock_rows = [
            {
                "id": conv.id,
                "created_at": conv.created_at,
                "source_body": conv.source_body,
                "source_url": None,
                "issue_type": "product_issue",
                "sentiment": conv.sentiment,
                "priority": conv.priority,
                "churn_risk": conv.churn_risk,
                "customer_digest": None,
                "full_conversation": None,
            }
            for conv in sample_conversations
        ]

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_conn.encoding = "UTF8"  # For psycopg2 execute_values
            mock_cursor = Mock()
            mock_cursor.connection = mock_conn
            mock_cursor.fetchall.return_value = mock_rows
            mock_cursor.fetchone.return_value = [123]  # theme_id from INSERT RETURNING
            mock_cursor.execute = Mock()  # Prevent actual SQL execution
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            with patch(
                "src.theme_extractor.ThemeExtractor"
            ) as mock_extractor_class:
                mock_extractor = Mock()
                mock_extractor.extract_async = mock_extract_async
                mock_extractor.clear_session_signatures = Mock()
                mock_extractor.get_existing_signatures = Mock(return_value=[])
                mock_extractor_class.return_value = mock_extractor

                with patch(
                    "src.theme_quality.filter_themes_by_quality"
                ) as mock_filter:
                    mock_filter.return_value = ([mock_theme] * 5, [], [])

                    # Mock check_theme_quality
                    mock_quality_result = Mock()
                    mock_quality_result.quality_score = 0.8
                    mock_quality_result.to_dict = Mock(return_value={})
                    with patch(
                        "src.theme_quality.check_theme_quality",
                        return_value=mock_quality_result
                    ):
                        with patch("src.utils.normalize.normalize_product_area", return_value="test"):
                            with patch("src.utils.normalize.canonicalize_component", return_value="test"):
                                with patch("psycopg2.extras.execute_values"):
                                    stop_checker = lambda: False

                                    result = await pipeline_module._run_theme_extraction_async(
                                        run_id=1, stop_checker=stop_checker, concurrency=5
                                    )

                                    # Verify all 5 conversations were processed
                                    assert len(call_times) == 5

                                    # Verify they started in parallel (within 100ms window)
                                    # If sequential, they'd be 10ms+ apart
                                    time_spread = max(call_times) - min(call_times)
                                    assert time_spread < 0.1, (
                                        f"Extractions appear sequential: {time_spread:.3f}s spread"
                                    )

    @pytest.mark.asyncio
    async def test_respects_stop_signal_during_extraction(
        self, sample_conversations, mock_theme
    ):
        """Test that extraction stops when stop_checker returns True."""
        import src.api.routers.pipeline as pipeline_module

        call_count = 0

        async def mock_extract_async(*args, **kwargs):
            """Mock extract that counts calls."""
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return mock_theme

        # Stop after first extraction starts
        stop_after = 2
        call_tracker = {"count": 0}

        def stop_checker():
            call_tracker["count"] += 1
            return call_tracker["count"] > stop_after

        # Mock database
        mock_rows = [
            {
                "id": conv.id,
                "created_at": conv.created_at,
                "source_body": conv.source_body,
                "source_url": None,
                "issue_type": "product_issue",
                "sentiment": conv.sentiment,
                "priority": conv.priority,
                "churn_risk": conv.churn_risk,
                "customer_digest": None,
                "full_conversation": None,
            }
            for conv in sample_conversations
        ]

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_conn.encoding = "UTF8"  # For psycopg2 execute_values
            mock_cursor = Mock()
            mock_cursor.connection = mock_conn
            mock_cursor.fetchall.return_value = mock_rows
            mock_cursor.fetchone.return_value = [123]  # theme_id from INSERT RETURNING
            mock_cursor.execute = Mock()  # Prevent actual SQL execution
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            with patch(
                "src.theme_extractor.ThemeExtractor"
            ) as mock_extractor_class:
                mock_extractor = Mock()
                mock_extractor.extract_async = mock_extract_async
                mock_extractor.clear_session_signatures = Mock()
                mock_extractor_class.return_value = mock_extractor

                result = await pipeline_module._run_theme_extraction_async(
                    run_id=1, stop_checker=stop_checker, concurrency=5
                )

                # Should have stopped early
                assert result["themes_extracted"] == 0

    @pytest.mark.asyncio
    async def test_handles_extraction_failures_gracefully(
        self, sample_conversations, mock_theme
    ):
        """Test that extraction failures don't crash the entire process."""
        import src.api.routers.pipeline as pipeline_module

        call_count = 0

        async def mock_extract_async(*args, **kwargs):
            """Mock extract that fails on some conversations."""
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ValueError("Extraction failed")
            await asyncio.sleep(0.01)
            return mock_theme

        # Mock database
        mock_rows = [
            {
                "id": conv.id,
                "created_at": conv.created_at,
                "source_body": conv.source_body,
                "source_url": None,
                "issue_type": "product_issue",
                "sentiment": conv.sentiment,
                "priority": conv.priority,
                "churn_risk": conv.churn_risk,
                "customer_digest": None,
                "full_conversation": None,
            }
            for conv in sample_conversations
        ]

        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_conn.encoding = "UTF8"  # For psycopg2 execute_values
            mock_cursor = Mock()
            mock_cursor.connection = mock_conn
            mock_cursor.fetchall.return_value = mock_rows
            mock_cursor.fetchone.return_value = [123]  # theme_id from INSERT RETURNING
            mock_cursor.execute = Mock()  # Prevent actual SQL execution
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            with patch(
                "src.theme_extractor.ThemeExtractor"
            ) as mock_extractor_class:
                mock_extractor = Mock()
                mock_extractor.extract_async = mock_extract_async
                mock_extractor.clear_session_signatures = Mock()
                mock_extractor.get_existing_signatures = Mock(return_value=[])
                mock_extractor_class.return_value = mock_extractor

                with patch(
                    "src.theme_quality.filter_themes_by_quality"
                ) as mock_filter:
                    # Only 3 succeed (5 conversations, 2 fail)
                    mock_filter.return_value = ([mock_theme] * 3, [], [])

                    # Mock check_theme_quality
                    mock_quality_result = Mock()
                    mock_quality_result.quality_score = 0.8
                    mock_quality_result.to_dict = Mock(return_value={})
                    with patch(
                        "src.theme_quality.check_theme_quality",
                        return_value=mock_quality_result
                    ):
                        with patch("src.utils.normalize.normalize_product_area", return_value="test"):
                            with patch("src.utils.normalize.canonicalize_component", return_value="test"):
                                with patch("psycopg2.extras.execute_values"):
                                    stop_checker = lambda: False

                                    result = await pipeline_module._run_theme_extraction_async(
                                        run_id=1, stop_checker=stop_checker, concurrency=5
                                    )

                                    # Should complete with partial results
                                    # (exact count depends on filter, but should not crash)
                                    assert isinstance(result, dict)
                                    assert "themes_extracted" in result

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_conversations(self):
        """Test that function returns zero counts when no conversations to process."""
        import src.api.routers.pipeline as pipeline_module

        # Mock database to return empty result set
        with patch("src.db.connection.get_connection") as mock_get_conn:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            mock_get_conn.return_value.__enter__ = Mock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = Mock(return_value=False)

            stop_checker = lambda: False

            result = await pipeline_module._run_theme_extraction_async(
                run_id=1, stop_checker=stop_checker, concurrency=5
            )

            assert result["themes_extracted"] == 0
            assert result["themes_new"] == 0
            assert result["themes_filtered"] == 0


# -----------------------------------------------------------------------------
# ThemeExtractor.extract_async Tests
# -----------------------------------------------------------------------------


class TestThemeExtractorExtractAsync:
    """Tests for ThemeExtractor.extract_async() wrapper."""

    @pytest.mark.asyncio
    async def test_delegates_to_sync_extract(self):
        """Test that extract_async calls sync extract() with correct args."""
        from src.theme_extractor import ThemeExtractor

        extractor = ThemeExtractor()

        conv = Conversation(
            id="test_conv",
            created_at=datetime.now(timezone.utc),
            source_body="Test message about login issues",
            issue_type="bug_report",
            sentiment="neutral",
            priority="normal",
            churn_risk=False,
        )

        mock_theme = Mock()

        with patch.object(extractor, "extract", return_value=mock_theme) as mock_extract:
            result = await extractor.extract_async(
                conv,
                canonicalize=True,
                use_embedding=False,
                auto_add_to_vocabulary=False,
                strict_mode=True,
                customer_digest="Test digest",
                full_conversation="Full conversation text",
                use_full_conversation=True,
            )

            # Verify sync extract was called with all args
            mock_extract.assert_called_once_with(
                conv,
                canonicalize=True,
                use_embedding=False,
                auto_add_to_vocabulary=False,
                strict_mode=True,
                customer_digest="Test digest",
                full_conversation="Full conversation text",
                use_full_conversation=True,
            )

            # Verify result is returned
            assert result == mock_theme

    @pytest.mark.asyncio
    async def test_runs_in_thread_pool_not_blocking(self):
        """Test that extract_async doesn't block event loop."""
        from src.theme_extractor import ThemeExtractor

        extractor = ThemeExtractor()

        conv = Conversation(
            id="test_conv",
            created_at=datetime.now(timezone.utc),
            source_body="Test message",
            issue_type="bug_report",
            sentiment="neutral",
            priority="normal",
            churn_risk=False,
        )

        # Track event loop responsiveness
        event_loop_ticks = []

        async def tick_counter():
            """Count event loop ticks."""
            for i in range(10):
                event_loop_ticks.append(i)
                await asyncio.sleep(0.01)

        def slow_extract(*args, **kwargs):
            """Simulate slow extraction."""
            import time
            time.sleep(0.1)
            return Mock()

        with patch.object(extractor, "extract", side_effect=slow_extract):
            # Run extraction and tick counter concurrently
            await asyncio.gather(
                extractor.extract_async(conv),
                tick_counter(),
            )

            # Event loop should have remained responsive
            assert len(event_loop_ticks) >= 5, (
                f"Event loop only ticked {len(event_loop_ticks)} times"
            )

    @pytest.mark.asyncio
    async def test_propagates_exceptions_from_sync_extract(self):
        """Test that exceptions from sync extract are propagated."""
        from src.theme_extractor import ThemeExtractor

        extractor = ThemeExtractor()

        conv = Conversation(
            id="test_conv",
            created_at=datetime.now(timezone.utc),
            source_body="Test message",
            issue_type="bug_report",
            sentiment="neutral",
            priority="normal",
            churn_risk=False,
        )

        def failing_extract(*args, **kwargs):
            raise ValueError("Extraction failed")

        with patch.object(extractor, "extract", side_effect=failing_extract):
            with pytest.raises(ValueError, match="Extraction failed"):
                await extractor.extract_async(conv)


# -----------------------------------------------------------------------------
# Concurrency Validation Tests
# -----------------------------------------------------------------------------


class TestConcurrencyValidation:
    """Tests for concurrency validation in PipelineRunRequest schema."""

    def test_accepts_valid_concurrency_values(self):
        """Test that valid concurrency values (1-20) are accepted."""
        # Test minimum
        request = PipelineRunRequest(concurrency=1)
        assert request.concurrency == 1

        # Test maximum
        request = PipelineRunRequest(concurrency=20)
        assert request.concurrency == 20

        # Test middle value
        request = PipelineRunRequest(concurrency=10)
        assert request.concurrency == 10

    def test_rejects_concurrency_above_20(self):
        """Test that concurrency > 20 is rejected (OpenAI rate limit)."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineRunRequest(concurrency=21)

        error = exc_info.value.errors()[0]
        assert error["loc"] == ("concurrency",)
        assert "less than or equal to 20" in error["msg"]

    def test_rejects_concurrency_below_1(self):
        """Test that concurrency < 1 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineRunRequest(concurrency=0)

        error = exc_info.value.errors()[0]
        assert error["loc"] == ("concurrency",)
        assert "greater than or equal to 1" in error["msg"]

    def test_defaults_to_20(self):
        """Test that concurrency defaults to 20."""
        request = PipelineRunRequest()
        assert request.concurrency == 20

    def test_rejects_negative_concurrency(self):
        """Test that negative concurrency is rejected."""
        with pytest.raises(ValidationError):
            PipelineRunRequest(concurrency=-5)


# -----------------------------------------------------------------------------
# Integration Test: Full Async Flow
# -----------------------------------------------------------------------------


class TestAsyncFlowIntegration:
    """Integration tests for the complete async flow."""

    @pytest.mark.asyncio
    async def test_pipeline_task_calls_asyncio_run_for_theme_extraction(self):
        """Test that _run_theme_extraction calls asyncio.run for async implementation."""
        import src.api.routers.pipeline as pipeline_module

        # Track whether asyncio.run was called
        asyncio_run_called = False
        original_asyncio_run = asyncio.run

        def mock_asyncio_run(*args, **kwargs):
            nonlocal asyncio_run_called
            asyncio_run_called = True
            # Return empty result instead of running the actual async function
            return {"themes_extracted": 0, "themes_new": 0, "themes_filtered": 0, "warnings": []}

        with patch("asyncio.run", side_effect=mock_asyncio_run):
            stop_checker = lambda: False
            result = pipeline_module._run_theme_extraction(
                run_id=1,
                stop_checker=stop_checker,
                concurrency=5
            )

            # Verify asyncio.run was called (wrapping async function)
            assert asyncio_run_called, "_run_theme_extraction should use asyncio.run"
            assert result["themes_extracted"] == 0
