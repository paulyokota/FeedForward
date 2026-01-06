"""
Pipeline tests for Phase 2.

Run with: pytest tests/test_pipeline.py -v
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from intercom_client import IntercomClient, IntercomConversation, QualityFilterResult
from db.models import Conversation, PipelineRun, ClassificationResult


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_quality_conversation():
    """A conversation that should pass quality filter."""
    return {
        "id": "123456",
        "created_at": int(datetime.utcnow().timestamp()),
        "source": {
            "type": "conversation",
            "delivered_as": "customer_initiated",
            "body": "<p>I'm having trouble with my scheduled pins not posting correctly. They show as scheduled but never go live.</p>",
            "author": {
                "type": "user",
                "id": "user_abc",
                "email": "customer@example.com",
            },
        },
    }


@pytest.fixture
def sample_admin_conversation():
    """A conversation initiated by admin (should be filtered)."""
    return {
        "id": "123457",
        "created_at": int(datetime.utcnow().timestamp()),
        "source": {
            "type": "conversation",
            "delivered_as": "admin_initiated",
            "body": "<p>Hi! Just checking in to see how you're doing with Tailwind.</p>",
            "author": {
                "type": "admin",
                "id": "admin_xyz",
            },
        },
    }


@pytest.fixture
def sample_template_conversation():
    """A template click (should be filtered)."""
    return {
        "id": "123458",
        "created_at": int(datetime.utcnow().timestamp()),
        "source": {
            "type": "conversation",
            "delivered_as": "customer_initiated",
            "body": "I have a product question or feedback",
            "author": {
                "type": "user",
                "id": "user_def",
            },
        },
    }


@pytest.fixture
def sample_short_conversation():
    """A message too short to classify."""
    return {
        "id": "123459",
        "created_at": int(datetime.utcnow().timestamp()),
        "source": {
            "type": "conversation",
            "delivered_as": "customer_initiated",
            "body": "hi",
            "author": {
                "type": "user",
                "id": "user_ghi",
            },
        },
    }


# -----------------------------------------------------------------------------
# Quality Filter Tests
# -----------------------------------------------------------------------------

class TestQualityFilter:
    """Test the quality filtering logic."""

    def test_passes_quality_conversation(self, sample_quality_conversation):
        """Quality customer conversation should pass."""
        client = IntercomClient.__new__(IntercomClient)
        client.TEMPLATE_MESSAGES = IntercomClient.TEMPLATE_MESSAGES

        result = client.quality_filter(sample_quality_conversation)

        assert result.passed is True
        assert result.reason is None

    def test_filters_admin_initiated(self, sample_admin_conversation):
        """Admin-initiated conversations should be filtered."""
        client = IntercomClient.__new__(IntercomClient)

        result = client.quality_filter(sample_admin_conversation)

        assert result.passed is False
        assert "admin_initiated" in result.reason

    def test_filters_template_clicks(self, sample_template_conversation):
        """Template clicks should be filtered."""
        client = IntercomClient.__new__(IntercomClient)
        client.TEMPLATE_MESSAGES = IntercomClient.TEMPLATE_MESSAGES

        result = client.quality_filter(sample_template_conversation)

        assert result.passed is False
        assert "template" in result.reason

    def test_filters_short_messages(self, sample_short_conversation):
        """Messages under 20 chars should be filtered."""
        client = IntercomClient.__new__(IntercomClient)
        client.TEMPLATE_MESSAGES = IntercomClient.TEMPLATE_MESSAGES

        result = client.quality_filter(sample_short_conversation)

        assert result.passed is False
        assert "too short" in result.reason or "template" in result.reason

    def test_filter_ratio_approximately_50_percent(self):
        """Roughly 50% of conversations should be filtered based on Phase 1 analysis."""
        # This is a documentation test - actual ratio depends on data
        # We validated ~48% filter rate in Phase 1
        pass


# -----------------------------------------------------------------------------
# HTML Stripping Tests
# -----------------------------------------------------------------------------

class TestHtmlStripping:
    """Test HTML stripping utility."""

    def test_strips_html_tags(self):
        """Should remove HTML tags."""
        html = "<p>Hello <strong>world</strong></p>"
        result = IntercomClient.strip_html(html)
        assert result == "Hello world"

    def test_decodes_entities(self):
        """Should decode HTML entities."""
        html = "Hello &amp; goodbye"
        result = IntercomClient.strip_html(html)
        assert result == "Hello & goodbye"

    def test_normalizes_whitespace(self):
        """Should normalize whitespace."""
        html = "<p>Hello</p>   <p>world</p>"
        result = IntercomClient.strip_html(html)
        assert result == "Hello world"

    def test_handles_empty_input(self):
        """Should handle empty/None input."""
        assert IntercomClient.strip_html("") == ""
        assert IntercomClient.strip_html(None) == ""


# -----------------------------------------------------------------------------
# Conversation Parsing Tests
# -----------------------------------------------------------------------------

class TestConversationParsing:
    """Test parsing raw Intercom data to our model."""

    def test_parses_conversation(self, sample_quality_conversation):
        """Should parse all fields correctly."""
        client = IntercomClient.__new__(IntercomClient)

        result = client.parse_conversation(sample_quality_conversation)

        assert isinstance(result, IntercomConversation)
        assert result.id == "123456"
        assert "scheduled pins" in result.source_body
        assert result.contact_email == "customer@example.com"


# -----------------------------------------------------------------------------
# Database Model Tests
# -----------------------------------------------------------------------------

class TestDatabaseModels:
    """Test Pydantic models."""

    def test_conversation_model_valid(self):
        """Should accept valid data."""
        conv = Conversation(
            id="test_123",
            created_at=datetime.utcnow(),
            source_body="Test message",
            issue_type="bug_report",
            sentiment="frustrated",
            churn_risk=False,
            priority="normal",
        )
        assert conv.id == "test_123"
        assert conv.issue_type == "bug_report"

    def test_conversation_model_invalid_issue_type(self):
        """Should reject invalid issue type."""
        with pytest.raises(ValueError):
            Conversation(
                id="test_123",
                created_at=datetime.utcnow(),
                issue_type="invalid_type",  # Not in allowed list
                sentiment="neutral",
                churn_risk=False,
                priority="normal",
            )

    def test_pipeline_run_model(self):
        """Should create valid pipeline run."""
        run = PipelineRun(
            date_from=datetime.utcnow() - timedelta(days=7),
            date_to=datetime.utcnow(),
        )
        assert run.status == "running"
        assert run.conversations_fetched == 0


# -----------------------------------------------------------------------------
# Integration Tests (require database)
# -----------------------------------------------------------------------------

class TestPipelineIntegration:
    """Integration tests that require PostgreSQL.

    These are marked to skip if database is not available.
    Run with: pytest tests/test_pipeline.py -v -m integration
    """

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually")
    def test_init_db(self):
        """Should initialize database schema."""
        from db.connection import init_db, get_connection

        init_db()

        # Verify tables exist
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                tables = [row[0] for row in cur.fetchall()]

        assert "conversations" in tables
        assert "pipeline_runs" in tables

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually")
    def test_upsert_conversation(self):
        """Should insert and update conversations."""
        from db.connection import init_db, upsert_conversation, get_connection

        init_db()

        conv = Conversation(
            id="test_upsert_123",
            created_at=datetime.utcnow(),
            source_body="Test message",
            issue_type="bug_report",
            sentiment="neutral",
            churn_risk=False,
            priority="normal",
        )

        # Insert
        upsert_conversation(conv)

        # Update
        conv.sentiment = "frustrated"
        upsert_conversation(conv)

        # Verify
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sentiment FROM conversations WHERE id = %s",
                    (conv.id,)
                )
                result = cur.fetchone()

        assert result[0] == "frustrated"

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually")
    def test_idempotency(self):
        """Running pipeline twice should not create duplicates."""
        from db.connection import init_db, bulk_upsert_conversations, get_conversation_count

        init_db()

        conversations = [
            Conversation(
                id=f"test_idem_{i}",
                created_at=datetime.utcnow(),
                source_body=f"Test message {i}",
                issue_type="bug_report",
                sentiment="neutral",
                churn_risk=False,
                priority="normal",
            )
            for i in range(5)
        ]

        # First insert
        bulk_upsert_conversations(conversations)
        count1 = get_conversation_count()

        # Second insert (same data)
        bulk_upsert_conversations(conversations)
        count2 = get_conversation_count()

        # Count should not increase
        assert count2 == count1


# -----------------------------------------------------------------------------
# Pipeline Dry Run Test
# -----------------------------------------------------------------------------

class TestPipelineDryRun:
    """Test pipeline without database."""

    @pytest.mark.skip(reason="Requires Intercom API - run manually")
    def test_dry_run_fetches_and_classifies(self):
        """Dry run should fetch and classify without storing."""
        from pipeline import run_pipeline

        run = run_pipeline(days=1, dry_run=True, max_conversations=5)

        assert run.status == "completed"
        assert run.conversations_fetched > 0
        assert run.conversations_stored == 0  # Dry run


# -----------------------------------------------------------------------------
# Performance Test
# -----------------------------------------------------------------------------

class TestPerformance:
    """Performance benchmarks."""

    @pytest.mark.skip(reason="Requires full setup - run manually")
    def test_pipeline_completes_in_5_minutes(self):
        """Pipeline should complete 100 conversations in < 5 minutes."""
        import time
        from pipeline import run_pipeline

        start = time.time()
        run = run_pipeline(days=30, dry_run=True, max_conversations=100)
        elapsed = time.time() - start

        assert elapsed < 300, f"Pipeline took {elapsed:.0f}s, exceeds 5 minute limit"
        assert run.conversations_classified == 100
