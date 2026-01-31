"""
Unified Search Service

Provides semantic search across all embedded content sources using pgvector.

IMPORTANT: This service MUST use the same embedding model as EmbeddingPipeline.
Vector similarity only works when embeddings are generated with the same model.
Both services read from config/research_search.yaml to ensure alignment.

If you change the model in config:
1. All existing embeddings become incompatible with search queries
2. You MUST re-run the embedding pipeline to re-index all content
3. Use the /api/research/stats endpoint to verify the current model
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

import yaml
from openai import OpenAI

from .models import (
    SearchableContent,
    UnifiedSearchResult,
    UnifiedSearchRequest,
    SimilarContentRequest,
    EmbeddingStats,
)

logger = logging.getLogger(__name__)

# Resolves to {project_root}/config/research_search.yaml
# Path: this file → research/ → src/ → project_root/
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "research_search.yaml"

# Valid OpenAI embedding models - validated to prevent config errors
VALID_EMBEDDING_MODELS = {
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
}


class EmbeddingServiceError(Exception):
    """Raised when embedding generation fails."""
    pass


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


class UnifiedSearchService:
    """
    Unified search service using pgvector for semantic similarity.

    Provides:
    - Semantic search across all sources
    - "More like this" similarity search
    - Source-type filtering
    - Graceful degradation on errors
    """

    def __init__(
        self,
        embedding_model: Optional[str] = None,
        embedding_dimensions: Optional[int] = None,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize the search service.

        Configuration precedence: explicit params > config file > hardcoded defaults.
        This ensures both UnifiedSearchService and EmbeddingPipeline use the same
        model from config by default, while allowing overrides for testing.

        Args:
            embedding_model: OpenAI embedding model name (defaults to config)
            embedding_dimensions: Vector dimensions (defaults to config)
            config_path: Path to configuration YAML (for testing)
        """
        self._client = OpenAI()
        self._config = self._load_config(config_path or CONFIG_PATH)

        # Apply config values, allowing explicit overrides
        embedding_config = self._config["embedding"]
        self._embedding_model = embedding_model or embedding_config["model"]
        self._embedding_dimensions = embedding_dimensions or embedding_config["dimensions"]

        # Validate model name to catch config errors early
        if self._embedding_model not in VALID_EMBEDDING_MODELS:
            logger.warning(
                f"Unknown embedding model: {self._embedding_model}. "
                f"Valid models: {VALID_EMBEDDING_MODELS}"
            )

        # Validate dimensions
        if not (1 <= self._embedding_dimensions <= 4096):
            raise ValueError(f"Invalid embedding dimensions: {self._embedding_dimensions}")

        logger.info(f"Search service initialized with model: {self._embedding_model}")

    def _load_config(self, path: Path) -> dict:
        """
        Load configuration from YAML file.

        Merges loaded config with defaults. If config file is missing or malformed,
        falls back to hardcoded defaults (same as EmbeddingPipeline).

        IMPORTANT: Default values here MUST match those in EmbeddingPipeline._load_config()
        to ensure alignment when config file is unavailable.
        """
        defaults = {
            "embedding": {
                "model": "text-embedding-3-small",
                "dimensions": 1536,
            },
            "search": {
                "default_limit": 20,
                "max_limit": 100,
                "default_min_similarity": 0.5,
                "server_min_similarity": 0.3,
            },
            "context_augmentation": {
                "max_results": 3,
                "max_tokens": 500,
            },
            "evidence_suggestion": {
                "min_similarity": 0.7,
                "max_suggestions": 5,
            },
        }

        if path.exists():
            try:
                with open(path) as f:
                    loaded = yaml.safe_load(f)
                    if loaded:
                        # Merge with defaults (type-safe)
                        for key in defaults:
                            if key in loaded and isinstance(loaded[key], dict):
                                defaults[key].update(loaded[key])
                            elif key in loaded:
                                logger.warning(
                                    f"Config key '{key}' should be a dict, got {type(loaded[key]).__name__}"
                                )
                        return defaults
            except Exception as e:
                logger.error(
                    f"Failed to load config from {path}: {e}. "
                    f"Using hardcoded defaults. Check config file format."
                )

        return defaults

    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding vector for text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector

        Raises:
            EmbeddingServiceError: If embedding generation fails
        """
        try:
            # Truncate very long text to avoid token limits
            max_chars = 8000 * 4  # Approximate token limit
            if len(text) > max_chars:
                text = text[:max_chars]

            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=text,
                dimensions=self._embedding_dimensions,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise EmbeddingServiceError(f"Embedding generation failed: {e}")

    def search(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        source_types: Optional[List[str]] = None,
        min_similarity: float = 0.5,
    ) -> List[UnifiedSearchResult]:
        """
        Search for content semantically similar to query.

        Args:
            query: Search query text
            limit: Maximum results to return
            offset: Results to skip for pagination
            source_types: Filter by source types (e.g., ['coda_page', 'intercom'])
            min_similarity: Minimum similarity threshold

        Returns:
            List of search results ordered by similarity

        Note: Returns empty list on errors (graceful degradation)
        """
        try:
            # Enforce server-side limits
            config = self._config["search"]
            limit = min(limit, config["max_limit"])
            min_similarity = max(min_similarity, config["server_min_similarity"])

            # Get query embedding
            query_embedding = self.get_embedding(query)

            return self._vector_search(
                embedding=query_embedding,
                limit=limit,
                offset=offset,
                source_types=source_types,
                min_similarity=min_similarity,
            )
        except EmbeddingServiceError as e:
            logger.warning(f"Embedding service unavailable: {e}")
            return []
        except DatabaseError as e:
            logger.error(f"Database error in search: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in search: {e}")
            return []

    def _vector_search(
        self,
        embedding: List[float],
        limit: int,
        offset: int = 0,
        source_types: Optional[List[str]] = None,
        min_similarity: float = 0.5,
        exclude_id: Optional[int] = None,
    ) -> List[UnifiedSearchResult]:
        """
        Perform vector similarity search in PostgreSQL.

        Uses pgvector's cosine distance operator for similarity.
        """
        try:
            from src.db.connection import get_connection

            # Build query with optional source type filter
            params = [embedding, min_similarity, limit, offset]

            source_filter = ""
            if source_types:
                placeholders = ", ".join(["%s"] * len(source_types))
                source_filter = f"AND source_type IN ({placeholders})"
                params = [embedding, min_similarity] + source_types + [limit, offset]

            exclude_filter = ""
            if exclude_id:
                exclude_filter = "AND id != %s"
                params.insert(-2, exclude_id)  # Insert before limit and offset

            # Use 1 - cosine distance = cosine similarity
            query = f"""
                SELECT
                    id,
                    source_type,
                    source_id,
                    title,
                    content,
                    1 - (embedding <=> %s::vector) as similarity,
                    metadata
                FROM research_embeddings
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> %s::vector) >= %s
                  {source_filter}
                  {exclude_filter}
                ORDER BY embedding <=> %s::vector
                LIMIT %s OFFSET %s
            """

            # Need to pass embedding twice (once for similarity, once for WHERE, once for ORDER BY)
            final_params = [embedding] + params[:1] + params[1:]
            final_params.insert(3, embedding)  # For ORDER BY

            # Rebuild params correctly
            if source_types:
                final_params = [
                    embedding,  # For similarity calculation
                    embedding,  # For WHERE clause
                    min_similarity,
                ] + source_types
                if exclude_id:
                    final_params.append(exclude_id)
                final_params.extend([embedding, limit, offset])  # For ORDER BY, LIMIT, OFFSET
            else:
                final_params = [
                    embedding,  # For similarity
                    embedding,  # For WHERE
                    min_similarity,
                ]
                if exclude_id:
                    final_params.append(exclude_id)
                final_params.extend([embedding, limit, offset])

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, final_params)
                    rows = cur.fetchall()

                    return [
                        UnifiedSearchResult(
                            id=row[0],
                            source_type=row[1],
                            source_id=row[2],
                            title=row[3] or "Untitled",
                            snippet=self._create_snippet(row[4]),
                            similarity=float(row[5]),
                            url=self._build_url(row[1], row[2]),
                            metadata=row[6] or {},
                        )
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise DatabaseError(f"Vector search failed: {e}")

    def search_similar(
        self,
        source_type: str,
        source_id: str,
        limit: int = 10,
        exclude_same_source: bool = False,
        min_similarity: float = 0.5,
    ) -> List[UnifiedSearchResult]:
        """
        Find content similar to a specific item ("more like this").

        Args:
            source_type: Source type of reference item
            source_id: ID of reference item
            limit: Maximum results to return
            exclude_same_source: Exclude items from same source type
            min_similarity: Minimum similarity threshold

        Returns:
            List of similar items ordered by similarity
        """
        try:
            from src.db.connection import get_connection

            # Get the embedding for the reference item
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, embedding
                        FROM research_embeddings
                        WHERE source_type = %s AND source_id = %s
                    """, (source_type, source_id))
                    row = cur.fetchone()

                    if not row:
                        logger.warning(f"Reference item not found: {source_type}/{source_id}")
                        return []

                    ref_id, embedding = row

            if not embedding:
                logger.warning(f"Reference item has no embedding: {source_type}/{source_id}")
                return []

            # Search for similar items
            source_filter = None
            if exclude_same_source:
                # Get all source types except the reference
                source_filter = self._get_other_source_types(source_type)

            return self._vector_search(
                embedding=embedding,
                limit=limit,
                source_types=source_filter,
                min_similarity=min_similarity,
                exclude_id=ref_id,
            )
        except Exception as e:
            logger.error(f"Similar search failed: {e}")
            return []

    def _get_other_source_types(self, exclude_type: str) -> List[str]:
        """Get all source types except the specified one."""
        all_types = ["coda_page", "coda_theme", "intercom"]
        return [t for t in all_types if t != exclude_type]

    def get_stats(self) -> EmbeddingStats:
        """Get statistics about embeddings."""
        try:
            from src.db.connection import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Total count
                    cur.execute("SELECT COUNT(*) FROM research_embeddings")
                    total = cur.fetchone()[0]

                    # Count by source type
                    cur.execute("""
                        SELECT source_type, COUNT(*)
                        FROM research_embeddings
                        GROUP BY source_type
                    """)
                    by_type = {row[0]: row[1] for row in cur.fetchall()}

                    # Last updated
                    cur.execute("""
                        SELECT MAX(updated_at) FROM research_embeddings
                    """)
                    last_updated = cur.fetchone()[0]

                    return EmbeddingStats(
                        total_embeddings=total,
                        by_source_type=by_type,
                        last_updated=last_updated,
                        embedding_model=self._embedding_model,
                        embedding_dimensions=self._embedding_dimensions,
                    )
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return EmbeddingStats(
                total_embeddings=0,
                by_source_type={},
                last_updated=None,
                embedding_model=self._embedding_model,
                embedding_dimensions=self._embedding_dimensions,
            )

    @staticmethod
    def _create_snippet(content: str, max_length: int = 200) -> str:
        """Create a snippet from content."""
        if not content:
            return ""

        if len(content) <= max_length:
            return content

        # Find a good break point
        truncated = content[:max_length]
        last_period = truncated.rfind('.')
        last_space = truncated.rfind(' ')

        if last_period > max_length * 0.5:
            return truncated[:last_period + 1]
        elif last_space > max_length * 0.5:
            return truncated[:last_space] + '...'
        else:
            return truncated + '...'

    @staticmethod
    def _build_url(source_type: str, source_id: str) -> str:
        """Build URL for a source item."""
        doc_id = os.getenv("CODA_DOC_ID", "")

        if source_type == "coda_page":
            return f"https://coda.io/d/{doc_id}/_/{source_id}"
        elif source_type == "coda_theme":
            return f"https://coda.io/d/{doc_id}#theme_{source_id}"
        elif source_type == "intercom":
            return f"https://app.intercom.com/a/inbox/_/inbox/conversation/{source_id}"
        else:
            return ""

    def search_for_context(
        self,
        query: str,
        max_results: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> List[UnifiedSearchResult]:
        """
        Search for context augmentation (used by ThemeExtractor).

        Only searches Coda sources (not Intercom to avoid circular references).

        Args:
            query: Search query (typically conversation text)
            max_results: Maximum results (defaults to config)
            max_tokens: Token budget (defaults to config)

        Returns:
            List of research results for context
        """
        config = self._config["context_augmentation"]
        max_results = max_results or config["max_results"]

        return self.search(
            query=query[:500],  # Limit query length
            limit=max_results,
            source_types=["coda_page", "coda_theme"],  # Exclude intercom
            min_similarity=0.5,
        )

    def suggest_evidence(
        self,
        query: str,
        min_similarity: Optional[float] = None,
        max_suggestions: Optional[int] = None,
    ) -> List[UnifiedSearchResult]:
        """
        Find research evidence for a story.

        Args:
            query: Story title + description
            min_similarity: Threshold (defaults to config)
            max_suggestions: Maximum suggestions (defaults to config)

        Returns:
            List of suggested research evidence
        """
        config = self._config["evidence_suggestion"]
        min_similarity = min_similarity or config["min_similarity"]
        max_suggestions = max_suggestions or config["max_suggestions"]

        return self.search(
            query=query,
            limit=max_suggestions,
            source_types=["coda_page", "coda_theme"],  # Research only
            min_similarity=min_similarity,
        )
