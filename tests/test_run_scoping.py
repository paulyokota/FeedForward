"""
Tests for Issue #103: Pipeline Run Scoping

Verifies that conversations are correctly scoped to pipeline runs
using explicit pipeline_run_id instead of timestamp heuristics.

Run with: pytest tests/test_run_scoping.py -v
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


class TestStorageWithPipelineRunId:
    """Test that classification storage functions accept and use pipeline_run_id."""

    def test_store_classification_results_batch_accepts_pipeline_run_id(self):
        """store_classification_results_batch should accept pipeline_run_id parameter."""
        from src.db.classification_storage import store_classification_results_batch
        import inspect

        sig = inspect.signature(store_classification_results_batch)
        params = list(sig.parameters.keys())

        assert "pipeline_run_id" in params, (
            "store_classification_results_batch should accept pipeline_run_id parameter"
        )

    def test_store_classification_result_accepts_pipeline_run_id(self):
        """store_classification_result should accept pipeline_run_id parameter."""
        from src.db.classification_storage import store_classification_result
        import inspect

        sig = inspect.signature(store_classification_result)
        params = list(sig.parameters.keys())

        assert "pipeline_run_id" in params, (
            "store_classification_result should accept pipeline_run_id parameter"
        )


class TestPipelinePassesPipelineRunId:
    """Test that the pipeline functions accept and pass through pipeline_run_id."""

    def test_run_pipeline_async_accepts_pipeline_run_id(self):
        """run_pipeline_async should accept pipeline_run_id parameter."""
        from src.two_stage_pipeline import run_pipeline_async
        import inspect

        sig = inspect.signature(run_pipeline_async)
        params = list(sig.parameters.keys())

        assert "pipeline_run_id" in params, (
            "run_pipeline_async should accept pipeline_run_id parameter"
        )

    def test_run_pipeline_sync_accepts_pipeline_run_id(self):
        """run_pipeline should accept pipeline_run_id parameter."""
        from src.two_stage_pipeline import run_pipeline
        import inspect

        sig = inspect.signature(run_pipeline)
        params = list(sig.parameters.keys())

        assert "pipeline_run_id" in params, (
            "run_pipeline should accept pipeline_run_id parameter"
        )


class TestMigrationExists:
    """Test that the migration for pipeline_run_id exists."""

    def test_migration_010_exists(self):
        """Migration 010 should exist for conversation run scoping."""
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "src/db/migrations/010_conversation_run_scoping.sql"
        assert migration_path.exists(), (
            "Migration 010_conversation_run_scoping.sql should exist"
        )

    def test_migration_adds_pipeline_run_id_column(self):
        """Migration should add pipeline_run_id column to conversations."""
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "src/db/migrations/010_conversation_run_scoping.sql"
        content = migration_path.read_text()

        assert "pipeline_run_id" in content, (
            "Migration should reference pipeline_run_id"
        )
        assert "conversations" in content.lower(), (
            "Migration should reference conversations table"
        )


class TestThemeExtractionQueryUsesExplicitRunId:
    """Test that theme extraction uses pipeline_run_id instead of timestamp heuristic."""

    def test_theme_extraction_query_uses_pipeline_run_id(self):
        """
        The theme extraction query should use c.pipeline_run_id = %s
        instead of the broken timestamp heuristic JOIN.
        """
        from pathlib import Path

        pipeline_path = Path(__file__).parent.parent / "src/api/routers/pipeline.py"
        content = pipeline_path.read_text()

        # The fix should use explicit pipeline_run_id with timestamp fallback for NULL values
        # New conversations: WHERE c.pipeline_run_id = %s
        # Pre-migration conversations (NULL): OR (c.pipeline_run_id IS NULL AND c.classified_at >= pr.started_at)
        # This preserves backward compatibility while fixing run scoping for new runs.

        assert "c.pipeline_run_id = %s" in content, (
            "Theme extraction should query by c.pipeline_run_id for new conversations"
        )

        # The timestamp heuristic should now be used ONLY as fallback for NULL pipeline_run_id
        # Check that we have the NULL fallback pattern
        import re

        # Find the _run_theme_extraction function
        theme_func_match = re.search(
            r'def _run_theme_extraction\([^)]+\)[^:]*:.*?(?=\ndef |\Z)',
            content,
            re.DOTALL
        )
        if theme_func_match:
            theme_func_content = theme_func_match.group(0)
            # Should have explicit run_id check
            assert "c.pipeline_run_id = %s" in theme_func_content, (
                "Theme extraction should use explicit c.pipeline_run_id = %s"
            )
            # Should have NULL fallback for backward compatibility
            assert "c.pipeline_run_id IS NULL" in theme_func_content, (
                "Theme extraction should have NULL fallback for pre-migration conversations"
            )


class TestRunScopingIntegration:
    """
    Integration tests for run scoping.

    These tests verify the complete flow from pipeline execution
    to theme extraction uses proper run scoping.
    """

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually with DB")
    def test_conversations_linked_to_correct_run(self):
        """
        Conversations should be linked to their pipeline run via pipeline_run_id.

        This test:
        1. Creates a pipeline run
        2. Stores conversations with that run's ID
        3. Verifies conversations are retrievable by run ID
        """
        from src.db.connection import get_connection, create_pipeline_run
        from src.db.classification_storage import store_classification_results_batch
        from src.db.models import PipelineRun
        from datetime import datetime, timedelta

        # Create a test pipeline run
        run = PipelineRun(
            date_from=datetime.utcnow() - timedelta(days=1),
            date_to=datetime.utcnow(),
        )
        run_id = create_pipeline_run(run)

        # Create test classification results
        test_results = [
            {
                "conversation_id": f"test_run_scope_{run_id}_{i}",
                "created_at": datetime.utcnow(),
                "source_body": f"Test conversation {i}",
                "source_type": "conversation",
                "source_url": None,
                "contact_email": f"test{i}@example.com",
                "contact_id": f"contact_{i}",
                "stage1_result": {
                    "conversation_type": "product_issue",
                    "confidence": "high",
                    "routing_priority": "normal",
                },
                "stage2_result": None,
            }
            for i in range(3)
        ]

        # Store with pipeline_run_id
        stored = store_classification_results_batch(test_results, pipeline_run_id=run_id)
        assert stored == 3

        # Verify conversations are linked to the run
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM conversations
                    WHERE pipeline_run_id = %s
                """, (run_id,))
                count = cur.fetchone()[0]

        assert count == 3, f"Expected 3 conversations linked to run {run_id}, got {count}"

        # Cleanup
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE id LIKE %s",
                    (f"test_run_scope_{run_id}_%",)
                )
                cur.execute(
                    "DELETE FROM pipeline_runs WHERE id = %s",
                    (run_id,)
                )

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually with DB")
    def test_overlapping_runs_scoped_correctly(self):
        """
        Overlapping runs should not contaminate each other's conversation sets.

        This test:
        1. Creates two pipeline runs
        2. Stores conversations for each run
        3. Verifies each run only sees its own conversations
        """
        from src.db.connection import get_connection, create_pipeline_run
        from src.db.classification_storage import store_classification_results_batch
        from src.db.models import PipelineRun
        from datetime import datetime, timedelta

        # Create two pipeline runs (simulating overlap)
        run_a = PipelineRun(
            date_from=datetime.utcnow() - timedelta(days=1),
            date_to=datetime.utcnow(),
        )
        run_a_id = create_pipeline_run(run_a)

        run_b = PipelineRun(
            date_from=datetime.utcnow() - timedelta(days=1),
            date_to=datetime.utcnow(),
        )
        run_b_id = create_pipeline_run(run_b)

        # Store conversations for run A
        results_a = [
            {
                "conversation_id": f"test_overlap_a_{run_a_id}_{i}",
                "created_at": datetime.utcnow(),
                "source_body": f"Run A conversation {i}",
                "source_type": "conversation",
                "source_url": None,
                "contact_email": f"a{i}@example.com",
                "contact_id": f"contact_a_{i}",
                "stage1_result": {"conversation_type": "product_issue", "confidence": "high"},
                "stage2_result": None,
            }
            for i in range(3)
        ]
        store_classification_results_batch(results_a, pipeline_run_id=run_a_id)

        # Store conversations for run B
        results_b = [
            {
                "conversation_id": f"test_overlap_b_{run_b_id}_{i}",
                "created_at": datetime.utcnow(),
                "source_body": f"Run B conversation {i}",
                "source_type": "conversation",
                "source_url": None,
                "contact_email": f"b{i}@example.com",
                "contact_id": f"contact_b_{i}",
                "stage1_result": {"conversation_type": "feature_request", "confidence": "high"},
                "stage2_result": None,
            }
            for i in range(2)
        ]
        store_classification_results_batch(results_b, pipeline_run_id=run_b_id)

        # Verify run A only sees its conversations
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM conversations WHERE pipeline_run_id = %s
                """, (run_a_id,))
                count_a = cur.fetchone()[0]

                cur.execute("""
                    SELECT COUNT(*) FROM conversations WHERE pipeline_run_id = %s
                """, (run_b_id,))
                count_b = cur.fetchone()[0]

        assert count_a == 3, f"Run A should have 3 conversations, got {count_a}"
        assert count_b == 2, f"Run B should have 2 conversations, got {count_b}"

        # Cleanup
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE id LIKE 'test_overlap_%%'"
                )
                cur.execute(
                    "DELETE FROM pipeline_runs WHERE id IN (%s, %s)",
                    (run_a_id, run_b_id)
                )
