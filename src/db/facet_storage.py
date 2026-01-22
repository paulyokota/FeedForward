"""
Database storage for conversation facets.

Stores facets in the conversation_facet table (migration 012).
Uses batch inserts for efficiency.
"""

import logging
from typing import List, Optional

from psycopg2.extras import execute_values

from src.db.connection import get_connection
from src.services.facet_service import FacetResult

logger = logging.getLogger(__name__)


def store_facet(
    conversation_id: str,
    action_type: str,
    direction: str,
    symptom: str,
    user_goal: str,
    pipeline_run_id: Optional[int] = None,
    model_version: str = "gpt-4o-mini",
) -> None:
    """
    Store a single conversation facet.

    Args:
        conversation_id: Conversation ID
        action_type: Extracted action type
        direction: Extracted direction
        symptom: Brief description of symptom (10 words max)
        user_goal: User's goal (10 words max)
        pipeline_run_id: Pipeline run ID for scoping
        model_version: Model used for extraction
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_facet (
                    conversation_id, pipeline_run_id, action_type, direction,
                    symptom, user_goal, model_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (conversation_id, pipeline_run_id) DO UPDATE SET
                    action_type = EXCLUDED.action_type,
                    direction = EXCLUDED.direction,
                    symptom = EXCLUDED.symptom,
                    user_goal = EXCLUDED.user_goal,
                    model_version = EXCLUDED.model_version,
                    created_at = NOW()
            """,
                (conversation_id, pipeline_run_id, action_type, direction,
                 symptom, user_goal, model_version),
            )
            conn.commit()


def store_facets_batch(
    results: List[FacetResult],
    pipeline_run_id: Optional[int] = None,
    model_version: str = "gpt-4o-mini",
) -> int:
    """
    Store multiple conversation facets in a single batch operation.

    ~50x faster than individual inserts for large batches.

    Args:
        results: List of FacetResult objects (only successful ones stored)
        pipeline_run_id: Pipeline run ID for scoping
        model_version: Model used for extraction

    Returns:
        Number of facets stored
    """
    # Filter to successful results only
    successful_results = [r for r in results if r.success]

    if not successful_results:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Prepare rows for batch insert
            rows = [
                (
                    result.conversation_id,
                    pipeline_run_id,
                    result.action_type,
                    result.direction,
                    result.symptom,
                    result.user_goal,
                    model_version,
                )
                for result in successful_results
            ]

            # Batch upsert
            sql = """
                INSERT INTO conversation_facet (
                    conversation_id, pipeline_run_id, action_type, direction,
                    symptom, user_goal, model_version
                ) VALUES %s
                ON CONFLICT (conversation_id, pipeline_run_id) DO UPDATE SET
                    action_type = EXCLUDED.action_type,
                    direction = EXCLUDED.direction,
                    symptom = EXCLUDED.symptom,
                    user_goal = EXCLUDED.user_goal,
                    model_version = EXCLUDED.model_version,
                    created_at = NOW()
            """

            execute_values(cur, sql, rows)
            conn.commit()

            logger.info(f"Stored {len(rows)} facets for run {pipeline_run_id}")
            return len(rows)


def get_facets_for_run(
    pipeline_run_id: int,
) -> List[dict]:
    """
    Get all facets for a pipeline run.

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        List of dicts with facet data
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id, action_type, direction, symptom, user_goal,
                       model_version, created_at
                FROM conversation_facet
                WHERE pipeline_run_id = %s
                ORDER BY conversation_id
            """,
                (pipeline_run_id,),
            )
            rows = cur.fetchall()

    return [
        {
            "conversation_id": row[0],
            "action_type": row[1],
            "direction": row[2],
            "symptom": row[3],
            "user_goal": row[4],
            "model_version": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def count_facets_for_run(pipeline_run_id: int) -> int:
    """
    Count facets for a pipeline run.

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        Number of facets
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM conversation_facet
                WHERE pipeline_run_id = %s
            """,
                (pipeline_run_id,),
            )
            result = cur.fetchone()
            return result[0] if result else 0
