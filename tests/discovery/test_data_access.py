"""Tests for the explorer data access layer.

Verifies that ConversationReader reads raw conversation text only,
handles null/empty fallback correctly, and excludes pipeline output.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.discovery.agents.data_access import ConversationReader, RawConversation


# ============================================================================
# Fixtures
# ============================================================================


def _make_row(**overrides) -> dict:
    """Create a mock DB row matching the SELECT columns."""
    base = {
        "conversation_id": "conv_001",
        "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "source_body": "I can't schedule posts",
        "full_conversation": "Customer: I can't schedule posts\nAgent: Can you describe...",
        "source_url": "https://app.example.com/scheduler",
        "used_fallback": False,
    }
    base.update(overrides)
    return base


class FakeCursor:
    """Minimal cursor mock that supports context manager and fetchall/fetchone."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed_query = None
        self.executed_params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=None):
        self.executed_query = query
        self.executed_params = params

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    """Minimal connection mock that returns a FakeCursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor


# ============================================================================
# fetch_conversations tests
# ============================================================================


class TestFetchConversations:
    def test_returns_raw_conversations(self):
        rows = [_make_row(), _make_row(conversation_id="conv_002")]
        cursor = FakeCursor(rows=rows)
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.fetch_conversations(days=14)

        assert len(result) == 2
        assert isinstance(result[0], RawConversation)
        assert result[0].conversation_id == "conv_001"
        assert result[1].conversation_id == "conv_002"

    def test_passes_days_parameter(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.fetch_conversations(days=7)

        assert cursor.executed_params[0] == 7

    def test_applies_limit(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.fetch_conversations(days=14, limit=50)

        assert cursor.executed_params == [14, 50]
        assert "LIMIT" in cursor.executed_query

    def test_no_limit_by_default(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.fetch_conversations(days=14)

        assert "LIMIT" not in cursor.executed_query

    def test_tracks_fallback_usage(self):
        rows = [
            _make_row(used_fallback=False),
            _make_row(conversation_id="conv_002", used_fallback=True,
                      full_conversation=None),
            _make_row(conversation_id="conv_003", used_fallback=True,
                      full_conversation=None),
        ]
        cursor = FakeCursor(rows=rows)
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.fetch_conversations(days=14)

        assert result[0].used_fallback is False
        assert result[1].used_fallback is True
        assert result[2].used_fallback is True

    def test_logs_warning_on_fallback(self, caplog):
        rows = [_make_row(used_fallback=True, full_conversation=None)]
        cursor = FakeCursor(rows=rows)
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        with caplog.at_level("WARNING"):
            reader.fetch_conversations(days=14)

        assert "source_body fallback" in caplog.text
        assert "1 of 1" in caplog.text

    def test_no_warning_when_no_fallback(self, caplog):
        rows = [_make_row(used_fallback=False)]
        cursor = FakeCursor(rows=rows)
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        with caplog.at_level("WARNING"):
            reader.fetch_conversations(days=14)

        assert "fallback" not in caplog.text

    def test_handles_empty_result(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.fetch_conversations(days=14)

        assert result == []

    def test_source_body_defaults_to_empty_string_when_none(self):
        rows = [_make_row(source_body=None)]
        cursor = FakeCursor(rows=rows)
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.fetch_conversations(days=14)

        assert result[0].source_body == ""

    def test_sql_excludes_pipeline_output(self):
        """Verify the query doesn't select classification or theme columns."""
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.fetch_conversations(days=14)

        query = cursor.executed_query.lower()
        # Must NOT select pipeline output columns
        assert "stage1_type" not in query
        assert "stage2_type" not in query
        assert "sentiment" not in query
        assert "issue_type" not in query
        assert "priority" not in query
        assert "churn_risk" not in query
        # Must NOT join to themes
        assert "themes" not in query

    def test_sql_uses_nullif_for_empty_string(self):
        """MF3: Verify NULLIF is used so empty string triggers fallback."""
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.fetch_conversations(days=14)

        assert "NULLIF" in cursor.executed_query


# ============================================================================
# fetch_conversation_by_id tests
# ============================================================================


class TestFetchConversationById:
    def test_returns_conversation(self):
        rows = [_make_row()]
        cursor = FakeCursor(rows=rows)
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.fetch_conversation_by_id("conv_001")

        assert result is not None
        assert result.conversation_id == "conv_001"
        assert result.full_conversation is not None

    def test_returns_none_when_not_found(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.fetch_conversation_by_id("conv_missing")

        assert result is None

    def test_passes_conversation_id(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.fetch_conversation_by_id("conv_123")

        assert cursor.executed_params == ("conv_123",)


# ============================================================================
# get_conversation_count tests
# ============================================================================


class TestGetConversationCount:
    def test_returns_count(self):
        cursor = FakeCursor(rows=[{"cnt": 42}])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.get_conversation_count(days=14)

        assert result == 42

    def test_passes_days_parameter(self):
        cursor = FakeCursor(rows=[{"cnt": 0}])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        reader.get_conversation_count(days=7)

        assert cursor.executed_params == (7,)

    def test_returns_zero_on_empty(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)
        reader = ConversationReader(conn)

        result = reader.get_conversation_count(days=14)

        assert result == 0
