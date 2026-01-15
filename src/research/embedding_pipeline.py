"""
Embedding Pipeline

Batch embedding generation for research content.
Handles extraction from all sources and upserting to PostgreSQL.
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import yaml
from openai import OpenAI
from psycopg2.extras import execute_values

from .adapters import CodaSearchAdapter, IntercomSearchAdapter, SearchSourceAdapter
from .adapters.coda_adapter import get_coda_adapters
from .models import SearchableContent, ReindexResponse

logger = logging.getLogger(__name__)

# Configuration path
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "research_search.yaml"


class EmbeddingPipeline:
    """
    Batch embedding generation pipeline.

    Extracts content from all sources, generates embeddings,
    and upserts to the research_embeddings table.
    """

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-large",
        embedding_dimensions: int = 1536,
        batch_size: int = 100,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize the embedding pipeline.

        Args:
            embedding_model: OpenAI embedding model name
            embedding_dimensions: Vector dimensions
            batch_size: Items per embedding API call
            config_path: Path to configuration YAML
        """
        self._client = OpenAI()
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._batch_size = batch_size
        self._config = self._load_config(config_path or CONFIG_PATH)

        # Initialize adapters
        self._adapters: List[SearchSourceAdapter] = []

    def _load_config(self, path: Path) -> dict:
        """Load configuration from YAML file."""
        defaults = {
            "embedding": {
                "model": "text-embedding-3-large",
                "dimensions": 1536,
                "batch_size": 100,
            },
        }

        if path.exists():
            try:
                with open(path) as f:
                    loaded = yaml.safe_load(f)
                    if loaded and "embedding" in loaded:
                        defaults["embedding"].update(loaded["embedding"])
            except Exception as e:
                logger.warning(f"Failed to load config from {path}: {e}")

        return defaults

    def register_adapter(self, adapter: SearchSourceAdapter) -> None:
        """Register a source adapter."""
        self._adapters.append(adapter)
        logger.info(f"Registered adapter: {adapter.get_source_type()}")

    def register_default_adapters(self) -> None:
        """Register all default adapters."""
        # Coda adapters (pages and themes)
        for adapter in get_coda_adapters():
            self.register_adapter(adapter)

        # Intercom adapter
        self.register_adapter(IntercomSearchAdapter())

        logger.info(f"Registered {len(self._adapters)} default adapters")

    def run(
        self,
        source_types: Optional[List[str]] = None,
        force: bool = False,
        limit: Optional[int] = None,
    ) -> ReindexResponse:
        """
        Run the embedding pipeline.

        Args:
            source_types: Filter to specific sources (None = all)
            force: Force re-embed even if content unchanged
            limit: Maximum items per source (for testing)

        Returns:
            ReindexResponse with statistics
        """
        start_time = time.time()

        if not self._adapters:
            self.register_default_adapters()

        # Filter adapters if specific sources requested
        adapters = self._adapters
        if source_types:
            adapters = [a for a in adapters if a.get_source_type() in source_types]

        if not adapters:
            return ReindexResponse(
                status="failed",
                source_types=source_types or [],
                error="No adapters registered for specified source types",
            )

        total_processed = 0
        total_updated = 0
        total_failed = 0
        processed_source_types = []

        try:
            from src.db.connection import get_connection

            with get_connection() as conn:
                for adapter in adapters:
                    source_type = adapter.get_source_type()
                    processed_source_types.append(source_type)

                    logger.info(f"Processing source: {source_type}")

                    try:
                        processed, updated, failed = self._process_adapter(
                            conn=conn,
                            adapter=adapter,
                            force=force,
                            limit=limit,
                        )
                        total_processed += processed
                        total_updated += updated
                        total_failed += failed

                        logger.info(
                            f"Completed {source_type}: "
                            f"processed={processed}, updated={updated}, failed={failed}"
                        )
                    except Exception as e:
                        logger.error(f"Failed processing {source_type}: {e}")
                        total_failed += 1

            duration = time.time() - start_time

            return ReindexResponse(
                status="completed",
                source_types=processed_source_types,
                items_processed=total_processed,
                items_updated=total_updated,
                items_failed=total_failed,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return ReindexResponse(
                status="failed",
                source_types=processed_source_types,
                items_processed=total_processed,
                items_updated=total_updated,
                items_failed=total_failed,
                duration_seconds=time.time() - start_time,
                error=str(e),
            )

    def _process_adapter(
        self,
        conn,
        adapter: SearchSourceAdapter,
        force: bool,
        limit: Optional[int],
    ) -> Tuple[int, int, int]:
        """
        Process a single adapter.

        Returns:
            Tuple of (processed, updated, failed) counts
        """
        processed = 0
        updated = 0
        failed = 0

        batch: List[SearchableContent] = []

        for content in adapter.extract_all(limit=limit):
            batch.append(content)
            processed += 1

            if len(batch) >= self._batch_size:
                batch_updated, batch_failed = self._process_batch(conn, batch, force)
                updated += batch_updated
                failed += batch_failed
                batch = []

        # Process remaining items
        if batch:
            batch_updated, batch_failed = self._process_batch(conn, batch, force)
            updated += batch_updated
            failed += batch_failed

        return processed, updated, failed

    def _process_batch(
        self,
        conn,
        batch: List[SearchableContent],
        force: bool,
    ) -> Tuple[int, int]:
        """
        Process a batch of content items.

        Returns:
            Tuple of (updated, failed) counts
        """
        updated = 0
        failed = 0

        # Compute content hashes
        items_with_hash = []
        for item in batch:
            content_hash = hashlib.sha256(item.content.encode('utf-8')).hexdigest()
            items_with_hash.append((item, content_hash))

        if not force:
            # Check which items need updating
            items_to_embed = self._filter_unchanged(conn, items_with_hash)
        else:
            items_to_embed = items_with_hash

        if not items_to_embed:
            return 0, 0

        # Generate embeddings in batch
        try:
            texts = [item.content for item, _ in items_to_embed]
            embeddings = self._generate_embeddings_batch(texts)

            # Prepare data for upsert
            rows = []
            for (item, content_hash), embedding in zip(items_to_embed, embeddings):
                if embedding:
                    rows.append((
                        item.source_type,
                        item.source_id,
                        content_hash,
                        item.title,
                        item.content,
                        embedding,
                        item.metadata,
                    ))
                    updated += 1
                else:
                    failed += 1

            # Upsert to database
            if rows:
                self._upsert_embeddings(conn, rows)

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            failed = len(items_to_embed)

        return updated, failed

    def _filter_unchanged(
        self,
        conn,
        items_with_hash: List[Tuple[SearchableContent, str]],
    ) -> List[Tuple[SearchableContent, str]]:
        """Filter out items that haven't changed (same content hash)."""
        if not items_with_hash:
            return []

        # Get existing hashes
        source_keys = [
            (item.source_type, item.source_id)
            for item, _ in items_with_hash
        ]

        with conn.cursor() as cur:
            # Build query for multiple items
            placeholders = ", ".join(
                [f"(%s, %s)"] * len(source_keys)
            )
            flat_keys = [val for pair in source_keys for val in pair]

            cur.execute(f"""
                SELECT source_type, source_id, content_hash
                FROM research_embeddings
                WHERE (source_type, source_id) IN ({placeholders})
            """, flat_keys)

            existing = {
                (row[0], row[1]): row[2]
                for row in cur.fetchall()
            }

        # Filter to items that are new or changed
        return [
            (item, content_hash)
            for item, content_hash in items_with_hash
            if existing.get((item.source_type, item.source_id)) != content_hash
        ]

    def _generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []

        try:
            # Truncate very long texts
            max_chars = 8000 * 4  # Approximate token limit
            truncated_texts = [
                text[:max_chars] if len(text) > max_chars else text
                for text in texts
            ]

            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=truncated_texts,
            )

            return [data.embedding for data in response.data]

        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            return [None] * len(texts)

    def _upsert_embeddings(
        self,
        conn,
        rows: List[Tuple],
    ) -> None:
        """Upsert embeddings to database."""
        from psycopg2.extras import Json

        with conn.cursor() as cur:
            # Use execute_values for efficient bulk upsert
            sql = """
                INSERT INTO research_embeddings (
                    source_type, source_id, content_hash,
                    title, content, embedding, metadata
                ) VALUES %s
                ON CONFLICT (source_type, source_id) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """

            # Convert embeddings to proper format and metadata to Json
            formatted_rows = [
                (
                    source_type,
                    source_id,
                    content_hash,
                    title,
                    content,
                    embedding,  # pgvector handles list conversion
                    Json(metadata) if metadata else None,
                )
                for source_type, source_id, content_hash, title, content, embedding, metadata in rows
            ]

            execute_values(cur, sql, formatted_rows)

        conn.commit()
        logger.debug(f"Upserted {len(rows)} embeddings")


def run_embedding_pipeline(
    source_types: Optional[List[str]] = None,
    force: bool = False,
    limit: Optional[int] = None,
) -> ReindexResponse:
    """
    Convenience function to run the embedding pipeline.

    Args:
        source_types: Filter to specific sources (None = all)
        force: Force re-embed even if content unchanged
        limit: Maximum items per source (for testing)

    Returns:
        ReindexResponse with statistics
    """
    pipeline = EmbeddingPipeline()
    return pipeline.run(source_types=source_types, force=force, limit=limit)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Run embedding pipeline")
    parser.add_argument("--source", type=str, help="Specific source type to process")
    parser.add_argument("--force", action="store_true", help="Force re-embed all")
    parser.add_argument("--limit", type=int, help="Max items per source")

    args = parser.parse_args()

    source_types = [args.source] if args.source else None

    result = run_embedding_pipeline(
        source_types=source_types,
        force=args.force,
        limit=args.limit,
    )

    print(f"\nPipeline Result:")
    print(f"  Status: {result.status}")
    print(f"  Sources: {', '.join(result.source_types)}")
    print(f"  Processed: {result.items_processed}")
    print(f"  Updated: {result.items_updated}")
    print(f"  Failed: {result.items_failed}")
    if result.duration_seconds:
        print(f"  Duration: {result.duration_seconds:.2f}s")
    if result.error:
        print(f"  Error: {result.error}")
