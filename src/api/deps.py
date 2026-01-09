"""
FastAPI Dependency Injection

Provides database connections and other shared dependencies
for API endpoints using FastAPI's dependency injection system.
"""

from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extras import RealDictCursor

from src.db.connection import get_connection_string


def get_db() -> Generator:
    """
    FastAPI dependency for database connections.

    Yields a database connection with RealDictCursor for dict-style row access.
    Automatically commits on success, rolls back on error, and closes connection.

    Usage in endpoints:
        @router.get("/items")
        def list_items(db = Depends(get_db)):
            with db.cursor() as cur:
                cur.execute("SELECT * FROM items")
                return cur.fetchall()
    """
    conn = psycopg2.connect(
        get_connection_string(),
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_cursor() -> Generator:
    """
    FastAPI dependency that yields a cursor directly.

    Convenience wrapper when you just need cursor access.

    Usage:
        @router.get("/count")
        def get_count(cursor = Depends(get_db_cursor)):
            cursor.execute("SELECT COUNT(*) FROM items")
            return cursor.fetchone()
    """
    conn = psycopg2.connect(
        get_connection_string(),
        cursor_factory=RealDictCursor
    )
    try:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
