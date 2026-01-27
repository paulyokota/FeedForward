"""
EmbeddingService: Generate and store conversation embeddings for hybrid clustering.

Uses OpenAI text-embedding-3-small (1536 dimensions) for semantic similarity.
Supports batched API calls for efficiency and async operation.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)

# Model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Batch size for OpenAI API calls (max ~2048 for embedding API, but 50 is safer for rate limits)
DEFAULT_BATCH_SIZE = 50

# Maximum characters per text input (text-embedding-3-small has 8191 token limit)
# Using ~4 chars per token heuristic, 8000 tokens * 4 = 32000 chars
MAX_TEXT_CHARS = 32000


def _sanitize_error_message(error: Exception) -> str:
    """
    Sanitize error message for safe logging and storage.

    Removes potentially sensitive information like API keys, endpoints,
    and internal system details from error messages.
    """
    error_str = str(error)

    # Map known error patterns to safe messages
    error_patterns = {
        "rate_limit": "Rate limit exceeded - please retry later",
        "invalid_api_key": "API authentication failed",
        "insufficient_quota": "API quota exceeded",
        "server_error": "OpenAI service temporarily unavailable",
        "connection": "Network connection error",
        "timeout": "Request timed out",
    }

    error_lower = error_str.lower()
    for pattern, safe_message in error_patterns.items():
        if pattern in error_lower:
            return safe_message

    # For unknown errors, return a generic message with error type
    error_type = type(error).__name__
    return f"Embedding generation failed ({error_type})"


@dataclass
class EmbeddingResult:
    """Result of embedding generation for a single conversation."""

    conversation_id: str
    embedding: List[float]
    success: bool
    error: Optional[str] = None


@dataclass
class BatchEmbeddingResult:
    """Result of batch embedding generation."""

    successful: List[EmbeddingResult]
    failed: List[EmbeddingResult]
    total_processed: int
    total_success: int
    total_failed: int


class EmbeddingService:
    """
    Service for generating conversation embeddings using OpenAI.

    Supports both synchronous and asynchronous batch operations.
    Designed for integration into the pipeline after classification.
    """

    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        model: str = EMBEDDING_MODEL,
    ):
        """
        Initialize the embedding service.

        Args:
            batch_size: Number of texts to embed per API call (default 50)
            model: OpenAI embedding model to use
        """
        self.batch_size = batch_size
        self.model = model
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None

    @property
    def sync_client(self) -> OpenAI:
        """Lazy-initialize sync OpenAI client."""
        if self._sync_client is None:
            self._sync_client = OpenAI()
        return self._sync_client

    @property
    def async_client(self) -> AsyncOpenAI:
        """Lazy-initialize async OpenAI client."""
        if self._async_client is None:
            self._async_client = AsyncOpenAI()
        return self._async_client

    def _truncate_text(self, text: str) -> str:
        """Truncate text to maximum allowed length."""
        if len(text) > MAX_TEXT_CHARS:
            return text[:MAX_TEXT_CHARS]
        return text

    def _prepare_text(
        self,
        source_body: str,
        excerpt: Optional[str] = None,
        customer_digest: Optional[str] = None
    ) -> str:
        """
        Select best available text source for embedding (priority fallback).

        Priority (Issue #139):
        1. customer_digest if available (includes most specific customer message)
        2. excerpt if available (focused text)
        3. source_body as fallback (first customer message only)

        Returns empty string if none are available.
        """
        # Priority 1: Customer digest (Issue #139)
        if customer_digest and customer_digest.strip():
            return self._truncate_text(customer_digest.strip())

        # Log fallback when digest was expected but empty/missing
        if customer_digest is not None:
            logger.debug("customer_digest was empty/whitespace, falling back to excerpt/source_body")

        # Priority 2: Excerpt
        if excerpt and excerpt.strip():
            return self._truncate_text(excerpt.strip())

        # Priority 3: Source body
        if source_body and source_body.strip():
            return self._truncate_text(source_body.strip())

        return ""

    def generate_embeddings_sync(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """
        Generate embeddings synchronously for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (1536 dimensions each)

        Raises:
            ValueError: If texts is empty or contains only empty strings
        """
        if not texts:
            return []

        # Filter out empty texts
        non_empty_texts = [self._truncate_text(t) for t in texts if t and t.strip()]
        if not non_empty_texts:
            raise ValueError("All provided texts are empty")

        all_embeddings: List[List[float]] = []

        for i in range(0, len(non_empty_texts), self.batch_size):
            batch = non_empty_texts[i : i + self.batch_size]

            logger.info(
                f"Generating embeddings for batch {i // self.batch_size + 1}/"
                f"{(len(non_empty_texts) - 1) // self.batch_size + 1}"
            )

            response = self.sync_client.embeddings.create(
                model=self.model,
                input=batch,
            )

            # Sort by index to ensure correct ordering (OpenAI may return in any order)
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [data.embedding for data in sorted_data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def generate_embeddings_async(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """
        Generate embeddings asynchronously for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (1536 dimensions each)

        Raises:
            ValueError: If texts is empty or contains only empty strings
        """
        if not texts:
            return []

        # Filter out empty texts
        non_empty_texts = [self._truncate_text(t) for t in texts if t and t.strip()]
        if not non_empty_texts:
            raise ValueError("All provided texts are empty")

        all_embeddings: List[List[float]] = []

        for i in range(0, len(non_empty_texts), self.batch_size):
            batch = non_empty_texts[i : i + self.batch_size]

            logger.info(
                f"Generating embeddings for batch {i // self.batch_size + 1}/"
                f"{(len(non_empty_texts) - 1) // self.batch_size + 1}"
            )

            response = await self.async_client.embeddings.create(
                model=self.model,
                input=batch,
            )

            # Sort by index to ensure correct ordering (OpenAI may return in any order)
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [data.embedding for data in sorted_data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def generate_conversation_embeddings_async(
        self,
        conversations: List[dict],
        stop_checker: Optional[Callable[[], bool]] = None,
    ) -> BatchEmbeddingResult:
        """
        Generate embeddings for a list of conversations.

        Args:
            conversations: List of conversation dicts with keys:
                - id: Conversation ID
                - source_body: Full conversation text
                - excerpt (optional): Focused excerpt for embedding
            stop_checker: Optional callback to check for stop signal

        Returns:
            BatchEmbeddingResult with successful and failed embeddings
        """
        if not conversations:
            return BatchEmbeddingResult(
                successful=[],
                failed=[],
                total_processed=0,
                total_success=0,
                total_failed=0,
            )

        successful: List[EmbeddingResult] = []
        failed: List[EmbeddingResult] = []

        # Prepare texts and track conversation IDs
        texts: List[str] = []
        conv_ids: List[str] = []

        for conv in conversations:
            if stop_checker and stop_checker():
                logger.info("Stop signal received during embedding preparation")
                break

            conv_id = conv.get("id", "")
            source_body = conv.get("source_body", "")
            excerpt = conv.get("excerpt")
            customer_digest = conv.get("customer_digest")  # Issue #139

            text = self._prepare_text(source_body, excerpt, customer_digest)

            if not text:
                failed.append(
                    EmbeddingResult(
                        conversation_id=conv_id,
                        embedding=[],
                        success=False,
                        error="Empty text after preparation",
                    )
                )
                continue

            texts.append(text)
            conv_ids.append(conv_id)

        if not texts:
            return BatchEmbeddingResult(
                successful=successful,
                failed=failed,
                total_processed=len(conversations),
                total_success=0,
                total_failed=len(failed),
            )

        # Generate embeddings in batches
        try:
            for i in range(0, len(texts), self.batch_size):
                if stop_checker and stop_checker():
                    logger.info("Stop signal received during embedding generation")
                    # Mark remaining as failed
                    for j in range(i, len(texts)):
                        failed.append(
                            EmbeddingResult(
                                conversation_id=conv_ids[j],
                                embedding=[],
                                success=False,
                                error="Stopped by user",
                            )
                        )
                    break

                batch_texts = texts[i : i + self.batch_size]
                batch_ids = conv_ids[i : i + self.batch_size]

                logger.info(
                    f"Generating embeddings for batch {i // self.batch_size + 1}/"
                    f"{(len(texts) - 1) // self.batch_size + 1} "
                    f"({len(batch_texts)} conversations)"
                )

                try:
                    response = await self.async_client.embeddings.create(
                        model=self.model,
                        input=batch_texts,
                    )

                    # Sort by index to ensure correct ordering (OpenAI may return in any order)
                    sorted_data = sorted(response.data, key=lambda x: x.index)

                    # Map embeddings back to conversation IDs using sorted order
                    for data in sorted_data:
                        successful.append(
                            EmbeddingResult(
                                conversation_id=batch_ids[data.index],
                                embedding=data.embedding,
                                success=True,
                            )
                        )

                except Exception as e:
                    # Log full error for debugging, but store sanitized message
                    logger.warning(f"Batch embedding failed: {e}")
                    sanitized_error = _sanitize_error_message(e)
                    # Mark entire batch as failed
                    for conv_id in batch_ids:
                        failed.append(
                            EmbeddingResult(
                                conversation_id=conv_id,
                                embedding=[],
                                success=False,
                                error=sanitized_error,
                            )
                        )

        except Exception as e:
            # Log full error for debugging, but store sanitized message
            logger.error(f"Embedding generation failed: {e}")
            sanitized_error = _sanitize_error_message(e)
            # Mark all remaining as failed
            for conv_id in conv_ids[len(successful) + len(failed) :]:
                failed.append(
                    EmbeddingResult(
                        conversation_id=conv_id,
                        embedding=[],
                        success=False,
                        error=sanitized_error,
                    )
                )

        return BatchEmbeddingResult(
            successful=successful,
            failed=failed,
            total_processed=len(conversations),
            total_success=len(successful),
            total_failed=len(failed),
        )

    def generate_conversation_embeddings_sync(
        self,
        conversations: List[dict],
        stop_checker: Optional[Callable[[], bool]] = None,
    ) -> BatchEmbeddingResult:
        """
        Synchronous wrapper for generate_conversation_embeddings_async.

        Useful for non-async contexts like tests.
        """
        return asyncio.run(
            self.generate_conversation_embeddings_async(conversations, stop_checker)
        )
