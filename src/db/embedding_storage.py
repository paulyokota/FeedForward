"""
Database storage for conversation embeddings.

Stores embeddings in the conversation_embeddings table (migration 012).
Uses batch inserts for efficiency.
"""

import logging
from datetime import datetime
from typing import List, Optional

from psycopg2.extras import execute_values

from src.db.connection import get_connection
from src.services.embedding_service import EmbeddingResult

logger = logging.getLogger(__name__)


def store_embedding(
    conversation_id: str,
    embedding: List[float],
    pipeline_run_id: Optional[int] = None,
    model_version: str = "text-embedding-3-small",
) -> None:
    """
    Store a single conversation embedding.

    Args:
        conversation_id: Conversation ID
        embedding: 1536-dimensional embedding vector
        pipeline_run_id: Pipeline run ID for scoping
        model_version: Model used to generate embedding
    """
    if len(embedding) != 1536:
        raise ValueError(f"Embedding must be 1536 dimensions, got {len(embedding)}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Format embedding as pgvector array string
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            cur.execute(
                """
                INSERT INTO conversation_embeddings (
                    conversation_id, embedding, pipeline_run_id, model_version
                ) VALUES (%s, %s::vector, %s, %s)
                ON CONFLICT (conversation_id, pipeline_run_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model_version = EXCLUDED.model_version,
                    created_at = NOW()
            """,
                (conversation_id, embedding_str, pipeline_run_id, model_version),
            )
            conn.commit()


def store_embeddings_batch(
    results: List[EmbeddingResult],
    pipeline_run_id: Optional[int] = None,
    model_version: str = "text-embedding-3-small",
) -> int:
    """
    Store multiple conversation embeddings in a single batch operation.

    ~50x faster than individual inserts for large batches.

    Args:
        results: List of EmbeddingResult objects (only successful ones stored)
        pipeline_run_id: Pipeline run ID for scoping
        model_version: Model used to generate embeddings

    Returns:
        Number of embeddings stored
    """
    # Filter to successful results only
    successful_results = [r for r in results if r.success and r.embedding]

    if not successful_results:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Prepare rows for batch insert
            rows = []
            for result in successful_results:
                if len(result.embedding) != 1536:
                    logger.warning(
                        f"Skipping embedding for {result.conversation_id}: "
                        f"wrong dimensions ({len(result.embedding)})"
                    )
                    continue

                # Format embedding as pgvector array string
                embedding_str = "[" + ",".join(str(x) for x in result.embedding) + "]"

                rows.append(
                    (
                        result.conversation_id,
                        embedding_str,
                        pipeline_run_id,
                        model_version,
                    )
                )

            if not rows:
                return 0

            # Batch upsert
            sql = """
                INSERT INTO conversation_embeddings (
                    conversation_id, embedding, pipeline_run_id, model_version
                ) VALUES %s
                ON CONFLICT (conversation_id, pipeline_run_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model_version = EXCLUDED.model_version,
                    created_at = NOW()
            """

            # Custom template to cast embedding string to vector type
            execute_values(
                cur,
                sql,
                rows,
                template="(%s, %s::vector, %s, %s)",
            )
            conn.commit()

            logger.info(f"Stored {len(rows)} embeddings for run {pipeline_run_id}")
            return len(rows)


def get_embeddings_for_run(
    pipeline_run_id: int,
) -> List[dict]:
    """
    Get all embeddings for a pipeline run.

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        List of dicts with conversation_id and embedding
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id, embedding::text
                FROM conversation_embeddings
                WHERE pipeline_run_id = %s
                ORDER BY conversation_id
            """,
                (pipeline_run_id,),
            )
            rows = cur.fetchall()

    results = []
    for row in rows:
        # Parse pgvector string back to list
        embedding_str = row[1]
        if embedding_str.startswith("[") and embedding_str.endswith("]"):
            embedding = [float(x) for x in embedding_str[1:-1].split(",")]
        else:
            embedding = []

        results.append(
            {
                "conversation_id": row[0],
                "embedding": embedding,
            }
        )

    return results


def count_embeddings_for_run(pipeline_run_id: int) -> int:
    """
    Count embeddings for a pipeline run.

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        Number of embeddings
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM conversation_embeddings
                WHERE pipeline_run_id = %s
            """,
                (pipeline_run_id,),
            )
            result = cur.fetchone()
            return result[0] if result else 0
