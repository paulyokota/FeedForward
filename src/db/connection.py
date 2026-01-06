"""PostgreSQL database connection and operations."""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import Conversation, PipelineRun


def get_connection_string() -> str:
    """Get database connection string from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://localhost:5432/feedforward"
    )


@contextmanager
def get_connection() -> Generator:
    """Get a database connection context manager."""
    conn = psycopg2.connect(get_connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database schema."""
    schema_path = Path(__file__).parent / "schema.sql"
    with open(schema_path) as f:
        schema_sql = f.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)


def upsert_conversation(conv: Conversation) -> None:
    """Insert or update a conversation."""
    sql = """
    INSERT INTO conversations (
        id, created_at, classified_at,
        source_body, source_type, source_subject,
        contact_email, contact_id,
        issue_type, sentiment, churn_risk, priority,
        classifier_version, raw_response
    ) VALUES (
        %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        %s, %s, %s, %s,
        %s, %s
    )
    ON CONFLICT (id) DO UPDATE SET
        classified_at = EXCLUDED.classified_at,
        issue_type = EXCLUDED.issue_type,
        sentiment = EXCLUDED.sentiment,
        churn_risk = EXCLUDED.churn_risk,
        priority = EXCLUDED.priority,
        classifier_version = EXCLUDED.classifier_version,
        raw_response = EXCLUDED.raw_response
    """

    import json
    raw_response_json = json.dumps(conv.raw_response) if conv.raw_response else None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                conv.id, conv.created_at, conv.classified_at,
                conv.source_body, conv.source_type, conv.source_subject,
                conv.contact_email, conv.contact_id,
                conv.issue_type, conv.sentiment, conv.churn_risk, conv.priority,
                conv.classifier_version, raw_response_json
            ))


def bulk_upsert_conversations(conversations: list[Conversation]) -> int:
    """Bulk insert or update conversations. Returns count of rows affected."""
    if not conversations:
        return 0

    import json
    from psycopg2.extras import execute_values

    sql = """
    INSERT INTO conversations (
        id, created_at, classified_at,
        source_body, source_type, source_subject,
        contact_email, contact_id,
        issue_type, sentiment, churn_risk, priority,
        classifier_version, raw_response
    ) VALUES %s
    ON CONFLICT (id) DO UPDATE SET
        classified_at = EXCLUDED.classified_at,
        issue_type = EXCLUDED.issue_type,
        sentiment = EXCLUDED.sentiment,
        churn_risk = EXCLUDED.churn_risk,
        priority = EXCLUDED.priority,
        classifier_version = EXCLUDED.classifier_version,
        raw_response = EXCLUDED.raw_response
    """

    values = [
        (
            c.id, c.created_at, c.classified_at,
            c.source_body, c.source_type, c.source_subject,
            c.contact_email, c.contact_id,
            c.issue_type, c.sentiment, c.churn_risk, c.priority,
            c.classifier_version,
            json.dumps(c.raw_response) if c.raw_response else None
        )
        for c in conversations
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, values)
            return len(conversations)


def create_pipeline_run(run: PipelineRun) -> int:
    """Create a new pipeline run record. Returns the run ID."""
    sql = """
    INSERT INTO pipeline_runs (
        started_at, date_from, date_to, status
    ) VALUES (%s, %s, %s, %s)
    RETURNING id
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                run.started_at, run.date_from, run.date_to, run.status
            ))
            result = cur.fetchone()
            return result[0]


def update_pipeline_run(run: PipelineRun) -> None:
    """Update an existing pipeline run."""
    sql = """
    UPDATE pipeline_runs SET
        completed_at = %s,
        conversations_fetched = %s,
        conversations_filtered = %s,
        conversations_classified = %s,
        conversations_stored = %s,
        status = %s,
        error_message = %s
    WHERE id = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                run.completed_at,
                run.conversations_fetched,
                run.conversations_filtered,
                run.conversations_classified,
                run.conversations_stored,
                run.status,
                run.error_message,
                run.id
            ))


def get_conversation_count() -> int:
    """Get total conversation count."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM conversations")
            return cur.fetchone()[0]


def conversation_exists(conv_id: str) -> bool:
    """Check if a conversation already exists."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM conversations WHERE id = %s",
                (conv_id,)
            )
            return cur.fetchone() is not None
